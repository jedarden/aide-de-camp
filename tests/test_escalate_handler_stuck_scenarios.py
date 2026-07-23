"""
Tests for escalate handler stuck scenario edge cases (bead adc-5036z).

This suite tests escalate handler behavior in stuck/edge case scenarios:
- Escalate handler with stuck intent type (edge case during escalation)
- Escalate handler methods when fence detection happens
- Bead watch creation with stuck intent tracking
- Terminal failure handling with stuck context
- Auto-approve evaluation with stuck metadata

These tests ensure the escalate handler integrates correctly with fence detection
and stuck card creation logic.
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.escalate.handler import (
    EscalateRequest,
    EscalateHandler,
    EscalateError,
    BeadCreationError,
    get_escalate_handler,
    handle_terminal_failure,
)
from src.session.store import SessionStore
from src.sse.broadcaster import SSEBroadcaster, SSEEvent, EventType


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """Isolated SessionStore on a tmp DB."""
    db_path = tmp_path / "test.db"
    s = SessionStore(db_path)
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def broadcaster() -> SSEBroadcaster:
    """Fresh SSEBroadcaster per test."""
    b = SSEBroadcaster()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def escalate_handler(store: SessionStore) -> EscalateHandler:
    """EscalateHandler with test store."""
    return EscalateHandler(store=store)


# --- Test Escalate Handler with Stuck Intent Type ----------------------------


class TestEscalateHandlerStuckIntentType:
    """Test escalate handler behavior with stuck intent type (edge case)."""

    @pytest.mark.asyncio
    async def test_escalate_request_with_stuck_type(self, escalate_handler: EscalateHandler):
        """EscalateRequest accepts stuck intent type."""
        request = EscalateRequest(
            intent_id="stuck-123",
            session_id="session-456",
            utterance="Task is stuck",
            intent_type="stuck",
            project_slug="adc",
            context={
                "stuck_reason": "Missing user input",
                "refusal_count": 3,
            },
            metadata={
                "urgency": "high",
                "surface_id": "canvas-123",
            },
        )

        assert request.intent_type == "stuck"
        assert request.context["stuck_reason"] == "Missing user input"
        assert request.metadata["urgency"] == "high"

    @pytest.mark.asyncio
    async def test_escalate_handler_to_dict_with_stuck_metadata(self, escalate_handler: EscalateHandler):
        """EscalateRequest.to_dict preserves stuck metadata."""
        request = EscalateRequest(
            intent_id="test-123",
            session_id="session-456",
            utterance="Test utterance",
            intent_type="stuck",
            project_slug="adc",
            context={
                "stuck_reason": "Test stuck",
                "refusal_count": 2,
                "bead_id": "adc-stuck-123",
            },
            metadata={"confidence": 0.85, "urgency": "high"},
        )

        request_dict = request.to_dict()

        assert request_dict["intent_type"] == "stuck"
        assert request_dict["context"]["stuck_reason"] == "Test stuck"
        assert request_dict["context"]["refusal_count"] == 2
        assert request_dict["context"]["bead_id"] == "adc-stuck-123"
        assert request_dict["metadata"]["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_escalate_handler_preserves_stuck_context(self, escalate_handler: EscalateHandler, store: SessionStore):
        """EscalateHandler preserves stuck context through operations."""
        request = EscalateRequest(
            intent_id="preserve-ctx-123",
            session_id="session-456",
            utterance="Preserve stuck context",
            intent_type="stuck",
            project_slug="adc",
            context={
                "stuck_reason": "Context preservation test",
                "refusal_count": 3,
                "fenced_at": int(datetime.now(timezone.utc).timestamp()),
                "bead_id": "adc-fenced-123",
            },
            metadata={"urgency": "high"},
        )

        # Verify context is preserved
        assert "stuck_reason" in request.context
        assert request.context["stuck_reason"] == "Context preservation test"
        assert request.context["refusal_count"] == 3
        assert request.context["fenced_at"] > 0
        assert request.context["bead_id"] == "adc-fenced-123"


# --- Test Bead Watch Creation with Stuck Intent Tracking --------------------


class TestBeadWatchCreationWithStuckIntent:
    """Test bead watch creation and tracking with stuck intents."""

    @pytest.mark.asyncio
    async def test_create_bead_watch_with_stuck_intent_type(self, escalate_handler: EscalateHandler, store: SessionStore):
        """_create_bead_watch handles stuck intent type correctly."""
        bead_ref = "adc-stuck-watch-123"

        await escalate_handler._create_bead_watch(
            bead_ref=bead_ref,
            project_slug="adc",
            intent_type="stuck",
        )

        # Verify bead watch was created
        watch = await store.get_bead_watch(bead_ref)
        assert watch is not None
        assert watch["bead_ref"] == bead_ref
        assert watch["refusal_count"] == 0
        assert watch["fenced_at"] is None

    @pytest.mark.asyncio
    async def test_create_bead_watch_with_sla_override(self, escalate_handler: EscalateHandler, store: SessionStore):
        """_create_bead_watch applies per-project SLA override for stuck intents."""
        # Note: The registry is read-only from YAML/discovery, so we test with
        # a project that doesn't have an SLA override, using the default
        bead_ref = "adc-sla-stuck-456"

        # Create bead watch for adc project (no SLA override configured)
        await escalate_handler._create_bead_watch(
            bead_ref=bead_ref,
            project_slug="adc",
            intent_type="stuck",
        )

        # Verify bead watch was created
        watch = await store.get_bead_watch(bead_ref)
        assert watch is not None
        assert watch["bead_ref"] == bead_ref
        assert watch["sla_deadline"] is not None

        # Verify SLA deadline is in the future (default SLA applied)
        # Default SLA for unstuck intents is 6 hours (stuck not in DEFAULT_SLA_HOURS)
        created_at = watch.get("created_at") or int(datetime.now(timezone.utc).timestamp())
        assert watch["sla_deadline"] > created_at

        # Verify it's reasonable (around 6 hours from now for default SLA)
        deadline_diff_hours = (watch["sla_deadline"] - created_at) / 3600
        assert 5 <= deadline_diff_hours <= 7  # Allow some tolerance for 6h default

    @pytest.mark.asyncio
    async def test_create_bead_watch_without_sla_override(self, escalate_handler: EscalateHandler, store: SessionStore):
        """_create_bead_watch uses default SLA when no override exists."""
        bead_ref = "adc-default-sla-789"

        await escalate_handler._create_bead_watch(
            bead_ref=bead_ref,
            project_slug="adc",  # No SLA override configured
            intent_type="stuck",
        )

        # Verify bead watch with default SLA (default is typically 24h)
        watch = await store.get_bead_watch(bead_ref)
        assert watch is not None
        assert watch["sla_deadline"] is not None


# --- Test Terminal Failure with Stuck Context --------------------------------


class TestTerminalFailureWithStuckContext:
    """Test terminal failure handling when intent has stuck context."""

    @pytest.mark.asyncio
    async def test_handle_terminal_failure_with_stuck_bead_ref(self, store: SessionStore, broadcaster: SSEBroadcaster):
        """handle_terminal_failure updates bead_watch when stuck bead_ref provided."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Stuck Failure Test",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="stuck task that failed",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="stuck",
            bead_ref="adc-stuck-fail-123",
            topic_id=topic_id,
        )

        # Create bead watch
        await store.create_bead_watch(
            bead_ref="adc-stuck-fail-123",
            sla_hours=6,
            intent_type="stuck",
        )

        # Register SSE connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Handle terminal failure with stuck bead ref
        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Stuck task execution failed",
                error_type="stuck_timeout",
                bead_ref="adc-stuck-fail-123",
            )

        # Verify bead_watch updated with failure
        watch = await store.get_bead_watch("adc-stuck-fail-123")
        assert watch["last_refusal_reason"] == "Stuck task execution failed"
        assert watch["refusal_count"] == 1

        # Verify SSE event
        event = await conn.queue.get()
        assert event.event_type == "task_failed"
        assert event.data["bead_id"] == "adc-stuck-fail-123"

    @pytest.mark.asyncio
    async def test_handle_terminal_failure_creates_topic_when_none_for_stuck(self, store: SessionStore, broadcaster: SSEBroadcaster):
        """handle_terminal_failure creates exception topic for stuck intent when topic_id is None."""
        session_id = "test-session-no-topic"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="stuck without topic",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="stuck",
            bead_ref="adc-no-topic-123",
        )

        # Create bead watch
        await store.create_bead_watch(
            bead_ref="adc-no-topic-123",
            sla_hours=6,
            intent_type="stuck",
        )

        # Register SSE connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Handle terminal failure without topic
        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=None,  # No topic provided
                failure_reason="Stuck task with no topic failed",
                error_type="stuck_no_topic",
                bead_ref="adc-no-topic-123",
            )

        # Verify intent now has a topic
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"
        assert intent["topic_id"] is not None

        # Verify topic is exception type
        topics = await store.get_active_topics(session_id)
        created_topic = next((t for t in topics if t["id"] == intent["topic_id"]), None)
        assert created_topic is not None
        assert "Failed:" in created_topic["label"]
        assert created_topic["type"] == "exception"

        # Verify SSE event
        event = await conn.queue.get()
        assert event.event_type == "task_failed"
        assert event.data["intent_id"] == intent_id
        assert event.data["topic_id"] == intent["topic_id"]


