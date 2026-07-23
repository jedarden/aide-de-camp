"""
Backend unit tests for stuck and failed card creation and SSE broadcast (bead adc-2cjdj).

This suite tests the core backend logic:
- Intent router fence detection and stuck card creation
- Session store operations for stuck/failed cards
- Terminal failure detection and handling
- SSE broadcaster operations for stuck/failed events

These are hermetic, unit-level backend tests that verify the core operations
without involving the full request/response cycle.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from datetime import datetime, timezone

from src.session.store import SessionStore
from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEEvent,
    EventType,
)
from src.intent.router import (
    IntentRouter,
    IntentType,
    IntentClassification,
    RoutedIntent,
)
from src.escalate.handler import (
    handle_terminal_failure,
)


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


# --- Test Session Store Operations for Stuck Cards ---------------------------


class TestSessionStoreStuckCardOperations:
    """Test session.store operations for stuck card creation."""

    @pytest.mark.asyncio
    async def test_create_utterance_returns_id(self, store: SessionStore):
        """create_utterance returns a valid utterance ID."""
        session_id = "test-session"
        raw_text = "test utterance"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text=raw_text,
        )

        assert utterance_id is not None
        assert isinstance(utterance_id, str)
        assert len(utterance_id) > 0

    @pytest.mark.asyncio
    async def test_find_or_create_topic_returns_tuple(self, store: SessionStore):
        """find_or_create_topic returns (topic_id, created) tuple."""
        session_id = "test-session"

        topic_id, created = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="project",
        )

        assert topic_id is not None
        assert isinstance(topic_id, str)
        assert isinstance(created, bool)
        # First call should create
        assert created is True

        # Second call should find existing
        topic_id2, created2 = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="project",
        )
        assert topic_id2 == topic_id
        assert created2 is False

    @pytest.mark.asyncio
    async def test_update_intent_type_and_status_to_stuck(self, store: SessionStore):
        """update_intent_type_and_status can set intent to stuck."""
        session_id = "test-session"
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

        # Update to stuck
        await store.update_intent_type_and_status(
            intent_id=intent_id,
            intent_type="stuck",
            status="stuck",
        )

        # Verify
        intent = await store.get_intent(intent_id)
        assert intent["intent_type"] == "stuck"
        assert intent["status"] == "stuck"

    @pytest.mark.asyncio
    async def test_link_intent_to_topic(self, store: SessionStore):
        """link_intent_to_topic creates many-to-many relationship."""
        import aiosqlite
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="project",
        )
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

        # Link intent to topic
        await store.link_intent_to_topic(intent_id, topic_id)

        # Verify the link was created in intent_topics
        async with aiosqlite.connect(store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM intent_topics WHERE intent_id = ? AND topic_id = ?",
                (intent_id, topic_id)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None
                assert row["intent_id"] == intent_id
                assert row["topic_id"] == topic_id

    @pytest.mark.asyncio
    async def test_create_result_for_stuck_card(self, store: SessionStore):
        """create_result stores stuck card data correctly."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="project",
        )

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

        # Create stuck result
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Task stuck — needs your input",
            data={
                "bead_id": "adc-stuck123",
                "stuck_reason": "Test refusal",
                "refusal_count": 3,
                "message": "This task has been blocked after 3 refusals.",
                "action_hint": "Review the bead and provide missing information.",
            },
            urgency="high",
        )

        assert result_id is not None

        # Verify result
        result = await store.get_latest_result_for_topic(topic_id)
        assert result is not None
        assert result["id"] == result_id
        assert result["summary"] == "Task stuck — needs your input"
        assert result["urgency"] == "high"

        result_data = json.loads(result["data"])
        assert result_data["bead_id"] == "adc-stuck123"
        assert result_data["stuck_reason"] == "Test refusal"
        assert result_data["refusal_count"] == 3

    @pytest.mark.asyncio
    async def test_create_bead_watch_for_tracking(self, store: SessionStore):
        """create_bead_watch initializes circuit breaker tracking."""
        bead_ref = "adc-test123"

        await store.create_bead_watch(
            bead_ref=bead_ref,
            sla_hours=6,
            intent_type="task-profile",
        )

        # Verify watch row created
        watch = await store.get_bead_watch(bead_ref)
        assert watch is not None
        assert watch["bead_ref"] == bead_ref
        assert watch["refusal_count"] == 0
        assert watch["comment_high_water"] == -1
        assert watch["sla_deadline"] is not None
        assert watch["fenced_at"] is None

    @pytest.mark.asyncio
    async def test_fence_bead_sets_fenced_at(self, store: SessionStore):
        """fence_bead sets fenced_at timestamp."""
        bead_ref = "adc-fence123"

        await store.create_bead_watch(
            bead_ref=bead_ref,
            sla_hours=6,
            intent_type="task-profile",
        )

        # Fence the bead
        await store.fence_bead(bead_ref)

        # Verify fenced_at is set
        watch = await store.get_bead_watch(bead_ref)
        assert watch is not None
        assert watch["fenced_at"] is not None
        assert watch["fenced_at"] > 0

    @pytest.mark.asyncio
    async def test_get_fenced_beads_for_session(self, store: SessionStore):
        """get_fenced_beads_for_session returns fenced beads."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Test",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-fenced",
            topic_id=topic_id,
        )

        await store.create_bead_watch(bead_ref="adc-fenced", sla_hours=6)
        await store.fence_bead(bead_ref="adc-fenced")

        # Get fenced beads
        fenced = await store.get_fenced_beads_for_session(session_id)

        assert len(fenced) == 1
        assert fenced[0]["bead_ref"] == "adc-fenced"
        assert fenced[0]["intent_id"] == intent_id
        assert fenced[0]["topic_id"] == topic_id


# --- Test Session Store Operations for Failed Cards --------------------------


class TestSessionStoreFailedCardOperations:
    """Test session.store operations for failed card creation."""

    @pytest.mark.asyncio
    async def test_update_intent_status_to_failed(self, store: SessionStore):
        """update_intent_status can set intent to failed."""
        session_id = "test-session"
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

        # Update to failed
        await store.update_intent_status(
            intent_id=intent_id,
            status="failed",
        )

        # Verify
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

    @pytest.mark.asyncio
    async def test_create_result_for_failed_card(self, store: SessionStore):
        """create_result stores failed card data correctly."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Failed Topic",
            session_id=session_id,
            topic_type="exception",
        )

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

        # Create failed result
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Task Failed: Worker Crash",
            data={
                "bead_ref": "adc-fail123",
                "failure_reason": "Worker process crashed",
                "error_type": "worker_crash",
                "message": "Task failed: Worker process crashed",
                "action_hint": "Review the error details and retry if applicable.",
            },
            urgency="high",
        )

        assert result_id is not None

        # Verify result
        result = await store.get_latest_result_for_topic(topic_id)
        assert result is not None
        assert result["id"] == result_id
        assert result["summary"] == "Task Failed: Worker Crash"
        assert result["urgency"] == "high"

        result_data = json.loads(result["data"])
        assert result_data["bead_ref"] == "adc-fail123"
        assert result_data["failure_reason"] == "Worker process crashed"
        assert result_data["error_type"] == "worker_crash"

    @pytest.mark.asyncio
    async def test_bead_watch_refusal_update(self, store: SessionStore):
        """update_bead_watch_refusal increments refusal count."""
        bead_ref = "adc-refusal123"

        await store.create_bead_watch(
            bead_ref=bead_ref,
            sla_hours=6,
            intent_type="task-profile",
        )

        # Add refusal
        await store.update_bead_watch_refusal(
            bead_ref=bead_ref,
            refusal_reason="Test refusal",
            comment_index=0,
            refusal_count_add=1,
        )

        # Verify
        watch = await store.get_bead_watch(bead_ref)
        assert watch["refusal_count"] == 1
        assert watch["last_refusal_reason"] == "Test refusal"
        assert watch["last_refusal_at"] is not None
        assert watch["comment_high_water"] == 0


