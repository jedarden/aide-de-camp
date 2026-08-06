"""
Unit tests for action execution model base types.

Tests the core Pydantic models used by the Action Execution Model:
- StepStatus: Status enumeration for workflow steps
- ExecutionContext: Context passed to all step executors
- StepResult: Result of a single workflow step execution
- ActionResult: Result of an action workflow execution
- Step: Base class for all workflow step types
"""

import time

import pytest

from src.action.models import (
    ActionResult,
    ExecutionContext,
    Step,
    StepResult,
    StepStatus,
)


class TestStepStatus:
    """Test StepStatus enumeration."""

    def test_status_values(self):
        """StepStatus has all expected status values."""
        assert StepStatus.PENDING == "pending"
        assert StepStatus.IN_PROGRESS == "in_progress"
        assert StepStatus.COMPLETED == "completed"
        assert StepStatus.FAILED == "failed"
        assert StepStatus.SKIPPED == "skipped"

    def test_status_is_string_enum(self):
        """StepStatus values are comparable as strings."""
        status = StepStatus.COMPLETED
        assert status == "completed"
        assert status.value == "completed"
        # Note: str(status) returns "StepStatus.COMPLETED" but status.value gives the string value


class TestExecutionContext:
    """Test ExecutionContext model."""

    def test_minimal_context(self):
        """Context can be created with required fields only."""
        ctx = ExecutionContext(
            intent_id="test-intent-123",
            session_id="test-session-456",
        )
        assert ctx.intent_id == "test-intent-123"
        assert ctx.session_id == "test-session-456"
        assert ctx.project_slug is None
        assert ctx.project_cfg == {}

    def test_full_context(self):
        """Context with all fields populated."""
        ctx = ExecutionContext(
            intent_id="intent-1",
            session_id="session-1",
            project_slug="my-app",
            project_cfg={
                "cluster": "test-cluster",
                "namespace": "test-ns",
                "repo_path": "/path/to/repo",
                "argocd_app": "my-app-prod",
            },
        )
        assert ctx.intent_id == "intent-1"
        assert ctx.session_id == "session-1"
        assert ctx.project_slug == "my-app"
        assert ctx.cluster == "test-cluster"
        assert ctx.namespace == "test-ns"
        assert ctx.repo_path == "/path/to/repo"
        assert ctx.argocd_app == "my-app-prod"

    def test_cluster_property(self):
        """cluster property extracts from project_cfg."""
        ctx = ExecutionContext(
            intent_id="i1",
            session_id="s1",
            project_cfg={"cluster": "prod-cluster"},
        )
        assert ctx.cluster == "prod-cluster"

    def test_cluster_property_missing(self):
        """cluster property returns None when not configured."""
        ctx = ExecutionContext(
            intent_id="i1",
            session_id="s1",
            project_cfg={},
        )
        assert ctx.cluster is None

    def test_namespace_property(self):
        """namespace property extracts from project_cfg."""
        ctx = ExecutionContext(
            intent_id="i1",
            session_id="s1",
            project_cfg={"namespace": "production"},
        )
        assert ctx.namespace == "production"

    def test_namespace_property_missing(self):
        """namespace property returns None when not configured."""
        ctx = ExecutionContext(
            intent_id="i1",
            session_id="s1",
            project_cfg={},
        )
        assert ctx.namespace is None

    def test_repo_path_property(self):
        """repo_path property extracts from project_cfg."""
        ctx = ExecutionContext(
            intent_id="i1",
            session_id="s1",
            project_cfg={"repo_path": "/home/coding/my-app"},
        )
        assert ctx.repo_path == "/home/coding/my-app"

    def test_argocd_app_property(self):
        """argocd_app property extracts from project_cfg."""
        ctx = ExecutionContext(
            intent_id="i1",
            session_id="s1",
            project_cfg={"argocd_app": "my-app-deployment"},
        )
        assert ctx.argocd_app == "my-app-deployment"

    def test_dry_run_default(self):
        """dry_run defaults to False."""
        ctx = ExecutionContext(
            intent_id="i1",
            session_id="s1",
        )
        assert ctx.dry_run is False

    def test_dry_run_explicit_true(self):
        """dry_run can be set to True."""
        ctx = ExecutionContext(
            intent_id="i1",
            session_id="s1",
            dry_run=True,
        )
        assert ctx.dry_run is True

    def test_dry_run_explicit_false(self):
        """dry_run can be explicitly set to False."""
        ctx = ExecutionContext(
            intent_id="i1",
            session_id="s1",
            dry_run=False,
        )
        assert ctx.dry_run is False


