#!/usr/bin/env python3
"""
Attach the automated diagnostic report to starvation alert beads.

NEEDLE files a "Starvation alert: beads invisible in <workspace>" bead when the
pluck waterfall finds no candidates, and the unravel strand files "[Unravel]
Starvation alert: ..." alternatives beneath it. Those beads used to reach a
human with an empty Workspace field and no evidence attached, so the first step
was always a hand investigation of the same five checks. This script closes
that gap: for every alert bead that does not carry a report yet it runs

  1. scripts/diagnose_pluck_starvation.py   (the five-check diagnostic suite)
  2. scripts/bead_recovery_workflow.sh      (stale-checkpoint flush, visibility
                                             repair, corruption rehearsal)

and then writes into the bead's notes

  - the diagnostics report JSON path,
  - the report's overall_status,
  - the top recommendations,
  - the recovery workflow's RECOVERY_SUMMARY block (read back from
    /tmp/bead-recovery.log, so the note and the log carry the same run), and
  - a classification label:

      starvation:legitimately-blocked  every open bead is manually blocked or
                                       waiting on an unclosed blocker - the
                                       frontier is empty for a stated reason
      starvation:auto-recovered        the recovery workflow restored frontier
                                       visibility (ready count rose, or beads
                                       became visible again)
      starvation:false-positive        the frontier reads empty and the fresh
                                       diagnostics prove the workspace is
                                       healthy - the alert contradicted its
                                       own counts
      starvation:unresolved            none of the above - the starvation
                                       survived the automated recovery and
                                       still needs a human

Two of those verdicts are proven outright, so the enrichment then closes the
bead (`bead close --reason`, reversible with `bead reopen`):

      starvation:false-positive        reason = the diagnostics verdict plus
                                       the report JSON path
      starvation:auto-recovered        reason = the recovery outcome from the
                                       RECOVERY_SUMMARY block

A bead is closed only when it is open (an in_progress bead has a live worker
claim, which wins) and the enrichment note has landed, so re-runs are no-ops.
legitimately-blocked and unresolved stay open - unblocking or escalating
those still needs judgment. A failed close is logged and the bead keeps its
label and notes, which is the pre-existing outcome; it never fails the run.

Notes are appended to whatever the bead already carries, not rewritten:
`bead update --notes` replaces the whole field, so annotate_bead reads the
current notes back first and writes the combination under `--if-revision`
from that same read — a concurrent edit makes the update fail loudly (rc=4)
instead of destroying either side's text.

Run standalone, or from scripts/bead-healthcheck.sh so a freshly filed alert is
enriched within one timer period (the healthcheck timer fires every 15 minutes).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# A bead is a starvation alert when its title carries this marker - this covers
# both the plain alert NEEDLE files and the "[Unravel] Starvation alert: ..."
# alternatives filed beneath it.
ALERT_TITLE_MARKER = "Starvation alert:"

# Present in a bead's notes once this script has enriched it. The
# classification label is the other idempotency signal, but notes are checked
# too because labels alone can be removed by hand.
ENRICHMENT_MARKER = "Starvation diagnostics (automated):"

LABEL_AUTO_RECOVERED = "starvation:auto-recovered"
LABEL_FALSE_POSITIVE = "starvation:false-positive"
LABEL_LEGITIMATELY_BLOCKED = "starvation:legitimately-blocked"
LABEL_UNRESOLVED = "starvation:unresolved"

# The two verdicts the evidence proves outright - the enrichment closes these
# after labelling. legitimately-blocked and unresolved still need a human.
CLOSEABLE_LABELS = (LABEL_AUTO_RECOVERED, LABEL_FALSE_POSITIVE)

# The note text for the false-positive class states the actual finding: the
# alert's own body claimed open beads existed while its counts said zero.
FALSE_POSITIVE_REASON = (
    "workspace quiescent — 0 open beads at filing and at enrichment; "
    "alert body contradicted its own counts"
)

DEFAULT_LOG_FILE = "/tmp/bead-recovery.log"
RECOVERY_SUMMARY_START = "=== RECOVERY_SUMMARY ==="
RECOVERY_SUMMARY_END = "=== END_RECOVERY_SUMMARY ==="

# bead list silently caps output at its --limit (default 100); fetch the whole
# queue so blocker statuses resolve against every bead, not the first 100.
BEAD_LIST_LIMIT = 999999


def resolve_bead_bin(explicit: Optional[str] = None) -> str:
    """Locate the bead CLI.

    The systemd user manager runs the healthcheck with a minimal PATH that
    misses ~/.local/bin and ~/.cargo/bin, where this box's bead wrapper and
    binaries live. Mirrors resolve_bead_bin() in diagnose_pluck_starvation.py.
    """
    if explicit:
        return explicit
    found = shutil.which("bead")
    if found:
        return found
    for candidate in (
        Path.home() / ".local" / "bin" / "bead",
        Path.home() / ".cargo" / "bin" / "bead",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "bead"  # let subprocess surface the familiar not-found error


def resolve_python(workspace: Path) -> str:
    """Prefer the workspace venv interpreter, fall back to the running one.

    The diagnostic suite is stdlib-only, so either works; the venv is
    preferred for parity with bead-healthcheck.sh.
    """
    venv_python = workspace / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable


# ---------------------------------------------------------------------------
# bead list plumbing
# ---------------------------------------------------------------------------


def normalize_bead_stream(stdout: str) -> List[Dict[str, Any]]:
    """Flatten `bead list --json` output into a list of bead objects.

    The CLI emits compact JSONL, prints a bare "[]" for an empty result, and
    has been seen emitting nested arrays; slurp-and-flatten normalizes every
    shape (the same pattern bead-healthcheck.sh uses). Progress lines that are
    not JSON are skipped rather than fatal.
    """
    if not stdout.strip():
        return []
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # progress chatter, not a bead
    if isinstance(parsed, dict):
        parsed = [parsed]
    flat: List[Dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, list):
            flat.extend(i for i in item if isinstance(i, dict))
        elif isinstance(item, dict):
            flat.append(item)
    return flat


def run_bead_list(
    args: List[str], bead_bin: str, workspace: Path, timeout: int = 60
) -> List[Dict[str, Any]]:
    # --limit overrides the CLI's silent default cap (100): the enrichment
    # resolves blocker statuses against this fetch, and a capped fetch marks
    # every bead whose blocker fell past the cap as dependency-blocked.
    result = subprocess.run(
        [bead_bin, "list", *args, "--json", "--limit", str(BEAD_LIST_LIMIT)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workspace),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"bead list {' '.join(args)} failed (rc={result.returncode}): "
            f"{result.stderr.strip()[:300]}"
        )
    return normalize_bead_stream(result.stdout)


def has_unclosed_blocker(bead: Dict[str, Any], status_of: Dict[str, str]) -> bool:
    """True when any blocker of this bead is not closed.

    A blocker missing from the status map counts as unclosed - absence of
    evidence is not evidence a blocker finished.
    """
    for dep in bead.get("dependencies") or []:
        blocker = dep.get("blocker")
        if blocker and status_of.get(blocker, "unknown") != "closed":
            return True
    return False


def is_manually_blocked(bead: Dict[str, Any]) -> bool:
    return bool(bead.get("manual_blocked")) or "human" in (bead.get("labels") or [])


def classify_frontier(
    open_beads: List[Dict[str, Any]], all_beads: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Bucket every open bead the way bead-healthcheck.sh does.

    Returns counts plus the legitimately-blocked verdict: every open bead is
    either manually blocked or waiting on an unclosed blocker. An empty queue
    is never legitimately blocked - a wiped workspace must stay loud.
    """
    status_of = {
        b["id"]: b.get("status") or b.get("effective_status") or "unknown"
        for b in all_beads
        if b.get("id")
    }
    buckets = {
        "human_blocked": [],
        "dependency_blocked": [],
        "other": [],
    }
    for bead in open_beads:
        if is_manually_blocked(bead):
            buckets["human_blocked"].append(bead["id"])
        elif has_unclosed_blocker(bead, status_of):
            buckets["dependency_blocked"].append(bead["id"])
        else:
            buckets["other"].append(bead["id"])

    total_open = len(open_beads)
    explained = len(buckets["human_blocked"]) + len(buckets["dependency_blocked"])
    return {
        "total_open": total_open,
        "human_blocked": buckets["human_blocked"],
        "dependency_blocked": buckets["dependency_blocked"],
        "other": buckets["other"],
        "unexplained": len(buckets["other"]),
        "all_explained": total_open > 0 and explained == total_open,
    }


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------


