"""Unit tests for scripts/enrich_underspecified_beads.py (bead aidedeca-be51beed).

Covers the pure decision logic (marker scan, discovery filters, kubectl request
parsing, candidate matching, resolve-vs-defer policy, note formatting) and the
guarded `bead update` path, using stub commands so no test touches the live
bead store or a real cluster.
"""

import importlib.util
import json
import stat
from pathlib import Path

import pytest


def subprocess_result(stdout="", stderr="", returncode=0):
    class Result:
        pass

    result = Result()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "enrich_underspecified_beads.py"
_spec = importlib.util.spec_from_file_location("enrich_underspecified_beads", _SCRIPT)
eub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eub)

# The exact shape that motivated the tool: an open bead asking for a kubectl
# mutation whose target was never named.
A1BA8617_DESCRIPTION = """```markdown
## Task
Execute a Kubernetes pod deletion using the `kubectl delete pod` command.

## Implementation Notes
**IMPORTANT:** The user did not specify which pod to delete. Before executing:
1. List available pods to determine the target (`kubectl get pods`).
2. Ask the user to specify the pod name and namespace if multiple candidates exist.
3. Execute `kubectl delete pod <pod_name> -n <namespace>` once the target is confirmed.
```
"""

A1BA8617_NOTES = """Task blocked by organizational policy and technical constraints:
No pod deletion was executed. Task requires clarification from the user on the
correct remediation path."""


def make_bead(bead_id, title="kubectl delete pod", **overrides):
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


def a1ba8617_like(bead_id="aidedeca-a1ba8617", **overrides):
    fields = {"description": A1BA8617_DESCRIPTION, "notes": A1BA8617_NOTES}
    fields.update(overrides)
    return make_bead(bead_id, **fields)


# ---------------------------------------------------------------------------
# marker scan
# ---------------------------------------------------------------------------


def test_marker_scan_hits_the_motivating_bead():
    assert eub.carries_awaiting_input_marker(a1ba8617_like()) is True


def test_marker_scan_matches_each_documented_marker():
    for marker in eub.AWAITING_INPUT_MARKERS:
        bead = make_bead("a", notes=f"some note\n{marker}\n")
        assert eub.carries_awaiting_input_marker(bead) is True, marker


def test_marker_scan_is_case_insensitive():
    bead = make_bead("a", notes="AWAITING USER INPUT on the pod name")
    assert eub.carries_awaiting_input_marker(bead) is True


def test_marker_scan_ignores_actionable_beads():
    bead = make_bead("a", description="Implement the retry helper in src/utilities/retry.py")
    assert eub.carries_awaiting_input_marker(bead) is False


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_find_underspecified_beads_selects_the_motivating_shape():
    beads = [
        a1ba8617_like(),
        make_bead("b", description="Implement X in src/y.py"),           # no marker
        make_bead("c", description=A1BA8617_DESCRIPTION, dependencies=[{"blocker": "z"}]),  # has deps
        make_bead("d", description=A1BA8617_DESCRIPTION, status="deferred"),  # not open
        make_bead("e", description=A1BA8617_DESCRIPTION, assignee="worker-1"),  # claimed
        make_bead("f", description=A1BA8617_DESCRIPTION, manual_blocked=True),  # human set aside
        make_bead("g", description=A1BA8617_DESCRIPTION, labels=["human"]),  # human label
        make_bead("h", description=A1BA8617_DESCRIPTION, status="in_progress"),  # being worked
    ]
    assert [b["id"] for b in eub.find_underspecified_beads(beads)] == ["aidedeca-a1ba8617"]


def test_find_underspecified_beads_skips_already_processed():
    processed = a1ba8617_like(
        "p", notes=A1BA8617_NOTES + "\n\n" + eub.format_deferred_note(None, [], [])
    )
    assert eub.find_underspecified_beads([processed]) == []
    annotated = a1ba8617_like("q", notes=f"{eub.ENRICHMENT_MARKER}\n- Resolved: ...")
    assert eub.find_underspecified_beads([annotated]) == []


def test_no_declared_deps_is_strict():
    # A bead whose blockers are all closed is already claimable; enrichment is
    # deliberately scoped to the dependency-free shape only.
    assert eub.has_no_declared_deps(make_bead("a")) is True
    assert eub.has_no_declared_deps(
        make_bead("b", dependencies=[{"blocker": "x", "kind": "blocks"}])
    ) is False


# ---------------------------------------------------------------------------
# request parsing
# ---------------------------------------------------------------------------


