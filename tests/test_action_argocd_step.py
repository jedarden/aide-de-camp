"""
Unit tests for ArgoCD sync status action step.

Tests ArgoCDSyncStatusStep with mocked dependencies to verify correct behavior
including ArgoCD API polling, timeout handling, progress streaming, and error cases.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest
import httpx

from src.action.steps.argocd import (
    ArgoCDSyncStatusStep,
    SyncStatus,
    HealthStatus,
    ArgoCDApplicationStatus,
    StepResult,
)


@pytest.fixture
def mock_clusters_config(tmp_path):
    """Create a mock clusters.yaml configuration file."""
    clusters_content = """
clusters:
  ardenone-cluster:
    argocd_api: https://argocd-ro-ardenone-manager-ts.ardenone.com:8444
    access: read-only-proxy
  ardenone-manager:
    argocd_api: https://argocd-ro-ardenone-manager-ts.ardenone.com:8444
    access: read-only-proxy
  apexalgo-iad:
    argocd_api: https://argocd-rs-manager.tail1b1987.ts.net:8080
    access: authenticated
  iad-options:
    argocd_api: https://argocd-rs-manager.tail1b1987.ts.net:8080
    access: authenticated
"""
    config_path = tmp_path / "clusters.yaml"
    config_path.write_text(clusters_content)
    return str(config_path)


@pytest.fixture
def argocd_synced_response():
    """Mock ArgoCD API response for Synced/Healthy application."""
    return {
        "status": {
            "sync": {
                "status": "Synced",
                "revision": "main@sha256:abc123",
            },
            "health": {
                "status": "Healthy",
            },
            "operationState": {
                "operation": "Sync",
                "phase": "Succeeded",
                "startedAt": "2026-08-11T20:00:00Z",
                "finishedAt": "2026-08-11T20:00:30Z",
            },
        }
    }


@pytest.fixture
def argocd_unknown_response():
    """Mock ArgoCD API response for Unknown application (not found)."""
    return {
        "status": {
            "sync": {
                "status": "Unknown",
            },
            "health": {
                "status": "Unknown",
            },
        }
    }


@pytest.fixture
def argocd_out_of_sync_response():
    """Mock ArgoCD API response for OutOfSync application."""
    return {
        "status": {
            "sync": {
                "status": "OutOfSync",
                "revision": "main@sha256:def456",
            },
            "health": {
                "status": "Progressing",
            },
            "operationState": {
                "operation": "Sync",
                "phase": "Running",
                "startedAt": "2026-08-11T20:01:00Z",
            },
        }
    }


class TestSyncStatusEnums:
    """Test SyncStatus and HealthStatus enums."""

    def test_sync_status_values(self):
        """SyncStatus enum has expected values."""
        assert SyncStatus.SYNCED == "Synced"
        assert SyncStatus.UNKNOWN == "Unknown"
        assert SyncStatus.OUT_OF_SYNC == "OutOfSync"
        assert SyncStatus.IN_PROGRESS == "InProgress"

    def test_health_status_values(self):
        """HealthStatus enum has expected values."""
        assert HealthStatus.HEALTHY == "Healthy"
        assert HealthStatus.UNKNOWN == "Unknown"
        assert HealthStatus.PROGRESSING == "Progressing"
        assert HealthStatus.DEGRADED == "Degraded"
        assert HealthStatus.MISSING == "Missing"


class TestArgoCDApplicationStatus:
    """Test ArgoCDApplicationStatus dataclass."""

    def test_create_application_status(self):
        """ArgoCDApplicationStatus can be created with all fields."""
        operation_state = {"operation": "Sync", "phase": "Succeeded"}
        status = ArgoCDApplicationStatus(
            sync_status=SyncStatus.SYNCED,
            health_status=HealthStatus.HEALTHY,
            operation_state=operation_state,
            operation_timestamp="2026-08-11T20:00:00Z",
            revision="main@sha256:abc123",
        )

        assert status.sync_status == SyncStatus.SYNCED
        assert status.health_status == HealthStatus.HEALTHY
        assert status.operation_state == operation_state
        assert status.operation_timestamp == "2026-08-11T20:00:00Z"
        assert status.revision == "main@sha256:abc123"

    def test_create_application_status_minimal(self):
        """ArgoCDApplicationStatus can be created with minimal fields."""
        status = ArgoCDApplicationStatus(
            sync_status=SyncStatus.UNKNOWN,
            health_status=HealthStatus.UNKNOWN,
        )

        assert status.sync_status == SyncStatus.UNKNOWN
        assert status.health_status == HealthStatus.UNKNOWN
        assert status.operation_state is None
        assert status.operation_timestamp is None
        assert status.revision is None


class TestArgoCDSyncStatusStepInit:
    """Test ArgoCDSyncStatusStep initialization and validation."""

    def test_init_with_defaults(self):
        """ArgoCDSyncStatusStep can be initialized with defaults."""
        step = ArgoCDSyncStatusStep()

        assert step.timeout == 300
        assert step.poll_interval == 5

    def test_init_with_custom_values(self):
        """ArgoCDSyncStatusStep can be initialized with custom values."""
        step = ArgoCDSyncStatusStep(
            timeout=600,
            poll_interval=10,
        )

        assert step.timeout == 600
        assert step.poll_interval == 10

    def test_init_with_custom_config_path(self, mock_clusters_config):
        """ArgoCDSyncStatusStep can be initialized with custom config path."""
        step = ArgoCDSyncStatusStep(
            clusters_config_path=mock_clusters_config,
        )

        assert step.clusters_config_path == Path(mock_clusters_config)

    def test_init_invalid_timeout(self):
        """ArgoCDSyncStatusStep rejects invalid timeout."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            ArgoCDSyncStatusStep(timeout=0)

        with pytest.raises(ValueError, match="timeout must be positive"):
            ArgoCDSyncStatusStep(timeout=-10)

    def test_init_invalid_poll_interval(self):
        """ArgoCDSyncStatusStep rejects invalid poll interval."""
        with pytest.raises(ValueError, match="poll_interval must be positive"):
            ArgoCDSyncStatusStep(poll_interval=0)

        with pytest.raises(ValueError, match="poll_interval must be positive"):
            ArgoCDSyncStatusStep(poll_interval=-5)

    def test_init_poll_interval_exceeds_timeout(self):
        """ArgoCDSyncStatusStep rejects poll_interval >= timeout."""
        with pytest.raises(ValueError, match="poll_interval.*must be less than timeout"):
            ArgoCDSyncStatusStep(timeout=60, poll_interval=60)

        with pytest.raises(ValueError, match="poll_interval.*must be less than timeout"):
            ArgoCDSyncStatusStep(timeout=60, poll_interval=120)


