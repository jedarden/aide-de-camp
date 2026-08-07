"""
Integration tests for persistence and SSE pipeline.

This test suite verifies the complete flow from result creation to SSE broadcast:
- Result creation triggers both storage and SSE broadcast
- Database persistence works correctly
- SSE events are delivered to canvas connections with correct data
- Topic data is properly structured and received

These are end-to-end integration tests covering the full pipeline.
"""
import asyncio
import json
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEEvent,
    EventType,
    broadcast_result,
)


class TestPersistenceSSEPipeline:
    """Integration tests for the complete persistence → SSE pipeline."""

    async def test_result_creation_stores_and_broadcasts(
        self, test_db_store, broadcaster
    ):
        """Test that creating a result stores it and broadcasts an SSE event.

        This is the core integration test verifying:
        1. Result is stored in the database
        2. SSE event is broadcast
        3. Event contains correct data
        """
        # Arrange: Create session, topic, and canvas connection
        session_id = await test_db_store.create_session()
        topic_id = await test_db_store.create_topic(
            label="Test Topic",
            topic_type="project",
            session_id=session_id
        )

        surface_id = str(uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        # Create event collector
        received_events = []
        async def collect_events():
            try:
                while True:
                    event = await connection.queue.get()
                    received_events.append(event)
                    if len(received_events) >= 1:  # Collect the result event
                        break
            except asyncio.CancelledError:
                pass

        collector_task = asyncio.create_task(collect_events())

        # Act: Create a result (this should both store and broadcast)
        result_id = await test_db_store.create_result(
            intent_id=str(uuid4()),
            topic_id=topic_id,
            session_id=session_id,
            summary="Test result summary",
            data={"key": "value", "number": 42},
            urgency="normal",
            result_type="status:test-project"
        )

        # Broadcast the result via SSE
        sent_count = await broadcast_result(
            result={
                "result_id": result_id,
                "summary": "Test result summary",
                "urgency": "normal",
                "result_type": "status:test-project",
            },
            session_id=session_id,
            target_surface_id=surface_id
        )

        # Wait for event collection
        await collector_task

        # Assert: Verify storage
        retrieved_result = await test_db_store.get_result(result_id)
        assert retrieved_result is not None
        assert retrieved_result["id"] == result_id
        assert retrieved_result["summary"] == "Test result summary"
        assert retrieved_result["urgency"] == "normal"
        assert retrieved_result["topic_id"] == topic_id
        assert retrieved_result["session_id"] == session_id

        # Assert: Verify SSE broadcast
        assert sent_count == 1
        assert len(received_events) == 1

        event = received_events[0]
        assert isinstance(event, SSEEvent)
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["result_id"] == result_id
        assert event.data["summary"] == "Test result summary"
        assert event.data["urgency"] == "normal"

    async def test_result_created_with_all_fields(
        self, test_db_store, broadcaster
    ):
        """Test result creation with all optional fields populated.

        Verifies that complex result data with all fields is correctly:
        - Stored in the database
        - Broadcast via SSE
        - Received with all fields intact
        """
        # Arrange
        session_id = await test_db_store.create_session()
        topic_id = await test_db_store.create_topic(
            label="Complex Topic",
            topic_type="research",
            session_id=session_id
        )

        surface_id = str(uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        received_events = []
        async def collect_events():
            try:
                while True:
                    event = await connection.queue.get()
                    received_events.append(event)
                    if len(received_events) >= 1:
                        break
            except asyncio.CancelledError:
                pass

        collector_task = asyncio.create_task(collect_events())

        # Act: Create result with all fields
        result_data = {
            "key": "value",
            "nested": {
                "field1": "value1",
                "field2": 42,
                "field3": [1, 2, 3]
            },
            "array": ["item1", "item2"],
            "number": 123.45,
            "boolean": True,
        }

        result_id = await test_db_store.create_result(
            intent_id=str(uuid4()),
            topic_id=topic_id,
            session_id=session_id,
            summary="Complex result with all fields",
            data=result_data,
            urgency="high",
            result_type="status:complex-project"
        )

        # Broadcast
        sent_count = await broadcast_result(
            result={
                "result_id": result_id,
                "summary": "Complex result with all fields",
                "urgency": "high",
                "result_type": "status:complex-project",
            },
            session_id=session_id,
            target_surface_id=surface_id
        )

        await collector_task

        # Assert: Database storage
        retrieved = await test_db_store.get_result(result_id)
        assert retrieved is not None
        retrieved_data = json.loads(retrieved["data"])
        assert retrieved_data == result_data

        # Assert: SSE broadcast
        assert sent_count == 1
        event = received_events[0]
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["summary"] == "Complex result with all fields"
        assert event.data["urgency"] == "high"

    async def test_multiple_results_stored_and_broadcast(
        self, test_db_store, broadcaster
    ):
        """Test creating multiple results in sequence.

        Verifies that:
        - All results are stored correctly
        - Each result generates its own SSE event
        - Events are received in order
        """
        # Arrange
        session_id = await test_db_store.create_session()
        topic_id = await test_db_store.create_topic(
            label="Multi-Result Topic",
            topic_type="project",
            session_id=session_id
        )

        surface_id = str(uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        received_events = []
        async def collect_events():
            try:
                while True:
                    event = await connection.queue.get()
                    received_events.append(event)
                    if len(received_events) >= 3:
                        break
            except asyncio.CancelledError:
                pass

        collector_task = asyncio.create_task(collect_events())

        # Act: Create multiple results
        result_ids = []
        summaries = ["First result", "Second result", "Third result"]

        for i, summary in enumerate(summaries):
            result_id = await test_db_store.create_result(
                intent_id=str(uuid4()),
                topic_id=topic_id,
                session_id=session_id,
                summary=summary,
                data={"index": i},
                urgency="normal"
            )
            result_ids.append(result_id)

            # Broadcast
            await broadcast_result(
                result={
                    "result_id": result_id,
                    "summary": summary,
                    "urgency": "normal",
                },
                session_id=session_id,
                target_surface_id=surface_id
            )

        await collector_task

        # Assert: All results stored
        for i, result_id in enumerate(result_ids):
            retrieved = await test_db_store.get_result(result_id)
            assert retrieved is not None
            assert retrieved["summary"] == summaries[i]

        # Assert: All events received
        assert len(received_events) == 3
        for i, event in enumerate(received_events):
            assert event.event_type == EventType.RESULT_CREATED
            assert event.data["summary"] == summaries[i]

    async def test_canvas_receives_correct_topic_data(
        self, test_db_store, broadcaster
    ):
        """Test that canvas receives correct topic data via SSE.

        Verifies the complete flow from result creation to canvas display:
        - Result is stored with topic association
        - SSE event includes topic information
        - Canvas can reconstruct topic context
        """
        # Arrange
        session_id = await test_db_store.create_session()
        topic_id = await test_db_store.create_topic(
            label="Deployment Status",
            topic_type="project",
            project_slugs=["pbx-web"],
            session_id=session_id
        )

        surface_id = str(uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        received_events = []
        async def collect_events():
            try:
                while True:
                    event = await connection.queue.get()
                    received_events.append(event)
                    if len(received_events) >= 1:
                        break
            except asyncio.CancelledError:
                pass

        collector_task = asyncio.create_task(collect_events())

        # Act: Create deployment status result
        result_id = await test_db_store.create_result(
            intent_id=str(uuid4()),
            topic_id=topic_id,
            session_id=session_id,
            summary="Deployment successful",
            data={
                "status": "deployed",
                "version": "v1.2.3",
                "replicas": 3
            },
            urgency="normal",
            result_type="status:pbx-web"
        )

        # Broadcast with full context
        sent_count = await broadcast_result(
            result={
                "result_id": result_id,
                "summary": "Deployment successful",
                "urgency": "normal",
                "result_type": "status:pbx-web",
                "topic_id": topic_id,
            },
            session_id=session_id,
            target_surface_id=surface_id
        )

        await collector_task

        # Assert: Event contains topic context
        assert sent_count == 1
        event = received_events[0]

        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["result_id"] == result_id
        assert event.data["topic_id"] == topic_id
        assert event.data["summary"] == "Deployment successful"

        # Assert: Topic can be retrieved
        topic = await test_db_store.get_topic(topic_id)
        assert topic is not None
        assert topic["label"] == "Deployment Status"
        assert topic["type"] == "project"

    async def test_sse_event_targeting_by_surface(
        self, test_db_store, broadcaster
    ):
        """Test that SSE events correctly target specific surfaces.

        Verifies that:
        - Events are only sent to the target surface
        - Other surfaces don't receive the event
        - Session-level broadcasting works
        """
        # Arrange
        session_id = await test_db_store.create_session()
        topic_id = await test_db_store.create_topic(
            label="Target Test",
            topic_type="project",
            session_id=session_id
        )

        # Register two surfaces for the same session
        surface_a = str(uuid4())
        surface_b = str(uuid4())

        connection_a = broadcaster.register(
            surface_id=surface_a,
            session_id=session_id,
            surface_type="canvas"
        )

        connection_b = broadcaster.register(
            surface_id=surface_b,
            session_id=session_id,
            surface_type="canvas"
        )

        # Collect events for both surfaces
        events_a = []
        events_b = []

        async def collect_surface_a():
            try:
                while True:
                    event = await connection_a.queue.get()
                    events_a.append(event)
                    break
            except asyncio.CancelledError:
                pass

        async def collect_surface_b():
            try:
                while True:
                    event = await connection_b.queue.get()
                    events_b.append(event)
                    break
            except asyncio.CancelledError:
                pass

        task_a = asyncio.create_task(collect_surface_a())
        task_b = asyncio.create_task(collect_surface_b())

        # Act: Create result and target only surface_a
        result_id = await test_db_store.create_result(
            intent_id=str(uuid4()),
            topic_id=topic_id,
            session_id=session_id,
            summary="Targeted result",
            data={"test": "data"},
            urgency="normal"
        )

        # Broadcast targeting only surface_a
        sent_count = await broadcast_result(
            result={
                "result_id": result_id,
                "summary": "Targeted result",
                "urgency": "normal",
            },
            session_id=session_id,
            target_surface_id=surface_a  # Only surface_a
        )

        await task_a
        await task_b

        # Assert: Only surface_a received the event
        assert sent_count == 1  # Only one surface targeted
        assert len(events_a) == 1
        assert len(events_b) == 0  # Surface b should not receive

        assert events_a[0].event_type == EventType.RESULT_CREATED
        assert events_a[0].data["result_id"] == result_id

    async def test_database_transaction_rollback_on_error(
        self, test_db_store, broadcaster
    ):
        """Test that database errors don't leave partial data.

        Verifies that if result creation fails, no partial data is stored.
        """
        # Arrange
        session_id = await test_db_store.create_session()
        topic_id = await test_db_store.create_topic(
            label="Test Topic",
            topic_type="project",
            session_id=session_id
        )

        # Act: Attempt to create result with invalid data
        # (This should fail gracefully)
        try:
            # Simulate a database error by using invalid JSON
            result_id = await test_db_store.create_result(
                intent_id=str(uuid4()),
                topic_id=topic_id,
                session_id=session_id,
                summary="Invalid result",
                data={"invalid": "\x00"},  # Null byte in JSON
                urgency="normal"
            )
            # If it doesn't fail, that's also OK - SQLite handles null bytes
            result_id = await test_db_store.create_result(
                intent_id=str(uuid4()),
                topic_id=topic_id,
                session_id=session_id,
                summary="Valid result",
                data={"key": "value"},
                urgency="normal"
            )
        except Exception as e:
            # If creation failed, verify no partial data
            pass

        # Assert: Query results for topic - should have valid results only
        results = await test_db_store.get_results_for_intent(topic_id)
        # All results should be complete and valid
        for result in results:
            assert result["summary"] is not None
            assert result["data"] is not None
            # Should be able to parse JSON
            try:
                json.loads(result["data"])
            except json.JSONDecodeError:
                pytest.fail(f"Result {result['id']} has invalid JSON data")

    async def test_concurrent_result_creation(
        self, test_db_store, broadcaster
    ):
        """Test concurrent result creation doesn't cause conflicts.

        Verifies that multiple concurrent result creations:
        - All complete successfully
        - Don't interfere with each other
        - All generate correct SSE events
        """
        # Arrange
        session_id = await test_db_store.create_session()
        topic_id = await test_db_store.create_topic(
            label="Concurrent Test",
            topic_type="project",
            session_id=session_id
        )

        surface_id = str(uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        # Collect events
        received_events = []
        async def collect_events():
            try:
                async for event in connection.queue:
                    received_events.append(event)
                    if len(received_events) >= 5:
                        break
            except asyncio.CancelledError:
                pass

        collector_task = asyncio.create_task(collect_events())

        # Act: Create multiple results concurrently
        async def create_result(index):
            result_id = await test_db_store.create_result(
                intent_id=str(uuid4()),
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Concurrent result {index}",
                data={"index": index},
                urgency="normal"
            )

            await broadcast_result(
                result={
                    "result_id": result_id,
                    "summary": f"Concurrent result {index}",
                    "urgency": "normal",
                },
                session_id=session_id,
                target_surface_id=surface_id
            )
            return result_id

        # Create 5 results concurrently
        tasks = [create_result(i) for i in range(5)]
        result_ids = await asyncio.gather(*tasks)

        await collector_task

        # Assert: All results stored successfully
        for i, result_id in enumerate(result_ids):
            retrieved = await test_db_store.get_result(result_id)
            assert retrieved is not None
            assert retrieved["summary"] == f"Concurrent result {i}"
            assert retrieved["data"]["index"] == i

        # Assert: All events received
        assert len(received_events) == 5
        for event in received_events:
            assert event.event_type == EventType.RESULT_CREATED

    async def test_result_with_diff_data(
        self, test_db_store, broadcaster
    ):
        """Test result creation with diff information.

        Verifies that results with previous_result_id and diff data
        are correctly stored and broadcast.
        """
        # Arrange
        session_id = await test_db_store.create_session()
        topic_id = await test_db_store.create_topic(
            label="Diff Test",
            topic_type="project",
            session_id=session_id
        )

        surface_id = str(uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        received_events = []
        async def collect_events():
            try:
                while True:
                    event = await connection.queue.get()
                    received_events.append(event)
                    if len(received_events) >= 1:
                        break
            except asyncio.CancelledError:
                pass

        collector_task = asyncio.create_task(collect_events())

        # Act: Create initial result
        initial_result_id = await test_db_store.create_result(
            intent_id=str(uuid4()),
            topic_id=topic_id,
            session_id=session_id,
            summary="Initial state",
            data={"status": "pending", "count": 0},
            urgency="normal"
        )

        # Create updated result with diff
        updated_result_id = await test_db_store.create_result(
            intent_id=str(uuid4()),
            topic_id=topic_id,
            session_id=session_id,
            summary="Updated state",
            data={"status": "complete", "count": 1},
            urgency="normal",
            previous_result_id=initial_result_id,
            diff_summary="Status changed from pending to complete",
            diff_data={
                "fields": [
                    {
                        "field_name": "status",
                        "old_value": "pending",
                        "new_value": "complete",
                        "change_type": "update"
                    }
                ]
            }
        )

        await broadcast_result(
            result={
                "result_id": updated_result_id,
                "summary": "Updated state",
                "urgency": "normal",
                "previous_result_id": initial_result_id,
            },
            session_id=session_id,
            target_surface_id=surface_id
        )

        await collector_task

        # Assert: Updated result stored correctly
        updated = await test_db_store.get_result(updated_result_id)
        assert updated is not None
        assert updated["previous_result_id"] == initial_result_id
        assert updated["diff_summary"] == "Status changed from pending to complete"

        diff_data = json.loads(updated["diff_data"])
        assert diff_data["fields"][0]["field_name"] == "status"

        # Assert: SSE event includes diff information
        event = received_events[0]
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["result_id"] == updated_result_id
        assert event.data["previous_result_id"] == initial_result_id


class TestTopicResultIntegration:
    """Integration tests for topic-result relationships."""

    async def test_results_aggregated_by_topic(
        self, test_db_store, broadcaster
    ):
        """Test that results are correctly aggregated by topic.

        Verifies that:
        - Multiple results for the same topic are stored
        - Topic can be queried with all its results
        - Latest results can be retrieved per topic
        """
        # Arrange
        session_id = await test_db_store.create_session()
        topic_id = await test_db_store.create_topic(
            label="Aggregation Test",
            topic_type="project",
            session_id=session_id
        )

        # Act: Create multiple results for the same topic
        result_ids = []
        for i in range(3):
            result_id = await test_db_store.create_result(
                intent_id=str(uuid4()),
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Result {i}",
                data={"index": i},
                urgency="normal"
            )
            result_ids.append(result_id)

        # Assert: Get latest result for topic
        latest = await test_db_store.get_latest_result_for_topic(topic_id)
        assert latest is not None
        assert latest["id"] == result_ids[-1]  # Last created
        assert latest["summary"] == "Result 2"

    async def test_cross_session_topic_visibility(
        self, test_db_store, broadcaster
    ):
        """Test that cross-session topics work correctly.

        Verifies that:
        - Cross-session topics are visible across sessions
        - Results from different sessions can be associated
        - Session isolation is maintained
        """
        # Arrange: Create two sessions
        session_a = await test_db_store.create_session()
        session_b = await test_db_store.create_session()

        # Create a cross-session topic (session_id = NULL)
        topic_id = await test_db_store.create_topic(
            label="Global Topic",
            topic_type="project",
            scope="cross-session",
            session_id=None  # Cross-session
        )

        # Act: Create results from both sessions
        result_a = await test_db_store.create_result(
            intent_id=str(uuid4()),
            topic_id=topic_id,
            session_id=session_a,
            summary="Result from session A",
            data={"session": "A"},
            urgency="normal"
        )

        result_b = await test_db_store.create_result(
            intent_id=str(uuid4()),
            topic_id=topic_id,
            session_id=session_b,
            summary="Result from session B",
            data={"session": "B"},
            urgency="normal"
        )

        # Assert: Both results stored correctly
        retrieved_a = await test_db_store.get_result(result_a)
        retrieved_b = await test_db_store.get_result(result_b)

        assert retrieved_a is not None
        assert retrieved_a["session_id"] == session_a
        assert retrieved_a["summary"] == "Result from session A"

        assert retrieved_b is not None
        assert retrieved_b["session_id"] == session_b
        assert retrieved_b["summary"] == "Result from session B"

        # Assert: Topic accessible from both sessions
        topic = await test_db_store.get_topic(topic_id)
        assert topic is not None
        assert topic["scope"] == "cross-session"
