"""
Action executor - deterministic step runner for action workflows.

This module implements the Action Execution Model: a deterministic step runner
that interprets workflow steps from the project registry and executes them
through GitOps mutation patterns or read-only status checks.

Per the plan (docs/plan/plan.md → Action Execution Model):
- No LLM calls: execution is fully deterministic
- GitOps mutations: edits to declarative-config, committed and pushed
- Sync status polling: read-only ArgoCD API checks
- Progress streaming: each step outcome streams to canvas
- Failure handling: failed steps halt the workflow

Step vocabulary:
- ci_status: Check CI/workflow status (gates workflow if not green)
- image_tag: Resolve image tag/digest from CI
- gitops_commit: Templated declarative-config edit
- argocd_sync_status: Poll ArgoCD until Synced/Healthy
- pod_status: Post-sync pod verification
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from logging import getLogger
from pathlib import Path
from typing import Any, Optional

from ..registry import get_project
from ..sse.broadcaster import get_broadcaster, SSEEvent, EventType
from .models import ActionResult, ExecutionContext, StepResult, StepStatus


logger = getLogger(__name__)


class StepExecutor(ABC):
    """
    Abstract base class defining the contract for workflow step executors.

    This interface defines the contract that all concrete step implementations
    (bash, kubectl, git, ArgoCD, etc.) must follow. Each step executor is
    responsible for executing a single type of workflow step deterministically.

    ## Executor Contract

    All step executors MUST:
    1. Be deterministic - no LLM calls, no randomness
    2. Execute synchronously or async but complete within a timeout
    3. Return a StepResult with clear status (completed/failed)
    4. Handle errors gracefully and include error context in StepResult
    5. Respect the dry_run flag in ExecutionContext to skip mutations

    ## Execution Flow

    For each step execution:
    1. ActionExecutor calls validate() (if implemented) for pre-checks
    2. ActionExecutor calls execute(ctx) to run the step
    3. Executor returns StepResult with status and output/error
    4. ActionExecutor broadcasts result via SSE to canvas

    ## Step Types

    Mutating steps (respect dry_run):
    - gitops_commit: Templated declarative-config edits
    - image_update: Update image tags in manifests

    Read-only steps:
    - ci_status: Check CI/workflow status
    - argocd_sync_status: Poll ArgoCD sync status
    - pod_status: Get pod health via kubectl proxy
    - deployment_info: Get deployment/statefulset details

    ## Implementation Example

    ```python
    class PodStatusExecutor(StepExecutor):
        \"\"\"Executor for pod status checks.\"\"\"

        def validate(self, ctx: ExecutionContext) -> None:
            if not ctx.namespace:
                raise ValueError(\"namespace required in context\")

        async def execute(self, ctx: ExecutionContext) -> StepResult:
            start = time.time()
            result = StepResult(
                step_name=\"pod_status\",
                status=StepStatus.IN_PROGRESS,
                started_at=start,
            )

            try:
                # Execute step logic
                output = await self._get_pod_status(ctx)

                result.status = StepStatus.COMPLETED
                result.output = output
                result.completed_at = time.time()
                result.duration_ms = (result.completed_at - start) * 1000
            except Exception as e:
                result.status = StepStatus.FAILED
                result.error = str(e)
                result.completed_at = time.time()
                result.duration_ms = (result.completed_at - start) * 1000

            return result
    ```

    ## Required Methods

    - `execute(ctx: ExecutionContext) -> StepResult`: Main execution logic.
      MUST be implemented by all subclasses. Can be async or sync.

    ## Optional Methods

    - `validate(ctx: ExecutionContext) -> None`: Pre-execution validation.
      Raise ValueError if context is invalid. Called before execute().

    ## Helper Methods

    - `log_step_start(ctx, step_name)`: Log step execution start
    - `log_step_complete(ctx, step_name, duration_ms)`: Log successful completion
    - `log_step_error(ctx, step_name, error)`: Log step failure
    - `create_result(step_name, status, **kwargs)`: Factory for StepResult objects
    """

    @abstractmethod
    def execute(self, ctx: ExecutionContext) -> StepResult:
        """
        Execute the step with the given context.

        This is the main entry point for step execution. Implementations
        should:
        1. Perform the step's core logic (kubectl check, git operation, etc.)
        2. Handle any exceptions and convert to StepResult with FAILED status
        3. Return StepResult with appropriate status and output/error

        Args:
            ctx: ExecutionContext containing project config, cluster info,
                 intent/session IDs, and dry_run flag

        Returns:
            StepResult with execution outcome. Must include:
            - status: StepStatus (COMPLETED or FAILED)
            - output: dict with step-specific data on success
            - error: str with error message on failure
            - started_at, completed_at, duration_ms: timing metrics

        Raises:
            NotImplementedError: If subclass doesn't implement this method
            (Should be caught and converted to StepResult with FAILED status)
        """
        pass

    def validate(self, ctx: ExecutionContext) -> None:
        """
        Optional pre-execution validation hook.

        Implementations can override this to validate the ExecutionContext
        before execute() is called. Use this to check required fields
        (namespace, cluster, repo_path, etc.) are present and valid.

        Raise ValueError with a clear message if validation fails.
        The ActionExecutor will catch this and mark the step as FAILED.

        Args:
            ctx: ExecutionContext to validate

        Raises:
            ValueError: If context is invalid for this step type
        """
        pass  # Default: no validation

    def log_step_start(self, ctx: ExecutionContext, step_name: str) -> None:
        """Log step execution start."""
        logger.info(
            f"Starting step '{step_name}' "
            f"(project={ctx.project_slug}, intent={ctx.intent_id[:8]}, "
            f"dry_run={ctx.dry_run})"
        )

    def log_step_complete(
        self, ctx: ExecutionContext, step_name: str, duration_ms: float
    ) -> None:
        """Log successful step completion."""
        logger.info(
            f"Step '{step_name}' completed in {duration_ms:.0f}ms "
            f"(project={ctx.project_slug}, intent={ctx.intent_id[:8]})"
        )

    def log_step_error(
        self, ctx: ExecutionContext, step_name: str, error: Exception
    ) -> None:
        """Log step failure with error details."""
        logger.error(
            f"Step '{step_name}' failed: {error} "
            f"(project={ctx.project_slug}, intent={ctx.intent_id[:8]})",
            exc_info=error,
        )

    def create_result(
        self,
        step_name: str,
        status: StepStatus,
        started_at: Optional[float] = None,
        output: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> StepResult:
        """
        Factory method to create StepResult objects with defaults.

        Args:
            step_name: Name of the step
            status: StepStatus (PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED)
            started_at: Unix timestamp (defaults to current time)
            output: Output data dict (defaults to empty dict)
            error: Error message string (defaults to None)

        Returns:
            StepResult object with provided fields
        """
        if started_at is None:
            started_at = time.time()

        return StepResult(
            step_name=step_name,
            status=status,
            output=output or {},
            error=error,
            started_at=started_at,
        )


class ActionExecutor:
    """
    Deterministic step runner for action workflows.

    Interprets workflow steps from the project registry and executes them
    through GitOps mutation patterns or read-only status checks.

    All mutations execute as declarative-config GitOps edits (commit + push),
    never as direct kubectl mutations. Read-only checks use kubectl proxies
    and ArgoCD read-only APIs.
    """

    def __init__(self):
        self._step_executors = {
            # Mutating steps (respect dry_run)
            "ci_status": self._execute_ci_status,
            "image_tag": self._execute_image_tag,
            "gitops_commit": self._execute_gitops_commit,
            # Read-only steps
            "argocd_sync_status": self._execute_argocd_sync_status,
            "argocd_sync": self._execute_argocd_sync_status,  # Alias for argocd_sync_status
            "pod_status": self._execute_pod_status,
            "pod_logs": self._execute_pod_logs,
            "argocd_events": self._execute_argocd_events,
            "deployment_info": self._execute_deployment_info,
            "git_log": self._execute_git_log,
            "argocd_apps": self._execute_argocd_apps,
            "open_beads": self._execute_open_beads,
        }

    async def execute_workflow(
        self,
        intent_id: str,
        session_id: str,
        utterance: str,
        project_slug: str | None,
        workflow_name: str,
    ) -> ActionResult:
        """
        Execute an action workflow by running its steps sequentially.

        Args:
            intent_id: Intent ID for tracking
            session_id: Session ID for SSE targeting
            utterance: Original user utterance
            project_slug: Project slug for registry lookup
            workflow_name: Name of the workflow to execute

        Returns:
            ActionResult with all step results
        """
        logger.info(
            f"Executing workflow '{workflow_name}' for project '{project_slug}' "
            f"(intent {intent_id[:8]})"
        )

        # Initialize action result
        start_time = time.time()
        result = ActionResult(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            workflow_name=workflow_name,
            status="running",
            started_at=start_time,
        )

        # Get project configuration
        project_cfg = None
        if project_slug:
            project_cfg = get_project(project_slug)

        if not project_cfg:
            error_msg = f"Project '{project_slug}' not found in registry"
            logger.error(error_msg)
            result.status = "failed"
            result.error = error_msg
            result.completed_at = time.time()
            result.duration_ms = (result.completed_at - result.started_at) * 1000
            await self._broadcast_result(result, session_id)
            return result

        # Get workflow steps from registry
        workflows = project_cfg.get("workflows", {})
        workflow_config = workflows.get(workflow_name, {})
        steps = workflow_config.get("steps", [])

        if not steps:
            error_msg = f"Workflow '{workflow_name}' has no steps defined"
            logger.error(error_msg)
            result.status = "failed"
            result.error = error_msg
            result.completed_at = time.time()
            result.duration_ms = (result.completed_at - result.started_at) * 1000
            await self._broadcast_result(result, session_id)
            return result

        logger.info(f"Workflow '{workflow_name}' has {len(steps)} steps")

        # Broadcast workflow started
        await self._broadcast_workflow_started(result, session_id, utterance)

        # Execute each step sequentially
        for i, step_name in enumerate(steps):
            logger.info(f"Executing step {i+1}/{len(steps)}: {step_name}")

            # Broadcast workflow progress
            await self._broadcast_workflow_progress(
                result, session_id, current_step=i+1, total_steps=len(steps)
            )

            step_result = await self._execute_step(
                step_name=step_name,
                intent_id=intent_id,
                session_id=session_id,
                project_slug=project_slug,
                project_cfg=project_cfg,
                workflow_name=workflow_name,
            )

            result.add_step(step_result)

            # Broadcast step completion or failure
            if step_result.status == StepStatus.FAILED:
                await self._broadcast_step_failed(step_result, session_id)
            else:
                await self._broadcast_step_completed(step_result, session_id)

            # Check if step failed - halt workflow
            if step_result.status == StepStatus.FAILED:
                logger.error(f"Step '{step_name}' failed: {step_result.error}")
                result.status = "failed"
                result.error = f"Step '{step_name}' failed: {step_result.error}"
                result.completed_at = time.time()
                result.duration_ms = (result.completed_at - result.started_at) * 1000

                # Broadcast workflow failed
                await self._broadcast_result(result, session_id)
                return result

        # All steps completed successfully
        result.status = "completed"
        result.completed_at = time.time()
        result.duration_ms = (result.completed_at - result.started_at) * 1000

        logger.info(
            f"Workflow '{workflow_name}' completed in {result.duration_ms:.0f}ms"
        )

        # Broadcast workflow completed
        await self._broadcast_result(result, session_id)

        return result

    async def _execute_step(
        self,
        step_name: str,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> StepResult:
        """
        Execute a single workflow step.

        Args:
            step_name: Name of the step to execute
            intent_id: Intent ID for tracking
            session_id: Session ID for SSE targeting
            project_slug: Project slug
            project_cfg: Project configuration from registry
            workflow_name: Name of the workflow

        Returns:
            StepResult with execution outcome
        """
        step_start = time.time()
        step_result = StepResult(
            step_name=step_name,
            status=StepStatus.IN_PROGRESS,
            started_at=step_start,
        )

        # Broadcast step started
        await self._broadcast_step_started(step_result, session_id)

        try:
            # Get step executor
            executor = self._step_executors.get(step_name)

            if not executor:
                raise ValueError(f"Unknown step type: '{step_name}'")

            # Execute the step
            output = await executor(
                intent_id=intent_id,
                session_id=session_id,
                project_slug=project_slug,
                project_cfg=project_cfg,
                workflow_name=workflow_name,
            )

            step_result.status = StepStatus.COMPLETED
            step_result.output = output
            step_result.completed_at = time.time()
            step_result.duration_ms = (step_result.completed_at - step_start) * 1000

            logger.info(
                f"Step '{step_name}' completed in {step_result.duration_ms:.0f}ms"
            )

            # Broadcast step progress with final result
            await self._broadcast_step_progress(
                step_name=step_name,
                progress_data={
                    "status": "completed",
                    "duration_ms": step_result.duration_ms,
                    "output": output,
                },
                session_id=session_id,
            )

        except Exception as e:
            logger.exception(f"Step '{step_name}' failed with exception")
            step_result.status = StepStatus.FAILED
            step_result.error = str(e)
            step_result.completed_at = time.time()
            step_result.duration_ms = (step_result.completed_at - step_start) * 1000

            # Broadcast step progress with error
            await self._broadcast_step_progress(
                step_name=step_name,
                progress_data={
                    "status": "failed",
                    "error": str(e),
                    "duration_ms": step_result.duration_ms,
                },
                session_id=session_id,
            )

        return step_result

    async def _execute_ci_status(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """
        Execute ci_status step: check CI/workflow status.

        Gates the workflow if CI is not green.

        Returns:
            Dict with CI status information
        """
        # Import here to avoid circular dependency
        from .steps import execute_ci_status_step

        return await execute_ci_status_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_image_tag(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """
        Execute image_tag step: resolve image tag/digest from CI.

        Returns:
            Dict with image tag information
        """
        from .steps import execute_image_tag_step

        return await execute_image_tag_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_gitops_commit(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """
        Execute gitops_commit step: templated declarative-config edit.

        The executor itself authors the declarative-config edit (never LLM-authored),
        commits, and pushes. The edit is a templated field substitution only.

        Returns:
            Dict with commit information
        """
        from .steps import execute_gitops_commit_step

        return await execute_gitops_commit_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_argocd_sync_status(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """
        Execute argocd_sync_status step: poll ArgoCD until Synced/Healthy.

        Returns:
            Dict with sync status information
        """
        from .steps import execute_argocd_sync_status_step

        return await execute_argocd_sync_status_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_pod_status(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """
        Execute pod_status step: post-sync pod verification.

        Returns:
            Dict with pod status information
        """
        from .steps import execute_pod_status_step

        return await execute_pod_status_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_deployment_info(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """Execute deployment_info step (read-only)."""
        from .steps import execute_deployment_info_step

        return await execute_deployment_info_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_git_log(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """Execute git_log step (read-only)."""
        from .steps import execute_git_log_step

        return await execute_git_log_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_argocd_apps(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """Execute argocd_apps step (read-only)."""
        from .steps import execute_argocd_apps_step

        return await execute_argocd_apps_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_open_beads(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """Execute open_beads step (read-only)."""
        from .steps import execute_open_beads_step

        return await execute_open_beads_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_pod_logs(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """Execute pod_logs step: get recent pod logs."""
        from .steps import execute_pod_logs_step

        return await execute_pod_logs_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _execute_argocd_events(
        self,
        intent_id: str,
        session_id: str,
        project_slug: str | None,
        project_cfg: dict[str, Any],
        workflow_name: str,
    ) -> dict[str, Any]:
        """Execute argocd_events step: get recent ArgoCD events."""
        from .steps import execute_argocd_events_step

        return await execute_argocd_events_step(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            project_cfg=project_cfg,
        )

    async def _broadcast_workflow_started(
        self,
        result: ActionResult,
        session_id: str,
        utterance: str,
    ) -> None:
        """Broadcast workflow started event to canvas."""
        broadcaster = get_broadcaster()
        await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.ACTION_WORKFLOW_STARTED,
                data={
                    "intent_id": result.intent_id,
                    "session_id": session_id,
                    "project_slug": result.project_slug,
                    "workflow_name": result.workflow_name,
                    "utterance": utterance,
                    "started_at": result.started_at,
                },
                target_session_id=session_id,
            )
        )

    async def _broadcast_workflow_progress(
        self,
        result: ActionResult,
        session_id: str,
        current_step: int,
        total_steps: int,
    ) -> None:
        """Broadcast workflow progress event to canvas."""
        broadcaster = get_broadcaster()
        await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.ACTION_WORKFLOW_PROGRESS,
                data={
                    "intent_id": result.intent_id,
                    "workflow_name": result.workflow_name,
                    "current_step": current_step,
                    "total_steps": total_steps,
                    "progress_percent": int((current_step / total_steps) * 100),
                    "timestamp": time.time(),
                },
                target_session_id=session_id,
            )
        )

    async def _broadcast_step_started(
        self,
        step: StepResult,
        session_id: str,
    ) -> None:
        """Broadcast step started event to canvas."""
        broadcaster = get_broadcaster()
        await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.ACTION_STEP_STARTED,
                data={
                    "step_name": step.step_name,
                    "status": step.status.value,
                    "started_at": step.started_at,
                },
                target_session_id=session_id,
            )
        )

    async def _broadcast_step_progress(
        self,
        step_name: str,
        progress_data: dict[str, Any],
        session_id: str,
    ) -> None:
        """Broadcast step progress event with incremental updates."""
        broadcaster = get_broadcaster()
        await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.ACTION_STEP_PROGRESS,
                data={
                    "step_name": step_name,
                    "progress": progress_data,
                    "timestamp": time.time(),
                },
                target_session_id=session_id,
            )
        )

    async def _broadcast_step_failed(
        self,
        step: StepResult,
        session_id: str,
    ) -> None:
        """Broadcast step failed event to canvas."""
        broadcaster = get_broadcaster()
        await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.ACTION_STEP_FAILED,
                data=step.to_dict(),
                target_session_id=session_id,
            )
        )

    async def _broadcast_step_completed(
        self,
        step: StepResult,
        session_id: str,
    ) -> None:
        """Broadcast step completed event to canvas."""
        broadcaster = get_broadcaster()
        await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.ACTION_STEP_COMPLETED,
                data=step.to_dict(),
                target_session_id=session_id,
            )
        )

    async def _broadcast_result(
        self,
        result: ActionResult,
        session_id: str,
    ) -> None:
        """Broadcast final action result to canvas."""
        broadcaster = get_broadcaster()

        # Determine event type based on status
        if result.status == "completed":
            event_type = EventType.ACTION_WORKFLOW_COMPLETED
        elif result.status == "failed":
            event_type = EventType.ACTION_WORKFLOW_FAILED
        else:
            event_type = EventType.ACTION_WORKFLOW_CANCELLED

        await broadcaster.broadcast(
            SSEEvent(
                event_type=event_type,
                data=result.to_dict(),
                target_session_id=session_id,
            )
        )


# Global executor instance
_executor: ActionExecutor | None = None


def get_action_executor() -> ActionExecutor:
    """Get or create the global action executor instance."""
    global _executor
    if _executor is None:
        _executor = ActionExecutor()
    return _executor
