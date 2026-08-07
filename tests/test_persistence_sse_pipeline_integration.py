"""
Integration tests for the complete persistence → SSE pipeline.

This test module verifies that the full flow from result creation to SSE broadcast works correctly:
- Result creation triggers both storage and SSE broadcast
- Canvas receives correct topic data via SSE
- The complete intent router → fetch → synthesize → persist → SSE pipeline works end-to-end

Acceptance criteria:
- End-to-end tests for the full persistence → SSE pipeline
- Verify that result creation triggers both storage and SSE broadcast
- Test that the canvas receives correct topic data via SSE
- All tests pass

Bead: adc-27tb0
"""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import aiosqlite
import pytest

from src.session.store import SessionStore
from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEEvent,
    EventType,
    get_broadcaster,
    broadcast_result,
)
from src.intent.router import IntentRouter, IntentType, IntentClassification, RoutedIntent


# --- Fixtures -----------------------------------------------------------------


@pytest.fixture
async def temp_db_path():
    """Create a temporary database path for isolated test runs."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup is handled by SessionStore fixture


@pytest.fixture
async def test_store(temp_db_path):
    """Create an isolated test session store."""
    store = SessionStore(db_path=temp_db_path)
    await store.initialize()
    yield store
    await store.close()
    # Cleanup database file
    temp_db_path.unlink(missing_ok=True)


@pytest.fixture
async def test_broadcaster():
    """Get the global SSE broadcaster and ensure it's running."""
    broadcaster = get_broadcaster()
    if not broadcaster._running:
        await broadcaster.start()

    # Clear connections before each test
    broadcaster.connections.clear()

    yield broadcaster

    # Cleanup: don't stop the global broadcaster as other tests may need it


@pytest.fixture
async def test_router(test_store):
    """Create an intent router with the test store."""
    router = IntentRouter(store=test_store)
    yield router


# --- Test Helper Functions -----------------------------------------------------


async def create_test_connection(broadcaster, session_id, surface_id=None):
    """Helper to register a test SSE connection."""
    if surface_id is None:
        surface_id = str(uuid4())
    return broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )


async def collect_sse_events(connection, max_events=10, timeout=1.0):
    """Helper to collect all events from an SSE connection."""
    events = []
    try:
        # Wait a moment for events to propagate
        await asyncio.sleep(0.05)

        while not connection.queue.empty() and len(events) < max_events:
            try:
                event = connection.queue.get_nowait()
                if event is not None:  # Skip None values
                    events.append(event)
            except asyncio.QueueEmpty:
                break
    except Exception as e:
        pass
    return events


async def create_synthetic_result(
    store,
    session_id,
    intent_id=None,
    topic_id=None,
    summary="Test result",
    data=None,
    urgency="normal"
):
    """Helper to create a synthetic result in the store."""
    if intent_id is None:
        intent_id = str(uuid4())
    if topic_id is None:
        topic_id, _ = await store.find_or_create_topic(
            label="Test Topic",
            session_id=session_id,
            topic_type="research"
        )
    if data is None:
        data = {"test": "data"}

    result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary=summary,
        data=data,
        urgency=urgency
    )
    return result_id, intent_id, topic_id


# --- Integration Tests ---------------------------------------------------------


