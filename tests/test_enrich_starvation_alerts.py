"""Unit tests for scripts/enrich_starvation_alerts.py (bead aidedeca-2a3e09ac).

Covers the pure decision logic (discovery, frontier classification, starvation
classification, recovery-summary parsing, note formatting), the offset-based
recovery-log read, and the resolution step that closes the two
deterministically-decided classes, using stubs so no test touches the live bead
store or the real bead CLI.
"""

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "enrich_starvation_alerts.py"
_spec = importlib.util.spec_from_file_location("enrich_starvation_alerts", _SCRIPT)
esa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(esa)


def make_bead(bead_id, title="Starvation alert: beads invisible in ", **overrides):
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
    }
    bead.update(overrides)
    return bead


# ---------------------------------------------------------------------------
# normalize_bead_stream
# ---------------------------------------------------------------------------


def test_normalize_jsonl_lines():
    out = '{"id": "a"}\n{"id": "b"}\n'
    assert [b["id"] for b in esa.normalize_bead_stream(out)] == ["a", "b"]


def test_normalize_bare_empty_array():
    assert esa.normalize_bead_stream("[]\n") == []
    assert esa.normalize_bead_stream("") == []


def test_normalize_nested_arrays():
    out = '[{"id": "a"}, {"id": "b"}]\n[{"id": "c"}]\n'
    assert [b["id"] for b in esa.normalize_bead_stream(out)] == ["a", "b", "c"]


def test_normalize_skips_non_json_progress_lines():
    out = 'Fetching beads...\n{"id": "a"}\n'
    assert [b["id"] for b in esa.normalize_bead_stream(out)] == ["a"]


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_find_alert_beads_matches_title_marker_any_prefix():
    plain = make_bead("a", "Starvation alert: beads invisible in ws")
    unravel = make_bead("b", "[Unravel] Starvation alert: beads invisible in ws — fix it")
    other = make_bead("c", "Unrelated task")
    found = esa.find_alert_beads([plain, unravel, other])
    assert [b["id"] for b in found] == ["a", "b"]


def test_find_alert_beads_skips_in_progress():
    working = make_bead("a", status="in_progress")
    assert esa.find_alert_beads([working]) == []


def test_find_alert_beads_skips_already_labeled():
    labeled = make_bead("a", labels=["starvation:legitimately-blocked"])
    assert esa.find_alert_beads([labeled]) == []


def test_find_alert_beads_skips_already_annotated():
    annotated = make_bead("a", notes=f"earlier note\n{esa.ENRICHMENT_MARKER}\n- x")
    assert esa.find_alert_beads([annotated]) == []


# ---------------------------------------------------------------------------
# frontier classification
# ---------------------------------------------------------------------------


def test_classify_frontier_buckets_manual_and_dependency_blocked():
    open_beads = [
        make_bead("m", manual_blocked=True),
        make_bead("h", labels=["human"]),
        make_bead("d", dependencies=[{"blocker": "blocker-1", "kind": "blocks"}]),
        make_bead("u"),
    ]
    all_beads = open_beads + [make_bead("blocker-1", status="open")]
    frontier = esa.classify_frontier(open_beads, all_beads)
    assert frontier["human_blocked"] == ["m", "h"]
    assert frontier["dependency_blocked"] == ["d"]
    assert frontier["other"] == ["u"]
    assert frontier["all_explained"] is False


def test_classify_frontier_all_explained_requires_nonempty_queue():
    # Vacuous truth guard: a workspace with zero open beads is NOT legitimately
    # blocked - it must stay loud.
    frontier = esa.classify_frontier([], [])
    assert frontier["total_open"] == 0
    assert frontier["all_explained"] is False


def test_classify_frontier_closed_blocker_does_not_explain():
    # A bead whose blockers are all closed should be claimable; if it is open,
    # unassigned and still not ready, that is genuinely unexplained.
    open_beads = [make_bead("a", dependencies=[{"blocker": "b1", "kind": "blocks"}])]
    all_beads = open_beads + [make_bead("b1", status="closed")]
    frontier = esa.classify_frontier(open_beads, all_beads)
    assert frontier["unexplained"] == 1
    assert frontier["all_explained"] is False


def test_classify_frontier_missing_blocker_counts_as_unclosed():
    open_beads = [make_bead("a", dependencies=[{"blocker": "ghost", "kind": "blocks"}])]
    frontier = esa.classify_frontier(open_beads, open_beads)
    assert frontier["dependency_blocked"] == ["a"]


# ---------------------------------------------------------------------------
# starvation classification
# ---------------------------------------------------------------------------


