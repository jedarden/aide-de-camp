#!/usr/bin/env python3
"""
Unblock beads whose notes record a credential-read failure.

Beads blocked with "OpenBao permission denied" starve the ready frontier
because the fix is assumed to need a human with read access. It does not: it
needs the credential's *consumer* to fetch the value itself at start, so no
agent read ever has to be granted. This script is the standing, deterministic
response — it runs from scripts/beead-healthcheck.sh within one timer period
(15 minutes) of a bead recording the failure shape, and never touches a
secret value.

For every open bead whose notes or description record a credential-read
failure against a `secret/...` path, it runs the four-step recipe:

  1. Confirm the path exists via the WRITE-ONLY provisioning identity —
     `bao-as openbao-v2-provision bao kv metadata get` (metadata is readable
     there; values are not). A 403 is a sanctioned denial: record it and
     stop for that path. "No value found" is recorded as missing.
  2. Report the delivery restructure: the consuming process fetches its own
     value at start — for this workspace, deploy/aide-de-camp.service's
     ExecStartPre (deploy/fetch_runtime_secrets.sh) piping
     `bao-as openbao-v2 bao kv get -field=<key>` into a mode-600 file under
     /run/user/$UID, read back via TELEGRAM_BOT_TOKEN_FILE. Never a literal
     in a manifest, bead, note, or command line.
  3. Verify by property only: the delivered file exists mode 600 and the
     service's status endpoint reports the integration configured. The value
     is never read back, printed, or logged — not here, not anywhere.
  4. Append the result to the bead via `bead update --notes` (read-back plus
     --if-revision, so a concurrent edit fails loudly instead of clobbering)
     so its dependents become claimable without a human in the path.

A path this recipe cannot finish (missing secret, sanctioned 403, OpenBao
unreachable, no delivery wired) is recorded on the bead exactly as it stands:
the note says what is proven, what is missing, and what the mechanical next
step is — not a request for a human decision.

Idempotent: a bead already carrying the "Credential unblock (automated):"
marker is skipped, so re-runs are no-ops. Beads labeled `unravel-proposal`
are skipped — those *describe* the blocker class; they are not blocked by it.

Run standalone, or from scripts/bead-healthcheck.sh.
"""

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

DEFAULT_HEALTH_URL = "http://localhost:8000/api/v1/status/telegram"
DEFAULT_LOG_FILE = "/tmp/bead-healthcheck.log"

# Present in a bead's notes once this script has processed it - the
# idempotency signal, checked before any probe runs.
UNBLOCK_MARKER = "Credential unblock (automated):"

# The OpenBao instance and its write-only sibling identity. Metadata reads
# (existence, version) go through -provision; the recipe never needs a value.
BAO_INSTANCE = "openbao-v2"
BAO_PROVISION_INSTANCE = "openbao-v2-provision"

# A bead is a candidate when its text carries BOTH a credential-read failure
# marker AND at least one secret path. The marker alone is too broad
# ("permission denied" also describes kubectl RBAC notes); the path anchors
# it to credential content. Case-insensitive.
DENIAL_MARKERS = (
    r"openbao\s+permission\s+denied",
    r"permission\s+denied",
    r"cannot\s+(?:read|access|retrieve)\s+(?:the\s+)?(?:openbao\s+)?secret",
    r"unreadable\s+credential",
    r"credential(?:-read)?\s+failure",
    r"openbao\s+permissions?\b",
    r"access\s+denied",
    r"credential[^\n]{0,40}denied",
)

# `secret/<instance>/<app>[/key...]`. The final segment may be a `*` glob
# (beads sometimes record a prefix rather than a leaf path).
SECRET_PATH_RE = re.compile(
    r"\bsecret/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*(?:/\*)?"
)

# The four probe verdicts. Only EXISTS (+ the delivery property check) lets
# the bead be annotated as unblocked; the others are recorded and stop.
VERIF_EXISTS = "exists"
VERIF_PREFIX = "prefix-exists"
VERIF_MISSING = "missing"
VERIF_DENIED = "denied-sanctioned"
VERIF_UNREACHABLE = "openbao-unreachable"