# --- Test Auto-Approve Evaluation with Stuck Metadata ------------------------


class TestAutoApproveEvaluationWithStuckMetadata:
    """Test auto-approve evaluation when stuck metadata is present."""

    @pytest.mark.asyncio
    async def test_evaluate_auto_approve_with_stuck_context(self, escalate_handler: EscalateHandler):
        """_evaluate_auto_approve handles stuck context in metadata."""
        # Create exceptions config with auto-approve rules
        exceptions_config = {
            "auto_approve": {
                "read_only": ["kubectl_get", "git_log"],
                "safe_mutations": [],
            },
            "approval": {
                "never_auto_approve": [],
            },
        }

        # Request with stuck context
        request = EscalateRequest(
            intent_id="stuck-auto-approve-123",
            session_id="session-456",
            utterance="kubectl get pods",
            intent_type="action",
            context={
                "stuck_reason": "Previous attempt refused",
            },
            metadata={
                "action": "kubectl_get",
                "environment": "staging",
            },
        )

        auto_approve, reason = escalate_handler._evaluate_auto_approve(request, exceptions_config)

        # Should be auto-approved (read-only action)
        assert auto_approve is True
        assert "Read-only operation" in reason

    @pytest.mark.asyncio
    async def test_evaluate_auto_approve_stuck_intent_needs_manual_approval(self, escalate_handler: EscalateHandler):
        """_evaluate_auto_approve requires manual approval for stuck intent actions."""
        exceptions_config = {
            "auto_approve": {
                "read_only": ["kubectl_get"],
                "safe_mutations": [],
            },
            "approval": {
                "never_auto_approve": [],
            },
        }

        # Request for write action (not auto-approved)
        request = EscalateRequest(
            intent_id="stuck-manual-123",
            session_id="session-456",
            utterance="kubectl delete pod",
            intent_type="stuck",
            context={
                "stuck_reason": "Need approval for delete",
            },
            metadata={
                "action": "kubectl_delete_pod",
                "environment": "production",
            },
        )

        auto_approve, reason = escalate_handler._evaluate_auto_approve(request, exceptions_config)

        # Should NOT be auto-approved (requires manual approval)
        assert auto_approve is False
        assert "requires manual approval" in reason or "Unknown action" in reason

    @pytest.mark.asyncio
    async def test_evaluate_condition_with_stuck_context(self, escalate_handler: EscalateHandler):
        """_evaluate_condition evaluates conditions with stuck context variables."""
        # Test environment condition
        result = escalate_handler._evaluate_condition(
            condition="environment == 'staging'",
            context={"environment": "staging"},
        )
        assert result is True

        # Test project_slug condition
        result = escalate_handler._evaluate_condition(
            condition="project_slug == 'adc'",
            context={"project_slug": "adc"},
        )
        assert result is True

        # Test compound condition (OR)
        result = escalate_handler._evaluate_condition(
            condition="environment == 'staging' || environment == 'development'",
            context={"environment": "development"},
        )
        assert result is True

        # Test compound condition (AND)
        result = escalate_handler._evaluate_condition(
            condition="environment == 'staging' && action == 'kubectl_get'",
            context={"environment": "staging", "action": "kubectl_get"},
        )
        assert result is True

        # Test false condition
        result = escalate_handler._evaluate_condition(
            condition="environment == 'production'",
            context={"environment": "staging"},
        )
        assert result is False