def test_classify_legitimately_blocked_when_all_open_beads_blocked():
    frontier = {
        "total_open": 7,
        "human_blocked": ["a", "b"],
        "dependency_blocked": ["c", "d", "e", "f", "g"],
        "other": [],
        "unexplained": 0,
        "all_explained": True,
    }
    label, reason = esa.classify_starvation(frontier, {"ready": 0}, None)
    assert label == esa.LABEL_LEGITIMATELY_BLOCKED
    assert "7 open bead" in reason


def test_classify_auto_recovered_when_ready_frontier_grew():
    frontier = {
        "total_open": 3,
        "human_blocked": [],
        "dependency_blocked": [],
        "other": ["x"],
        "unexplained": 1,
        "all_explained": False,
        "ready": 4,
    }
    label, _ = esa.classify_starvation(frontier, {"ready": 0}, None)
    assert label == esa.LABEL_AUTO_RECOVERED


def test_classify_auto_recovered_when_visibility_restored():
    frontier = {
        "total_open": 2,
        "human_blocked": [],
        "dependency_blocked": [],
        "other": ["x"],
        "unexplained": 1,
        "all_explained": False,
        "ready": 0,
    }
    summary = {"open_beads_before": "0", "open_beads_after": "2", "recovery_successful": "true"}
    label, _ = esa.classify_starvation(frontier, {"ready": 0}, summary)
    assert label == esa.LABEL_AUTO_RECOVERED


def test_classify_unresolved_when_recovery_helped_nothing():
    frontier = {
        "total_open": 3,
        "human_blocked": [],
        "dependency_blocked": [],
        "other": ["x", "y"],
        "unexplained": 2,
        "all_explained": False,
        "ready": 0,
    }
    summary = {"open_beads_before": "3", "open_beads_after": "3", "recovery_successful": "true"}
    label, reason = esa.classify_starvation(frontier, {"ready": 0}, summary)
    assert label == esa.LABEL_UNRESOLVED
    assert "2 open bead" in reason


def test_classify_legitimately_blocked_wins_over_incidental_frontier_growth():
    # An explained frontier is legitimately blocked even if the recovery pass
    # nudged the ready count.
    frontier = {
        "total_open": 2,
        "human_blocked": ["a"],
        "dependency_blocked": ["b"],
        "other": [],
        "unexplained": 0,
        "all_explained": True,
        "ready": 3,
    }
    label, _ = esa.classify_starvation(frontier, {"ready": 1}, None)
    assert label == esa.LABEL_LEGITIMATELY_BLOCKED


# ---------------------------------------------------------------------------
# recovery log parsing
# ---------------------------------------------------------------------------

SUMMARY_LOG = (
    "[t1] noise from an older run\n"
    f"[t1] {esa.RECOVERY_SUMMARY_START}\n"
    "[t1] open_beads_before: 0\n"
    "[t1] recovery_successful: false\n"
    f"[t1] {esa.RECOVERY_SUMMARY_END}\n"
    f"[t2] {esa.RECOVERY_SUMMARY_START}\n"
    "[t2] checkpoint_age_seconds: 811\n"
    "[t2] checkpoint_stale: false\n"
    "[t2] open_beads_before: 8\n"
    "[t2] open_beads_after: 8\n"
    "[t2] recovery_successful: true\n"
    "[t2] timestamp: 2026-09-08T00:18:05Z\n"
    f"[t2] {esa.RECOVERY_SUMMARY_END}\n"
)


def test_parse_recovery_summary_takes_last_block():
    summary = esa.parse_recovery_summary(SUMMARY_LOG)
    assert summary["open_beads_before"] == "8"
    assert summary["recovery_successful"] == "true"
    assert summary["timestamp"] == "2026-09-08T00:18:05Z"


def test_parse_recovery_summary_absent():
    assert esa.parse_recovery_summary("no summary here") is None


def test_parse_recovery_summary_tolerates_truncated_block():
    truncated = f"{esa.RECOVERY_SUMMARY_START}\nrecovery_successful: true\n"
    summary = esa.parse_recovery_summary(truncated)
    assert summary is None


# ---------------------------------------------------------------------------
# note formatting
# ---------------------------------------------------------------------------


