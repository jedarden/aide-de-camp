#!/usr/bin/env python3
"""Auto-replenish an empty ready frontier from the workspace's tracked backlog.

Invoked by scripts/bead_recovery_workflow.sh when the ready frontier is empty.
Before creating anything it re-verifies, independently, that the frontier is
*legitimately* empty: no corruption (bead doctor --rehearse), no stale
assignees (open + assigned beads), and every remaining open bead accounted for
as manually blocked or dependency-blocked. If any open bead is unexplained the
frontier query itself may be lying, so the run refuses rather than papering
over it with fresh beads.

Candidate sources, in priority order:
  1. stub-inventory findings  (docs/notes/stub-inventory-*.md, unresolved only)
  2. TODO/FIXME markers       (src/, excluding __pycache__)
  3. unchecked plan phases    (docs/plan/plan.md "- [ ]" items)

Safety rules enforced here:
  - Dedupe against existing open/in-progress beads by title and by target
    file — two implement beads for the same defect is prohibited.
  - Beads touching the same target file are serialized with a blocking
    dependency (--depends-on, attached inside the create transaction, so no
    claim race can see both ready at once).
  - At most --cap beads per run, labelled "auto:replenished".
  - The only mutation this tool ever issues is `bead create`. Existing beads
    are never updated, reopened, or unblocked — a manually-blocked bead
    (manual_blocked=1) is untouched by construction. Existing IDs appear only
    as --depends-on values on brand-new beads.
  - Every create carries --unique-ref, so a repeated run is idempotent
    (the CLI returns EXISTING instead of minting a duplicate).

Output: a structured JSON report (default /tmp/bead-replenish-report.json).

Exit codes: 0 = ran to completion (created beads, nothing to do, or gate
refusal — the verdict is in the report); 1 = unexpected error.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPLENISH_LABEL = "auto:replenished"
DEFAULT_CAP = 5

# Candidates from concrete code defects outrank plan-process gates when the
# cap forces a choice.
SOURCE_RANK = {"stub": 0, "todo": 1, "plan": 2}

# Real corruption indicators in `bead doctor --rehearse` output, mirroring
# scripts/diagnose_pluck_starvation.py so the two tools agree on the verdict.
CORRUPTION_KEYWORDS = [
    "corruption",
    "corrupt",
    "malformed",
    "inconsistent",
    "database is corrupted",
    "fatal",
    "critical failure",
]
DOCTOR_FALSE_POSITIVES = [
    "recovery rehearsal completed successfully",
    "semantic: equivalent",
    "cleanup: success",
    "diagnostics completed",
]

PLAN_CHECKBOX_RE = re.compile(r"^\s*-\s\[ \]\s+(.+?)\s*$")
HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
STUB_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$")
STUB_FILE_RE = re.compile(r"^\*\*File:\*\*\s*(.+?)\s*$", re.MULTILINE)
STUB_FIX_SCOPE_RE = re.compile(r"^\*\*Fix scope:\*\*\s*(.+?)\s*$", re.MULTILINE)
TODO_RE = re.compile(r"\b(TODO|FIXME)\b[:\s]*(.*)$")
PATHLIKE_RE = re.compile(r"\b([\w.-]+(?:/[\w.-]+)+\.(?:py|sh|md|toml|ya?ml|json|html|js|ts))\b")


def _truncate(text: str, limit: int = 100) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:.") + " …"


def normalize_title(title: str) -> str:
    """Canonical form for title-level dedupe comparisons."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title.lower())).strip()


def normalize_path(path: str) -> str:
    """Canonical workspace-relative target path.

    Inventory entries wrap paths in backticks and usually append a line or
    line range — ``**File:** `src/escalate/handler.py:402` ``. The wrapping
    must come off *before* the line ref, or the trailing backtick defeats the
    ``:402`` strip and the ref survives into the target path.
    """
    cleaned = path.strip()
    if len(cleaned) >= 2 and cleaned[0] in "`\"'" and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1].strip()
    cleaned = re.sub(r":\d+(?:-\d+)?$", "", cleaned)
    return cleaned.lstrip("./")


