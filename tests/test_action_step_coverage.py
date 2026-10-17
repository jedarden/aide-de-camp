"""Contract tests for the action workflow's read steps and CI gates.

External systems are mocked so these tests exercise normalization and workflow
decisions without contacting a cluster, ArgoCD, Git, or the bead store.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.action import steps
from src.action.executor import ActionExecutor
from src.action.models import StepStatus
from src.action.registry import _validate_workflow_steps

pytestmark = pytest.mark.asyncio


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url, **_kwargs):
        self.urls.append(url)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def kwargs(project_cfg=None, project_slug="example"):
    return {
        "intent_id": "intent-123",
        "session_id": "session-123",
        "project_slug": project_slug,
        "project_cfg": project_cfg or {},
    }


async def test_all_documented_step_names_are_registered_and_accepted():
    names = [
        "deployment_info", "git_log", "argocd_apps", "open_beads",
        "ci_status", "pod_status", "image_tag",
    ]
    assert set(names) <= ActionExecutor()._step_executors.keys()
    assert _validate_workflow_steps("example", "status", names) == []


async def test_deployment_info_normalizes_kubernetes_json(monkeypatch):
    client = FakeClient(
        {"items": [{"metadata": {"name": "api"}, "spec": {"replicas": 3},
                    "status": {"readyReplicas": 2, "updatedReplicas": 3}}]},
        {"items": [{"metadata": {"name": "db"}, "spec": {"replicas": 1},
                    "status": {}}]},
    )
    monkeypatch.setattr(steps, "_get_cluster_proxy", lambda _cluster: "http://proxy")
    monkeypatch.setattr(steps.httpx, "AsyncClient", lambda **_kwargs: client)

    result = await steps.execute_deployment_info_step(**kwargs({"cluster": "c1", "namespace": "prod"}))

    assert result == {
        "deployments": [{"name": "api", "replicas": 3, "ready": 2, "updated": 3}],
        "statefulsets": [{"name": "db", "replicas": 1, "ready": 0}],
        "namespace": "prod", "cluster": "c1",
    }
    assert client.urls == [
        "http://proxy/apis/apps/v1/namespaces/prod/deployments",
        "http://proxy/apis/apps/v1/namespaces/prod/statefulsets",
    ]


async def test_deployment_info_requires_namespace_and_proxy(monkeypatch):
    with pytest.raises(ValueError, match="namespace"):
        await steps.execute_deployment_info_step(**kwargs({"cluster": "c1"}))
    monkeypatch.setattr(steps, "_get_cluster_proxy", lambda _cluster: None)
    with pytest.raises(ValueError, match="proxy"):
        await steps.execute_deployment_info_step(**kwargs({"cluster": "c1", "namespace": "prod"}))


async def test_git_log_returns_last_ten_commits_and_reports_failure(monkeypatch, tmp_path):
    repo_path = str(tmp_path)
    command = Mock(return_value=Mock(returncode=0, stdout="abc123 Add feature\ndef456 Fix bug\n", stderr=""))
    monkeypatch.setattr(steps.subprocess, "run", command)

    result = await steps.execute_git_log_step(**kwargs({"repo_path": repo_path}))

    assert result == {"commits": [
        {"hash": "abc123", "message": "Add feature"},
        {"hash": "def456", "message": "Fix bug"},
    ], "count": 2, "repo_path": repo_path}
    assert command.call_args.args[0] == ["git", "-C", repo_path, "log", "-10", "--oneline"]

    command.return_value = Mock(returncode=1, stdout="", stderr="bad repository")
    with pytest.raises(RuntimeError, match="bad repository"):
        await steps.execute_git_log_step(**kwargs({"repo_path": repo_path}))


async def test_git_log_rejects_invalid_commit_count(tmp_path):
    with pytest.raises(ValueError, match="commit_count"):
        await steps.execute_git_log_step(**kwargs({"repo_path": str(tmp_path), "commit_count": 0}))


async def test_argocd_apps_filters_and_normalizes_json(monkeypatch):
    client = FakeClient({"items": [
        {"metadata": {"name": "other", "namespace": "argocd"},
         "status": {"sync": {"status": "Synced"}, "health": {"status": "Healthy"}}},
        {"metadata": {"name": "example-app", "namespace": "argocd"},
         "status": {"sync": {"status": "OutOfSync"}, "health": {"status": "Degraded"},
                    "operationState": {"operation": {"sync": {"prune": False}}}}},
    ]})
    monkeypatch.setattr(steps, "_get_argocd_base_url", lambda: "https://argocd")
    monkeypatch.setattr(steps.httpx, "AsyncClient", lambda **_kwargs: client)

    result = await steps.execute_argocd_apps_step(**kwargs({"argocd_app": "example-app"}))

    assert result == {"applications": [{
        "name": "example-app", "namespace": "argocd", "sync_status": "OutOfSync",
        "health_status": "Degraded", "operation": {"sync": {"prune": False}},
    }], "cluster": None}
    assert client.urls == ["https://argocd/api/v1/applications"]


async def test_argocd_apps_reports_http_failure(monkeypatch):
    monkeypatch.setattr(steps, "_get_argocd_base_url", lambda: "https://argocd")
    monkeypatch.setattr(steps.httpx, "AsyncClient", lambda **_kwargs: FakeClient(httpx.ConnectError("offline")))
    with pytest.raises(RuntimeError, match="ArgoCD"):
        await steps.execute_argocd_apps_step(**kwargs())


async def test_argocd_base_url_is_resolved_relative_to_checkout(monkeypatch, tmp_path):
    steps_file = tmp_path / "src" / "action" / "steps" / "__init__.py"
    steps_file.parent.mkdir(parents=True)
    steps_file.touch()
    registry = tmp_path / "config" / "registry.yaml"
    registry.parent.mkdir()
    registry.write_text("argocd:\n  base_url: https://archive-argocd\n")
    monkeypatch.setattr(steps, "__file__", str(steps_file))

    assert steps._get_argocd_base_url() == "https://archive-argocd"


async def test_argocd_apps_uses_mapped_cluster_endpoint(monkeypatch):
    client = FakeClient({"items": []})
    monkeypatch.setattr("src.fetch.clusters.resolve_argocd_endpoint", lambda _cluster: SimpleNamespace(
        satisfiable=True, argocd_api="https://cluster-manager"))
    monkeypatch.setattr(steps.httpx, "AsyncClient", lambda **_kwargs: client)

    await steps.execute_argocd_apps_step(**kwargs({"cluster": "ardenone-cluster"}))

    assert client.urls == ["https://cluster-manager/api/v1/applications"]


async def test_argocd_apps_rejects_unmapped_or_unreadable_cluster():
    with pytest.raises(ValueError, match="no ArgoCD mapping"):
        await steps.execute_argocd_apps_step(**kwargs({"cluster": "unmapped-cluster"}))
    with pytest.raises(ValueError, match="authenticated|read-only|not satisfiable"):
        await steps.execute_argocd_apps_step(**kwargs({"cluster": "iad-kalshi"}))


async def test_open_beads_reads_bead_rs_jsonl(monkeypatch, tmp_path):
    repo_path = str(tmp_path)
    bead_dir = tmp_path / ".beads"
    bead_dir.mkdir()
    (bead_dir / "config.json").write_text("{}")
    stdout = '\n'.join((
        json.dumps({"id": "adc-1", "title": "One", "status": "open"}),
        json.dumps({"id": "adc-2", "title": "Two", "status": "open"}),
    )) + '\n'
    command = Mock(return_value=Mock(returncode=0, stdout=stdout, stderr=""))
    monkeypatch.setattr(steps.subprocess, "run", command)

    result = await steps.execute_open_beads_step(**kwargs({"repo_path": repo_path}))

    assert [item["id"] for item in result["open_beads"]] == ["adc-1", "adc-2"]
    assert result["count"] == 2
    assert result["repo_path"] == repo_path
    assert Path(command.call_args.args[0][0]).name == "bead"
    assert "bf" not in command.call_args.args[0]
    assert "--json" in command.call_args.args[0]
    assert command.call_args.kwargs["cwd"] == repo_path


async def test_open_beads_reports_invalid_output(monkeypatch, tmp_path):
    bead_dir = tmp_path / ".beads"
    bead_dir.mkdir()
    (bead_dir / "config.json").write_text("{}")
    monkeypatch.setattr(steps.subprocess, "run", Mock(return_value=Mock(
        returncode=0, stdout="not json\n", stderr="")))
    with pytest.raises(RuntimeError, match="JSON|parse|bead"):
        await steps.execute_open_beads_step(**kwargs({"repo_path": str(tmp_path)}))


async def test_ci_status_succeeds_only_for_latest_green_workflow(monkeypatch):
    monkeypatch.setattr(steps.Path, "exists", lambda _self: True)
    workflow = {"metadata": {"name": "build-2", "creationTimestamp": "2026-10-17T12:00:00Z"},
                "status": {"phase": "Succeeded"}}
    command = Mock(return_value=Mock(returncode=0, stdout=json.dumps({"items": [workflow]}), stderr=""))
    monkeypatch.setattr(steps.subprocess, "run", command)

    result = await steps.execute_ci_status_step(**kwargs({"cluster": "c1"}))

    assert result["status"] == "success"
    assert result["phase"] == "Succeeded"
    assert result["workflow_name"] == "build-2"
    assert "project=example" in command.call_args.args[0]


@pytest.mark.parametrize("phase", ["Failed", "Running", "Pending", "Error", "Unknown"])
async def test_ci_status_blocks_non_green_phase(monkeypatch, phase):
    monkeypatch.setattr(steps.Path, "exists", lambda _self: True)
    workflow = {"metadata": {"name": "build-2"}, "status": {"phase": phase}}
    monkeypatch.setattr(steps.subprocess, "run", Mock(return_value=Mock(
        returncode=0, stdout=json.dumps({"items": [workflow]}), stderr="")))
    with pytest.raises(RuntimeError, match="CI|workflow|phase"):
        await steps.execute_ci_status_step(**kwargs({"cluster": "c1"}))


@pytest.mark.parametrize("kubeconfig_exists,items", [(False, []), (True, [])])
async def test_ci_status_blocks_missing_evidence(monkeypatch, kubeconfig_exists, items):
    monkeypatch.setattr(steps.Path, "exists", lambda _self: kubeconfig_exists)
    monkeypatch.setattr(steps.subprocess, "run", Mock(return_value=Mock(
        returncode=0, stdout=json.dumps({"items": items}), stderr="")))
    with pytest.raises(RuntimeError, match="CI|workflow|kubeconfig"):
        await steps.execute_ci_status_step(**kwargs({"cluster": "c1"}))


async def test_pod_status_normalizes_json(monkeypatch):
    client = FakeClient({"items": [
        {"metadata": {"name": "pod-a"}, "status": {"phase": "Running",
            "containerStatuses": [{"ready": True}]}},
        {"metadata": {"name": "pod-b"}, "status": {"phase": "Pending",
            "containerStatuses": [{"ready": False}]}},
    ]})
    monkeypatch.setattr(steps, "_get_cluster_proxy", lambda _cluster: "http://proxy")
    monkeypatch.setattr(steps.httpx, "AsyncClient", lambda **_kwargs: client)

    result = await steps.execute_pod_status_step(**kwargs({"cluster": "c1", "namespace": "prod"}))

    assert result["total_pods"] == 2
    assert result["running"] == 1
    assert result["pending"] == 1
    assert result["failed"] == 0
    assert result["pod_names"] == ["pod-a", "pod-b"]
    assert client.urls == ["http://proxy/api/v1/namespaces/prod/pods"]


async def test_pod_status_verify_ready_blocks_unready_pods(monkeypatch):
    client = FakeClient({"items": [{"metadata": {"name": "pod-a"},
        "status": {"phase": "Running", "containerStatuses": [{"ready": False}]}}]})
    monkeypatch.setattr(steps, "_get_cluster_proxy", lambda _cluster: "http://proxy")
    monkeypatch.setattr(steps.httpx, "AsyncClient", lambda **_kwargs: client)

    with pytest.raises(RuntimeError, match="ready|pod"):
        await steps.execute_pod_status_step(
            **kwargs({"cluster": "c1", "namespace": "prod"}), verify_ready=True)


async def test_pod_status_verify_ready_blocks_empty_namespace(monkeypatch):
    monkeypatch.setattr(steps, "_get_cluster_proxy", lambda _cluster: "http://proxy")
    monkeypatch.setattr(steps.httpx, "AsyncClient", lambda **_kwargs: FakeClient({"items": []}))
    with pytest.raises(RuntimeError, match="ready|no pods"):
        await steps.execute_pod_status_step(
            **kwargs({"cluster": "c1", "namespace": "prod"}), verify_ready=True)


async def test_pod_status_verify_ready_checks_pod_ready_condition(monkeypatch):
    pod = {"metadata": {"name": "pod-a"}, "status": {
        "phase": "Running", "containerStatuses": [{"ready": True}],
        "conditions": [{"type": "Ready", "status": "False"}],
    }}
    monkeypatch.setattr(steps, "_get_cluster_proxy", lambda _cluster: "http://proxy")
    monkeypatch.setattr(steps.httpx, "AsyncClient", lambda **_kwargs: FakeClient({"items": [pod]}))

    with pytest.raises(RuntimeError, match="pod-a"):
        await steps.execute_pod_status_step(
            **kwargs({"cluster": "c1", "namespace": "prod"}), verify_ready=True)


async def test_image_tag_uses_ci_output_and_rejects_latest():
    ci_result = {"status": "success", "phase": "Succeeded", "image_tag": "v1.2.3",
                 "registry_path": "registry.example/app:v1.2.3"}
    result = await steps.execute_image_tag_step(**kwargs(), ci_status_result=ci_result)
    assert result["tag"] == "v1.2.3"
    assert result["registry_path"] == "registry.example/app:v1.2.3"

    with pytest.raises((RuntimeError, ValueError), match="latest"):
        await steps.execute_image_tag_step(**kwargs(), ci_status_result={
            **ci_result, "image_tag": "latest", "registry_path": "registry.example/app:latest"})


async def test_image_tag_requires_proven_ci_output():
    with pytest.raises((RuntimeError, ValueError), match="CI|image|tag"):
        await steps.execute_image_tag_step(**kwargs(), ci_status_result=None)


async def test_executor_passes_ci_evidence_to_image_step_and_halts_on_ci_failure(monkeypatch):
    config = {"cluster": "c1", "namespace": "prod", "workflows": {
        "deploy": {"steps": ["ci_status", "image_tag"]}}}
    monkeypatch.setattr("src.action.executor.get_project", lambda _slug: config)
    executor = ActionExecutor()
    for name in (
        "_broadcast_workflow_started", "_broadcast_workflow_progress", "_broadcast_step_started",
        "_broadcast_step_progress", "_broadcast_step_completed", "_broadcast_step_failed",
        "_broadcast_result",
    ):
        monkeypatch.setattr(executor, name, AsyncMock())

    ci_output = {"status": "success", "phase": "Succeeded", "image_tag": "v1.2.3",
                 "registry_path": "registry.example/app:v1.2.3"}
    with patch.object(steps, "execute_ci_status_step", new_callable=AsyncMock, return_value=ci_output) as ci, \
         patch.object(steps, "execute_image_tag_step", new_callable=AsyncMock,
                      return_value={"tag": "v1.2.3", "registry_path": ci_output["registry_path"]}) as image:
        result = await executor.execute_workflow("intent-123", "session-123", "deploy example", "example", "deploy")
        assert result.status == "completed"
        assert [step.status for step in result.steps] == [StepStatus.COMPLETED, StepStatus.COMPLETED]
        assert ci.await_count == image.await_count == 1
        assert image.await_args.kwargs["ci_status_result"] == ci_output

    with patch.object(steps, "execute_ci_status_step", new_callable=AsyncMock,
                      side_effect=RuntimeError("CI workflow failed")) as ci, \
         patch.object(steps, "execute_image_tag_step", new_callable=AsyncMock) as image:
        result = await executor.execute_workflow("intent-124", "session-123", "deploy example", "example", "deploy")
        assert result.status == "failed"
        assert result.steps[0].status == StepStatus.FAILED
        assert len(result.steps) == 1
        ci.assert_awaited_once()
        image.assert_not_awaited()


async def test_ci_workflow_output_parameters_reach_image_tag(monkeypatch, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("test")
    config = {
        "cluster": "c1", "namespace": "prod", "kubectl_config": str(kubeconfig),
        "workflows": {"deploy": {"steps": ["ci_status", "image_tag"]}},
    }
    workflow = {"metadata": {"name": "build-2"}, "status": {
        "phase": "Succeeded", "outputs": {"parameters": [
            {"name": "image_tag", "value": "v1.2.3"},
            {"name": "registry_path", "value": "registry.example/app:v1.2.3"},
        ]},
    }}
    monkeypatch.setattr("src.action.executor.get_project", lambda _slug: config)
    monkeypatch.setattr(steps.subprocess, "run", Mock(return_value=Mock(
        returncode=0, stdout=json.dumps({"items": [workflow]}), stderr="")))
    executor = ActionExecutor()
    for name in (
        "_broadcast_workflow_started", "_broadcast_workflow_progress", "_broadcast_step_started",
        "_broadcast_step_progress", "_broadcast_step_completed", "_broadcast_step_failed",
        "_broadcast_result",
    ):
        monkeypatch.setattr(executor, name, AsyncMock())

    result = await executor.execute_workflow(
        "intent-125", "session-123", "deploy example", "example", "deploy")

    assert result.status == "completed"
    assert [step.step_name for step in result.steps] == ["ci_status", "image_tag"]
    assert result.steps[0].output["image_tag"] == "v1.2.3"
    assert result.steps[1].output["tag"] == "v1.2.3"
    assert result.steps[1].output["registry_path"] == "registry.example/app:v1.2.3"
