"""
Action workflow step implementations.

Each step is deterministic (no LLM calls) and executes through GitOps patterns
or read-only status checks. Steps follow the Action Execution Model from
docs/plan/plan.md → Action Execution Model.
"""

import asyncio
import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from .argocd import ArgoCDApplicationStatus, ArgoCDSyncStatusStep, HealthStatus, SyncStatus
from .gitops import GitOperationResult, GitOperationStatus, GitOpsCommitStep, StepResult
from .read import CIStatusStep, ImageTagStep, PodStatusStep

logger = logging.getLogger(__name__)

__all__ = [
    "CIStatusStep",
    "ImageTagStep",
    "PodStatusStep",
    "GitOpsCommitStep",
    "GitOperationResult",
    "GitOperationStatus",
    "StepResult",
    "ArgoCDSyncStatusStep",
    "SyncStatus",
    "HealthStatus",
    "ArgoCDApplicationStatus",
    "execute_ci_status_step",
    "execute_image_tag_step",
    "execute_pod_status_step",
    "execute_deployment_info_step",
    "execute_git_log_step",
    "execute_argocd_apps_step",
    "execute_open_beads_step",
    "execute_pod_logs_step",
    "execute_argocd_events_step",
]

def _required_text(config: dict[str, Any], key: str, project_slug: str | None) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Project '{project_slug}' has no {key} configured")
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("API response must contain an items list")
    items = payload["items"]
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("API response items must be objects")
    return items


def _pod_is_ready(pod: dict[str, Any]) -> bool:
    metadata = pod.get("metadata") or {}
    status = pod.get("status") or {}
    containers = status.get("containerStatuses") or []
    ready_conditions = [
        condition for condition in status.get("conditions", [])
        if condition.get("type") == "Ready"
    ]
    return (
        not metadata.get("deletionTimestamp")
        and status.get("phase") == "Running"
        and bool(containers)
        and all(container.get("ready") is True for container in containers)
        and all(condition.get("status") == "True" for condition in ready_conditions)
    )