def test_parse_finds_unnamed_pod_target():
    request = eub.parse_kubectl_request(A1BA8617_DESCRIPTION)
    assert request is not None
    assert request.verb == "delete"
    assert request.kind == "pod"
    assert request.name is None
    assert request.underspecified is True


def test_parse_does_not_read_prose_as_the_resource_name():
    # The sentence after the fenced command must not become the target.
    request = eub.parse_kubectl_request(A1BA8617_DESCRIPTION)
    assert request is not None
    assert request.name not in ("once", "the", "target", "confirmed")


def test_parse_recognises_a_fully_named_request():
    request = eub.parse_kubectl_request(
        "Execute `kubectl delete pod web-7d9f8-xk2pz -n whisper-stt`"
    )
    assert request.kind == "pod"
    assert request.name == "web-7d9f8-xk2pz"
    assert request.named_namespaces == ["whisper-stt"]
    assert request.underspecified is False


def test_parse_namespace_placeholder_is_missing_not_literal():
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name> -n <namespace>`")
    assert request.name is None
    assert request.named_namespaces == []


def test_parse_bare_line_form():
    request = eub.parse_kubectl_request("kubectl delete pod\n")
    assert request is not None
    assert request.verb == "delete"
    assert request.kind == "pod"
    assert request.name is None


def test_parse_kind_only_believed_when_it_is_a_known_alias():
    # "whisper-stt" is a namespace, not a resource kind; trusting it would
    # mislabel the request as an unsupported kind.
    request = eub.parse_kubectl_request("delete the whisper-stt pod")
    assert request is None or request.kind in (None, "pod")


def test_parse_inline_kind_name_form():
    request = eub.parse_kubectl_request("run `kubectl delete pod/web-1`")
    assert request.kind == "pod"
    assert request.name == "web-1"
    assert request.underspecified is False


def test_parse_returns_none_for_non_kubectl_text():
    assert eub.parse_kubectl_request("Implement the fetch orchestrator") is None
    assert eub.parse_kubectl_request("helm upgrade the release") is None


def test_describe_renders_the_missing_target():
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name> -n <namespace>`")
    assert "<no resource name given>" in request.describe()
    assert "kubectl delete pod" in request.describe()


# ---------------------------------------------------------------------------
# context extraction
# ---------------------------------------------------------------------------


def test_distinctive_tokens_drop_stopwords():
    tokens = eub.distinctive_tokens(
        "Delete the stuck pod in the whisper-stt namespace, please. kubectl delete pod"
    )
    # "stuck" survives on purpose: it is exactly the kind of word that singles a
    # pod out ("...-stuck-restart"), unlike the pure grammar words below.
    assert "stuck" in tokens
    assert "whisper-stt" in tokens
    for stopword in ("delete", "pod", "namespace", "kubectl", "please"):
        assert stopword not in tokens


def test_mentioned_clusters_only_known_names():
    text = "the stuck pod on ardenone-cluster and maybe iad-kalshi, not on frobnicator"
    assert eub.mentioned_clusters(text) == ["ardenone-cluster", "iad-kalshi"]


def test_cluster_proxies_covers_every_documented_cluster():
    proxies = eub.cluster_proxies()
    for cluster in (
        "ardenone-cluster", "ardenone-manager", "rs-manager", "iad-ci",
        "iad-options", "ord-devimprint", "apexalgo-iad", "iad-kalshi",
    ):
        assert cluster in proxies
    assert proxies["iad-kalshi"].endswith("kubectl-proxy-iad-kalshi:8001")


def test_cluster_proxies_honours_restriction(monkeypatch):
    monkeypatch.delenv("ADC_KUBECTL_PROXIES", raising=False)
    proxies = eub.cluster_proxies(["iad-ci"])
    assert list(proxies) == ["iad-ci"]


def test_cluster_proxies_ignores_bad_override(monkeypatch, capsys):
    monkeypatch.setenv("ADC_KUBECTL_PROXIES", "{not json")
    proxies = eub.cluster_proxies()
    assert "ardenone-cluster" in proxies  # the fleet map survives
    assert "not valid JSON" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# candidate matching
# ---------------------------------------------------------------------------


def pod(name, namespace, labels=None, owners=None, images=None):
    metadata = {"name": name, "namespace": namespace}
    if labels:
        metadata["labels"] = labels
    if owners:
        metadata["ownerReferences"] = [{"name": owner} for owner in owners]
    spec = {"containers": [{"image": image} for image in (images or [])]}
    return {"metadata": metadata, "spec": spec}


