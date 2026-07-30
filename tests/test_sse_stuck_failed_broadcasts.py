"""
Comprehensive SSE broadcast tests for stuck and failed card events (bead adc-5fhqo).

This test suite verifies SSE broadcasting behavior for stuck and failed cards:
- broadcaster.broadcast() is called during stuck/failed card creation
- SSEEvent contains correct event_type ('task_stuck'/'task_failed')
- SSEEvent targets correct surface_id and session_id
- SSEEvent includes complete card data in payload
- Multiple connections receive appropriate events
- Surface filtering and exclusion work correctly

Acceptance criteria:
- Test broadcaster.broadcast() is called on stuck card creation
- Test broadcaster.broadcast() is called on failed card creation
- Test SSEEvent contains correct event_type ('task_stuck'/'task_failed')
- Test SSEEvent targets correct surface_id
- Test SSEEvent includes card data in payload
- All tests pass
- Coverage for sse/broadcaster.py
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
def router(store: SessionStore) -> IntentRouter:
    """IntentRouter with test store."""
    return IntentRouter(store=store)


# --- Test broadcaster.broadcast() is called on stuck card creation ---------


class TestStuckCardBroadcastCalls:
    """Test that broadcaster.broadcast() is called when stuck cards are created."""

    @pytest.mark.asyncio
    async def test_stuck_card_creation_calls_broadcast(self, router: IntentRouter, store: SessionStore):
        """Creating a stuck card calls broadcaster.broadcast() with correct parameters."""
        session_id = "test-session-stuck"
        surface_id = "test-surface-stuck"

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
            "bead_id": "adc-stuck123",
            "refusal_reason": "Missing requirements",
            "refusal_count": 3,
            "fenced_at": int(datetime.now(timezone.utc).timestamp()),
        }

        # Mock broadcaster to verify it was called
        broadcaster_mock = AsyncMock()
        broadcaster_mock.broadcast.return_value = 1

        with patch("src.intent.router.get_broadcaster", return_value=broadcaster_mock):
            result = await router._create_stuck_card_from_fence(
                routed_intent=routed_intent,
                fence_context=fence_context,
            )

        # Verify broadcast was called
        assert broadcaster_mock.broadcast.called, "broadcaster.broadcast() should be called"
        assert broadcaster_mock.broadcast.call_count == 1

        # Verify call parameters
        call_args = broadcaster_mock.broadcast.call_args
        event = call_args[0][0]  # First positional argument is the SSEEvent

        assert isinstance(event, SSEEvent), "broadcast() should receive SSEEvent"
        assert event.event_type == EventType.TASK_STUCK, "Event type should be task_stuck"
        assert event.target_session_id == session_id, "Should target correct session"

    @pytest.mark.asyncio
    async def test_stuck_card_broadcast_event_data_complete(self, router: IntentRouter, store: SessionStore):
        """Stuck card broadcast includes all required card data in payload."""
        session_id = "test-session-data"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="Test stuck data",
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
            utterance_fragment="Test stuck data",
        )

        routed_intent = RoutedIntent(
            intent_id=intent_id,
            classification=classification,
            session_id=session_id,
            utterance="Test stuck data",
        )

        fence_context = {
            "bead_id": "adc-data456",
            "refusal_reason": "Test refusal",
            "refusal_count": 2,
            "fenced_at": int(datetime.now(timezone.utc).timestamp()),
        }

        # Capture broadcast call
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

        # Verify event data completeness
        assert len(captured_events) == 1
        event = captured_events[0]

        # Required fields for stuck card payload
        required_fields = ["bead_id", "stuck_reason", "refusal_count", "intent_id", "session_id", "timestamp"]
        for field in required_fields:
            assert field in event.data, f"Event data should include {field}"

        assert event.data["bead_id"] == "adc-data456"
        assert event.data["stuck_reason"] == "Test refusal"
        assert event.data["refusal_count"] == 2
        assert event.data["intent_id"] == intent_id
        assert event.data["session_id"] == session_id


# --- Test broadcaster.broadcast() is called on failed card creation --------


class TestFailedCardBroadcastCalls:
    """Test that broadcaster.broadcast() is called when failed cards are created."""

    @pytest.mark.asyncio
    async def test_failed_card_creation_calls_broadcast(self, store: SessionStore):
        """Creating a failed card calls broadcaster.broadcast() with correct parameters."""
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

        # Mock broadcaster to verify it was called
        broadcaster_mock = AsyncMock()
        broadcaster_mock.broadcast.return_value = 1

        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster_mock), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Worker crashed",
                error_type="worker_crash",
                bead_ref="adc-failed123",
            )

        # Verify broadcast was called
        assert broadcaster_mock.broadcast.called, "broadcaster.broadcast() should be called"
        assert broadcaster_mock.broadcast.call_count == 1

        # Verify call parameters
        call_args = broadcaster_mock.broadcast.call_args
        event = call_args[0][0]  # First positional argument is the SSEEvent

        assert isinstance(event, SSEEvent), "broadcast() should receive SSEEvent"
        assert event.event_type == EventType.TASK_FAILED, "Event type should be task_failed"
        assert event.target_session_id == session_id, "Should target correct session"

    @pytest.mark.asyncio
    async def test_failed_card_broadcast_event_data_complete(self, store: SessionStore):
        """Failed card broadcast includes all required card data in payload."""
        session_id = "test-session-payload"
        topic_id, _ = await store.find_or_create_topic(
            label="Failed Payload",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test payload",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
            topic_id=topic_id,
        )

        # Capture broadcast call
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
                failure_reason="Invalid input provided",
                error_type="invalid_input",
                bead_ref="adc-payload789",
            )

        # Verify event data completeness
        assert len(captured_events) == 1
        event = captured_events[0]

        # Required fields for failed card payload
        required_fields = ["bead_id", "intent_id", "session_id", "topic_id",
                          "failure_reason", "error_type", "message", "timestamp"]
        for field in required_fields:
            assert field in event.data, f"Event data should include {field}"

        assert event.data["bead_id"] == "adc-payload789"
        assert event.data["intent_id"] == intent_id
        assert event.data["session_id"] == session_id
        assert event.data["topic_id"] == topic_id
        assert event.data["failure_reason"] == "Invalid input provided"
        assert event.data["error_type"] == "invalid_input"
        assert "Task failed" in event.data["message"]


# --- Test SSEEvent contains correct event_type --------------------------------


class TestSSEEventTypes:
    """Test that SSEEvent uses correct event types."""

    @pytest.mark.asyncio
    async def test_stuck_card_event_type_is_task_stuck(self, broadcaster: SSEBroadcaster):
        """Stuck card SSEEvent has event_type='task_stuck'."""
        session_id = "test-session-type"

        conn = broadcaster.register(
            surface_id="surface-type",
            session_id=session_id,
            surface_type="canvas",
        )

        event = SSEEvent(
            event_type=EventType.TASK_STUCK,
            data={
                "bead_id": "adc-type123",
                "stuck_reason": "Test",
                "refusal_count": 1,
            },
            target_session_id=session_id,
        )

        await broadcaster.broadcast(event)

        # Verify received event has correct type
        received = await conn.queue.get()
        assert received.event_type == "task_stuck", "Event type should be 'task_stuck'"
        assert received.event_type == EventType.TASK_STUCK

    @pytest.mark.asyncio
    async def test_failed_card_event_type_is_task_failed(self, broadcaster: SSEBroadcaster):
        """Failed card SSEEvent has event_type='task_failed'."""
        session_id = "test-session-type-f"

        conn = broadcaster.register(
            surface_id="surface-type-f",
            session_id=session_id,
            surface_type="canvas",
        )

        event = SSEEvent(
            event_type=EventType.TASK_FAILED,
            data={
                "intent_id": "intent-123",
                "failure_reason": "Test failure",
                "error_type": "test_error",
            },
            target_session_id=session_id,
        )

        await broadcaster.broadcast(event)

        # Verify received event has correct type
        received = await conn.queue.get()
        assert received.event_type == "task_failed", "Event type should be 'task_failed'"
        assert received.event_type == EventType.TASK_FAILED


# --- Test SSEEvent targets correct surface_id --------------------------------


class TestSurfaceIDTargeting:
    """Test that SSEEvent targets correct surface_id."""

    @pytest.mark.asyncio
    async def test_broadcast_to_specific_surface_id(self, broadcaster: SSEBroadcaster):
        """Broadcast with target_surface_id sends only to that surface."""
        session_id = "test-session-surface"

        # Register multiple surfaces for same session
        conn_1 = broadcaster.register(
            surface_id="surface-1",
            session_id=session_id,
            surface_type="canvas",
        )

        conn_2 = broadcaster.register(
            surface_id="surface-2",
            session_id=session_id,
            surface_type="canvas",
        )

        conn_3 = broadcaster.register(
            surface_id="surface-3",
            session_id=session_id,
            surface_type="telegram",
        )

        # Broadcast targeting only surface-2
        event = SSEEvent(
            event_type=EventType.TASK_STUCK,
            data={"bead_id": "adc-target123"},
            target_session_id=session_id,
            target_surface_id="surface-2",  # Only this surface
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1, "Only one surface should receive event"

        # Verify only surface-2 received it
        received_2 = await conn_2.queue.get()
        assert received_2.data["bead_id"] == "adc-target123"

        # Other surfaces should not have received it
        assert conn_1.queue.empty(), "surface-1 should not receive event"
        assert conn_3.queue.empty(), "surface-3 should not receive event"

    @pytest.mark.asyncio
    async def test_broadcast_excludes_specific_surface_id(self, broadcaster: SSEBroadcaster):
        """Broadcast with exclude_surface_id sends to all except that surface."""
        session_id = "test-session-exclude"

        conn_1 = broadcaster.register(
            surface_id="surface-exclude-1",
            session_id=session_id,
            surface_type="canvas",
        )

        conn_2 = broadcaster.register(
            surface_id="surface-exclude-2",
            session_id=session_id,
            surface_type="canvas",
        )

        # Broadcast excluding surface-exclude-1
        event = SSEEvent(
            event_type=EventType.TASK_FAILED,
            data={"intent_id": "intent-exclude"},
            target_session_id=session_id,
            exclude_surface_id="surface-exclude-1",  # Exclude this one
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1, "Only one surface should receive event"

        # Verify only surface-2 received it
        received_2 = await conn_2.queue.get()
        assert received_2.data["intent_id"] == "intent-exclude"

        # surface-1 should not have received it
        assert conn_1.queue.empty(), "surface-exclude-1 should not receive event"


# --- Test SSEEvent includes card data in payload ------------------------------


class TestEventPayloadData:
    """Test that SSEEvent includes complete card data in payload."""

    @pytest.mark.asyncio
    async def test_stuck_card_payload_has_all_fields(self, broadcaster: SSEBroadcaster):
        """Stuck card event payload contains all required card data."""
        session_id = "test-session-payload-stuck"

        conn = broadcaster.register(
            surface_id="surface-payload-stuck",
            session_id=session_id,
            surface_type="canvas",
        )

        # Full stuck card payload
        event = SSEEvent(
            event_type=EventType.TASK_STUCK,
            data={
                "bead_id": "adc-stuck-full",
                "stuck_reason": "Missing requirements: user authentication",
                "refusal_count": 5,
                "intent_id": "intent-stuck-123",
                "session_id": session_id,
                "topic_id": "topic-stuck-456",
                "message": "This task has been blocked after 5 refusals.",
                "action_hint": "Review the bead and provide missing information.",
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
            },
            target_session_id=session_id,
        )

        await broadcaster.broadcast(event)

        # Verify payload integrity
        received = await conn.queue.get()

        assert received.data["bead_id"] == "adc-stuck-full"
        assert received.data["stuck_reason"] == "Missing requirements: user authentication"
        assert received.data["refusal_count"] == 5
        assert received.data["intent_id"] == "intent-stuck-123"
        assert received.data["session_id"] == session_id
        assert received.data["topic_id"] == "topic-stuck-456"
        assert "blocked" in received.data["message"]
        assert "Review" in received.data["action_hint"]
        assert received.data["timestamp"] > 0

    @pytest.mark.asyncio
    async def test_failed_card_payload_has_all_fields(self, broadcaster: SSEBroadcaster):
        """Failed card event payload contains all required card data."""
        session_id = "test-session-payload-failed"

        conn = broadcaster.register(
            surface_id="surface-payload-failed",
            session_id=session_id,
            surface_type="canvas",
        )

        # Full failed card payload
        event = SSEEvent(
            event_type=EventType.TASK_FAILED,
            data={
                "bead_id": "adc-failed-full",
                "intent_id": "intent-failed-123",
                "session_id": session_id,
                "topic_id": "topic-failed-456",
                "failure_reason": "Worker process crashed unexpectedly",
                "error_type": "worker_crash",
                "message": "Task failed: Worker process crashed unexpectedly",
                "action_hint": "This task encountered a terminal error and cannot proceed.",
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
            },
            target_session_id=session_id,
        )

        await broadcaster.broadcast(event)

        # Verify payload integrity
        received = await conn.queue.get()

        assert received.data["bead_id"] == "adc-failed-full"
        assert received.data["intent_id"] == "intent-failed-123"
        assert received.data["session_id"] == session_id
        assert received.data["topic_id"] == "topic-failed-456"
        assert received.data["failure_reason"] == "Worker process crashed unexpectedly"
        assert received.data["error_type"] == "worker_crash"
        assert "Task failed" in received.data["message"]
        assert "terminal error" in received.data["action_hint"]
        assert received.data["timestamp"] > 0


# --- Test multiple connections and sessions ----------------------------------


class TestMultipleConnections:
    """Test SSE broadcasting with multiple connections and sessions."""

    @pytest.mark.asyncio
    async def test_stuck_event_sent_to_all_session_surfaces(self, broadcaster: SSEBroadcaster):
        """Stuck event sent to all surfaces in the same session."""
        session_id = "test-session-multi"

        # Multiple surfaces in same session
        conn_canvas = broadcaster.register(
            surface_id="surface-canvas",
            session_id=session_id,
            surface_type="canvas",
        )

        conn_telegram = broadcaster.register(
            surface_id="surface-telegram",
            session_id=session_id,
            surface_type="telegram",
        )

        event = SSEEvent(
            event_type=EventType.TASK_STUCK,
            data={"bead_id": "adc-multi123"},
            target_session_id=session_id,
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 2, "Both surfaces should receive event"

        # Both should receive the event
        received_canvas = await conn_canvas.queue.get()
        received_telegram = await conn_telegram.queue.get()

        assert received_canvas.data["bead_id"] == "adc-multi123"
        assert received_telegram.data["bead_id"] == "adc-multi123"

    @pytest.mark.asyncio
    async def test_failed_event_session_isolation(self, broadcaster: SSEBroadcaster):
        """Failed event only sent to target session, not others."""
        session_a = "session-a-isolated"
        session_b = "session-b-isolated"

        conn_a = broadcaster.register(
            surface_id="surface-a",
            session_id=session_a,
            surface_type="canvas",
        )

        conn_b = broadcaster.register(
            surface_id="surface-b",
            session_id=session_b,
            surface_type="canvas",
        )

        event = SSEEvent(
            event_type=EventType.TASK_FAILED,
            data={"intent_id": "intent-iso-123"},
            target_session_id=session_a,  # Only session A
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1, "Only session A should receive event"

        # Only session A should receive
        received_a = await conn_a.queue.get()
        assert received_a.data["intent_id"] == "intent-iso-123"

        # Session B should not receive
        assert conn_b.queue.empty(), "Session B should not receive event"


# --- Test broadcaster functionality coverage ----------------------------------


class TestBroadcasterFunctionality:
    """Test core SSEBroadcaster functionality for stuck/failed events."""

    @pytest.mark.asyncio
    async def test_broadcaster_register_and_unregister(self, broadcaster: SSEBroadcaster):
        """Can register and unregister connections."""
        session_id = "test-session-reg"

        conn = broadcaster.register(
            surface_id="surface-reg",
            session_id=session_id,
            surface_type="canvas",
        )

        assert conn.connection_id in broadcaster.connections
        assert broadcaster.connections[conn.connection_id].surface_id == "surface-reg"

        # Unregister
        broadcaster.unregister(conn.connection_id)
        assert conn.connection_id not in broadcaster.connections

    @pytest.mark.asyncio
    async def test_broadcaster_returns_correct_sent_count(self, broadcaster: SSEBroadcaster):
        """broadcast() returns count of connections event was sent to."""
        session_id = "test-session-count"

        # Register 3 connections
        broadcaster.register(surface_id="s1", session_id=session_id, surface_type="canvas")
        broadcaster.register(surface_id="s2", session_id=session_id, surface_type="canvas")
        broadcaster.register(surface_id="s3", session_id="other-session", surface_type="canvas")

        event = SSEEvent(
            event_type=EventType.TASK_STUCK,
            data={"bead_id": "adc-count123"},
            target_session_id=session_id,
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 2, "Should send to 2 connections in target session"

    @pytest.mark.asyncio
    async def test_broadcaster_with_no_matching_connections(self, broadcaster: SSEBroadcaster):
        """broadcast() handles no matching connections gracefully."""
        event = SSEEvent(
            event_type=EventType.TASK_FAILED,
            data={"intent_id": "intent-nomatch"},
            target_session_id="nonexistent-session",
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 0, "No connections should match"

    @pytest.mark.asyncio
    async def test_global_broadcaster_singleton(self):
        """get_broadcaster() returns same instance."""
        b1 = get_broadcaster()
        b2 = get_broadcaster()

        assert b1 is b2, "Should return same singleton instance"
        assert isinstance(b1, SSEBroadcaster)


# --- Test event type constants -----------------------------------------------


class TestEventTypeConstants:
    """Test EventType constants are correctly defined."""

    def test_task_stuck_constant(self):
        """EventType.TASK_STUCK is 'task_stuck'."""
        assert EventType.TASK_STUCK == "task_stuck"

    def test_task_failed_constant(self):
        """EventType.TASK_FAILED is 'task_failed'."""
        assert EventType.TASK_FAILED == "task_failed"

    def test_event_type_values_are_strings(self):
        """EventType values are strings suitable for SSE."""
        assert isinstance(EventType.TASK_STUCK, str)
        assert isinstance(EventType.TASK_FAILED, str)
        assert len(EventType.TASK_STUCK) > 0
        assert len(EventType.TASK_FAILED) > 0
