"""
Unit tests for action runner workflow execution logic.

Tests the core workflow execution engine that:
- Loads workflow steps from the project registry
- Executes steps sequentially through step executors
- Handles step failures (halts workflow on first failure)
- Returns structured results with step outcomes

Tests use mocked step executors to verify execution logic without
requiring live clusters or external dependencies.
"""

import time
from unittest.mock import AsyncMock, Mock, patch
from unittest.mock import MagicMock

import pytest

from src.action.models import (
    ActionResult,
    ExecutionContext,
    StepResult,
    StepStatus,
)
from src.action.executor import ActionExecutor
from src.action.registry import WorkflowValidationError


class TestActionRunnerWorkflowExecution:
    """Test ActionRunner workflow execution logic with mocked steps."""

    @pytest.fixture
    def mock_project_config(self):
        """Create a mock project configuration with workflows."""
        return {
            "cluster": "test-cluster",
            "namespace": "test-namespace",
            "repo_path": "/tmp/test-repo",
            "argocd_app": "test-app",
            "workflows": {
                "test_workflow": {
                    "description": "Test workflow with 3 steps",
                    "steps": ["step1", "step2", "step3"],
                },
                "failing_workflow": {
                    "description": "Workflow with failing step",
                    "steps": ["step1", "failing_step", "step3"],
                },
            },
        }

    @pytest.fixture
    def mock_registry(self, mock_project_config):
        """Create a mock registry with test project."""
        return {
            "projects": {
                "test-project": mock_project_config,
            },
        }

    @pytest.fixture
    def executor(self):
        """Create an ActionExecutor instance for testing."""
        return ActionExecutor()

    @pytest.fixture
    def execution_context(self):
        """Create a test execution context."""
        return ExecutionContext(
            intent_id="test-intent-123",
            session_id="test-session-456",
            project_slug="test-project",
            project_cfg={
                "cluster": "test-cluster",
                "namespace": "test-namespace",
            },
        )

    @pytest.mark.asyncio
    async def test_execute_workflow_with_three_steps(
        self, executor, mock_project_config
    ):
        """Test executing a workflow with 3 steps runs in order."""
        # Track execution order
        execution_order = []

        # Create mock step executors that track execution order
        async def mock_step1(*args, **kwargs):
            execution_order.append("step1")
            return {"status": "step1_complete"}

        async def mock_step2(*args, **kwargs):
            execution_order.append("step2")
            return {"status": "step2_complete"}

        async def mock_step3(*args, **kwargs):
            execution_order.append("step3")
            return {"status": "step3_complete"}

        # Mock the step executors
        executor._step_executors = {
            "step1": mock_step1,
            "step2": mock_step2,
            "step3": mock_step3,
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute workflow
                            result = await executor.execute_workflow(
                                intent_id="test-intent",
                                session_id="test-session",
                                utterance="test utterance",
                                project_slug="test-project",
                                workflow_name="test_workflow",
                            )

                            # Verify execution order
                            assert execution_order == ["step1", "step2", "step3"]

                            # Verify result structure
                            assert result.status == "completed"
                            assert result.workflow_name == "test_workflow"
                            assert len(result.steps) == 3
                            assert result.intent_id == "test-intent"
                            assert result.session_id == "test-session"
                            assert result.project_slug == "test-project"

                            # Verify all steps completed successfully
                            for step in result.steps:
                                assert step.status == StepStatus.COMPLETED
                                assert step.error is None

    @pytest.mark.asyncio
    async def test_workflow_halt_on_first_failure(
        self, executor, mock_project_config
    ):
        """Test that workflow halts on first step failure."""
        execution_order = []

        async def mock_step1(*args, **kwargs):
            execution_order.append("step1")
            return {"status": "step1_complete"}

        async def failing_step(*args, **kwargs):
            execution_order.append("failing_step")
            raise ValueError("Step execution failed")

        async def mock_step3(*args, **kwargs):
            # This should NOT execute
            execution_order.append("step3")
            return {"status": "step3_complete"}

        # Mock the step executors
        executor._step_executors = {
            "step1": mock_step1,
            "failing_step": failing_step,
            "step3": mock_step3,
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute workflow that should fail
                            result = await executor.execute_workflow(
                                intent_id="test-intent",
                                session_id="test-session",
                                utterance="test utterance",
                                project_slug="test-project",
                                workflow_name="failing_workflow",
                            )

                            # Verify execution stopped at failure
                            assert execution_order == ["step1", "failing_step"]
                            assert "step3" not in execution_order

                            # Verify workflow failed
                            assert result.status == "failed"
                            assert result.error is not None
                            assert "failing_step" in result.error

                            # Verify first step completed, second failed
                            assert result.steps[0].status == StepStatus.COMPLETED
                            assert result.steps[1].status == StepStatus.FAILED
                            assert result.steps[1].error is not None

    @pytest.mark.asyncio
    async def test_workflow_result_contains_step_outcomes(
        self, executor, mock_project_config
    ):
        """Test that workflow result contains structured step outcomes."""
        step_outputs = {
            "step1": {"output": "result1", "value": 100},
            "step2": {"output": "result2", "value": 200},
            "step3": {"output": "result3", "value": 300},
        }

        async def mock_step1(*args, **kwargs):
            return step_outputs["step1"]

        async def mock_step2(*args, **kwargs):
            return step_outputs["step2"]

        async def mock_step3(*args, **kwargs):
            return step_outputs["step3"]

        # Mock the step executors
        executor._step_executors = {
            "step1": mock_step1,
            "step2": mock_step2,
            "step3": mock_step3,
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute workflow
                            result = await executor.execute_workflow(
                                intent_id="test-intent",
                                session_id="test-session",
                                utterance="test utterance",
                                project_slug="test-project",
                                workflow_name="test_workflow",
                            )

                            # Verify each step result contains correct output
                            for i, step in enumerate(result.steps):
                                expected_output = step_outputs[f"step{i+1}"]
                                assert step.output == expected_output
                                assert step.status == StepStatus.COMPLETED

                            # Verify result contains timing information
                            assert result.started_at > 0
                            assert result.completed_at > result.started_at
                            assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_workflow_with_unknown_step_type(
        self, executor, mock_project_config
    ):
        """Test that unknown step types cause workflow failure."""
        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute workflow with unknown step
                            result = await executor.execute_workflow(
                                intent_id="test-intent",
                                session_id="test-session",
                                utterance="test utterance",
                                project_slug="test-project",
                                workflow_name="test_workflow",
                            )

                            # Verify workflow failed on first unknown step
                            assert result.status == "failed"
                            assert len(result.steps) == 1
                            assert result.steps[0].status == StepStatus.FAILED
                            assert "Unknown step type" in result.steps[0].error

    @pytest.mark.asyncio
    async def test_workflow_with_missing_project(
        self, executor
    ):
        """Test that missing project in registry causes workflow failure."""
        # Mock get_project to return None (project not found)
        with patch("src.action.executor.get_project", return_value=None):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_result"):
                # Execute workflow for non-existent project
                result = await executor.execute_workflow(
                    intent_id="test-intent",
                    session_id="test-session",
                    utterance="test utterance",
                    project_slug="nonexistent-project",
                    workflow_name="test_workflow",
                )

                # Verify workflow failed
                assert result.status == "failed"
                assert "not found in registry" in result.error
                assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_workflow_with_empty_steps(
        self, executor, mock_project_config
    ):
        """Test that workflow with no steps defined fails gracefully."""
        # Create workflow config with no steps
        empty_workflow_config = {
            "cluster": "test-cluster",
            "namespace": "test-namespace",
            "workflows": {
                "empty_workflow": {
                    "description": "Workflow with no steps",
                    "steps": [],
                },
            },
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=empty_workflow_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_result"):
                    # Execute workflow with no steps
                    result = await executor.execute_workflow(
                        intent_id="test-intent",
                        session_id="test-session",
                        utterance="test utterance",
                        project_slug="test-project",
                        workflow_name="empty_workflow",
                    )

                    # Verify workflow failed
                    assert result.status == "failed"
                    assert "no steps defined" in result.error

    @pytest.mark.asyncio
    async def test_workflow_timing_metrics(
        self, executor, mock_project_config
    ):
        """Test that workflow captures accurate timing metrics."""
        step_delays = [0.1, 0.2, 0.15]  # seconds

        async def mock_step_delayed(delay):
            """Mock step that simulates work."""
            import asyncio
            await asyncio.sleep(delay)
            return {"delay": delay}

        # Mock the step executors with delays
        executor._step_executors = {
            "step1": lambda *a, **k: mock_step_delayed(step_delays[0]),
            "step2": lambda *a, **k: mock_step_delayed(step_delays[1]),
            "step3": lambda *a, **k: mock_step_delayed(step_delays[2]),
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute workflow
                            start_time = time.time()
                            result = await executor.execute_workflow(
                                intent_id="test-intent",
                                session_id="test-session",
                                utterance="test utterance",
                                project_slug="test-project",
                                workflow_name="test_workflow",
                            )
                            total_time = time.time() - start_time

                            # Verify total duration is approximately sum of step delays
                            expected_total = sum(step_delays)
                            assert result.duration_ms >= expected_total * 1000 * 0.9  # Allow 10% tolerance
                            assert result.duration_ms <= (expected_total * 1000) + 200  # Allow overhead

                            # Verify each step has individual timing
                            for i, step in enumerate(result.steps):
                                assert step.duration_ms >= step_delays[i] * 1000 * 0.9
                                assert step.completed_at > step.started_at

    @pytest.mark.asyncio
    async def test_step_executor_instantiation(
        self, executor, mock_project_config
    ):
        """Test that steps are instantiated and executed correctly."""
        # Track which step executors were called
        called_executors = []

        async def mock_executor_1(*args, **kwargs):
            called_executors.append("executor_1")
            return {"executor": "executor_1"}

        async def mock_executor_2(*args, **kwargs):
            called_executors.append("executor_2")
            return {"executor": "executor_2"}

        # Mock the step executors
        executor._step_executors = {
            "step1": mock_executor_1,
            "step2": mock_executor_2,
        }

        # Modify workflow to use only step1 and step2
        two_step_workflow = {
            "cluster": "test-cluster",
            "namespace": "test-namespace",
            "workflows": {
                "two_step": {
                    "description": "Two step workflow",
                    "steps": ["step1", "step2"],
                },
            },
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=two_step_workflow):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute workflow
                            result = await executor.execute_workflow(
                                intent_id="test-intent",
                                session_id="test-session",
                                utterance="test utterance",
                                project_slug="test-project",
                                workflow_name="two_step",
                            )

                            # Verify both executors were called in order
                            assert called_executors == ["executor_1", "executor_2"]

                            # Verify workflow completed successfully
                            assert result.status == "completed"
                            assert len(result.steps) == 2

    @pytest.mark.asyncio
    async def test_sequential_step_execution_order(
        self, executor, mock_project_config
    ):
        """Test that steps execute strictly sequentially, not concurrently."""
        execution_timestamps = []

        async def mock_step_with_timestamp(step_name):
            """Mock step that records its execution timestamp."""
            import asyncio
            execution_timestamps.append((step_name, time.time()))
            await asyncio.sleep(0.05)  # Small delay to ensure ordering is observable
            return {"step": step_name}

        # Mock the step executors
        executor._step_executors = {
            "step1": lambda *a, **k: mock_step_with_timestamp("step1"),
            "step2": lambda *a, **k: mock_step_with_timestamp("step2"),
            "step3": lambda *a, **k: mock_step_with_timestamp("step3"),
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute workflow
                            await executor.execute_workflow(
                                intent_id="test-intent",
                                session_id="test-session",
                                utterance="test utterance",
                                project_slug="test-project",
                                workflow_name="test_workflow",
                            )

                            # Verify sequential execution (timestamps should be strictly increasing)
                            assert len(execution_timestamps) == 3
                            timestamps = [t for _, t in execution_timestamps]
                            assert timestamps[0] < timestamps[1] < timestamps[2]

                            # Verify step names match execution order
                            step_names = [name for name, _ in execution_timestamps]
                            assert step_names == ["step1", "step2", "step3"]


class TestActionRunnerEdgeCases:
    """Test edge cases and error handling in action runner."""

    @pytest.fixture
    def executor(self):
        """Create an ActionExecutor instance for testing."""
        return ActionExecutor()

    @pytest.mark.asyncio
    async def test_workflow_with_exception_in_step(
        self, executor
    ):
        """Test that exceptions in step execution are caught and marked as failures."""
        # Create project config
        project_config = {
            "cluster": "test-cluster",
            "namespace": "test-namespace",
            "workflows": {
                "exception_workflow": {
                    "description": "Workflow with exception",
                    "steps": ["good_step", "exception_step", "after_step"],
                },
            },
        }

        async def good_step(*args, **kwargs):
            return {"status": "good"}

        async def exception_step(*args, **kwargs):
            raise RuntimeError("Unexpected error in step")

        async def after_step(*args, **kwargs):
            # Should not execute
            return {"status": "after"}

        # Mock the step executors
        executor._step_executors = {
            "good_step": good_step,
            "exception_step": exception_step,
            "after_step": after_step,
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute workflow
                            result = await executor.execute_workflow(
                                intent_id="test-intent",
                                session_id="test-session",
                                utterance="test utterance",
                                project_slug="test-project",
                                workflow_name="exception_workflow",
                            )

                            # Verify workflow halted at exception
                            assert result.status == "failed"
                            assert len(result.steps) == 2  # good_step and exception_step only

                            # Verify first step succeeded, second failed with exception
                            assert result.steps[0].status == StepStatus.COMPLETED
                            assert result.steps[1].status == StepStatus.FAILED
                            assert "Unexpected error in step" in result.steps[1].error

    @pytest.mark.asyncio
    async def test_workflow_with_missing_workflow_name(
        self, executor
    ):
        """Test that missing workflow name in project config fails gracefully."""
        project_config = {
            "cluster": "test-cluster",
            "namespace": "test-namespace",
            "workflows": {
                "existing_workflow": {
                    "description": "Existing workflow",
                    "steps": ["step1"],
                },
            },
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_result"):
                    # Execute non-existent workflow
                    result = await executor.execute_workflow(
                        intent_id="test-intent",
                        session_id="test-session",
                        utterance="test utterance",
                        project_slug="test-project",
                        workflow_name="nonexistent_workflow",
                    )

                    # Verify workflow failed (no steps found)
                    assert result.status == "failed"
                    assert "no steps defined" in result.error.lower()

    @pytest.mark.asyncio
    async def test_workflow_result_to_dict(
        self, executor
    ):
        """Test that ActionResult.to_dict() returns proper structure."""
        # Create a mock ActionResult
        result = ActionResult(
            intent_id="test-intent",
            session_id="test-session",
            project_slug="test-project",
            workflow_name="test_workflow",
            status="completed",
            started_at=time.time(),
        )

        # Add some step results
        result.add_step(
            StepResult(
                step_name="step1",
                status=StepStatus.COMPLETED,
                output={"data": "value1"},
                started_at=time.time(),
                completed_at=time.time(),
                duration_ms=100.0,
            )
        )

        result.add_step(
            StepResult(
                step_name="step2",
                status=StepStatus.COMPLETED,
                output={"data": "value2"},
                started_at=time.time(),
                completed_at=time.time(),
                duration_ms=150.0,
            )
        )

        # Convert to dict
        result_dict = result.to_dict()

        # Verify structure
        assert result_dict["intent_id"] == "test-intent"
        assert result_dict["session_id"] == "test-session"
        assert result_dict["project_slug"] == "test-project"
        assert result_dict["workflow_name"] == "test_workflow"
        assert result_dict["status"] == "completed"
        assert len(result_dict["steps"]) == 2
        assert result_dict["steps"][0]["step_name"] == "step1"
        assert result_dict["steps"][0]["status"] == "completed"
        assert result_dict["steps"][0]["output"] == {"data": "value1"}


class TestActionRunnerSSEBroadcasting:
    """Test SSE event broadcasting during workflow execution."""

    @pytest.fixture
    def executor(self):
        """Create an ActionExecutor instance for testing."""
        return ActionExecutor()

    @pytest.fixture
    def mock_project_config(self):
        """Create a mock project configuration with workflows."""
        return {
            "cluster": "test-cluster",
            "namespace": "test-namespace",
            "repo_path": "/tmp/test-repo",
            "argocd_app": "test-app",
            "workflows": {
                "test_workflow": {
                    "description": "Test workflow with 3 steps",
                    "steps": ["step1", "step2", "step3"],
                },
                "failing_workflow": {
                    "description": "Workflow with failing step",
                    "steps": ["step1", "failing_step", "step3"],
                },
            },
        }

    @pytest.mark.asyncio
    async def test_sse_event_sequence_for_successful_workflow(
        self, executor, mock_project_config
    ):
        """Test that SSE events are broadcast in correct order for successful workflow."""
        # Track SSE events in order
        sse_events = []

        # Mock broadcaster to capture events
        async def mock_broadcast(event):
            sse_events.append({
                "event_type": event.event_type,
                "data": event.data,
            })

        mock_broadcaster = Mock()
        mock_broadcaster.broadcast = mock_broadcast

        # Mock step executors
        async def mock_step1(*args, **kwargs):
            return {"status": "step1_complete"}
        async def mock_step2(*args, **kwargs):
            return {"status": "step2_complete"}
        async def mock_step3(*args, **kwargs):
            return {"status": "step3_complete"}

        executor._step_executors = {
            "step1": mock_step1,
            "step2": mock_step2,
            "step3": mock_step3,
        }

        # Mock get_project and get_broadcaster
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            with patch("src.action.executor.get_broadcaster", return_value=mock_broadcaster):
                # Execute workflow
                result = await executor.execute_workflow(
                    intent_id="test-intent",
                    session_id="test-session",
                    utterance="test utterance",
                    project_slug="test-project",
                    workflow_name="test_workflow",
                )

                # Verify workflow completed
                assert result.status == "completed"

                # Verify SSE event sequence
                event_types = [e["event_type"] for e in sse_events]

                # Expected sequence:
                # 1. workflow_started
                # 2. workflow_progress (1/3)
                # 3. step_started (step1)
                # 4. step_progress (step1 in-progress)
                # 5. step_completed (step1)
                # 6. workflow_progress (2/3)
                # 7. step_started (step2)
                # 8. step_progress (step2 in-progress)
                # 9. step_completed (step2)
                # 10. workflow_progress (3/3)
                # 11. step_started (step3)
                # 12. step_progress (step3 in-progress)
                # 13. step_completed (step3)
                # 14. workflow_completed

                assert event_types[0] == "action_workflow_started"
                assert event_types[-1] == "action_workflow_completed"

                # Count events by type
                workflow_started_count = sum(1 for t in event_types if t == "action_workflow_started")
                workflow_progress_count = sum(1 for t in event_types if t == "action_workflow_progress")
                step_started_count = sum(1 for t in event_types if t == "action_step_started")
                step_progress_count = sum(1 for t in event_types if t == "action_step_progress")
                step_completed_count = sum(1 for t in event_types if t == "action_step_completed")
                workflow_completed_count = sum(1 for t in event_types if t == "action_workflow_completed")

                assert workflow_started_count == 1
                assert workflow_progress_count == 3  # One per step
                assert step_started_count == 3
                assert step_progress_count == 3  # NEW: progress events for each step
                assert step_completed_count == 3
                assert workflow_completed_count == 1

    @pytest.mark.asyncio
    async def test_sse_event_sequence_for_failed_workflow(
        self, executor, mock_project_config
    ):
        """Test that SSE events include failure events when workflow fails."""
        sse_events = []

        # Mock broadcaster to capture events
        async def mock_broadcast(event):
            sse_events.append({
                "event_type": event.event_type,
                "data": event.data,
            })

        mock_broadcaster = Mock()
        mock_broadcaster.broadcast = mock_broadcast

        # Mock step executors with failure
        async def mock_step1(*args, **kwargs):
            return {"status": "step1_complete"}

        async def failing_step(*args, **kwargs):
            raise ValueError("Step execution failed")

        executor._step_executors = {
            "step1": mock_step1,
            "failing_step": failing_step,
        }

        # Mock get_project and get_broadcaster
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            with patch("src.action.executor.get_broadcaster", return_value=mock_broadcaster):
                # Execute workflow that fails
                result = await executor.execute_workflow(
                    intent_id="test-intent",
                    session_id="test-session",
                    utterance="test utterance",
                    project_slug="test-project",
                    workflow_name="failing_workflow",
                )

                # Verify workflow failed
                assert result.status == "failed"

                # Verify SSE event sequence
                event_types = [e["event_type"] for e in sse_events]

                # Should include failure events
                assert "action_step_failed" in event_types
                assert "action_workflow_failed" in event_types
                assert "action_workflow_completed" not in event_types

                # Verify step_progress contains error
                progress_events = [e for e in sse_events if e["event_type"] == "action_step_progress"]
                failing_progress = progress_events[-1]  # Last progress event is for failing step
                assert failing_progress["data"]["progress"]["status"] == "failed"
                assert "error" in failing_progress["data"]["progress"]

    @pytest.mark.asyncio
    async def test_sse_event_data_structure(self, executor, mock_project_config):
        """Test that SSE events contain correct data structure."""
        sse_events = []

        # Mock broadcaster to capture events
        async def mock_broadcast(event):
            sse_events.append({
                "event_type": event.event_type,
                "data": event.data,
            })

        mock_broadcaster = Mock()
        mock_broadcaster.broadcast = mock_broadcast

        # Mock step executors (all three steps in test_workflow)
        async def mock_step1(*args, **kwargs):
            return {"output": "test_result", "value": 42}

        async def mock_step2(*args, **kwargs):
            return {"output": "step2_result", "value": 100}

        async def mock_step3(*args, **kwargs):
            return {"output": "step3_result", "value": 200}

        executor._step_executors = {
            "step1": mock_step1,
            "step2": mock_step2,
            "step3": mock_step3,
        }

        # Mock get_project and get_broadcaster
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            with patch("src.action.executor.get_broadcaster", return_value=mock_broadcaster):
                # Execute workflow
                await executor.execute_workflow(
                    intent_id="test-intent-123",
                    session_id="test-session-456",
                    utterance="test utterance",
                    project_slug="test-project",
                    workflow_name="test_workflow",
                )

                # Verify workflow_started event data
                workflow_started = next(e for e in sse_events if e["event_type"] == "action_workflow_started")
                assert workflow_started["data"]["intent_id"] == "test-intent-123"
                assert workflow_started["data"]["session_id"] == "test-session-456"
                assert workflow_started["data"]["project_slug"] == "test-project"
                assert workflow_started["data"]["workflow_name"] == "test_workflow"
                assert "utterance" in workflow_started["data"]
                assert "started_at" in workflow_started["data"]

                # Verify step_started event data (check first step)
                step_started_events = [e for e in sse_events if e["event_type"] == "action_step_started"]
                assert len(step_started_events) >= 1
                first_step_started = step_started_events[0]
                assert first_step_started["data"]["step_name"] == "step1"
                assert "status" in first_step_started["data"]
                assert "started_at" in first_step_started["data"]

                # Verify step_progress event data (check first step)
                step_progress_events = [e for e in sse_events if e["event_type"] == "action_step_progress"]
                assert len(step_progress_events) >= 1
                first_step_progress = step_progress_events[0]
                assert first_step_progress["data"]["step_name"] == "step1"
                assert "progress" in first_step_progress["data"]
                assert first_step_progress["data"]["progress"]["status"] == "completed"
                assert first_step_progress["data"]["progress"]["output"] == {"output": "test_result", "value": 42}
                assert "duration_ms" in first_step_progress["data"]["progress"]
                assert "timestamp" in first_step_progress["data"]

                # Verify step_completed event data (check first step)
                step_completed_events = [e for e in sse_events if e["event_type"] == "action_step_completed"]
                assert len(step_completed_events) >= 1
                first_step_completed = step_completed_events[0]
                assert "step_name" in first_step_completed["data"]
                assert "status" in first_step_completed["data"]
                assert "started_at" in first_step_completed["data"]
                assert "completed_at" in first_step_completed["data"]
                assert "duration_ms" in first_step_completed["data"]

                # Verify workflow_completed event data
                workflow_completed = next(e for e in sse_events if e["event_type"] == "action_workflow_completed")
                assert workflow_completed["data"]["intent_id"] == "test-intent-123"
                assert workflow_completed["data"]["status"] == "completed"
                assert "steps" in workflow_completed["data"]
                assert "started_at" in workflow_completed["data"]
                assert "completed_at" in workflow_completed["data"]
                assert "duration_ms" in workflow_completed["data"]

    @pytest.mark.asyncio
    async def test_sse_workflow_progress_events(self, executor, mock_project_config):
        """Test that workflow_progress events track step completion correctly."""
        sse_events = []

        # Mock broadcaster to capture events
        async def mock_broadcast(event):
            sse_events.append({
                "event_type": event.event_type,
                "data": event.data,
            })

        mock_broadcaster = Mock()
        mock_broadcaster.broadcast = mock_broadcast

        # Mock step executors
        async def mock_step(*args, **kwargs):
            return {"result": "success"}

        executor._step_executors = {
            "step1": mock_step,
            "step2": mock_step,
            "step3": mock_step,
        }

        # Mock get_project and get_broadcaster
        with patch("src.action.executor.get_project", return_value=mock_project_config):
            with patch("src.action.executor.get_broadcaster", return_value=mock_broadcaster):
                # Execute workflow
                await executor.execute_workflow(
                    intent_id="test-intent",
                    session_id="test-session",
                    utterance="test utterance",
                    project_slug="test-project",
                    workflow_name="test_workflow",
                )

                # Verify workflow_progress events
                progress_events = [e for e in sse_events if e["event_type"] == "action_workflow_progress"]
                assert len(progress_events) == 3

                # Verify progress increments correctly
                assert progress_events[0]["data"]["current_step"] == 1
                assert progress_events[0]["data"]["total_steps"] == 3
                assert progress_events[0]["data"]["progress_percent"] == 33

                assert progress_events[1]["data"]["current_step"] == 2
                assert progress_events[1]["data"]["total_steps"] == 3
                assert progress_events[1]["data"]["progress_percent"] == 66

                assert progress_events[2]["data"]["current_step"] == 3
                assert progress_events[2]["data"]["total_steps"] == 3
                assert progress_events[2]["data"]["progress_percent"] == 100

                # Verify all progress events have timestamp
                for event in progress_events:
                    assert "timestamp" in event["data"]
                    assert event["data"]["workflow_name"] == "test_workflow"


class TestActionRunnerIntegration:
    """Integration tests for action runner with real-like scenarios."""

    @pytest.fixture
    def executor(self):
        """Create an ActionExecutor instance for testing."""
        return ActionExecutor()

    @pytest.mark.asyncio
    async def test_complete_deployment_workflow_simulation(
        self, executor
    ):
        """Test a complete deployment workflow simulation with multiple step types."""
        # Simulate a real deployment workflow:
        # 1. Check CI status
        # 2. Get image tag
        # 3. Commit gitops change
        # 4. Wait for ArgoCD sync
        # 5. Verify pod status

        project_config = {
            "cluster": "production-cluster",
            "namespace": "production",
            "repo_path": "/tmp/declarative-config",
            "argocd_app": "my-app",
            "workflows": {
                "deploy": {
                    "description": "Deploy application to production",
                    "steps": [
                        "ci_status",
                        "image_tag",
                        "gitops_commit",
                        "argocd_sync_status",
                        "pod_status",
                    ],
                },
            },
        }

        execution_log = []

        async def mock_ci_status(*args, **kwargs):
            execution_log.append("ci_status")
            return {"status": "success", "workflow": "build-123", "phase": "Succeeded"}

        async def mock_image_tag(*args, **kwargs):
            execution_log.append("image_tag")
            return {"tag": "v1.2.3", "digest": "sha256:abc123"}

        async def mock_gitops_commit(*args, **kwargs):
            execution_log.append("gitops_commit")
            return {
                "commit": "abc123def",
                "branch": "main",
                "manifest": "deployment.yaml",
                "status": "success",
            }

        async def mock_argocd_sync(*args, **kwargs):
            execution_log.append("argocd_sync_status")
            return {"status": "synced", "sync_status": "Synced", "health_status": "Healthy"}

        async def mock_pod_status(*args, **kwargs):
            execution_log.append("pod_status")
            return {"total_pods": 3, "running": 3, "pending": 0, "failed": 0}

        # Mock the step executors
        executor._step_executors = {
            "ci_status": mock_ci_status,
            "image_tag": mock_image_tag,
            "gitops_commit": mock_gitops_commit,
            "argocd_sync_status": mock_argocd_sync,
            "pod_status": mock_pod_status,
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute deployment workflow
                            result = await executor.execute_workflow(
                                intent_id="deploy-intent",
                                session_id="session-123",
                                utterance="Deploy my app to production",
                                project_slug="my-app",
                                workflow_name="deploy",
                            )

                            # Verify execution order matches deployment workflow
                            assert execution_log == [
                                "ci_status",
                                "image_tag",
                                "gitops_commit",
                                "argocd_sync_status",
                                "pod_status",
                            ]

                            # Verify workflow completed successfully
                            assert result.status == "completed"
                            assert len(result.steps) == 5

                            # Verify each step has appropriate output
                            assert result.steps[0].output["status"] == "success"
                            assert result.steps[1].output["tag"] == "v1.2.3"
                            assert result.steps[2].output["commit"] == "abc123def"
                            assert result.steps[3].output["sync_status"] == "Synced"
                            assert result.steps[4].output["running"] == 3

    @pytest.mark.asyncio
    async def test_deployment_workflow_failure_at_ci_gate(
        self, executor
    ):
        """Test deployment workflow that fails at CI status gate."""
        project_config = {
            "cluster": "production-cluster",
            "namespace": "production",
            "workflows": {
                "deploy": {
                    "description": "Deploy application to production",
                    "steps": ["ci_status", "image_tag", "gitops_commit"],
                },
            },
        }

        execution_log = []

        async def mock_ci_status_failed(*args, **kwargs):
            execution_log.append("ci_status")
            # CI gate raises exception when CI fails
            raise RuntimeError("CI workflow build-124 failed: phase=Failed")

        async def mock_image_tag(*args, **kwargs):
            # Should not execute
            execution_log.append("image_tag")
            return {"tag": "v1.2.3"}

        async def mock_gitops_commit(*args, **kwargs):
            # Should not execute
            execution_log.append("gitops_commit")
            return {"commit": "abc123def"}

        # Mock the step executors
        executor._step_executors = {
            "ci_status": mock_ci_status_failed,
            "image_tag": mock_image_tag,
            "gitops_commit": mock_gitops_commit,
        }

        # Mock get_project to return test config
        with patch("src.action.executor.get_project", return_value=project_config):
            # Mock SSE broadcasts
            with patch.object(executor, "_broadcast_workflow_started"):
                with patch.object(executor, "_broadcast_step_started"):
                    with patch.object(executor, "_broadcast_step_completed"):
                        with patch.object(executor, "_broadcast_result"):
                            # Execute deployment workflow
                            result = await executor.execute_workflow(
                                intent_id="deploy-intent",
                                session_id="session-123",
                                utterance="Deploy my app to production",
                                project_slug="my-app",
                                workflow_name="deploy",
                            )

                            # Verify only CI status executed
                            assert execution_log == ["ci_status"]

                            # Verify workflow failed
                            assert result.status == "failed"
                            assert len(result.steps) == 1

                            # Verify CI status check was recorded
                            assert result.steps[0].step_name == "ci_status"
                            assert result.steps[0].status == StepStatus.FAILED
                            assert "CI workflow build-124 failed" in result.steps[0].error