def test_format_note_carries_report_path_status_and_classification():
    note = esa.format_note(
        report_path="/tmp/pluck-starvation-diagnostic-1.json",
        overall_status="HIGH_RISK",
        recommendations=[
            "[HIGH] Run: bead sync flush-only",
            "[MEDIUM] Review bead doctor --rehearse output",
        ],
        classification=esa.LABEL_AUTO_RECOVERED,
        classification_reason="ready frontier grew 0 -> 4",
        recovery_summary={
            "open_beads_before": "0",
            "open_beads_after": "8",
            "timestamp": "2026-09-08T00:18:05Z",
        },
        report_timestamp="2026-09-08T00:18:04+00:00",
    )
    assert esa.ENRICHMENT_MARKER in note
    assert "/tmp/pluck-starvation-diagnostic-1.json" in note
    assert "Overall status: HIGH_RISK" in note
    assert esa.LABEL_AUTO_RECOVERED in note
    assert "[HIGH] Run: bead sync flush-only" in note
    assert "timestamp: 2026-09-08T00:18:05Z" in note


def test_format_note_caps_recommendations_at_five():
    recommendations = [f"rec {i}" for i in range(9)]
    note = esa.format_note(
        "/tmp/r.json", "HEALTHY", recommendations, esa.LABEL_UNRESOLVED, "why", None, "t"
    )
    assert "rec 4" in note
    assert "rec 5" not in note


def test_format_note_handles_missing_recommendations_and_summary():
    note = esa.format_note(
        "/tmp/r.json", "HEALTHY", [], esa.LABEL_LEGITIMATELY_BLOCKED, "why", None, "t"
    )
    assert "none - no actionable finding" in note
    assert f"see {esa.DEFAULT_LOG_FILE}" in note


# ---------------------------------------------------------------------------
# report path collision handling
# ---------------------------------------------------------------------------


def test_unique_report_path_suffixes_on_collision(tmp_path):
    first = esa.unique_report_path(tmp_path, "20260908_001805")
    first.write_text("{}")
    second = esa.unique_report_path(tmp_path, "20260908_001805")
    assert first.name == "pluck-starvation-diagnostic-20260908_001805.json"
    assert second.name == "pluck-starvation-diagnostic-20260908_001805-2.json"
    assert first != second


# ---------------------------------------------------------------------------
# subprocess steps against stubs (no live bead store involved)
# ---------------------------------------------------------------------------


