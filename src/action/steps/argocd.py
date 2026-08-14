"""
ArgoCD sync status polling step.

Polls the read-only ArgoCD API for application sync/health status until
the application reaches Synced/Healthy state or times out. Supports
progress streaming to canvas and cluster-specific endpoint resolution.

This is a read-only operation - it never performs ArgoCD mutations.
If sync is stuck, that escalates to a reviewed bead, not a forced sync.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import httpx
import yaml

logger = logging.getLogger(__name__)


class SyncStatus(str, Enum):
    """ArgoCD sync status values."""
    SYNCED = "Synced"
    UNKNOWN = "Unknown"
    OUT_OF_SYNC = "OutOfSync"
    IN_PROGRESS = "InProgress"


class HealthStatus(str, Enum):
    """ArgoCD health status values."""
    HEALTHY = "Healthy"
    UNKNOWN = "Unknown"
    PROGRESSING = "Progressing"
    DEGRADED = "Degraded"
    MISSING = "Missing"


@dataclass
class ArgoCDApplicationStatus:
    """ArgoCD application sync and health status."""
    sync_status: SyncStatus
    health_status: HealthStatus
    operation_state: dict[str, Any] | None = None
    operation_timestamp: str | None = None
    revision: str | None = None


@dataclass
class StepResult:
    """Standardized result from step execution."""
    success: bool
    data: dict[str, Any]
    error: str | None = None


class ArgoCDSyncStatusStep:
    """
    Poll ArgoCD API until application reaches Synced/Healthy or timeout.

    This step performs read-only polling of the ArgoCD API to monitor
    application sync and health status. It resolves the correct ArgoCD
    endpoint per cluster using config/clusters.yaml and handles both
    read-only-proxy and authenticated access modes.

    The step supports progress streaming to canvas via periodic SSE events
    with poll count and elapsed time.

    Returns:
        StepResult with final sync status, health status, operation timestamp,
        and duration information
    """

    def __init__(
        self,
        timeout: int = 300,
        poll_interval: int = 5,
        progress_throttle_seconds: int = 5,
        clusters_config_path: str = "/home/coding/aide-de-camp/config/clusters.yaml",
    ):
        """
        Initialize ArgoCD sync status step.

        Args:
            timeout: Maximum poll duration in seconds (default: 5 minutes)
            poll_interval: Seconds between polls (default: 5 seconds)
            progress_throttle_seconds: Minimum seconds between progress updates (default: 5)
            clusters_config_path: Path to clusters.yaml for endpoint resolution
        """
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.progress_throttle_seconds = progress_throttle_seconds
        self.clusters_config_path = Path(clusters_config_path)

        # Validate configuration
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")
        if poll_interval <= 0:
            raise ValueError(f"poll_interval must be positive, got {poll_interval}")
        if poll_interval >= timeout:
            raise ValueError(f"poll_interval ({poll_interval}) must be less than timeout ({timeout})")
        if progress_throttle_seconds <= 0:
            raise ValueError(f"progress_throttle_seconds must be positive, got {progress_throttle_seconds}")

    async def execute(
        self,
        argocd_app: str,
        cluster: str,
        progress_callback: Callable | None = None,
        **kwargs,
    ) -> StepResult:
        """
        Execute ArgoCD sync status polling.

        Args:
            argocd_app: ArgoCD application name
            cluster: Cluster name for endpoint resolution
            progress_callback: Optional async callback for progress updates
            **kwargs: Additional parameters (unused but kept for interface compatibility)

        Returns:
            StepResult with sync/health status information
        """
        logger.info(f"Executing argocd_sync_status step for app '{argocd_app}' on cluster '{cluster}'")

        # Resolve ArgoCD API endpoint for cluster
        endpoint_info = self._get_argocd_endpoint(cluster)
        if not endpoint_info:
            return StepResult(
                success=False,
                data={"application": argocd_app, "cluster": cluster},
                error=f"Cluster '{cluster}' not found in {self.clusters_config_path} or has no ArgoCD API configured",
            )

        argocd_api = endpoint_info["argocd_api"]
        access_mode = endpoint_info["access"]

        # Check if we can access this endpoint
        if access_mode != "read-only-proxy":
            return StepResult(
                success=False,
                data={"application": argocd_app, "cluster": cluster, "access_mode": access_mode},
                error=f"ArgoCD API for cluster '{cluster}' requires authentication (access mode: {access_mode}). "
                      f"Only 'read-only-proxy' access is supported by this step.",
            )

        logger.debug(f"Polling ArgoCD API: {argocd_api} (access: {access_mode})")

        # Poll for sync status
        start_time = time.time()
        poll_count = 0
        last_progress_time = 0.0

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                while (time.time() - start_time) < self.timeout:
                    poll_count += 1
                    elapsed = time.time() - start_time

                    try:
                        # Query ArgoCD API for application status
                        app_status = await self._query_application_status(
                            client, argocd_api, argocd_app
                        )

                        logger.debug(
                            f"Poll {poll_count}: sync={app_status.sync_status.value}, "
                            f"health={app_status.health_status.value}"
                        )

                        # Stream progress to canvas if callback provided (throttled)
                        # Always send first update, then throttle
                        should_send = last_progress_time == 0.0 or (elapsed - last_progress_time) >= self.progress_throttle_seconds
                        if progress_callback and should_send:
                            try:
                                await progress_callback({
                                    "poll_count": poll_count,
                                    "elapsed_seconds": round(elapsed, 1),
                                    "application": argocd_app,
                                    "cluster": cluster,
                                    "current_status": {
                                        "sync_status": app_status.sync_status.value,
                                        "health_status": app_status.health_status.value,
                                    }
                                })
                                last_progress_time = elapsed
                            except Exception as callback_error:
                                # Log but don't fail the step - progress updates are best-effort
                                logger.warning(f"Progress callback failed: {callback_error}")

                        # Check if application is Synced and Healthy
                        if (
                            app_status.sync_status == SyncStatus.SYNCED
                            and app_status.health_status == HealthStatus.HEALTHY
                        ):
                            logger.info(
                                f"Application '{argocd_app}' reached Synced/Healthy "
                                f"after {poll_count} polls ({round(elapsed, 1)}s)"
                            )
                            return StepResult(
                                success=True,
                                data={
                                    "status": "synced",
                                    "sync_status": app_status.sync_status.value,
                                    "health_status": app_status.health_status.value,
                                    "operation_timestamp": app_status.operation_timestamp,
                                    "revision": app_status.revision,
                                    "application": argocd_app,
                                    "cluster": cluster,
                                    "poll_count": poll_count,
                                    "duration_seconds": round(elapsed, 1),
                                },
                            )

                        # Unknown is a valid transient state during polling
                        # Continue polling until success or timeout
                        logger.debug(
                            f"Application status: sync={app_status.sync_status.value}, "
                            f"health={app_status.health_status.value} - waiting {self.poll_interval}s"
                        )
                        await asyncio.sleep(self.poll_interval)

                    except httpx.HTTPError as e:
                        logger.warning(f"ArgoCD poll {poll_count} failed: {e}, retrying...")
                        await asyncio.sleep(self.poll_interval)

                # Timeout exceeded - capture final status before timing out
                final_elapsed = time.time() - start_time

                # Query one last time to get the final status for the error message
                try:
                    final_status = await self._query_application_status(
                        client, argocd_api, argocd_app
                    )
                    final_sync_status = final_status.sync_status.value
                    final_health_status = final_status.health_status.value
                    final_revision = final_status.revision
                except Exception:
                    # If final query fails, use unknown status
                    final_sync_status = "Unknown"
                    final_health_status = "Unknown"
                    final_revision = None

                logger.warning(
                    f"ArgoCD sync polling timed out after {poll_count} polls "
                    f"({round(final_elapsed, 1)}s). Final status: "
                    f"sync={final_sync_status}, health={final_health_status}"
                )

                timeout_message = (
                    f"Sync did not complete within {self.timeout}s timeout. "
                    f"Final status: sync={final_sync_status}, health={final_health_status}"
                )
                if final_revision:
                    timeout_message += f", revision={final_revision}"

                return StepResult(
                    success=False,
                    data={
                        "status": "timeout",
                        "application": argocd_app,
                        "cluster": cluster,
                        "poll_count": poll_count,
                        "duration_seconds": round(final_elapsed, 1),
                        "timeout_seconds": self.timeout,
                        "final_sync_status": final_sync_status,
                        "final_health_status": final_health_status,
                        "final_revision": final_revision,
                    },
                    error=timeout_message,
                )

        except Exception as e:
            logger.error(f"Failed to poll ArgoCD sync status: {e}")
            return StepResult(
                success=False,
                data={"application": argocd_app, "cluster": cluster},
                error=f"Failed to poll ArgoCD sync status: {e}",
            )

    def _get_argocd_endpoint(self, cluster: str) -> dict[str, str] | None:
        """
        Resolve ArgoCD API endpoint for a cluster from clusters.yaml.

        Args:
            cluster: Cluster name

        Returns:
            Dict with 'argocd_api' and 'access' fields, or None if not found
        """
        if not self.clusters_config_path.exists():
            logger.error(f"Clusters config not found: {self.clusters_config_path}")
            return None

        try:
            with open(self.clusters_config_path) as f:
                cluster_config = yaml.safe_load(f)

            cluster_entry = cluster_config.get("clusters", {}).get(cluster)
            if not cluster_entry:
                logger.warning(f"Cluster '{cluster}' not found in clusters.yaml")
                return None

            argocd_api = cluster_entry.get("argocd_api")
            access = cluster_entry.get("access")

            if not argocd_api:
                logger.warning(f"Cluster '{cluster}' has no argocd_api configured")
                return None

            if not access:
                # Default to read-only-proxy for backward compatibility
                access = "read-only-proxy"
                logger.debug(f"Cluster '{cluster}' has no access mode specified, defaulting to read-only-proxy")

            return {
                "argocd_api": argocd_api,
                "access": access,
            }

        except Exception as e:
            logger.error(f"Failed to read clusters config: {e}")
            return None

    async def _query_application_status(
        self,
        client: httpx.AsyncClient,
        argocd_api: str,
        argocd_app: str,
    ) -> ArgoCDApplicationStatus:
        """
        Query ArgoCD API for application status.

        Args:
            client: httpx async client
            argocd_api: ArgoCD API base URL
            argocd_app: Application name

        Returns:
            ArgoCDApplicationStatus with current sync and health status

        Raises:
            httpx.HTTPError: If API request fails
        """
        url = f"{argocd_api}/api/v1/applications/{argocd_app}"
        response = await client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()

        app_data = response.json()

        # Extract sync status
        sync_data = app_data.get("status", {}).get("sync", {})
        sync_status_str = sync_data.get("status", "Unknown")
        try:
            sync_status = SyncStatus(sync_status_str)
        except ValueError:
            sync_status = SyncStatus.UNKNOWN
        revision = sync_data.get("revision")

        # Extract health status
        health_data = app_data.get("status", {}).get("health", {})
        health_status_str = health_data.get("status", "Unknown")
        try:
            health_status = HealthStatus(health_status_str)
        except ValueError:
            health_status = HealthStatus.UNKNOWN

        # Extract operation state
        operation_state = app_data.get("status", {}).get("operationState")
        operation_timestamp = None
        if operation_state:
            # Prefer finishedAt over startedAt for completed operations
            operation_timestamp = operation_state.get("finishedAt") or operation_state.get("startedAt")

        return ArgoCDApplicationStatus(
            sync_status=sync_status,
            health_status=health_status,
            operation_state=operation_state,
            operation_timestamp=operation_timestamp,
            revision=revision,
        )
