"""
Fetch strand: concurrent data fetcher with streaming support.

Executes fetch commands concurrently, streams partial results, and tracks
coverage of which sources succeeded/failed.
"""

import asyncio
import time
from collections import defaultdict
from logging import getLogger
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from .commands import (
    FetchContext,
    FetchCoverage,
    FetchRequest,
    FetchResult,
    FetchSource,
    IntentType,
    get_fetch_commands,
    get_required_sources,
    SourceResult,
)


logger = getLogger(__name__)


# Cluster proxy mappings from CLAUDE.md
KUBECTL_PROXIES = {
    "apexalgo-iad": "http://traefik-apexalgo-iad:8001",
    "ardenone-cluster": "http://traefik-ardenone-cluster:8001",
    "ardenone-hub": "http://traefik-ardenone-hub:8001",
    "ardenone-manager": "http://traefik-ardenone-manager:8001",
    "rs-manager": "http://traefik-rs-manager:8001",
    "ord-devimprint": "http://kubectl-proxy-ord-devimprint:8001",
    "iad-kalshi": "http://kubectl-proxy-iad-kalshi:8001",
    "iad-options": "http://traefik-iad-options:8001",
    "iad-ci": "http://traefik-iad-ci:8001",
}

ARGOCD_RO_PROXY = "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444"


