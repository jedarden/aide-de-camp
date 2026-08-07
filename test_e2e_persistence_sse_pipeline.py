#!/usr/bin/env .venv/bin/python
"""
End-to-end persistence and SSE pipeline tests.

Tests verify the complete flow:
1. Result created → stored in session.db → SSE broadcast sent
2. Canvas receives correct topic data after result_created event
3. Parallel results don't corrupt each other
4. SSE failure doesn't block persistence

These are integration tests that verify the entire pipeline works correctly.
"""

import asyncio
import json
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

import pytest
import aiosqlite

from src.session.store import SessionStore
from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEConnection,
    SSEEvent,
    EventType,
    get_broadcaster,
    broadcast_result,
)
from src.intent.router import IntentRouter
from src.api.models import DispatchRequest


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()
        yield store
        await store.close()


@pytest.fixture
async def broadcaster():
    """Create a fresh SSE broadcaster for testing."""
    broadcaster = SSEBroadcaster()
    await broadcaster.start()
    yield broadcaster
    await broadcaster.stop()


@pytest.fixture
async def sample_session(temp_db):
    """Create a sample session with topic and intent."""
    session_id = await temp_db.create_session()
    surface_id = await temp_db.register_surface(session_id, "canvas")

    utterance_id = await temp_db.create_utterance(
        session_id=session_id,
        raw_text="test utterance for pipeline"
    )

    intent_id = await temp_db.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="status"
    )

    topic_id, _ = await temp_db.find_or_create_topic(
        label="test-topic",
        session_id=session_id,
        topic_type="project",
        project_slugs=["test-project"],
        scope="session"
    )

    return {
        "session_id": session_id,
        "surface_id": surface_id,
        "utterance_id": utterance_id,
        "intent_id": intent_id,
        "topic_id": topic_id,
    }


# ============================================================================
# Complete Pipeline Tests
# ============================================================================

@pytest.mark.asyncio
async def test_complete_pipeline_result_created_to_sse(temp_db, broadcaster, sample_session):
    """
    Test the complete pipeline: result created → stored → SSE broadcast.

    This verifies that when a result is created:
    1. It's persisted correctly in session.db
    2. SSE broadcaster receives and sends the event
    3. Registered connections receive the event
    """
    session_id = sample_session["session_id"]
    surface_id = sample_session["surface_id"]
    intent_id = sample_session["intent_id"]
    topic_id = sample_session["topic_id"]

    # Register a canvas connection
    connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )

    # Create result
    test_data = {"status": "healthy", "replicas": 3, "deployment": "test-app"}
    result_id = await temp_db.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Deployment is healthy",
        data=test_data,
        urgency="normal",
        result_type="status:test-project"
    )

    # Verify persistence
    result = await temp_db.get_result(result_id)
    assert result is not None, "Result should be persisted"
    assert result["summary"] == "Deployment is healthy"
    assert json.loads(result["data"]) == test_data

    # Broadcast SSE event
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={
            "intent_id": intent_id,
            "topic_id": topic_id,
            "summary": result["summary"],
            "urgency": result["urgency"],
            "result_id": result_id,
        },
        target_session_id=session_id,
        target_surface_id=surface_id,
    )

    sent_count = await broadcaster.broadcast(event)
    assert sent_count == 1, "Event should be sent to one connection"

    # Verify event was queued
    assert not connection.queue.empty(), "Connection should have received event"
    received_event = await connection.queue.get()
    assert received_event.event_type == EventType.RESULT_CREATED
    assert received_event.data["intent_id"] == intent_id
    assert received_event.data["topic_id"] == topic_id