def test_match_pods_namespace_named_in_bead():
    pods = [pod("a-1", "whisper-stt"), pod("b-1", "kube-system")]
    got = eub.match_pods([], ["whisper-stt"], "ardenone-cluster", pods)
    assert [(c.namespace, c.name) for c in got] == [("whisper-stt", "a-1")]


def test_match_pods_by_distinctive_token():
    pods = [pod("pluck-7d9f8-xk2pz", "aide-de-camp"), pod("unrelated-1", "default")]
    got = eub.match_pods(["pluck"], [], "ardenone-cluster", pods)
    assert [(c.namespace, c.name) for c in got] == [("aide-de-camp", "pluck-7d9f8-xk2pz")]


def test_match_pods_token_hits_labels_and_images_too():
    pods = [
        pod("arbitrary-name", "default", labels={"app": "kalshi-tape"}),
        pod("other", "default", images=["ronaldraygun/whisper-stt:1.2.3"]),
    ]
    got = eub.match_pods(["kalshi-tape", "whisper-stt"], [], "iad-ci", pods)
    assert {c.name for c in got} == {"arbitrary-name", "other"}


def test_match_pods_generic_words_match_nothing():
    pods = [pod("web-1", "default"), pod("web-2", "kube-system")]
    got = eub.match_pods(eub.distinctive_tokens("delete the pod in the namespace"), [], "iad-ci", pods)
    assert got == []


def test_match_pods_namespace_reason_names_the_evidence():
    got = eub.match_pods([], ["whisper-stt"], "ardenone-cluster", [pod("a-1", "whisper-stt")])
    assert 'namespace "whisper-stt" named in the bead' in got[0].reason


def test_candidate_identity_is_cluster_scoped():
    first = eub.Candidate("ardenone-cluster", "ns", "p", "r1")
    second = eub.Candidate("iad-ci", "ns", "p", "r2")
    assert first != second
    assert eub.Candidate("c", "ns", "p", "r1") == eub.Candidate("c", "ns", "p", "r9")


def test_gather_candidates_dedupes_and_reports_unreachable(monkeypatch, tmp_path):
    pods = [pod("pluck-1", "aide-de-camp"), pod("pluck-2", "aide-de-camp")]
    monkeypatch.setattr(
        eub,
        "fetch_pods",
        lambda cluster, server, timeout=8: (
            (pods, None) if cluster == "ardenone-cluster" else (None, "connection refused")
        ),
    )
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name>`")
    candidates, unreachable = eub.gather_candidates(
        request,
        "delete the stuck pluck pod",
        "",
        tmp_path,
        {"ardenone-cluster": "http://x:8001", "iad-ci": "http://y:8001"},
    )
    assert [(c.namespace, c.name) for c in candidates] == [
        ("aide-de-camp", "pluck-1"),
        ("aide-de-camp", "pluck-2"),
    ]
    assert unreachable == ["iad-ci"]


def test_gather_candidates_corroborates_notes_against_live_pods(monkeypatch, tmp_path):
    pods = [pod("web-7d9f8-xk2pz", "whisper-stt")]
    monkeypatch.setattr(eub, "fetch_pods", lambda cluster, server, timeout=8: (pods, None))
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name> -n <namespace>`")
    candidates, unreachable = eub.gather_candidates(
        request,
        "delete the pod",
        "later note: the pod is pods/web-7d9f8-xk2pz in namespace whisper-stt",
        tmp_path,
        {"ardenone-cluster": "http://x:8001"},
    )
    assert unreachable == []
    assert [(c.namespace, c.name) for c in candidates] == [("whisper-stt", "web-7d9f8-xk2pz")]


def test_notes_candidates_ignore_placeholders():
    pairs = eub.notes_candidates(None, "run pods/<pod_name> with -n <namespace>")
    assert pairs == []


def test_fetch_pods_is_read_only_and_reports_failure(monkeypatch):
    recorded = {}

    def fake_run(argv, capture_output, text, timeout):
        recorded["argv"] = argv
        class Result:
            returncode = 0
            stdout = '{"items": []}'
            stderr = ""
        return Result()

    monkeypatch.setattr(eub.subprocess, "run", fake_run)
    pods, error = eub.fetch_pods("ardenone-cluster", "http://x:8001")
    assert pods == []
    assert error is None
    # The only cluster command this tool may ever issue.
    assert recorded["argv"][:2] == ["kubectl", "--server=http://x:8001"]
    assert recorded["argv"][2:] == ["get", "pods", "-A", "-o", "json"]