class TestStepResult:
    """Test StepResult model."""

    def test_minimal_result(self):
        """Result can be created with required fields only."""
        now = time.time()
        result = StepResult(
            step_name="test_step",
            status=StepStatus.COMPLETED,
            started_at=now,
        )
        assert result.step_name == "test_step"
        assert result.status == StepStatus.COMPLETED
        assert result.output == {}
        assert result.error is None
        assert result.started_at == now
        assert result.completed_at is None
        assert result.duration_ms == 0.0

    def test_full_result(self):
        """Result with all fields populated."""
        started = time.time() - 1.0  # 1 second ago
        completed = time.time()
        result = StepResult(
            step_name="deploy_step",
            status=StepStatus.FAILED,
            output={"deployed": False},
            error="Deployment failed",
            started_at=started,
            completed_at=completed,
            duration_ms=1000.0,
        )
        assert result.step_name == "deploy_step"
        assert result.status == StepStatus.FAILED
        assert result.output == {"deployed": False}
        assert result.error == "Deployment failed"
        assert result.started_at == started
        assert result.completed_at == completed
        assert result.duration_ms == 1000.0

    def test_to_dict(self):
        """to_dict converts result to dictionary for SSE."""
        now = time.time()
        result = StepResult(
            step_name="test_step",
            status=StepStatus.COMPLETED,
            output={"key": "value"},
            started_at=now,
            completed_at=now + 0.5,
            duration_ms=500.0,
        )
        data = result.to_dict()
        assert data["step_name"] == "test_step"
        assert data["status"] == "completed"
        assert data["output"] == {"key": "value"}
        assert data["error"] is None
        assert data["started_at"] == now
        assert data["completed_at"] == now + 0.5
        assert data["duration_ms"] == 500.0

    def test_status_enum_value_in_dict(self):
        """Status enum is converted to string value in to_dict."""
        result = StepResult(
            step_name="test",
            status=StepStatus.IN_PROGRESS,
            started_at=time.time(),
        )
        data = result.to_dict()
        assert data["status"] == "in_progress"
        assert isinstance(data["status"], str)


