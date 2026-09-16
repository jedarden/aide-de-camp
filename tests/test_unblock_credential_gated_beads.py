"""Unit tests for scripts/unblock_credential_gated_beads.py.

Covers the pure decision logic — discovery of the credential-read-failure
shape, secret-path extraction, provisioning-identity probe verdicts, the
property-only delivery check, note composition, and the annotate step —
using stubs so no test touches the live bead store, OpenBao, or the running
server. The recipe under test retires the "OpenBao permission denied"
blocker class by proving runtime delivery, never by reading a value.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "unblock_credential_gated_beads.py"
_spec = importlib.util.spec_from_file_location("unblock_credential_gated_beads", _SCRIPT)
ucgb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ucgb)


def make_bead(bead_id, title="Capture and store credentials", **overrides):
    bead = {
        "id": bead_id,
        "title": title,
        "status": "open",
        "effective_status": "open",
        "assignee": None,
        "labels": [],
        "manual_blocked": False,
        "dependencies": [],
        "notes": "",
        "description": "",
        "revision": 1,
    }
    bead.update(overrides)
    return bead


HISTORICAL_NOTE = (
    "BLOCKED by OpenBao permission denied - cannot read "
    "secret/ardenone-cluster/aide-de-camp/telegram_bot_token."
)

TOKEN_PATH = "secret/ardenone-cluster/aide-de-camp/telegram_bot_token"


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_historical_permission_denied_shape_is_found():
    bead = make_bead("a", notes=HISTORICAL_NOTE)
    found = ucgb.find_credential_blocked_beads([bead])
    assert [b["id"] for b, _ in found] == ["a"]
    assert found[0][1] == [TOKEN_PATH]


def test_openbao_permissions_shape_from_aidedeca_73d9fe27_is_found():
    bead = make_bead(
        "a",
        notes="❌ BLOCKED: OpenBao permissions\n"
        "- Cannot access 'secret/ardenone-cluster/aide-de-camp/*' paths\n"
        "- Both read and write operations return 'permission denied'",
    )
    found = ucgb.find_credential_blocked_beads([bead])
    assert [b["id"] for b, _ in found] == ["a"]
    # The glob is stripped to the prefix.
    assert found[0][1] == ["secret/ardenone-cluster/aide-de-camp"]


def test_denial_without_a_secret_path_is_ignored():
    bead = make_bead("a", notes="permission denied on kubectl get pods -n foo")
    assert ucgb.find_credential_blocked_beads([bead]) == []


def test_secret_path_without_a_denial_is_ignored():
    bead = make_bead(
        "a",
        notes="stored at secret/ardenone-cluster/aide-de-camp/telegram_bot_token",
    )
    assert ucgb.find_credential_blocked_beads([bead]) == []


def test_unravel_proposals_are_skipped():
    """Unravel alternatives *describe* the blocker class in their bodies;
    they are not blocked by it."""
    bead = make_bead(
        "a", notes=HISTORICAL_NOTE, labels=["unravel-proposal", "starvation:unresolved"]
    )
    assert ucgb.find_credential_blocked_beads([bead]) == []


def test_already_annotated_bead_is_skipped():
    bead = make_bead("a", notes=f"{HISTORICAL_NOTE}\n\n{ucgb.UNBLOCK_MARKER} done")
    assert ucgb.find_credential_blocked_beads([bead]) == []


def test_in_progress_bead_is_skipped():
    """A live worker's claim wins, same rule as the starvation enricher."""
    bead = make_bead("a", notes=HISTORICAL_NOTE, status="in_progress")
    assert ucgb.find_credential_blocked_beads([bead]) == []


def test_marker_in_description_also_counts():
    bead = make_bead("a", description=f"Blocked: {HISTORICAL_NOTE}")
    assert ucgb.find_credential_blocked_beads([bead]) != []


# ---------------------------------------------------------------------------
# path extraction
# ---------------------------------------------------------------------------


def test_trailing_sentence_period_is_stripped():
    assert ucgb.extract_secret_paths(f"cannot read {TOKEN_PATH}.") == [TOKEN_PATH]


def test_trailing_slash_is_stripped():
    assert ucgb.extract_secret_paths(f"{TOKEN_PATH}/ is the path") == [TOKEN_PATH]


def test_glob_prefix_is_stripped_to_parent():
    assert ucgb.extract_secret_paths("secret/ardenone-cluster/aide-de-camp/*") == [
        "secret/ardenone-cluster/aide-de-camp"
    ]


def test_paths_are_deduplicated_in_order():
    text = f"{TOKEN_PATH} and again {TOKEN_PATH}"
    assert ucgb.extract_secret_paths(text) == [TOKEN_PATH]


