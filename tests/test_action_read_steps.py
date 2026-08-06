"""
Unit tests for read-only action steps.

Tests CIStatusStep, ImageTagStep, and PodStatusStep with mocked dependencies
to verify correct behavior without requiring live clusters.
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from src.action.steps.read import CIStatusStep, ImageTagStep, PodStatusStep, StepResult


@pytest.fixture
def mock_clusters_config(tmp_path):
    """Create a mock clusters.yaml config."""
    config_content = """
clusters:
  test-cluster:
    proxy: http://test-proxy:8001
  another-cluster:
    proxy: http://another-proxy:8001
"""
    config_file = tmp_path / "clusters.yaml"
    config_file.write_text(config_content)
    return str(config_file)


@pytest.fixture
def mock_kubectl_config(tmp_path):
    """Create a mock kubeconfig file."""
    kubeconfig = tmp_path / "config"
    kubeconfig.write_text("mock kubeconfig content")
    return str(kubeconfig)


class TestCIStatusStep:
    """Test CIStatusStep workflow status queries."""

    def test_init_with_defaults(self):
        """Step initializes with default parameters."""
        step = CIStatusStep()
        assert step.kubectl_config == "/home/coding/.kube/iad-ci.kubeconfig"
        assert step.timeout == 15
        assert step.cluster == "iad-ci"

    def test_init_with_custom_params(self):
        """Step initializes with custom parameters."""
        step = CIStatusStep(
            kubectl_config="/custom/path/kubeconfig",
            timeout=30,
        )
        assert step.kubectl_config == "/custom/path/kubeconfig"
        assert step.timeout == 30

    @patch("subprocess.run")
    async def test_execute_successful_workflow_query(self, mock_run):
        """Successful workflow query returns parsed data."""
        # Mock successful kubectl response
        workflow_data = {
            "items": [
                {
                    "metadata": {
                        "name": "test-workflow-abc123",
                        "creationTimestamp": "2026-08-06T12:00:00Z",
                    },
                    "status": {
                        "phase": "Succeeded",
                        "message": "Workflow completed",
                    },
                }
            ]
        }
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(workflow_data),
            stderr="",
        )

        step = CIStatusStep()
        result = await step.execute(project_slug="test-project")

        assert result.success is True
        assert result.data["status"] == "success"
        assert result.data["phase"] == "Succeeded"
        assert result.data["workflow_name"] == "test-workflow-abc123"
        assert result.data["project_slug"] == "test-project"

    @patch("subprocess.run")
    async def test_execute_no_workflows_found(self, mock_run):
        """No workflows returns appropriate result."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps({"items": []}),
            stderr="",
        )

        step = CIStatusStep()
        result = await step.execute(project_slug="test-project")

        assert result.success is True
        assert result.data["status"] == "no_workflows"
        assert "No CI workflows found" in result.data["reason"]

    @patch("subprocess.run")
    async def test_execute_kubectl_command_fails(self, mock_run):
        """kubectl command failure returns error result."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Error from server (NotFound): workflows.argoproj.io not found",
        )

        step = CIStatusStep()
        result = await step.execute(project_slug="test-project")

        assert result.success is False
        assert "kubectl get workflows failed" in result.error

    @patch("subprocess.run")
    async def test_execute_timeout(self, mock_run):
        """Timeout returns error result."""
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired("kubectl", 15)

        step = CIStatusStep()
        result = await step.execute(project_slug="test-project")

        assert result.success is False
        assert "timed out" in result.error

    @patch("subprocess.run")
    async def test_execute_invalid_json_response(self, mock_run):
        """Invalid JSON in kubectl response returns error."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="not valid json",
            stderr="",
        )

        step = CIStatusStep()
        result = await step.execute(project_slug="test-project")

        assert result.success is False
        assert "Failed to parse" in result.error

    @patch("pathlib.Path.exists")
    def test_execute_missing_kubeconfig(self, mock_exists):
        """Missing kubeconfig returns skipped result."""
        mock_exists.return_value = False

        step = CIStatusStep()
        result = await step.execute(project_slug="test-project")

        assert result.success is False
        assert result.data["status"] == "skipped"
        assert "not accessible" in result.data["reason"]

    @patch("subprocess.run")
    async def test_workflow_phase_mapping(self, mock_run):
        """Workflow phases map to simple statuses correctly."""
        test_phases = [
            ("Succeeded", "success"),
            ("Failed", "failed"),
            ("Running", "running"),
            ("Pending", "pending"),
            ("Error", "error"),
            ("UnknownPhase", "unknown"),
        ]

        for phase, expected_status in test_phases:
            workflow_data = {
                "items": [
                    {
                        "metadata": {"name": f"workflow-{phase}"},
                        "status": {"phase": phase},
                    }
                ]
            }
            mock_run.return_value = Mock(
                returncode=0,
                stdout=json.dumps(workflow_data),
                stderr="",
            )

            step = CIStatusStep()
            result = await step.execute(project_slug="test-project")

            assert result.data["status"] == expected_status