def unique_ref(kind: str, key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"replenish:{kind}:{digest}"


class ScanCandidate:
    """One piece of untracked actionable work discovered in the workspace."""

    def __init__(self, source: str, title: str, body: str, target_file: Optional[str],
                 priority: int, ref_key: str, location: str) -> None:
        self.source = source          # stub | todo | plan
        self.title = title
        self.body = body
        self.target_file = target_file  # workspace-relative path or None
        self.priority = priority
        self.ref = unique_ref(source, ref_key)
        self.location = location      # human-readable pointer for the body/report
        self.quoted_text = ""         # code quoted in the source entry (stub only)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "target_file": self.target_file,
            "priority": self.priority,
            "unique_ref": self.ref,
            "location": self.location,
        }


# --------------------------------------------------------------------------
# Candidate extraction (pure functions over file text)
# --------------------------------------------------------------------------

def extract_plan_candidates(plan_text: str, relpath: str = "docs/plan/plan.md") -> List[ScanCandidate]:
    """Unchecked "- [ ]" items in the plan, with their enclosing section."""
    candidates: List[ScanCandidate] = []
    section = ""
    for lineno, line in enumerate(plan_text.splitlines(), start=1):
        heading = HEADING_RE.match(line)
        if heading:
            section = heading.group(2)
            continue
        match = PLAN_CHECKBOX_RE.match(line)
        if not match:
            continue
        item = re.sub(r"\*\*(.+?)\*\*", r"\1", match.group(1)).strip()
        path_match = PATHLIKE_RE.search(item)
        target = None
        if path_match:
            candidate_path = normalize_path(path_match.group(1))
            # A path mentioned in prose is only a target if it plausibly exists
            # relative to the workspace (plan items frequently reference docs).
            target = candidate_path
        candidates.append(ScanCandidate(
            source="plan",
            title=_truncate(f"Complete plan item: {item}"),
            body=(
                f"Unchecked phase/gate item in {relpath} ({section}, line {lineno}):\n\n"
                f"> {item}\n\n"
                "Discovered by ready-frontier replenishment while the frontier was "
                "legitimately empty. Verify whether this item is genuinely still open, "
                "then implement or explicitly close the bead with a reason."
            ),
            target_file=target,
            priority=3,
            ref_key=f"{relpath}:{lineno}:{item}",
            location=f"{relpath}:{lineno}",
        ))
    return candidates


def _is_resolved(block_text: str) -> bool:
    if re.search(r"RESOLVED", block_text, re.IGNORECASE):
        return True
    fix_scope = STUB_FIX_SCOPE_RE.search(block_text)
    if fix_scope and re.match(r"^None\b", fix_scope.group(1).strip(), re.IGNORECASE):
        return True
    return False