def diagnostics_report_is_healthy(report: Optional[Dict[str, Any]]) -> bool:
    """True when the fresh diagnostics report proves the workspace healthy.

    Exactly the three checks that can fake a starvation: the doctor rehearsal
    found no corruption, no bead is assigned-but-open, and the checkpoint is
    not stale. Each check must actually have run - one that did not execute
    cannot vote the workspace clean, so a missing count counts as a failure
    (the same idiom as has_unclosed_blocker: absence of evidence is not
    evidence of health).

    overall_status is deliberately not part of the bar. In the exact shape
    this class exists for - an alert filed over a queue that has since
    emptied - the stale pluck-diagnostics snapshot still on disk re-reports
    the old starvation as CRITICAL on every fresh run, which says nothing
    about the live store these three checks just measured. Likewise a leftover
    empty publish.lock only ever earns a medium finding and is not a stall.
    """
    if not isinstance(report, dict):
        return False
    results = report.get("detailed_results") or {}
    corruption = results.get("corruption_check") or {}
    if not corruption.get("rehearse_executed") or corruption.get("corruption_detected"):
        return False
    database = results.get("database") or {}
    if _as_int(database.get("assigned_but_open_beads")) != 0:
        return False
    checkpoint = results.get("checkpoint") or {}
    if checkpoint.get("checkpoint_stale"):
        return False
    return True