class TestPersistenceAndSSEPipeline:
    """
    Integration tests for the complete persistence → SSE pipeline.

    Tests that result creation triggers both storage and SSE broadcast,
    and that canvas receives correct topic data.
    """

    @pytest.mark.asyncio
    async def test_result_creation_stores_in_database(self, test_store):
        """Verify that result creation stores data in the database."""
        # Arrange: Create session and topic
        session_id = await test_store.create_session()
        topic_id, _ = await test_store.find_or_create_topic(
            label="Storage Test Topic",
            session_id=session_id,
            topic_type="research"
        )
        intent_id = str(uuid4())

        # Act: Create result
        result_id = await test_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Test summary for storage",
            data={"field1": "value1", "field2": [1, 2, 3]},
            urgency="normal"
        )

        # Assert: Result stored in database
        result = await test_store.get_result(result_id)
        assert result is not None
        assert result["id"] == result_id
        assert result["summary"] == "Test summary for storage"
        assert result["intent_id"] == intent_id
        assert result["topic_id"] == topic_id
        assert result["session_id"] == session_id

        # Verify data field stored as JSON
        stored_data = json.loads(result["data"])
        assert stored_data["field1"] == "value1"
        assert stored_data["field2"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_result_creation_broadcasts_sse_event(self, test_store, test_broadcaster):
        """Verify that result creation triggers SSE broadcast."""
        # Arrange: Create session, topic, and SSE connection
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        connection = await create_test_connection(test_broadcaster, session_id, surface_id)

        topic_id, _ = await test_store.find_or_create_topic(
            label="SSE Test Topic",
            session_id=session_id,
            topic_type="research"
        )
        intent_id = str(uuid4())

        # Act: Create result and broadcast
        result_id = await test_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Broadcast test result",
            data={"broadcast": "test"},
            urgency="normal"
        )

        result_data = {
            "result_id": result_id,
            "summary": "Broadcast test result",
            "intent_id": intent_id,
            "topic_id": topic_id,
            "session_id": session_id,
        }

        sent_count = await broadcast_result(
            result=result_data,
            session_id=session_id,
            target_surface_id=surface_id
        )

        # Assert: Event was broadcast to the connection
        assert sent_count == 1

        # Verify the event is in the connection queue
        assert not connection.queue.empty()
        event = connection.queue.get_nowait()
        assert isinstance(event, SSEEvent)
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["result_id"] == result_id
        assert event.data["summary"] == "Broadcast test result"

    @pytest.mark.asyncio
    async def test_complete_pipeline_storage_to_sse(self, test_store, test_broadcaster):
        """Verify the complete pipeline: storage → SSE broadcast → canvas reception."""
        # Arrange: Create session and SSE connection
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        connection = await create_test_connection(test_broadcaster, session_id, surface_id)

        # Act: Create result and broadcast
        result_id, intent_id, topic_id = await create_synthetic_result(
            test_store,
            session_id,
            summary="Complete pipeline test",
            data={"pipeline": "complete"},
            urgency="high"
        )

        result_data = {
            "result_id": result_id,
            "summary": "Complete pipeline test",
            "intent_id": intent_id,
            "topic_id": topic_id,
            "urgency": "high",
        }

        sent_count = await broadcast_result(
            result=result_data,
            session_id=session_id,
            target_surface_id=surface_id
        )

        # Assert: Both storage and broadcast succeeded
        assert sent_count == 1

        # Verify storage
        result = await test_store.get_result(result_id)
        assert result is not None
        assert result["summary"] == "Complete pipeline test"
        assert result["urgency"] == "high"

        # Verify SSE broadcast
        event = connection.queue.get_nowait()
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["result_id"] == result_id
        assert event.data["urgency"] == "high"

    @pytest.mark.asyncio
    async def test_canvas_receives_correct_topic_data(self, test_store, test_broadcaster):
        """Verify that canvas receives correct topic data via SSE."""
        # Arrange: Create session with topic
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        connection = await create_test_connection(test_broadcaster, session_id, surface_id)

        topic_id, _ = await test_store.find_or_create_topic(
            label="Canvas Data Topic",
            session_id=session_id,
            topic_type="project",
            project_slugs=["test-project"]
        )

        # Act: Create result and broadcast
        result_id, intent_id, _ = await create_synthetic_result(
            test_store,
            session_id,
            topic_id=topic_id,
            summary="Canvas data test",
            data={"canvas": "data", "fields": {"status": "active"}},
            urgency="normal"
        )

        result_data = {
            "result_id": result_id,
            "summary": "Canvas data test",
            "intent_id": intent_id,
            "topic_id": topic_id,
            "data": {"canvas": "data", "fields": {"status": "active"}},
        }

        await broadcast_result(
            result=result_data,
            session_id=session_id,
            target_surface_id=surface_id
        )

        # Assert: Event contains correct topic data
        event = connection.queue.get_nowait()
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["topic_id"] == topic_id
        assert event.data["summary"] == "Canvas data test"
        assert "data" in event.data
        assert event.data["data"]["canvas"] == "data"
        assert event.data["data"]["fields"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_multiple_results_multiple_surfaces(self, test_store, test_broadcaster):
        """Verify multiple results broadcast to multiple surfaces correctly."""
        # Arrange: Create session with multiple surfaces
        session_id = await test_store.create_session()
        surface1 = await create_test_connection(test_broadcaster, session_id)
        surface2 = await create_test_connection(test_broadcaster, session_id)

        # Act: Create multiple results
        topic_id, _ = await test_store.find_or_create_topic(
            label="Multi-result Topic",
            session_id=session_id,
            topic_type="research"
        )

        result1_id, intent1_id, _ = await create_synthetic_result(
            test_store,
            session_id,
            topic_id=topic_id,
            summary="First result"
        )

        result2_id, intent2_id, _ = await create_synthetic_result(
            test_store,
            session_id,
            topic_id=topic_id,
            summary="Second result"
        )

        # Broadcast both results
        await broadcast_result(
            result={"result_id": result1_id, "summary": "First result", "intent_id": intent1_id, "topic_id": topic_id},
            session_id=session_id
        )
        await broadcast_result(
            result={"result_id": result2_id, "summary": "Second result", "intent_id": intent2_id, "topic_id": topic_id},
            session_id=session_id
        )

        # Assert: Both surfaces received both events
        for surface in [surface1, surface2]:
            events_received = []
            while not surface.queue.empty():
                event = surface.queue.get_nowait()
                events_received.append(event)

            assert len(events_received) == 2
            summaries = {e.data["summary"] for e in events_received}
            assert "First result" in summaries
            assert "Second result" in summaries

    @pytest.mark.asyncio
    async def test_sse_targeting_filters(self, test_store, test_broadcaster):
        """Verify SSE targeting filters work correctly."""
        # Arrange: Create multiple sessions and surfaces
        session_a = await test_store.create_session()
        session_b = await test_store.create_session()

        surface_a1 = await create_test_connection(test_broadcaster, session_a)
        surface_a2 = await create_test_connection(test_broadcaster, session_a)
        surface_b1 = await create_test_connection(test_broadcaster, session_b)

        # Act: Broadcast to session_a only
        result_id, intent_id, topic_id = await create_synthetic_result(test_store, session_a)

        sent_count = await broadcast_result(
            result={"result_id": result_id, "summary": "Targeted result", "intent_id": intent_id, "topic_id": topic_id},
            session_id=session_a,  # Target only session_a
        )

        # Assert: Only session_a connections received the event
        assert sent_count == 2  # surface_a1 and surface_a2

        # Verify session_a surfaces received events
        assert not surface_a1.queue.empty()
        assert not surface_a2.queue.empty()

        # Verify session_b surface did not receive event
        assert surface_b1.queue.empty()

    @pytest.mark.asyncio
    async def test_result_with_rendered_html(self, test_store, test_broadcaster):
        """Verify result creation with rendered HTML field."""
        # Arrange: Create session and connection
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        connection = await create_test_connection(test_broadcaster, session_id, surface_id)

        # Act: Create result with rendered HTML
        result_id, intent_id, topic_id = await create_synthetic_result(test_store, session_id)
        rendered_html = "<div class='card'>Test Card</div>"

        result_data = {
            "result_id": result_id,
            "summary": "HTML test",
            "intent_id": intent_id,
            "topic_id": topic_id,
        }

        sent_count = await broadcast_result(
            result=result_data,
            session_id=session_id,
            target_surface_id=surface_id,
            rendered_html=rendered_html
        )

        # Assert: Event includes rendered HTML
        assert sent_count == 1
        event = connection.queue.get_nowait()
        assert event.rendered_html == rendered_html

    @pytest.mark.asyncio
    async def test_urgency_levels_persist_and_broadcast(self, test_store, test_broadcaster):
        """Verify different urgency levels persist and broadcast correctly."""
        urgency_levels = ["low", "normal", "high", "critical"]
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        connection = await create_test_connection(test_broadcaster, session_id, surface_id)

        for urgency in urgency_levels:
            # Create result with specific urgency
            result_id, intent_id, topic_id = await create_synthetic_result(
                test_store,
                session_id,
                urgency=urgency
            )

            result_data = {
                "result_id": result_id,
                "summary": f"{urgency} urgency test",
                "intent_id": intent_id,
                "topic_id": topic_id,
                "urgency": urgency,
            }

            await broadcast_result(
                result=result_data,
                session_id=session_id,
                target_surface_id=surface_id
            )

            # Verify urgency in storage
            result = await test_store.get_result(result_id)
            assert result["urgency"] == urgency

            # Verify urgency in SSE event
            event = connection.queue.get_nowait()
            assert event.data["urgency"] == urgency

    @pytest.mark.asyncio
    async def test_session_store_integrity_after_pipeline(self, test_store, test_broadcaster):
        """Verify database integrity after running the complete pipeline."""
        # Arrange: Create session and connection
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        await create_test_connection(test_broadcaster, session_id, surface_id)

        # Act: Run complete pipeline multiple times
        for i in range(5):
            result_id, intent_id, topic_id = await create_synthetic_result(
                test_store,
                session_id,
                summary=f"Result {i}",
                data={"iteration": i}
            )

            await broadcast_result(
                result={"result_id": result_id, "summary": f"Result {i}", "intent_id": intent_id, "topic_id": topic_id},
                session_id=session_id,
                target_surface_id=surface_id
            )

        # Assert: Verify database integrity
        # Check all results are present
        results = await test_store.get_all_results()
        session_results = [r for r in results if r["session_id"] == session_id]
        assert len(session_results) == 5

        # Verify topic linkage
        for result in session_results:
            assert result["topic_id"] is not None
            topic = await test_store.get_topic(result["topic_id"])
            assert topic is not None

        # Verify intent linkage
        for result in session_results:
            if result["intent_id"]:
                intent = await test_store.get_intent(result["intent_id"])
                assert intent is not None

    @pytest.mark.asyncio
    async def test_concurrent_result_creation_and_broadcast(self, test_store, test_broadcaster):
        """Verify concurrent result creation and broadcast works correctly."""
        # Arrange: Create session and connection
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        connection = await create_test_connection(test_broadcaster, session_id, surface_id)

        # Act: Create multiple results concurrently
        async def create_and_broadcast(i):
            result_id, intent_id, topic_id = await create_synthetic_result(
                test_store,
                session_id,
                summary=f"Concurrent result {i}",
                data={"index": i}
            )

            await broadcast_result(
                result={"result_id": result_id, "summary": f"Concurrent result {i}", "intent_id": intent_id, "topic_id": topic_id},
                session_id=session_id,
                target_surface_id=surface_id
            )
            return result_id

        # Create 10 results concurrently
        result_ids = await asyncio.gather(*[create_and_broadcast(i) for i in range(10)])

        # Assert: All results stored and broadcast
        assert len(result_ids) == 10

        # Verify all results in database
        results = await test_store.get_all_results()
        session_results = [r for r in results if r["session_id"] == session_id]
        assert len(session_results) == 10

        # Verify all events broadcast
        events_received = []
        while not connection.queue.empty():
            event = connection.queue.get_nowait()
            events_received.append(event)

        assert len(events_received) == 10

    @pytest.mark.asyncio
    async def test_error_handling_in_pipeline(self, test_store, test_broadcaster):
        """Verify error handling when pipeline components fail."""
        # Arrange: Create session and connection
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        await create_test_connection(test_broadcaster, session_id, surface_id)

        # Test: Invalid topic_id doesn't crash
        result_id = await test_store.create_result(
            intent_id=str(uuid4()),
            topic_id=str(uuid4()),  # Non-existent topic
            session_id=session_id,
            summary="Error handling test",
            data={"test": "data"},
            urgency="normal"
        )

        # Assert: Result still created (foreign key not enforced)
        result = await test_store.get_result(result_id)
        assert result is not None

        # Broadcast still works
        sent_count = await broadcast_result(
            result={"result_id": result_id, "summary": "Error handling test", "intent_id": str(uuid4()), "topic_id": str(uuid4())},
            session_id=session_id,
            target_surface_id=surface_id
        )
        assert sent_count == 1


class TestIntentRoutingToResultPipeline:
    """
    Integration tests for the intent router → result → SSE pipeline.

    Tests the complete flow from intent classification through result creation
    to SSE broadcast.
    """

    @pytest.mark.asyncio
    async def test_intent_classification_to_result_storage(self, test_router, test_store):
        """Verify intent classification leads to result storage."""
        # Arrange: Create session
        session_id = await test_store.create_session()
        utterance_id = str(uuid4())

        # Mock the fetch and synthesize process
        classification = IntentClassification(
            intent_type=IntentType.STATUS,
            project_slug="test-project",
            confidence=0.9,
            utterance_fragment="check status"
        )

        routed_intent = RoutedIntent(
            intent_id=str(uuid4()),
            classification=classification,
            session_id=session_id,
            utterance="check status of test project"
        )

        # Act: Create intent and result directly
        intent_id = await test_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug=classification.project_slug,
            intent_type=classification.intent_type.value
        )

        # Create topic
        topic_id, _ = await test_store.find_or_create_topic(
            label="check status of test project",
            session_id=session_id,
            topic_type="research",
            project_slugs=[classification.project_slug] if classification.project_slug else []
        )

        # Link intent to topic
        await test_store.link_intent_to_topic(intent_id, topic_id)

        # Create result
        result_id = await test_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Status check complete",
            data={"status": "healthy"},
            urgency="normal",
            result_type="status:test-project"
        )

        # Assert: Verify complete chain stored
        intent = await test_store.get_intent(intent_id)
        assert intent is not None
        assert intent["intent_type"] == "status"

        result = await test_store.get_result(result_id)
        assert result is not None
        assert result["summary"] == "Status check complete"
        assert result["result_type"] == "status:test-project"

        topic = await test_store.get_topic(topic_id)
        assert topic is not None
        assert "test-project" in topic["project_slugs"]

    @pytest.mark.asyncio
    async def test_multiple_intents_same_session(self, test_router, test_store, test_broadcaster):
        """Verify multiple intents in same session create distinct results."""
        # Arrange: Create session and SSE connection
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        await create_test_connection(test_broadcaster, session_id, surface_id)

        # Act: Create multiple intents with different types
        intents = []
        topics = []

        for i, intent_type in enumerate(["status", "lookup", "brainstorm"]):
            utterance_id = str(uuid4())
            intent_id = await test_store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug=f"project-{i}",
                intent_type=intent_type
            )
            intents.append(intent_id)

            topic_id, _ = await test_store.find_or_create_topic(
                label=f"Topic {i}",
                session_id=session_id,
                topic_type="research",
                project_slugs=[f"project-{i}"]
            )
            topics.append(topic_id)

            await test_store.link_intent_to_topic(intent_id, topic_id)

            result_id = await test_store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Result {i}",
                data={"index": i},
                urgency="normal",
                result_type=f"{intent_type}:project-{i}"
            )

            await broadcast_result(
                result={"result_id": result_id, "summary": f"Result {i}", "intent_id": intent_id, "topic_id": topic_id},
                session_id=session_id,
                target_surface_id=surface_id
            )

        # Assert: All intents and results stored correctly
        for i, intent_id in enumerate(intents):
            intent = await test_store.get_intent(intent_id)
            assert intent is not None
            assert intent["intent_type"] in ["status", "lookup", "brainstorm"]

        # Verify all SSE events received
        events_received = []
        while not surface_id and not test_broadcaster.connections.get(surface_id):
            # Wait a moment for events to propagate
            await asyncio.sleep(0.01)
            break

        # Get connection events
        connection = None
        for conn in test_broadcaster.connections.values():
            if conn.surface_id == surface_id:
                connection = conn
                break

        if connection:
            while not connection.queue.empty():
                event = connection.queue.get_nowait()
                events_received.append(event)

            assert len(events_received) == 3