# --- Test SSE Broadcaster Operations ------------------------------------------


class TestSSEBroadcasterStuckFailedEvents:
    """Test SSE broadcaster operations for stuck/failed events."""

    @pytest.mark.asyncio
    async def test_broadcast_stuck_event(self, broadcaster: SSEBroadcaster):
        """broadcast sends task_stuck event to connections."""
        session_id = "test-session"

        # Register connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Broadcast stuck event
        sent_count = await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.TASK_STUCK,
                data={
                    "bead_id": "adc-stuck123",
                    "stuck_reason": "Test refusal",
                    "refusal_count": 3,
                    "message": "Task blocked after refusals",
                    "timestamp": int(datetime.now(timezone.utc).timestamp()),
                },
                target_session_id=session_id,
            )
        )

        assert sent_count == 1

        # Verify event received
        event = await conn.queue.get()
        assert event.event_type == "task_stuck"
        assert event.data["bead_id"] == "adc-stuck123"
        assert event.data["stuck_reason"] == "Test refusal"
        assert event.data["refusal_count"] == 3

    @pytest.mark.asyncio
    async def test_broadcast_failed_event(self, broadcaster: SSEBroadcaster):
        """broadcast sends task_failed event to connections."""
        session_id = "test-session"

        # Register connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Broadcast failed event
        sent_count = await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.TASK_FAILED,
                data={
                    "intent_id": "intent-123",
                    "failure_reason": "Worker crashed",
                    "error_type": "worker_crash",
                    "message": "Task failed: Worker crashed",
                    "timestamp": int(datetime.now(timezone.utc).timestamp()),
                },
                target_session_id=session_id,
            )
        )

        assert sent_count == 1

        # Verify event received
        event = await conn.queue.get()
        assert event.event_type == "task_failed"
        assert event.data["intent_id"] == "intent-123"
        assert event.data["failure_reason"] == "Worker crashed"
        assert event.data["error_type"] == "worker_crash"

    @pytest.mark.asyncio
    async def test_broadcast_with_target_filtering(self, broadcaster: SSEBroadcaster):
        """broadcast respects target_session_id filtering."""
        session_a = "session-a"
        session_b = "session-b"

        # Register connections for different sessions
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

        # Broadcast to session_a only
        sent_count = await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.TASK_STUCK,
                data={"bead_id": "adc-test"},
                target_session_id=session_a,
            )
        )

        assert sent_count == 1

        # Verify only session_a received
        event_a = await conn_a.queue.get()
        assert event_a.event_type == "task_stuck"

        # session_b queue should be empty
        assert conn_b.queue.empty()

    @pytest.mark.asyncio
    async def test_broadcast_with_exclude_surface(self, broadcaster: SSEBroadcaster):
        """broadcast respects exclude_surface_id filtering."""
        session_id = "test-session"

        # Register two connections
        conn_1 = broadcaster.register(
            surface_id="surface-1",
            session_id=session_id,
            surface_type="canvas",
        )

        conn_2 = broadcaster.register(
            surface_id="surface-2",
            session_id=session_id,
            surface_type="telegram",
        )

        # Broadcast excluding surface-1
        sent_count = await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.TASK_STUCK,
                data={"bead_id": "adc-test"},
                target_session_id=session_id,
                exclude_surface_id="surface-1",
            )
        )

        assert sent_count == 1

        # Verify only surface-2 received
        event_2 = await conn_2.queue.get()
        assert event_2.event_type == "task_stuck"

        # surface-1 queue should be empty
        assert conn_1.queue.empty()