class TestArgoCDEndpointResolution:
    """Test ArgoCD endpoint resolution from clusters.yaml."""

    def test_get_argocd_endpoint_read_only_proxy(self, mock_clusters_config):
        """Successfully resolve read-only-proxy endpoint."""
        step = ArgoCDSyncStatusStep(clusters_config_path=mock_clusters_config)
        endpoint = step._get_argocd_endpoint("ardenone-cluster")

        assert endpoint is not None
        assert endpoint["argocd_api"] == "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444"
        assert endpoint["access"] == "read-only-proxy"

    def test_get_argocd_endpoint_authenticated(self, mock_clusters_config):
        """Successfully resolve authenticated endpoint."""
        step = ArgoCDSyncStatusStep(clusters_config_path=mock_clusters_config)
        endpoint = step._get_argocd_endpoint("apexalgo-iad")

        assert endpoint is not None
        assert endpoint["argocd_api"] == "https://argocd-rs-manager.tail1b1987.ts.net:8080"
        assert endpoint["access"] == "authenticated"

    def test_get_argocd_endpoint_cluster_not_found(self, mock_clusters_config):
        """Return None for cluster not in config."""
        step = ArgoCDSyncStatusStep(clusters_config_path=mock_clusters_config)
        endpoint = step._get_argocd_endpoint("nonexistent-cluster")

        assert endpoint is None

    def test_get_argocd_endpoint_config_not_found(self):
        """Return None when config file doesn't exist."""
        step = ArgoCDSyncStatusStep(clusters_config_path="/nonexistent/clusters.yaml")
        endpoint = step._get_argocd_endpoint("ardenone-cluster")

        assert endpoint is None