# bead list silently caps output at its --limit (default 100); fetch the
# whole queue so nothing hides behind the cap.
BEAD_LIST_LIMIT = 999999


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_bead_bin(explicit: Optional[str] = None) -> str:
    """Locate the bead CLI (systemd user units miss ~/.local/bin on PATH)."""
    if explicit:
        return explicit
    found = shutil.which("bead")
    if found:
        return found
    for candidate in (
        os.path.expanduser("~/.local/bin/bead"),
        os.path.expanduser("~/.cargo/bin/bead"),
    ):
        if os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("no usable bead CLI found (PATH, ~/.local/bin, ~/.cargo/bin)")


def resolve_bao_as_bin(explicit: Optional[str] = None) -> Optional[str]:
    """Locate bao-as; None when absent (probes record 'cannot check')."""
    if explicit:
        return explicit
    found = shutil.which("bao-as")
    if found:
        return found
    for candidate in (
        os.path.expanduser("~/.local/bin/bao-as"),
        os.path.expanduser("~/.cargo/bin/bao-as"),
    ):
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def normalize_bead_stream(stdout: str) -> List[Dict[str, Any]]:
    """Flatten `bead list --json` output (JSONL, bare [], or nested arrays)."""
    beads: List[Dict[str, Any]] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue  # progress chatter, not a bead
        if isinstance(parsed, list):
            beads.extend(b for b in parsed if isinstance(b, dict))
        elif isinstance(parsed, dict):
            beads.append(parsed)
    return beads


def run_command(
    command: List[str], timeout: int = 60
) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )


def http_get_json(url: str, timeout: int = 3) -> Optional[Dict[str, Any]]:
    """GET a JSON document; None on any failure (a down endpoint is a
    verdict, not an exception)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def bead_text(bead: Dict[str, Any]) -> str:
    return f"{bead.get('notes') or ''}\n{bead.get('description') or ''}"


def extract_secret_paths(text: str) -> List[str]:
    """Unique secret paths in order of first appearance."""
    seen: List[str] = []
    for match in SECRET_PATH_RE.finditer(text):
        # Dots are legal inside segments but prose sentences end with one, so
        # a match like "...telegram_bot_token." is the punctuation, not the
        # path. Same for a trailing slash. Strip both before use.
        path = match.group(0).rstrip("/").rstrip(".")
        if path.endswith("/*"):
            path = path[:-2]
        if path and path not in seen:
            seen.append(path)
    return seen


def is_credential_blocked(bead: Dict[str, Any]) -> bool:
    """True when an open bead's own text records a credential-read failure
    against at least one secret path.

    Skips `unravel-proposal` beads: those are alternative *proposals about*
    the blocker class (their descriptions quote it as evidence), not work
    blocked by it — annotating them would be noise on top of the signal.
    """
    if (bead.get("labels") or []) and "unravel-proposal" in (bead.get("labels") or []):
        return False
    if UNBLOCK_MARKER in (bead.get("notes") or ""):
        return False
    text = bead_text(bead)
    lowered = text.lower()
    if not any(re.search(marker, lowered) for marker in DENIAL_MARKERS):
        return False
    return bool(extract_secret_paths(text))


def find_credential_blocked_beads(
    beads: List[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], List[str]]]:
    """(bead, secret paths) for every open bead matching the failure shape."""
    results: List[Tuple[Dict[str, Any], List[str]]] = []
    for bead in beads:
        if bead.get("status") != "open":
            continue  # an in_progress bead has a live worker claim, which wins
        text = bead_text(bead)
        if not is_credential_blocked(bead):
            continue
        results.append((bead, extract_secret_paths(text)))
    return results


# ---------------------------------------------------------------------------
# step 1 — existence via the provisioning identity (metadata only)
# ---------------------------------------------------------------------------


def probe_secret_path(
    path: str, bao_as_bin: Optional[str]
) -> Dict[str, Any]:
    """Existence check for one secret path, values untouched.

    Runs `bao-as openbao-v2-provision bao kv metadata get` — the write-only
    identity may read metadata (it needs it for -cas) but can never read a
    value, so the probe cannot leak one even in principle.
    """
    no_check = {"path": path, "verdict": VERIF_UNREACHABLE, "detail": "unavailable"}
    if bao_as_bin is None:
        no_check["detail"] = "bao-as CLI not found - existence not checked"
        return no_check
    try:
        result = run_command(
            [
                bao_as_bin,
                BAO_PROVISION_INSTANCE,
                "bao",
                "kv",
                "metadata",
                "get",
                "-format=json",
                path,
            ],
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return {"path": path, "verdict": VERIF_UNREACHABLE, "detail": "probe timed out"}

    stderr = (result.stderr or "").strip()
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout).get("data", {})
            version = data.get("current_version")
            if version is not None:
                return {
                    "path": path,
                    "verdict": VERIF_EXISTS,
                    "detail": f"current_version={version}",
                }
        except (json.JSONDecodeError, AttributeError):
            pass
        return {
            "path": path,
            "verdict": VERIF_UNREACHABLE,
            "detail": "metadata read returned no parsable version",
        }

    if "no value found" in stderr.lower():
        return {
            "path": path,
            "verdict": VERIF_MISSING,
            "detail": "no value found at path",
        }
    if "permission denied" in stderr.lower() or "403" in stderr:
        return {
            "path": path,
            "verdict": VERIF_DENIED,
            "detail": "403 from the provisioning identity - sanctioned denial, stop",
        }
    return {
        "path": path,
        "verdict": VERIF_UNREACHABLE,
        "detail": f"probe failed: {stderr[:200] or 'no stderr'}",
    }


# ---------------------------------------------------------------------------
# steps 2+3 — delivery wiring and property verification
# ---------------------------------------------------------------------------


def expand_unit_specifier(value: str) -> str:
    """Expand the one systemd specifier the unit uses for the runtime dir."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return value.replace("%t", runtime_dir).replace("%U", str(os.getuid()))


