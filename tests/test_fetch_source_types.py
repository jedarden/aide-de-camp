"""
Fetch source-type executor unit tests (bead adc-1mzt).

Where tests/test_fetch_strand.py (bead adc-mwrx) stubs *every* source executor
to test dispatch/parallelism/coverage, this suite exercises the **real executor
implementations** in src/fetch/orchestrator.py against a mocked HTTP layer —
proving that each fetch source type (kubectl API, ArgoCD API, pod logs, events)
parses its real response shape into the structured dict synthesize consumes.

httpx is faked, so no kubectl proxy, ArgoCD endpoint, or live cluster is hit.
No subprocess or filesystem source is touched here (those are covered by the
local-repo integration test at the end).

What this suite locks down (the "various fetch source types execute correctly"
contract):

1. **HTTP source types parse real payloads** — kubectl_pods, kubectl_deployments,
   kubectl_workflows, argocd_app, logs, and events each turn a realistic API
   response into the field set the component library expects.
2. **Missing-argument guards** — every executor returns a structured error dict
   (and makes no HTTP call) when its required context fields are absent, rather
   than raising.
3. **HTTP error handling** — 404s and empty-result envelopes become error dicts,
   not exceptions (synthesize surfaces caveats, never crashes).
4. **End-to-end strand wiring** — a real FetchStrand.fetch() over a STATUS
   utterance, with httpx mocked and local sources stubbed, yields parsed data
   for each HTTP source — i.e. the strand correctly maps source types to
   executors to structured results.
"""

from unittest.mock import MagicMock

import httpx
import pytest

from src.fetch import orchestrator
from src.fetch.commands import FetchContext, FetchRequest, FetchSource, IntentType
from src.fetch.orchestrator import FetchStrand

# --- httpx fakes -----------------------------------------------------------


class FakeResponse:
    """Stand-in for httpx.Response — serves canned JSON/text + status."""

    def __init__(self, json_data=None, text="", status_code=200):
        self._json_data = json_data
        self.text = text if text else ""
        self.status_code = status_code

    def json(self):
        if self._json_data is None:
            raise ValueError("response has no JSON body")
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=MagicMock(),
                response=self,
            )


