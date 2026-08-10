"""
Action workflow step implementations.

Each step is deterministic (no LLM calls) and executes through GitOps patterns
or read-only status checks. Steps follow the Action Execution Model from
docs/plan/plan.md → Action Execution Model.
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


from .gitops import GitOperationResult, GitOperationStatus, GitOpsCommitStep, StepResult
from .read import CIStatusStep, ImageTagStep, PodStatusStep

__all__ = [
    "CIStatusStep",
    "ImageTagStep",
    "PodStatusStep",
    "GitOpsCommitStep",
    "GitOperationResult",
    "GitOperationStatus",
    "StepResult",
]

from ..models import ExecutionContext


async def execute_pod_status_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute pod_status step: get pod status via kubectl proxy.

    Returns:
        Dict with pod status information
    """
    logger.info(f"Executing pod_status step for project '{project_slug}'")

    namespace = project_cfg.get("namespace")
    cluster = project_cfg.get("cluster")

    if not namespace:
        raise ValueError(f"Project '{project_slug}' has no namespace configured")

    # Get kubectl proxy for cluster
    proxy_url = _get_cluster_proxy(cluster)
    if not proxy_url:
        raise ValueError(f"Cluster '{cluster}' has no proxy configured")

    # Execute kubectl get pods via proxy
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{proxy_url}/api/v1/namespaces/{namespace}/pods",
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()

            pod_data = response.json()
            pods = pod_data.get("items", [])

            # Extract key information
            running_pods = [p for p in pods if p.get("status", {}).get("phase") == "Running"]
            pending_pods = [p for p in pods if p.get("status", {}).get("phase") == "Pending"]
            failed_pods = [p for p in pods if p.get("status", {}).get("phase") == "Failed"]

            result = {
                "total_pods": len(pods),
                "running": len(running_pods),
                "pending": len(pending_pods),
                "failed": len(failed_pods),
                "pod_names": [p.metadata.name for p in pods],
                "namespace": namespace,
                "cluster": cluster,
            }

            logger.info(f"Pod status: {result['running']}/{result['total_pods']} running")
            return result

    except httpx.HTTPError as e:
        raise RuntimeError(f"Failed to get pod status: {e}")


async def execute_deployment_info_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute deployment_info step: get deployment/statefulset info.

    Returns:
        Dict with deployment information
    """
    logger.info(f"Executing deployment_info step for project '{project_slug}'")

    namespace = project_cfg.get("namespace")
    cluster = project_cfg.get("cluster")

    if not namespace:
        raise ValueError(f"Project '{project_slug}' has no namespace configured")

    proxy_url = _get_cluster_proxy(cluster)
    if not proxy_url:
        raise ValueError(f"Cluster '{cluster}' has no proxy configured")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try Deployments first
            deployments_response = await client.get(
                f"{proxy_url}/apis/apps/v1/namespaces/{namespace}/deployments",
                headers={"Accept": "application/json"}
            )
            deployments_response.raise_for_status()
            deployments_data = deployments_response.json()

            # Try StatefulSets
            statefulsets_response = await client.get(
                f"{proxy_url}/apis/apps/v1/namespaces/{namespace}/statefulsets",
                headers={"Accept": "application/json"}
            )
            statefulsets_response.raise_for_status()
            statefulsets_data = statefulsets_response.json()

            deployments = deployments_data.get("items", [])
            statefulsets = statefulsets_data.get("items", [])

            result = {
                "deployments": [
                    {
                        "name": d.metadata.name,
                        "replicas": d.spec.replicas,
                        "ready": d.status.readyReplicas or 0,
                        "updated": d.status.updatedReplicas or 0,
                    }
                    for d in deployments
                ],
                "statefulsets": [
                    {
                        "name": s.metadata.name,
                        "replicas": s.spec.replicas,
                        "ready": s.status.readyReplicas or 0,
                    }
                    for s in statefulsets
                ],
                "namespace": namespace,
                "cluster": cluster,
            }

            logger.info(f"Found {len(deployments)} deployments, {len(statefulsets)} statefulsets")
            return result

    except httpx.HTTPError as e:
        raise RuntimeError(f"Failed to get deployment info: {e}")


async def execute_git_log_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute git_log step: get recent git history.

    Returns:
        Dict with recent git commits
    """
    logger.info(f"Executing git_log step for project '{project_slug}'")

    repo_path = project_cfg.get("repo_path")

    if not repo_path:
        raise ValueError(f"Project '{project_slug}' has no repo_path configured")

    if not Path(repo_path).exists():
        raise RuntimeError(f"Repository path '{repo_path}' does not exist")

    try:
        # Get last 10 commits
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "-10", "--oneline"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            raise RuntimeError(f"git log failed: {result.stderr}")

        commits = [
            {"hash": line.split()[0], "message": " ".join(line.split()[1:])}
            for line in result.stdout.strip().split("\n")
            if line.strip()
        ]

        log_result = {
            "commits": commits,
            "count": len(commits),
            "repo_path": repo_path,
        }

        logger.info(f"Found {len(commits)} recent commits")
        return log_result

    except subprocess.TimeoutExpired:
        raise RuntimeError("git log timed out")
    except Exception as e:
        raise RuntimeError(f"Failed to get git log: {e}")


