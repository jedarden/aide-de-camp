"""
Comprehensive integration tests for stuck and failed card flows (bead adc-5i9kp).

This test suite provides complete end-to-end coverage for stuck and failed card functionality:

1. SSE broadcast on fence event
2. Stuck card creation in session store
3. Terminal failure detection and failed card creation
4. Canvas rendering of stuck/failed cards
5. Card dismissal functionality
6. Both 'stuck' and 'failed' intent coverage

Acceptance criteria:
- Test SSE broadcast on fence event
- Test stuck card creation in session store
- Test terminal failure detection and failed card creation
- Test canvas renders stuck/failed cards correctly
- Test card dismissal functionality
- All tests pass
- Coverage for both 'stuck' and 'failed' intents
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.session.store import SessionStore
from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEEvent,
    EventType,
    get_broadcaster,
)
from src.intent.router import IntentRouter, RoutedIntent, IntentClassification, IntentType
from src.escalate.handler import handle_terminal_failure


# --- Fixtures ------------------------------------------------------------------


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
def router(store: SessionStore) -> IntentRouter:
    """IntentRouter with test store."""
    return IntentRouter(store=store)


# --- 1. SSE Broadcast on Fence Event ------------------------------------------


class TestSSEBroadcastOnFenceEvent:
    """Test SSE broadcast behavior when fence events occur."""

    @pytest.mark.asyncio
    async def test_stuck_card_broadcasts_on_fence_event(self, router: IntentRouter, store: SessionStore):
        """Creating a stuck card from fence event broadcasts SSE event."""
        session_id = "test-session-fence"
        surface_id = "test-surface-fence"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="Implement stuck feature",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
        )

        classification = IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="adc",
            utterance_fragment="Implement stuck feature",
        )

        routed_intent = RoutedIntent(
            intent_id=intent_id,
            classification=classification,
            session_id=session_id,
            utterance="Implement stuck feature",
        )

        fence_context = {
            "bead_id": "adc-fence-stuck",
            "refusal_reason": "Missing requirements",
            "refusal_count": 3,
            "fenced_at": int(datetime.now(timezone.utc).timestamp()),
        }

        # Mock broadcaster to verify call
        broadcaster_mock = AsyncMock()
        broadcaster_mock.broadcast.return_value = 1

        with patch("src.intent.router.get_broadcaster", return_value=broadcaster_mock):
            result = await router._create_stuck_card_from_fence(
                routed_intent=routed_intent,
                fence_context=fence_context,
            )

        # Verify broadcast was called
        assert broadcaster_mock.broadcast.called, "broadcaster.broadcast() should be called"
        call_args = broadcaster_mock.broadcast.call_args
        event = call_args[0][0]

        assert isinstance(event, SSEEvent), "broadcast() should receive SSEEvent"
        assert event.event_type == EventType.TASK_STUCK, "Event type should be task_stuck"
        assert event.target_session_id == session_id, "Should target correct session"

    @pytest.mark.asyncio
    async def test_sse_event_contains_complete_stuck_data(self, router: IntentRouter, store: SessionStore):
        """SSE event for stuck card contains all required data fields."""
        session_id = "test-session-complete"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="Complete test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
        )

        classification = IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="adc",
            utterance_fragment="Complete test",
        )

        routed_intent = RoutedIntent(
            intent_id=intent_id,
            classification=classification,
            session_id=session_id,
            utterance="Complete test",
        )

        fence_context = {
            "bead_id": "adc-complete",
            "refusal_reason": "Test refusal",
            "refusal_count": 2,
            "fenced_at": int(datetime.now(timezone.utc).timestamp()),
        }

        broadcaster_mock = AsyncMock()
        captured_events = []

        async def capture_broadcast(event):
            captured_events.append(event)
            return 1

        broadcaster_mock.broadcast.side_effect = capture_broadcast

        with patch("src.intent.router.get_broadcaster", return_value=broadcaster_mock):
            await router._create_stuck_card_from_fence(
                routed_intent=routed_intent,
                fence_context=fence_context,
            )

        # Verify complete data
        assert len(captured_events) == 1
        event = captured_events[0]

        required_fields = ["bead_id", "stuck_reason", "refusal_count", "intent_id", "session_id", "timestamp"]
        for field in required_fields:
            assert field in event.data, f"Event data should include {field}"

        assert event.data["bead_id"] == "adc-complete"
        assert event.data["stuck_reason"] == "Test refusal"
        assert event.data["refusal_count"] == 2


# --- 2. Stuck Card Creation in Session Store ----------------------------------


class TestStuckCardCreationSessionStore:
    """Test stuck card creation and persistence in session store."""

    @pytest.mark.asyncio
    async def test_stuck_card_persists_with_correct_type_and_status(self, store: SessionStore):
        """Stuck cards persist with intent_type='stuck' and status='stuck'."""
        session_id = "test-session-stuck-persist"
        topic_id, _ = await store.find_or_create_topic(
            label="Stuck Topic",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test stuck",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-stuck-persist",
            topic_id=topic_id,
        )

        # Update to stuck
        await store.update_intent_type_and_status(
            intent_id=intent_id,
            intent_type="stuck",
            status="stuck",
        )

        # Create stuck result
        await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Task stuck — needs your input",
            data={
                "bead_id": "adc-stuck-persist",
                "stuck_reason": "Test refusal",
                "refusal_count": 3,
                "message": "This task has been blocked.",
            },
            urgency="high",
        )

        # Verify persistence
        intent = await store.get_intent(intent_id)
        assert intent["intent_type"] == "stuck"
        assert intent["status"] == "stuck"

        result = await store.get_latest_result_for_topic(topic_id)
        assert result is not None
        assert result["summary"] == "Task stuck — needs your input"

    @pytest.mark.asyncio
    async def test_stuck_card_queryable_via_session_api(self, store: SessionStore):
        """Stuck cards are queryable via session API."""
        session_id = "test-session-query"

        topic_id, _ = await store.find_or_create_topic(
            label="Query Topic",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test query",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-query",
            topic_id=topic_id,
        )

        await store.update_intent_type_and_status(
            intent_id=intent_id,
            intent_type="stuck",
            status="stuck",
        )

        await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Query test stuck",
            data={"bead_id": "adc-query", "stuck_reason": "Test"},
            urgency="high",
        )

        # Query via API
        topics = await store.get_active_topics(session_id)
        assert len(topics) >= 1

        topic = next((t for t in topics if t["id"] == topic_id), None)
        assert topic is not None
        assert topic["label"] == "Query Topic"


# --- 3. Terminal Failure Detection and Failed Card Creation ------------------


class TestTerminalFailureDetection:
    """Test terminal failure detection and failed card creation."""

    @pytest.mark.asyncio
    async def test_terminal_failure_creates_failed_card(self, store: SessionStore):
        """Terminal failure creates failed card in session store."""
        session_id = "test-session-failed"
        topic_id, _ = await store.find_or_create_topic(
            label="Failed Topic",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test failure",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
            topic_id=topic_id,
        )

        broadcaster_mock = AsyncMock()

        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster_mock), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Worker crashed",
                error_type="worker_crash",
                bead_ref="adc-failed",
            )

        # Verify intent status is failed
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

    @pytest.mark.asyncio
    async def test_failed_card_persists_with_all_fields(self, store: SessionStore):
        """Failed card persists with all required fields."""
        session_id = "test-session-persist"

        topic_id, _ = await store.find_or_create_topic(
            label="Persist Topic",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test persist",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
            topic_id=topic_id,
        )

        broadcaster_mock = AsyncMock()

        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster_mock), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Required sources failed",
                error_type="source_failure",
                bead_ref=None,
            )

        # Verify result contains failed card data
        result = await store.get_latest_result_for_topic(topic_id)
        assert result is not None
        assert result["summary"] == "Task Failed: Source Failure"
        assert result["urgency"] == "high"

    @pytest.mark.asyncio
    async def test_failed_card_without_topic_creates_topic(self, store: SessionStore):
        """handle_terminal_failure creates topic when topic_id is None."""
        session_id = "test-session-no-topic"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test without topic",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="status",
        )

        broadcaster_mock = AsyncMock()

        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster_mock), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=None,
                failure_reason="Invalid input",
                error_type="invalid_input",
                bead_ref=None,
            )

        # Verify intent status is failed
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

        # Verify topic was created
        intent = await store.get_intent(intent_id)
        created_topic_id = intent.get("topic_id")
        assert created_topic_id is not None


# --- 4. Canvas Renders Stuck/Failed Cards Correctly ---------------------------


class TestCanvasRendersStuckFailedCards:
    """Test canvas rendering of stuck and failed cards."""

    def test_canvas_has_stuck_card_listener(self):
        """Canvas has event listener for task_stuck events."""
        canvas_html = Path("/home/coding/aide-de-camp/src/canvas/index.html").read_text()
        assert "addEventListener('task_stuck'" in canvas_html
        assert "createStuckCard" in canvas_html

    def test_canvas_has_failed_card_listener(self):
        """Canvas has event listener for task_failed events."""
        canvas_html = Path("/home/coding/aide-de-camp/src/canvas/index.html").read_text()
        assert "addEventListener('task_failed'" in canvas_html
        assert "createFailedCard" in canvas_html

    def test_canvas_exports_stuck_card_function(self):
        """Canvas exports createStuckCard to window."""
        canvas_js = Path("/home/coding/aide-de-camp/src/canvas/canvas.js").read_text()
        assert "window.createStuckCard" in canvas_js

    def test_canvas_exports_failed_card_function(self):
        """Canvas exports createFailedCard to window."""
        canvas_js = Path("/home/coding/aide-de-camp/src/canvas/canvas.js").read_text()
        assert "window.createFailedCard" in canvas_js


# --- 5. Card Dismissal Functionality ------------------------------------------


class TestCardDismissalFunctionality:
    """Test card dismissal functionality for stuck and failed cards."""

    @pytest.mark.asyncio
    async def test_stuck_card_can_be_dismissed(self, store: SessionStore):
        """Stuck cards can be dismissed via API."""
        session_id = "test-session-dismiss"

        topic_id, _ = await store.find_or_create_topic(
            label="Dismiss Topic",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test dismiss",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-dismiss",
            topic_id=topic_id,
        )

        await store.update_intent_type_and_status(
            intent_id=intent_id,
            intent_type="stuck",
            status="stuck",
        )

        # Verify stuck status
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "stuck"

        # Simulate dismissal - update to cancelled
        await store.update_intent_status(intent_id=intent_id, status="cancelled")

        # Verify dismissed
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_failed_card_can_be_dismissed(self, store: SessionStore):
        """Failed cards can be dismissed via API."""
        session_id = "test-session-failed-dismiss"

        topic_id, _ = await store.find_or_create_topic(
            label="Failed Dismiss",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test failed dismiss",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
            topic_id=topic_id,
        )

        await store.update_intent_status(intent_id=intent_id, status="failed")

        # Verify failed status
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

        # Dismiss
        await store.update_intent_status(intent_id=intent_id, status="cancelled")

        # Verify dismissed
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "cancelled"


# --- 6. Coverage for Both 'stuck' and 'failed' Intents ----------------------


class TestBothIntentsCoverage:
    """Test coverage for both 'stuck' and 'failed' intent types."""

    @pytest.mark.asyncio
    async def test_stuck_intent_type_accepted(self, store: SessionStore):
        """Intent type 'stuck' is accepted."""
        session_id = "test-session-stuck-type"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
        )

        await store.update_intent_type_and_status(
            intent_id=intent_id,
            intent_type="stuck",
            status="stuck",
        )

        intent = await store.get_intent(intent_id)
        assert intent["intent_type"] == "stuck"
        assert intent["status"] == "stuck"

    @pytest.mark.asyncio
    async def test_failed_status_accepted(self, store: SessionStore):
        """Status 'failed' is accepted."""
        session_id = "test-session-failed-status"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
        )

        await store.update_intent_status(intent_id=intent_id, status="failed")

        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

    @pytest.mark.asyncio
    async def test_both_intents_have_distinct_event_types(self, broadcaster: SSEBroadcaster):
        """Stuck and failed intents use distinct SSE event types."""
        session_id = "test-session-both"

        conn = broadcaster.register(
            surface_id="surface-both",
            session_id=session_id,
            surface_type="canvas",
        )

        # Send stuck event
        stuck_event = SSEEvent(
            event_type=EventType.TASK_STUCK,
            data={"bead_id": "adc-stuck"},
            target_session_id=session_id,
        )
        await broadcaster.broadcast(stuck_event)

        received = await conn.queue.get()
        assert received.event_type == "task_stuck"

        # Send failed event
        failed_event = SSEEvent(
            event_type=EventType.TASK_FAILED,
            data={"intent_id": "intent-failed"},
            target_session_id=session_id,
        )
        await broadcaster.broadcast(failed_event)

        received = await conn.queue.get()
        assert received.event_type == "task_failed"


# --- 7. Integration Scenarios -------------------------------------------------


class TestIntegrationScenarios:
    """Test complete integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_stuck_card_flow(self, router: IntentRouter, store: SessionStore):
        """Complete flow: fence → stuck card → broadcast → canvas render."""
        session_id = "test-session-flow-stuck"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="Full flow test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
        )

        classification = IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="adc",
            utterance_fragment="Full flow test",
        )

        routed_intent = RoutedIntent(
            intent_id=intent_id,
            classification=classification,
            session_id=session_id,
            utterance="Full flow test",
        )

        fence_context = {
            "bead_id": "adc-flow-stuck",
            "refusal_reason": "Flow test refusal",
            "refusal_count": 3,
            "fenced_at": int(datetime.now(timezone.utc).timestamp()),
        }

        broadcaster_mock = AsyncMock()
        captured_events = []

        async def capture_broadcast(event):
            captured_events.append(event)
            return 1

        broadcaster_mock.broadcast.side_effect = capture_broadcast

        with patch("src.intent.router.get_broadcaster", return_value=broadcaster_mock):
            result = await router._create_stuck_card_from_fence(
                routed_intent=routed_intent,
                fence_context=fence_context,
            )

        # Verify complete flow
        assert result["intent_id"] == intent_id
        assert result["intent_type"] == "stuck"
        assert result["status"] == "stuck"
        assert len(captured_events) == 1
        assert captured_events[0].event_type == EventType.TASK_STUCK

    @pytest.mark.asyncio
    async def test_full_failed_card_flow(self, store: SessionStore):
        """Complete flow: terminal failure → failed card → broadcast."""
        session_id = "test-session-flow-failed"

        topic_id, _ = await store.find_or_create_topic(
            label="Flow Failed",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="Flow failed test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
            topic_id=topic_id,
        )

        broadcaster_mock = AsyncMock()
        captured_events = []

        async def capture_broadcast(event):
            captured_events.append(event)
            return 1

        broadcaster_mock.broadcast.side_effect = capture_broadcast

        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster_mock), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Flow test failure",
                error_type="flow_test",
                bead_ref="adc-flow-failed",
            )

        # Verify complete flow
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

        assert len(captured_events) == 1
        assert captured_events[0].event_type == EventType.TASK_FAILED