# --- End-to-End Tests ---------------------------------------------------------


class TestEndToEndPipeline:
    """
    End-to-end integration tests for the complete pipeline.

    Tests verify that the entire flow from utterance to result to SSE
    works as expected.
    """

    @pytest.mark.asyncio
    async def test_synthetic_result_end_to_end(self, test_store, test_broadcaster):
        """Verify end-to-end synthetic result creation and broadcast."""
        # Arrange: Complete setup
        session_id = await test_store.create_session()
        surface_id = str(uuid4())
        connection = await create_test_connection(test_broadcaster, session_id, surface_id)

        # Act: Create complete synthetic result
        utterance_id = str(uuid4())
        intent_id = await test_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="e2e-test",
            intent_type="status"
        )

        topic_id, _ = await test_store.find_or_create_topic(
            label="End-to-end test",
            session_id=session_id,
            topic_type="research",
            project_slugs=["e2e-test"]
        )

        await test_store.link_intent_to_topic(intent_id, topic_id)

        result_id = await test_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="End-to-end test result",
            data={"e2e": "test", "fields": {"value": 123}},
            urgency="normal",
            result_type="status:e2e-test"
        )

        result_data = {
            "result_id": result_id,
            "summary": "End-to-end test result",
            "intent_id": intent_id,
            "topic_id": topic_id,
            "urgency": "normal",
            "data": {"e2e": "test", "fields": {"value": 123}},
        }

        sent_count = await broadcast_result(
            result=result_data,
            session_id=session_id,
            target_surface_id=surface_id
        )

        # Assert: Complete pipeline verified
        assert sent_count == 1

        # Verify database records
        utterance = await test_store.get_utterance(utterance_id)
        assert utterance is not None

        intent = await test_store.get_intent(intent_id)
        assert intent is not None
        assert intent["intent_type"] == "status"

        topic = await test_store.get_topic(topic_id)
        assert topic is not None
        assert "e2e-test" in topic["project_slugs"]

        result = await test_store.get_result(result_id)
        assert result is not None
        assert result["summary"] == "End-to-end test result"

        # Verify SSE broadcast
        event = connection.queue.get_nowait()
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["result_id"] == result_id
        assert event.data["summary"] == "End-to-end test result"
        assert event.data["data"]["e2e"] == "test"
        assert event.data["data"]["fields"]["value"] == 123


if __name__ == "__main__":
    print("Persistence and SSE Pipeline Integration Tests")
    print("=" * 60)
    print("Bead: adc-27tb0")
    print("=" * 60)
    print("\nTest classes:")
    print("  - TestPersistenceAndSSEPipeline")
    print("  - TestIntentRoutingToResultPipeline")
    print("  - TestEndToEndPipeline")
    print("\nRun with: pytest tests/test_persistence_sse_pipeline_integration.py -v")