def _write_stub(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_run_recovery_workflow_reads_only_its_own_log_block(tmp_path):
    log_file = tmp_path / "bead-recovery.log"
    log_file.write_text(
        f"{esa.RECOVERY_SUMMARY_START}\nstale_value: yes\n{esa.RECOVERY_SUMMARY_END}\n"
    )

    workspace = tmp_path / "ws"
    (workspace / "scripts").mkdir(parents=True)
    # The stub appends 40 filler lines before its summary, so a summary read
    # back from offset 0 would pick up the stale pre-existing block instead.
    _write_stub(
        workspace / "scripts" / "bead_recovery_workflow.sh",
        f"""\
#!/usr/bin/env bash
for i in $(seq 1 40); do echo "filler line $i" >> "{log_file}"; done
echo "{esa.RECOVERY_SUMMARY_START}" >> "{log_file}"
echo "open_beads_before: 8" >> "{log_file}"
echo "recovery_successful: true" >> "{log_file}"
echo "{esa.RECOVERY_SUMMARY_END}" >> "{log_file}"
""",
    )
    summary = esa.run_recovery_workflow(
        workspace,
        str(log_file),
        bead_bin="bead",
    )
    assert summary is not None
    assert summary["open_beads_before"] == "8"
    assert "stale_value" not in summary


def test_run_recovery_workflow_propagates_failure(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "scripts").mkdir(parents=True)
    _write_stub(
        workspace / "scripts" / "bead_recovery_workflow.sh",
        "#!/usr/bin/env bash\necho boom >&2\nexit 7\n",
    )
    with pytest.raises(RuntimeError, match="rc=7"):
        esa.run_recovery_workflow(workspace, str(tmp_path / "log"), bead_bin="bead")


def test_run_diagnostics_reads_report(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "scripts").mkdir(parents=True)
    report = {"metadata": {"overall_status": "HEALTHY"}}
    _write_stub(
        workspace / "scripts" / "diagnose_pluck_starvation.py",
        """\
import json, sys
args = sys.argv[1:]
out = args[args.index("--output") + 1]
with open(out, "w") as handle:
    json.dump({"metadata": {"overall_status": "HEALTHY"}}, handle)
""",
    )
    loaded, report_path = esa.run_diagnostics(
        workspace, bead_bin="bead", output_path=tmp_path / "r.json"
    )
    assert loaded == report
    assert report_path == str(tmp_path / "r.json")


def test_run_diagnostics_raises_when_report_missing(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "scripts").mkdir(parents=True)
    _write_stub(
        workspace / "scripts" / "diagnose_pluck_starvation.py", "import sys\nsys.exit(0)\n"
    )  # exits 0, writes nothing
    with pytest.raises(RuntimeError, match="unreadable"):
        esa.run_diagnostics(workspace, bead_bin="bead", output_path=tmp_path / "missing.json")


def test_run_diagnostics_raises_on_script_failure(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "scripts").mkdir(parents=True)
    _write_stub(workspace / "scripts" / "diagnose_pluck_starvation.py", "import sys\nsys.exit(3)\n")
    with pytest.raises(RuntimeError, match="rc=3"):
        esa.run_diagnostics(workspace, bead_bin="bead", output_path=tmp_path / "r.json")


# ---------------------------------------------------------------------------
# enrich() end to end against stubs
# ---------------------------------------------------------------------------


class FakeBeadList:
    """Returns queued payloads to successive run_bead_list calls."""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def __call__(self, args, bead_bin, workspace, timeout=60):
        self.calls.append(list(args))
        return self.payloads.pop(0)


def test_enrich_skips_recovery_when_no_alert_beads(tmp_path, monkeypatch):
    payloads = [
        [make_bead("plain", "Just a task")],  # --status open (before)
        [],  # --ready (before)
    ]
    monkeypatch.setattr(esa, "run_bead_list", FakeBeadList(payloads))

    def fail(*args, **kwargs):  # the recovery workflow must never be reached
        raise AssertionError("recovery workflow ran with no alert beads")

    monkeypatch.setattr(esa, "run_recovery_workflow", fail)
    records = esa.enrich(tmp_path, bead_bin="bead", log_file=str(tmp_path / "log"))
    assert records == []


def test_enrich_happy_path_attaches_report_and_label(tmp_path, monkeypatch):
    alert = make_bead("alert-1", "[Unravel] Starvation alert: beads invisible in ws — fix")
    blocker = make_bead("blocker-1", status="open")
    dependent = make_bead("dep-1", dependencies=[{"blocker": "blocker-1", "kind": "blocks"}])
    payloads = [
        [alert, make_bead("done", "Done thing")],  # open before
        [],  # ready before
        [alert, make_bead("done", "Done thing")],  # open after
        [alert, dependent, blocker, make_bead("done", "Done thing")],  # all
        [],  # ready after
    ]
    monkeypatch.setattr(esa, "run_bead_list", FakeBeadList(payloads))

    summary = {
        "open_beads_before": "2",
        "open_beads_after": "2",
        "recovery_successful": "true",
        "timestamp": "2026-09-08T00:00:00Z",
    }
    monkeypatch.setattr(esa, "run_recovery_workflow", lambda *a, **k: summary)
    monkeypatch.setattr(
        esa,
        "run_diagnostics",
        lambda *a, **k: (
            {
                "metadata": {"overall_status": "HEALTHY", "timestamp": "t"},
                "recommendations": ["[MEDIUM] check publish.lock"],
            },
            "/tmp/report.json",
        ),
    )

    written = {}

    def fake_annotate(bead_id, note, bead_bin, workspace):
        written["note"] = note

    def fake_label(bead_id, label, bead_bin, workspace):
        written["label"] = (bead_id, label)

    monkeypatch.setattr(esa, "annotate_bead", fake_annotate)
    monkeypatch.setattr(esa, "label_bead", fake_label)

    records = esa.enrich(tmp_path, bead_bin="bead", log_file=str(tmp_path / "log"))
    assert len(records) == 1
    record = records[0]
    assert record["action"] == "enriched"
    assert record["bead_id"] == "alert-1"
    # "done" is open, unassigned and not ready with no blocker -> unexplained,
    # so the frontier is not legitimately blocked and recovery moved nothing.
    assert record["classification"] == esa.LABEL_UNRESOLVED
    assert written["label"] == ("alert-1", esa.LABEL_UNRESOLVED)
    assert "/tmp/report.json" in written["note"]
    assert "Overall status: HEALTHY" in written["note"]
    assert "[MEDIUM] check publish.lock" in written["note"]
    assert "recovery_successful: true" in written["note"]


def test_enrich_only_beads_filters_candidates(tmp_path, monkeypatch):
    alert_a = make_bead("alert-a", "Starvation alert: beads invisible in ws")
    alert_b = make_bead("alert-b", "Starvation alert: beads invisible in ws")
    payloads = [
        [alert_a, alert_b],  # open before
        [],  # ready before
    ]
    monkeypatch.setattr(esa, "run_bead_list", FakeBeadList(payloads))
    records = esa.enrich(
        tmp_path,
        bead_bin="bead",
        log_file=str(tmp_path / "log"),
        dry_run=True,
        only_beads=["alert-b"],
    )
    assert [r["bead_id"] for r in records] == ["alert-b"]
    assert all(r["action"] == "would-enrich" for r in records)


def test_enrich_reports_missing_explicit_bead(tmp_path, monkeypatch, capsys):
    payloads = [
        [make_bead("alert-a", "Starvation alert: beads invisible in ws")],
        [],  # ready before
    ]
    monkeypatch.setattr(esa, "run_bead_list", FakeBeadList(payloads))
    records = esa.enrich(
        tmp_path,
        bead_bin="bead",
        log_file=str(tmp_path / "log"),
        dry_run=True,
        only_beads=["alert-zz"],
    )
    assert records == []
    assert "alert-zz" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# diagnostics health gate (the false-positive evidence bar)
# ---------------------------------------------------------------------------


def healthy_report():
    """A diagnostics report whose three faking-a-starvation checks all pass."""
    return {
        "metadata": {"overall_status": "HEALTHY", "timestamp": "t"},
        "detailed_results": {
            "corruption_check": {"rehearse_executed": True, "corruption_detected": False},
            "database": {"assigned_but_open_beads": 0},
            "checkpoint": {"checkpoint_stale": False},
        },
    }


def test_diagnostics_report_healthy_when_all_three_checks_pass():
    assert esa.diagnostics_report_is_healthy(healthy_report()) is True


def test_diagnostics_report_unhealthy_when_any_check_fails_or_is_missing():
    def mutated(section, key, value):
        report = healthy_report()
        report["detailed_results"][section][key] = value
        return report

    no_rehearsal = mutated("corruption_check", "rehearse_executed", False)
    corruption = mutated("corruption_check", "corruption_detected", True)
    stuck = mutated("database", "assigned_but_open_beads", 4)
    stale = mutated("checkpoint", "checkpoint_stale", True)

    missing_count = healthy_report()
    del missing_count["detailed_results"]["database"]["assigned_but_open_beads"]

    for report in (None, {}, no_rehearsal, corruption, stuck, missing_count, stale):
        assert esa.diagnostics_report_is_healthy(report) is False, report


# ---------------------------------------------------------------------------
# false-positive classification
# ---------------------------------------------------------------------------


def quiescent_frontier():
    return {
        "total_open": 0,
        "human_blocked": [],
        "dependency_blocked": [],
        "other": [],
        "unexplained": 0,
        "all_explained": False,
        "ready": 0,
    }


def test_classify_false_positive_when_quiescent_and_healthy():
    label, reason = esa.classify_starvation(
        quiescent_frontier(), {"ready": 0}, None, healthy_report()
    )
    assert label == esa.LABEL_FALSE_POSITIVE
    assert reason == esa.FALSE_POSITIVE_REASON
    assert "workspace quiescent" in reason
    assert "0 open beads" in reason


def test_classify_quiescent_with_unhealthy_report_stays_unresolved():
    stale = healthy_report()
    stale["detailed_results"]["checkpoint"]["checkpoint_stale"] = True
    label, reason = esa.classify_starvation(quiescent_frontier(), {"ready": 0}, None, stale)
    assert label == esa.LABEL_UNRESOLVED
    assert "0 open bead" in reason


def test_classify_quiescent_without_report_stays_unresolved():
    label, _ = esa.classify_starvation(quiescent_frontier(), {"ready": 0}, None, None)
    assert label == esa.LABEL_UNRESOLVED


# ---------------------------------------------------------------------------
# close decision and close reason
# ---------------------------------------------------------------------------


def marker_note():
    return f"earlier text\n{esa.ENRICHMENT_MARKER}\n- Diagnostics report: /tmp/r.json"


def test_should_close_only_the_two_proven_classes():
    assert esa.should_close_bead(make_bead("a"), marker_note(), esa.LABEL_FALSE_POSITIVE) is True
    assert esa.should_close_bead(make_bead("a"), marker_note(), esa.LABEL_AUTO_RECOVERED) is True
    # Still needing judgment - never closed by automation.
    assert esa.should_close_bead(make_bead("a"), marker_note(), esa.LABEL_UNRESOLVED) is False
    assert (
        esa.should_close_bead(make_bead("a"), marker_note(), esa.LABEL_LEGITIMATELY_BLOCKED)
        is False
    )


def test_should_close_never_touches_in_progress_or_closed_beads():
    for status in ("in_progress", "closed"):
        assert (
            esa.should_close_bead(
                make_bead("a", status=status), marker_note(), esa.LABEL_FALSE_POSITIVE
            )
            is False
        )
        assert (
            esa.should_close_bead(
                make_bead("a", status=status), marker_note(), esa.LABEL_AUTO_RECOVERED
            )
            is False
        )


def test_should_close_requires_this_runs_note_to_have_landed():
    assert (
        esa.should_close_bead(make_bead("a"), "no marker here", esa.LABEL_FALSE_POSITIVE) is False
    )


def test_build_close_reason_false_positive_cites_verdict_and_report_path():
    reason = esa.build_close_reason(
        esa.LABEL_FALSE_POSITIVE, esa.FALSE_POSITIVE_REASON, "/tmp/report.json", None
    )
    assert reason.startswith("False positive:")
    assert esa.FALSE_POSITIVE_REASON in reason
    assert "/tmp/report.json" in reason


def test_build_close_reason_auto_recovered_cites_recovery_summary():
    summary = {
        "open_beads_before": "0",
        "open_beads_after": "8",
        "recovery_successful": "true",
        "timestamp": "2026-09-08T00:00:00Z",
    }
    reason = esa.build_close_reason(
        esa.LABEL_AUTO_RECOVERED, "ready frontier grew 0 -> 4", "/tmp/r.json", summary
    )
    assert reason.startswith("Auto-recovered:")
    assert "open_beads_before=0" in reason
    assert "open_beads_after=8" in reason
    assert "recovery_successful=true" in reason


def test_build_close_reason_auto_recovered_without_summary_stays_one_line():
    reason = esa.build_close_reason(
        esa.LABEL_AUTO_RECOVERED, "ready frontier grew 0 -> 4", "/tmp/r.json", None
    )
    assert reason == "Auto-recovered: ready frontier grew 0 -> 4"


# ---------------------------------------------------------------------------
# resolution: enrich() closing the proven classes
# ---------------------------------------------------------------------------


def _enqueue_enrich(monkeypatch, payloads, summary, report):
    """Stub the read/recovery/diagnostics legs of enrich() with fixed results."""
    monkeypatch.setattr(esa, "run_bead_list", FakeBeadList(payloads))
    monkeypatch.setattr(esa, "run_recovery_workflow", lambda *a, **k: summary)
    monkeypatch.setattr(esa, "run_diagnostics", lambda *a, **k: report)


def test_enrich_closes_quiescent_false_positive_with_report_path(tmp_path, monkeypatch):
    alert = make_bead("alert-fp", "[Unravel] Starvation alert: beads invisible in ws")
    payloads = [
        [alert],  # open before - discovery only sees open beads
        [],  # ready before
        [],  # open after - the queue emptied: quiescent
        [],  # all beads
        [],  # ready after
    ]
    _enqueue_enrich(monkeypatch, payloads, None, (healthy_report(), "/tmp/report.json"))

    calls = []
    monkeypatch.setattr(esa, "annotate_bead", lambda bead_id, *a: calls.append(("note", bead_id)))
    monkeypatch.setattr(
        esa, "label_bead", lambda bead_id, label, *a: calls.append(("label", bead_id, label))
    )
    monkeypatch.setattr(
        esa, "close_bead", lambda bead_id, reason, *a: calls.append(("close", bead_id, reason))
    )

    records = esa.enrich(tmp_path, bead_bin="bead", log_file=str(tmp_path / "log"))
    record = records[0]
    assert record["classification"] == esa.LABEL_FALSE_POSITIVE
    assert record["closed"] is True
    assert record["close_reason"] == calls[-1][2]
    closes = [c for c in calls if c[0] == "close"]
    assert len(closes) == 1
    assert closes[0][1] == "alert-fp"
    # The close reason carries the diagnostics verdict and the report JSON path.
    assert esa.FALSE_POSITIVE_REASON in closes[0][2]
    assert "/tmp/report.json" in closes[0][2]
    # The note and label landed before the close, keeping the action idempotent.
    assert calls[0] == ("note", "alert-fp")
    assert calls[1] == ("label", "alert-fp", esa.LABEL_FALSE_POSITIVE)


def test_enrich_closes_auto_recovered_with_recovery_summary(tmp_path, monkeypatch):
    alert = make_bead("alert-ar", "[Unravel] Starvation alert: beads invisible in ws")
    restored = make_bead("restored-1")
    payloads = [
        [alert],  # open before
        [],  # ready before
        [alert, restored],  # open after - visibility was restored
        [alert, restored],  # all beads
        [],  # ready after (unchanged; recovery shows in the open count)
    ]
    summary = {
        "open_beads_before": "0",
        "open_beads_after": "2",
        "recovery_successful": "true",
        "timestamp": "2026-09-08T00:00:00Z",
    }
    _enqueue_enrich(
        monkeypatch,
        payloads,
        summary,
        (healthy_report(), "/tmp/report-ar.json"),
    )

    closes = []
    monkeypatch.setattr(esa, "annotate_bead", lambda *a: None)
    monkeypatch.setattr(esa, "label_bead", lambda *a: None)
    monkeypatch.setattr(
        esa, "close_bead", lambda bead_id, reason, *a: closes.append((bead_id, reason))
    )

    records = esa.enrich(tmp_path, bead_bin="bead", log_file=str(tmp_path / "log"))
    record = records[0]
    assert record["classification"] == esa.LABEL_AUTO_RECOVERED
    assert record["closed"] is True
    assert closes == [("alert-ar", record["close_reason"])]
    # The close reason is the recovery outcome from the RECOVERY_SUMMARY block.
    assert "open_beads_before=0" in closes[0][1]
    assert "open_beads_after=2" in closes[0][1]
    assert "recovery_successful=true" in closes[0][1]


def test_enrich_leaves_unresolved_open(tmp_path, monkeypatch):
    alert = make_bead("alert-un", "[Unravel] Starvation alert: beads invisible in ws")
    stuck = make_bead("stuck-1")
    payloads = [
        [alert],  # open before
        [],  # ready before
        [alert, stuck],  # open after - recovery moved nothing
        [alert, stuck],  # all beads
        [],  # ready after
    ]
    summary = {"open_beads_before": "2", "open_beads_after": "2", "recovery_successful": "true"}

    def refuse(*args, **kwargs):
        raise AssertionError("unresolved alert bead must stay open")

    monkeypatch.setattr(esa, "close_bead", refuse)
    monkeypatch.setattr(esa, "annotate_bead", lambda *a: None)
    monkeypatch.setattr(esa, "label_bead", lambda *a: None)
    _enqueue_enrich(monkeypatch, payloads, summary, (healthy_report(), "/tmp/r.json"))

    records = esa.enrich(tmp_path, bead_bin="bead", log_file=str(tmp_path / "log"))
    assert records[0]["classification"] == esa.LABEL_UNRESOLVED
    assert records[0]["closed"] is False


def test_enrich_leaves_legitimately_blocked_open(tmp_path, monkeypatch):
    # The alert itself is open at enrichment time, so it counts in the frontier
    # too - every bead including the alert needs a stated reason to reach the
    # legitimately-blocked verdict.
    alert = make_bead(
        "alert-lb",
        "[Unravel] Starvation alert: beads invisible in ws",
        manual_blocked=True,
    )
    human = make_bead("human-1", manual_blocked=True)
    dependent = make_bead("dep-1", dependencies=[{"blocker": "blocker-1", "kind": "blocks"}])
    blocker = make_bead("blocker-1", status="open")
    payloads = [
        [alert],  # open before
        [],  # ready before
        [alert, human, dependent],  # open after - every bead has a stated reason
        [alert, human, dependent, blocker],  # all beads
        [],  # ready after
    ]

    def refuse(*args, **kwargs):
        raise AssertionError("legitimately-blocked alert bead must stay open")

    monkeypatch.setattr(esa, "close_bead", refuse)
    monkeypatch.setattr(esa, "annotate_bead", lambda *a: None)
    monkeypatch.setattr(esa, "label_bead", lambda *a: None)
    _enqueue_enrich(monkeypatch, payloads, None, (healthy_report(), "/tmp/r.json"))

    records = esa.enrich(tmp_path, bead_bin="bead", log_file=str(tmp_path / "log"))
    assert records[0]["classification"] == esa.LABEL_LEGITIMATELY_BLOCKED
    assert records[0]["closed"] is False


def test_enrich_degrades_to_label_and_notes_when_close_fails(tmp_path, monkeypatch, capsys):
    alert = make_bead("alert-fc", "[Unravel] Starvation alert: beads invisible in ws")
    payloads = [
        [alert],
        [],
        [],
        [],
        [],
    ]
    _enqueue_enrich(monkeypatch, payloads, None, (healthy_report(), "/tmp/report-fc.json"))

    calls = []
    monkeypatch.setattr(esa, "annotate_bead", lambda bead_id, *a: calls.append(("note", bead_id)))
    monkeypatch.setattr(
        esa, "label_bead", lambda bead_id, label, *a: calls.append(("label", bead_id, label))
    )

    def failing_close(bead_id, reason, *a, **k):
        raise subprocess.CalledProcessError(returncode=1, cmd="bead close")

    monkeypatch.setattr(esa, "close_bead", failing_close)

    records = esa.enrich(tmp_path, bead_bin="bead", log_file=str(tmp_path / "log"))
    record = records[0]
    # Label and notes landed; the close failed and was absorbed.
    assert calls == [("note", "alert-fc"), ("label", "alert-fc", esa.LABEL_FALSE_POSITIVE)]
    assert record["action"] == "enriched"
    assert record["closed"] is False
    assert "close_error" in record
    assert "WARN close failed" in capsys.readouterr().err


def test_main_exits_zero_when_a_close_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        esa,
        "enrich",
        lambda **kwargs: [
            {
                "bead_id": "alert-x",
                "action": "enriched",
                "classification": esa.LABEL_FALSE_POSITIVE,
                "closed": False,
                "close_error": "bead close exited 1",
            }
        ],
    )
    monkeypatch.setattr(sys, "argv", ["enrich_starvation_alerts.py", "--workspace", str(tmp_path)])
    assert esa.main() == 0