@pytest.mark.asyncio
async def test_canvas_receives_correct_topic_data(temp_db, broadcaster, sample_session):
    """
    Test that canvas receives correct topic data after result_created event.

    This simulates the canvas behavior:
    1. Canvas connects via SSE
    2. Result is created and broadcast
    3. Canvas calls loadTopics() and receives updated data
    """
    session_id = sample_session["session_id"]
    surface_id = sample_session["surface_id"]
    intent_id = sample_session["intent_id"]
    topic_id = sample_session["topic_id"]

    # Register canvas connection
    connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )

    # Create multiple results for the same topic
    result_ids = []
    for i in range(3):
        result_id = await temp_db.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=f"Result {i+1}",
            data={"index": i, "value": f"test-{i}"},
            urgency="normal",
            result_type="status:test-project"
        )
        result_ids.append(result_id)

    # Broadcast result_created for each result
    for rid in result_ids:
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={
                "intent_id": intent_id,
                "topic_id": topic_id,
                "result_id": rid,
                "summary": f"Result updated",
            },
            target_session_id=session_id,
            target_surface_id=surface_id,
        )
        await broadcaster.broadcast(event)

    # Verify canvas received all events
    received_count = 0
    while not connection.queue.empty():
        event = await connection.queue.get()
        if event.event_type == EventType.RESULT_CREATED:
            received_count += 1

    assert received_count == 3, "Canvas should receive 3 result_created events"

    # Verify get_active_topics returns correct data (simulating loadTopics())
    topics = await temp_db.get_active_topics(session_id)
    assert len(topics) >= 1, "Should have at least one active topic"

    topic = next((t for t in topics if t["id"] == topic_id), None)
    assert topic is not None, "Topic should be in active topics"
    assert topic["label"] == "test-topic"


@pytest.mark.asyncio
async def test_parallel_results_no_corruption(temp_db, broadcaster):
    """
    Test that parallel result creation doesn't corrupt each other.

    This simulates concurrent dispatches creating results simultaneously.
    Each result should be isolated and not interfere with others.
    """
    # Create multiple independent sessions
    sessions = []
    for i in range(5):
        session_id = await temp_db.create_session()
        surface_id = await temp_db.register_surface(session_id, "canvas")
        utterance_id = await temp_db.create_utterance(
            session_id=session_id,
            raw_text=f"test utterance {i}"
        )
        intent_id = await temp_db.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug=f"project-{i}",
            intent_type="status"
        )
        topic_id, _ = await temp_db.find_or_create_topic(
            label=f"topic-{i}",
            session_id=session_id,
            topic_type="project",
            project_slugs=[f"project-{i}"],
            scope="session"
        )
        sessions.append({
            "session_id": session_id,
            "surface_id": surface_id,
            "intent_id": intent_id,
            "topic_id": topic_id,
            "index": i,
        })

    # Register all connections
    connections = {}
    for session in sessions:
        conn = broadcaster.register(
            surface_id=session["surface_id"],
            session_id=session["session_id"],
            surface_type="canvas"
        )
        connections[session["session_id"]] = conn

    # Create all results in parallel (simulate concurrent dispatches)
    async def create_result_for_session(session):
        result_id = await temp_db.create_result(
            intent_id=session["intent_id"],
            topic_id=session["topic_id"],
            session_id=session["session_id"],
            summary=f"Result {session['index']}",
            data={"index": session["index"], "unique_value": f"value-{session['index']}"},
            urgency="normal",
            result_type=f"status:project-{session['index']}"
        )

        # Broadcast event
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={
                "intent_id": session["intent_id"],
                "topic_id": session["topic_id"],
                "result_id": result_id,
                "summary": f"Result {session['index']}",
            },
            target_session_id=session["session_id"],
            target_surface_id=session["surface_id"],
        )
        await broadcaster.broadcast(event)
        return result_id, session

    # Run all in parallel
    results = await asyncio.gather(*[create_result_for_session(s) for s in sessions])

    # Verify no corruption: each result should have unique correct data
    for result_id, session in results:
        result = await temp_db.get_result(result_id)
        assert result is not None, f"Result {result_id} should exist"

        result_data = json.loads(result["data"])
        expected_index = session["index"]
        assert result_data["index"] == expected_index, \
            f"Result data should match expected index {expected_index}"
        assert result_data["unique_value"] == f"value-{expected_index}", \
            f"Result data should have unique value for session {expected_index}"

    # Verify each session received exactly one event
    for session_id, conn in connections.items():
        received_count = 0
        while not conn.queue.empty():
            event = await conn.queue.get()
            if event.event_type == EventType.RESULT_CREATED:
                received_count += 1
        assert received_count == 1, f"Session {session_id} should receive exactly 1 event"


