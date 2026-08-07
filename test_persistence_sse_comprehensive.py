#!/usr/bin/env .venv/bin/python
"""
Comprehensive tests for session store persistence and SSE broadcasting.

Tests verify:
1. Results are correctly stored in session.db
2. SSE broadcaster sends result_created events
3. Topic records are created/updated correctly
4. Data relationships and constraints are maintained
5. SSE event targeting and filtering work correctly
"""

import asyncio
import json
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from src.session.store import SessionStore
from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEConnection,
    SSEEvent,
    EventType,
    get_broadcaster,
    broadcast_result,
)


# ============================================================================
# Session Store Persistence Tests
# ============================================================================

@pytest.mark.asyncio
async def test_session_store_initialization():
    """Test that session store initializes correctly with schema."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Verify database file exists
        assert db_path.exists(), "Database file should be created"

        # Verify we can query the database
        import aiosqlite
        async with aiosqlite.connect(store.db_path) as db:
            # Check that tables exist
            tables = await db.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            table_names = [t[0] for t in tables]

            required_tables = [
                'sessions', 'surfaces', 'utterances', 'intents', 'results',
                'topics', 'intent_topics', 'dispatch_timings'
            ]
            for table in required_tables:
                assert table in table_names, f"Table {table} should exist"

        await store.close()


@pytest.mark.asyncio
async def test_create_and_get_session():
    """Test creating and retrieving a session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create session
        session_id = await store.create_session()
        assert session_id is not None, "Session ID should be returned"

        # Retrieve session
        session = await store.get_session(session_id)
        assert session is not None, "Session should be retrievable"
        assert session['id'] == session_id, "Session ID should match"

        await store.close()


@pytest.mark.asyncio
async def test_create_utterance_and_intent():
    """Test creating utterances and intents with proper relationships."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create session
        session_id = await store.create_session()

        # Create utterance
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test utterance"
        )
        assert utterance_id is not None, "Utterance ID should be returned"

        # Retrieve utterance
        utterance = await store.get_utterance(utterance_id)
        assert utterance is not None, "Utterance should be retrievable"
        assert utterance['raw_text'] == "test utterance", "Raw text should match"
        assert utterance['session_id'] == session_id, "Session ID should match"

        # Create intent
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test-project",
            intent_type="status"
        )
        assert intent_id is not None, "Intent ID should be returned"

        # Retrieve intent
        intent = await store.get_intent(intent_id)
        assert intent is not None, "Intent should be retrievable"
        assert intent['utterance_id'] == utterance_id, "Utterance ID should match"
        assert intent['intent_type'] == "status", "Intent type should match"

        await store.close()


@pytest.mark.asyncio
async def test_create_and_find_topic():
    """Test creating topics and find_or_create_topic functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create session
        session_id = await store.create_session()

        # Test find_or_create_topic - should create new topic
        topic_id, created = await store.find_or_create_topic(
            label="test-topic",
            session_id=session_id,
            topic_type="project",  # Must be one of: project, research, personal, exception, compound
            project_slugs=["test-project"],
            scope="session"
        )
        assert topic_id is not None, "Topic ID should be returned"
        assert created is True, "Topic should be marked as created"

        # Retrieve topic
        topic = await store.get_topic(topic_id)
        assert topic is not None, "Topic should be retrievable"
        assert topic['label'] == "test-topic", "Label should match"
        assert topic['type'] == "project", "Type should match"
        assert topic['session_id'] == session_id, "Session ID should match"

        # Test find_or_create_topic - should find existing topic
        topic_id2, created2 = await store.find_or_create_topic(
            label="test-topic",
            session_id=session_id,
            topic_type="project",  # Must be one of: project, research, personal, exception, compound
            scope="session"
        )
        assert topic_id2 == topic_id, "Should return existing topic ID"
        assert created2 is False, "Should not mark as created"

        await store.close()