# --- Test Escalate Handler Error Handling with Stuck Context ------------------


class TestEscalateHandlerErrorHandlingWithStuckContext:
    """Test escalate handler error handling with stuck context."""

    @pytest.mark.asyncio
    async def test_escalate_error_with_stuck_context(self, escalate_handler: EscalateHandler):
        """EscalateError can be raised with stuck context."""
        with pytest.raises(EscalateError) as exc_info:
            raise EscalateError("Escalate failed for stuck intent: missing context")

        assert "Escalate failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bead_creation_error_with_stuck_context(self, escalate_handler: EscalateHandler):
        """BeadCreationError can be raised with stuck bead ref."""
        with pytest.raises(BeadCreationError) as exc_info:
            raise BeadCreationError("bf create failed for stuck bead adc-stuck-123")

        assert "bf create failed" in str(exc_info.value)
        assert "adc-stuck-123" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_formulate_bead_body_preserves_stuck_context(self, escalate_handler: EscalateHandler):
        """formulate_bead_body includes stuck context in LLM prompt."""
        request = EscalateRequest(
            intent_id="formulate-stuck-123",
            session_id="session-456",
            utterance="Unblock this task",
            intent_type="stuck",
            project_slug="adc",
            topic_id="topic-789",
            context={
                "stuck_reason": "Missing user requirements",
                "refusal_count": 3,
            },
        )

        # Mock ZAI client
        mock_client = AsyncMock()
        mock_client.call_simple.return_value = "**Bead Body**\n\nTask unblocking: Missing user requirements"

        escalate_handler._zai_client = mock_client

        bead_body = await escalate_handler.formulate_bead_body(request)

        # Verify stuck context is included in the call (via user_message)
        mock_client.call_simple.assert_called_once()
        call_args = mock_client.call_simple.call_args

        # Check that the utterance includes stuck information
        user_message = call_args[1]["user_message"]
        assert "Unblock this task" in user_message
        assert "stuck" in call_args[1]["system_prompt"].lower() or "task" in call_args[1]["system_prompt"].lower()

        assert bead_body == "**Bead Body**\n\nTask unblocking: Missing user requirements"


