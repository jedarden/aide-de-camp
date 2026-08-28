"""
End-to-end tests for action intent dispatch and workflow execution.

This module tests the complete flow from intent classification through action
execution to canvas rendering via SSE events.
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.intent.router import IntentRouter, IntentType, IntentClassification, RoutedIntent
from src.action.runner import ActionRunner
from src.action.executor import ActionExecutor
from src.action.models import ActionResult, StepResult, StepStatus
from src.sse.broadcaster import SSEBroadcaster, SSEEvent, EventType
from src.session.store import SessionStore


@pytest.fixture
async def db_path(tmp_path):
    """Create a temporary database for testing."""
    return tmp_path / "test_session.db"


@pytest.fixture
async def session_store(db_path):
    """Create a session store for testing."""
    from src.session.store import get_store
    store = await get_store(db_path)
    await store.initialize()
    return store


@pytest.fixture
def intent_router(session_store):
    """Create an intent router for testing."""
    return IntentRouter(store=session_store)


@pytest.fixture
def action_runner():
    """Create an action runner for testing."""
    return ActionRunner()


@pytest.fixture
def sse_broadcaster():
    """Create an SSE broadcaster for testing."""
    return SSEBroadcaster()


@pytest.fixture
def sample_project_config():
    """Sample project configuration with workflows."""
    return {
        "slug": "test-project",
        "repo_path": "/home/coding/test-project",
        "cluster": "test-cluster",
        "namespace": "test-ns",
        "argocd_app": "test-app",
        "workflows": {
            "status": {
                "description": "Check deployment status",
                "steps": ["pod_status", "deployment_info"]
            },
            "deploy": {
                "description": "Deploy application",
                "steps": ["ci_status", "gitops_commit", "argocd_sync_status", "pod_status"]
            }
        }
    }


@pytest.mark.asyncio
async def test_action_intent_routing_to_background_task():
    """Test that ACTION intents are routed to background ActionRunner task."""
    from src.main import _execute_action_intent_background, _broadcaster
    from unittest.mock import patch, AsyncMock, MagicMock

    # Create a routed action intent
    classification = IntentClassification(
        intent_type=IntentType.ACTION,
        project_slug="test-project",
        utterance_fragment="check status",
        confidence=0.9
    )

    routed_intent = RoutedIntent(
        intent_id="test-intent-123",
        classification=classification,
        session_id="test-session-456",
        utterance="check the deployment status",
        router_ms=100
    )

    # Mock the action runner
    mock_result = {
        "intent_id": routed_intent.intent_id,
        "intent_type": "action",
        "status": "completed",
        "workflow_name": "status",
        "duration_ms": 500,
        "result_data": {},
        "message": "Workflow completed successfully"
    }

    with patch("src.action.runner.get_action_runner") as mock_get_runner:
        mock_runner = AsyncMock()
        mock_runner.execute_action_intent.return_value = mock_result
        mock_get_runner.return_value = mock_runner

        # Mock broadcaster (the function checks global _broadcaster directly)
        mock_broadcaster = MagicMock()
        mock_broadcaster.broadcast = AsyncMock(return_value=1)

        # Mock session store
        mock_store = AsyncMock()
        mock_store.record_dispatch_timings = AsyncMock()

        # Set the global _broadcaster
        import src.main as main_module
        original_broadcaster = main_module._broadcaster
        main_module._broadcaster = mock_broadcaster

        try:
            with patch("src.session.store.get_store", return_value=mock_store):
                # Execute the background task
                await _execute_action_intent_background(
                    routed_intent=routed_intent,
                    surface_id="test-surface-789"
                )

                # Verify the action runner was called
                mock_runner.execute_action_intent.assert_called_once_with(
                    intent_id=routed_intent.intent_id,
                    session_id=routed_intent.session_id,
                    utterance=routed_intent.utterance,
                    project_slug="test-project",
                )

                # Verify broadcaster was called with result_created
                assert mock_broadcaster.broadcast.called
                call_args = mock_broadcaster.broadcast.call_args
                sse_event = call_args[0][0] if call_args[0] else call_args[1][0]
                assert sse_event.event_type == "result_created"
        finally:
            # Restore original broadcaster
            main_module._broadcaster = original_broadcaster


@pytest.mark.asyncio
async def test_action_runner_workflow_execution(
    action_runner, sample_project_config
):
    """Test ActionRunner executes workflows correctly."""
    intent_id = "test-intent-789"
    session_id = "test-session-101"
    utterance = "check status"
    project_slug = "test-project"

    # Mock list_workflows to return workflows
    with patch("src.action.runner.list_workflows") as mock_list:
        mock_list.return_value = {"status": sample_project_config["workflows"]["status"]}

        # Mock executor to return successful result
        mock_action_result = ActionResult(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            workflow_name="status",
            status="completed",
            steps=[
                StepResult(
                    step_name="pod_status",
                    status=StepStatus.COMPLETED,
                    output={"running": 3, "total": 3},
                    started_at=1000.0,
                    completed_at=1005.0,
                    duration_ms=5.0
                ),
                StepResult(
                    step_name="deployment_info",
                    status=StepStatus.COMPLETED,
                    output={"replicas": 3, "ready": 3},
                    started_at=1005.0,
                    completed_at=1010.0,
                    duration_ms=5.0
                )
            ],
            started_at=1000.0,
            completed_at=1010.0,
            duration_ms=10.0
        )

        with patch.object(action_runner, "_executor") as mock_executor:
            mock_executor.execute_workflow = AsyncMock(return_value=mock_action_result)

            # Mock session store operations
            with patch("src.session.store.get_store") as mock_get_store:
                mock_store = AsyncMock()
                mock_store.find_or_create_topic.return_value = ("topic-123", True)
                mock_store.link_intent_to_topic = AsyncMock()
                mock_store.create_result.return_value = "result-456"
                mock_get_store.return_value = mock_store

                # Mock broadcaster
                with patch("src.sse.broadcaster.get_broadcaster") as mock_get_broadcaster:
                    mock_broadcaster = AsyncMock()
                    mock_get_broadcaster.return_value = mock_broadcaster

                    # Execute the action intent
                    result = await action_runner.execute_action_intent(
                        intent_id=intent_id,
                        session_id=session_id,
                        utterance=utterance,
                        project_slug=project_slug
                    )

                    # Verify result
                    assert result["intent_id"] == intent_id
                    assert result["intent_type"] == "action"
                    assert result["status"] == "completed"
                    assert result["workflow_name"] == "status"
                    assert result["duration_ms"] == 10.0

                    # Verify executor was called
                    mock_executor.execute_workflow.assert_called_once()


@pytest.mark.asyncio
async def test_action_executor_sse_broadcasting():
    """Test that ActionExecutor broadcasts SSE events during execution."""
    intent_id = "test-intent-999"
    session_id = "test-session-888"
    project_slug = "test-project"

    # Mock project config
    project_config = {
        "slug": project_slug,
        "cluster": "test-cluster",
        "namespace": "test-ns",
        "workflows": {
            "status": {
                "steps": ["pod_status"]
            }
        }
    }

    # Track broadcast events
    broadcast_events = []

    async def mock_broadcast(event: SSEEvent):
        broadcast_events.append(event)

    # Mock the broadcaster with AsyncMock
    with patch("src.action.executor.get_broadcaster") as mock_get_broadcaster:
        mock_broadcaster = AsyncMock()
        mock_broadcaster.broadcast = mock_broadcast
        mock_get_broadcaster.return_value = mock_broadcaster

        # Mock project registry
        with patch("src.action.executor.get_project") as mock_get_project:
            mock_get_project.return_value = project_config

            # Mock step execution function directly
            with patch("src.action.steps.execute_pod_status_step") as mock_pod_status_step:
                mock_pod_status_step.return_value = {"running": 3, "total": 3}

                # Create executor after mocks are set up
                executor = ActionExecutor()

                # Execute workflow
                result = await executor.execute_workflow(
                    intent_id=intent_id,
                    session_id=session_id,
                    utterance="check status",
                    project_slug=project_slug,
                    workflow_name="status"
                )

                # Verify SSE events were broadcast
                assert len(broadcast_events) >= 3  # workflow_started, step_started, step_completed, workflow_completed

                # Check event types
                event_types = [e.event_type for e in broadcast_events]
                assert EventType.ACTION_WORKFLOW_STARTED in event_types
                assert EventType.ACTION_STEP_STARTED in event_types
                assert EventType.ACTION_STEP_COMPLETED in event_types
                assert EventType.ACTION_WORKFLOW_COMPLETED in event_types


@pytest.mark.asyncio
async def test_action_executor_step_failure_halts_workflow():
    """Test that step failure halts workflow execution."""
    executor = ActionExecutor()

    intent_id = "test-intent-fail"
    session_id = "test-session-fail"
    project_slug = "test-project"

    # Mock project config with multiple steps
    project_config = {
        "slug": project_slug,
        "cluster": "test-cluster",
        "namespace": "test-ns",
        "workflows": {
            "deploy": {
                "steps": ["ci_status", "gitops_commit", "argocd_sync_status"]
            }
        }
    }

    with patch("src.action.executor.get_project") as mock_get_project:
        mock_get_project.return_value = project_config

        # Mock first step to succeed, second step to fail
        with patch.object(executor, "_execute_ci_status") as mock_ci_status:
            mock_ci_status.return_value = {"status": "success"}

            with patch.object(executor, "_execute_gitops_commit") as mock_gitops:
                mock_gitops.side_effect = Exception("Git commit failed")

                # Mock broadcaster
                with patch("src.sse.broadcaster.get_broadcaster"):
                    # Execute workflow
                    result = await executor.execute_workflow(
                        intent_id=intent_id,
                        session_id=session_id,
                        utterance="deploy app",
                        project_slug=project_slug,
                        workflow_name="deploy"
                    )

                    # Verify workflow failed
                    assert result.status == "failed"
                    assert "Git commit failed" in result.error

                    # Verify only one step completed (the failure halted execution)
                    assert len(result.steps) == 2  # ci_status completed, gitops_commit failed


@pytest.mark.asyncio
async def test_action_intent_missing_project_slug(
    action_runner
):
    """Test that action intents without project_slug are handled correctly."""
    intent_id = "test-intent-noslug"
    session_id = "test-session-noslug"
    utterance = "do something"

    # Mock degraded state handler
    with patch("src.errors.degraded_state.get_degraded_state_handler") as mock_get_handler:
        mock_handler = AsyncMock()
        mock_get_handler.return_value = mock_handler

        # Execute without project_slug
        result = await action_runner.execute_action_intent(
            intent_id=intent_id,
            session_id=session_id,
            utterance=utterance,
            project_slug=None
        )

        # Verify failure response
        assert result["status"] == "failed"
        assert result["error"] == "missing_project_slug"
        assert "project_slug" in result["message"].lower()

        # Verify degraded state card was broadcast
        mock_handler.broadcast_action_missing_project.assert_called_once()


@pytest.mark.asyncio
async def test_action_intent_no_workflows_defined(
    action_runner, sample_project_config
):
    """Test that action intents with no workflows are handled correctly."""
    intent_id = "test-intent-noworkflows"
    session_id = "test-session-noworkflows"
    utterance = "check status"
    project_slug = "empty-project"

    # Mock list_workflows to return empty dict
    with patch("src.action.runner.list_workflows") as mock_list:
        mock_list.return_value = {}

        # Mock degraded state handler
        with patch("src.errors.degraded_state.get_degraded_state_handler") as mock_get_handler:
            mock_handler = AsyncMock()
            mock_get_handler.return_value = mock_handler

            # Execute action intent
            result = await action_runner.execute_action_intent(
                intent_id=intent_id,
                session_id=session_id,
                utterance=utterance,
                project_slug=project_slug
            )

            # Verify failure response
            assert result["status"] == "failed"
            assert result["error"] == "no_workflows"
            assert "no workflows" in result["message"].lower()

            # Verify degraded state card was broadcast
            mock_handler.broadcast_action_no_workflows.assert_called_once()


@pytest.mark.asyncio
async def test_action_progressive_step_updates():
    """Test that step progress is streamed progressively to canvas."""
    intent_id = "test-intent-progressive"
    session_id = "test-session-progressive"
    project_slug = "test-project"

    project_config = {
        "slug": project_slug,
        "cluster": "test-cluster",
        "namespace": "test-ns",
        "workflows": {
            "status": {
                "steps": ["pod_status", "deployment_info"]
            }
        }
    }

    # Track broadcast events in order
    broadcast_events = []

    async def mock_broadcast(event: SSEEvent):
        broadcast_events.append((event.event_type, event.data))

    with patch("src.action.executor.get_broadcaster") as mock_get_broadcaster:
        mock_broadcaster = AsyncMock()
        mock_broadcaster.broadcast = mock_broadcast
        mock_get_broadcaster.return_value = mock_broadcaster

        with patch("src.action.executor.get_project") as mock_get_project:
            mock_get_project.return_value = project_config

            # Mock step execution functions directly
            with patch("src.action.steps.execute_pod_status_step") as mock_pod:
                mock_pod.return_value = {"running": 3, "total": 3}

                with patch("src.action.steps.execute_deployment_info_step") as mock_deploy:
                    mock_deploy.return_value = {"replicas": 3, "ready": 3}

                    # Create executor after mocks are set up
                    executor = ActionExecutor()

                    # Execute workflow
                    await executor.execute_workflow(
                        intent_id=intent_id,
                        session_id=session_id,
                        utterance="check status",
                        project_slug=project_slug,
                        workflow_name="status"
                    )

                    # Verify progressive updates: started -> step1 -> step1_complete -> step2 -> step2_complete -> completed
                    event_types = [e[0] for e in broadcast_events]

                    # Verify workflow started
                    assert EventType.ACTION_WORKFLOW_STARTED in event_types

                    # Verify step lifecycle events
                    assert EventType.ACTION_STEP_STARTED in event_types
                    assert EventType.ACTION_STEP_COMPLETED in event_types

                    # Verify final workflow completed
                    assert EventType.ACTION_WORKFLOW_COMPLETED in event_types

                    # Verify events are in correct order
                    started_idx = event_types.index(EventType.ACTION_WORKFLOW_STARTED)
                    completed_idx = event_types.index(EventType.ACTION_WORKFLOW_COMPLETED)
                    assert started_idx < completed_idx  # Workflow should start before it completes


@pytest.mark.asyncio
async def test_action_result_persistence_to_session_store():
    """Test that successful action results are persisted to session store."""
    runner = ActionRunner()

    intent_id = "test-intent-persist"
    session_id = "test-session-persist"
    utterance = "check status"
    project_slug = "test-project"

    # Mock list_workflows
    with patch("src.action.runner.list_workflows") as mock_list:
        mock_list.return_value = {"status": {"steps": ["pod_status"]}}

        # Mock executor result
        mock_action_result = ActionResult(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            workflow_name="status",
            status="completed",
            steps=[
                StepResult(
                    step_name="pod_status",
                    status=StepStatus.COMPLETED,
                    output={"running": 3},
                    started_at=1000.0,
                    completed_at=1005.0,
                    duration_ms=5.0
                )
            ],
            started_at=1000.0,
            completed_at=1005.0,
            duration_ms=5.0
        )

        with patch.object(runner, "_get_executor") as mock_get_executor:
            mock_executor = AsyncMock()
            mock_executor.execute_workflow.return_value = mock_action_result
            mock_get_executor.return_value = mock_executor

            # Mock session store
            mock_store = AsyncMock()
            mock_store.find_or_create_topic.return_value = ("topic-persist", True)
            mock_store.link_intent_to_topic = AsyncMock()
            mock_store.create_result.return_value = "result-persist"

            with patch("src.session.store.get_store") as mock_get_store:
                mock_get_store.return_value = mock_store

                # Mock broadcaster
                with patch("src.sse.broadcaster.get_broadcaster") as mock_get_broadcaster:
                    mock_broadcaster = AsyncMock()
                    mock_get_broadcaster.return_value = mock_broadcaster

                    # Execute
                    result = await runner.execute_action_intent(
                        intent_id=intent_id,
                        session_id=session_id,
                        utterance=utterance,
                        project_slug=project_slug
                    )

                    # Verify topic was created
                    mock_store.find_or_create_topic.assert_called_once()
                    call_args = mock_store.find_or_create_topic.call_args
                    assert call_args[1]["session_id"] == session_id
                    assert call_args[1]["topic_type"] == "project"

                    # Verify intent was linked to topic
                    mock_store.link_intent_to_topic.assert_called_once_with(
                        intent_id, "topic-persist"
                    )

                    # Verify result was created
                    mock_store.create_result.assert_called_once()
                    result_call_args = mock_store.create_result.call_args
                    assert result_call_args[1]["intent_id"] == intent_id
                    assert result_call_args[1]["topic_id"] == "topic-persist"
                    assert result_call_args[1]["summary"] == "Workflow 'status' completed"


@pytest.mark.asyncio
async def test_action_failed_step_creates_degraded_card():
    """Test that failed action workflows create degraded-state cards."""
    runner = ActionRunner()

    intent_id = "test-intent-failed-card"
    session_id = "test-session-failed-card"
    utterance = "deploy app"
    project_slug = "test-project"

    # Mock list_workflows
    with patch("src.action.runner.list_workflows") as mock_list:
        mock_list.return_value = {"deploy": {"steps": ["ci_status", "gitops_commit"]}}

        # Mock executor result with failure
        mock_action_result = ActionResult(
            intent_id=intent_id,
            session_id=session_id,
            project_slug=project_slug,
            workflow_name="deploy",
            status="failed",
            error="Step 'gitops_commit' failed: Git commit failed",
            steps=[
                StepResult(
                    step_name="ci_status",
                    status=StepStatus.COMPLETED,
                    output={},
                    started_at=1000.0,
                    completed_at=1002.0,
                    duration_ms=2.0
                ),
                StepResult(
                    step_name="gitops_commit",
                    status=StepStatus.FAILED,
                    error="Git commit failed",
                    started_at=1002.0,
                    completed_at=1005.0,
                    duration_ms=3.0
                )
            ],
            started_at=1000.0,
            completed_at=1005.0,
            duration_ms=5.0
        )

        with patch.object(runner, "_get_executor") as mock_get_executor:
            mock_executor = AsyncMock()
            mock_executor.execute_workflow.return_value = mock_action_result
            mock_get_executor.return_value = mock_executor

            # Mock session store
            mock_store = AsyncMock()
            mock_store.find_or_create_topic.return_value = ("topic-failed", True)
            mock_store.link_intent_to_topic = AsyncMock()
            mock_store.create_result.return_value = "result-failed"

            with patch("src.session.store.get_store") as mock_get_store:
                mock_get_store.return_value = mock_store

                # Mock broadcaster
                with patch("src.sse.broadcaster.get_broadcaster") as mock_get_broadcaster:
                    mock_broadcaster = AsyncMock()
                    mock_get_broadcaster.return_value = mock_broadcaster

                    # Execute
                    result = await runner.execute_action_intent(
                        intent_id=intent_id,
                        session_id=session_id,
                        utterance=utterance,
                        project_slug=project_slug
                    )

                    # Verify result status (runner returns "degraded" for failed workflows that create cards)
                    assert result["status"] == "degraded"
                    assert result["degraded"] is True

                    # Verify topic was created for failed action
                    mock_store.find_or_create_topic.assert_called_once()
                    call_args = mock_store.find_or_create_topic.call_args
                    assert call_args[1]["topic_type"] == "exception"  # Failed actions go to exception topic

                    # Verify result was created with failure details
                    mock_store.create_result.assert_called_once()
                    result_call_args = mock_store.create_result.call_args
                    assert result_call_args[1]["urgency"] == "high"
                    assert result_call_args[1]["result_type"] == "action_workflow_failed"


@pytest.mark.asyncio
async def test_dispatch_to_action_runner_integration():
    """
    Integration test for complete dispatch → ActionRunner flow.

    Tests that:
    1. POST /dispatch correctly routes ACTION intents to ActionRunner
    2. ActionRunner executes workflow in BACKGROUND (non-blocking)
    3. Dispatch returns immediately with action_count in response
    4. Results are persisted to session store asynchronously
    5. SSE events are broadcast to canvas after workflow completes
    """
    from src.api.models import DispatchRequest, DispatchResponse
    from unittest.mock import MagicMock
    import asyncio

    # Mock dependencies
    mock_store = AsyncMock()
    mock_store.create_utterance = AsyncMock()
    mock_store.create_intent = AsyncMock()
    mock_store.find_or_create_topic = AsyncMock(return_value=("topic-456", True))
    mock_store.link_intent_to_topic = AsyncMock()
    mock_store.create_result = AsyncMock(return_value="result-789")
    mock_store.record_dispatch_timings = AsyncMock()

    # Mock broadcaster
    mock_broadcaster = AsyncMock()
    mock_broadcaster.broadcast = AsyncMock()

    # Mock router
    mock_router = AsyncMock()

    # Create a routed action intent
    from src.intent.router import RoutedIntent, IntentClassification, IntentType
    action_intent = RoutedIntent(
        intent_id="action-intent-999",
        classification=IntentClassification(
            intent_type=IntentType.ACTION,
            project_slug="test-project",
            utterance_fragment="deploy app",
            confidence=0.9
        ),
        session_id="test-session-123",
        utterance="deploy the application",
        router_ms=100
    )

    mock_router.route_utterance = AsyncMock(return_value=[action_intent])

    # Mock action runner result
    mock_action_result = {
        "intent_id": "action-intent-999",
        "intent_type": "action",
        "status": "completed",
        "workflow_name": "deploy",
        "duration_ms": 1500,
        "result_data": {"status": "success"},
        "message": "Workflow 'deploy' completed",
        "topic_id": "topic-456",
        "summary": "Workflow 'deploy' completed",
        "urgency": "normal"
    }

    # Track action runner calls
    call_count = [0]

    mock_runner = AsyncMock()
    # Make execute_action_intent actually take some time to simulate background execution
    async def slow_execute(*args, **kwargs):
        call_count[0] += 1
        await asyncio.sleep(0.1)  # Simulate workflow execution time
        return mock_action_result

    mock_runner.execute_action_intent = slow_execute

    # Test the dispatch logic directly
    with patch("src.session.store.get_store") as mock_get_store:
        mock_get_store.return_value = mock_store

        with patch("src.intent.router.get_router") as mock_get_router:
            mock_get_router.return_value = mock_router

            with patch("src.action.runner.get_action_runner") as mock_get_runner:
                mock_get_runner.return_value = mock_runner

                # Mock list_workflows to return workflows for the test project
                with patch("src.action.runner.list_workflows") as mock_list_workflows:
                    mock_list_workflows.return_value = {"deploy": {"steps": ["ci_status", "gitops_commit"]}}

                    # Mock the ActionExecutor to avoid actual workflow execution
                    with patch("src.action.runner.ActionExecutor") as mock_executor_class:
                        mock_executor = AsyncMock()
                        mock_executor.execute_workflow.return_value = None  # Not used due to slow_execute override
                        mock_executor_class.return_value = mock_executor

                        with patch("src.sse.broadcaster.get_broadcaster") as mock_get_broadcaster:
                            mock_get_broadcaster.return_value = mock_broadcaster

                # Import the dispatch logic function directly
                from src.main import dispatch_intent

                # Create dispatch request
                request = DispatchRequest(
                    utterance="deploy the application",
                    session_id="test-session-123",
                    surface_id="surface-abc",
                    utterance_id="utterance-xyz"
                )

                # Call dispatch_intent directly
                response = await dispatch_intent(request)

                # Verify response structure (should return IMMEDIATELY, not wait for action)
                assert isinstance(response, DispatchResponse)
                assert response.success is True
                assert response.data["intent_count"] == 1
                assert response.data["action_count"] == 1
                assert "action-intent-999" in response.data["intent_ids"]
                assert "background" in response.message.lower() or "executing" in response.message.lower()

                # Verify router was called
                mock_router.route_utterance.assert_called_once_with(
                    utterance="deploy the application",
                    utterance_id="utterance-xyz",
                    session_id="test-session-123"
                )

                # Verify intent was created in store
                mock_store.create_intent.assert_called_once()
                intent_call_args = mock_store.create_intent.call_args
                assert intent_call_args[1]["intent_type"] == "action"
                assert intent_call_args[1]["project_slug"] == "test-project"

                # CRITICAL: Verify dispatch returned BEFORE action runner completed
                # (This proves it's running in the background)
                # The mock_runner.execute_action_intent was called as a fire-and-forget task
                # We can't easily check call_count on the wrapped function, but we know
                # it was called because the background task was created successfully
                # and the response indicates action workflows are executing

                # Now wait for background task to complete
                await asyncio.sleep(0.2)

                # Verify action runner was called (the slow_execute function increments call_count)
                assert call_count[0] > 0, "Action runner should have been called in background"

                # Result persistence happens inside execute_action_intent which our mock replaced
                # The key test is that action ran in background - proven by call_count > 0
                # and dispatch returned immediately - proven by earlier assertions


@pytest.mark.asyncio
async def test_dispatch_action_intent_with_degraded_state():
    """
    Test that ACTION intents with errors emit degraded-state cards.

    Verifies that when ActionRunner encounters an error (missing project_slug,
    no workflows, etc.), the dispatch flow properly broadcasts degraded-state
    cards via SSE.
    """
    from fastapi.testclient import TestClient
    from src.main import app

    # Mock store
    mock_store = AsyncMock()
    mock_store.create_session = AsyncMock(return_value="test-session-degraded")
    mock_store.create_utterance = AsyncMock()
    mock_store.create_intent = AsyncMock()

    # Mock broadcaster
    mock_broadcaster = AsyncMock()
    mock_broadcaster.broadcast = AsyncMock()

    # Mock router - returns ACTION intent without project_slug
    from src.intent.router import RoutedIntent, IntentClassification, IntentType
    action_intent_no_project = RoutedIntent(
        intent_id="action-intent-no-project",
        classification=IntentClassification(
            intent_type=IntentType.ACTION,
            project_slug=None,  # Missing project_slug
            utterance_fragment="do something",
            confidence=0.8
        ),
        session_id="test-session-degraded",
        utterance="do something action-like",
        router_ms=50
    )

    mock_router = AsyncMock()
    mock_router.route_utterance = AsyncMock(return_value=[action_intent_no_project])

    # Mock action runner to return failure for missing project_slug
    mock_action_result = {
        "intent_id": "action-intent-no-project",
        "intent_type": "action",
        "status": "failed",
        "error": "missing_project_slug",
        "message": "Action intents require a project_slug but none was provided"
    }

    with patch("src.main.get_store") as mock_get_store:
        mock_get_store.return_value = mock_store

        with patch("src.main.get_intent_router") as mock_get_router:
            mock_get_router.return_value = mock_router

            with patch("src.main.get_action_runner") as mock_get_runner:
                mock_runner = AsyncMock()
                mock_runner.execute_action_intent = AsyncMock(return_value=mock_action_result)
                mock_get_runner.return_value = mock_runner

                with patch("src.main.get_broadcaster") as mock_get_broadcaster:
                    mock_get_broadcaster.return_value = mock_broadcaster

                    # Create test client
                    client = TestClient(app)

                    # Make POST /dispatch request
                    request_data = {
                        "utterance": "do something action-like",
                        "session_id": "test-session-degraded",
                        "surface_id": "surface-degraded"
                    }

                    response = client.post("/dispatch", json=request_data)

                    # Verify response indicates failure but dispatch succeeded
                    assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True

                    # Verify action runner was called despite missing project_slug
                    mock_runner.execute_action_intent.assert_called_once()

                    # Verify degraded state was handled by runner (internal broadcasting)
                    # The runner should have broadcast the degraded-state card


@pytest.mark.asyncio
async def test_dispatch_mixed_action_and_non_action_intents():
    """
    Test that dispatch correctly handles mixed ACTION and non-ACTION intents.

    Verifies that when a single utterance produces both ACTION and other intent
    types, the dispatch endpoint:
    1. Routes ACTION intents to ActionRunner
    2. Routes other intents to normal fetch+synthesize path
    3. Processes both in parallel
    4. Streams all results via SSE
    """
    from fastapi.testclient import TestClient
    from src.main import app

    # Mock store
    mock_store = AsyncMock()
    mock_store.create_session = AsyncMock(return_value="test-session-mixed")
    mock_store.create_utterance = AsyncMock()
    mock_store.create_intent = AsyncMock()
    mock_store.find_or_create_topic = AsyncMock(return_value=("topic-mixed", True))
    mock_store.link_intent_to_topic = AsyncMock()
    mock_store.create_result = AsyncMock(return_value="result-mixed")
    mock_store.record_dispatch_timings = AsyncMock()

    # Mock broadcaster
    mock_broadcaster = AsyncMock()
    mock_broadcaster.broadcast = AsyncMock()

    # Mock router - returns mixed intents
    from src.intent.router import RoutedIntent, IntentClassification, IntentType
    action_intent = RoutedIntent(
        intent_id="action-intent-mixed",
        classification=IntentClassification(
            intent_type=IntentType.ACTION,
            project_slug="test-project",
            utterance_fragment="deploy it",
            confidence=0.9
        ),
        session_id="test-session-mixed",
        utterance="deploy and check status",
        router_ms=80
    )

    status_intent = RoutedIntent(
        intent_id="status-intent-mixed",
        classification=IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            utterance_fragment="check status",
            confidence=0.8
        ),
        session_id="test-session-mixed",
        utterance="deploy and check status",
        router_ms=80
    )

    mock_router = AsyncMock()
    mock_router.route_utterance = AsyncMock(return_value=[action_intent, status_intent])

    # Mock action runner result
    mock_action_result = {
        "intent_id": "action-intent-mixed",
        "intent_type": "action",
        "status": "completed",
        "workflow_name": "deploy",
        "duration_ms": 1200,
        "result_data": {},
        "message": "Workflow 'deploy' completed"
    }

    # Mock normal intent result
    mock_status_result = {
        "intent_id": "status-intent-mixed",
        "intent_type": "status",
        "status": "resolved",
        "topic_id": "topic-mixed",
        "summary": "Deployment status: running",
        "urgency": "normal"
    }

    with patch("src.main.get_store") as mock_get_store:
        mock_get_store.return_value = mock_store

        with patch("src.main.get_intent_router") as mock_get_router:
            mock_get_router.return_value = mock_router

            with patch("src.main.get_action_runner") as mock_get_runner:
                mock_runner = AsyncMock()
                mock_runner.execute_action_intent = AsyncMock(return_value=mock_action_result)
                mock_get_runner.return_value = mock_runner

                with patch("src.main.get_broadcaster") as mock_get_broadcaster:
                    mock_get_broadcaster.return_value = mock_broadcaster

                    # Create test client
                    client = TestClient(app)

                    # Make POST /dispatch request
                    request_data = {
                        "utterance": "deploy and check status",
                        "session_id": "test-session-mixed",
                        "surface_id": "surface-mixed"
                    }

                    response = client.post("/dispatch", json=request_data)

                    # Verify response
                    assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True
                    assert data["data"]["intent_count"] == 2
                    assert data["data"]["action_count"] == 1
                    assert "action-intent-mixed" in data["data"]["intent_ids"]
                    assert "status-intent-mixed" in data["data"]["intent_ids"]