class TestImageTagStep:
    """Test ImageTagStep tag extraction from CI results."""

    def test_init(self):
        """Step initializes without parameters."""
        step = ImageTagStep()
        assert step is not None

    async def test_execute_with_ci_status_result(self):
        """Extract tag from successful CI status result."""
        ci_result = StepResult(
            success=True,
            data={
                "status": "success",
                "workflow_name": "build-workflow-v1.2.3",
                "project_slug": "test-project",
            },
        )

        step = ImageTagStep()
        result = await step.execute(ci_status_result=ci_result)

        assert result.success is True
        assert result.data["tag"] == "v1.2.3"
        assert "test-project" in result.data["registry_path"]

    async def test_execute_with_digest_in_workflow_name(self):
        """Extract digest when present in workflow name."""
        ci_result = StepResult(
            success=True,
            data={
                "status": "success",
                "workflow_name": "build-sha256:abc123def456-final",
                "project_slug": "test-project",
            },
        )

        step = ImageTagStep()
        result = await step.execute(ci_status_result=ci_result)

        assert result.success is True
        assert result.data["digest"] == "sha256:abc123def456"

    async def test_execute_rejects_latest_tag(self):
        """Reject :latest tag explicitly."""
        ci_result = StepResult(
            success=True,
            data={
                "status": "success",
                "workflow_name": "build-latest",
                "project_slug": "test-project",
            },
        )

        step = ImageTagStep()
        result = await step.execute(ci_status_result=ci_result)

        # Should not return "latest" as the tag
        assert result.data["tag"] != "latest"
        assert result.data["tag"] == "build-latest"  # Fallback to full name

    async def test_execute_with_failed_ci_result(self):
        """Failed CI result returns error."""
        ci_result = StepResult(
            success=False,
            data={},
            error="CI check failed",
        )

        step = ImageTagStep()
        result = await step.execute(ci_status_result=ci_result)

        assert result.success is False
        assert "not provided or failed" in result.error

    async def test_execute_with_none_ci_result(self):
        """None CI result returns error."""
        step = ImageTagStep()
        result = await step.execute(ci_status_result=None)

        assert result.success is False
        assert "not provided or failed" in result.error

    async def test_registry_path_format(self):
        """Registry path includes project and tag."""
        ci_result = StepResult(
            success=True,
            data={
                "status": "success",
                "workflow_name": "build-v1.0.0",
                "project_slug": "my-app",
            },
        )

        step = ImageTagStep()
        result = await step.execute(ci_status_result=ci_result)

        assert result.success is True
        assert result.data["registry_path"] == "ronaldraygun/my-app:v1.0.0"