def check_delivery(
    workspace: Path,
    secret_path: str,
    health_url: str,
    http_get: Callable[[str, int], Optional[Dict[str, Any]]] = http_get_json,
) -> Dict[str, Any]:
    """Property-only verification that runtime delivery is live for a path.

    Three properties, each checkable without reading a value:
      wired      the unit declares the ExecStartPre fetch and the
                 TELEGRAM_BOT_TOKEN_FILE the server reads
      file       the delivered file exists, is mode 600, and is non-empty
      service    the status endpoint reports the integration configured
    `applies` is False when the bead's path is not the one the unit
    delivers — the properties are then reported for the wired path only.
    """
    result: Dict[str, Any] = {
        "applies": False,
        "wired": False,
        "file": None,
        "service": None,
    }

    unit_path = workspace / "deploy" / "aide-de-camp.service"
    try:
        unit_text = unit_path.read_text(encoding="utf-8")
    except OSError:
        return result

    file_match = re.search(r"^Environment=TELEGRAM_BOT_TOKEN_FILE=(\S+)", unit_text, re.M)
    fetch_wired = "fetch_runtime_secrets" in unit_text and "ExecStartPre" in unit_text
    if not (fetch_wired and file_match):
        return result
    result["wired"] = True

    delivered_path = extract_secret_paths(
        re.search(
            r"^Environment=TELEGRAM_BOT_TOKEN_PATH=(\S+)", unit_text, re.M
        ).group(1)
        if re.search(r"^Environment=TELEGRAM_BOT_TOKEN_PATH=(\S+)", unit_text, re.M)
        else ""
    )
    result["applies"] = bool(delivered_path and delivered_path[0] == secret_path)
    result["delivered_path"] = delivered_path[0] if delivered_path else None

    target = expand_unit_specifier(file_match.group(1))
    try:
        mode = stat.S_IMODE(os.stat(target).st_mode)
        size = os.path.getsize(target)
        result["file"] = {
            "path": target,
            "exists": True,
            "mode": format(mode, "o"),
            "mode_ok": mode == 0o600,
            "nonempty": size > 0,
        }
    except OSError:
        result["file"] = {"path": target, "exists": False}

    status = http_get(health_url, 3)
    if status is not None:
        result["service"] = {
            "url": health_url,
            "reachable": True,
            "bot_configured": bool(status.get("bot_configured")),
        }
    else:
        result["service"] = {"url": health_url, "reachable": False}
    return result


def delivery_is_proven(delivery: Dict[str, Any]) -> bool:
    """True only when every property holds for the bead's own path."""
    if not (delivery.get("applies") and delivery.get("wired")):
        return False
    file_prop = delivery.get("file") or {}
    service_prop = delivery.get("service") or {}
    return bool(
        file_prop.get("exists")
        and file_prop.get("mode_ok")
        and file_prop.get("nonempty")
        and service_prop.get("reachable")
        and service_prop.get("bot_configured")
    )


# ---------------------------------------------------------------------------
# step 4 — annotate the bead
# ---------------------------------------------------------------------------