class TestActionResult:
    """Test ActionResult model."""

    def test_minimal_result(self):
        """Result can be created with required fields only."""
        now = time.time()
        result = ActionResult(
            intent_id="intent-1",
            session_id="session-1",
            workflow_name="deploy",
            status="running",
            started_at=now,
        )
        assert result.intent_id == "intent-1"
        assert result.session_id == "session-1"
        assert result.project_slug is None
        assert result.workflow_name == "deploy"
        assert result.status == "running"
        assert result.steps == []
        assert result.started_at == now
        assert result.completed_at is None
        assert result.duration_ms == 0.0
        assert result.error is None

    def test_full_result(self):
        """Result with all fields populated."""
        now = time.time()
        step = StepResult(
            step_name="step1",
            status=StepStatus.COMPLETED,
            started_at=now,
            completed_at=now + 0.5,
            duration_ms=500.0,
        )
        result = ActionResult(
            intent_id="intent-1",
            session_id="session-1",
            project_slug="my-app",
            workflow_name="deploy",
            status="completed",
            steps=[step],
            started_at=now,
            completed_at=now + 2.0,
            duration_ms=2000.0,
        )
        assert result.intent_id == "intent-1"
        assert result.session_id == "session-1"
        assert result.project_slug == "my-app"
        assert result.workflow_name == "deploy"
        assert result.status == "completed"
        assert len(result.steps) == 1
        assert result.started_at == now
        assert result.completed_at == now + 2.0
        assert result.duration_ms == 2000.0

    def test_add_step(self):
        """add_step appends a step result to the steps list."""
        result = ActionResult(
            intent_id="i1",
            session_id="s1",
            workflow_name="test",
            status="running",
            started_at=time.time(),
        )
        assert len(result.steps) == 0

        step1 = StepResult(
            step_name="step1",
            status=StepStatus.COMPLETED,
            started_at=time.time(),
        )
        result.add_step(step1)
        assert len(result.steps) == 1
        assert result.steps[0].step_name == "step1"

        step2 = StepResult(
            step_name="step2",
            status=StepStatus.FAILED,
            started_at=time.time(),
        )
        result.add_step(step2)
        assert len(result.steps) == 2
        assert result.steps[1].step_name == "step2"

    def test_to_dict(self):
        """to_dict converts result to dictionary for SSE."""
        now = time.time()
        step = StepResult(
            step_name="step1",
            status=StepStatus.COMPLETED,
            started_at=now,
            completed_at=now + 0.5,
            duration_ms=500.0,
        )
        result = ActionResult(
            intent_id="intent-1",
            session_id="session-1",
            project_slug="my-app",
            workflow_name="deploy",
            status="completed",
            steps=[step],
            started_at=now,
            completed_at=now + 2.0,
            duration_ms=2000.0,
        )
        data = result.to_dict()
        assert data["intent_id"] == "intent-1"
        assert data["session_id"] == "session-1"
        assert data["project_slug"] == "my-app"
        assert data["workflow_name"] == "deploy"
        assert data["status"] == "completed"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["step_name"] == "step1"
        assert data["started_at"] == now
        assert data["completed_at"] == now + 2.0
        assert data["duration_ms"] == 2000.0

    def test_to_dict_with_failed_step(self):
        """to_dict includes failed step information."""
        now = time.time()
        step = StepResult(
            step_name="failing_step",
            status=StepStatus.FAILED,
            error="Step failed",
            started_at=now,
            completed_at=now + 0.5,
            duration_ms=500.0,
        )
        result = ActionResult(
            intent_id="i1",
            session_id="s1",
            workflow_name="test",
            status="failed",
            steps=[step],
            error="Workflow failed",
            started_at=now,
            completed_at=now + 1.0,
            duration_ms=1000.0,
        )
        data = result.to_dict()
        assert data["status"] == "failed"
        assert data["error"] == "Workflow failed"
        assert data["steps"][0]["status"] == "failed"
        assert data["steps"][0]["error"] == "Step failed"


class TestStep:
    """Test Step base model."""

    def test_minimal_step(self):
        """Step can be created with required fields only."""
        step = Step(step_type="ci_status")
        assert step.step_type == "ci_status"
        assert step.description is None
        assert step.metadata == {}

    def test_full_step(self):
        """Step with all fields populated."""
        step = Step(
            step_type="gitops_commit",
            description="Update deployment image tag",
            metadata={"template": "deployment", "file": "deploy.yaml"},
        )
        assert step.step_type == "gitops_commit"
        assert step.description == "Update deployment image tag"
        assert step.metadata == {"template": "deployment", "file": "deploy.yaml"}

    def test_known_step_types(self):
        """All known step types from documentation are valid."""
        known_types = [
            "ci_status",
            "image_tag",
            "gitops_commit",
            "argocd_sync_status",
            "pod_status",
            "deployment_info",
            "git_log",
            "argocd_apps",
            "open_beads",
        ]
        for step_type in known_types:
            step = Step(step_type=step_type)
            assert step.step_type == step_type

    def test_step_type_is_required(self):
        """step_type is a required field."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            Step()

    def test_metadata_defaults_to_empty_dict(self):
        """metadata defaults to empty dict, not None."""
        step = Step(step_type="test")
        assert step.metadata == {}
        assert isinstance(step.metadata, dict)

    def test_metadata_can_store_arbitrary_data(self):
        """metadata can store any JSON-serializable data."""
        step = Step(
            step_type="test",
            metadata={
                "timeout": 30,
                "retry_count": 3,
                "cluster": "prod",
                "tags": ["critical", "production"],
            },
        )
        assert step.metadata["timeout"] == 30
        assert step.metadata["retry_count"] == 3
        assert step.metadata["cluster"] == "prod"
        assert step.metadata["tags"] == ["critical", "production"]

    def test_description_is_optional(self):
        """description can be None if not provided."""
        step = Step(step_type="test")
        assert step.description is None

    def test_description_can_be_set(self):
        """description can be set for human-readable context."""
        step = Step(
            step_type="ci_status",
            description="Verify CI workflow succeeded before proceeding",
        )
        assert step.description == "Verify CI workflow succeeded before proceeding"