# ---------------------------------------------------------------------------
# annotate_bead appends instead of replacing (bead update --notes replaces)
# ---------------------------------------------------------------------------


class FakeBeadCLI:
    """Records subprocess calls; answers `bead show --json` from a bead dict."""

    def __init__(self, bead):
        self.bead = bead
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        result = subprocess.CompletedProcess(command, 0)
        if "show" in command:
            result.stdout = json.dumps([self.bead])
        else:
            result.stdout = ""
        result.stderr = ""
        return result


def test_annotate_bead_appends_to_existing_notes(monkeypatch):
    # `bead update --notes` replaces the whole field; an annotate that passed
    # only the enrichment note would erase the bead's investigation notes.
    bead = {"id": "alert-1", "notes": "prior investigation", "revision": 4}
    fake = FakeBeadCLI(bead)
    monkeypatch.setattr(esa.subprocess, "run", fake)
    esa.annotate_bead("alert-1", "the enrichment note", "bead", Path("/ws"))
    update = next(c for c in fake.calls if "update" in c)
    written = update[update.index("--notes") + 1]
    assert "prior investigation" in written
    assert "the enrichment note" in written
    assert written.index("prior investigation") < written.index("the enrichment note")


def test_annotate_bead_guards_the_read_modify_write_with_if_revision(monkeypatch):
    bead = {"id": "alert-1", "notes": "old", "revision": 7}
    fake = FakeBeadCLI(bead)
    monkeypatch.setattr(esa.subprocess, "run", fake)
    esa.annotate_bead("alert-1", "new", "bead", Path("/ws"))
    update = next(c for c in fake.calls if "update" in c)
    assert "--if-revision" in update
    assert update[update.index("--if-revision") + 1] == "7"


