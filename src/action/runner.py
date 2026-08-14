"""
Action runner - workflow execution orchestrator.

This module provides the ActionRunner class that orchestrates workflow execution
by loading workflow definitions from the project registry and executing steps
sequentially through the ActionExecutor.

The ActionRunner provides a high-level interface for running workflows:
- Load workflow steps from project registry
- Execute steps sequentially through step executors
- Handle step failures (halt workflow on first failure)
- Return structured results with step outcomes

Per the plan (docs/plan/plan.md → Action Execution Model):
- No LLM calls: execution is fully deterministic
- GitOps mutations: edits to declarative-config, committed and pushed
- Sequential execution: steps run one at a time, not concurrently
- Failure handling: failed steps halt the workflow immediately
"""

import logging
import time
from typing import Any, Optional

from ..registry import get_project
from .executor import ActionExecutor
from .models import ActionResult, ExecutionContext, StepResult, StepStatus
from .registry import list_workflows


logger = logging.getLogger(__name__)


class ActionRunner:
    """
    Workflow execution orchestrator.

    Loads workflow definitions from the project registry and executes steps
    sequentially through the ActionExecutor. This class provides a high-level
    interface for running workflows with proper error handling and result tracking.

    ## Workflow Execution Flow

    1. Load project configuration from registry
    2. Get workflow definition (steps list) from project config
    3. Execute each step sequentially through ActionExecutor
    4. Halt on first step failure
    5. Return structured ActionResult with all step outcomes

    ## Step Executors

    The runner delegates step execution to ActionExecutor, which maintains
    a registry of step executor functions for each step type:
    - ci_status: Check CI/workflow status
    - image_tag: Resolve image tag/digest from CI
    - gitops_commit: Templated declarative-config edit
    - argocd_sync_status: Poll ArgoCD until Synced/Healthy
    - pod_status: Post-sync pod verification
    - deployment_info: Get deployment/statefulset information
    - git_log: Get recent git history
    - argocd_apps: Get ArgoCD application status
    - open_beads: Get open beads for project

    ## Example Usage

    ```python
    runner = ActionRunner()

    result = await runner.execute_workflow(
        intent_id="intent-123",
        session_id="session-456",
        utterance="Deploy my app",
        project_slug="my-app",
        workflow_name="deploy",
    )

    if result.status == "completed":
        print(f"Workflow completed in {result.duration_ms:.0f}ms")
        for step in result.steps:
            print(f"  {step.step_name}: {step.status.value}")
    else:
        print(f"Workflow failed: {result.error}")
    ```

    ## Error Handling

    The runner handles errors at multiple levels:
    - Project not found in registry → workflow fails immediately
    - Workflow not found → workflow fails immediately
    - Step execution fails → workflow halts, subsequent steps don't run
    - Individual step failures → captured in StepResult with error message

    All errors are captured in the ActionResult.error field for debugging
    and canvas display.
    """

    def __init__(self):
        """Initialize the ActionRunner with an ActionExecutor instance."""
        self._executor = ActionExecutor()

    async def execute_workflow(
        self,
        intent_id: str,
        session_id: str,
        utterance: str,
        project_slug: Optional[str],
        workflow_name: str,
    ) -> ActionResult:
        """
        Execute a workflow by loading steps from registry and running sequentially.

        This method loads the workflow definition from the project registry,
        executes each step in order, and returns a structured result with
        all step outcomes.

        Args:
            intent_id: Intent ID for tracking and SSE targeting
            session_id: Session ID for SSE targeting
            utterance: Original user utterance that triggered the workflow
            project_slug: Project slug for registry lookup (None = no project)
            workflow_name: Name of the workflow to execute

        Returns:
            ActionResult with workflow status, all step results, and error details
        """
        logger.info(
            f"ActionRunner executing workflow '{workflow_name}' "
            f"for project '{project_slug}' (intent {intent_id[:8]})"
        )

        # Delegate to ActionExecutor for execution
        result = await self._executor.execute_workflow(
            intent_id=intent_id,
            session_id=session_id,
            utterance=utterance,
            project_slug=project_slug,
            workflow_name=workflow_name,
        )

        return result

    async def load_workflow_steps(
        self,
        project_slug: str,
        workflow_name: str,
    ) -> list[str]:
        """
        Load workflow step names from project registry.

        This is a convenience method for inspecting workflow definitions
        without executing them. Useful for validation and UI display.

        Args:
            project_slug: Project slug for registry lookup
            workflow_name: Name of the workflow to load

        Returns:
            List of step names in execution order

        Raises:
            ValueError: If project or workflow not found
        """
        project_cfg = get_project(project_slug)

        if not project_cfg:
            raise ValueError(f"Project '{project_slug}' not found in registry")

        workflows = project_cfg.get("workflows", {})
        workflow_config = workflows.get(workflow_name, {})

        if not workflow_config:
            raise ValueError(
                f"Workflow '{workflow_name}' not found for project '{project_slug}'. "
                f"Available workflows: {', '.join(workflows.keys()) or '(none)'}"
            )

        steps = workflow_config.get("steps", [])

        logger.info(
            f"Loaded {len(steps)} steps for workflow '{workflow_name}' "
            f"in project '{project_slug}'"
        )

        return steps

    def list_available_steps(self) -> set[str]:
        """
        List all available step types that can be executed.

        Returns the set of step executor names registered in ActionExecutor.
        Useful for validation and UI display of supported step types.

        Returns:
            Set of step type names (e.g., {'ci_status', 'gitops_commit', ...})
        """
        return set(self._executor._step_executors.keys())


# Global runner instance
_runner: Optional[ActionRunner] = None


def get_action_runner() -> ActionRunner:
    """
    Get or create the global action runner instance.

    This provides a singleton pattern for the ActionRunner, ensuring
    all workflow executions use the same runner instance with the
    same step executor registry.

    Returns:
        The global ActionRunner instance
    """
    global _runner
    if _runner is None:
        _runner = ActionRunner()
        logger.debug("Created global ActionRunner instance")
    return _runner
