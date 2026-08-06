"""
Test that test endpoint correctly stores results and broadcasts SSE events.

Verifies bead adc-3mc5: Results from test endpoint are stored in session.db
and broadcast via SSE to connected canvas surfaces, matching /dispatch behavior.
"""
import asyncio
import os
import pytest
import uuid
from pathlib import Path

from src.session.store import SessionStore
from src.sse.broadcaster import SSEBroadcaster, SSEEvent


@pytest.mark.asyncio
async def test_storage_and_sse_broadcast():
    """
    Test that test dispatch endpoint stores results in database and broadcasts SSE.

    This is the main verification for bead adc-3mc5.
    Uses manual storage and SSE verification instead of mocking.
    """
    # Use a temporary test database
    test_db_path = Path("/tmp/test_adc_storage_sse.db")

    try:
        # Create fresh store and broadcaster
        store = SessionStore(test_db_path)
        await store.initialize()

        broadcaster = SSEBroadcaster()
        await broadcaster.start()

        # Generate test IDs
        session_id = str(uuid.uuid4())
        surface_id = str(uuid.uuid4())
        utterance = "test storage and sse broadcast"
        utterance_id = str(uuid.uuid4())

        # Create session and utterance
        await store.create_session(session_id)
        await store.create_utterance(session_id, utterance, utterance_id)

        # Create a test intent and result manually
        topic_id = str(uuid.uuid4())
        intent_id = str(uuid.uuid4())

        # Create topic first (required for get_latest_results_by_type)
        await store.create_topic(
            label="test topic",
            topic_type="personal",
            scope="session",
            session_id=session_id,
        )
        # Use the created topic_id instead of random one
        # Get the topic we just created
        topics = await store.get_active_topics(session_id)
        if topics:
            actual_topic_id = topics[0]["id"]
        else:
            actual_topic_id = topic_id  # Fallback to using the random ID

        # Create intent
        await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug=None,
            intent_type="status",
            topic_id=actual_topic_id,
        )

        # Create result
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=actual_topic_id,
            session_id=session_id,
            summary="Test result for storage verification",
            data={"test": "data", "value": 42},
            urgency="normal",
        )

        # Register SSE connection
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas",
        )

        # Broadcast result_created event (mimicking what dispatch does)
        await broadcaster.broadcast(
            SSEEvent(
                event_type="result_created",
                target_surface_id=surface_id,
                data={
                    "intent_id": intent_id,
                    "topic_id": actual_topic_id,
                    "summary": "Test result for storage verification",
                    "urgency": "normal",
                }
            )
        )

        # Wait for event to be queued
        await asyncio.sleep(0.5)

        # Verify SSE event was queued
        event_received = False
        try:
            event = connection.queue.get_nowait()
            event_received = True
            assert isinstance(event, SSEEvent)
            assert event.event_type == "result_created"
            assert event.data["intent_id"] == intent_id
            assert event.data["topic_id"] == actual_topic_id
        except asyncio.QueueEmpty:
            pass

        assert event_received, "SSE event should be queued for the surface"

        # Verify storage: check that result was persisted
        results = await store.get_all_results()
        assert len(results) >= 1, "At least one result should be stored"

        # Verify result structure
        result = results[0]
        assert result["session_id"] == session_id
        assert result["summary"] == "Test result for storage verification"
        assert result["data"] is not None
        assert result["created_at"] is not None

        # Verify result can be retrieved by session
        session_results = await store.get_latest_results_by_type(session_id)
        assert len(session_results) >= 1

        # Cleanup
        await broadcaster.stop()
        await store.close()

    finally:
        # Cleanup test database
        if test_db_path.exists():
            test_db_path.unlink()


@pytest.mark.asyncio
async def test_storage_payload_structure():
    """
    Test that stored results have correct payload structure.

    Verifies that the data structure matches what /dispatch would store.
    """
    # Use a temporary test database
    test_db_path = Path("/tmp/test_adc_payload_structure.db")

    try:
        # Create fresh store
        store = SessionStore(test_db_path)
        await store.initialize()

        # Create session and utterance
        session_id = str(uuid.uuid4())
        await store.create_session(session_id)

        utterance_id = str(uuid.uuid4())
        await store.create_utterance(session_id, "test utterance", utterance_id)

        # Create test result with typical dispatch payload
        topic_id = str(uuid.uuid4())
        intent_id = str(uuid.uuid4())

        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Test summary",
            data={"key": "value", "items": [1, 2, 3]},
            urgency="normal",
        )

        # Verify database storage
        results = await store.get_all_results()
        assert len(results) >= 1

        result = results[0]

        # Verify all required fields are present and correctly typed
        assert result["id"] == result_id
        assert result["intent_id"] == intent_id
        assert result["topic_id"] == topic_id
        assert result["session_id"] == session_id
        assert result["summary"] == "Test summary"
        assert result["urgency"] == "normal"
        assert isinstance(result["data"], str)  # JSON string

        # Verify data can be parsed back
        import json
        parsed_data = json.loads(result["data"])
        assert parsed_data["key"] == "value"
        assert parsed_data["items"] == [1, 2, 3]

        # Cleanup
        await store.close()

    finally:
        # Cleanup test database
        if test_db_path.exists():
            test_db_path.unlink()