def build_note(
    probes: List[Dict[str, Any]], delivery: Dict[str, Any], verified: bool
) -> str:
    """The note that unblocks dependents — properties and paths only."""
    lines = [UNBLOCK_MARKER, ""]
    lines.append(
        "Runtime secret delivery — the consuming process fetches its own "
        "value at start; no agent or human read access is needed. (1)-(4) "
        "per scripts/unblock_credential_gated_beads.py:"
    )
    for probe in probes:
        verdict = probe["verdict"]
        detail = probe["detail"]
        if verdict == VERIF_EXISTS:
            lines.append(
                f"- {probe['path']}: exists on {BAO_INSTANCE} "
                f"({detail}; confirmed via the write-only provisioning "
                f"identity, metadata only)."
            )
        elif verdict == VERIF_PREFIX:
            lines.append(f"- {probe['path']}: prefix exists ({detail}).")
        elif verdict == VERIF_MISSING:
            lines.append(f"- {probe['path']}: NOT FOUND ({detail}) - nothing to deliver.")
        elif verdict == VERIF_DENIED:
            lines.append(f"- {probe['path']}: 403 - sanctioned denial ({detail}).")
        else:
            lines.append(f"- {probe['path']}: could not check ({detail}).")

    if delivery.get("wired"):
        lines.append(
            "- Delivery is runtime-side: deploy/aide-de-camp.service "
            "ExecStartPre (deploy/fetch_runtime_secrets.sh) pipes "
            f"`bao-as {BAO_INSTANCE} bao kv get -field=<key>` into a mode-600 "
            "file under /run/user/$UID; the server reads it via "
            "TELEGRAM_BOT_TOKEN_FILE. Never a literal in a manifest, bead, "
            "note, or command line."
        )
        if delivery.get("applies"):
            file_prop = delivery.get("file") or {}
            service_prop = delivery.get("service") or {}
            if verified:
                mode = file_prop.get("mode")
                lines.append(
                    f"- Verified by property {now_utc()}: delivered file "
                    f"{file_prop.get('path')} present (mode {mode}, "
                    f"non-empty; value never read back) and "
                    f"{(service_prop.get('url') or DEFAULT_HEALTH_URL)} "
                    f"reports bot_configured=true."
                )
            else:
                lines.append(
                    f"- NOT yet verified: file="
                    f"{json.dumps(file_prop)}, service="
                    f"{json.dumps(service_prop)} — this path's delivery is "
                    f"wired but its properties do not yet prove live."
                )
        else:
            delivered = delivery.get("delivered_path") or "<unparsable>"
            lines.append(
                f"- No runtime delivery is wired for this path yet "
                f"(the unit delivers {delivered}); wire it per the "
                f"ExecStartPre pattern above."
            )
    else:
        lines.append(
            "- No runtime delivery is wired in deploy/aide-de-camp.service "
            "for this path; wire one per the ExecStartPre pattern in "
            "deploy/fetch_runtime_secrets.sh before depending on it."
        )

    lines.append(
        "- The escalation this blocker class was waiting on (a human grant) "
        "no longer exists on the delivered path: dependents may proceed "
        "without it."
    )
    return "\n".join(lines)