async def execute_argocd_apps_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute argocd_apps step: get ArgoCD application status.

    Returns:
        Dict with ArgoCD application information
    """
    logger.info(f"Executing argocd_apps step for project '{project_slug}'")

    cluster = project_cfg.get("cluster")

    # Get ArgoCD API endpoint from global config
    argocd_base_url = _get_argocd_base_url()

    if not argocd_base_url:
        raise RuntimeError("ArgoCD base URL not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            # Get all applications
            response = await client.get(
                f"{argocd_base_url}/api/v1/applications",
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()

            apps_data = response.json()
            apps = apps_data.get("items", [])

            # Filter apps if project_slug is specified
            if project_slug:
                argocd_app_name = project_cfg.get("argocd_app", project_slug)
                apps = [a for a in apps if a.metadata.name == argocd_app_name]

            result = {
                "applications": [
                    {
                        "name": app.metadata.name,
                        "namespace": app.metadata.namespace,
                        "sync_status": app.status.sync.status,
                        "health_status": app.status.health.status,
                        "operation": app.status.operationState and app.status.operationState.operation,
                    }
                    for app in apps
                ],
                "cluster": cluster,
            }

            logger.info(f"Found {len(apps)} ArgoCD applications")
            return result

    except httpx.HTTPError as e:
        raise RuntimeError(f"Failed to get ArgoCD applications: {e}")


async def execute_open_beads_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute open_beads step: get open beads for project.

    Returns:
        Dict with open bead information
    """
    logger.info(f"Executing open_beads step for project '{project_slug}'")

    repo_path = project_cfg.get("repo_path")

    if not repo_path:
        # Fall back to aide-de-camp workspace with project filter
        repo_path = "/home/coding/aide-de-camp"

    if not Path(repo_path).exists():
        raise RuntimeError(f"Repository path '{repo_path}' does not exist")

    try:
        # Build bf list command
        cmd = ["bf", "list", "--status", "open", "--format", "json"]

        # Add project filter if we're in aide-de-camp workspace
        if project_slug and repo_path == "/home/coding/aide-de-camp":
            cmd.extend(["--project", project_slug])

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            raise RuntimeError(f"bf list failed: {result.stderr}")

        try:
            beads = json.loads(result.stdout)
        except json.JSONDecodeError:
            beads = []

        beads_result = {
            "open_beads": beads,
            "count": len(beads),
            "repo_path": repo_path,
            "project_filter": project_slug,
        }

        logger.info(f"Found {len(beads)} open beads")
        return beads_result

    except subprocess.TimeoutExpired:
        raise RuntimeError("bf list timed out")
    except Exception as e:
        raise RuntimeError(f"Failed to get open beads: {e}")


async def execute_ci_status_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute ci_status step: check CI/workflow status.

    Gates the workflow if CI is not green.

    Returns:
        Dict with CI status information
    """
    logger.info(f"Executing ci_status step for project '{project_slug}'")

    cluster = project_cfg.get("cluster")

    # For now, check if there are recent CI workflows in iad-ci
    # This would need to be adapted based on actual CI setup
    try:
        kubectl_config = "/home/coding/.kube/iad-ci.kubeconfig"

        if not Path(kubectl_config).exists():
            logger.warning(f"Kubeconfig for iad-ci not found, skipping CI check")
            return {
                "status": "skipped",
                "reason": "CI cluster not accessible",
                "cluster": cluster,
            }

        # Get recent workflows
        result = subprocess.run(
            [
                "kubectl",
                "--kubeconfig", kubectl_config,
                "get", "workflows", "-n", "argo-workflows",
                "-l", f"project={project_slug}" if project_slug else "-l",
                "--sort-by=.metadata.creationTimestamp",
                "-o", "json",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            raise RuntimeError(f"kubectl get workflows failed: {result.stderr}")

        workflows_data = json.loads(result.stdout)
        workflows = workflows_data.get("items", [])

        # Get the most recent workflow
        recent_workflow = workflows[-1] if workflows else None

        if recent_workflow:
            phase = recent_workflow.get("status", {}).get("phase", "Unknown")
            status_result = {
                "status": "success" if phase == "Succeeded" else "failed",
                "phase": phase,
                "workflow_name": recent_workflow.get("metadata", {}).get("name"),
                "cluster": cluster,
            }

            if phase != "Succeeded":
                logger.warning(f"CI workflow {status_result['workflow_name']} phase: {phase}")

            return status_result
        else:
            return {
                "status": "no_workflows",
                "reason": "No CI workflows found",
                "cluster": cluster,
            }

    except subprocess.TimeoutExpired:
        raise RuntimeError("CI status check timed out")
    except Exception as e:
        raise RuntimeError(f"Failed to check CI status: {e}")


async def execute_image_tag_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute image_tag step: resolve image tag/digest from CI.

    Returns:
        Dict with image tag information
    """
    logger.info(f"Executing image_tag step for project '{project_slug}'")

    # This would need to be adapted based on actual CI setup
    # For now, return a placeholder
    return {
        "status": "not_implemented",
        "reason": "Image tag resolution needs CI-specific implementation",
        "project_slug": project_slug,
    }