def test_fetch_pods_reports_nonzero_exit(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "Unable to connect to the server"
        return Result()

    monkeypatch.setattr(eub.subprocess, "run", fake_run)
    pods, error = eub.fetch_pods("ardenone-cluster", "http://x:8001")
    assert pods is None
    assert "Unable to connect" in error


# ---------------------------------------------------------------------------
# decision policy
# ---------------------------------------------------------------------------


def test_decide_defers_when_nothing_matches():
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name>`")
    assert eub.decide(request, []) == eub.ACTION_DEFER


def test_decide_resolves_exactly_one_candidate():
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name>`")
    one = [eub.Candidate("ardenone-cluster", "whisper-stt", "web-1", "namespace match")]
    assert eub.decide(request, one) == eub.ACTION_RESOLVE


def test_decide_defers_several_candidates():
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name>`")
    many = [
        eub.Candidate("ardenone-cluster", "ns", "a", "r"),
        eub.Candidate("ardenone-cluster", "ns", "b", "r"),
    ]
    assert eub.decide(request, many) == eub.ACTION_DEFER


def test_decide_leaves_unparseable_beads_alone():
    assert eub.decide(None, []) == eub.ACTION_NO_REQUEST_SHAPE


def test_decide_leaves_unsupported_kinds_alone():
    request = eub.parse_kubectl_request("run `kubectl scale deployment <name>`")
    assert eub.decide(request, []) == eub.ACTION_UNSUPPORTED_KIND


def test_decide_leaves_already_specific_beads_alone():
    request = eub.parse_kubectl_request("run `kubectl delete pod web-1 -n whisper-stt`")
    assert eub.decide(request, []) == eub.ACTION_ALREADY_SPECIFIC


# ---------------------------------------------------------------------------
# note formatting
# ---------------------------------------------------------------------------


def test_deferred_note_opens_with_the_documented_sentence():
    note = eub.format_deferred_note(
        eub.parse_kubectl_request("run `kubectl delete pod <pod_name>`"), [], []
    )
    assert note.startswith("underspecified: 0 candidates, needs disambiguation")


def test_deferred_note_counts_and_caps_candidates():
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name>`")
    many = [
        eub.Candidate("ardenone-cluster", "ns", f"pod-{i}", "r") for i in range(14)
    ]
    note = eub.format_deferred_note(request, many, [])
    assert "underspecified: 14 candidates, needs disambiguation" in note
    assert "pod-9" in note
    assert "pod-10" not in note
    assert "… and 4 more" in note


def test_deferred_note_explains_an_empty_match():
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name>`")
    note = eub.format_deferred_note(request, [], [])
    assert "could not be resolved deterministically" in note


def test_resolved_note_carries_candidate_and_scope_boundary():
    request = eub.parse_kubectl_request("run `kubectl delete pod <pod_name>`")
    note = eub.format_resolved_note(
        request,
        [eub.Candidate("ardenone-cluster", "whisper-stt", "web-1", 'namespace "whisper-stt" named in the bead')],
        [],
        ["src/fetch/commands.py: a1b2c3d fix: something"],
    )
    assert eub.ENRICHMENT_MARKER in note
    assert "- candidate: pod/web-1 namespace=whisper-stt cluster=ardenone-cluster" in note
    assert "get pods -A -o json (read-only)" in note
    assert "src/fetch/commands.py: a1b2c3d fix: something" in note
    assert "declarative-config edit" in note


def test_notes_flag_unreachable_clusters():
    lines = eub.format_caveats(["iad-ci", "rs-manager"])
    assert len(lines) == 1
    assert "iad-ci, rs-manager" in lines[0]
    assert eub.format_caveats([]) == []


def test_append_notes_preserves_existing_text():
    assert eub.append_notes("", "NEW") == "NEW"
    assert eub.append_notes("old note", "NEW") == "old note\n\nNEW"


# ---------------------------------------------------------------------------
# git evidence
# ---------------------------------------------------------------------------


def test_git_evidence_reads_only_files_that_exist(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "retry.py").write_text("x = 1\n")
    requested_paths = []
    git_calls = []

    def fake_run(argv, capture_output, text, timeout):
        git_calls.append(list(argv))
        if argv[0] == "git":
            requested_paths.append(argv[-1])
            return subprocess_result(stdout="a1b2c3 fix: retry\n")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(eub.subprocess, "run", fake_run)
    evidence = eub.git_evidence(
        "fix the retry logic in src/retry.py and also missing/ghost.py", tmp_path
    )
    # Only the file that exists on disk is probed; the ghost path never reaches git.
    assert requested_paths == ["src/retry.py"]
    assert evidence == ["src/retry.py: a1b2c3 fix: retry"]


# ---------------------------------------------------------------------------
# guarded bead update (stub CLI — no live bead store)
# ---------------------------------------------------------------------------


def _write_stub(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_update_bead_appends_and_guards_revision(tmp_path):
    bead_bin = tmp_path / "bead"
    _write_stub(
        bead_bin,
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        f"with open({str(tmp_path / 'calls.jsonl')!r}, 'a') as h:\n"
        "    h.write(json.dumps(args) + '\\n')\n",
    )

    eub.update_bead(
        {"id": "aidedeca-x", "notes": "earlier", "revision": 7},
        str(bead_bin),
        tmp_path,
        "NEW BLOCK",
    )
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert calls == [["update", "aidedeca-x", "--if-revision", "7", "--notes", "earlier\n\nNEW BLOCK"]]


def test_update_bead_carries_the_status_transition(tmp_path):
    bead_bin = tmp_path / "bead"
    _write_stub(
        bead_bin,
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        f"with open({str(tmp_path / 'calls.jsonl')!r}, 'a') as h:\n"
        "    h.write(json.dumps(args) + '\\n')\n",
    )
    eub.update_bead(
        {"id": "aidedeca-x", "notes": "", "revision": 2},
        str(bead_bin),
        tmp_path,
        "underspecified: 0 candidates, needs disambiguation",
        status="deferred",
    )
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert calls == [
        [
            "update",
            "aidedeca-x",
            "--if-revision",
            "2",
            "--status",
            "deferred",
            "--notes",
            "underspecified: 0 candidates, needs disambiguation",
        ]
    ]


def test_update_bead_surfaces_conflict_without_retrying(tmp_path):
    bead_bin = tmp_path / "bead"
    _write_stub(
        bead_bin,
        "#!/usr/bin/env python3\n"
        "import sys\nprint('revision conflict', file=sys.stderr)\nsys.exit(4)\n",
    )
    with pytest.raises(RuntimeError, match="rc=4"):
        eub.update_bead(
            {"id": "aidedeca-x", "notes": "", "revision": 2}, str(bead_bin), tmp_path, "n"
        )


def test_enrich_bead_resolves_one_candidate(tmp_path):
    bead = make_bead(
        "aidedeca-one",
        description="The pod is blocked awaiting user input. Run `kubectl delete pod <pod_name> -n <namespace>` in whisper-stt.",
        notes="requires clarification from the user",
    )
    written = {}

    def fake_update(target, bead_bin, workspace, note, status=None):
        written["note"] = note
        written["status"] = status

    original_update = eub.update_bead
    original_fetch = eub.fetch_pods
    eub.update_bead = fake_update  # type: ignore[assignment]
    eub.fetch_pods = lambda cluster, server, timeout=8: (  # type: ignore[assignment]
        [pod("web-7d9f8-xk2pz", "whisper-stt")],
        None,
    )
    try:
        record = eub.enrich_bead(bead, tmp_path, "bead", {"ardenone-cluster": "http://x:8001"})
    finally:
        eub.update_bead = original_update  # type: ignore[assignment]
        eub.fetch_pods = original_fetch  # type: ignore[assignment]
    assert record["action"] == eub.ACTION_RESOLVE
    assert written["status"] is None  # stays open, now claimable
    assert eub.ENRICHMENT_MARKER in written["note"]
    assert "pod/web-7d9f8-xk2pz" in written["note"]
    assert "cluster=ardenone-cluster" in written["note"]


def test_enrich_bead_defers_zero_candidates(tmp_path):
    bead = a1ba8617_like("aidedeca-zero")
    written = {}

    def fake_update(target, bead_bin, workspace, note, status=None):
        written["note"] = note
        written["status"] = status

    original_update = eub.update_bead
    eub.update_bead = fake_update  # type: ignore[assignment]
    original_fetch = eub.fetch_pods
    eub.fetch_pods = lambda cluster, server, timeout=8: ([], None)  # type: ignore[assignment]
    try:
        record = eub.enrich_bead(bead, tmp_path, "bead", {"ardenone-cluster": "http://x:8001"})
    finally:
        eub.update_bead = original_update  # type: ignore[assignment]
        eub.fetch_pods = original_fetch  # type: ignore[assignment]
    assert record["action"] == eub.ACTION_DEFER
    assert written["status"] == "deferred"
    assert written["note"].startswith("underspecified: 0 candidates, needs disambiguation")


def test_enrich_bead_reports_failure_without_raising(tmp_path):
    bead = a1ba8617_like("aidedeca-err")

    def boom(*args, **kwargs):
        raise RuntimeError("bead update failed (rc=4): revision conflict")

    original_update = eub.update_bead
    eub.update_bead = boom  # type: ignore[assignment]
    try:
        record = eub.enrich_bead(
            bead,
            tmp_path,
            "bead",
            {"ardenone-cluster": "http://x:8001"},
        )
    finally:
        eub.update_bead = original_update  # type: ignore[assignment]
    assert record["action"] == "failed"
    assert "rc=4" in record["error"]


def test_enrich_bead_dry_run_mutates_nothing(tmp_path):
    bead = a1ba8617_like("aidedeca-dry")
    original_update = eub.update_bead

    def must_not_run(*args, **kwargs):
        raise AssertionError("dry run issued a bead update")

    eub.update_bead = must_not_run  # type: ignore[assignment]
    try:
        record = eub.enrich_bead(
            bead,
            tmp_path,
            "bead",
            {"ardenone-cluster": "http://x:8001"},
            dry_run=True,
        )
    finally:
        eub.update_bead = original_update  # type: ignore[assignment]
    assert record["action"].startswith("would-")


# ---------------------------------------------------------------------------
# enrich() end to end against stubs
# ---------------------------------------------------------------------------


def test_enrich_skips_kubectl_entirely_on_a_quiet_workspace(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        eub, "run_bead_list", lambda args, bead_bin, workspace, timeout=60: calls.append(args) or []
    )
    records = eub.enrich(tmp_path, "bead")
    assert records == []
    assert calls == [["--status", "open"]]


def test_run_bead_list_overrides_the_silent_100_cap(monkeypatch, tmp_path):
    # bead list silently caps output at its default --limit of 100; the
    # enricher must fetch the whole open set, or a qualifying bead sitting
    # past the cap starves on — invisible to this tool exactly as it was to
    # pluck. (enrich_starvation_alerts.py and unblock_credential_gated_beads.py
    # carry the same guard.)
    recorded = {}

    def fake_run(argv, capture_output, text, timeout, cwd=None):
        recorded["argv"] = list(argv)
        return subprocess_result(stdout="[]")

    monkeypatch.setattr(eub.subprocess, "run", fake_run)
    assert eub.run_bead_list(["--status", "open"], "bead", tmp_path) == []
    assert eub.BEAD_LIST_LIMIT > 100
    assert recorded["argv"] == [
        "bead", "list", "--status", "open", "--json",
        "--limit", str(eub.BEAD_LIST_LIMIT),
    ]


def test_enrich_processes_only_qualifying_beads(tmp_path, monkeypatch):
    beads = [
        a1ba8617_like("aidedeca-hit"),
        make_bead("aidedeca-miss", description="Implement X in src/y.py"),
    ]

    def fake_list(args, bead_bin, workspace, timeout=60):
        return beads

    monkeypatch.setattr(eub, "run_bead_list", fake_list)
    processed = []

    def spy(bead, *args, **kwargs):
        processed.append(bead["id"])
        return {"bead_id": bead["id"], "action": "would-defer"}

    monkeypatch.setattr(eub, "enrich_bead", spy)
    records = eub.enrich(tmp_path, "bead")
    assert processed == ["aidedeca-hit"]
    assert [r["bead_id"] for r in records] == ["aidedeca-hit"]


def test_enrich_restricts_to_requested_bead_ids(tmp_path, monkeypatch, capsys):
    beads = [
        a1ba8617_like("aidedeca-hit"),
        a1ba8617_like("aidedeca-other"),
        make_bead("aidedeca-notqualifying", description="Implement X in src/y.py"),
    ]
    monkeypatch.setattr(eub, "run_bead_list", lambda args, b, w, timeout=60: beads)
    monkeypatch.setattr(
        eub, "enrich_bead", lambda bead, *a, **k: {"bead_id": bead["id"], "action": "would-defer"}
    )
    records = eub.enrich(tmp_path, "bead", only_beads=["aidedeca-hit", "aidedeca-notqualifying"])
    assert [r["bead_id"] for r in records] == ["aidedeca-hit"]
    assert "SKIP aidedeca-notqualifying" in capsys.readouterr().err
