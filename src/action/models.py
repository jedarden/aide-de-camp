"""
Action Execution Model - base Pydantic models for workflows and steps.

This module defines the core data structures for the Action Execution Model:
- Step: Base class for all workflow step types
- ExecutionContext: Context passed to all step executors (project, cluster, namespace)
- StepResult: Result of a single workflow step execution
- StepStatus: Status enumeration for workflow steps

These models are used by the ActionExecutor to interpret and execute workflow
definitions from the project registry.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class StepStatus(str, Enum):
    """Status of a workflow step execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionContext(BaseModel):
    """
    Context passed to all step executors.

    Contains project configuration and runtime context needed for step execution:
    - Project identification (slug, repo path)
    - Cluster configuration (cluster name, namespace)
    - Tracking identifiers (intent_id, session_id)
    - Execution flags (dry_run)
    """
    intent_id: str = Field(..., description="Intent ID for tracking and SSE targeting")
    session_id: str = Field(..., description="Session ID for SSE targeting")
    project_slug: Optional[str] = Field(None, description="Project slug for registry lookup")
    project_cfg: dict[str, Any] = Field(default_factory=dict, description="Project configuration from registry")
    dry_run: bool = Field(default=False, description="If True, skip mutating operations")

    # Cluster configuration (extracted from project_cfg for convenience)
    @property
    def cluster(self) -> Optional[str]:
        """Get cluster name from project configuration."""
        return self.project_cfg.get("cluster")

    @property
    def namespace(self) -> Optional[str]:
        """Get namespace from project configuration."""
        return self.project_cfg.get("namespace")

    @property
    def repo_path(self) -> Optional[str]:
        """Get repository path from project configuration."""
        return self.project_cfg.get("repo_path")

    @property
    def argocd_app(self) -> Optional[str]:
        """Get ArgoCD application name from project configuration."""
        return self.project_cfg.get("argocd_app")


class StepResult(BaseModel):
    """
    Result of a single workflow step execution.

    Contains the outcome of a step execution including status, output,
    error information, and timing metrics.
    """
    step_name: str = Field(..., description="Name of the step that was executed")
    status: StepStatus = Field(..., description="Execution status")
    output: dict[str, Any] = Field(default_factory=dict, description="Step output data")
    error: Optional[str] = Field(None, description="Error message if step failed")
    started_at: float = Field(..., description="Unix timestamp when step started")
    completed_at: Optional[float] = Field(None, description="Unix timestamp when step completed")
    duration_ms: float = Field(default=0.0, description="Step execution duration in milliseconds")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for SSE broadcasting."""
        return {
            "step_name": self.step_name,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }


class ActionResult(BaseModel):
    """
    Result of an action workflow execution.

    Contains the complete execution result for a workflow including all
    step results, timing information, and final status.
    """
    intent_id: str = Field(..., description="Intent ID for tracking")
    session_id: str = Field(..., description="Session ID for SSE targeting")
    project_slug: Optional[str] = Field(None, description="Project slug that was executed")
    workflow_name: str = Field(..., description="Name of the workflow that was executed")
    status: str = Field(..., description="Final workflow status: running, completed, failed, cancelled")
    steps: list[StepResult] = Field(default_factory=list, description="All step results in execution order")
    started_at: float = Field(..., description="Unix timestamp when workflow started")
    completed_at: Optional[float] = Field(None, description="Unix timestamp when workflow completed")
    duration_ms: float = Field(default=0.0, description="Workflow execution duration in milliseconds")
    error: Optional[str] = Field(None, description="Error message if workflow failed")

    def add_step(self, step: StepResult) -> None:
        """Add a step result to the action result."""
        self.steps.append(step)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for SSE broadcasting."""
        return {
            "intent_id": self.intent_id,
            "session_id": self.session_id,
            "project_slug": self.project_slug,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "steps": [step.to_dict() for step in self.steps],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class Step(BaseModel):
    """
    Base class for all workflow step types.

    A step represents a single unit of work in an action workflow.
    Concrete step types (e.g., CiStatusStep, GitOpsCommitStep) inherit
    from this base and implement execution logic.

    Step vocabulary:
    - ci_status: Check CI/workflow status (gates workflow if not green)
    - image_tag: Resolve image tag/digest from CI
    - gitops_commit: Templated declarative-config edit
    - argocd_sync_status: Poll ArgoCD until Synced/Healthy
    - pod_status: Post-sync pod verification

    Read-only steps (no mutation):
    - deployment_info: Get deployment/statefulset information
    - git_log: Get recent git history
    - argocd_apps: Get ArgoCD application status
    - open_beads: Get open beads for project
    """
    step_type: str = Field(..., description="Type of step (e.g., 'ci_status', 'gitops_commit')")
    description: Optional[str] = Field(None, description="Human-readable step description")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional step metadata")

    model_config = ConfigDict(use_enum_values=True)