# ---------------------------------------------------------------------------
# probe verdicts (metadata only, via the write-only identity)
# ---------------------------------------------------------------------------


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_probe(monkeypatch, result=None, exc=None):
    calls = []

    def _run(command, timeout=60):
        calls.append(command)
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(ucgb, "run_command", _run)
    return calls


def test_probe_exists_reports_version(monkeypatch):
    result = FakeResult(
        0,
        stdout='{"data": {"current_version": 4, "created_time": "t", "updated_time": "t"}}',
    )
    fake_probe(monkeypatch, result)

    probe = ucgb.probe_secret_path(TOKEN_PATH, "/usr/bin/bao-as")

    assert probe["verdict"] == ucgb.VERIF_EXISTS
    assert probe["detail"] == "current_version=4"
    # The probe must go through the WRITE-ONLY identity.
    calls = fake_probe(monkeypatch, result)
    ucgb.probe_secret_path(TOKEN_PATH, "/usr/bin/bao-as")
    assert "openbao-v2-provision" in calls[0]
    assert "metadata" in calls[0]


def test_probe_missing(monkeypatch):
    fake_probe(monkeypatch, FakeResult(1, stderr="No value found at secret/metadata/x"))

    probe = ucgb.probe_secret_path(TOKEN_PATH, "/usr/bin/bao-as")

    assert probe["verdict"] == ucgb.VERIF_MISSING


def test_probe_denied_is_sanctioned(monkeypatch):
    fake_probe(monkeypatch, FakeResult(1, stderr="permission denied"))

    probe = ucgb.probe_secret_path(TOKEN_PATH, "/usr/bin/bao-as")

    assert probe["verdict"] == ucgb.VERIF_DENIED
    assert "sanctioned" in probe["detail"]


def test_probe_unreachable(monkeypatch):
    fake_probe(monkeypatch, FakeResult(1, stderr="connection refused"))

    probe = ucgb.probe_secret_path(TOKEN_PATH, "/usr/bin/bao-as")

    assert probe["verdict"] == ucgb.VERIF_UNREACHABLE


def test_probe_timeout_is_unreachable(monkeypatch):
    fake_probe(monkeypatch, exc=subprocess.TimeoutExpired(cmd="bao", timeout=45))

    probe = ucgb.probe_secret_path(TOKEN_PATH, "/usr/bin/bao-as")

    assert probe["verdict"] == ucgb.VERIF_UNREACHABLE


def test_probe_without_bao_as_cannot_check(monkeypatch):
    probe = ucgb.probe_secret_path(TOKEN_PATH, None)

    assert probe["verdict"] == ucgb.VERIF_UNREACHABLE
    assert "not found" in probe["detail"]


# ---------------------------------------------------------------------------
# delivery property check
# ---------------------------------------------------------------------------


def make_workspace(tmp_path, token_path=TOKEN_PATH, wired=True, unit_text=None):
    """A workspace dir whose unit declares (or not) the ExecStartPre fetch."""
    deploy = tmp_path / "deploy"
    deploy.mkdir(exist_ok=True)
    if unit_text is None:
        fetch = (
            "ExecStartPre=/home/coding/aide-de-camp/deploy/fetch_runtime_secrets.sh\n"
            if wired
            else ""
        )
        unit_text = (
            "[Service]\n"
            f"{fetch}"
            f"Environment=TELEGRAM_BOT_TOKEN_FILE=%t/aide-de-camp/telegram_bot_token\n"
            f"Environment=TELEGRAM_BOT_TOKEN_PATH={token_path}\n"
        )
    (deploy / "aide-de-camp.service").write_text(unit_text)
    return tmp_path


def fake_http(status=None):
    def _get(url, timeout=3):
        return status

    return _get