def classify_starvation(
    frontier: Dict[str, Any],
    frontier_before: Dict[str, Any],
    recovery_summary: Optional[Dict[str, Any]],
    report: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Decide the classification label and return (label, reason).

    Order matters: a frontier that is fully explained is legitimately blocked
    even when a recovery pass coincidentally nudged a number, and a restored
    frontier wins over the unresolved fallback. A workspace with no open beads
    at all can only be a false positive (the diagnostics prove it is healthy),
    auto-recovered, or unresolved - "every bead is blocked" must not hold
    vacuously over an empty queue, and a quiescent queue can neither grow a
    ready frontier nor move recovery's open count, so without the
    false-positive branch it would land on unresolved with nothing to resolve.
    """
    if frontier["all_explained"]:
        return LABEL_LEGITIMATELY_BLOCKED, (
            f"all {frontier['total_open']} open bead(s) are manually blocked or "
            f"waiting on an unclosed blocker "
            f"({len(frontier['human_blocked'])} manual, "
            f"{len(frontier['dependency_blocked'])} dependency)"
        )

    ready_before = frontier_before.get("ready")
    ready_after = frontier.get("ready")
    if ready_before is not None and ready_after is not None and ready_after > ready_before:
        return LABEL_AUTO_RECOVERED, (
            f"ready frontier grew {ready_before} -> {ready_after} after the recovery workflow ran"
        )

    if recovery_summary:
        before = _as_int(recovery_summary.get("open_beads_before"))
        after = _as_int(recovery_summary.get("open_beads_after"))
        if before == 0 and after > 0:
            return LABEL_AUTO_RECOVERED, (
                f"recovery workflow restored bead visibility (open beads {before} -> {after})"
            )

    if frontier["total_open"] == 0 and diagnostics_report_is_healthy(report):
        return LABEL_FALSE_POSITIVE, FALSE_POSITIVE_REASON

    return LABEL_UNRESOLVED, (
        f"{frontier['unexplained']} open bead(s) remain unexplained after the "
        f"recovery workflow; automated recovery did not restore the frontier"
    )


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# recovery log parsing
# ---------------------------------------------------------------------------


def parse_recovery_summary(log_text: str) -> Optional[Dict[str, Any]]:
    """Extract the last RECOVERY_SUMMARY block from bead-recovery.log text.

    Every line the workflow logs carries a "[<utc timestamp>] " prefix, so both
    the block markers and the `key: value` lines are matched after stripping
    that prefix - otherwise the keys would be named for their timestamps.
    """
    start = log_text.rfind(RECOVERY_SUMMARY_START)
    if start == -1:
        return None
    end = log_text.find(RECOVERY_SUMMARY_END, start)
    if end == -1:
        return None
    block = log_text[start + len(RECOVERY_SUMMARY_START) : end]
    summary: Dict[str, Any] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key.startswith("[") and "]" in key:
            key = key.split("]", 1)[1].strip()
        if key:
            summary[key] = value.strip()
    return summary or None


def read_log_from(path: str, offset: int) -> str:
    try:
        with open(path, "r", errors="replace") as handle:
            handle.seek(offset)
            return handle.read()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# note formatting
# ---------------------------------------------------------------------------


def format_note(
    report_path: str,
    overall_status: str,
    recommendations: List[str],
    classification: str,
    classification_reason: str,
    recovery_summary: Optional[Dict[str, Any]],
    report_timestamp: str,
) -> str:
    lines = [
        ENRICHMENT_MARKER,
        f"- Diagnostics report: {report_path}",
        f"- Overall status: {overall_status}",
        f"- Classified: {classification} - {classification_reason}",
        f"- Report generated: {report_timestamp}",
    ]
    if recommendations:
        lines.append("- Top recommendations:")
        for rec in recommendations[:5]:
            lines.append(f"  - {rec}")
    else:
        lines.append("- Top recommendations: none - no actionable finding")
    if recovery_summary:
        lines.append("- Recovery workflow RECOVERY_SUMMARY:")
        for key in (
            "checkpoint_age_seconds",
            "checkpoint_stale",
            "open_beads_before",
            "open_beads_after",
            "recovery_successful",
            "timestamp",
        ):
            if key in recovery_summary:
                lines.append(f"  - {key}: {recovery_summary[key]}")
    else:
        lines.append(f"- Recovery workflow RECOVERY_SUMMARY: not captured (see {DEFAULT_LOG_FILE})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# enrichment steps
# ---------------------------------------------------------------------------


def is_enriched(bead: Dict[str, Any]) -> bool:
    if any(str(label).startswith("starvation:") for label in bead.get("labels") or []):
        return True
    return ENRICHMENT_MARKER in (bead.get("notes") or "")


def find_alert_beads(
    beads: List[Dict[str, Any]], statuses: Tuple[str, ...] = ("open",)
) -> List[Dict[str, Any]]:
    """Alert beads not enriched yet.

    Defaults to open beads only: a bead another worker is actively operating on
    (in_progress) should not gain notes mid-flight from this automation.
    """
    return [
        bead
        for bead in beads
        if ALERT_TITLE_MARKER in (bead.get("title") or "")
        and (bead.get("status") or bead.get("effective_status")) in statuses
        and not is_enriched(bead)
    ]


def run_diagnostics(
    workspace: Path, bead_bin: str, output_path: Path, timeout: int = 120
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Run the diagnostic suite and load its report."""
    script = workspace / "scripts" / "diagnose_pluck_starvation.py"
    result = subprocess.run(
        [
            resolve_python(workspace),
            str(script),
            "--workspace",
            str(workspace),
            "--quiet",
            "--output",
            str(output_path),
            "--bead-bin",
            bead_bin,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workspace),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"diagnose_pluck_starvation.py failed (rc={result.returncode}): "
            f"{result.stderr.strip()[:300]}"
        )
    try:
        with open(output_path, "r") as handle:
            return json.load(handle), str(output_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"diagnostics report {output_path} is unreadable: {exc}") from exc


def run_recovery_workflow(
    workspace: Path, log_file: str, bead_bin: str, timeout: int = 300
) -> Optional[Dict[str, Any]]:
    """Run the recovery workflow, then return its RECOVERY_SUMMARY block.

    The log is read from the byte offset it had before the run, so the summary
    returned is the one this invocation wrote - not a block left by an earlier
    pass.
    """
    script = workspace / "scripts" / "bead_recovery_workflow.sh"
    if not script.is_file():
        raise RuntimeError(f"recovery workflow not found: {script}")

    offset = 0
    if os.path.exists(log_file):
        offset = os.path.getsize(log_file)

    env = dict(os.environ)
    env["BEAD_BIN"] = bead_bin  # the workflow resolves this when PATH does not
    result = subprocess.run(
        [str(script)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workspace),
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"bead_recovery_workflow.sh failed (rc={result.returncode}): "
            f"{(result.stderr or result.stdout).strip()[:300]}"
        )
    return parse_recovery_summary(read_log_from(log_file, offset))


def unique_report_path(directory: Path, stamp: str) -> Path:
    """A report path that does not collide with one written in the same second."""
    base = f"pluck-starvation-diagnostic-{stamp}"
    candidate = directory / f"{base}.json"
    suffix = 2
    while candidate.exists():
        candidate = directory / f"{base}-{suffix}.json"
        suffix += 1
    return candidate


def label_bead(bead_id: str, label: str, bead_bin: str, workspace: Path) -> None:
    subprocess.run(
        [bead_bin, "label", "add", bead_id, "--label", label],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(workspace),
        check=True,
    )


def read_bead(
    bead_id: str, bead_bin: str, workspace: Path, timeout: int = 60
) -> Dict[str, Any]:
    """Fetch one bead as a dict via `bead show --json`.

    The CLI wraps the single bead in a JSON array; a bare dict is accepted too
    so a future format change does not turn into a data-loss path.
    """
    result = subprocess.run(
        [bead_bin, "show", "--json", bead_id],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workspace),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"bead show --json {bead_id} failed (rc={result.returncode}): "
            f"{result.stderr.strip()[:300]}"
        )
    beads = normalize_bead_stream(result.stdout)
    for bead in beads:
        if bead.get("id") == bead_id:
            return bead
    # Never fall back to "the only bead returned": an id mismatch here means
    # writing notes onto the wrong bead, which is worse than failing this
    # pass and letting the next one retry.
    raise RuntimeError(f"bead show --json {bead_id} returned no recognizable bead")


