"""
Read-only step implementations for CI/CD and cluster status checks.

These steps query external systems (Argo Workflows, kubectl proxy) without
mutating any state. Each step class encapsulates the logic for a specific
read operation following the Action Execution Model.
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Standardized result from step execution."""
    success: bool
    data: dict[str, Any]
    error: str | None = None


class CIStatusStep:
    """
    Query Argo Workflows API for latest workflow with project label.

    Returns workflow status, name, and timestamp. Handles timeout and error cases.
    """

    def __init__(
        self,
        kubectl_config: str = "/home/coding/.kube/iad-ci.kubeconfig",
        timeout: int = 15,
    ):
        """
        Initialize CI status step.

        Args:
            kubectl_config: Path to kubectl config for CI cluster
            timeout: Query timeout in seconds
        """
        self.kubectl_config = kubectl_config
        self.timeout = timeout
        self.cluster = "iad-ci"

    async def execute(
        self,
        project_slug: str | None,
        **kwargs,
    ) -> StepResult:
        """
        Execute CI status query for project.

        Args:
            project_slug: Project label to filter workflows

        Returns:
            StepResult with workflow status information
        """
        logger.info(f"Executing ci_status step for project '{project_slug}'")

        if not Path(self.kubectl_config).exists():
            return StepResult(
                success=False,
                data={
                    "status": "skipped",
                    "reason": "CI cluster not accessible",
                    "cluster": self.cluster,
                },
                error=f"Kubeconfig not found at {self.kubectl_config}",
            )

        try:
            # Build kubectl command to query workflows
            cmd = [
                "kubectl",
                "--kubeconfig", self.kubectl_config,
                "get", "workflows", "-n", "argo-workflows",
            ]

            # Add project label filter if provided
            if project_slug:
                cmd.extend(["-l", f"project={project_slug}"])

            cmd.extend([
                "--sort-by=.metadata.creationTimestamp",
                "-o", "json",
            ])

            # Execute kubectl command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                return StepResult(
                    success=False,
                    data={"cluster": self.cluster},
                    error=f"kubectl get workflows failed: {result.stderr}",
                )

            # Parse workflow data
            workflows_data = json.loads(result.stdout)
            workflows = workflows_data.get("items", [])

            # Get the most recent workflow (last in sorted list)
            recent_workflow = workflows[-1] if workflows else None

            if not recent_workflow:
                return StepResult(
                    success=True,
                    data={
                        "status": "no_workflows",
                        "reason": "No CI workflows found",
                        "cluster": self.cluster,
                        "project_slug": project_slug,
                    },
                )

            # Extract workflow information
            phase = recent_workflow.get("status", {}).get("phase", "Unknown")
            workflow_name = recent_workflow.get("metadata", {}).get("name", "unknown")
            created_at = recent_workflow.get("metadata", {}).get("creationTimestamp", "")
            message = recent_workflow.get("status", {}).get("message", "")

            # Map Argo workflow phases to simple status
            status_mapping = {
                "Succeeded": "success",
                "Failed": "failed",
                "Running": "running",
                "Pending": "pending",
                "Error": "error",
            }
            simple_status = status_mapping.get(phase, "unknown")

            return StepResult(
                success=True,
                data={
                    "status": simple_status,
                    "phase": phase,
                    "workflow_name": workflow_name,
                    "created_at": created_at,
                    "message": message,
                    "cluster": self.cluster,
                    "project_slug": project_slug,
                },
            )

        except subprocess.TimeoutExpired:
            return StepResult(
                success=False,
                data={"cluster": self.cluster},
                error="CI status check timed out",
            )
        except json.JSONDecodeError as e:
            return StepResult(
                success=False,
                data={"cluster": self.cluster},
                error=f"Failed to parse workflow data: {e}",
            )
        except Exception as e:
            return StepResult(
                success=False,
                data={"cluster": self.cluster},
                error=f"Failed to check CI status: {e}",
            )


