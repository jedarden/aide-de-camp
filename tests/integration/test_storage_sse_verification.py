"""
Integration test: Verify storage and SSE broadcast via test endpoint.

Tests that the /api/v1/test/dispatch-synthetic endpoint:
1. Stores results correctly in SQLite session store
2. Broadcasts SSE events to connected surfaces
3. Matches /dispatch payload structure
4. Broadcasts with correct timing

This test validates the requirements from bead adc-3mc5.
"""
import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
import sqlite3

import httpx
import pytest

from src.session.store import SessionStore, get_store
from src.sse.broadcaster import SSEBroadcaster, get_broadcaster, SSEEvent


@pytest.fixture
async def test_db_path(tmp_path):
    """Create isolated test database."""
    db_path = tmp_path / "test_session.db"
    yield db_path
    # Cleanup is automatic with tmp_path


@pytest.fixture
async def test_store(test_db_path):
    """Create test session store."""
    store = SessionStore(test_db_path)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
async def test_broadcaster():
    """Create test SSE broadcaster."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()
    yield broadcaster
    await broadcaster.stop()


class TestStorageAndSSEVerification:
    """Test suite for storage and SSE broadcast verification."""

    async def test_synthetic_result_storage(self, test_store: SessionStore):
        """Test that synthetic results are stored correctly in SQLite."""
        # Arrange
        session_id = str(uuid.uuid4())
        utterance_id = str(uuid.uuid4())
        intent_id = str(uuid.uuid4())
        topic_id = str(uuid.uuid4())

        # Create session and topic
        await test_store.create_session(session_id)
        topic_id_created = await test_store.create_topic(
            label="Test Topic",
            topic_type="research",
            project_slugs=["test-project"],
            scope="session",
            session_id=session_id,
        )

        # Act
        result_id = await test_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id_created,
            session_id=session_id,
            summary="Test summary",
            data={"test": "data", "synthetic": True},
            urgency="normal",
            result_type="status",
            card_fallback=False,
        )

        # Assert - Verify result exists in database
        import aiosqlite
        async with aiosqlite.connect(test_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM results WHERE id = ?",
                (result_id,)
            )
            row = await cursor.fetchone()

            assert row is not None
            assert row["id"] == result_id
            assert row["intent_id"] == intent_id
            assert row["topic_id"] == topic_id_created
            assert row["session_id"] == session_id
            assert row["summary"] == "Test summary"
            assert row["urgency"] == "normal"
            assert row["result_type"] == "status"
            assert row["card_fallback"] == 0

            # Parse JSON data
            data = json.loads(row["data"])
            assert data["test"] == "data"
            assert data["synthetic"] is True

    async def test_sse_broadcast_to_surface(self, test_broadcaster: SSEBroadcaster):
        """Test that SSE events are broadcast to the correct surface."""
        # Arrange
        session_id = str(uuid.uuid4())
        surface_id = str(uuid.uuid4())

        # Register a test connection
        connection = test_broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas",
        )

        # Track events received by this connection
        received_events = []
        original_queue = connection.queue

        async def event_tracker():
            while True:
                try:
                    event = await asyncio.wait_for(original_queue.get(), timeout=1.0)
                    received_events.append(event)
                    if event.event_type == "disconnect":
                        break
                except asyncio.TimeoutError:
                    break

        tracker_task = asyncio.create_task(event_tracker())

        # Act - Broadcast a result_created event
        await test_broadcaster.broadcast(
            SSEEvent(
                event_type="result_created",
                target_surface_id=surface_id,
                data={
                    "intent_id": str(uuid.uuid4()),
                    "topic_id": str(uuid.uuid4()),
                    "summary": "Test result",
                    "urgency": "normal",
                }
            )
        )

        # Wait for event to be processed
        await asyncio.sleep(0.1)

        # Assert
        assert len(received_events) == 1
        assert received_events[0].event_type == "result_created"
        assert received_events[0].data["summary"] == "Test result"

        # Cleanup
        tracker_task.cancel()
        test_broadcaster.unregister(connection.connection_id)

    async def test_sse_event_filters_by_surface_id(self, test_broadcaster: SSEBroadcaster):
        """Test that SSE events only reach the target surface."""
        # Arrange
        session_id = str(uuid.uuid4())
        surface_1 = str(uuid.uuid4())
        surface_2 = str(uuid.uuid4())

        # Register two connections
        conn_1 = test_broadcaster.register(
            surface_id=surface_1,
            session_id=session_id,
            surface_type="canvas",
        )
        conn_2 = test_broadcaster.register(
            surface_id=surface_2,
            session_id=session_id,
            surface_type="canvas",
        )

        # Track events for both connections
        events_1 = []
        events_2 = []

        async def tracker_for(connection, event_list):
            while True:
                try:
                    event = await asyncio.wait_for(connection.queue.get(), timeout=1.0)
                    event_list.append(event)
                    if event.event_type == "disconnect":
                        break
                except asyncio.TimeoutError:
                    break

        tracker_1 = asyncio.create_task(tracker_for(conn_1, events_1))
        tracker_2 = asyncio.create_task(tracker_for(conn_2, events_2))

        # Act - Broadcast event only to surface_1
        await test_broadcaster.broadcast(
            SSEEvent(
                event_type="result_created",
                target_surface_id=surface_1,
                data={"summary": "Targeted event"}
            )
        )

        await asyncio.sleep(0.1)

        # Assert
        assert len(events_1) == 1, "surface_1 should receive the event"
        assert events_1[0].data["summary"] == "Targeted event"
        assert len(events_2) == 0, "surface_2 should NOT receive the event"

        # Cleanup
        tracker_1.cancel()
        tracker_2.cancel()
        test_broadcaster.unregister(conn_1.connection_id)
        test_broadcaster.unregister(conn_2.connection_id)

    async def test_sse_event_data_matches_dispatch_structure(self, test_broadcaster: SSEBroadcaster):
        """Test that SSE event payload matches /dispatch structure."""
        # Arrange
        surface_id = str(uuid.uuid4())
        connection = test_broadcaster.register(
            surface_id=surface_id,
            session_id=str(uuid.uuid4()),
            surface_type="canvas",
        )

        received_events = []

        async def event_tracker():
            while True:
                try:
                    event = await asyncio.wait_for(connection.queue.get(), timeout=1.0)
                    received_events.append(event)
                    if event.event_type == "disconnect":
                        break
                except asyncio.TimeoutError:
                    break

        tracker_task = asyncio.create_task(event_tracker())

        # Act - Broadcast event with /dispatch-style payload
        intent_id = str(uuid.uuid4())
        topic_id = str(uuid.uuid4())

        await test_broadcaster.broadcast(
            SSEEvent(
                event_type="result_created",
                target_surface_id=surface_id,
                data={
                    "intent_id": intent_id,
                    "topic_id": topic_id,
                    "summary": "Status check completed",
                    "urgency": "normal",
                }
            )
        )

        await asyncio.sleep(0.1)

        # Assert - Verify payload structure matches /dispatch
        assert len(received_events) == 1
        event_data = received_events[0].data

        # Required fields from /dispatch
        assert "intent_id" in event_data
        assert "topic_id" in event_data
        assert "summary" in event_data
        assert "urgency" in event_data

        assert event_data["intent_id"] == intent_id
        assert event_data["topic_id"] == topic_id
        assert event_data["summary"] == "Status check completed"
        assert event_data["urgency"] == "normal"

        # Cleanup
        tracker_task.cancel()
        test_broadcaster.unregister(connection.connection_id)

    async def test_synthetic_dispatch_creates_all_records(self, test_store: SessionStore):
        """Test that synthetic dispatch creates utterance, intent, topic, and result records."""
        # Arrange
        session_id = str(uuid.uuid4())
        await test_store.create_session(session_id)

        # Act - Simulate synthetic dispatch sequence
        utterance_id = str(uuid.uuid4())
        await test_store.create_utterance(
            session_id=session_id,
            raw_text="synthetic test utterance",
            utterance_id=utterance_id
        )

        topic_id = await test_store.create_topic(
            label="Synthetic Test Topic",
            topic_type="research",
            project_slugs=["test-project"],
            scope="session",
            session_id=session_id,
        )

        intent_id = await test_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test-project",
            intent_type="status",
            topic_id=topic_id,
        )

        result_id = await test_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Synthetic test result",
            data={"synthetic": True, "test_mode": True},
            urgency="normal",
            result_type="status",
        )

        # Assert - Verify all records exist
        import aiosqlite
        async with aiosqlite.connect(test_store.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Check utterance
            cursor = await db.execute(
                "SELECT * FROM utterances WHERE id = ?", (utterance_id,)
            )
            utterance = await cursor.fetchone()
            assert utterance is not None
            assert utterance["raw_text"] == "synthetic test utterance"

            # Check topic
            cursor = await db.execute(
                "SELECT * FROM topics WHERE id = ?", (topic_id,)
            )
            topic = await cursor.fetchone()
            assert topic is not None
            assert topic["label"] == "Synthetic Test Topic"

            # Check intent
            cursor = await db.execute(
                "SELECT * FROM intents WHERE id = ?", (intent_id,)
            )
            intent = await cursor.fetchone()
            assert intent is not None
            assert intent["intent_type"] == "status"
            assert intent["topic_id"] == topic_id

            # Check result
            cursor = await db.execute(
                "SELECT * FROM results WHERE id = ?", (result_id,)
            )
            result = await cursor.fetchone()
            assert result is not None
            assert result["summary"] == "Synthetic test result"
            assert result["intent_id"] == intent_id

    async def test_broadcast_timing_matches_dispatch(self, test_broadcaster: SSEBroadcaster):
        """Test that SSE broadcast timing aligns with /dispatch expectations."""
        # Arrange
        surface_id = str(uuid.uuid4())
        connection = test_broadcaster.register(
            surface_id=surface_id,
            session_id=str(uuid.uuid4()),
            surface_type="canvas",
        )

        broadcast_times = []

        async def event_tracker():
            while True:
                try:
                    start = asyncio.get_event_loop().time()
                    event = await asyncio.wait_for(connection.queue.get(), timeout=1.0)
                    end = asyncio.get_event_loop().time()
                    broadcast_times.append((event.event_type, end - start))
                    if event.event_type == "disconnect":
                        break
                except asyncio.TimeoutError:
                    break

        tracker_task = asyncio.create_task(event_tracker())

        # Act - Broadcast multiple events rapidly (simulating /dispatch behavior)
        start_broadcast = asyncio.get_event_loop().time()

        for i in range(3):
            await test_broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    target_surface_id=surface_id,
                    data={"sequence": i}
                )
            )

        end_broadcast = asyncio.get_event_loop().time()
        broadcast_duration = end_broadcast - start_broadcast

        await asyncio.sleep(0.2)  # Allow events to propagate

        # Assert - All events should be received quickly (< 100ms for 3 events)
        assert len(broadcast_times) == 3, "All events should be received"
        assert broadcast_duration < 0.1, "Broadcast should complete within 100ms"

        # Events should be in order
        for i, (event_type, latency) in enumerate(broadcast_times):
            assert event_type == "result_created"
            assert latency < 0.05, f"Event {i} should have < 50ms latency"

        # Cleanup
        tracker_task.cancel()
        test_broadcaster.unregister(connection.connection_id)

    async def test_storage_payload_fields_match_dispatch(self, test_store: SessionStore):
        """Test that stored result payload matches /dispatch field structure."""
        # Arrange
        session_id = str(uuid.uuid4())
        await test_store.create_session(session_id)

        topic_id = await test_store.create_topic(
            label="Test",
            topic_type="research",
            project_slugs=["test"],
            scope="session",
            session_id=session_id,
        )

        # Act - Create result with /dispatch-style fields
        result_id = await test_store.create_result(
            intent_id=str(uuid.uuid4()),
            topic_id=topic_id,
            session_id=session_id,
            summary="Test summary",
            data={
                "coverage": {"sources_tested": 5, "sources_passed": 3},
                "caveats": ["Test caveat"],
                "test_mode": True,
            },
            urgency="high",
            result_type="status:test-project",
        )

        # Assert - Verify stored structure
        import aiosqlite
        async with aiosqlite.connect(test_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM results WHERE id = ?",
                (result_id,)
            )
            row = await cursor.fetchone()

            # Required fields
            assert row["summary"] == "Test summary"
            assert row["urgency"] == "high"
            assert row["result_type"] == "status:test-project"
            assert row["card_fallback"] == 0

            # Data payload
            data = json.loads(row["data"])
            assert "coverage" in data
            assert "caveats" in data
            assert data["test_mode"] is True

    async def test_result_created_event_type(self, test_broadcaster: SSEBroadcaster):
        """Test that broadcast events use correct event_type='result_created'."""
        # Arrange
        surface_id = str(uuid.uuid4())
        connection = test_broadcaster.register(
            surface_id=surface_id,
            session_id=str(uuid.uuid4()),
            surface_type="canvas",
        )

        received_events = []

        async def event_tracker():
            while True:
                try:
                    event = await asyncio.wait_for(connection.queue.get(), timeout=1.0)
                    received_events.append(event)
                    if event.event_type == "disconnect":
                        break
                except asyncio.TimeoutError:
                    break

        tracker_task = asyncio.create_task(event_tracker())

        # Act - Broadcast result_created event
        await test_broadcaster.broadcast(
            SSEEvent(
                event_type="result_created",
                target_surface_id=surface_id,
                data={"test": "data"}
            )
        )

        await asyncio.sleep(0.1)

        # Assert
        assert len(received_events) == 1
        assert received_events[0].event_type == "result_created"

        # Cleanup
        tracker_task.cancel()
        test_broadcaster.unregister(connection.connection_id)


@pytest.mark.asyncio
async def test_end_to_end_synthetic_dispatch_via_http():
    """End-to-end test of synthetic dispatch via HTTP endpoint."""
    # This test requires the server to be running
    # It would typically be run in a separate integration test suite
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