def annotate_bead(bead_id: str, note: str, bead_bin: str, workspace: Path) -> None:
    """Append the enrichment note to the bead's existing notes.

    `bead update --notes` REPLACES the whole notes field — writing only the
    enrichment note would erase whatever investigation notes the bead already
    carried. So the current notes are read back immediately before the write
    and combined, and the update carries `--if-revision` from that same read:
    if anything edits the bead in between, the update exits 4 instead of
    silently clobbering it, and the caller records the bead as failed for the
    next pass rather than losing data.
    """
    current = read_bead(bead_id, bead_bin, workspace)
    existing = (current.get("notes") or "").rstrip()
    combined = f"{existing}\n\n{note}" if existing else note
    revision = current.get("revision")
    command = [bead_bin, "update", bead_id, "--notes", combined]
    if revision is not None:
        command += ["--if-revision", str(revision)]
    subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(workspace),
        check=True,
    )


def close_bead(bead_id: str, reason: str, bead_bin: str, workspace: Path) -> None:
    subprocess.run(
        [bead_bin, "close", bead_id, "--reason", reason],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(workspace),
        check=True,
    )


def should_close_bead(bead: Dict[str, Any], note: str, classification: str) -> bool:
    """True when the enrichment may close this bead.

    Only the two proven verdicts close at all. The bead must still be open -
    in_progress means a worker claimed it and that claim wins - and the note
    this run wrote must be on it: the marker is the idempotency signal, so a
    bead that already reached a human (or a previous pass) is never re-closed.
    """
    if classification not in CLOSEABLE_LABELS:
        return False
    status = bead.get("status") or bead.get("effective_status")
    if status != "open":
        return False
    return ENRICHMENT_MARKER in note