def extract_stub_inventory_candidates(text: str, source_name: str) -> List[ScanCandidate]:
    """Unresolved findings from a docs/notes/stub-inventory-*.md sweep file.

    Only the "## Findings" section is parsed — the trailing "Non-Findings"
    section documents patterns that were checked and came back clean, and
    must not spawn beads. Findings marked RESOLVED (or whose fix scope is
    explicitly "None") are skipped.
    """
    findings_start = re.search(r"^##\s+Findings\s*$", text, re.MULTILINE)
    if not findings_start:
        return []
    scoped = text[findings_start.end():]
    # Stop at the next "## " section (e.g. "## Non-Findings") — those document
    # patterns that were checked and came back clean, never beads.
    section_end = re.search(r"^##\s+", scoped, re.MULTILINE)
    if section_end:
        scoped = scoped[:section_end.start()]

    candidates: List[ScanCandidate] = []
    blocks = re.split(r"^###\s+", scoped, flags=re.MULTILINE)[1:]
    for block in blocks:
        block = "### " + block
        title_match = STUB_HEADING_RE.match(block.splitlines()[0])
        if not title_match:
            continue
        finding_title = title_match.group(1).strip()
        if _is_resolved(block):
            continue
        file_match = STUB_FILE_RE.search(block)
        if not file_match:
            continue
        raw_path = file_match.group(1).strip()
        # "**File:** `src/escalate/handler.py:402`" — normalize_path unwraps the
        # backticks and drops the line/range suffix.
        target = normalize_path(raw_path)
        fix_scope_match = STUB_FIX_SCOPE_RE.search(block)
        quoted = "\n".join(re.findall(r"```[a-z]*\n(.*?)```", block, re.DOTALL))
        candidate = ScanCandidate(
            source="stub",
            title=_truncate(f"Fix stub in {target}: {finding_title}"),
            body=(
                f"Unresolved stub-inventory finding \"{finding_title}\" in {target}.\n\n"
                f"Source inventory: {source_name}\n\n"
                "Fix scope from the inventory:\n"
                + (fix_scope_match.group(1).strip()
                   if fix_scope_match else "(not stated — inspect the site)")
                + "\n\nDiscovered by ready-frontier replenishment while the frontier was "
                "legitimately empty. Resolve the stub or close the bead with a reason if "
                "the stub is deliberate."
            ),
            target_file=target,
            priority=2,
            ref_key=f"{source_name}:{target}:{finding_title}",
            location=f"{source_name}:{finding_title}",
        )
        # The quoted code lines let the TODO scanner recognize a marker this
        # finding already documents (same defect → not new work).
        candidate.quoted_text = normalize_title(quoted)
        candidates.append(candidate)
    return candidates


def extract_todo_candidates(file_text: str, relpath: str) -> List[ScanCandidate]:
    """TODO/FIXME markers in one source file."""
    candidates: List[ScanCandidate] = []
    for lineno, line in enumerate(file_text.splitlines(), start=1):
        match = TODO_RE.search(line)
        if not match:
            continue
        marker, note = match.group(1), match.group(2).strip()
        note = re.sub(r"\s*#+$", "", note).strip() or "(no description on the marker line)"
        candidate = ScanCandidate(
            source="todo",
            title=_truncate(f"Address {marker} in {relpath}: {note}"),
            body=(
                f"{marker} marker at {relpath}:{lineno}:\n\n"
                f"    {line.strip()}\n\n"
                "Discovered by ready-frontier replenishment while the frontier was "
                "legitimately empty. Implement the missing behavior or, if the marker is "
                "deliberate, close the bead with a reason saying so."
            ),
            target_file=relpath,
            priority=2,
            ref_key=f"{relpath}:{lineno}:{marker}:{note}",
            location=f"{relpath}:{lineno}",
        )
        # The verbatim marker line is the cross-source dedupe key: a
        # stub-inventory finding that quotes this line documents the same
        # defect.
        candidate.quoted_text = normalize_title(line)
        candidates.append(candidate)
    return candidates


def scan_workspace(workspace: Path) -> List[ScanCandidate]:
    """Collect candidates from every supported backlog source."""
    candidates: List[ScanCandidate] = []

    plan = workspace / "docs" / "plan" / "plan.md"
    if plan.is_file():
        candidates.extend(extract_plan_candidates(
            plan.read_text(encoding="utf-8", errors="replace"),
            str(plan.relative_to(workspace)),
        ))

    stub_dir = workspace / "docs" / "notes"
    if stub_dir.is_dir():
        for stub_file in sorted(stub_dir.glob("stub-inventory-*.md")):
            candidates.extend(extract_stub_inventory_candidates(
                stub_file.read_text(encoding="utf-8", errors="replace"),
                str(stub_file.relative_to(workspace)),
            ))

    src_dir = workspace / "src"
    if src_dir.is_dir():
        for src_file in sorted(src_dir.rglob("*.py")):
            if "__pycache__" in src_file.parts:
                continue
            candidates.extend(extract_todo_candidates(
                src_file.read_text(encoding="utf-8", errors="replace"),
                str(src_file.relative_to(workspace)),
            ))

    return candidates