class FakeAsyncClient:
    """async-with fake for httpx.AsyncClient. Routes GETs via `responder`."""

    def __init__(self, responder):
        # responder: either a FakeResponse, or a callable(url, params) -> FakeResponse
        self._responder = responder
        self.requests: list[tuple[str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        self.requests.append((url, params))
        if callable(self._responder):
            return self._responder(url, params)
        return self._responder


@pytest.fixture
def mock_httpx(monkeypatch):
    """
    Patch httpx.AsyncClient in the orchestrator module so the next executor
    that constructs one gets `responder`. Returns the installed client so tests
    can assert on which URLs/params were hit.
    """

    def install(responder) -> FakeAsyncClient:
        client = FakeAsyncClient(responder)
        # Executors construct via `httpx.AsyncClient(timeout=..., verify=...)`;
        # ignore those kwargs and hand back our instrumented client.
        monkeypatch.setattr(orchestrator.httpx, "AsyncClient", lambda *a, **kw: client)
        return client

    return install


def _ctx(**kwargs) -> FetchContext:
    """FetchContext with sane kubectl-proxy defaults + per-test overrides."""
    defaults = {
        "proxy": "http://traefik-test:8001",
        "namespace": "myns",
        "project_slug": "my-proj",
    }
    defaults.update(kwargs)
    return FetchContext(**defaults)


# --- 1. HTTP source types parse real payloads -----------------------------


class TestKubectlPods:
    """_fetch_kubectl_pods parses a PodList into per-pod + summary fields."""

    @pytest.mark.asyncio
    async def test_parses_pod_list_with_counts(self, mock_httpx):
        pods_list = {
            "items": [
                {
                    "metadata": {"name": "web-0"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [{"ready": True, "restartCount": 0}],
                    },
                },
                {
                    "metadata": {"name": "worker-1"},
                    "status": {
                        "phase": "Pending",
                        "containerStatuses": [{"ready": False, "restartCount": 3}],
                    },
                },
            ]
        }
        client = mock_httpx(FakeResponse(json_data=pods_list))
        strand = FetchStrand()
        data = await strand._fetch_kubectl_pods(_ctx())

        assert data["namespace"] == "myns"
        assert data["pod_count"] == 2
        assert data["healthy_count"] == 1  # only web-0 is Running
        assert data["pods"][0]["name"] == "web-0"
        assert data["pods"][0]["phase"] == "Running"
        assert data["pods"][0]["ready"] == "1/1"
        assert data["pods"][1]["restarts"] == 3
        # The right URL was hit.
        assert client.requests
        assert "namespaces/myns/pods" in client.requests[0][0]

    @pytest.mark.asyncio
    async def test_namespace_derived_from_project_slug(self, mock_httpx):
        """No namespace → derived from project_slug by stripping dashes."""
        client = mock_httpx(FakeResponse(json_data={"items": []}))
        strand = FetchStrand()
        await strand._fetch_kubectl_pods(_ctx(namespace=None, project_slug="my-cool-proj"))
        # Derived namespace appears in the requested URL.
        assert "namespaces/mycoolproj/pods" in client.requests[0][0]

    @pytest.mark.asyncio
    async def test_404_returns_namespace_not_found(self, mock_httpx):
        mock_httpx(FakeResponse(status_code=404))
        strand = FetchStrand()
        data = await strand._fetch_kubectl_pods(_ctx())
        assert data["error"] == "Namespace not found"
        assert data["pods"] == []

    @pytest.mark.asyncio
    async def test_missing_namespace_and_project_returns_error_without_call(self, mock_httpx):
        client = mock_httpx(FakeResponse(json_data={}))
        strand = FetchStrand()
        data = await strand._fetch_kubectl_pods(_ctx(namespace=None, project_slug=None))
        assert data["error"] == "No namespace specified"
        assert client.requests == []  # no HTTP call made


class TestKubectlDeployments:
    """_fetch_kubectl_deployments parses a Deployment's status/spec."""

    @pytest.mark.asyncio
    async def test_parses_deployment_replica_state(self, mock_httpx):
        deploy = {
            "spec": {"replicas": 3},
            "status": {
                "readyReplicas": 2,
                "availableReplicas": 2,
                "updatedReplicas": 3,
                "conditions": [{"type": "Available", "status": "True"}],
            },
        }
        mock_httpx(FakeResponse(json_data=deploy))
        strand = FetchStrand()
        data = await strand._fetch_kubectl_deployments(_ctx(deployment="web"))

        assert data["name"] == "web"
        assert data["replicas"] == 3
        assert data["ready_replicas"] == 2
        assert data["available_replicas"] == 2
        assert data["updated_replicas"] == 3
        assert len(data["conditions"]) == 1

    @pytest.mark.asyncio
    async def test_app_name_falls_back_when_no_deployment(self, mock_httpx):
        mock_httpx(FakeResponse(json_data={"spec": {}, "status": {}}))
        client = mock_httpx(FakeResponse(json_data={"spec": {}, "status": {}}))
        strand = FetchStrand()
        await strand._fetch_kubectl_deployments(_ctx(deployment=None, app_name="web-svc"))
        assert "deployments/web-svc" in client.requests[0][0]

    @pytest.mark.asyncio
    async def test_missing_namespace_returns_error(self, mock_httpx):
        client = mock_httpx(FakeResponse(json_data={}))
        strand = FetchStrand()
        data = await strand._fetch_kubectl_deployments(
            _ctx(namespace=None, deployment=None, app_name=None)
        )
        assert "error" in data
        assert client.requests == []

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, mock_httpx):
        mock_httpx(FakeResponse(status_code=404))
        strand = FetchStrand()
        data = await strand._fetch_kubectl_deployments(_ctx(deployment="web"))
        assert "not found" in data["error"].lower()


class TestKubectlWorkflows:
    """_fetch_kubectl_workflows parses Argo Workflow runs, newest-first, top-10."""

    @pytest.mark.asyncio
    async def test_sorts_by_started_at_desc_and_caps_at_ten(self, mock_httpx):
        items = []
        for i in range(12):
            items.append(
                {
                    "metadata": {"name": f"wf-{i:02d}"},
                    "status": {"phase": "Succeeded", "startedAt": f"2026-01-{i + 1:02d}T00:00:00Z"},
                }
            )
        client = mock_httpx(FakeResponse(json_data={"items": items}))
        strand = FetchStrand()
        data = await strand._fetch_kubectl_workflows(_ctx(project_slug="my-proj"))

        assert data["count"] == 12
        assert len(data["workflows"]) == 10  # capped
        # Newest first (wf-11 has the latest startedAt).
        assert data["workflows"][0]["name"] == "wf-11"
        assert data["workflows"][0]["phase"] == "Succeeded"
        # Project label selector was passed.
        assert client.requests[0][1] == {"labelSelector": "project=my-proj"}

    @pytest.mark.asyncio
    async def test_empty_items_returns_zero_count(self, mock_httpx):
        mock_httpx(FakeResponse(json_data={"items": []}))
        strand = FetchStrand()
        data = await strand._fetch_kubectl_workflows(_ctx())
        assert data["count"] == 0
        assert data["workflows"] == []


class TestArgocdApp:
    """_fetch_argocd_app parses sync/health status from the ArgoCD API."""

    @pytest.mark.asyncio
    async def test_parses_sync_and_health(self, mock_httpx):
        apps = {
            "items": [
                {
                    "status": {
                        "sync": {"status": "Synced", "revision": "abc123"},
                        "health": {"status": "Healthy"},
                        "operationState": {"startedAt": "2026-07-20T00:00:00Z"},
                    },
                    "operation": {"operation": {"sync": {}}},
                }
            ]
        }
        client = mock_httpx(FakeResponse(json_data=apps))
        strand = FetchStrand()
        data = await strand._fetch_argocd_app(_ctx(app_name="my-app", cluster="ardenone-cluster"))

        assert data["name"] == "my-app"
        assert data["sync_status"] == "Synced"
        assert data["health_status"] == "Healthy"
        assert data["revision"] == "abc123"

    @pytest.mark.asyncio
    async def test_empty_items_returns_not_found(self, mock_httpx):
        mock_httpx(FakeResponse(json_data={"items": []}))
        strand = FetchStrand()
        data = await strand._fetch_argocd_app(_ctx(app_name="ghost", cluster="ardenone-cluster"))
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_no_app_name_returns_error(self, mock_httpx):
        client = mock_httpx(FakeResponse(json_data={"items": []}))
        strand = FetchStrand()
        data = await strand._fetch_argocd_app(_ctx(app_name=None, project_slug=None, cluster="ardenone-cluster"))
        assert data["error"] == "No application name specified"
        assert client.requests == []

    @pytest.mark.asyncio
    async def test_queries_correct_argocd_base_url(self, mock_httpx):
        """Mapped read-only cluster queries the correct ArgoCD API base URL."""
        apps = {"items": []}
        client = mock_httpx(FakeResponse(json_data=apps))
        strand = FetchStrand()
        await strand._fetch_argocd_app(_ctx(app_name="test-app", cluster="ardenone-cluster"))

        # Assert the requested URL contains the ardenone-cluster ArgoCD API base
        assert client.requests
        url = client.requests[0][0]
        assert "argocd-ro-ardenone-manager-ts.ardenone.com:8444" in url

    @pytest.mark.asyncio
    async def test_app_name_falls_back_to_project_slug(self, mock_httpx):
        """Omitting app_name falls back to project_slug for the ArgoCD application name."""
        apps = {
            "items": [
                {
                    "status": {
                        "sync": {"status": "Synced"},
                        "health": {"status": "Healthy"},
                    },
                }
            ]
        }
        client = mock_httpx(FakeResponse(json_data=apps))
        strand = FetchStrand()
        await strand._fetch_argocd_app(_ctx(app_name=None, project_slug="my-proj", cluster="ardenone-cluster"))

        # The app name should be passed as a query parameter
        assert client.requests
        params = client.requests[0][1]
        assert params == {"name": "my-proj"}

    @pytest.mark.asyncio
    async def test_authenticated_cluster_fails_fast_with_caveat(self, mock_httpx):
        """
        apexalgo-iad (access: authenticated) raises ArgocdEndpointUnresolvable
        with a reason mentioning authentication — ZERO HTTP requests issued.
        This proves a wrong-instance query is impossible.
        """
        from src.fetch.clusters import ArgocdEndpointUnresolvable, reset_cache

        reset_cache()  # ensure fresh clusters.yaml read
        client = mock_httpx(FakeResponse(json_data={"items": []}))
        strand = FetchStrand()

        # apexalgo-iad is mapped in clusters.yaml with access: authenticated
        with pytest.raises(ArgocdEndpointUnresolvable) as exc_info:
            await strand._fetch_argocd_app(
                _ctx(app_name="test-app", cluster="apexalgo-iad")
            )

        # The exception carries the cluster and a human-readable reason
        assert exc_info.value.cluster == "apexalgo-iad"
        assert "authentication" in exc_info.value.reason.lower()
        assert "apexalgo-iad" in exc_info.value.reason

        # CRITICAL: no HTTP request was made — proving no wrong-instance query
        assert client.requests == []

    @pytest.mark.asyncio
    async def test_unmapped_cluster_fails_fast_with_caveat(self, mock_httpx):
        """
        A cluster absent from clusters.yaml (e.g., 'some-unmapped-cluster')
        raises ArgocdEndpointUnresolvable with a reason mentioning no ArgoCD
        mapping — ZERO HTTP requests issued. This proves a wrong-instance
        query is impossible.
        """
        from src.fetch.clusters import ArgocdEndpointUnresolvable, reset_cache

        reset_cache()  # ensure fresh clusters.yaml read
        client = mock_httpx(FakeResponse(json_data={"items": []}))
        strand = FetchStrand()

        # 'some-unmapped-cluster' does not exist in clusters.yaml
        with pytest.raises(ArgocdEndpointUnresolvable) as exc_info:
            await strand._fetch_argocd_app(
                _ctx(app_name="test-app", cluster="some-unmapped-cluster")
            )

        # The exception carries the cluster and a human-readable reason
        assert exc_info.value.cluster == "some-unmapped-cluster"
        assert "no argocd mapping" in exc_info.value.reason.lower()
        assert "some-unmapped-cluster" in exc_info.value.reason

        # CRITICAL: no HTTP request was made — proving no wrong-instance query
        assert client.requests == []

    @pytest.mark.asyncio
    async def test_none_cluster_fails_fast_with_caveat(self, mock_httpx):
        """
        cluster=None (unconfigured) raises ArgocdEndpointUnresolvable with
        a reason mentioning no cluster configured — ZERO HTTP requests issued.
        """
        from src.fetch.clusters import ArgocdEndpointUnresolvable, reset_cache

        reset_cache()
        client = mock_httpx(FakeResponse(json_data={"items": []}))
        strand = FetchStrand()

        # cluster=None means no cluster is configured for the project
        with pytest.raises(ArgocdEndpointUnresolvable) as exc_info:
            await strand._fetch_argocd_app(
                _ctx(app_name="test-app", cluster=None)
            )

        # The exception carries a human-readable reason
        assert exc_info.value.cluster is None
        assert "no cluster configured" in exc_info.value.reason.lower()

        # CRITICAL: no HTTP request was made
        assert client.requests == []


class TestLogsAndEvents:
    """_fetch_logs returns raw text; _fetch_events parses an EventList."""

    @pytest.mark.asyncio
    async def test_logs_returns_text_and_line_count(self, mock_httpx):
        text = "line one\nline two\nline three"
        mock_httpx(FakeResponse(text=text))
        strand = FetchStrand()
        data = await strand._fetch_logs(_ctx(pod_name="web-0"))

        assert data["pod"] == "web-0"
        assert data["logs"] == text
        assert data["line_count"] == 3

    @pytest.mark.asyncio
    async def test_logs_missing_pod_returns_error(self, mock_httpx):
        client = mock_httpx(FakeResponse(text=""))
        strand = FetchStrand()
        data = await strand._fetch_logs(_ctx(pod_name=None))
        assert "error" in data
        assert client.requests == []

    @pytest.mark.asyncio
    async def test_events_parses_items_with_count(self, mock_httpx):
        events = {
            "items": [
                {"type": "Warning", "reason": "BackOff", "message": "Back-off restarting"},
                {"type": "Normal", "reason": "Started", "message": "Started container"},
            ]
        }
        mock_httpx(FakeResponse(json_data=events))
        strand = FetchStrand()
        data = await strand._fetch_events(_ctx())

        assert data["namespace"] == "myns"
        assert data["count"] == 2
        assert data["events"][0]["reason"] == "BackOff"
        assert data["events"][0]["involved_object"] == {}

    @pytest.mark.asyncio
    async def test_events_missing_namespace_returns_error(self, mock_httpx):
        client = mock_httpx(FakeResponse(json_data={"items": []}))
        strand = FetchStrand()
        data = await strand._fetch_events(_ctx(namespace=None))
        assert data["error"] == "No namespace specified"
        assert client.requests == []


# --- 2. local-source guards (no I/O) --------------------------------------


class TestLocalSourceGuards:
    """Local/subprocess executors fail gracefully when context is incomplete."""

    @pytest.mark.asyncio
    async def test_git_log_without_repo_path_returns_error(self):
        strand = FetchStrand()
        data = await strand._fetch_git_log(_ctx(repo_path=None))
        assert "error" in data

    @pytest.mark.asyncio
    async def test_git_log_nonexistent_local_path_returns_error(self):
        strand = FetchStrand()
        data = await strand._fetch_git_log(_ctx(repo_path="/nonexistent/path/xyz", ssh_target=None))
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_bead_list_without_repo_path_returns_error(self):
        strand = FetchStrand()
        data = await strand._fetch_bead_list(_ctx(repo_path=None))
        assert "error" in data

    @pytest.mark.asyncio
    async def test_fs_explore_without_repo_path_returns_error(self):
        strand = FetchStrand()
        data = await strand._fetch_fs_explore(_ctx(repo_path=None))
        assert "error" in data


# --- 3. end-to-end strand wiring ------------------------------------------


class TestStrandWiring:
    """
    A real FetchStrand.fetch() over a STATUS utterance with httpx mocked and
    local sources stubbed: the HTTP source types must execute and land parsed
    data in the FetchResult. This proves source-type → executor → structured
    data wiring, complementing the per-executor tests above.
    """

    @pytest.mark.asyncio
    async def test_status_intent_yields_parsed_http_source_data(self, mock_httpx):
        # One canned responder handles every HTTP URL the STATUS intent hits:
        # kubectl_pods + ci_status(workflows) + argocd_app.
        def responder(url, params):
            if "pods" in url and "log" not in url:
                return FakeResponse(
                    json_data={
                        "items": [
                            {
                                "metadata": {"name": "web-0"},
                                "status": {
                                    "phase": "Running",
                                    "containerStatuses": [{"ready": True}],
                                },
                            }
                        ]
                    }
                )
            if "workflows" in url:
                return FakeResponse(
                    json_data={
                        "items": [
                            {
                                "metadata": {"name": "wf-1"},
                                "status": {
                                    "phase": "Succeeded",
                                    "startedAt": "2026-07-20T00:00:00Z",
                                },
                            }
                        ]
                    }
                )
            if "applications" in url:
                return FakeResponse(
                    json_data={
                        "items": [
                            {
                                "status": {
                                    "sync": {"status": "Synced"},
                                    "health": {"status": "Healthy"},
                                }
                            }
                        ]
                    }
                )
            return FakeResponse(json_data={"items": []})

        mock_httpx(responder)

        strand = FetchStrand()

        # Stub only the non-HTTP/local sources so no subprocess/fs is touched.
        async def _stub(_ctx):
            return {"stubbed": True}

        for src in (
            FetchSource.FS_EXPLORE,
            FetchSource.FS_README,
            FetchSource.GIT_LOG,
            FetchSource.BEAD_LIST,
        ):
            strand._source_executors[src] = _stub

        request = FetchRequest(
            intent_type=IntentType.STATUS,
            context=_ctx(app_name="my-app", cluster="ardenone-cluster"),
            intent_id="intent-status-utterance",
            session_id="session-test",
        )
        result = await strand.fetch(request)

        # The strand succeeded and the HTTP source types produced parsed data.
        assert result.coverage.success_rate == 1.0
        pods = result.get_source_result(FetchSource.KUBECTL_PODS)
        assert pods.status == "success"
        assert pods.data["pod_count"] == 1
        assert pods.data["pods"][0]["name"] == "web-0"
        wf = result.get_source_result(FetchSource.CI_STATUS)
        assert wf.status == "success"
        assert wf.data["workflows"][0]["name"] == "wf-1"
        app = result.get_source_result(FetchSource.ARGOCD_APP)
        assert app.status == "success"
        assert app.data["sync_status"] == "Synced"