def build_close_reason(
    classification: str,
    classification_reason: str,
    report_path: str,
    recovery_summary: Optional[Dict[str, Any]],
) -> str:
    """One-line close reason citing the evidence that decided the class."""
    if classification == LABEL_FALSE_POSITIVE:
        return f"False positive: {classification_reason} (diagnostics report: {report_path})"
    evidence = ""
    if recovery_summary:
        parts = [
            f"{key}={recovery_summary[key]}"
            for key in ("open_beads_before", "open_beads_after", "recovery_successful")
            if key in recovery_summary
        ]
        if parts:
            evidence = f" [{'; '.join(parts)}]"
    return f"Auto-recovered: {classification_reason}{evidence}"


def enrich(
    workspace: Path,
    bead_bin: str,
    log_file: str,
    dry_run: bool = False,
    only_beads: Optional[List[str]] = None,
    report_dir: Path = Path("/tmp"),
) -> List[Dict[str, Any]]:
    """Enrich every unenriched alert bead; returns one record per bead."""
    # Frontier before the recovery pass - the "did the workflow help?" baseline.
    open_before = run_bead_list(["--status", "open"], bead_bin, workspace)
    ready_before_count = len(run_bead_list(["--ready"], bead_bin, workspace))
    frontier_before = {"total_open": len(open_before), "ready": ready_before_count}

    candidates = find_alert_beads(open_before)
    if only_beads is not None:
        wanted = set(only_beads)
        candidates = [bead for bead in candidates if bead.get("id") in wanted]
        missing = wanted - {bead.get("id") for bead in candidates}
        for bead_id in sorted(missing):
            print(f"SKIP {bead_id}: not an unenriched open starvation alert bead", file=sys.stderr)

    if not candidates:
        # Nothing to attach a report to, so the recovery workflow does not run:
        # the healthcheck calls this every 15 minutes and must stay cheap on a
        # quiet workspace.
        return []

    if dry_run:
        # Read-only preview: stop after discovery, before the recovery pass and
        # the post-recovery re-reads.
        for bead in candidates:
            print(f"[dry-run] would enrich {bead['id']}: {bead.get('title')}")
        return [{"bead_id": bead["id"], "action": "would-enrich"} for bead in candidates]

    recovery_summary: Optional[Dict[str, Any]] = None
    recovery_error: Optional[str] = None
    try:
        recovery_summary = run_recovery_workflow(workspace, log_file, bead_bin)
    except (RuntimeError, subprocess.SubprocessError) as exc:
        # A failed recovery pass must not stop the diagnostics being
        # attached - the report is the part the human needs.
        recovery_error = str(exc)
        print(f"WARN recovery workflow failed: {recovery_error}", file=sys.stderr)

    # Post-recovery frontier - what the classification is judged on. Re-read
    # every bead, not just the open ones: a blocker may have closed mid-pass.
    open_after = run_bead_list(["--status", "open"], bead_bin, workspace)
    frontier = classify_frontier(open_after, run_bead_list([], bead_bin, workspace))
    frontier["ready"] = len(run_bead_list(["--ready"], bead_bin, workspace))

    records: List[Dict[str, Any]] = []
    for bead in candidates:
        bead_id = bead["id"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = unique_report_path(report_dir, stamp)

        try:
            report, report_path = run_diagnostics(workspace, bead_bin, output_path)
        except (RuntimeError, subprocess.SubprocessError) as exc:
            print(f"ERROR enriching {bead_id}: {exc}", file=sys.stderr)
            records.append({"bead_id": bead_id, "action": "failed", "error": str(exc)})
            continue

        metadata = report.get("metadata") or {}
        overall_status = metadata.get("overall_status", "UNKNOWN")
        recommendations = report.get("recommendations") or []
        classification, reason = classify_starvation(
            frontier, frontier_before, recovery_summary, report
        )
        note = format_note(
            report_path=report_path,
            overall_status=overall_status,
            recommendations=recommendations,
            classification=classification,
            classification_reason=reason,
            recovery_summary=recovery_summary,
            report_timestamp=metadata.get("timestamp", "unknown"),
        )

        try:
            annotate_bead(bead_id, note, bead_bin, workspace)
            label_bead(bead_id, classification, bead_bin, workspace)
        except (subprocess.SubprocessError, subprocess.CalledProcessError) as exc:
            print(f"ERROR writing enrichment to {bead_id}: {exc}", file=sys.stderr)
            records.append({"bead_id": bead_id, "action": "failed", "error": str(exc)})
            continue

        record = {
            "bead_id": bead_id,
            "action": "enriched",
            "report_path": report_path,
            "overall_status": overall_status,
            "classification": classification,
            "recovery_summary": recovery_summary,
            "closed": False,
        }

        if should_close_bead(bead, note, classification):
            close_reason = build_close_reason(classification, reason, report_path, recovery_summary)
            try:
                close_bead(bead_id, close_reason, bead_bin, workspace)
                record["closed"] = True
                record["close_reason"] = close_reason
                print(f"CLOSED {bead_id} [{classification}] reason={close_reason}")
            except (subprocess.SubprocessError, subprocess.CalledProcessError) as exc:
                # The label and notes are already on the bead, which is the
                # pre-existing outcome; a failed close must not fail the run.
                record["close_error"] = str(exc)
                print(f"WARN close failed for {bead_id}: {exc}", file=sys.stderr)

        print(f"ENRICHED {bead_id} [{classification}] report={report_path}")
        records.append(record)

    if recovery_error:
        records.append({"action": "recovery_failed", "error": recovery_error})
    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Attach the automated diagnostic report to starvation alert beads"
    )
    parser.add_argument(
        "--workspace",
        default="/home/coding/aide-de-camp",
        help="Path to the beads workspace (default: /home/coding/aide-de-camp)",
    )
    parser.add_argument(
        "--bead",
        action="append",
        dest="only_beads",
        metavar="ID",
        help="Enrich only this bead id (repeatable). Status filters still apply.",
    )
    parser.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help=f"Recovery workflow log to read the summary from (default: {DEFAULT_LOG_FILE})",
    )
    parser.add_argument(
        "--report-dir",
        default="/tmp",
        help="Directory the diagnostics report JSON is written to (default: /tmp)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be enriched without mutating anything",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print a JSON summary of the actions taken",
    )
    parser.add_argument(
        "--bead-bin",
        help="Path to the bead CLI (default: bead on PATH, falling "
        "back to ~/.local/bin/bead and ~/.cargo/bin/bead)",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    bead_bin = resolve_bead_bin(args.bead_bin)

    records = enrich(
        workspace=workspace,
        bead_bin=bead_bin,
        log_file=args.log_file,
        dry_run=args.dry_run,
        only_beads=args.only_beads,
        report_dir=Path(args.report_dir),
    )

    if args.as_json:
        print(json.dumps({"workspace": str(workspace), "records": records}, indent=2))
    else:
        enriched = sum(1 for r in records if r.get("action") == "enriched")
        closed = sum(1 for r in records if r.get("closed"))
        failed = sum(1 for r in records if r.get("action") == "failed")
        print(
            f"Done: {enriched} enriched, {closed} closed, {failed} failed, "
            f"{len(records)} record(s) total"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