class ImageTagStep:
    """
    Extract image tag/digest from CI workflow output.

    Never returns :latest — always a specific tag or digest.
    """

    def __init__(self):
        """Initialize image tag extraction step."""
        pass

    async def execute(
        self,
        ci_status_result: StepResult | None = None,
        **kwargs,
    ) -> StepResult:
        """
        Extract image tag from CI status result.

        Args:
            ci_status_result: Result from CIStatusStep execution

        Returns:
            StepResult with image tag and registry path
        """
        logger.info("Executing image_tag step")

        if ci_status_result is None or not ci_status_result.success:
            return StepResult(
                success=False,
                data={},
                error="CI status result not provided or failed",
            )

        # Extract image tag from workflow annotations or output
        # This implementation extracts from workflow labels if present
        workflow_data = ci_status_result.data

        # Try to extract image information from workflow metadata
        # In real implementation, this would parse workflow output/pod specs
        workflow_name = workflow_data.get("workflow_name", "")

        # Placeholder: extract tag from workflow name or metadata
        # Real implementation would query the workflow's output artifacts
        if "sha256:" in workflow_name:
            # Extract digest if present in name
            digest = workflow_name.split("sha256:")[-1].split("-")[0]
            tag = f"sha256:{digest}"
        else:
            # Default to extracting version from workflow metadata
            # This is simplified; real implementation would parse workflow YAML
            tag = workflow_name.split("-")[-1] if workflow_name else "unknown"

        # Validate we don't return :latest
        if tag == ":latest" or tag == "latest":
            return StepResult(
                success=False,
                data={"tag": tag},
                error="Refusing to return :latest tag",
            )

        # Build registry path (simplified)
        # Real implementation would use project config to build full path
        project_slug = workflow_data.get("project_slug", "unknown")
        registry_path = f"ronaldraygun/{project_slug}:{tag}"

        return StepResult(
            success=True,
            data={
                "tag": tag,
                "registry_path": registry_path,
                "digest": tag if tag.startswith("sha256:") else None,
                "project_slug": project_slug,
            },
        )


class PodStatusStep:
    """
    Query kubectl proxy for pod status in namespace.

    Returns pod names, phases, and ready counts. Handles proxy timeout and errors.
    """

    def __init__(
        self,
        proxy_url: str | None = None,
        timeout: float = 10.0,
    ):
        """
        Initialize pod status step.

        Args:
            proxy_url: Override kubectl proxy URL (auto-detected if None)
            timeout: HTTP request timeout in seconds
        """
        self.proxy_url = proxy_url
        self.timeout = timeout

    async def execute(
        self,
        namespace: str,
        cluster: str | None = None,
        **kwargs,
    ) -> StepResult:
        """
        Execute pod status query for namespace.

        Args:
            namespace: Kubernetes namespace to query
            cluster: Cluster name for proxy lookup

        Returns:
            StepResult with pod status information
        """
        logger.info(f"Executing pod_status step for namespace '{namespace}'")

        if not namespace:
            return StepResult(
                success=False,
                data={},
                error="Namespace is required",
            )

        # Get proxy URL if not overridden
        proxy_url = self.proxy_url or self._get_cluster_proxy(cluster)
        if not proxy_url:
            return StepResult(
                success=False,
                data={"namespace": namespace, "cluster": cluster},
                error=f"Cluster '{cluster}' has no proxy configured",
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(
                    f"{proxy_url}/api/v1/namespaces/{namespace}/pods",
                    headers={"Accept": "application/json"}
                )
                response.raise_for_status()

                pod_data = response.json()
                pods = pod_data.get("items", [])

                # Extract pod information
                pod_list = []
                phase_counts = {"Running": 0, "Pending": 0, "Failed": 0, "Succeeded": 0, "Unknown": 0}

                for pod in pods:
                    pod_name = pod.get("metadata", {}).get("name", "unknown")
                    phase = pod.get("status", {}).get("phase", "Unknown")

                    # Count ready containers
                    container_statuses = pod.get("status", {}).get("containerStatuses", [])
                    ready_count = sum(
                        1 for cs in container_statuses if cs.get("ready", False)
                    )
                    total_containers = len(container_statuses)

                    phase_counts[phase] = phase_counts.get(phase, 0) + 1

                    pod_list.append({
                        "name": pod_name,
                        "phase": phase,
                        "ready": ready_count,
                        "total": total_containers,
                        "ready_ratio": f"{ready_count}/{total_containers}",
                    })

                return StepResult(
                    success=True,
                    data={
                        "total_pods": len(pods),
                        "phase_counts": phase_counts,
                        "pods": pod_list,
                        "namespace": namespace,
                        "cluster": cluster,
                    },
                )

        except httpx.HTTPError as e:
            return StepResult(
                success=False,
                data={"namespace": namespace, "cluster": cluster},
                error=f"Failed to get pod status: {e}",
            )
        except Exception as e:
            return StepResult(
                success=False,
                data={"namespace": namespace, "cluster": cluster},
                error=f"Unexpected error: {e}",
            )

    def _get_cluster_proxy(self, cluster: str | None) -> str | None:
        """Get kubectl proxy URL for a cluster from config."""
        if not cluster:
            return None

        cluster_config_path = Path("/home/coding/aide-de-camp/config/clusters.yaml")

        if not cluster_config_path.exists():
            logger.warning("clusters.yaml not found")
            return None

        try:
            import yaml

            with open(cluster_config_path) as f:
                cluster_config = yaml.safe_load(f)

            cluster_entry = cluster_config.get("clusters", {}).get(cluster, {})
            return cluster_entry.get("proxy")

        except Exception as e:
            logger.error(f"Failed to read cluster config: {e}")
            return None