class TestArgoCDApplicationStatusQuery:
    """Test _query_application_status method."""

    @pytest.mark.asyncio
    async def test_query_synced_healthy(self, argocd_synced_response):
        """Successfully query Synced/Healthy application status."""
        step = ArgoCDSyncStatusStep()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=argocd_synced_response)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        status = await step._query_application_status(
            mock_client,
            "https://argocd.example.com",
            "test-app",
        )

        assert status.sync_status == SyncStatus.SYNCED
        assert status.health_status == HealthStatus.HEALTHY
        assert status.revision == "main@sha256:abc123"
        assert status.operation_timestamp == "2026-08-11T20:00:30Z"
        assert status.operation_state is not None

    @pytest.mark.asyncio
    async def test_query_unknown_status(self, argocd_unknown_response):
        """Successfully query Unknown application status."""
        step = ArgoCDSyncStatusStep()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=argocd_unknown_response)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        status = await step._query_application_status(
            mock_client,
            "https://argocd.example.com",
            "test-app",
        )

        assert status.sync_status == SyncStatus.UNKNOWN
        assert status.health_status == HealthStatus.UNKNOWN
        assert status.revision is None

    @pytest.mark.asyncio
    async def test_query_unhandled_sync_status(self):
        """Handle unexpected sync status gracefully."""
        unexpected_response = {
            "status": {
                "sync": {"status": "UnexpectedStatus"},
                "health": {"status": "Healthy"},
            }
        }

        step = ArgoCDSyncStatusStep()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=unexpected_response)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        status = await step._query_application_status(
            mock_client,
            "https://argocd.example.com",
            "test-app",
        )

        assert status.sync_status == SyncStatus.UNKNOWN  # Falls back to UNKNOWN

    @pytest.mark.asyncio
    async def test_query_http_error(self):
        """Raise httpx.HTTPError on API failure."""
        step = ArgoCDSyncStatusStep()

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")

        with pytest.raises(httpx.HTTPError):
            await step._query_application_status(
                mock_client,
                "https://argocd.example.com",
                "test-app",
            )