async def execute_pod_status_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
    verify_ready: bool = False,
) -> dict[str, Any]:
    """
    Execute pod_status step: get pod status via kubectl proxy.

    Returns:
        Dict with pod status information
    """
    logger.info(f"Executing pod_status step for project '{project_slug}'")

    namespace = _required_text(project_cfg, "namespace", project_slug)
    cluster = _required_text(project_cfg, "cluster", project_slug)

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
            pods = _items(pod_data)

            # Extract key information
            running_pods = [p for p in pods if p.get("status", {}).get("phase") == "Running"]
            pending_pods = [p for p in pods if p.get("status", {}).get("phase") == "Pending"]
            failed_pods = [p for p in pods if p.get("status", {}).get("phase") == "Failed"]

            result = {
                "total_pods": len(pods),
                "running": len(running_pods),
                "pending": len(pending_pods),
                "failed": len(failed_pods),
                "pod_names": [p.get("metadata", {}).get("name") for p in pods],
                "namespace": namespace,
                "cluster": cluster,
            }

            if verify_ready:
                unhealthy = [
                    p.get("metadata", {}).get("name", "unknown")
                    for p in pods
                    if not _pod_is_ready(p)
                ]
                if not pods or unhealthy:
                    raise RuntimeError(
                        f"Post-sync pods are not ready: {', '.join(unhealthy) or 'no pods found'}"
                    )

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

    namespace = _required_text(project_cfg, "namespace", project_slug)
    cluster = _required_text(project_cfg, "cluster", project_slug)

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

            deployments = _items(deployments_data)
            statefulsets = _items(statefulsets_data)

            result = {
                "deployments": [
                    {
                        "name": d.get("metadata", {}).get("name"),
                        "replicas": d.get("spec", {}).get("replicas", 1),
                        "ready": d.get("status", {}).get("readyReplicas") or 0,
                        "updated": d.get("status", {}).get("updatedReplicas") or 0,
                    }
                    for d in deployments
                ],
                "statefulsets": [
                    {
                        "name": s.get("metadata", {}).get("name"),
                        "replicas": s.get("spec", {}).get("replicas", 1),
                        "ready": s.get("status", {}).get("readyReplicas") or 0,
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

    repo_path = _required_text(project_cfg, "repo_path", project_slug)
    if not Path(repo_path).is_dir():
        raise ValueError(f"Repository path '{repo_path}' does not exist")
    commit_count = _positive_int(project_cfg.get("commit_count", 10), "commit_count")

    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", f"-{commit_count}", "--oneline"],
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
    except OSError as e:
        raise RuntimeError(f"Failed to get git log: {e}") from e


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
    if cluster:
        from ...fetch.clusters import resolve_argocd_endpoint

        resolution = resolve_argocd_endpoint(cluster)
        if not resolution.satisfiable:
            raise ValueError(resolution.reason)
        argocd_base_url = resolution.argocd_api
    else:
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

            apps = _items(response.json())

            # Filter apps if project_slug is specified
            if project_slug:
                argocd_app_name = project_cfg.get("argocd_app") or project_slug
                apps = [a for a in apps if a.get("metadata", {}).get("name") == argocd_app_name]

            result = {
                "applications": [
                    {
                        "name": app.get("metadata", {}).get("name"),
                        "namespace": app.get("metadata", {}).get("namespace"),
                        "sync_status": app.get("status", {}).get("sync", {}).get("status"),
                        "health_status": app.get("status", {}).get("health", {}).get("status"),
                        "operation": app.get("status", {}).get("operationState", {}).get("operation"),
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
    if not repo_path and project_slug == "aide-de-camp":
        repo_path = str(Path(__file__).resolve().parents[3])
    if not isinstance(repo_path, str) or not repo_path.strip():
        raise ValueError(f"Project '{project_slug}' has no repo_path configured")
    if not Path(repo_path).is_dir():
        raise ValueError(f"Repository path '{repo_path}' does not exist")
    if not (Path(repo_path) / ".beads" / "config.json").is_file():
        raise ValueError(f"Repository path '{repo_path}' is not a bead-rs workspace")

    try:
        bead_binary = shutil.which("bead") or str(Path.home() / ".cargo" / "bin" / "bead")
        cmd = [bead_binary, "list", "--status", "open", "--json", "--limit", "999999"]

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            raise RuntimeError(f"bead list failed: {result.stderr}")

        try:
            beads = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid bead list output: {e}") from e

        beads_result = {
            "open_beads": beads,
            "count": len(beads),
            "repo_path": repo_path,
            "project_filter": None,
        }

        logger.info(f"Found {len(beads)} open beads")
        return beads_result

    except subprocess.TimeoutExpired:
        raise RuntimeError("bead list timed out")
    except OSError as e:
        raise RuntimeError(f"Failed to get open beads: {e}") from e


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

    from .read import CIStatusStep

    if not isinstance(project_slug, str) or not project_slug.strip():
        raise ValueError("ci_status requires a project slug")
    kubectl_config = project_cfg.get("kubectl_config", "/home/coding/.kube/iad-ci.kubeconfig")
    if not isinstance(kubectl_config, str) or not kubectl_config.strip():
        raise ValueError("kubectl_config must be a non-empty path")
    timeout = _positive_int(project_cfg.get("ci_timeout", 15), "ci_timeout")
    result = await CIStatusStep(kubectl_config=kubectl_config, timeout=timeout).execute(project_slug)
    if not result.success or result.data.get("status") != "success":
        raise RuntimeError(result.error or f"CI is not green: {result.data.get('status', 'unknown')}")
    return result.data


async def execute_image_tag_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
    ci_status_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute image_tag step: resolve image tag/digest from CI.

    Returns:
        Dict with image tag information
    """
    logger.info(f"Executing image_tag step for project '{project_slug}'")

    from .read import ImageTagStep
    from .read import StepResult as ReadStepResult

    if not ci_status_result or ci_status_result.get("status") != "success":
        raise ValueError("image_tag requires a successful preceding ci_status step")
    result = await ImageTagStep().execute(
        ci_status_result=ReadStepResult(success=True, data=ci_status_result),
        project_slug=project_slug,
        project_cfg=project_cfg,
    )
    if not result.success:
        raise RuntimeError(result.error or "Could not resolve image tag")
    return result.data


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


async def execute_pod_logs_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute pod_logs step: get recent pod logs.

    Returns:
        Dict with recent pod logs
    """
    logger.info(f"Executing pod_logs step for project '{project_slug}'")

    namespace = project_cfg.get("namespace")
    cluster = project_cfg.get("cluster")

    if not namespace:
        raise ValueError(f"Project '{project_slug}' has no namespace configured")

    proxy_url = _get_cluster_proxy(cluster)
    if not proxy_url:
        raise ValueError(f"Cluster '{cluster}' has no proxy configured")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get pods first to find pod names
            pods_response = await client.get(
                f"{proxy_url}/api/v1/namespaces/{namespace}/pods",
                headers={"Accept": "application/json"}
            )
            pods_response.raise_for_status()
            pods_data = pods_response.json()
            pods = pods_data.get("items", [])

            if not pods:
                return {
                    "logs": [],
                    "pod_count": 0,
                    "namespace": namespace,
                    "cluster": cluster,
                    "message": "No pods found in namespace",
                }

            # Get logs from the first few pods (limit to avoid overwhelming output)
            pod_logs = []
            max_pods = 3  # Limit to first 3 pods
            tail_lines = 50

            for pod in pods[:max_pods]:
                pod_name = pod.metadata.name
                try:
                    logs_response = await client.get(
                        f"{proxy_url}/api/v1/namespaces/{namespace}/pods/{pod_name}/log",
                        params={"tailLines": str(tail_lines)},
                        headers={"Accept": "text/plain"}
                    )
                    logs_response.raise_for_status()
                    logs = logs_response.text

                    pod_logs.append({
                        "pod_name": pod_name,
                        "logs": logs.split("\n")[-tail_lines:],  # Get last N lines
                        "line_count": len(logs.split("\n")),
                    })

                except httpx.HTTPError as e:
                    logger.warning(f"Failed to get logs for pod {pod_name}: {e}")
                    pod_logs.append({
                        "pod_name": pod_name,
                        "logs": [],
                        "error": str(e),
                    })

            return {
                "pod_logs": pod_logs,
                "pod_count": len(pod_logs),
                "namespace": namespace,
                "cluster": cluster,
            }

    except httpx.HTTPError as e:
        raise RuntimeError(f"Failed to get pod logs: {e}")


async def execute_argocd_events_step(
    intent_id: str,
    session_id: str,
    project_slug: str | None,
    project_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute argocd_events step: get recent ArgoCD events.

    Returns:
        Dict with recent ArgoCD events
    """
    logger.info(f"Executing argocd_events step for project '{project_slug}'")

    cluster = project_cfg.get("cluster")
    argocd_app = project_cfg.get("argocd_app", project_slug)

    argocd_base_url = _get_argocd_base_url()
    if not argocd_base_url:
        raise RuntimeError("ArgoCD base URL not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            # Get application details to find events
            response = await client.get(
                f"{argocd_base_url}/api/v1/applications/{argocd_app}",
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()

            app_data = response.json()

            # Extract recent events from application status
            # ArgoCD stores events in the status field
            events = []
            app_status = app_data.get("status", {})

            # Get operation state if available
            operation_state = app_status.get("operationState", {})
            if operation_state:
                events.append({
                    "type": "operation",
                    "phase": operation_state.get("phase"),
                    "message": operation_state.get("message", ""),
                    "started_at": operation_state.get("startedAt"),
                    "finished_at": operation_state.get("finishedAt"),
                })

            # Get sync status history
            sync_status = app_status.get("sync", {})
            if sync_status:
                events.append({
                    "type": "sync",
                    "status": sync_status.get("status"),
                    "revision": sync_status.get("revision"),
                    "synced_at": sync_status.get("startedAt"),
                })

            # Get health status
            health_status = app_status.get("health", {})
            if health_status:
                events.append({
                    "type": "health",
                    "status": health_status.get("status"),
                    "message": health_status.get("message", ""),
                })

            return {
                "events": events,
                "application": argocd_app,
                "cluster": cluster,
                "event_count": len(events),
            }

    except httpx.HTTPError as e:
        raise RuntimeError(f"Failed to get ArgoCD events: {e}")


def _get_cluster_proxy(cluster: str | None) -> str | None:
    """Get kubectl proxy URL for a cluster."""
    if not cluster:
        return None

    # Kubernetes proxy URLs live in the registry; clusters.yaml maps ArgoCD APIs.
    cluster_config_path = Path(__file__).resolve().parents[3] / "config" / "registry.yaml"

    if not cluster_config_path.exists():
        logger.warning("registry.yaml not found")
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
    registry_path = Path(__file__).resolve().parents[3] / "config" / "registry.yaml"

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
