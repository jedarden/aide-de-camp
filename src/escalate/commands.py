"""
Command execution module for auto-approved actions.

Handles direct execution of auto-approved kubectl and git commands
without creating beads.
"""

import asyncio
import re
from logging import getLogger
from typing import Optional

from ..fetch.strand import KUBECTL_PROXIES


logger = getLogger(__name__)


class CommandExecutionError(Exception):
    """Command execution failed."""
    pass


class KubernetesCommandExecutor:
    """
    Executor for kubectl commands.

    Handles pod deletion and other kubectl operations that are
    auto-approved based on exceptions.yaml rules.
    """

    def __init__(self):
        self._proxies = KUBECTL_PROXIES

    def _resolve_cluster_proxy(self, project_slug: Optional[str]) -> str:
        """
        Resolve project slug to cluster proxy endpoint.

        Args:
            project_slug: Project identifier (e.g., 'options-pipeline')

        Returns:
            Proxy URL for kubectl access
        """
        # Project slug to cluster mapping
        # Based on CLAUDE.md cluster descriptions
        project_clusters = {
            "options-pipeline": "traefik-iad-options",
            "iad-options": "traefik-iad-options",
            "kalshi-tape": "traefik-iad-kalshi",
            "kalshi-weather": "traefik-iad-kalshi",
            "iad-kalshi": "traefik-iad-kalshi",
            "native-ads": "traefik-iad-native-ads-1",
            "iad-native-ads": "traefik-iad-native-ads-1",
            "aide-de-camp": "traefik-ardenone-manager",
            "ardenone-manager": "traefik-ardenone-manager",
            "declarative-config": "traefik-ardenone-manager",
        }

        if project_slug:
            cluster_host = project_clusters.get(project_slug)
            if cluster_host:
                # Check if this cluster has a proxy
                for cluster_name, proxy in self._proxies.items():
                    if cluster_host in proxy or cluster_host.endswith(f"-{cluster_name}"):
                        return proxy
                # Fallback: construct from cluster host
                return f"http://{cluster_host}:8001"

        # Default: ardenone-manager proxy
        return self._proxies.get("ardenone-manager", "http://traefik-ardenone-manager:8001")

    def _resolve_namespace(self, project_slug: Optional[str]) -> str:
        """
        Resolve project slug to kubernetes namespace.

        Args:
            project_slug: Project identifier

        Returns:
            Namespace name
        """
        # Project to namespace mapping
        # Most projects use the project slug with dashes removed
        if project_slug:
            # Remove dashes for namespace (e.g., options-pipeline -> optionspipeline)
            return project_slug.replace("-", "")

        # Default namespace
        return "default"

    def parse_delete_pod_utterance(
        self,
        utterance: str,
        project_slug: Optional[str] = None,
    ) -> dict:
        """
        Parse kubectl delete pod utterance to extract parameters.

        Args:
            utterance: User utterance (e.g., "kubectl delete pod my-pod-123")
            project_slug: Project context for namespace inference

        Returns:
            Dict with pod_name and namespace

        Raises:
            CommandExecutionError: If required parameters are missing
        """
        # Pattern: kubectl delete pod <pod-name> [-n <namespace>]
        pattern = r"kubectl\s+delete\s+pod\s+(\S+)(?:\s+-n\s+(\S+))?"
        match = re.search(pattern, utterance, re.IGNORECASE)

        if not match:
            raise CommandExecutionError(
                "Could not parse kubectl delete pod command. "
                "Expected format: kubectl delete pod <pod-name> [-n <namespace>]"
            )

        pod_name = match.group(1)
        namespace = match.group(2)

        # If no namespace specified, infer from project_slug
        if not namespace:
            namespace = self._resolve_namespace(project_slug)

        return {
            "pod_name": pod_name,
            "namespace": namespace,
        }

    async def execute_delete_pod(
        self,
        pod_name: str,
        namespace: str,
        cluster_proxy: Optional[str] = None,
        project_slug: Optional[str] = None,
    ) -> dict:
        """
        Execute kubectl delete pod command.

        Args:
            pod_name: Name of the pod to delete
            namespace: Kubernetes namespace
            cluster_proxy: Optional proxy URL (auto-resolved if not provided)
            project_slug: Project context for proxy resolution

        Returns:
            Execution result dict with status, message, and data
        """
        # Resolve proxy if not provided
        if not cluster_proxy:
            cluster_proxy = self._resolve_cluster_proxy(project_slug)

        logger.info(
            f"Deleting pod: {pod_name} in namespace: {namespace} "
            f"via proxy: {cluster_proxy}"
        )

        # Build kubectl command
        cmd = [
            "kubectl",
            "--server", cluster_proxy,
            "delete", "pod", pod_name,
            "-n", namespace,
        ]

        try:
            # Execute command
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                output = stdout.decode().strip()
                logger.info(f"Pod deleted successfully: {output}")

                return {
                    "status": "completed",
                    "summary": f"Deleted pod '{pod_name}' from namespace '{namespace}'",
                    "data": {
                        "action": "kubectl_delete_pod",
                        "pod_name": pod_name,
                        "namespace": namespace,
                        "cluster_proxy": cluster_proxy,
                        "output": output,
                    },
                    "urgency": "low",
                }
            else:
                error_msg = stderr.decode().strip()
                logger.error(f"Failed to delete pod: {error_msg}")

                return {
                    "status": "failed",
                    "summary": f"Failed to delete pod '{pod_name}': {error_msg}",
                    "data": {
                        "action": "kubectl_delete_pod",
                        "pod_name": pod_name,
                        "namespace": namespace,
                        "error": error_msg,
                    },
                    "urgency": "normal",
                }

        except FileNotFoundError:
            error = "kubectl command not found"
            logger.error(error)
            raise CommandExecutionError(error)

        except Exception as e:
            logger.error(f"Error executing kubectl delete pod: {e}")
            raise CommandExecutionError(f"Command execution failed: {e}")


# Global executor instance
_executor: Optional[KubernetesCommandExecutor] = None


def get_kubectl_executor() -> KubernetesCommandExecutor:
    """Get or create the global kubectl executor instance."""
    global _executor
    if _executor is None:
        _executor = KubernetesCommandExecutor()
    return _executor