def test_annotate_bead_without_existing_notes_writes_just_the_note(monkeypatch):
    bead = {"id": "alert-1", "notes": "", "revision": 1}
    fake = FakeBeadCLI(bead)
    monkeypatch.setattr(esa.subprocess, "run", fake)
    esa.annotate_bead("alert-1", "the note", "bead", Path("/ws"))
    update = next(c for c in fake.calls if "update" in c)
    assert update[update.index("--notes") + 1] == "the note"


def test_read_bead_accepts_bare_dict_shape(monkeypatch):
    def raw(command, **kwargs):
        result = subprocess.CompletedProcess(command, 0)
        result.stdout = json.dumps({"id": "alert-1", "notes": "x", "revision": 2})
        result.stderr = ""
        return result

    monkeypatch.setattr(esa.subprocess, "run", raw)
    assert esa.read_bead("alert-1", "bead", Path("/ws"))["revision"] == 2


def test_read_bead_refuses_unrecognizable_output(monkeypatch):
    def raw(command, **kwargs):
        result = subprocess.CompletedProcess(command, 0)
        result.stdout = json.dumps([{"id": "someone-else"}])
        result.stderr = ""
        return result

    monkeypatch.setattr(esa.subprocess, "run", raw)
    with pytest.raises(RuntimeError, match="no recognizable bead"):
        esa.read_bead("alert-1", "bead", Path("/ws"))


def test_run_bead_list_requests_the_whole_queue(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = list(command)
        result = subprocess.CompletedProcess(command, 0)
        result.stdout = '{"id": "a"}\n'
        result.stderr = ""
        return result

    monkeypatch.setattr(esa.subprocess, "run", fake_run)
    beads = esa.run_bead_list(["--status", "open"], "bead", Path("/ws"))
    # Without --limit the CLI silently caps at 100 and blocker statuses past
    # the cap resolve as "unknown" (read: unclosed) in classify_frontier.
    assert seen["command"][seen["command"].index("--limit") + 1] == str(esa.BEAD_LIST_LIMIT)
    assert [b["id"] for b in beads] == ["a"]