@pytest.mark.asyncio
async def test_create_result_with_persistence():
    """Test creating a result and verifying it's persisted correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create session and topic
        session_id = await store.create_session()
        topic_id, _ = await store.find_or_create_topic(
            label="test-topic",
            session_id=session_id,
            topic_type="project",
            project_slugs=["test-project"],
            scope="session"
        )

        # Create intent
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test utterance"
        )
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test-project",
            intent_type="status"
        )

        # Create result
        test_data = {"status": "healthy", "replicas": 3}
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Test result",
            data=test_data,
            urgency="normal",
            result_type="status:test-project"
        )
        assert result_id is not None, "Result ID should be returned"

        # Retrieve result
        result = await store.get_result(result_id)
        assert result is not None, "Result should be retrievable"
        assert result['id'] == result_id, "Result ID should match"
        assert result['summary'] == "Test result", "Summary should match"
        assert result['urgency'] == "normal", "Urgency should match"
        assert result['result_type'] == "status:test-project", "Result type should match"

        # Verify data is JSON-serialized correctly
        result_data = json.loads(result['data'])
        assert result_data == test_data, "Result data should match"

        await store.close()


@pytest.mark.asyncio
async def test_update_intent_status():
    """Test updating intent status."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create session, utterance, and intent
        session_id = await store.create_session()
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test"
        )
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test-project",
            intent_type="status"
        )

        # Verify initial status
        intent = await store.get_intent(intent_id)
        assert intent['status'] == 'pending', "Initial status should be pending"

        # Update status to dispatched
        await store.update_intent_status(intent_id, 'dispatched')
        intent = await store.get_intent(intent_id)
        assert intent['status'] == 'dispatched', "Status should be dispatched"

        # Update status to resolved (should auto-set resolved_at)
        await store.update_intent_status(intent_id, 'resolved')
        intent = await store.get_intent(intent_id)
        assert intent['status'] == 'resolved', "Status should be resolved"
        assert intent['resolved_at'] is not None, "resolved_at should be set"

        await store.close()


@pytest.mark.asyncio
async def test_link_intent_to_topic():
    """Test linking intents to topics (many-to-many)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create session, topics, and intent
        session_id = await store.create_session()
        topic_id1, _ = await store.find_or_create_topic(
            label="topic1",
            session_id=session_id,
            topic_type="project",  # Must be one of: project, research, personal, exception, compound
            scope="session"
        )
        topic_id2, _ = await store.find_or_create_topic(
            label="topic2",
            session_id=session_id,
            topic_type="research",  # Must be one of: project, research, personal, exception, compound
            scope="session"
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test"
        )
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            intent_type="status",
            topic_id=topic_id1
        )

        # Link intent to second topic
        await store.link_intent_to_topic(intent_id, topic_id2)

        # Verify intent is linked to both topics
        import aiosqlite
        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute(
                "SELECT topic_id FROM intent_topics WHERE intent_id = ?",
                (intent_id,)
            )
            linked_topics = await cursor.fetchall()

        topic_ids = [t[0] for t in linked_topics]
        assert topic_id1 in topic_ids, "Intent should be linked to topic1"
        assert topic_id2 in topic_ids, "Intent should be linked to topic2"

        await store.close()


@pytest.mark.asyncio
async def test_get_active_topics():
    """Test retrieving active topics for a session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create session and topics
        session_id = await store.create_session()

        topic_id1, _ = await store.find_or_create_topic(
            label="topic1",
            session_id=session_id,
            topic_type="project",  # Must be one of: project, research, personal, exception, compound
            scope="session"
        )
        topic_id2, _ = await store.find_or_create_topic(
            label="topic2",
            session_id=session_id,
            topic_type="research",  # Must be one of: project, research, personal, exception, compound
            scope="session"
        )

        # Get active topics
        topics = await store.get_active_topics(session_id)
        assert len(topics) >= 2, "Should have at least 2 topics"

        topic_labels = {t['label'] for t in topics}
        assert 'topic1' in topic_labels, "topic1 should be in active topics"
        assert 'topic2' in topic_labels, "topic2 should be in active topics"

        await store.close()