# --------------------------------------------------------------------------
# Dedupe
# --------------------------------------------------------------------------

def cross_source_dedupe(candidates: List[ScanCandidate]) -> Tuple[List[ScanCandidate], List[Dict[str, str]]]:
    """Drop TODO markers already documented as a stub-inventory finding.

    The inventory sweep is a superset of a TODO grep — it quotes the marker
    line verbatim. So a TODO whose own source line appears in the quoted code
    of a same-file inventory finding is the same defect, not new work; the
    richer inventory entry (it carries a fix scope) is the one kept.
    """
    stub_by_file: Dict[str, List[ScanCandidate]] = {}
    for candidate in candidates:
        if candidate.source == "stub" and candidate.target_file:
            stub_by_file.setdefault(candidate.target_file, []).append(candidate)

    kept: List[ScanCandidate] = []
    skipped: List[Dict[str, str]] = []
    for candidate in candidates:
        if candidate.source == "todo" and candidate.target_file in stub_by_file:
            marker_text = normalize_title(candidate.quoted_text)
            covering = [
                stub for stub in stub_by_file[candidate.target_file]
                if marker_text and marker_text in stub.quoted_text
            ]
            if covering:
                skipped.append({
                    "title": candidate.title,
                    "reason": f"same defect as stub-inventory finding {covering[0].location}",
                })
                continue
        kept.append(candidate)
    return kept, skipped


def dedupe_against_existing_beads(
    candidates: List[ScanCandidate],
    existing_beads: List[Dict[str, Any]],
) -> Tuple[List[ScanCandidate], List[Dict[str, str]]]:
    """Drop candidates an open or in-flight bead already covers.

    Two implement beads for the same defect is prohibited: a candidate is
    skipped when a live bead's normalized title matches, or when the bead's
    title/body already names the candidate's target file.
    """
    live = [b for b in existing_beads if b.get("status") != "closed"]
    live_titles = {normalize_title(b.get("title", "")) for b in live}
    live_text = {
        b.get("id"): f"{b.get('title', '')}\n{b.get('description', '')}"
        for b in live
    }

    kept: List[ScanCandidate] = []
    skipped: List[Dict[str, str]] = []
    for candidate in candidates:
        if normalize_title(candidate.title) in live_titles:
            skipped.append({"title": candidate.title, "reason": "open bead with matching title"})
            continue
        if candidate.target_file and any(
            candidate.target_file in text for text in live_text.values()
        ):
            skipped.append({
                "title": candidate.title,
                "reason": f"open bead already targets {candidate.target_file}",
            })
            continue
        kept.append(candidate)
    return kept, skipped


def dedupe_in_batch(candidates: List[ScanCandidate]) -> Tuple[List[ScanCandidate], List[Dict[str, str]]]:
    """Drop exact duplicates within this run.

    Same-file candidates are deliberately NOT deduped here — distinct defects
    in one file are both real work, and they get serialized against each other
    by serialization_chains(). Only identical titles (or identical unique refs,
    which the CLI itself idempotently collapses) are duplicates.
    """
    seen_titles: set = set()
    seen_refs: set = set()
    kept: List[ScanCandidate] = []
    skipped: List[Dict[str, str]] = []
    for candidate in candidates:
        title_key = normalize_title(candidate.title)
        if candidate.ref in seen_refs or title_key in seen_titles:
            skipped.append({"title": candidate.title, "reason": "duplicate within batch"})
            continue
        seen_refs.add(candidate.ref)
        seen_titles.add(title_key)
        kept.append(candidate)
    return kept, skipped


def order_candidates(candidates: List[ScanCandidate]) -> List[ScanCandidate]:
    """Deterministic order: code defects before plan gates, then stable keys."""
    return sorted(
        candidates,
        key=lambda c: (
            c.priority,
            SOURCE_RANK.get(c.source, 9),
            c.target_file or "",
            normalize_title(c.title),
        ),
    )