def test_delivery_proven_when_every_property_holds(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    runtime_dir = tmp_path / "runtime"
    token_file = runtime_dir / "aide-de-camp" / "telegram_bot_token"
    token_file.parent.mkdir(parents=True)
    token_file.write_text("x")
    token_file.chmod(0o600)
    monkeypatch.setattr(ucgb, "expand_unit_specifier", lambda v: str(token_file))

    delivery = ucgb.check_delivery(
        workspace, TOKEN_PATH, "http://x/status", fake_http({"bot_configured": True})
    )

    assert delivery["wired"] and delivery["applies"]
    assert ucgb.delivery_is_proven(delivery)


def test_delivery_fails_on_wrong_mode(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    token_file = tmp_path / "telegram_bot_token"
    token_file.write_text("x")
    token_file.chmod(0o644)
    monkeypatch.setattr(ucgb, "expand_unit_specifier", lambda v: str(token_file))

    delivery = ucgb.check_delivery(
        workspace, TOKEN_PATH, "http://x/status", fake_http({"bot_configured": True})
    )

    assert delivery["file"]["mode_ok"] is False
    assert not ucgb.delivery_is_proven(delivery)


def test_delivery_fails_when_endpoint_not_configured(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    token_file = tmp_path / "telegram_bot_token"
    token_file.write_text("x")
    token_file.chmod(0o600)
    monkeypatch.setattr(ucgb, "expand_unit_specifier", lambda v: str(token_file))

    delivery = ucgb.check_delivery(
        workspace, TOKEN_PATH, "http://x/status", fake_http({"bot_configured": False})
    )

    assert not ucgb.delivery_is_proven(delivery)


def test_delivery_fails_when_endpoint_down(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    token_file = tmp_path / "telegram_bot_token"
    token_file.write_text("x")
    token_file.chmod(0o600)
    monkeypatch.setattr(ucgb, "expand_unit_specifier", lambda v: str(token_file))

    delivery = ucgb.check_delivery(workspace, TOKEN_PATH, "http://x/status", fake_http(None))

    assert delivery["service"]["reachable"] is False
    assert not ucgb.delivery_is_proven(delivery)


def test_delivery_fails_when_file_missing(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    monkeypatch.setattr(
        ucgb, "expand_unit_specifier", lambda v: str(tmp_path / "nope")
    )

    delivery = ucgb.check_delivery(
        workspace, TOKEN_PATH, "http://x/status", fake_http({"bot_configured": True})
    )

    assert delivery["file"]["exists"] is False
    assert not ucgb.delivery_is_proven(delivery)


def test_delivery_not_wired_without_unit_declarations(tmp_path):
    workspace = make_workspace(tmp_path, wired=False)

    delivery = ucgb.check_delivery(
        workspace, TOKEN_PATH, "http://x/status", fake_http({"bot_configured": True})
    )

    assert delivery["wired"] is False
    assert not ucgb.delivery_is_proven(delivery)


def test_delivery_does_not_apply_to_other_paths(tmp_path, monkeypatch):
    workspace = make_workspace(tmp_path)
    delivery = ucgb.check_delivery(
        workspace,
        "secret/other/app/api_key",
        "http://x/status",
        fake_http({"bot_configured": True}),
    )

    assert delivery["applies"] is False
    assert not ucgb.delivery_is_proven(delivery)


def test_expand_unit_specifier(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert ucgb.expand_unit_specifier("%t/aide-de-camp/x") == str(
        tmp_path / "aide-de-camp" / "x"
    )
    # %U is the uid (systemd semantics), independent of XDG_RUNTIME_DIR.
    assert ucgb.expand_unit_specifier("/run/user/%U/x") == f"/run/user/{os.getuid()}/x"


# ---------------------------------------------------------------------------
# note composition
# ---------------------------------------------------------------------------


def test_note_contains_properties_not_values():
    probes = [{"path": TOKEN_PATH, "verdict": ucgb.VERIF_EXISTS, "detail": "current_version=4"}]
    delivery = {"applies": False, "wired": False, "file": None, "service": None}

    note = ucgb.build_note(probes, delivery, verified=False)

    assert ucgb.UNBLOCK_MARKER in note
    assert "current_version=4" in note
    assert "no agent or human read access" in note
    assert "ExecStartPre" in note


def test_note_for_missing_path_says_nothing_to_deliver():
    probes = [{"path": TOKEN_PATH, "verdict": ucgb.VERIF_MISSING, "detail": "no value found at path"}]
    delivery = {"applies": False, "wired": False, "file": None, "service": None}

    note = ucgb.build_note(probes, delivery, verified=False)

    assert "NOT FOUND" in note


def test_note_for_sanctioned_denial_records_and_stops():
    probes = [{"path": TOKEN_PATH, "verdict": ucgb.VERIF_DENIED, "detail": "403 - sanctioned denial, stop"}]
    delivery = {"applies": False, "wired": False, "file": None, "service": None}

    note = ucgb.build_note(probes, delivery, verified=False)

    assert "403" in note and "sanctioned denial" in note


def test_note_unverified_delivery_states_what_is_missing():
    probes = [{"path": TOKEN_PATH, "verdict": ucgb.VERIF_EXISTS, "detail": "current_version=4"}]
    delivery = {
        "applies": True,
        "wired": True,
        "file": {"path": "/run/user/1000/aide-de-camp/telegram_bot_token", "exists": False},
        "service": {"url": "http://x", "reachable": False},
        "delivered_path": TOKEN_PATH,
    }

    note = ucgb.build_note(probes, delivery, verified=False)

    assert "NOT yet verified" in note
    assert '"exists": false' in note.lower()


def test_note_for_unwired_path_names_the_gap():
    probes = [{"path": "secret/other/app/api_key", "verdict": ucgb.VERIF_EXISTS, "detail": "current_version=1"}]
    delivery = {
        "applies": False,
        "wired": True,
        "file": None,
        "service": None,
        "delivered_path": TOKEN_PATH,
    }

    note = ucgb.build_note(probes, delivery, verified=False)

    assert "No runtime delivery is wired for this path yet" in note
    assert TOKEN_PATH in note


# ---------------------------------------------------------------------------
# annotate + orchestration
# ---------------------------------------------------------------------------


def test_annotate_appends_under_if_revision(monkeypatch, tmp_path):
    calls = []

    def _run(command, timeout=60):
        calls.append(command)
        if command[1] == "show":
            bead = make_bead("a", notes=HISTORICAL_NOTE, revision=7)
            return FakeResult(0, stdout=json.dumps(bead) + "\n")
        return FakeResult(0)

    monkeypatch.setattr(ucgb, "run_command", _run)

    ucgb.annotate_bead("a", "the note", "bead", tmp_path)

    update = calls[1]
    assert update[1] == "update"
    assert "--if-revision" in update
    assert update[update.index("--if-revision") + 1] == "7"
    # Appended, not replaced.
    combined = update[update.index("--notes") + 1]
    assert combined.startswith(HISTORICAL_NOTE)
    assert combined.endswith("the note")


def test_annotate_raises_when_show_returns_wrong_bead(monkeypatch, tmp_path):
    def _run(command, timeout=60):
        bead = make_bead("other")
        return FakeResult(0, stdout=json.dumps(bead) + "\n")

    monkeypatch.setattr(ucgb, "run_command", _run)

    with pytest.raises(RuntimeError, match="no matching bead"):
        ucgb.annotate_bead("a", "note", "bead", tmp_path)


def test_annotate_failure_is_recorded_not_raised(monkeypatch, tmp_path):
    def _run(command, timeout=60):
        bead = make_bead("a", notes=HISTORICAL_NOTE, revision=1)
        if command[1] == "show":
            return FakeResult(0, stdout=json.dumps(bead) + "\n")
        return FakeResult(4, stderr="stale revision")

    monkeypatch.setattr(ucgb, "run_command", _run)

    records = ucgb.unblock(
        tmp_path,
        bead_bin="bead",
        bao_as_bin="/usr/bin/bao-as",
        run_bead_list=lambda args, bead_bin, workspace: [
            make_bead("a", notes=HISTORICAL_NOTE)
        ],
    )

    assert records[0]["annotated"] is False
    assert "rc=4" in records[0]["error"]


def test_dry_run_annotates_nothing(monkeypatch, tmp_path):
    updated = []

    def _run(command, timeout=60):
        if command[1] == "update":
            updated.append(command)
        bead = make_bead("a", notes=HISTORICAL_NOTE, revision=1)
        return FakeResult(0, stdout=f"{bead}\n")

    monkeypatch.setattr(ucgb, "run_command", _run)
    monkeypatch.setattr(
        ucgb,
        "probe_secret_path",
        lambda path, bao_as: {"path": path, "verdict": ucgb.VERIF_EXISTS, "detail": "current_version=4"},
    )
    monkeypatch.setattr(
        ucgb,
        "check_delivery",
        lambda w, p, u, h: {"applies": True, "wired": True, "file": {"path": "/x", "exists": True, "mode": "600", "mode_ok": True, "nonempty": True}, "service": {"url": u, "reachable": True, "bot_configured": True}, "delivered_path": p},
    )

    records = ucgb.unblock(
        tmp_path,
        bead_bin="bead",
        bao_as_bin="/usr/bin/bao-as",
        dry_run=True,
        run_bead_list=lambda args, bead_bin, workspace: [
            make_bead("a", notes=HISTORICAL_NOTE)
        ],
    )

    assert updated == []
    assert records[0]["dry_run"] is True
    assert records[0]["delivery_verified"] is True
    assert ucgb.UNBLOCK_MARKER in records[0]["note"]


def test_only_beads_filters_candidates(monkeypatch, tmp_path):
    annotated = []
    monkeypatch.setattr(
        ucgb,
        "probe_secret_path",
        lambda path, bao_as: {"path": path, "verdict": ucgb.VERIF_MISSING, "detail": "no value found"},
    )
    monkeypatch.setattr(
        ucgb, "annotate_bead", lambda bead_id, note, bead_bin, workspace: annotated.append(bead_id)
    )
    records = ucgb.unblock(
        tmp_path,
        bead_bin="bead",
        bao_as_bin="/usr/bin/bao-as",
        only_beads=["b"],
        run_bead_list=lambda args, bead_bin, workspace: [
            make_bead("a", notes=HISTORICAL_NOTE),
            make_bead("b", notes=HISTORICAL_NOTE),
        ],
    )

    assert [r["id"] for r in records] == ["b"]
    assert annotated == ["b"]