@pytest.mark.asyncio
async def test_delete_session_cascade():
    """Test that deleting a session properly removes all related data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create full hierarchy
        session_id = await store.create_session()
        surface_id = await store.register_surface(session_id, "canvas")

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test"
        )
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test-project",
            intent_type="status"
        )
        topic_id, _ = await store.find_or_create_topic(
            label="test-topic",
            session_id=session_id,
            topic_type="project",  # Must be one of: project, research, personal, exception, compound
            scope="session"
        )
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="test",
            data={}
        )

        # Verify all records exist
        session = await store.get_session(session_id)
        assert session is not None, "Session should exist"

        result = await store.get_result(result_id)
        assert result is not None, "Result should exist"

        # Delete session
        deletion_result = await store.delete_session(session_id)
        assert deletion_result['session_removed'] == 1, "Session should be removed"
        assert deletion_result['topics_removed'] >= 1, "Topics should be removed"

        # Verify cascade deletion
        session = await store.get_session(session_id)
        assert session is None, "Session should be deleted"

        result = await store.get_result(result_id)
        assert result is None, "Result should be deleted"

        await store.close()


# ============================================================================
# SSE Broadcaster Tests
# ============================================================================

@pytest.mark.asyncio
async def test_broadcaster_initialization():
    """Test SSE broadcaster initialization and lifecycle."""
    broadcaster = SSEBroadcaster()
    assert broadcaster is not None, "Broadcaster should be created"
    assert len(broadcaster.connections) == 0, "Should have no connections initially"

    await broadcaster.start()
    assert broadcaster._running is True, "Broadcaster should be running"

    await broadcaster.stop()
    assert broadcaster._running is False, "Broadcaster should be stopped"


@pytest.mark.asyncio
async def test_register_and_unregister_connection():
    """Test registering and unregistering SSE connections."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    # Register connection
    connection = broadcaster.register(
        surface_id="test-surface",
        session_id="test-session",
        surface_type="canvas"
    )

    assert connection is not None, "Connection should be created"
    assert connection.surface_id == "test-surface", "Surface ID should match"
    assert connection.session_id == "test-session", "Session ID should match"
    assert connection.surface_type == "canvas", "Surface type should match"
    assert connection.connection_id in broadcaster.connections, "Connection should be registered"

    # Unregister connection
    broadcaster.unregister(connection.connection_id)
    assert connection.connection_id not in broadcaster.connections, "Connection should be unregistered"

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_broadcast_event_to_all_connections():
    """Test broadcasting an event to all connections."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    # Register multiple connections
    conn1 = broadcaster.register("surface1", "session1", "canvas")
    conn2 = broadcaster.register("surface2", "session1", "canvas")
    conn3 = broadcaster.register("surface3", "session2", "telegram")

    # Broadcast event
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={"result_id": "test-result", "summary": "test"}
    )

    sent_count = await broadcaster.broadcast(event)
    assert sent_count == 3, "Event should be sent to all 3 connections"

    # Verify all connections received the event
    for conn in [conn1, conn2, conn3]:
        assert not conn.queue.empty(), f"Connection {conn.connection_id} should have received event"
        received_event = await conn.queue.get()
        assert received_event.event_type == EventType.RESULT_CREATED, "Event type should match"
        assert received_event.data['result_id'] == "test-result", "Result ID should match"

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_broadcast_with_session_filtering():
    """Test broadcasting with session_id filtering."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    # Register connections for different sessions
    conn1 = broadcaster.register("surface1", "session1", "canvas")
    conn2 = broadcaster.register("surface2", "session1", "canvas")
    conn3 = broadcaster.register("surface3", "session2", "canvas")

    # Broadcast to specific session
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={"result_id": "test-result"},
        target_session_id="session1"
    )

    sent_count = await broadcaster.broadcast(event)
    assert sent_count == 2, "Event should be sent to 2 connections in session1"

    # Verify session1 connections received it
    assert not conn1.queue.empty(), "conn1 should receive event"
    assert not conn2.queue.empty(), "conn2 should receive event"

    # Verify session2 connection did not receive it
    assert conn3.queue.empty(), "conn3 should NOT receive event"

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_broadcast_with_surface_filtering():
    """Test broadcasting with surface_id filtering."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    # Register connections
    conn1 = broadcaster.register("surface1", "session1", "canvas")
    conn2 = broadcaster.register("surface2", "session1", "canvas")
    conn3 = broadcaster.register("surface3", "session1", "telegram")

    # Broadcast to specific surface
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={"result_id": "test-result"},
        target_session_id="session1",
        target_surface_id="surface2"
    )

    sent_count = await broadcaster.broadcast(event)
    assert sent_count == 1, "Event should be sent to only 1 connection"

    # Verify only surface2 received it
    assert conn1.queue.empty(), "conn1 should NOT receive event"
    assert not conn2.queue.empty(), "conn2 should receive event"
    assert conn3.queue.empty(), "conn3 should NOT receive event"

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_broadcast_with_surface_exclusion():
    """Test broadcasting with surface_id exclusion."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    # Register connections
    conn1 = broadcaster.register("surface1", "session1", "canvas")
    conn2 = broadcaster.register("surface2", "session1", "canvas")

    # Broadcast excluding surface2
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={"result_id": "test-result"},
        target_session_id="session1",
        exclude_surface_id="surface2"
    )

    sent_count = await broadcaster.broadcast(event)
    assert sent_count == 1, "Event should be sent to only 1 connection"

    # Verify only surface1 received it
    assert not conn1.queue.empty(), "conn1 should receive event"
    assert conn2.queue.empty(), "conn2 should NOT receive event"

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_heartbeat_updates_connection():
    """Test that heartbeat updates connection timestamp."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    connection = broadcaster.register("surface1", "session1", "canvas")
    old_heartbeat = connection.last_heartbeat

    # Wait a bit to ensure timestamp would change
    await asyncio.sleep(0.01)

    # Update heartbeat
    updated = broadcaster.heartbeat(connection.connection_id)
    assert updated is True, "Heartbeat should succeed"

    # Verify timestamp updated
    new_heartbeat = broadcaster.connections[connection.connection_id].last_heartbeat
    assert new_heartbeat > old_heartbeat, "Heartbeat timestamp should be updated"

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_drop_session():
    """Test dropping all SSE streams for a session."""
    from src.sse.broadcaster import _DROP

    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    # Register connections for two sessions
    conn1 = broadcaster.register("surface1", "session1", "canvas")
    conn2 = broadcaster.register("surface2", "session1", "canvas")
    conn3 = broadcaster.register("surface3", "session2", "canvas")

    # Drop session1
    dropped_count = broadcaster.drop_session("session1")
    assert dropped_count == 2, "Should drop 2 connections for session1"

    # Verify session1 connections received the drop sentinel
    # drop_session doesn't remove connections from dict, it signals them to drop
    assert not conn1.queue.empty(), "conn1 queue should have drop signal"
    assert not conn2.queue.empty(), "conn2 queue should have drop signal"

    # Verify the sentinel is correct
    drop1 = await conn1.queue.get()
    drop2 = await conn2.queue.get()
    assert drop1 is _DROP, "conn1 should have _DROP sentinel"
    assert drop2 is _DROP, "conn2 should have _DROP sentinel"

    # Verify session2 connection did not receive drop signal
    assert conn3.queue.empty(), "conn3 queue should be empty (no drop signal)"

    await broadcaster.stop()


# ============================================================================
# Integration Tests - Persistence + SSE
# ============================================================================

@pytest.mark.asyncio
async def test_full_flow_persistence_to_sse():
    """Test full flow from persistence to SSE broadcast."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        broadcaster = SSEBroadcaster()
        await broadcaster.start()

        # Create session and topic
        session_id = await store.create_session()
        topic_id, _ = await store.find_or_create_topic(
            label="test-topic",
            session_id=session_id,
            topic_type="project",
            project_slugs=["test-project"],
            scope="session"
        )

        # Register SSE connection
        surface_id = str(uuid.uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        # Create utterance, intent, and result
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test utterance"
        )
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            intent_type="status",
            topic_id=topic_id
        )

        result_data = {"status": "healthy", "replicas": 3}
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Test result",
            data=result_data,
            urgency="normal",
            result_type="status:test-project"
        )

        # Broadcast result
        result_event_data = {
            "result_id": result_id,
            "summary": "Test result",
            "urgency": "normal"
        }

        sent_count = await broadcast_result(
            result=result_event_data,
            session_id=session_id,
            target_surface_id=surface_id
        )

        assert sent_count == 1, "Event should be sent to 1 connection"

        # Verify event was received
        assert not connection.queue.empty(), "Event should be in queue"
        event = await connection.queue.get()

        assert event.event_type == EventType.RESULT_CREATED, "Event type should be result_created"
        assert event.data['result_id'] == result_id, "Result ID should match"
        assert event.target_session_id == session_id, "Session ID should match"
        assert event.target_surface_id == surface_id, "Surface ID should match"

        # Verify result is persisted in database
        result = await store.get_result(result_id)
        assert result is not None, "Result should be persisted"
        assert result['id'] == result_id, "Result ID should match"

        await broadcaster.stop()
        await store.close()