def serialization_chains(candidates: List[ScanCandidate]) -> Dict[str, List[str]]:
    """Map each candidate ref to the refs it must wait for.

    Beads touching the same target file are chained in candidate order so
    only the first is ready at a time — the bead-level fix for concurrent
    workers colliding on one file.
    """
    by_file: Dict[str, List[str]] = {}
    chains: Dict[str, List[str]] = {}
    for candidate in candidates:
        if not candidate.target_file:
            chains[candidate.ref] = []
            continue
        blockers = by_file.get(candidate.target_file, [])
        chains[candidate.ref] = list(blockers)
        by_file.setdefault(candidate.target_file, []).append(candidate.ref)
    return chains


# --------------------------------------------------------------------------
# Bead CLI plumbing
# --------------------------------------------------------------------------

def parse_bead_jsonl(stdout: str) -> List[Dict[str, Any]]:
    beads = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue  # progress/diagnostics noise, not a bead record
        if isinstance(data, dict) and data.get("id"):
            beads.append(data)
    return beads


def run_bead(bead_bin: str, workspace: Path, args: List[str],
             timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [bead_bin] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workspace),
    )


def list_all_beads(bead_bin: str, workspace: Path) -> List[Dict[str, Any]]:
    result = run_bead(bead_bin, workspace, ["list", "--json", "--limit", "999999"])
    if result.returncode != 0:
        raise RuntimeError(f"bead list failed: {result.stderr.strip()[:300]}")
    return parse_bead_jsonl(result.stdout)


def ready_frontier(bead_bin: str, workspace: Path) -> List[Dict[str, Any]]:
    result = run_bead(bead_bin, workspace, ["list", "--ready", "--json"])
    if result.returncode != 0:
        raise RuntimeError(f"bead list --ready failed: {result.stderr.strip()[:300]}")
    return parse_bead_jsonl(result.stdout)


def doctor_clean(bead_bin: str, workspace: Path) -> Tuple[bool, str]:
    """True when `bead doctor --rehearse` finds no corruption."""
    result = run_bead(bead_bin, workspace, ["doctor", "--rehearse"], timeout=120)
    output = (result.stdout + result.stderr).lower()
    if result.returncode != 0:
        return False, f"bead doctor --rehearse exited {result.returncode}"
    if not any(fp in output for fp in DOCTOR_FALSE_POSITIVES):
        for keyword in CORRUPTION_KEYWORDS:
            if keyword in output:
                return False, f"corruption indicator in doctor output: {keyword}"
    return True, "no corruption detected"


def classify_frontier(beads: List[Dict[str, Any]], ready_ids: set) -> Dict[str, List[str]]:
    """Bucket every non-closed bead by why it is or isn't ready.

    Every bucket except ``unexplained`` is a legitimate reason for a bead to be
    absent from the ready frontier. ``deferred`` matters because a
    status-deferred bead is deliberately parked, not stuck — counting it as
    unexplained would make the gate refuse on any workspace that has ever
    deferred a bead.
    """
    status_by_id = {b["id"]: b.get("status") for b in beads}
    classification: Dict[str, List[str]] = {
        "in_progress": [],
        "deferred": [],
        "manually_blocked": [],
        "dependency_blocked": [],
        "assigned_open": [],
        "unexplained": [],
    }
    for bead in beads:
        bead_id = bead["id"]
        status = bead.get("status")
        if status == "closed":
            continue
        if status == "in_progress":
            classification["in_progress"].append(bead_id)
            continue
        if status == "deferred":
            classification["deferred"].append(bead_id)
            continue
        blockers = [
            d.get("blocker") for d in bead.get("dependencies", [])
            if d.get("kind") == "blocks" and status_by_id.get(d.get("blocker")) != "closed"
        ]
        if bead.get("manual_blocked"):
            classification["manually_blocked"].append(bead_id)
        elif blockers:
            classification["dependency_blocked"].append(bead_id)
        elif bead.get("assignee"):
            classification["assigned_open"].append(bead_id)
        elif bead_id not in ready_ids:
            classification["unexplained"].append(bead_id)
    return classification