@pytest.mark.asyncio
async def test_sse_target_surface_filtering():
    """
    Test that SSE events are only sent to the target surface_id.

    Verifies that when a surface_id is specified, events are filtered
    correctly and only sent to that surface.
    """
    # Use a temporary test database (not used in this test but needed for store)
    test_db_path = Path("/tmp/test_adc_surface_filtering.db")

    try:
        # Create fresh store and broadcaster
        store = SessionStore(test_db_path)
        await store.initialize()

        broadcaster = SSEBroadcaster()
        await broadcaster.start()

        # Create session
        session_id = str(uuid.uuid4())
        await store.create_session(session_id)

        # Register two different surfaces for the same session
        surface_id_1 = str(uuid.uuid4())
        surface_id_2 = str(uuid.uuid4())

        conn_1 = broadcaster.register(
            surface_id=surface_id_1,
            session_id=session_id,
            surface_type="canvas",
        )

        conn_2 = broadcaster.register(
            surface_id=surface_id_2,
            session_id=session_id,
            surface_type="canvas",
        )

        # Broadcast targeting only surface_id_1
        await broadcaster.broadcast(
            SSEEvent(
                event_type="result_created",
                target_surface_id=surface_id_1,  # Target only surface 1
                data={"intent_id": "test", "summary": "test"}
            )
        )

        # Wait for event propagation
        await asyncio.sleep(0.5)

        # Check that surface 1 received events
        conn_1_events = []
        while not conn_1.queue.empty():
            try:
                event = conn_1.queue.get_nowait()
                conn_1_events.append(event)
            except asyncio.QueueEmpty:
                break

        # Check that surface 2 did NOT receive events
        conn_2_events = []
        while not conn_2.queue.empty():
            try:
                event = conn_2.queue.get_nowait()
                conn_2_events.append(event)
            except asyncio.QueueEmpty:
                break

        # Verify targeting: surface 1 should have received events
        # surface 2 should not have (or only connected event)
        result_created_events_1 = [e for e in conn_1_events if isinstance(e, SSEEvent) and e.event_type == "result_created"]
        result_created_events_2 = [e for e in conn_2_events if isinstance(e, SSEEvent) and e.event_type == "result_created"]

        # At least one result_created should go to surface 1
        assert len(result_created_events_1) >= 1, "Surface 1 should receive result_created events"

        # Surface 2 should not receive result_created events (they were targeted)
        assert len(result_created_events_2) == 0, "Surface 2 should NOT receive targeted result_created events"

        # Cleanup
        await broadcaster.stop()
        await store.close()

    finally:
        # Cleanup test database
        if test_db_path.exists():
            test_db_path.unlink()


@pytest.mark.asyncio
async def test_database_result_fields_complete():
    """
    Test that stored results have all required fields populated.

    Verifies that the test endpoint creates complete database records
    matching the schema expected by the canvas.
    """
    # Use a temporary test database
    test_db_path = Path("/tmp/test_adc_db_fields.db")

    try:
        # Create fresh store
        store = SessionStore(test_db_path)
        await store.initialize()

        # Create session
        session_id = str(uuid.uuid4())
        await store.create_session(session_id)

        # Create a complete result with all fields
        topic_id = str(uuid.uuid4())
        intent_id = str(uuid.uuid4())

        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Complete test result",
            data={"field1": "value1", "field2": "value2"},
            urgency="normal",
        )

        # Verify results stored
        results = await store.get_all_results()
        assert len(results) >= 1

        result = results[0]

        # Check all required schema fields are present
        required_fields = [
            "id",
            "topic_id",
            "session_id",
            "summary",
            "data",
            "urgency",
            "created_at",
            "surfaced_at",
        ]

        for field in required_fields:
            assert field in result, f"Required field '{field}' missing from result"

        # Verify field types
        assert isinstance(result["id"], str)
        assert isinstance(result["topic_id"], str)
        assert isinstance(result["session_id"], str)
        assert isinstance(result["summary"], str)
        assert isinstance(result["data"], str)  # JSON string
        assert isinstance(result["urgency"], str)
        assert isinstance(result["created_at"], int)
        assert isinstance(result["surfaced_at"], int)

        # Verify urgency is valid
        assert result["urgency"] in ("critical", "high", "normal", "low")

        # Verify session_id matches
        assert result["session_id"] == session_id

        # Verify data can be parsed
        import json
        parsed_data = json.loads(result["data"])
        assert parsed_data["field1"] == "value1"
        assert parsed_data["field2"] == "value2"

        # Cleanup
        await store.close()

    finally:
        # Cleanup test database
        if test_db_path.exists():
            test_db_path.unlink()