# --- Test Intent Router Fence Detection --------------------------------------


class TestIntentRouterFenceDetection:
    """Test intent router fence detection logic."""

    @pytest.mark.asyncio
    async def test_check_fence_for_bead_fenced(self, router: IntentRouter, store: SessionStore):
        """_check_fence_for_bead returns context for fenced bead."""
        bead_ref = "adc-fenced123"

        # Create bead watch with fence
        await store.create_bead_watch(
            bead_ref=bead_ref,
            sla_hours=6,
            intent_type="task-profile",
        )
        await store.update_bead_watch_refusal(
            bead_ref=bead_ref,
            refusal_reason="Test refusal",
            comment_index=0,
            refusal_count_add=3,
        )
        await store.fence_bead(bead_ref)

        # Check fence
        fence_context = await router._check_fence_for_bead(bead_ref)

        assert fence_context is not None
        assert fence_context["bead_id"] == bead_ref
        assert fence_context["refusal_reason"] == "Test refusal"
        assert fence_context["refusal_count"] == 3
        assert fence_context["fenced_at"] is not None

    @pytest.mark.asyncio
    async def test_check_fence_for_bead_not_fenced(self, router: IntentRouter, store: SessionStore):
        """_check_fence_for_bead returns None for unfenced bead."""
        bead_ref = "adc-unfenced123"

        # Create bead watch without fence
        await store.create_bead_watch(
            bead_ref=bead_ref,
            sla_hours=6,
            intent_type="task-profile",
        )

        # Check fence
        fence_context = await router._check_fence_for_bead(bead_ref)

        assert fence_context is None

    @pytest.mark.asyncio
    async def test_check_fence_for_bead_no_watch(self, router: IntentRouter):
        """_check_fence_for_bead returns None when bead not watched."""
        fence_context = await router._check_fence_for_bead("adc-nonexistent")

        assert fence_context is None

    @pytest.mark.asyncio
    async def test_create_stuck_card_from_fence(self, router: IntentRouter, store: SessionStore):
        """_create_stuck_card_from_fence creates stuck card and broadcasts."""
        session_id = "test-session"
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

        classification = IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="adc",
            utterance_fragment="test",
        )

        routed_intent = RoutedIntent(
            intent_id=intent_id,
            classification=classification,
            session_id=session_id,
            utterance="test",
        )

        fence_context = {
            "bead_id": "adc-fenced123",
            "refusal_reason": "Test refusal",
            "refusal_count": 3,
            "fenced_at": int(datetime.now(timezone.utc).timestamp()),
        }

        # Mock broadcaster
        broadcaster_mock = AsyncMock()
        with patch("src.intent.router.get_broadcaster", return_value=broadcaster_mock):
            result = await router._create_stuck_card_from_fence(
                routed_intent=routed_intent,
                fence_context=fence_context,
            )

        # Verify result
        assert result["intent_id"] == intent_id
        assert result["intent_type"] == "stuck"
        assert result["status"] == "stuck"
        assert result["bead_id"] == "adc-fenced123"

        # Verify intent updated
        intent = await store.get_intent(intent_id)
        assert intent["intent_type"] == "stuck"
        assert intent["status"] == "stuck"

        # Verify broadcaster called
        broadcaster_mock.broadcast.assert_called_once()
        call_args = broadcaster_mock.broadcast.call_args
        event = call_args[0][0]
        assert event.event_type == "task_stuck"
        assert event.data["bead_id"] == "adc-fenced123"