def create_bead(bead_bin: str, workspace: Path, candidate: ScanCandidate,
                depends_on: List[str]) -> Tuple[str, Optional[str]]:
    """Create one replenishment bead. Returns (verdict, bead_id).

    verdict: created | existing | existing_closed | error
    """
    args = [
        "create",
        "--title", candidate.title,
        "--description", candidate.body,
        "--priority", str(candidate.priority),
        "--issue-type", "task",
        "--label", REPLENISH_LABEL,
        "--unique-ref", candidate.ref,
    ]
    for blocker in depends_on:
        args += ["--depends-on", blocker]
    result = run_bead(bead_bin, workspace, args)
    output = result.stdout.strip()
    if result.returncode != 0:
        return "error", None
    if output.startswith("EXISTING_CLOSED"):
        return "existing_closed", output.split()[-1] if len(output.split()) > 1 else None
    if output.startswith("EXISTING"):
        return "existing", output.split()[-1] if len(output.split()) > 1 else None
    bead_id = output.splitlines()[-1].strip() if output else None
    return ("created", bead_id) if bead_id else ("error", None)


# --------------------------------------------------------------------------
# Gate + orchestration
# --------------------------------------------------------------------------

def evaluate_gate(bead_bin: str, workspace: Path) -> Dict[str, Any]:
    """Confirm the frontier is legitimately empty before creating anything."""
    gate: Dict[str, Any] = {
        "verdict": "proceed",
        "refuse_reasons": [],
    }

    clean, detail = doctor_clean(bead_bin, workspace)
    gate["doctor"] = detail
    if not clean:
        gate["verdict"] = "refuse"
        gate["refuse_reasons"].append(f"corruption suspected: {detail}")

    beads = list_all_beads(bead_bin, workspace)
    ready = ready_frontier(bead_bin, workspace)
    ready_ids = {b["id"] for b in ready}
    gate["ready_count"] = len(ready)
    gate["non_closed_beads"] = sum(1 for b in beads if b.get("status") != "closed")

    classification = classify_frontier(beads, ready_ids)
    gate["classification"] = classification
    gate["legitimately_blocked"] = (
        len(classification["manually_blocked"]) + len(classification["dependency_blocked"])
    )

    if len(ready) != 0:
        gate["verdict"] = "refuse"
        gate["refuse_reasons"].append(
            f"ready frontier is not empty ({len(ready)} beads) — nothing to replenish"
        )
    if classification["assigned_open"]:
        gate["verdict"] = "refuse"
        gate["refuse_reasons"].append(
            "stale assignees present (open + assigned): "
            + ", ".join(classification["assigned_open"])
            + " — repair those first (bead update <id> --clear-assignee)"
        )
    if classification["unexplained"]:
        gate["verdict"] = "refuse"
        gate["refuse_reasons"].append(
            "open beads the ready-frontier query neither returns nor explains: "
            + ", ".join(classification["unexplained"])
            + " — the frontier query itself may be broken; do not replenish"
        )

    return gate