class TestPodStatusStep:
    """Test PodStatusStep kubectl proxy queries."""

    def test_init_with_defaults(self):
        """Step initializes with default parameters."""
        step = PodStatusStep()
        assert step.proxy_url is None
        assert step.timeout == 10.0

    def test_init_with_custom_params(self):
        """Step initializes with custom parameters."""
        step = PodStatusStep(
            proxy_url="http://custom-proxy:8001",
            timeout=30.0,
        )
        assert step.proxy_url == "http://custom-proxy:8001"
        assert step.timeout == 30.0

    @patch("httpx.AsyncClient")
    async def test_execute_successful_pod_query(self, mock_client_class):
        """Successful pod query returns parsed data."""
        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "metadata": {"name": "pod-1"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {"ready": True},
                            {"ready": True},
                        ]
                    }
                },
                {
                    "metadata": {"name": "pod-2"},
                    "status": {
                        "phase": "Pending",
                        "containerStatuses": [
                            {"ready": False},
                        ]
                    }
                },
            ]
        }

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        step = PodStatusStep()
        result = await step.execute(namespace="test-ns", cluster="test-cluster")

        assert result.success is True
        assert result.data["total_pods"] == 2
        assert result.data["phase_counts"]["Running"] == 1
        assert result.data["phase_counts"]["Pending"] == 1

        # Check pod details
        pods = result.data["pods"]
        assert len(pods) == 2
        assert pods[0]["name"] == "pod-1"
        assert pods[0]["phase"] == "Running"
        assert pods[0]["ready"] == 2
        assert pods[0]["total"] == 2

    @patch("httpx.AsyncClient")
    async def test_execute_http_error(self, mock_client_class):
        """HTTP error returns error result."""
        import httpx

        mock_client = Mock()
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        step = PodStatusStep()
        result = await step.execute(namespace="test-ns", cluster="test-cluster")

        assert result.success is False
        assert "Failed to get pod status" in result.error

    async def test_execute_missing_namespace(self):
        """Missing namespace returns error."""
        step = PodStatusStep()
        result = await step.execute(namespace="", cluster="test-cluster")

        assert result.success is False
        assert "Namespace is required" in result.error

    @patch.object(PodStatusStep, "_get_cluster_proxy")
    async def test_execute_no_proxy_configured(self, mock_get_proxy):
        """No proxy configured returns error."""
        mock_get_proxy.return_value = None

        step = PodStatusStep()
        result = await step.execute(namespace="test-ns", cluster="unmapped-cluster")

        assert result.success is False
        assert "no proxy configured" in result.error

    @patch("httpx.AsyncClient")
    @patch.object(PodStatusStep, "_get_cluster_proxy")
    async def test_proxy_url_lookup(self, mock_get_proxy, mock_client_class, mock_clusters_config):
        """Proxy URL is looked up from cluster config."""
        mock_get_proxy.return_value = "http://test-proxy:8001"

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        step = PodStatusStep()
        result = await step.execute(namespace="test-ns", cluster="test-cluster")

        assert result.success is True
        mock_get_proxy.assert_called_with("test-cluster")

    @patch("httpx.AsyncClient")
    async def test_pod_ready_ratio_calculation(self, mock_client_class):
        """Ready ratio is calculated correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "metadata": {"name": "pod-1"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {"ready": True},
                            {"ready": False},
                        ]
                    }
                },
            ]
        }

        mock_client = Mock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        step = PodStatusStep()
        result = await step.execute(namespace="test-ns")

        pods = result.data["pods"]
        assert pods[0]["ready"] == 1
        assert pods[0]["total"] == 2
        assert pods[0]["ready_ratio"] == "1/2"

    @patch("src.action.steps.read.Path")
    def test_get_cluster_proxy_reads_config(self, mock_path, mock_clusters_config):
        """Cluster proxy URL is read from config file."""
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.__truediv__.return_value.exists.return_value = True

        with patch("builtins.open", mock_clusters_config):
            step = PodStatusStep()
            proxy_url = step._get_cluster_proxy("test-cluster")

            assert proxy_url == "http://test-proxy:8001"

    @patch("src.action.steps.read.Path")
    def test_get_cluster_proxy_missing_config(self, mock_path):
        """Missing config file returns None."""
        mock_path.return_value.exists.return_value = False

        step = PodStatusStep()
        proxy_url = step._get_cluster_proxy("test-cluster")

        assert proxy_url is None

    @patch("src.action.steps.read.Path")
    def test_get_cluster_proxy_unknown_cluster(self, mock_path, mock_clusters_config):
        """Unknown cluster returns None."""
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.__truediv__.return_value.exists.return_value = True

        with patch("builtins.open", mock_clusters_config):
            step = PodStatusStep()
            proxy_url = step._get_cluster_proxy("unknown-cluster")

            assert proxy_url is None


# Helper to create awaitable versions for async tests
async def await_step(func, *args, **kwargs):
    """Helper to run async step methods in tests."""
    return await func(*args, **kwargs)


# Monkey patch for test execution
CIStatusStep.execute = await_step
ImageTagStep.execute = await_step
PodStatusStep.execute = await_step