@pytest.mark.asyncio
async def test_topic_updated_broadcast():
    """Test broadcasting topic_updated events."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    # Register connections
    conn1 = broadcaster.register("surface1", "session1", "canvas")
    conn2 = broadcaster.register("surface2", "session1", "telegram")

    # Create and broadcast topic update
    event = SSEEvent(
        event_type=EventType.TOPIC_UPDATED,
        data={
            "topic_id": "test-topic",
            "label": "Updated Topic",
            "result_count": 5
        },
        target_session_id="session1"
    )

    sent_count = await broadcaster.broadcast(event)
    assert sent_count == 2, "Event should be sent to both connections"

    # Verify both connections received the event
    for conn in [conn1, conn2]:
        assert not conn.queue.empty(), f"{conn.surface_id} should receive event"
        received = await conn.queue.get()
        assert received.event_type == EventType.TOPIC_UPDATED
        assert received.data['topic_id'] == "test-topic"

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_global_broadcaster_instance():
    """Test that get_broadcaster() returns the same global instance."""
    broadcaster1 = get_broadcaster()
    broadcaster2 = get_broadcaster()

    assert broadcaster1 is broadcaster2, "Should return the same instance"

    # Test that the instance is functional
    await broadcaster1.start()
    conn = broadcaster1.register("test", "test", "canvas")
    assert conn.connection_id in broadcaster1.connections

    await broadcaster1.stop()


@pytest.mark.asyncio
async def test_event_with_rendered_html():
    """Test that events can carry rendered HTML for canvas injection."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    connection = broadcaster.register("surface1", "session1", "canvas")

    # Create event with rendered HTML
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={"result_id": "test-result"},
        rendered_html="<div class=\"card\">Test Card</div>"
    )

    await broadcaster.broadcast(event)

    # Receive event
    received = await connection.queue.get()
    assert received.rendered_html is not None, "Event should have rendered HTML"
    assert "<div class=\"card\">" in received.rendered_html, "HTML content should match"

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_multiple_results_per_topic():
    """Test that multiple results can be stored for the same topic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create session and topic
        session_id = await store.create_session()
        topic_id, _ = await store.find_or_create_topic(
            label="test-topic",
            session_id=session_id,
            topic_type="project",
            project_slugs=["test-project"],
            scope="session"
        )

        # Create multiple results for the same topic
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test"
        )
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            intent_type="status",
            topic_id=topic_id
        )

        result_ids = []
        for i in range(3):
            result_id = await store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Result {i}",
                data={"iteration": i},
                result_type="status:test-project"
            )
            result_ids.append(result_id)

        # Verify all results exist
        results = await store.get_results_for_intent(intent_id)
        assert len(results) == 3, "Should have 3 results"

        # Verify results are ordered by created_at DESC
        for i, result in enumerate(results):
            assert result['summary'] == f"Result {2-i}", "Results should be in DESC order"

        await store.close()


# ============================================================================
# Test Runner
# ============================================================================

def main():
    """Run all tests and display results."""
    print("=" * 70)
    print("COMPREHENSIVE PERSISTENCE AND SSE BROADCAST TESTS")
    print("=" * 70)

    # Run pytest programmatically
    import sys
    exit_code = pytest.main([__file__, "-v", "--tb=short"])

    print("\n" + "=" * 70)
    if exit_code == 0:
        print("✓ ALL TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("=" * 70)

    return exit_code


if __name__ == "__main__":
    import sys
    sys.exit(main())