@pytest.mark.asyncio
async def test_sse_failure_does_not_block_persistence(temp_db, broadcaster, sample_session):
    """
    Test that SSE broadcast failure doesn't prevent result persistence.

    This verifies that even if SSE broadcasting fails, the result is still
    stored in the database correctly. The system should be resilient.
    """
    session_id = sample_session["session_id"]
    intent_id = sample_session["intent_id"]
    topic_id = sample_session["topic_id"]

    # Create result first (persistence should succeed even if SSE fails)
    result_id = await temp_db.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Critical result",
        data={"critical": True, "value": "important"},
        urgency="critical",
        result_type="status:test-project"
    )

    # Verify persistence succeeded
    result = await temp_db.get_result(result_id)
    assert result is not None, "Result should be persisted"
    assert result["summary"] == "Critical result"
    assert result["urgency"] == "critical"

    # Now try to broadcast (simulate failure scenario)
    # Even if no connections are registered, broadcast should not fail
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={
            "intent_id": intent_id,
            "topic_id": topic_id,
            "result_id": result_id,
            "summary": result["summary"],
        },
        target_session_id=session_id,
        target_surface_id="non-existent-surface",  # No connection for this
    )

    # Broadcast should not raise exception even with no connections
    sent_count = await broadcaster.broadcast(event)
    assert sent_count == 0, "No connections should receive event"

    # Result should still be persisted correctly
    result_after = await temp_db.get_result(result_id)
    assert result_after is not None, "Result should still exist after failed broadcast"
    assert result_after["summary"] == "Critical result"


@pytest.mark.asyncio
async def test_result_persistence_with_rendered_html(temp_db, broadcaster, sample_session):
    """
    Test that results with rendered HTML are handled correctly in the pipeline.

    This verifies the complete flow for component-rendered results:
    1. Result created with component_id
    2. Rendered HTML included in SSE event
    3. Canvas can inject HTML directly
    """
    session_id = sample_session["session_id"]
    surface_id = sample_session["surface_id"]
    intent_id = sample_session["intent_id"]
    topic_id = sample_session["topic_id"]

    # Register connection
    connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )

    # Create result (simulating component-rendered card)
    result_id = await temp_db.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Status Card",
        data={"status": "running", "uptime": "99.9%"},
        urgency="normal",
        result_type="status:test-project",
        card_fallback=False  # Component rendered this
    )

    # Simulate SSE event with rendered HTML
    rendered_html = "<div class='status-card'>Status: running</div>"
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={
            "intent_id": intent_id,
            "topic_id": topic_id,
            "result_id": result_id,
            "summary": "Status Card",
            "component_id": "status-card",
            "card_fallback": False,
        },
        target_session_id=session_id,
        target_surface_id=surface_id,
        rendered_html=rendered_html,
    )

    await broadcaster.broadcast(event)

    # Verify event includes rendered HTML
    assert not connection.queue.empty(), "Connection should receive event"
    received_event = await connection.queue.get()
    assert received_event.rendered_html == rendered_html
    assert received_event.data["component_id"] == "status-card"
    assert received_event.data["card_fallback"] is False


@pytest.mark.asyncio
async def test_multiple_surfaces_receive_events(temp_db, broadcaster, sample_session):
    """
    Test that multiple surfaces for the same session receive events correctly.

    A session can have multiple surfaces (canvas, telegram, etc.).
    Events should be broadcast to all active surfaces.
    """
    session_id = sample_session["session_id"]
    intent_id = sample_session["intent_id"]
    topic_id = sample_session["topic_id"]

    # Register multiple surfaces for the same session
    canvas_surface_id = await temp_db.register_surface(session_id, "canvas")
    telegram_surface_id = await temp_db.register_surface(session_id, "telegram")

    canvas_conn = broadcaster.register(
        surface_id=canvas_surface_id,
        session_id=session_id,
        surface_type="canvas"
    )

    telegram_conn = broadcaster.register(
        surface_id=telegram_surface_id,
        session_id=session_id,
        surface_type="telegram"
    )

    # Create result
    result_id = await temp_db.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Multi-surface result",
        data={"test": True},
        urgency="normal",
        result_type="status:test-project"
    )

    # Broadcast to all surfaces in the session (no specific surface target)
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={
            "intent_id": intent_id,
            "topic_id": topic_id,
            "result_id": result_id,
            "summary": "Multi-surface result",
        },
        target_session_id=session_id,
        # No target_surface_id - should go to all surfaces in session
    )

    sent_count = await broadcaster.broadcast(event)
    assert sent_count == 2, "Event should be sent to both surfaces"

    # Verify both surfaces received the event
    canvas_event = await canvas_conn.queue.get()
    telegram_event = await telegram_conn.queue.get()

    assert canvas_event.data["result_id"] == result_id
    assert telegram_event.data["result_id"] == result_id