def annotate_bead(
    bead_id: str, note: str, bead_bin: str, workspace: Path
) -> None:
    """Append the note to the bead's existing notes under --if-revision.

    `bead update --notes` REPLACES the whole field, so the current notes are
    read back immediately before the write and combined; the update carries
    --if-revision from that same read, so a concurrent edit exits 4 instead
    of silently clobbering either side.
    """
    shown = run_command(
        [bead_bin, "show", "--json", bead_id], timeout=60
    )
    if shown.returncode != 0:
        raise RuntimeError(
            f"bead show --json {bead_id} failed: {shown.stderr.strip()[:300]}"
        )
    current = next(
        (
            b
            for b in normalize_bead_stream(shown.stdout)
            if b.get("id") == bead_id
        ),
        None,
    )
    if current is None:
        raise RuntimeError(f"bead show --json {bead_id} returned no matching bead")
    existing = (current.get("notes") or "").rstrip()
    combined = f"{existing}\n\n{note}" if existing else note
    command = [bead_bin, "update", bead_id, "--notes", combined]
    if current.get("revision") is not None:
        command += ["--if-revision", str(current["revision"])]
    updated = run_command(command, timeout=60)
    if updated.returncode != 0:
        raise RuntimeError(
            f"bead update {bead_id} failed (rc={updated.returncode}): "
            f"{updated.stderr.strip()[:300]}"
        )


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def unblock(
    workspace: Path,
    bead_bin: str,
    bao_as_bin: Optional[str] = None,
    health_url: str = DEFAULT_HEALTH_URL,
    dry_run: bool = False,
    only_beads: Optional[List[str]] = None,
    run_bead_list: Optional[Callable[..., List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Process every credential-gated bead; returns one record per bead."""
    if run_bead_list is None:
        def run_bead_list(args, bead_bin, workspace):  # noqa: F811
            result = run_command(
                [bead_bin, "list", *args, "--json", "--limit", str(BEAD_LIST_LIMIT)],
                timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(f"bead list {args} failed: {result.stderr[:300]}")
            return normalize_bead_stream(result.stdout)

    open_beads = run_bead_list(["--status", "open"], bead_bin, workspace)
    candidates = find_credential_blocked_beads(open_beads)
    if only_beads is not None:
        wanted = set(only_beads)
        candidates = [c for c in candidates if c[0].get("id") in wanted]
        missing = wanted - {c[0].get("id") for c in candidates}
        for bead_id in sorted(missing):
            print(
                f"SKIP {bead_id}: not an open bead recording a credential-read failure",
                file=sys.stderr,
            )

    records: List[Dict[str, Any]] = []
    for bead, paths in candidates:
        bead_id = bead.get("id")
        probes = [probe_secret_path(p, bao_as_bin) for p in paths]
        # Delivery properties are per-path; the unit wires one canonical
        # path, so verify against the first probe's path (the note says so
        # for the rest).
        delivery = (
            check_delivery(workspace, probes[0]["path"], health_url, http_get_json)
            if probes
            else {"applies": False, "wired": False, "file": None, "service": None}
        )
        verified = delivery_is_proven(delivery)
        note = build_note(probes, delivery, verified)
        record: Dict[str, Any] = {
            "id": bead_id,
            "title": bead.get("title"),
            "paths": paths,
            "probes": probes,
            "delivery_verified": verified,
            "dry_run": dry_run,
            "annotated": False,
        }
        if dry_run:
            record["note"] = note
            records.append(record)
            continue
        try:
            annotate_bead(bead_id, note, bead_bin, workspace)
            record["annotated"] = True
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            record["error"] = str(exc)[:400]
        records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unblock beads whose notes record a credential-read failure "
        "by confirming the secret path and recording runtime delivery."
    )
    parser.add_argument("--workspace", default="/home/coding/aide-de-camp")
    parser.add_argument("--bead-bin", default=None)
    parser.add_argument("--bao-as-bin", default=None)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", nargs="*", default=None, metavar="BEAD_ID")
    parser.add_argument(
        "--json", action="store_true", help="emit one JSON summary to stdout"
    )
    args = parser.parse_args()

    def log(level: str, message: str) -> None:
        line = f"[{now_utc()}] [{level}] {message}"
        print(line, file=sys.stderr)
        try:
            with open(args.log_file, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    try:
        bead_bin = resolve_bead_bin(args.bead_bin)
    except RuntimeError as exc:
        log("ERROR", str(exc))
        return 3
    bao_as_bin = resolve_bao_as_bin(args.bao_as_bin)
    if bao_as_bin is None:
        log("WARN", "bao-as CLI not found - probes will record 'could not check'")

    workspace = Path(args.workspace)
    try:
        records = unblock(
            workspace=workspace,
            bead_bin=bead_bin,
            bao_as_bin=bao_as_bin,
            health_url=args.health_url,
            dry_run=args.dry_run,
            only_beads=args.only,
        )
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        log("ERROR", f"credential-gated bead unblock failed: {exc}")
        return 3

    annotated = sum(1 for r in records if r.get("annotated"))
    if not records:
        log("INFO", "No open beads record a credential-read failure - nothing to do")
    for record in records:
        if record.get("annotated"):
            log(
                "INFO",
                f"Annotated credential-gated bead {record['id']} "
                f"(paths: {', '.join(record['paths'])}; delivery verified: "
                f"{record['delivery_verified']})",
            )
        elif record.get("error"):
            log("ERROR", f"{record['id']}: {record['error']}")
        elif args.dry_run:
            log("INFO", f"[dry-run] Would annotate {record['id']}")

    if args.json:
        print(
            json.dumps(
                {
                    "checked_at": now_utc(),
                    "workspace": str(workspace),
                    "dry_run": args.dry_run,
                    "candidates": len(records),
                    "annotated": annotated,
                    "records": records,
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
