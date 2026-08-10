"""
Action Execution Model - deterministic step runner for action workflows.

This module provides the executor that interprets and runs workflow steps
defined in project registry entries. All actions execute through GitOps
mutation patterns (declarative-config edits) or read-only status checks.
"""

from .executor import ActionExecutor, StepExecutor, get_action_executor
from .models import (
    ActionResult,
    ExecutionContext,
    Step,
    StepResult,
    StepStatus,
)
from .registry import (
    get_workflow_definition,
    list_available_workflows,
    list_workflows,
    load_workflow_definition,
    reload_registry,
    validate_all_workflows,
    WorkflowValidationError,
)
from .steps import (
    execute_argocd_apps_step,
    execute_argocd_sync_status_step,
    execute_ci_status_step,
    execute_deployment_info_step,
    execute_git_log_step,
    execute_gitops_commit_step,
    execute_image_tag_step,
    execute_open_beads_step,
    execute_pod_status_step,
)

__all__ = [
    # Executor
    "ActionExecutor",
    "StepExecutor",
    "get_action_executor",
    # Models
    "ActionResult",
    "ExecutionContext",
    "Step",
    "StepResult",
    "StepStatus",
    # Registry
    "get_workflow_definition",
    "list_workflows",
    "list_available_workflows",
    "load_workflow_definition",
    "reload_registry",
    "validate_all_workflows",
    "WorkflowValidationError",
    # Step executors
    "execute_argocd_apps_step",
    "execute_argocd_sync_status_step",
    "execute_ci_status_step",
    "execute_deployment_info_step",
    "execute_git_log_step",
    "execute_gitops_commit_step",
    "execute_image_tag_step",
    "execute_open_beads_step",
    "execute_pod_status_step",
]

# Import-time validation: ensure all exported symbols are available
_imported_symbols = set(globals().keys()) - {"__all__", "_imported_symbols"}
_missing_symbols = set(__all__) - _imported_symbols
try:
    if _missing_symbols:
        raise ImportError(
            f"Action module is missing exported symbols: {_missing_symbols}. "
            "This indicates a circular import or missing dependency."
        )
finally:
    # Import validation owns these temporary names; even a failed validation
    # must not leave stale module globals for a later reload.
    globals().pop("_imported_symbols", None)
    globals().pop("_missing_symbols", None)