# --- Test Terminal Failure Handling ------------------------------------------


class TestTerminalFailureHandling:
    """Test terminal failure handling and failed card creation."""

    @pytest.mark.asyncio
    async def test_handle_terminal_failure_creates_failed_card(self, store: SessionStore):
        """handle_terminal_failure creates failed card and updates intent."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Failed Topic",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
            topic_id=topic_id,
        )

        # Mock broadcaster
        broadcaster_mock = AsyncMock()
        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster_mock), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Test failure",
                error_type="test_error",
                bead_ref=None,
            )

        # Verify intent status
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

        # Verify failed result created
        result = await store.get_latest_result_for_topic(topic_id)
        assert result is not None
        assert result["intent_id"] == intent_id
        assert "Task Failed" in result["summary"]

        result_data = json.loads(result["data"])
        assert result_data["failure_reason"] == "Test failure"
        assert result_data["error_type"] == "test_error"

        # Verify broadcaster called
        broadcaster_mock.broadcast.assert_called_once()
        call_args = broadcaster_mock.broadcast.call_args
        event = call_args[0][0]
        assert event.event_type == "task_failed"
        assert event.data["failure_reason"] == "Test failure"

    @pytest.mark.asyncio
    async def test_handle_terminal_failure_without_topic(self, store: SessionStore):
        """handle_terminal_failure creates topic when topic_id is None."""
        session_id = "test-session"
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test failure",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
        )

        # Mock broadcaster
        broadcaster_mock = AsyncMock()
        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster_mock), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=None,  # No topic
                failure_reason="Test failure",
                error_type="test_error",
                bead_ref=None,
            )

        # Verify intent has topic now
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"
        assert intent["topic_id"] is not None

        # Verify result created
        result = await store.get_latest_result_for_topic(intent["topic_id"])
        assert result is not None

    @pytest.mark.asyncio
    async def test_handle_terminal_failure_with_bead_ref(self, store: SessionStore):
        """handle_terminal_failure updates bead_watch when bead_ref provided."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Failed Topic",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-fail123",
            topic_id=topic_id,
        )

        # Create bead watch
        await store.create_bead_watch(
            bead_ref="adc-fail123",
            sla_hours=6,
            intent_type="task-profile",
        )

        # Mock broadcaster
        broadcaster_mock = AsyncMock()
        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster_mock), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Bead execution failed",
                error_type="worker_crash",
                bead_ref="adc-fail123",
            )

        # Verify bead_watch updated
        watch = await store.get_bead_watch("adc-fail123")
        assert watch["last_refusal_reason"] == "Bead execution failed"
        assert watch["refusal_count"] == 1

    @pytest.mark.asyncio
    async def test_handle_terminal_failure_broadcasts_sse(self, store: SessionStore, broadcaster: SSEBroadcaster):
        """handle_terminal_failure broadcasts task_failed SSE event."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Failed Topic",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
            topic_id=topic_id,
        )

        # Register SSE connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Patch get_broadcaster to use our test broadcaster
        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Worker crashed",
                error_type="worker_crash",
                bead_ref=None,
            )

        # Verify SSE event received
        event = await conn.queue.get()
        assert event.event_type == "task_failed"
        assert event.data["failure_reason"] == "Worker crashed"
        assert event.data["error_type"] == "worker_crash"
        assert event.data["intent_id"] == intent_id
        assert "timestamp" in event.data


# --- Test Intent Type Status Handling ----------------------------------------


class TestIntentTypeStatusHandling:
    """Test handling of both 'stuck' and 'failed' intent types."""

    @pytest.mark.asyncio
    async def test_stuck_intent_type_accepted(self, store: SessionStore):
        """Intent type 'stuck' is accepted by create_intent."""
        session_id = "test-session"
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test",
        )

        # Create intent with stuck type (via update)
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",  # Initially task-profile
        )

        # Update to stuck
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
        """Status 'failed' is accepted by update_intent_status."""
        session_id = "test-session"
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

        # Update to failed
        await store.update_intent_status(
            intent_id=intent_id,
            status="failed",
        )

        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

    @pytest.mark.asyncio
    async def test_get_intent_by_bead_ref_includes_stuck(self, store: SessionStore):
        """get_intent_by_bead_ref finds intents with stuck status."""
        session_id = "test-session"
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-stuck123",
        )

        # Update to stuck
        await store.update_intent_status(intent_id=intent_id, status="stuck")

        # Find by bead_ref
        intent = await store.get_intent_by_bead_ref("adc-stuck123")
        assert intent is not None
        assert intent["id"] == intent_id
        assert intent["status"] == "stuck"


# --- Test Integration Scenarios ----------------------------------------------


class TestBackendIntegrationScenarios:
    """Test integration scenarios for stuck/failed card flows."""

    @pytest.mark.asyncio
    async def test_full_stuck_card_flow(self, router: IntentRouter, store: SessionStore, broadcaster: SSEBroadcaster):
        """Test full stuck card creation flow from fence detection to SSE."""
        session_id = "test-session"
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test escalation",
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
            utterance_fragment="test escalation",
        )

        routed_intent = RoutedIntent(
            intent_id=intent_id,
            classification=classification,
            session_id=session_id,
            utterance="test escalation",
        )

        fence_context = {
            "bead_id": "adc-fenced456",
            "refusal_reason": "Missing required context",
            "refusal_count": 3,
            "fenced_at": int(datetime.now(timezone.utc).timestamp()),
        }

        # Register SSE connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Patch get_broadcaster
        with patch("src.intent.router.get_broadcaster", return_value=broadcaster):
            result = await router._create_stuck_card_from_fence(
                routed_intent=routed_intent,
                fence_context=fence_context,
            )

        # Verify result
        assert result["status"] == "stuck"
        assert result["bead_id"] == "adc-fenced456"

        # Verify SSE event
        event = await conn.queue.get()
        assert event.event_type == "task_stuck"
        assert event.data["bead_id"] == "adc-fenced456"
        assert event.data["stuck_reason"] == "Missing required context"

    @pytest.mark.asyncio
    async def test_full_failed_card_flow(self, store: SessionStore, broadcaster: SSEBroadcaster):
        """Test full failed card creation flow from failure to SSE."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Failed Flow",
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

        # Register SSE connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Patch get_broadcaster and get_store
        with patch("src.sse.broadcaster.get_broadcaster", return_value=broadcaster), \
             patch("src.session.store.get_store", return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Required data source unavailable",
                error_type="required_source_failure",
                bead_ref=None,
            )

        # Verify failed card
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

        result = await store.get_latest_result_for_topic(topic_id)
        assert "Task Failed" in result["summary"]

        # Verify SSE event
        event = await conn.queue.get()
        assert event.event_type == "task_failed"
        assert "data source unavailable" in event.data["failure_reason"]