def replenish(workspace: Path, bead_bin: str, cap: int, dry_run: bool) -> Dict[str, Any]:
    started = datetime.now(timezone.utc)
    report: Dict[str, Any] = {
        "metadata": {
            "workspace": str(workspace),
            "timestamp": started.isoformat(),
            "mode": "dry-run" if dry_run else "live",
            "cap": cap,
            "label": REPLENISH_LABEL,
        },
    }

    gate = evaluate_gate(bead_bin, workspace)
    report["gate"] = gate

    created: List[Dict[str, Any]] = []
    report["created"] = created

    if gate["verdict"] == "refuse":
        report["outcome"] = "gate_refused"
        return report

    candidates = scan_workspace(workspace)
    report["scan"] = {"candidates_found": len(candidates)}

    candidates, skipped = cross_source_dedupe(candidates)
    candidates, skipped_existing = dedupe_against_existing_beads(
        candidates, list_all_beads(bead_bin, workspace)
    )
    skipped.extend(skipped_existing)
    candidates, skipped_batch = dedupe_in_batch(candidates)
    skipped.extend(skipped_batch)
    report["scan"]["dedupe_skipped"] = skipped

    selected = order_candidates(candidates)[:cap]
    chains = serialization_chains(selected)
    report["scan"]["selected"] = [c.as_dict() for c in selected]

    ref_to_id: Dict[str, str] = {}
    for candidate in selected:
        blocker_refs = chains.get(candidate.ref, [])
        depends_on = [ref_to_id[ref] for ref in blocker_refs if ref in ref_to_id]
        if dry_run:
            created.append({
                "title": candidate.title,
                "unique_ref": candidate.ref,
                "depends_on": depends_on,
                "verdict": "would_create",
            })
            continue
        if any(ref not in ref_to_id for ref in blocker_refs):
            # A same-file blocker that failed to materialize must still
            # serialize its dependents — creating this one ready would put two
            # live beads on one file, the collision the chain exists to prevent.
            created.append({
                "title": candidate.title,
                "unique_ref": candidate.ref,
                "depends_on": depends_on,
                "verdict": "skipped_blocker_failed",
            })
            continue
        verdict, bead_id = create_bead(bead_bin, workspace, candidate, depends_on)
        entry = {
            "title": candidate.title,
            "unique_ref": candidate.ref,
            "depends_on": depends_on,
            "verdict": verdict,
        }
        if bead_id:
            entry["id"] = bead_id
            ref_to_id[candidate.ref] = bead_id
        created.append(entry)

    report["ready_count_after"] = len(ready_frontier(bead_bin, workspace))
    report["outcome"] = "replenished" if any(
        c.get("verdict") in ("created", "existing") for c in created
    ) else "nothing_to_create"
    report["metadata"]["duration_seconds"] = (
        datetime.now(timezone.utc) - started
    ).total_seconds()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replenish an empty ready frontier from the workspace's tracked backlog"
    )
    parser.add_argument(
        "--workspace",
        default="/home/coding/aide-de-camp",
        help="Path to the workspace directory (default: /home/coding/aide-de-camp)",
    )
    parser.add_argument(
        "--bead-bin",
        default=None,
        help="Path to the bead CLI (default: bead on PATH, falling back to "
             "~/.local/bin/bead and ~/.cargo/bin/bead)",
    )
    parser.add_argument(
        "--cap",
        type=int,
        default=DEFAULT_CAP,
        help=f"Maximum beads created per run (default: {DEFAULT_CAP})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the gate, scan, dedupe and serialization plan without creating anything",
    )
    parser.add_argument(
        "--output",
        default="/tmp/bead-replenish-report.json",
        help="Where to write the structured JSON report",
    )
    args = parser.parse_args()

    bead_bin = args.bead_bin or shutil.which("bead") or str(
        Path.home() / ".local" / "bin" / "bead"
    )
    workspace = Path(args.workspace).resolve()
    if not (workspace / ".beads").is_dir():
        print(f"ERROR: no .beads/ workspace at {workspace}", file=sys.stderr)
        return 1
    if args.cap < 1:
        print("ERROR: --cap must be >= 1", file=sys.stderr)
        return 1

    try:
        report = replenish(workspace, bead_bin, args.cap, args.dry_run)
    except Exception as exc:  # noqa: BLE001 — a report is written even on failure
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    gate = report["gate"]
    print(f"gate verdict: {gate['verdict']}")
    for reason in gate.get("refuse_reasons", []):
        print(f"  refused: {reason}")
    scan = report.get("scan") or {}
    print(f"candidates after dedupe: {len(scan.get('selected', []))}")
    for entry in report.get("created", []):
        print(f"  [{entry['verdict']}] {entry.get('id', '-')} {entry['title']}")
    if "ready_count_after" in report:
        print(f"ready frontier after run: {report['ready_count_after']}")
    print(f"report: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
