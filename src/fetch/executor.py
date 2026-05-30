"""
Fetch command executor.

Executes fetch commands (kubectl, git, argocd, etc.) for ambient monitoring
and context warming.
"""

import asyncio
import json
from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from pathlib import Path
from typing import Any, Optional
import subprocess


logger = getLogger(__name__)


class FetchType(Enum):
    """Types of fetch operations."""
    KUBECTL_STATUS = "kubectl_status"
    ARGOCD_STATUS = "argocd_status"
    GIT_LOG = "git_log"
    BEAD_LIST = "bead_list"
    CI_STATUS = "ci_status"
    POD_STATUS = "pod_status"
    DEPLOYMENT_STATUS = "deployment_status"


@dataclass
class FetchCommand:
    """A fetch command to execute."""
    fetch_type: FetchType
    project_slug: str
    args: list[str]
    timeout: int = 30


@dataclass
class FetchResult:
    """Result of a fetch operation."""
    fetch_type: FetchType
    project_slug: str
    success: bool
    data: dict[str, Any]
    error: Optional[str] = None
    duration_ms: int = 0


class FetchExecutor:
    """
    Executes fetch commands for monitoring and context warming.

    Supports:
    - kubectl commands (via proxy)
    - git log/status
    - ArgoCD app status
    - Bead list (via br CLI)
    - CI status (Argo Workflows)
    """

    def __init__(self):
        # kubectl proxy endpoints from CLAUDE.md
        self._kubectl_proxies = {
            "apexalgo-iad": "http://traefik-apexalgo-iad:8001",
            "ardenone-cluster": "http://traefik-ardenone-cluster:8001",
            "ardenone-hub": "http://traefik-ardenone-hub:8001",
            "ardenone-manager": "http://traefik-ardenone-manager:8001",
            "rs-manager": "http://traefik-rs-manager:8001",
            "ord-devimprint": "http://kubectl-proxy-ord-devimprint:8001",
            "iad-kalshi": "http://kubectl-proxy-iad-kalshi:8001",
            "iad-options": "http://traefik-iad-options:8001",
        }

        # Project to cluster mapping (simplified)
        self._project_clusters = {
            "options-pipeline": "iad-options",
            "ibkr-mcp": "ardenone-cluster",
            # Add more mappings as needed
        }

    async def execute(self, command: FetchCommand) -> FetchResult:
        """
        Execute a fetch command.

        Args:
            command: The fetch command to execute

        Returns:
            FetchResult with data or error
        """
        import time

        start = time.time()

        try:
            if command.fetch_type == FetchType.KUBECTL_STATUS:
                data = await self._fetch_kubectl_status(command.project_slug)
            elif command.fetch_type == FetchType.POD_STATUS:
                data = await self._fetch_pod_status(command.project_slug, command.args)
            elif command.fetch_type == FetchType.DEPLOYMENT_STATUS:
                data = await self._fetch_deployment_status(command.project_slug, command.args)
            elif command.fetch_type == FetchType.ARGOCD_STATUS:
                data = await self._fetch_argocd_status(command.project_slug)
            elif command.fetch_type == FetchType.GIT_LOG:
                data = await self._fetch_git_log(command.project_slug)
            elif command.fetch_type == FetchType.BEAD_LIST:
                data = await self._fetch_bead_list(command.project_slug)
            elif command.fetch_type == FetchType.CI_STATUS:
                data = await self._fetch_ci_status(command.project_slug)
            else:
                raise ValueError(f"Unknown fetch type: {command.fetch_type}")

            duration_ms = int((time.time() - start) * 1000)

            return FetchResult(
                fetch_type=command.fetch_type,
                project_slug=command.project_slug,
                success=True,
                data=data,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"Fetch error for {command.fetch_type}: {e}")

            return FetchResult(
                fetch_type=command.fetch_type,
                project_slug=command.project_slug,
                success=False,
                data={},
                error=str(e),
                duration_ms=duration_ms,
            )

    async def _fetch_kubectl_status(self, project_slug: str) -> dict:
        """Fetch general kubectl status for a project."""
        cluster = self._project_clusters.get(project_slug)
        if not cluster:
            return {"error": f"No cluster mapping for project: {project_slug}"}

        proxy = self._kubectl_proxies.get(cluster)
        if not proxy:
            return {"error": f"No proxy for cluster: {cluster}"}

        # Try to get namespace from project_slug
        namespace = project_slug.replace("-", "")

        # Use httpx to query kubectl proxy
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Get pods in namespace
                resp = await client.get(
                    f"{proxy}/api/v1/namespaces/{namespace}/pods"
                )
                resp.raise_for_status()
                pods_data = resp.json()

                # Extract relevant info
                pods = []
                for pod in pods_data.get("items", []):
                    pod_name = pod.get("metadata", {}).get("name", "")
                    phase = pod.get("status", {}).get("phase", "Unknown")
                    ready = self._get_pod_ready(pod)
                    restarts = sum(
                        c.get("restartCount", 0)
                        for c in pod.get("status", {}).get("containerStatuses", [])
                    )

                    pods.append({
                        "name": pod_name,
                        "phase": phase,
                        "ready": ready,
                        "restarts": restarts,
                    })

                return {
                    "cluster": cluster,
                    "namespace": namespace,
                    "pods": pods,
                    "pod_count": len(pods),
                    "healthy_count": sum(1 for p in pods if p["phase"] == "Running"),
                }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Namespace doesn't exist
                return {
                    "cluster": cluster,
                    "namespace": namespace,
                    "error": "Namespace not found",
                    "pods": [],
                }
            raise
        except Exception as e:
            return {
                "cluster": cluster,
                "namespace": namespace,
                "error": str(e),
                "pods": [],
            }

    async def _fetch_pod_status(self, project_slug: str, args: list[str]) -> dict:
        """Fetch detailed pod status."""
        # args might contain pod name
        pod_name = args[0] if args else None

        # Get general status and filter for specific pod
        status_data = await self._fetch_kubectl_status(project_slug)

        if pod_name:
            for pod in status_data.get("pods", []):
                if pod["name"] == pod_name:
                    return pod

            return {"error": f"Pod not found: {pod_name}"}

        return status_data

    async def _fetch_deployment_status(self, project_slug: str, args: list[str]) -> dict:
        """Fetch deployment status."""
        cluster = self._project_clusters.get(project_slug)
        if not cluster:
            return {"error": f"No cluster mapping for project: {project_slug}"}

        proxy = self._kubectl_proxies.get(cluster)
        if not proxy:
            return {"error": f"No proxy for cluster: {cluster}"}

        namespace = project_slug.replace("-")
        deployment_name = args[0] if args else f"{project_slug}"

        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{proxy}/apis/apps/v1/namespaces/{namespace}/deployments/{deployment_name}"
                )
                resp.raise_for_status()
                deploy_data = resp.json()

                # Extract deployment status
                status = deploy_data.get("status", {})
                spec = deploy_data.get("spec", {})

                return {
                    "name": deployment_name,
                    "namespace": namespace,
                    "replicas": spec.get("replicas", 0),
                    "ready_replicas": status.get("readyReplicas", 0),
                    "available_replicas": status.get("availableReplicas", 0),
                    "updated_replicas": status.get("updatedReplicas", 0),
                    "conditions": status.get("conditions", []),
                }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": f"Deployment not found: {deployment_name}"}
            raise

    async def _fetch_argocd_status(self, project_slug: str) -> dict:
        """Fetch ArgoCD application status."""
        # ArgoCD read-only API
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications",
                    params={"name": project_slug}
                )
                resp.raise_for_status()
                apps_data = resp.json()

                if not apps_data.get("items"):
                    return {"error": f"Application not found: {project_slug}"}

                app = apps_data["items"][0]
                status = app.get("status", {})
                operation = app.get("operation", {})

                return {
                    "name": project_slug,
                    "sync_status": status.get("sync", {}).get("status", "Unknown"),
                    "health_status": status.get("health", {}).get("status", "Unknown"),
                    "revision": status.get("sync", {}).get("revision", ""),
                    "operation": operation.get("operation", {}),
                    "created_at": status.get("operationState", {}).get("startedAt", ""),
                }

        except Exception as e:
            return {"error": f"ArgoCD fetch failed: {e}"}

    async def _fetch_git_log(self, project_slug: str) -> dict:
        """Fetch git log for a project."""
        # This would query git for the project
        # For now, return placeholder
        return {
            "project": project_slug,
            "commit_count": 0,
            "latest_commit": None,
            "latest_author": None,
            "error": "Not implemented",
        }

    async def _fetch_bead_list(self, project_slug: str) -> dict:
        """Fetch bead list for a project."""
        # This would call br CLI
        try:
            proc = await asyncio.create_subprocess_exec(
                "br",
                "list",
                f"--project={project_slug}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                # Parse br output (JSON format)
                try:
                    beads = json.loads(stdout.decode())
                    return {
                        "project": project_slug,
                        "beads": beads,
                        "count": len(beads),
                    }
                except json.JSONDecodeError:
                    return {
                        "project": project_slug,
                        "error": "Failed to parse br output",
                        "raw_output": stdout.decode(),
                    }
            else:
                return {
                    "project": project_slug,
                    "error": stderr.decode(),
                }

        except FileNotFoundError:
            return {
                "project": project_slug,
                "error": "br CLI not found",
            }
        except Exception as e:
            return {
                "project": project_slug,
                "error": str(e),
            }

    async def _fetch_ci_status(self, project_slug: str) -> dict:
        """Fetch CI status (Argo Workflows) for a project."""
        # This would query Argo Workflows on iad-ci
        import httpx

        try:
            # Use kubectl proxy to query workflows
            proxy = self._kubectl_proxies.get("iad-ci")
            if not proxy:
                return {"error": "No proxy for iad-ci cluster"}

            # Get recent workflows for this project
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{proxy}/api/v1/namespaces/argo-workflows/workflows",
                    params={"labelSelector": f"project={project_slug}"}
                )
                resp.raise_for_status()
                workflows_data = resp.json()

                workflows = []
                for wf in workflows_data.get("items", []):
                    workflows.append({
                        "name": wf.get("metadata", {}).get("name", ""),
                        "phase": wf.get("status", {}).get("phase", "Unknown"),
                        "started_at": wf.get("status", {}).get("startedAt", ""),
                        "finished_at": wf.get("status", {}).get("finishedAt", ""),
                        "message": wf.get("status", {}).get("message", ""),
                    })

                # Sort by started_at desc
                workflows.sort(key=lambda x: x.get("started_at", ""), reverse=True)

                return {
                    "project": project_slug,
                    "workflows": workflows[:10],  # Last 10
                    "count": len(workflows),
                }

        except Exception as e:
            return {
                "project": project_slug,
                "error": str(e),
            }

    def _get_pod_ready(self, pod_data: dict) -> str:
        """Get pod ready status (e.g., '1/1')."""
        container_statuses = pod_data.get("status", {}).get("containerStatuses", [])
        if not container_statuses:
            return "0/0"

        ready_count = sum(1 for cs in container_statuses if cs.get("ready", False))
        total_count = len(container_statuses)

        return f"{ready_count}/{total_count}"


# Global fetch executor instance
_executor: Optional[FetchExecutor] = None


def get_fetch_executor() -> FetchExecutor:
    """Get or create the global fetch executor instance."""
    global _executor
    if _executor is None:
        _executor = FetchExecutor()
    return _executor