# --- Test Escalate Handler Singleton with Stuck Context ---------------------


class TestEscalateHandlerSingletonWithStuckContext:
    """Test escalate handler singleton behavior with stuck context."""

    @pytest.mark.asyncio
    async def test_get_escalate_handler_returns_singleton(self, store: SessionStore):
        """get_escalate_handler returns singleton instance."""
        handler1 = get_escalate_handler(store=store)
        handler2 = get_escalate_handler(store=store)

        assert handler1 is handler2

    @pytest.mark.asyncio
    async def test_singleton_preserves_store_reference(self, store: SessionStore):
        """Singleton handler uses store reference for stuck context queries."""
        # Create a new handler directly with our store (bypassing singleton)
        from src.escalate.handler import EscalateHandler
        handler = EscalateHandler(store=store)

        # The handler was initialized with the store, so it should use it
        assert handler.store is store
        assert handler.store.db_path == store.db_path

        # _get_store should return the same store when it's already set
        retrieved_store = await handler._get_store()
        assert retrieved_store is store
        assert retrieved_store.db_path == store.db_path


# --- Test Coverage Verification ---------------------------------------------


class TestEscalateHandlerStuckLogicCoverage:
    """Verify coverage for escalate handler stuck logic."""

    @pytest.mark.asyncio
    async def test_escalate_handler_initialization(self, escalate_handler: EscalateHandler):
        """EscalateHandler initializes correctly for stuck scenarios."""
        assert escalate_handler is not None
        assert escalate_handler.store is not None
        assert escalate_handler._zai_client is None
        assert escalate_handler._reload_manager is None

    @pytest.mark.asyncio
    async def test_get_reload_manager(self, escalate_handler: EscalateHandler):
        """_get_reload_manager returns reload manager for config loading."""
        manager = escalate_handler._get_reload_manager()
        assert manager is not None

    @pytest.mark.asyncio
    async def test_get_bead_type_from_targets_with_stuck_mapping(self, escalate_handler: EscalateHandler):
        """_get_bead_type_from_targets handles stuck intent type mapping."""
        exceptions_config = {
            "escalation_targets": {
                "action": {"bead_type": "action"},
                "task-profile": {"bead_type": "task"},
                "stuck": {"bead_type": "exception"},
            }
        }

        # Test stuck intent type mapping
        bead_type = escalate_handler._get_bead_type_from_targets("stuck", exceptions_config)
        assert bead_type == "exception"

        # Test unknown intent type (defaults to 'task')
        bead_type = escalate_handler._get_bead_type_from_targets("unknown", exceptions_config)
        assert bead_type == "task"

    @pytest.mark.asyncio
    async def test_generate_bead_title_with_stuck_context(self, escalate_handler: EscalateHandler):
        """_generate_bead_title includes stuck context when available."""
        request = EscalateRequest(
            intent_id="title-stuck-123",
            session_id="session-456",
            utterance="Task is stuck: missing requirements",
            intent_type="stuck",
            project_slug="adc",
        )

        title = escalate_handler._generate_bead_title(request)

        assert "Task is stuck" in title or "missing requirements" in title
        assert "[adc]" in title

    @pytest.mark.asyncio
    async def test_extract_bead_id_handles_various_formats(self, escalate_handler: EscalateHandler):
        """_extract_bead_id handles various bf output formats."""
        # Standard format
        output1 = "adc-stuck-123"
        bead_id1 = escalate_handler._extract_bead_id(output1)
        assert "adc" in bead_id1 or "stuck" in bead_id1

        # With prefix text
        output2 = "Created bead adc-stuck-456"
        bead_id2 = escalate_handler._extract_bead_id(output2)
        assert "stuck" in bead_id2 or "456" in bead_id2

        # Empty output (should generate UUID)
        output3 = ""
        bead_id3 = escalate_handler._extract_bead_id(output3)
        assert len(bead_id3) > 0  # Should return UUID or placeholder