async def execute_gitops_commit_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
    manifest_path: str | None = None,
    template_fields: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Execute gitops_commit step: templated declarative-config edit.

    The executor itself authors the declarative-config edit (never LLM-authored),
    commits, and pushes. The edit is a templated field substitution only.

    Args:
        intent_id: Intent identifier
        session_id: Session identifier
        project_slug: Project slug
        project_cfg: Project configuration with cluster/namespace info
        manifest_path: Path to manifest file within declarative-config
        template_fields: List of {path: str, value: str|int} dicts for substitution
        dry_run: If True, skip actual commit and push

    Returns:
        Serialized GitOperationResult with commit, branch, manifest, and status
    """
    logger.info(f"Executing gitops_commit step for project '{project_slug}'")

    # Initialize the GitOps commit step
    step = GitOpsCommitStep()

    # Execute the step
    result = await step.execute(
        manifest_path=manifest_path,
        template_fields=template_fields,
        project_cfg=project_cfg,
        dry_run=dry_run,
    )

    # Return the structured GitOperationResult at the executor boundary.
    return result.to_dict()


async def execute_argocd_sync_status_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute argocd_sync_status step: poll ArgoCD until Synced/Healthy.

    Returns:
        Dict with sync status information
    """
    logger.info(f"Executing argocd_sync_status step for project '{project_slug}'")

    cluster = project_cfg.get("cluster")
    argocd_app = project_cfg.get("argocd_app", project_slug)

    argocd_base_url = _get_argocd_base_url()

    if not argocd_base_url:
        raise RuntimeError("ArgoCD base URL not configured")

    # Poll for sync status with timeout
    timeout = 300  # 5 minutes
    poll_interval = 5  # 5 seconds
    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            while (time.time() - start_time) < timeout:
                try:
                    response = await client.get(
                        f"{argocd_base_url}/api/v1/applications/{argocd_app}",
                        headers={"Accept": "application/json"}
                    )
                    response.raise_for_status()

                    app_data = response.json()
                    sync_status = app_data.get("status", {}).get("sync", {}).get("status")
                    health_status = app_data.get("status", {}).get("health", {}).get("status")

                    logger.debug(f"ArgoCD sync status: {sync_status}, health: {health_status}")

                    if sync_status == "Synced" and health_status == "Healthy":
                        return {
                            "status": "synced",
                            "sync_status": sync_status,
                            "health_status": health_status,
                            "application": argocd_app,
                            "cluster": cluster,
                            "duration_seconds": time.time() - start_time,
                        }
                    elif sync_status == "Unknown" or health_status == "Unknown":
                        # App might not exist or be deleted
                        return {
                            "status": "unknown",
                            "sync_status": sync_status,
                            "health_status": health_status,
                            "application": argocd_app,
                            "cluster": cluster,
                        }

                    # Wait before next poll
                    await asyncio.sleep(poll_interval)

                except httpx.HTTPError as e:
                    logger.warning(f"ArgoCD poll failed: {e}, retrying...")
                    await asyncio.sleep(poll_interval)

            # Timeout exceeded
            return {
                "status": "timeout",
                "reason": "Sync did not complete within timeout",
                "application": argocd_app,
                "cluster": cluster,
                "timeout_seconds": timeout,
            }

    except Exception as e:
        raise RuntimeError(f"Failed to poll ArgoCD sync status: {e}")


def _get_cluster_proxy(cluster: str | None) -> str | None:
    """Get kubectl proxy URL for a cluster."""
    if not cluster:
        return None

    # Read cluster config
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


def _get_argocd_base_url() -> str | None:
    """Get ArgoCD base URL from config."""
    registry_path = Path("/home/coding/aide-de-camp/config/registry.yaml")

    if not registry_path.exists():
        logger.warning("registry.yaml not found")
        return None

    try:
        import yaml

        with open(registry_path) as f:
            registry = yaml.safe_load(f)

        return registry.get("argocd", {}).get("base_url")

    except Exception as e:
        logger.error(f"Failed to read ArgoCD config: {e}")
        return None