class TestArgoCDSyncStatusExecute:
    """Test execute method with various scenarios."""

    @pytest.mark.asyncio
    async def test_execute_success_immediate_synced(self, mock_clusters_config, argocd_synced_response):
        """Successfully poll application that's already Synced/Healthy."""
        step = ArgoCDSyncStatusStep(
            timeout=60,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=argocd_synced_response)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        assert result.success is True
        assert result.data["status"] == "synced"
        assert result.data["sync_status"] == "Synced"
        assert result.data["health_status"] == "Healthy"
        assert result.data["application"] == "test-app"
        assert result.data["cluster"] == "ardenone-cluster"
        assert result.data["poll_count"] == 1
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_success_after_polls(self, mock_clusters_config):
        """Successfully poll application that reaches Synced/Healthy after multiple polls."""
        step = ArgoCDSyncStatusStep(
            timeout=60,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        # Mock responses: first OutOfSync, then Synced
        out_of_sync_response = {
            "status": {
                "sync": {"status": "OutOfSync"},
                "health": {"status": "Progressing"},
            }
        }

        synced_response = {
            "status": {
                "sync": {"status": "Synced", "revision": "main@sha256:abc123"},
                "health": {"status": "Healthy"},
                "operationState": {
                    "operation": "Sync",
                    "phase": "Succeeded",
                    "finishedAt": "2026-08-11T20:00:30Z",
                },
            }
        }

        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            Mock(json=Mock(return_value=out_of_sync_response), raise_for_status=Mock()),
            Mock(json=Mock(return_value=synced_response), raise_for_status=Mock()),
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        assert result.success is True
        assert result.data["status"] == "synced"
        assert result.data["poll_count"] == 2
        assert result.data["duration_seconds"] >= 1.0  # At least one sleep

    @pytest.mark.asyncio
    async def test_execute_unknown_application_times_out(self, mock_clusters_config, argocd_unknown_response):
        """Handle application in Unknown state (not found) - times out after polling."""
        step = ArgoCDSyncStatusStep(
            timeout=2,  # Short timeout for testing
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=argocd_unknown_response)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="nonexistent-app",
                cluster="ardenone-cluster",
            )

        # Unknown status will cause timeout since it never reaches Synced/Healthy
        assert result.success is False
        assert result.data["status"] == "timeout"
        assert "timeout" in result.error.lower()
        # Verify final status is Unknown
        assert result.data["final_sync_status"] == "Unknown"
        assert result.data["final_health_status"] == "Unknown"

    @pytest.mark.asyncio
    async def test_execute_timeout(self, mock_clusters_config, argocd_out_of_sync_response):
        """Handle timeout when application doesn't reach Synced/Healthy."""
        step = ArgoCDSyncStatusStep(
            timeout=2,  # Short timeout for testing
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = argocd_out_of_sync_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        assert result.success is False
        assert result.data["status"] == "timeout"
        assert "timeout" in result.error.lower()
        assert result.data["timeout_seconds"] == 2
        # Verify final status is included in timeout result
        assert "final_sync_status" in result.data
        assert "final_health_status" in result.data
        assert result.data["final_sync_status"] == "OutOfSync"
        assert result.data["final_health_status"] == "Progressing"
        # Verify error message includes final status
        assert "sync=OutOfSync" in result.error
        assert "health=Progressing" in result.error

    @pytest.mark.asyncio
    async def test_execute_cluster_not_found(self, mock_clusters_config):
        """Handle cluster not found in config."""
        step = ArgoCDSyncStatusStep(clusters_config_path=mock_clusters_config)

        result = await step.execute(
            argocd_app="test-app",
            cluster="nonexistent-cluster",
        )

        assert result.success is False
        assert "not found" in result.error.lower()
        assert "nonexistent-cluster" in result.data["cluster"]

    @pytest.mark.asyncio
    async def test_execute_authenticated_access_rejected(self, mock_clusters_config):
        """Reject authenticated access mode (only read-only-proxy supported)."""
        step = ArgoCDSyncStatusStep(clusters_config_path=mock_clusters_config)

        result = await step.execute(
            argocd_app="test-app",
            cluster="apexalgo-iad",  # Has authenticated access
        )

        assert result.success is False
        assert "requires authentication" in result.error.lower()
        assert result.data["access_mode"] == "authenticated"

    @pytest.mark.asyncio
    async def test_execute_http_error_retry(self, mock_clusters_config, argocd_synced_response):
        """Retry on transient HTTP errors."""
        step = ArgoCDSyncStatusStep(
            timeout=60,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        # First call fails, second succeeds
        mock_client.get.side_effect = [
            httpx.HTTPError("Connection timeout"),
            Mock(json=Mock(return_value=argocd_synced_response), raise_for_status=Mock()),
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        assert result.success is True
        assert result.data["poll_count"] >= 2  # At least 2 polls (one failed, one succeeded)

    @pytest.mark.asyncio
    async def test_execute_progress_callback(self, mock_clusters_config, argocd_synced_response):
        """Stream progress updates via callback."""
        step = ArgoCDSyncStatusStep(
            timeout=60,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        progress_updates = []

        async def progress_callback(update):
            progress_updates.append(update)

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = argocd_synced_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
                progress_callback=progress_callback,
            )

        assert result.success is True
        assert len(progress_updates) >= 1
        assert progress_updates[0]["poll_count"] == 1
        assert progress_updates[0]["application"] == "test-app"
        assert progress_updates[0]["cluster"] == "ardenone-cluster"
        assert "elapsed_seconds" in progress_updates[0]
        # Verify current_status is included in progress updates
        assert "current_status" in progress_updates[0]
        assert progress_updates[0]["current_status"]["sync_status"] == "Synced"
        assert progress_updates[0]["current_status"]["health_status"] == "Healthy"

    @pytest.mark.asyncio
    async def test_execute_config_file_missing(self, tmp_path):
        """Handle missing clusters.yaml file."""
        # Don't create the config file
        nonexistent_config = tmp_path / "nonexistent" / "clusters.yaml"

        step = ArgoCDSyncStatusStep(clusters_config_path=str(nonexistent_config))

        result = await step.execute(
            argocd_app="test-app",
            cluster="ardenone-cluster",
        )

        assert result.success is False
        assert "not found" in result.error.lower() or "Clusters config not found" in result.error


class TestArgoCDSyncStatusIntegration:
    """Integration tests with realistic scenarios."""

    @pytest.mark.asyncio
    async def test_full_sync_polling_scenario(self, mock_clusters_config):
        """Test realistic polling scenario with multiple status transitions."""
        step = ArgoCDSyncStatusStep(
            timeout=10,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        # Simulate progression: Unknown → OutOfSync → InProgress → Synced
        responses = [
            {"status": {"sync": {"status": "Unknown"}, "health": {"status": "Unknown"}}},
            {"status": {"sync": {"status": "OutOfSync"}, "health": {"status": "Progressing"}}},
            {"status": {"sync": {"status": "InProgress"}, "health": {"status": "Progressing"}}},
            {
                "status": {
                    "sync": {"status": "Synced", "revision": "main@sha256:final"},
                    "health": {"status": "Healthy"},
                    "operationState": {"finishedAt": "2026-08-11T20:00:00Z"},
                }
            },
        ]

        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            Mock(json=Mock(return_value=r), raise_for_status=Mock()) for r in responses
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        assert result.success is True
        assert result.data["poll_count"] == 4
        assert result.data["revision"] == "main@sha256:final"
        assert result.data["duration_seconds"] >= 3.0  # 3 sleeps between 4 polls

    @pytest.mark.asyncio
    async def test_degraded_health_after_sync(self, mock_clusters_config):
        """Handle Degraded health status after sync completes."""
        step = ArgoCDSyncStatusStep(
            timeout=5,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        # Application synced but unhealthy
        degraded_response = {
            "status": {
                "sync": {"status": "Synced"},
                "health": {"status": "Degraded"},
                "operationState": {"phase": "Succeeded"},
            }
        }

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = degraded_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        # Should time out because not Healthy
        assert result.success is False
        assert result.data["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_execute_progress_throttling(self, mock_clusters_config):
        """Verify progress updates are throttled according to progress_throttle_seconds."""
        step = ArgoCDSyncStatusStep(
            timeout=10,
            poll_interval=1,
            progress_throttle_seconds=2,  # Throttle to every 2 seconds
            clusters_config_path=mock_clusters_config,
        )

        progress_updates = []

        async def progress_callback(update):
            progress_updates.append(update)

        # Mock responses: Unknown → OutOfSync → Synced (3 transitions)
        responses = [
            {"status": {"sync": {"status": "Unknown"}, "health": {"status": "Unknown"}}},
            {"status": {"sync": {"status": "OutOfSync"}, "health": {"status": "Progressing"}}},
            {
                "status": {
                    "sync": {"status": "Synced", "revision": "main@sha256:abc"},
                    "health": {"status": "Healthy"},
                    "operationState": {"finishedAt": "2026-08-11T20:00:00Z"},
                }
            },
        ]

        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            Mock(json=Mock(return_value=r), raise_for_status=Mock()) for r in responses
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
                progress_callback=progress_callback,
            )

        assert result.success is True
        # With 3 polls over ~2 seconds and a 2-second throttle, we should get
        # progress updates on poll 1 (first poll always updates) and poll 3
        # (after 2 seconds have passed)
        assert len(progress_updates) >= 1
        # Verify each update has the required fields
        for update in progress_updates:
            assert "poll_count" in update
            assert "elapsed_seconds" in update
            assert "current_status" in update
            assert "sync_status" in update["current_status"]
            assert "health_status" in update["current_status"]


class TestArgoCDErrorHandling:
    """Test error handling edge cases."""

    @pytest.mark.asyncio
    async def test_execute_404_not_found(self, mock_clusters_config):
        """Handle HTTP 404 error when application not found."""
        step = ArgoCDSyncStatusStep(
            timeout=5,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        # Simulate 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError(
            "Application not found",
            request=Mock(),
            response=mock_response
        )
        mock_client.get.side_effect = http_error

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="nonexistent-app",
                cluster="ardenone-cluster",
            )

        # Should retry and eventually timeout
        assert result.success is False
        assert result.data["status"] == "timeout"
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_500_server_error(self, mock_clusters_config):
        """Handle HTTP 500 server error with retries."""
        step = ArgoCDSyncStatusStep(
            timeout=5,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        # First call returns 500, second succeeds
        mock_response_500 = Mock()
        mock_response_500.status_code = 500

        synced_response = {
            "status": {
                "sync": {"status": "Synced", "revision": "main@sha256:abc"},
                "health": {"status": "Healthy"},
            }
        }
        mock_response_success = Mock()
        mock_response_success.json = Mock(return_value=synced_response)
        mock_response_success.raise_for_status = Mock()

        http_error = httpx.HTTPStatusError(
            "Internal server error",
            request=Mock(),
            response=mock_response_500
        )

        mock_client.get.side_effect = [
            http_error,
            mock_response_success,
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        # Should recover and succeed
        assert result.success is True
        assert result.data["status"] == "synced"
        assert result.data["poll_count"] >= 2

    @pytest.mark.asyncio
    async def test_execute_malformed_json_response(self, mock_clusters_config):
        """Handle malformed JSON response from ArgoCD API."""
        step = ArgoCDSyncStatusStep(
            timeout=5,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        # Should catch exception and return error
        assert result.success is False
        assert "Failed to poll ArgoCD sync status" in result.error or "Invalid JSON" in result.error

    @pytest.mark.asyncio
    async def test_execute_missing_required_fields(self, mock_clusters_config):
        """Handle API response missing required fields."""
        step = ArgoCDSyncStatusStep(
            timeout=5,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        # Response with missing status field
        incomplete_response = {
            "metadata": {"name": "test-app"},
            # Missing "status" field
        }

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=incomplete_response)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        # Should handle gracefully with Unknown status
        assert result.success is False  # Never reaches Synced/Healthy
        assert result.data["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_progress_callback_exception(self, mock_clusters_config, argocd_synced_response):
        """Handle exceptions from progress callback gracefully."""
        step = ArgoCDSyncStatusStep(
            timeout=60,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        # Callback that raises an exception
        async def failing_callback(update):
            raise ValueError("Callback failed!")

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = argocd_synced_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Should not propagate callback exception
            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
                progress_callback=failing_callback,
            )

        # Step should still succeed despite callback failure
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_network_timeout(self, mock_clusters_config):
        """Handle network timeout during API request."""
        step = ArgoCDSyncStatusStep(
            timeout=5,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        # Simulate network timeout
        mock_client.get.side_effect = httpx.TimeoutException("Request timed out")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        # Should retry and eventually timeout
        assert result.success is False
        assert result.data["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_execute_connection_refused(self, mock_clusters_config):
        """Handle connection refused error."""
        step = ArgoCDSyncStatusStep(
            timeout=5,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        # Simulate connection refused
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        # Should retry and eventually timeout
        assert result.success is False
        assert result.data["status"] == "timeout"


class TestArgoCDTimestampParsing:
    """Test operation timestamp parsing edge cases."""

    @pytest.mark.asyncio
    async def test_operation_timestamp_prefer_finished_at(self):
        """Prefer finishedAt over startedAt for operation timestamp."""
        step = ArgoCDSyncStatusStep()

        response_with_both = {
            "status": {
                "sync": {"status": "Synced"},
                "health": {"status": "Healthy"},
                "operationState": {
                    "startedAt": "2026-08-11T20:00:00Z",
                    "finishedAt": "2026-08-11T20:00:30Z",
                },
            }
        }

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=response_with_both)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        status = await step._query_application_status(
            mock_client,
            "https://argocd.example.com",
            "test-app",
        )

        # Should prefer finishedAt
        assert status.operation_timestamp == "2026-08-11T20:00:30Z"

    @pytest.mark.asyncio
    async def test_operation_timestamp_fallback_to_started_at(self):
        """Fallback to startedAt when finishedAt is missing."""
        step = ArgoCDSyncStatusStep()

        response_without_finished = {
            "status": {
                "sync": {"status": "Synced"},
                "health": {"status": "Healthy"},
                "operationState": {
                    "startedAt": "2026-08-11T20:00:00Z",
                    # Missing finishedAt
                },
            }
        }

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=response_without_finished)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        status = await step._query_application_status(
            mock_client,
            "https://argocd.example.com",
            "test-app",
        )

        # Should fallback to startedAt
        assert status.operation_timestamp == "2026-08-11T20:00:00Z"

    @pytest.mark.asyncio
    async def test_operation_timestamp_missing(self):
        """Handle missing operation timestamp gracefully."""
        step = ArgoCDSyncStatusStep()

        response_without_timestamp = {
            "status": {
                "sync": {"status": "Synced"},
                "health": {"status": "Healthy"},
                "operationState": {
                    "phase": "Succeeded",
                    # Missing both startedAt and finishedAt
                },
            }
        }

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=response_without_timestamp)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        status = await step._query_application_status(
            mock_client,
            "https://argocd.example.com",
            "test-app",
        )

        # Should handle missing timestamp
        assert status.operation_timestamp is None

    @pytest.mark.asyncio
    async def test_operation_state_missing(self):
        """Handle missing operationState field."""
        step = ArgoCDSyncStatusStep()

        response_without_operation_state = {
            "status": {
                "sync": {"status": "Synced"},
                "health": {"status": "Healthy"},
                # Missing operationState
            }
        }

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=response_without_operation_state)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        status = await step._query_application_status(
            mock_client,
            "https://argocd.example.com",
            "test-app",
        )

        # Should handle missing operationState
        assert status.operation_state is None
        assert status.operation_timestamp is None


class TestArgoCDProgressStreamingDetailed:
    """Detailed progress streaming tests."""

    @pytest.mark.asyncio
    async def test_progress_first_update_always_sent(self, mock_clusters_config):
        """First progress update is always sent regardless of throttle."""
        step = ArgoCDSyncStatusStep(
            timeout=60,
            poll_interval=1,
            progress_throttle_seconds=10,  # High throttle
            clusters_config_path=mock_clusters_config,
        )

        progress_updates = []

        async def progress_callback(update):
            progress_updates.append(update)

        # Immediate synced response
        synced_response = {
            "status": {
                "sync": {"status": "Synced", "revision": "main@sha256:abc"},
                "health": {"status": "Healthy"},
            }
        }

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=synced_response)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
                progress_callback=progress_callback,
            )

        assert result.success is True
        # First update should always be sent even with high throttle
        assert len(progress_updates) >= 1
        assert progress_updates[0]["poll_count"] == 1

    @pytest.mark.asyncio
    async def test_progress_multiple_updates_with_throttle(self, mock_clusters_config):
        """Multiple progress updates sent when throttle period elapses."""
        step = ArgoCDSyncStatusStep(
            timeout=60,
            poll_interval=1,
            progress_throttle_seconds=2,
            clusters_config_path=mock_clusters_config,
        )

        progress_updates = []

        async def progress_callback(update):
            progress_updates.append(update)

        # Multiple out-of-sync responses before finally syncing
        responses = []
        for i in range(5):
            responses.append({
                "status": {
                    "sync": {"status": "OutOfSync"},
                    "health": {"status": "Progressing"},
                }
            })
        # Finally sync
        responses.append({
            "status": {
                "sync": {"status": "Synced", "revision": "main@sha256:final"},
                "health": {"status": "Healthy"},
            }
        })

        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            Mock(json=Mock(return_value=r), raise_for_status=Mock()) for r in responses
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
                progress_callback=progress_callback,
            )

        assert result.success is True
        # With 2-second throttle over ~5 seconds, expect ~3 updates (first, 2s, 4s)
        assert len(progress_updates) >= 2
        # Verify updates have increasing elapsed times
        elapsed_times = [u["elapsed_seconds"] for u in progress_updates]
        assert elapsed_times == sorted(elapsed_times), f"Elapsed times should be increasing: {elapsed_times}"

    @pytest.mark.asyncio
    async def test_progress_no_callback_no_error(self, mock_clusters_config, argocd_synced_response):
        """Execute succeeds without progress callback."""
        step = ArgoCDSyncStatusStep(
            timeout=60,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json.return_value = argocd_synced_response
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # No progress_callback provided
            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        assert result.success is True
        assert result.data["poll_count"] == 1


class TestArgoCDClusterConfigEdgeCases:
    """Test cluster configuration edge cases."""

    def test_get_argocd_endpoint_default_access_mode(self, tmp_path):
        """Default to read-only-proxy when access mode not specified."""
        clusters_content = """
clusters:
  test-cluster:
    argocd_api: https://argocd.example.com
    # No access mode specified
"""
        config_path = tmp_path / "clusters.yaml"
        config_path.write_text(clusters_content)

        step = ArgoCDSyncStatusStep(clusters_config_path=str(config_path))
        endpoint = step._get_argocd_endpoint("test-cluster")

        assert endpoint is not None
        assert endpoint["access"] == "read-only-proxy"  # Default

    def test_get_argocd_endpoint_empty_clusters(self, tmp_path):
        """Handle empty clusters section."""
        clusters_content = """
clusters: {}
"""
        config_path = tmp_path / "clusters.yaml"
        config_path.write_text(clusters_content)

        step = ArgoCDSyncStatusStep(clusters_config_path=str(config_path))
        endpoint = step._get_argocd_endpoint("any-cluster")

        assert endpoint is None

    def test_get_argocd_endpoint_no_argocd_api(self, tmp_path):
        """Handle cluster without argocd_api field."""
        clusters_content = """
clusters:
  no-api-cluster:
    access: read-only-proxy
    # Missing argocd_api
"""
        config_path = tmp_path / "clusters.yaml"
        config_path.write_text(clusters_content)

        step = ArgoCDSyncStatusStep(clusters_config_path=str(config_path))
        endpoint = step._get_argocd_endpoint("no-api-cluster")

        assert endpoint is None

    @pytest.mark.asyncio
    async def test_execute_yaml_parse_error(self, tmp_path):
        """Handle malformed YAML in clusters config."""
        # Create invalid YAML
        config_path = tmp_path / "clusters.yaml"
        config_path.write_text("invalid: yaml: content: [unclosed")

        step = ArgoCDSyncStatusStep(clusters_config_path=str(config_path))

        result = await step.execute(
            argocd_app="test-app",
            cluster="ardenone-cluster",
        )

        assert result.success is False
        assert "not found" in result.error.lower() or "Cluster" in result.error


class TestArgoCDTimeoutBehavior:
    """Test timeout handling behavior."""

    @pytest.mark.asyncio
    async def test_timeout_captures_final_status(self, mock_clusters_config):
        """Timeout result includes final application status."""
        step = ArgoCDSyncStatusStep(
            timeout=2,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        # Consistent out-of-sync response
        out_of_sync_response = {
            "status": {
                "sync": {"status": "OutOfSync", "revision": "main@sha256:def456"},
                "health": {"status": "Degraded"},
            }
        }

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.json = Mock(return_value=out_of_sync_response)
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        assert result.success is False
        assert result.data["status"] == "timeout"
        # Verify final status is captured
        assert result.data["final_sync_status"] == "OutOfSync"
        assert result.data["final_health_status"] == "Degraded"
        assert result.data["final_revision"] == "main@sha256:def456"
        # Verify error message includes status details
        assert "OutOfSync" in result.error
        assert "Degraded" in result.error
        assert "main@sha256:def456" in result.error

    @pytest.mark.asyncio
    async def test_timeout_final_query_failure(self, mock_clusters_config):
        """Handle failure of final status query after timeout."""
        step = ArgoCDSyncStatusStep(
            timeout=2,
            poll_interval=1,
            clusters_config_path=mock_clusters_config,
        )

        # First poll succeeds, final query fails
        out_of_sync_response = {
            "status": {
                "sync": {"status": "OutOfSync"},
                "health": {"status": "Progressing"},
            }
        }

        mock_client = AsyncMock()
        # First few polls succeed, then final query fails
        mock_client.get.side_effect = [
            Mock(json=Mock(return_value=out_of_sync_response), raise_for_status=Mock()),
            Mock(json=Mock(return_value=out_of_sync_response), raise_for_status=Mock()),
            httpx.HTTPError("Connection failed"),  # Final query fails
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await step.execute(
                argocd_app="test-app",
                cluster="ardenone-cluster",
            )

        assert result.success is False
        assert result.data["status"] == "timeout"
        # When final query fails, should show Unknown status
        assert result.data["final_sync_status"] == "Unknown"
        assert result.data["final_health_status"] == "Unknown"
        assert result.data["final_revision"] is None