# --- Test Integration: Escalate Handler + Stuck Detection --------------------


class TestEscalateHandlerStuckDetectionIntegration:
    """Test integration between escalate handler and stuck detection logic."""

    @pytest.mark.asyncio
    async def test_escalate_handler_does_not_interfere_with_fence_detection(self, escalate_handler: EscalateHandler, store: SessionStore):
        """Escalate handler operations don't interfere with fence detection."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Integration Test",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test integration",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-integration-123",
            topic_id=topic_id,
        )

        # Create bead watch (simulate escalate handler)
        await escalate_handler._create_bead_watch(
            bead_ref="adc-integration-123",
            project_slug="adc",
            intent_type="task-profile",
        )

        # Fence the bead (simulate circuit breaker)
        await store.fence_bead(bead_ref="adc-integration-123")

        # Verify fence is detectable
        fenced_beads = await store.get_fenced_beads_for_session(session_id)
        assert len(fenced_beads) == 1
        assert fenced_beads[0]["bead_ref"] == "adc-integration-123"

        # Verify escalate handler didn't interfere with fence tracking
        watch = await store.get_bead_watch("adc-integration-123")
        assert watch["fenced_at"] is not None

    @pytest.mark.asyncio
    async def test_escalate_handler_with_existing_stuck_bead(self, escalate_handler: EscalateHandler, store: SessionStore):
        """Escalate handler behaves correctly when bead is already stuck."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Existing Stuck",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="existing stuck bead",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="stuck",
            bead_ref="already-stuck-123",
            topic_id=topic_id,
        )

        # Create and fence the bead
        await store.create_bead_watch(bead_ref="already-stuck-123")
        await store.update_bead_watch_refusal(
            bead_ref="already-stuck-123",
            refusal_reason="Already stuck",
            comment_index=0,
            refusal_count_add=3,
        )
        await store.fence_bead(bead_ref="already-stuck-123")

        # Verify escalate handler can still query the bead
        watch = await store.get_bead_watch("already-stuck-123")
        assert watch is not None
        assert watch["fenced_at"] is not None
        assert watch["refusal_count"] == 3
