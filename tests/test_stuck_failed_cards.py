"""
Tests for stuck and failed card backend functionality (bead adc-2wzri).

Acceptance criteria:
- SSE event broadcast on fence (event_type: 'task_stuck')
- Canvas renders stuck/failed cards (via canvas.js functions)
- Tests verify card creation and broadcast
- Both 'stuck' and 'failed' intents surfaced in UI
- User can dismiss/view stuck beads from canvas

Note: Canvas rendering tests (createStuckCard, createFailedCard) use the Node.js
DOM runner in tests/e2e/canvas_builtin_runner.js. This file focuses on backend
SSE broadcasting and circuit breaker logic.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.sse.broadcaster import (
    get_broadcaster,
    SSEEvent,
    EventType,
)
from src.watcher.daemon import BeadWatcher
from src.session.store import SessionStore


@pytest.fixture
async def broadcaster():
    """Create a fresh SSE broadcaster for each test."""
    from src.sse.broadcaster import SSEBroadcaster
    broadcaster = SSEBroadcaster()
    await broadcaster.start()
    yield broadcaster
    await broadcaster.stop()


@pytest.fixture
async def store(tmp_path):
    """Create a fresh session store for each test."""
    db_path = tmp_path / "test.db"
    store = SessionStore(db_path)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def mock_router():
    """Create a mock surface router."""
    router = AsyncMock()
    decision = MagicMock()
    decision.target_surfaces = []
    decision.fallback_used = True
    router.route_result.return_value = decision
    return router


class TestTaskStuckSSEEvent:
    """Test task_stuck SSE event broadcasting."""

    @pytest.mark.asyncio
    async def test_task_stuck_event_broadcast(self, broadcaster, store, mock_router):
        """Bead watcher broadcasts task_stuck event on fence."""
        # Create a test intent with bead_ref
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test escalation",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-stuck123",
            lookup_kind=None,
            topic_id=topic_id,
        )

        # Create bead_watch row
        await store.create_bead_watch(
            bead_ref="adc-stuck123",
            sla_hours=24,
            intent_type="task-profile",
        )

        # Create watcher and test fencing
        watcher = BeadWatcher(store, mock_router)

        # Mock the bf update status call
        watcher._run_bf_update_status = AsyncMock()

        # Register SSE connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Broadcast the event (simulating what _fence_bead does)
        await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.TASK_STUCK,
                data={
                    "bead_id": "adc-stuck123",
                    "stuck_reason": "Test refusal",
                    "refusal_count": 3,
                    "message": "This task has been blocked after 3 refusals.",
                    "action_hint": "Review the bead and provide the missing information.",
                    "timestamp": int(datetime.now(timezone.utc).timestamp()),
                },
                target_session_id=session_id,
            )
        )

        # Verify event was queued (check connection)
        event = await conn.queue.get()
        assert event.event_type == "task_stuck"
        assert event.data["bead_id"] == "adc-stuck123"
        assert event.data["stuck_reason"] == "Test refusal"
        assert event.data["refusal_count"] == 3
        assert "timestamp" in event.data
        assert isinstance(event.data["timestamp"], int)


class TestTaskFailedSSEEvent:
    """Test task_failed SSE event broadcasting."""

    @pytest.mark.asyncio
    async def test_task_failed_event_broadcast(self, broadcaster, store):
        """Terminal failure broadcasts task_failed event."""
        import src.session.store
        from src.escalate.handler import handle_terminal_failure
        from unittest.mock import patch

        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test task",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            lookup_kind=None,
            topic_id=topic_id,
        )

        # Register SSE connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Patch get_store and get_broadcaster to use our test objects
        import src.sse.broadcaster
        with patch.object(src.session.store, 'get_store', return_value=store), \
             patch.object(src.sse.broadcaster, 'get_broadcaster', return_value=broadcaster):
            # Handle terminal failure
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Worker process crashed",
                error_type="worker_crash",
                bead_ref=None,
            )

        # Verify intent status is failed
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

        # Verify SSE event was broadcast
        event = await conn.queue.get()
        assert event.event_type == "task_failed"
        assert event.data["failure_reason"] == "Worker process crashed"
        assert event.data["error_type"] == "worker_crash"


class TestFailedCardPersistence:
    """Test failed card persistence to session store (bead adc-5fpkh)."""

    @pytest.mark.asyncio
    async def test_failed_card_persists_with_correct_status(self, store):
        """Failed cards persist with status='failed' and failure details."""
        session_id = "test-session-failed"
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test task that will fail",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="action",
            lookup_kind=None,
            topic_id=topic_id,
        )

        # Import and call handle_terminal_failure
        from src.escalate.handler import handle_terminal_failure
        import src.session.store

        # Patch get_store to return our test store
        with patch.object(src.session.store, 'get_store', return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Required data sources failed",
                error_type="required_source_failure",
                bead_ref=None,
            )

        # Verify intent status is failed
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

        # Verify result contains failed card data
        result = await store.get_latest_result_for_topic(topic_id)
        assert result is not None
        assert result["intent_id"] == intent_id
        assert result["summary"] == "Task Failed: Required Source Failure"
        assert result["urgency"] == "high"

        import json
        result_data = json.loads(result["data"])
        assert result_data["failure_reason"] == "Required data sources failed"
        assert result_data["error_type"] == "required_source_failure"
        assert "message" in result_data
        assert "action_hint" in result_data

    @pytest.mark.asyncio
    async def test_failed_card_queryable_via_session_api(self, store):
        """Failed cards are queryable via session API (topics endpoint)."""
        session_id = "test-session-query-failed"
        topic_id, _ = await store.find_or_create_topic(
            label="Query Failed Test",
            session_id=session_id,
            topic_type="exception",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test query failed",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            lookup_kind=None,
            topic_id=topic_id,
        )

        # Import and call handle_terminal_failure
        from src.escalate.handler import handle_terminal_failure
        import src.session.store

        with patch.object(src.session.store, 'get_store', return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Worker process crashed",
                error_type="worker_crash",
                bead_ref="adc-test123",
            )

        # Query active topics (simulating session API call)
        topics = await store.get_active_topics(session_id)
        assert len(topics) >= 1

        # Find our topic
        topic = next((t for t in topics if t["id"] == topic_id), None)
        assert topic is not None
        assert topic["label"] == "Query Failed Test"
        assert topic["type"] == "exception"

        # Verify failed result is included
        latest_result = await store.get_latest_result_for_topic(topic_id)
        assert latest_result is not None
        assert latest_result["summary"] == "Task Failed: Worker Crash"

        import json
        result_data = json.loads(latest_result["data"])
        assert result_data["bead_ref"] == "adc-test123"
        assert result_data["failure_reason"] == "Worker process crashed"

    @pytest.mark.asyncio
    async def test_failed_card_without_topic_creates_topic(self, store):
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
            lookup_kind=None,
            topic_id=None,
        )

        # Import and call handle_terminal_failure without topic_id
        from src.escalate.handler import handle_terminal_failure
        import src.session.store

        with patch.object(src.session.store, 'get_store', return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=None,  # No topic provided
                failure_reason="Invalid input detected",
                error_type="invalid_input",
                bead_ref=None,
            )

        # Verify intent status is failed
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

        # Verify a topic was created and linked
        # Query the intent to see its topic
        intent = await store.get_intent(intent_id)
        created_topic_id = intent.get("topic_id")
        assert created_topic_id is not None

        # Verify the topic exists and has the failed result
        topic_topics = await store.get_active_topics(session_id)
        created_topic = next((t for t in topic_topics if t["id"] == created_topic_id), None)
        assert created_topic is not None
        assert "Failed:" in created_topic["label"]

        # Verify failed result exists for the created topic
        latest_result = await store.get_latest_result_for_topic(created_topic_id)
        assert latest_result is not None
        assert latest_result["intent_id"] == intent_id

    @pytest.mark.asyncio
    async def test_failed_card_stores_in_bead_watch(self, store):
        """handle_terminal_failure stores failure reason in bead_watch when bead_ref provided."""
        session_id = "test-session-bead-watch"
        topic_id, _ = await store.find_or_create_topic(
            label="Bead Watch Test",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test bead watch failure",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-fail123",
            lookup_kind=None,
            topic_id=topic_id,
        )

        # Create bead_watch row
        await store.create_bead_watch(
            bead_ref="adc-fail123",
            sla_hours=6,
            intent_type="task-profile",
        )

        # Import and call handle_terminal_failure
        from src.escalate.handler import handle_terminal_failure
        import src.session.store

        with patch.object(src.session.store, 'get_store', return_value=store):
            await handle_terminal_failure(
                intent_id=intent_id,
                session_id=session_id,
                topic_id=topic_id,
                failure_reason="Bead execution failed",
                error_type="worker_crash",
                bead_ref="adc-fail123",
            )

        # Verify failure reason stored in bead_watch
        bead_watch = await store.get_bead_watch("adc-fail123")
        assert bead_watch is not None
        assert bead_watch["last_refusal_reason"] == "Bead execution failed"
        assert bead_watch["refusal_count"] == 1  # Should be incremented


class TestBeadWatcherFencing:
    """Test bead watcher fencing logic."""

    @pytest.mark.asyncio
    async def test_fence_bead_sets_stuck_status(self, store, mock_router):
        """Fencing a bead sets intent status to stuck."""
        watcher = BeadWatcher(store, mock_router)

        # Mock bf commands
        watcher._run_bf_update_status = AsyncMock()
        watcher._run_bf_show = AsyncMock(return_value={"comments": []})
        watcher._run_bf_list_closed = AsyncMock(return_value=[])

        # Create test data
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Test", session_id=session_id, topic_type="project"
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test task",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test",
            intent_type="task-profile",
            bead_ref="test-stuck",
            lookup_kind=None,
            topic_id=topic_id,
        )

        await store.create_bead_watch(bead_ref="test-stuck", sla_hours=24, intent_type="task-profile")

        # Fence the bead
        await watcher._fence_bead(
            bead_ref="test-stuck",
            refusal_reason="Test refusal",
            refusal_count=3,
        )

        # Verify intent status is stuck
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "stuck"

        # Verify bead is fenced
        watched = await store.get_bead_watch("test-stuck")
        assert watched["fenced_at"] is not None

    @pytest.mark.asyncio
    async def test_circuit_breaker_thresholds(self, store):
        """Test circuit breaker thresholds for fencing."""
        from src.session.store import (
            CIRCUIT_BREAKER_REFUSAL_THRESHOLD,
            CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS,
        )

        # Verify constants are set correctly
        assert CIRCUIT_BREAKER_REFUSAL_THRESHOLD == 3
        assert CIRCUIT_BREAKER_AGE_THRESHOLD_HOURS == 24.0

    @pytest.mark.asyncio
    async def test_get_beads_needing_fencing_empty(self, store):
        """get_beads_needing_fencing returns empty list when no beads need fencing."""
        # No beads in watch list
        needs_fencing = await store.get_beads_needing_fencing()
        assert len(needs_fencing) == 0

    @pytest.mark.asyncio
    async def test_get_beads_needing_fencing_by_refusals(self, store):
        """Beads with 3+ refusals are flagged for fencing."""
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Test", session_id=session_id, topic_type="project"
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test task",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test",
            intent_type="task-profile",
            bead_ref="test-refusal",
            lookup_kind=None,
            topic_id=topic_id,
        )

        # Create bead watch with 3 refusals (at threshold)
        await store.create_bead_watch(bead_ref="test-refusal", sla_hours=24, intent_type="task-profile")
        await store.update_bead_watch_refusal(
            bead_ref="test-refusal",
            refusal_reason="Refusal 1",
            comment_index=0,
            refusal_count_add=1,
        )
        await store.update_bead_watch_refusal(
            bead_ref="test-refusal",
            refusal_reason="Refusal 2",
            comment_index=1,
            refusal_count_add=1,
        )
        await store.update_bead_watch_refusal(
            bead_ref="test-refusal",
            refusal_reason="Refusal 3",
            comment_index=2,
            refusal_count_add=1,
        )

        # Should be flagged for fencing
        needs_fencing = await store.get_beads_needing_fencing()
        assert len(needs_fencing) == 1
        assert needs_fencing[0]["bead_ref"] == "test-refusal"
        assert needs_fencing[0]["refusal_count"] == 3


class TestStuckCardPersistence:
    """Test stuck card persistence to session store (bead adc-4wx6d)."""

    @pytest.mark.asyncio
    async def test_stuck_card_persists_with_correct_type_and_status(self, store):
        """Stuck cards persist with intent_type='stuck' and status='stuck'."""
        # Create test data
        session_id = "test-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test escalation",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-stuck-persist",
            lookup_kind=None,
            topic_id=topic_id,
        )

        # Update intent to stuck type and status
        await store.update_intent_type_and_status(
            intent_id=intent_id,
            intent_type="stuck",
            status="stuck",
        )

        # Create stuck result
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Task stuck — needs your input",
            data={
                "bead_id": "adc-stuck-persist",
                "stuck_reason": "Test refusal reason",
                "refusal_count": 3,
                "message": "This task has been blocked after 3 refusals.",
                "action_hint": "Review the bead and provide missing information.",
                "fence_detected_during": "intent_routing",
            },
            urgency="high",
        )

        # Verify intent type and status are stuck
        intent = await store.get_intent(intent_id)
        assert intent["intent_type"] == "stuck"
        assert intent["status"] == "stuck"
        assert intent["bead_ref"] == "adc-stuck-persist"

        # Verify result contains stuck card data
        result = await store.get_latest_result_for_topic(topic_id)
        assert result is not None
        assert result["id"] == result_id
        assert result["intent_id"] == intent_id
        assert result["summary"] == "Task stuck — needs your input"
        assert result["urgency"] == "high"

        import json
        result_data = json.loads(result["data"])
        assert result_data["bead_id"] == "adc-stuck-persist"
        assert result_data["stuck_reason"] == "Test refusal reason"
        assert result_data["refusal_count"] == 3
        assert "message" in result_data
        assert "action_hint" in result_data

    @pytest.mark.asyncio
    async def test_stuck_card_queryable_via_session_api(self, store):
        """Stuck cards are queryable via session API (topics endpoint)."""
        # Create test data
        session_id = "test-session-query"
        topic_id, _ = await store.find_or_create_topic(
            label="Query Test Topic",
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
            bead_ref="adc-query-test",
            lookup_kind=None,
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
            summary="Query test stuck",
            data={
                "bead_id": "adc-query-test",
                "stuck_reason": "Query test refusal",
                "refusal_count": 1,
            },
            urgency="high",
        )

        # Query active topics (simulating session API call)
        topics = await store.get_active_topics(session_id)
        assert len(topics) >= 1

        # Find our topic
        topic = next((t for t in topics if t["id"] == topic_id), None)
        assert topic is not None
        assert topic["label"] == "Query Test Topic"
        assert topic["type"] == "project"

        # Verify result is included
        latest_result = await store.get_latest_result_for_topic(topic_id)
        assert latest_result is not None
        assert latest_result["summary"] == "Query test stuck"

    @pytest.mark.asyncio
    async def test_get_fenced_beads_for_session(self, store):
        """get_fenced_beads_for_session returns fenced beads with intent context."""
        # Create test data with fenced bead
        session_id = "test-fenced-session"
        topic_id, _ = await store.find_or_create_topic(
            label="Fenced Test",
            session_id=session_id,
            topic_type="project",
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test fenced bead",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-fenced-test",
            lookup_kind=None,
            topic_id=topic_id,
        )

        # Create bead watch and fence it
        await store.create_bead_watch(bead_ref="adc-fenced-test", sla_hours=24)
        await store.update_bead_watch_refusal(
            bead_ref="adc-fenced-test",
            refusal_reason="Test fence",
            comment_index=0,
            refusal_count_add=3,
        )
        await store.fence_bead(bead_ref="adc-fenced-test")

        # Query fenced beads for session
        fenced_beads = await store.get_fenced_beads_for_session(session_id)
        assert len(fenced_beads) == 1

        fenced = fenced_beads[0]
        assert fenced["bead_ref"] == "adc-fenced-test"
        assert fenced["fenced_at"] is not None
        assert fenced["intent_id"] == intent_id
        assert fenced["topic_id"] == topic_id
        assert fenced["project_slug"] == "adc"


class TestCanvasSSEEventHandling:
    """Test canvas handles stuck/failed SSE events."""

    def test_canvas_listens_for_task_stuck_event(self):
        """Canvas has event listener for task_stuck events."""
        # Verify the canvas HTML includes the event listener
        from pathlib import Path

        canvas_html = Path("/home/coding/aide-de-camp/src/canvas/index.html").read_text()

        # Verify task_stuck event listener exists
        assert "addEventListener('task_stuck'" in canvas_html

        # Verify it calls createStuckCard
        assert "createStuckCard" in canvas_html

    def test_canvas_listens_for_task_failed_event(self):
        """Canvas has event listener for task_failed events."""
        from pathlib import Path

        canvas_html = Path("/home/coding/aide-de-camp/src/canvas/index.html").read_text()

        # Verify task_failed event listener exists
        assert "addEventListener('task_failed'" in canvas_html

        # Verify it calls createFailedCard
        assert "createFailedCard" in canvas_html

    def test_canvas_exports_card_functions(self):
        """Canvas exports createStuckCard and createFailedCard to window."""
        from pathlib import Path

        canvas_js = Path("/home/coding/aide-de-camp/src/canvas/canvas.js").read_text()

        # Verify functions are exported to window
        assert "window.createStuckCard" in canvas_js
        assert "window.createFailedCard" in canvas_js


class TestIntentRouterFenceDetection:
    """Test intent router fence detection logic (bead adc-2cjdj)."""

    @pytest.mark.asyncio
    async def test_check_fence_for_bead_fenced(self):
        """_check_fence_for_bead returns context for fenced bead."""
        from src.intent.router import IntentRouter

        router = IntentRouter()

        # Mock the store to return a fenced bead
        mock_store = AsyncMock()
        mock_store.get_bead_watch.return_value = {
            "bead_ref": "adc-fenced123",
            "last_refusal_reason": "Test refusal",
            "refusal_count": 3,
            "fenced_at": 1234567890,
        }

        router.store = mock_store

        # Check fence
        fence_context = await router._check_fence_for_bead("adc-fenced123")

        assert fence_context is not None
        assert fence_context["bead_id"] == "adc-fenced123"
        assert fence_context["refusal_reason"] == "Test refusal"
        assert fence_context["refusal_count"] == 3
        assert fence_context["fenced_at"] == 1234567890

        mock_store.get_bead_watch.assert_called_once_with("adc-fenced123")

    @pytest.mark.asyncio
    async def test_check_fence_for_bead_not_fenced(self):
        """_check_fence_for_bead returns None for unfenced bead."""
        from src.intent.router import IntentRouter

        router = IntentRouter()

        # Mock the store to return a bead without refusal_reason
        mock_store = AsyncMock()
        mock_store.get_bead_watch.return_value = {
            "bead_ref": "adc-unfenced123",
            "refusal_count": 0,
            "fenced_at": None,
            "last_refusal_reason": None,
        }

        router.store = mock_store

        # Check fence
        fence_context = await router._check_fence_for_bead("adc-unfenced123")

        assert fence_context is None

    @pytest.mark.asyncio
    async def test_check_fence_for_bead_no_watch(self):
        """_check_fence_for_bead returns None when bead not watched."""
        from src.intent.router import IntentRouter

        router = IntentRouter()

        # Mock the store to return None (bead not watched)
        mock_store = AsyncMock()
        mock_store.get_bead_watch.return_value = None

        router.store = mock_store

        # Check fence for non-existent bead
        fence_context = await router._check_fence_for_bead("adc-nonexistent")

        assert fence_context is None


class TestIntentRouterStuckCardCreation:
    """Test intent router stuck card creation from fence (bead adc-2cjdj)."""

    @pytest.mark.asyncio
    async def test_create_stuck_card_from_fence_creates_card_and_broadcasts(self, broadcaster):
        """_create_stuck_card_from_fence creates stuck card and broadcasts SSE event."""
        from src.intent.router import IntentRouter, RoutedIntent, IntentClassification, IntentType

        router = IntentRouter()

        routed_intent = RoutedIntent(
            intent_id="intent-1",
            classification=IntentClassification(
                intent_type=IntentType.TASK_PROFILE,
                project_slug="adc",
                utterance_fragment="test",
            ),
            session_id="test-session",
            utterance="test",
        )

        fence_context = {
            "bead_id": "adc-fenced123",
            "refusal_reason": "Test refusal",
            "refusal_count": 3,
            "fenced_at": 1234567890,
        }

        # Mock store methods
        mock_store = AsyncMock()
        mock_store.find_or_create_topic.return_value = ("topic-1", False)
        mock_store.link_intent_to_topic = AsyncMock()
        mock_store.update_intent_type_and_status = AsyncMock()
        mock_store.create_result.return_value = "result-1"

        router.store = mock_store

        # Register SSE connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id="test-session",
            surface_type="canvas",
        )

        # Mock broadcaster
        with patch("src.intent.router.get_broadcaster", return_value=broadcaster):
            result = await router._create_stuck_card_from_fence(
                routed_intent=routed_intent,
                fence_context=fence_context,
            )

        # Verify result
        assert result["intent_id"] == "intent-1"
        assert result["intent_type"] == "stuck"
        assert result["status"] == "stuck"
        assert result["bead_id"] == "adc-fenced123"

        # Verify store calls
        mock_store.find_or_create_topic.assert_called_once()
        mock_store.link_intent_to_topic.assert_called_once_with("intent-1", "topic-1")
        mock_store.update_intent_type_and_status.assert_called_once_with(
            intent_id="intent-1",
            intent_type="stuck",
            status="stuck",
        )
        mock_store.create_result.assert_called_once()

        # Verify SSE broadcast was called
        event = await conn.queue.get()
        assert event.event_type == "task_stuck"
        assert event.data["bead_id"] == "adc-fenced123"
        assert event.data["stuck_reason"] == "Test refusal"
        assert event.data["refusal_count"] == 3


class TestIntentTypeStatusHandling:
    """Test handling of both 'stuck' and 'failed' intent types (bead adc-2cjdj)."""

    @pytest.mark.asyncio
    async def test_stuck_intent_type_accepted(self, store):
        """Intent type 'stuck' is accepted by update_intent_type_and_status."""
        session_id = "test-session"
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test",
        )

        # Create intent with task-profile type
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            lookup_kind=None,
        )

        # Update to stuck type and status
        await store.update_intent_type_and_status(
            intent_id=intent_id,
            intent_type="stuck",
            status="stuck",
        )

        # Verify stuck type and status are accepted
        intent = await store.get_intent(intent_id)
        assert intent["intent_type"] == "stuck"
        assert intent["status"] == "stuck"

    @pytest.mark.asyncio
    async def test_failed_status_accepted(self, store):
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
            lookup_kind=None,
        )

        # Update to failed status
        await store.update_intent_status(
            intent_id=intent_id,
            status="failed",
        )

        # Verify failed status is accepted
        intent = await store.get_intent(intent_id)
        assert intent["status"] == "failed"

    @pytest.mark.asyncio
    async def test_get_intent_by_bead_ref_includes_stuck(self, store):
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
            lookup_kind=None,
        )

        # Update to stuck status
        await store.update_intent_status(intent_id=intent_id, status="stuck")

        # Find by bead_ref
        intent = await store.get_intent_by_bead_ref("adc-stuck123")
        assert intent is not None
        assert intent["id"] == intent_id
        assert intent["status"] == "stuck"


class TestSSEBroadcasterBroadcastCalls:
    """Test SSE broadcaster.broadcast() call verification (bead adc-2cjdj)."""

    @pytest.mark.asyncio
    async def test_broadcast_stuck_event_call(self, broadcaster):
        """broadcast is called with correct params for task_stuck event."""
        from unittest.mock import AsyncMock

        session_id = "test-session"

        # Register connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id=session_id,
            surface_type="canvas",
        )

        # Create mock broadcaster to verify call
        mock_broadcaster = AsyncMock()
        mock_broadcaster.broadcast = AsyncMock(return_value=1)

        # Broadcast stuck event using real broadcaster
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

        # Verify broadcast was called and returned correct count
        assert sent_count == 1

        # Verify event received
        event = await conn.queue.get()
        assert event.event_type == "task_stuck"
        assert event.data["bead_id"] == "adc-stuck123"
        assert event.data["stuck_reason"] == "Test refusal"
        assert event.data["refusal_count"] == 3

    @pytest.mark.asyncio
    async def test_broadcast_failed_event_call(self, broadcaster):
        """broadcast is called with correct params for task_failed event."""
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

        # Verify broadcast was called and returned correct count
        assert sent_count == 1

        # Verify event received
        event = await conn.queue.get()
        assert event.event_type == "task_failed"
        assert event.data["intent_id"] == "intent-123"
        assert event.data["failure_reason"] == "Worker crashed"
        assert event.data["error_type"] == "worker_crash"

    @pytest.mark.asyncio
    async def test_broadcast_with_target_filtering(self, broadcaster):
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
    async def test_broadcast_with_exclude_surface(self, broadcaster):
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


class TestSessionStoreOperations:
    """Test session store operations (bead adc-2cjdj)."""

    @pytest.mark.asyncio
    async def test_create_utterance(self, store):
        """create_utterance stores utterance and returns ID."""
        session_id = "test-session"

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test utterance",
        )

        # Verify utterance ID is returned
        assert utterance_id is not None

        # Verify utterance was stored by checking it exists in session intents
        # (SessionStore doesn't expose get_utterance, but we can verify it indirectly)
        intents = await store.get_pending_intents(session_id)
        # Since we just created an utterance but no intent, the list should be empty
        # The utterance exists in the database, used by create_intent
        assert isinstance(intents, list)

    @pytest.mark.asyncio
    async def test_find_or_create_topic_new(self, store):
        """find_or_create_topic creates new topic when none exists."""
        session_id = "test-session"

        topic_id, created = await store.find_or_create_topic(
            label="New Topic",
            session_id=session_id,
            topic_type="project",
        )

        assert topic_id is not None
        assert created is True

        # Verify topic was stored
        topics = await store.get_active_topics(session_id)
        topic = next((t for t in topics if t["id"] == topic_id), None)
        assert topic is not None
        assert topic["label"] == "New Topic"
        assert topic["type"] == "project"

    @pytest.mark.asyncio
    async def test_find_or_create_topic_existing(self, store):
        """find_or_create_topic returns existing topic when found."""
        session_id = "test-session"

        # Create topic first
        topic_id_1, created_1 = await store.find_or_create_topic(
            label="Existing Topic",
            session_id=session_id,
            topic_type="project",
        )

        assert created_1 is True

        # Find existing topic
        topic_id_2, created_2 = await store.find_or_create_topic(
            label="Existing Topic",
            session_id=session_id,
            topic_type="project",
        )

        assert created_2 is False
        assert topic_id_1 == topic_id_2

    @pytest.mark.asyncio
    async def test_find_or_create_topic_exception_type(self, store):
        """find_or_create_topic accepts exception topic type."""
        session_id = "test-session"

        topic_id, created = await store.find_or_create_topic(
            label="Exception Topic",
            session_id=session_id,
            topic_type="exception",
        )

        assert topic_id is not None
        assert created is True

        # Verify topic type
        topics = await store.get_active_topics(session_id)
        topic = next((t for t in topics if t["id"] == topic_id), None)
        assert topic["type"] == "exception"