class FetchStrand:
    """
    Fetch strand: concurrent data fetcher with streaming support.

    Executes all fetch commands for an intent concurrently, streams partial
    results as they arrive, and provides comprehensive coverage tracking.
    """

    def __init__(self):
        self._source_executors = {
            FetchSource.KUBECTL_PODS: self._fetch_kubectl_pods,
            FetchSource.KUBECTL_DEPLOYMENTS: self._fetch_kubectl_deployments,
            FetchSource.KUBECTL_WORKFLOWS: self._fetch_kubectl_workflows,
            FetchSource.ARGOCD_APP: self._fetch_argocd_app,
            FetchSource.GIT_LOG: self._fetch_git_log,
            FetchSource.GIT_STATUS: self._fetch_git_status,
            FetchSource.BEAD_LIST: self._fetch_bead_list,
            FetchSource.BEAD_DETAILS: self._fetch_bead_details,
            FetchSource.CI_STATUS: self._fetch_ci_status,
            FetchSource.COMPONENTS: self._fetch_components,
            FetchSource.LOGS: self._fetch_logs,
            FetchSource.EVENTS: self._fetch_events,
            FetchSource.SESSION_STATE: self._fetch_session_state,
            FetchSource.TOPIC_CONTEXT: self._fetch_topic_context,
            FetchSource.REMINDERS: self._fetch_reminders,
        }

    async def fetch(
        self,
        request: FetchRequest,
        on_partial_result: Optional[Callable[[FetchSource, SourceResult], None]] = None,
    ) -> FetchResult:
        """
        Execute fetch request with optional streaming callback.

        Args:
            request: The fetch request to execute
            on_partial_result: Optional callback for streaming partial results

        Returns:
            FetchResult with coverage information
        """
        start_time = time.time()

        # Get fetch commands for this intent type
        command_specs = get_fetch_commands(request.intent_type)
        required_sources = get_required_sources(request.intent_type)

        logger.info(
            f"Fetching {len(command_specs)} sources for intent {request.intent_id} "
            f"(type: {request.intent_type.value})"
        )

        # Create tasks for concurrent execution
        tasks = []
        for spec in command_specs:
            task = asyncio.create_task(
                self._execute_source(spec, request.context),
                name=f"fetch_{spec.source.value}_{request.intent_id[:8]}",
            )
            tasks.append((spec.source, spec.required, spec.timeout_seconds, task))

        # Wait for all tasks to complete (with per-task timeout)
        sources = {}
        succeeded = []
        timed_out = []
        failed = []
        skipped = []
        caveats = []

        for source, required, timeout, task in tasks:
            try:
                result = await asyncio.wait_for(task, timeout=timeout)

                if on_partial_result:
                    # Stream partial result as it arrives
                    on_partial_result(source, result)

                sources[source] = result

                if result.status == "success":
                    succeeded.append(source)
                elif result.status == "timeout":
                    timed_out.append(source)
                    caveats.append(f"{source.value} timed out")
                elif result.status == "error":
                    failed.append(source)
                    if required:
                        caveats.append(f"Required source {source.value} failed: {result.error}")
                    else:
                        caveats.append(f"Optional source {source.value} failed: {result.error}")

            except asyncio.TimeoutError:
                logger.warning(f"Source {source.value} timed out after {timeout}s")
                sources[source] = SourceResult(
                    source=source,
                    status="timeout",
                    data={},
                    error=f"Timed out after {timeout}s",
                    duration_ms=int(timeout * 1000),
                )
                timed_out.append(source)
                if required:
                    caveats.append(f"Required source {source.value} timed out")

            except Exception as e:
                logger.error(f"Error fetching {source.value}: {e}", exc_info=True)
                sources[source] = SourceResult(
                    source=source,
                    status="error",
                    data={},
                    error=str(e),
                    duration_ms=0,
                )
                failed.append(source)
                if required:
                    caveats.append(f"Required source {source.value} crashed: {e}")

        # Build coverage report
        coverage = FetchCoverage(
            total_sources=len(command_specs),
            succeeded=succeeded,
            timed_out=timed_out,
            failed=failed,
            skipped=skipped,
        )

        total_duration_ms = int((time.time() - start_time) * 1000)

        result = FetchResult(
            intent_id=request.intent_id,
            intent_type=request.intent_type,
            sources=sources,
            coverage=coverage,
            total_duration_ms=total_duration_ms,
            caveats=caveats if caveats else None,
        )

        logger.info(
            f"Fetch complete for intent {request.intent_id}: "
            f"{len(succeeded)}/{coverage.total_sources} succeeded, "
            f"{len(timed_out)} timed out, {len(failed)} failed"
        )

        return result

    async def _execute_source(
        self,
        spec,
        context: FetchContext,
    ) -> SourceResult:
        """Execute a single fetch source."""
        executor = self._source_executors.get(spec.source)
        if not executor:
            return SourceResult(
                source=spec.source,
                status="error",
                data={},
                error=f"No executor for source {spec.source.value}",
                duration_ms=0,
            )

        start = time.time()
        try:
            data = await executor(context)
            duration_ms = int((time.time() - start) * 1000)

            return SourceResult(
                source=spec.source,
                status="success",
                data=data,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start) * 1000)
            return SourceResult(
                source=spec.source,
                status="timeout",
                data={},
                error=f"Timed out after {spec.timeout_seconds}s",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return SourceResult(
                source=spec.source,
                status="error",
                data={},
                error=str(e),
                duration_ms=duration_ms,
            )

    # Source executors

    async def _fetch_kubectl_pods(self, context: FetchContext) -> dict:
        """Fetch pod status from kubernetes."""
        proxy = context.proxy
        namespace = context.namespace

        if not namespace:
            # Try to derive from project_slug
            if context.project_slug:
                namespace = context.project_slug.replace("-", "")
            else:
                return {"error": "No namespace specified"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{proxy}/api/v1/namespaces/{namespace}/pods"
                )
                resp.raise_for_status()
                pods_data = resp.json()

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
                    "namespace": namespace,
                    "pods": pods,
                    "pod_count": len(pods),
                    "healthy_count": sum(1 for p in pods if p["phase"] == "Running"),
                }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {
                    "namespace": namespace,
                    "error": "Namespace not found",
                    "pods": [],
                }
            raise
        except Exception as e:
            return {"error": str(e), "pods": []}

    async def _fetch_kubectl_deployments(self, context: FetchContext) -> dict:
        """Fetch deployment status from kubernetes."""
        proxy = context.proxy
        namespace = context.namespace
        deployment = context.deployment or context.app_name

        if not namespace or not deployment:
            return {"error": "Missing namespace or deployment name"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{proxy}/apis/apps/v1/namespaces/{namespace}/deployments/{deployment}"
                )
                resp.raise_for_status()
                deploy_data = resp.json()

                status = deploy_data.get("status", {})
                spec = deploy_data.get("spec", {})

                return {
                    "name": deployment,
                    "namespace": namespace,
                    "replicas": spec.get("replicas", 0),
                    "ready_replicas": status.get("readyReplicas", 0),
                    "available_replicas": status.get("availableReplicas", 0),
                    "updated_replicas": status.get("updatedReplicas", 0),
                    "conditions": status.get("conditions", []),
                }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": f"Deployment not found: {deployment}"}
            raise

    async def _fetch_kubectl_workflows(self, context: FetchContext) -> dict:
        """Fetch Argo Workflow status from CI cluster."""
        proxy = KUBECTL_PROXIES.get("iad-ci", context.proxy)
        project_slug = context.project_slug

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{proxy}/api/v1/namespaces/argo-workflows/workflows",
                    params={"labelSelector": f"project={project_slug}"} if project_slug else None
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

                workflows.sort(key=lambda x: x.get("started_at", ""), reverse=True)

                return {
                    "project": project_slug,
                    "workflows": workflows[:10],
                    "count": len(workflows),
                }

        except Exception as e:
            return {"error": str(e), "workflows": []}

    async def _fetch_argocd_app(self, context: FetchContext) -> dict:
        """Fetch ArgoCD application status."""
        proxy = ARGOCD_RO_PROXY
        app_name = context.app_name or context.project_slug

        if not app_name:
            return {"error": "No application name specified"}

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                resp = await client.get(
                    f"{proxy}/api/v1/applications",
                    params={"name": app_name}
                )
                resp.raise_for_status()
                apps_data = resp.json()

                if not apps_data.get("items"):
                    return {"error": f"Application not found: {app_name}"}

                app = apps_data["items"][0]
                status = app.get("status", {})
                operation = app.get("operation", {})

                return {
                    "name": app_name,
                    "sync_status": status.get("sync", {}).get("status", "Unknown"),
                    "health_status": status.get("health", {}).get("status", "Unknown"),
                    "revision": status.get("sync", {}).get("revision", ""),
                    "operation": operation.get("operation", {}),
                    "created_at": status.get("operationState", {}).get("startedAt", ""),
                }

        except Exception as e:
            return {"error": str(e)}

    async def _fetch_git_log(self, context: FetchContext) -> dict:
        """Fetch git log for a project."""
        repo_path = context.repo_path
        if not repo_path or not Path(repo_path).exists():
            return {"error": "No valid repo path specified"}

        try:
            # Fetch commits with author and date
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C", repo_path,
                "log", "-10",
                "--pretty=format:%h|%s|%an|%ar",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return {"error": stderr.decode()}

            commits = []
            for line in stdout.decode().strip().split("\n"):
                if line:
                    parts = line.split("|", 3)
                    if len(parts) == 4:
                        commits.append({
                            "hash": parts[0],
                            "message": parts[1],
                            "author": parts[2],
                            "date": parts[3],
                        })

            # Get current branch
            branch_proc = await asyncio.create_subprocess_exec(
                "git",
                "-C", repo_path,
                "branch", "--show-current",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            branch_stdout, _ = await branch_proc.communicate()
            branch = branch_stdout.decode().strip()

            return {
                "repo": repo_path,
                "branch": branch,
                "commits": commits,
                "count": len(commits),
            }

        except Exception as e:
            return {"error": str(e), "commits": []}

    async def _fetch_git_status(self, context: FetchContext) -> dict:
        """Fetch git status for a project."""
        repo_path = context.repo_path
        if not repo_path or not Path(repo_path).exists():
            return {"error": "No valid repo path specified"}

        try:
            # Get status output
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C", repo_path,
                "status", "--short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return {"error": stderr.decode()}

            # Parse status output - format: XY filename
            changed_files = []
            for line in stdout.decode().strip().split("\n"):
                if line and len(line) >= 3:
                    status_code = line[:2]
                    filename = line[3:]
                    changed_files.append({
                        "status": status_code,
                        "file": filename,
                    })

            # Get current branch
            branch_proc = await asyncio.create_subprocess_exec(
                "git",
                "-C", repo_path,
                "branch", "--show-current",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            branch_stdout, _ = await branch_proc.communicate()
            branch = branch_stdout.decode().strip()

            # Get last commit
            log_proc = await asyncio.create_subprocess_exec(
                "git",
                "-C", repo_path,
                "log", "-1", "--oneline",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            log_stdout, _ = await log_proc.communicate()
            last_commit = log_stdout.decode().strip()

            return {
                "repo": repo_path,
                "branch": branch,
                "last_commit": last_commit,
                "changed_files": changed_files,
                "count": len(changed_files),
                "has_changes": len(changed_files) > 0,
            }

        except Exception as e:
            return {"error": str(e), "changed_files": []}

    async def _fetch_bead_list(self, context: FetchContext) -> dict:
        """Fetch bead list for a project."""
        project_slug = context.project_slug
        if not project_slug:
            return {"error": "No project slug specified"}

        try:
            proc = await asyncio.create_subprocess_exec(
                "br",
                "list",
                f"--project={project_slug}",
                "--status=open",
                "--output=json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                import json
                beads = json.loads(stdout.decode())
                return {
                    "project": project_slug,
                    "beads": beads,
                    "count": len(beads),
                }
            else:
                return {"error": stderr.decode()}

        except FileNotFoundError:
            return {"error": "br CLI not found"}
        except Exception as e:
            return {"error": str(e)}

    async def _fetch_bead_details(self, context: FetchContext) -> dict:
        """Fetch detailed bead information."""
        # Would fetch specific bead details
        return {"error": "Not implemented"}

    async def _fetch_ci_status(self, context: FetchContext) -> dict:
        """Fetch CI status - alias for workflows."""
        return await self._fetch_kubectl_workflows(context)

    async def _fetch_components(self, context: FetchContext) -> dict:
        """Fetch component list from components library."""
        # Would integrate with components library
        return {
            "project": context.project_slug,
            "components": [],
            "count": 0,
        }

    async def _fetch_logs(self, context: FetchContext) -> dict:
        """Fetch logs from a pod."""
        proxy = context.proxy
        namespace = context.namespace
        pod_name = context.pod_name

        if not namespace or not pod_name:
            return {"error": "Missing namespace or pod name"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{proxy}/api/v1/namespaces/{namespace}/pods/{pod_name}/log",
                    params={"tailLines": "100"}
                )
                resp.raise_for_status()

                return {
                    "pod": pod_name,
                    "namespace": namespace,
                    "logs": resp.text,
                    "line_count": len(resp.text.split("\n")),
                }

        except Exception as e:
            return {"error": str(e)}

    async def _fetch_events(self, context: FetchContext) -> dict:
        """Fetch events from a namespace."""
        proxy = context.proxy
        namespace = context.namespace

        if not namespace:
            return {"error": "No namespace specified"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{proxy}/api/v1/namespaces/{namespace}/events"
                )
                resp.raise_for_status()
                events_data = resp.json()

                events = []
                for event in events_data.get("items", []):
                    events.append({
                        "type": event.get("type", ""),
                        "reason": event.get("reason", ""),
                        "message": event.get("message", ""),
                        "first_seen": event.get("firstTimestamp", ""),
                        "last_seen": event.get("lastTimestamp", ""),
                        "involved_object": event.get("involvedObject", {}),
                    })

                return {
                    "namespace": namespace,
                    "events": events,
                    "count": len(events),
                }

        except Exception as e:
            return {"error": str(e), "events": []}

    async def _fetch_session_state(self, context: FetchContext) -> dict:
        """Fetch session state."""
        # Would fetch from session store
        return {
            "session_id": context.session_id,
            "state": "unknown",
        }

    async def _fetch_topic_context(self, context: FetchContext) -> dict:
        """Fetch topic context cache."""
        # Would fetch from topic context cache
        return {
            "topic_id": context.topic_id,
            "context": {},
        }

    async def _fetch_reminders(self, context: FetchContext) -> dict:
        """Fetch reminders for a session."""
        # Would fetch from reminders system
        return {
            "session_id": context.session_id,
            "reminders": [],
            "count": 0,
        }

    def _get_pod_ready(self, pod_data: dict) -> str:
        """Get pod ready status (e.g., '1/1')."""
        container_statuses = pod_data.get("status", {}).get("containerStatuses", [])
        if not container_statuses:
            return "0/0"

        ready_count = sum(1 for cs in container_statuses if cs.get("ready", False))
        total_count = len(container_statuses)

        return f"{ready_count}/{total_count}"


# Global fetch strand instance
_fetch_strand: Optional[FetchStrand] = None


def get_fetch_strand() -> FetchStrand:
    """Get or create the global fetch strand instance."""
    global _fetch_strand
    if _fetch_strand is None:
        _fetch_strand = FetchStrand()
    return _fetch_strand