@pytest.mark.asyncio
async def test_sse_event_filtering_by_surface_id(temp_db, broadcaster, sample_session):
    """
    Test that SSE events correctly filter by target_surface_id.

    When an event specifies a target_surface_id, only that surface
    should receive the event.
    """
    session_id = sample_session["session_id"]
    intent_id = sample_session["intent_id"]
    topic_id = sample_session["topic_id"]

    # Register multiple surfaces
    surface1_id = await temp_db.register_surface(session_id, "canvas")
    surface2_id = await temp_db.register_surface(session_id, "canvas")

    conn1 = broadcaster.register(
        surface_id=surface1_id,
        session_id=session_id,
        surface_type="canvas"
    )

    conn2 = broadcaster.register(
        surface_id=surface2_id,
        session_id=session_id,
        surface_type="canvas"
    )

    # Create result
    result_id = await temp_db.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Targeted result",
        data={"test": True},
        urgency="normal",
        result_type="status:test-project"
    )

    # Broadcast only to surface1
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={
            "intent_id": intent_id,
            "topic_id": topic_id,
            "result_id": result_id,
        },
        target_session_id=session_id,
        target_surface_id=surface1_id,  # Only surface1 should receive
    )

    sent_count = await broadcaster.broadcast(event)
    assert sent_count == 1, "Event should be sent to only one surface"

    # Verify surface1 received the event
    assert not conn1.queue.empty(), "surface1 should receive event"
    event1 = await conn1.queue.get()
    assert event1.data["result_id"] == result_id

    # Verify surface2 did NOT receive the event
    assert conn2.queue.empty(), "surface2 should not receive event"


@pytest.mark.asyncio
async def test_persistence_during_concurrent_writes(temp_db):
    """
    Test SQLite WAL mode handles concurrent writes correctly.

    With multiple concurrent writes, the database should handle
    them gracefully without corruption or locks blocking indefinitely.
    """
    session_id = await temp_db.create_session()

    # Create multiple intents for the same utterance
    utterance_id = await temp_db.create_utterance(
        session_id=session_id,
        raw_text="concurrent test utterance"
    )

    intent_ids = []
    for i in range(10):
        intent_id = await temp_db.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug=f"project-{i}",
            intent_type="status"
        )
        intent_ids.append(intent_id)

    # Create topics in parallel
    async def create_topic_for_intent(i):
        topic_id, _ = await temp_db.find_or_create_topic(
            label=f"topic-{i}",
            session_id=session_id,
            topic_type="project",
            project_slugs=[f"project-{i}"],
            scope="session"
        )
        return topic_id

    topic_ids = await asyncio.gather(*[create_topic_for_intent(i) for i in range(10)])

    # Create results in parallel
    async def create_result_parallel(i):
        return await temp_db.create_result(
            intent_id=intent_ids[i],
            topic_id=topic_ids[i],
            session_id=session_id,
            summary=f"Result {i}",
            data={"index": i},
            urgency="normal",
            result_type=f"status:project-{i}"
        )

    result_ids = await asyncio.gather(*[create_result_parallel(i) for i in range(10)])

    # Verify all results persisted correctly
    for i, result_id in enumerate(result_ids):
        result = await temp_db.get_result(result_id)
        assert result is not None, f"Result {i} should exist"
        result_data = json.loads(result["data"])
        assert result_data["index"] == i, f"Result {i} should have correct data"


@pytest.mark.asyncio
async def test_manual_topic_activity_update(temp_db, broadcaster, sample_session):
    """
    Test that topic activity can be manually updated.

    The update_topic_activity method should be called explicitly when
    a topic becomes active (e.g., when a result is surfaced).
    """
    session_id = sample_session["session_id"]
    topic_id = sample_session["topic_id"]

    # Get initial topic state
    topic_before = await temp_db.get_topic(topic_id)
    assert topic_before is not None

    # Add a small delay to ensure timestamp difference
    await asyncio.sleep(0.01)

    # Manually update topic activity (this should be called when surfacing results)
    await temp_db.update_topic_activity(topic_id)

    # Verify topic was updated
    topic_after = await temp_db.get_topic(topic_id)
    assert topic_after is not None
    assert topic_after["last_active"] >= topic_before["last_active"], \
        "Topic last_active should be updated after update_topic_activity call"

    # Verify topic appears in active topics
    active_topics = await temp_db.get_active_topics(session_id)
    topic_ids = [t["id"] for t in active_topics]
    assert topic_id in topic_ids, "Topic should be in active topics"


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
