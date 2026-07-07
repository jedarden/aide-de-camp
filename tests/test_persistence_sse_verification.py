#!/usr/bin/env python3
"""Test persistence and SSE broadcast verification.

This test suite verifies:
1. Topic creation in session store
2. Result persistence with correct data structure
3. SSE events are broadcast with correct event_type
4. Surface_id targeting works correctly
"""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

# Ensure the project root is in the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.session.store import SessionStore
from src.sse.broadcaster import SSEBroadcaster, SSEEvent, EventType


async def test_topic_creation_persistence():
    """Test topic creation and persistence in session store."""
    print("Testing: Topic creation in session store...")

    test_db_path = Path("/tmp/test_topic_persistence.db")
    if test_db_path.exists():
        test_db_path.unlink()

    store = SessionStore(test_db_path)
    await store.initialize()

    # Create a session
    session_id = await store.create_session()
    print(f"  ✅ Created session: {session_id}")

    # Test topic creation
    topic_id = await store.create_topic(
        label="Test Topic",
        topic_type="project",
        project_slugs=["test-project"],
        scope="session",
        session_id=session_id
    )
    print(f"  ✅ Created topic: {topic_id}")

    # Verify topic was persisted
    topics = await store.get_active_topics(session_id)
    assert len(topics) == 1, f"Expected 1 topic, got {len(topics)}"
    print(f"  ✅ Topic persisted: {len(topics)} topic(s)")

    # Verify topic structure
    topic = topics[0]
    assert topic["id"] == topic_id, "Topic ID mismatch"
    assert topic["label"] == "Test Topic", "Topic label mismatch"
    assert topic["type"] == "project", "Topic type mismatch"
    assert topic["scope"] == "session", "Topic scope mismatch"
    assert topic["result_count"] == 0, "Expected 0 results for new topic"
    print(f"  ✅ Topic structure verified: {topic['label']} ({topic['type']})")

    # Test find_or_create_topic
    found_topic_id, created = await store.find_or_create_topic(
        label="Test Topic",
        session_id=session_id,
        topic_type="project",
        project_slugs=["test-project"]
    )
    assert found_topic_id == topic_id, "Find should return existing topic"
    assert not created, "Should not create duplicate topic"
    print(f"  ✅ Found existing topic (no duplicate created)")

    # Test creating a new topic with different label
    new_topic_id, created = await store.find_or_create_topic(
        label="New Topic",
        session_id=session_id,
        topic_type="research"
    )
    assert created, "Should create new topic for different label"
    assert new_topic_id != topic_id, "New topic should have different ID"
    print(f"  ✅ Created new topic: {new_topic_id}")

    # Verify we now have 2 topics
    topics = await store.get_active_topics(session_id)
    assert len(topics) == 2, f"Expected 2 topics, got {len(topics)}"
    print(f"  ✅ Total topics: {len(topics)}")

    await store.close()
    test_db_path.unlink()

    print("✅ Topic creation persistence test PASSED")
    return True


async def test_result_persistence():
    """Test result persistence with correct data structure."""
    print("\nTesting: Result persistence with correct data structure...")

    test_db_path = Path("/tmp/test_result_persistence.db")
    if test_db_path.exists():
        test_db_path.unlink()

    store = SessionStore(test_db_path)
    await store.initialize()

    # Create session, topic, intent, and utterance
    session_id = await store.create_session()
    topic_id = await store.create_topic(
        label="Test Topic",
        topic_type="project",
        project_slugs=["test-project"],
        scope="session",
        session_id=session_id
    )
    utterance_id = await store.create_utterance(session_id, "test utterance")
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="lookup"
    )

    # Test result creation with basic data
    result_data = {
        "status": "success",
        "message": "Test completed successfully",
        "metrics": {"cpu": 50, "memory": 75}
    }

    result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result",
        data=result_data,
        urgency="normal"
    )
    print(f"  ✅ Created result: {result_id}")

    # Verify result was persisted correctly
    # Get latest result for topic
    result = await store.get_latest_result_for_topic(topic_id)
    assert result is not None, "Result not found in database"
    assert result["id"] == result_id, "Result ID mismatch"
    assert result["intent_id"] == intent_id, "Intent ID mismatch"
    assert result["topic_id"] == topic_id, "Topic ID mismatch"
    assert result["session_id"] == session_id, "Session ID mismatch"
    assert result["summary"] == "Test result", "Summary mismatch"
    assert result["urgency"] == "normal", "Urgency mismatch"
    assert result["surfaced_at"] is not None, "surfaced_at should be set"
    print(f"  ✅ Result persisted correctly")

    # Verify data field is valid JSON
    parsed_data = json.loads(result["data"])
    assert parsed_data == result_data, "Data field mismatch"
    print(f"  ✅ Result data field is valid JSON")

    # Test result with previous_result_id (diff scenario)
    # Add a small delay to ensure different timestamp
    await asyncio.sleep(0.1)

    result2_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Updated result",
        data={"status": "updated", "metrics": {"cpu": 60, "memory": 80}},
        urgency="normal",
        previous_result_id=result_id,
        diff_summary="Metrics updated",
        diff_data={"fields": [{"field_name": "cpu", "old_value": 50, "new_value": 60}]}
    )
    print(f"  ✅ Created result with diff: {result2_id}")

    # Verify diff result by querying for it directly
    import aiosqlite
    async with aiosqlite.connect(test_db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM results WHERE id = ?", (result2_id,)
        ) as cursor:
            result2_row = await cursor.fetchone()
            if result2_row:
                result2 = dict(result2_row)
                assert result2["previous_result_id"] == result_id, "Previous result ID mismatch"
                assert result2["diff_summary"] == "Metrics updated", "Diff summary mismatch"
                print(f"  ✅ Result with diff persisted correctly")
            else:
                print(f"  ❌ Result with diff not found in database")
                return False

    # Test get_unsurfed_results
    unsurfed = await store.get_unsurfed_results(session_id)
    assert len(unsurfed) == 0, "All results should be surfaced by default"
    print(f"  ✅ get_unsurfed_results works correctly")

    # Create a result without surfaced_at (simulating unsurfed result)
    # We need to manually insert to bypass the surfaced_at default
    import aiosqlite
    from datetime import datetime
    unsurfed_result_id = str(uuid4())
    now = int(datetime.now().timestamp())
    async with aiosqlite.connect(test_db_path) as db:
        await db.execute(
            """INSERT INTO results
               (id, intent_id, topic_id, session_id, summary, data, urgency, created_at, surfaced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (unsurfed_result_id, intent_id, topic_id, session_id, "Unsurfaced",
             json.dumps({"test": "data"}), "normal", now)
        )
        await db.commit()

    unsurfed = await store.get_unsurfed_results(session_id)
    assert len(unsurfed) == 1, f"Expected 1 unsurfed result, got {len(unsurfed)}"
    print(f"  ✅ Unsurfed result detected correctly")

    # Test mark_results_surfed_by_ids
    await store.mark_results_surfed_by_ids(session_id, [unsurfed_result_id])
    unsurfed = await store.get_unsurfed_results(session_id)
    assert len(unsurfed) == 0, "Result should now be surfaced"
    print(f"  ✅ Mark results as surfaced works correctly")

    await store.close()
    test_db_path.unlink()

    print("✅ Result persistence test PASSED")
    return True


async def test_sse_event_broadcast():
    """Test SSE events are broadcast with correct event_type."""
    print("\nTesting: SSE events broadcast with correct event_type...")

    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    # Register multiple connections
    conn1 = broadcaster.register(
        surface_id="canvas-1",
        session_id="session-1",
        surface_type="canvas"
    )

    conn2 = broadcaster.register(
        surface_id="canvas-2",
        session_id="session-1",
        surface_type="canvas"
    )

    conn3 = broadcaster.register(
        surface_id="audio-1",
        session_id="session-2",
        surface_type="audio"
    )

    print(f"  ✅ Registered 3 connections")

    # Test RESULT_CREATED event
    result_event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={
            "result_id": "result-1",
            "summary": "Test result",
            "topic_id": "topic-1"
        },
        target_session_id="session-1"
    )

    sent_count = await broadcaster.broadcast(result_event)
    assert sent_count == 2, f"Expected 2 recipients for session-1, got {sent_count}"
    print(f"  ✅ RESULT_CREATED event sent to {sent_count} connections")

    # Verify event is in queue
    event1 = await conn1.queue.get()
    assert event1.event_type == EventType.RESULT_CREATED, "Event type mismatch"
    assert event1.data["result_id"] == "result-1", "Result ID mismatch"
    print(f"  ✅ Event in queue has correct event_type: {event1.event_type}")

    # Test TOPIC_UPDATED event
    topic_event = SSEEvent(
        event_type=EventType.TOPIC_UPDATED,
        data={
            "topic_id": "topic-1",
            "label": "Updated Topic"
        },
        target_session_id="session-1"
    )

    sent_count = await broadcaster.broadcast(topic_event)
    assert sent_count == 2, f"Expected 2 recipients, got {sent_count}"
    print(f"  ✅ TOPIC_UPDATED event sent to {sent_count} connections")

    # Test INTENT_RESOLVED event
    intent_event = SSEEvent(
        event_type=EventType.INTENT_RESOLVED,
        data={
            "intent_id": "intent-1",
            "status": "resolved"
        },
        target_session_id="session-2"
    )

    sent_count = await broadcaster.broadcast(intent_event)
    assert sent_count == 1, f"Expected 1 recipient for session-2, got {sent_count}"
    print(f"  ✅ INTENT_RESOLVED event sent to {sent_count} connection")

    # Verify conn3 received the intent event
    event3 = await conn3.queue.get()
    assert event3.event_type == EventType.INTENT_RESOLVED, "Event type mismatch"
    print(f"  ✅ Correct session received intent event")

    # Test event format
    formatted = broadcaster._format_sse("test_event", {"message": "hello"})
    lines = formatted.strip().split('\n')
    assert "event: test_event" in formatted, "Missing event line"
    assert "data:" in formatted, "Missing data line"
    print(f"  ✅ SSE format is correct")

    await broadcaster.stop()
    print("✅ SSE event broadcast test PASSED")
    return True


async def test_surface_id_targeting():
    """Test surface_id targeting works correctly."""
    print("\nTesting: Surface_id targeting...")

    broadcaster = SSEBroadcaster()
    await broadcaster.start()

    # Register multiple surfaces for same session
    conn_canvas1 = broadcaster.register(
        surface_id="canvas-1",
        session_id="session-1",
        surface_type="canvas"
    )

    conn_canvas2 = broadcaster.register(
        surface_id="canvas-2",
        session_id="session-1",
        surface_type="canvas"
    )

    conn_telegram = broadcaster.register(
        surface_id="telegram-1",
        session_id="session-1",
        surface_type="telegram"
    )

    conn_other_session = broadcaster.register(
        surface_id="canvas-3",
        session_id="session-2",
        surface_type="canvas"
    )

    print(f"  ✅ Registered 4 connections across 2 sessions")

    # Test targeting specific surface_id
    target_event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={"message": "Targeted message"},
        target_session_id="session-1",
        target_surface_id="canvas-1"
    )

    sent_count = await broadcaster.broadcast(target_event)
    assert sent_count == 1, f"Expected 1 recipient for targeted surface, got {sent_count}"
    print(f"  ✅ Event sent to 1 specific surface (canvas-1)")

    # Verify the correct connection received it
    event = await conn_canvas1.queue.get()
    assert event.event_type == EventType.RESULT_CREATED, "Event type mismatch"
    assert event.data["message"] == "Targeted message", "Data mismatch"
    print(f"  ✅ Correct surface (canvas-1) received the event")

    # Verify canvas-2 did NOT receive it (queue should be empty for this event)
    # We check by trying to get with timeout
    try:
        await asyncio.wait_for(conn_canvas2.queue.get(), timeout=0.1)
        print(f"  ❌ canvas-2 should not have received targeted event")
        return False
    except asyncio.TimeoutError:
        print(f"  ✅ canvas-2 correctly excluded from targeted event")

    # Test exclude_surface_id
    exclude_event = SSEEvent(
        event_type=EventType.WORKLOAD_SUMMARY,
        data={"pending": 5},
        target_session_id="session-1",
        exclude_surface_id="telegram-1"
    )

    sent_count = await broadcaster.broadcast(exclude_event)
    assert sent_count == 2, f"Expected 2 recipients (excluding telegram), got {sent_count}"
    print(f"  ✅ Event sent to 2 surfaces (excluding telegram-1)")

    # Verify both canvas connections received it
    event_c1 = await conn_canvas1.queue.get()
    event_c2 = await conn_canvas2.queue.get()
    assert event_c1.event_type == EventType.WORKLOAD_SUMMARY, "canvas-1 event type mismatch"
    assert event_c2.event_type == EventType.WORKLOAD_SUMMARY, "canvas-2 event type mismatch"
    print(f"  ✅ Both canvas surfaces received excluded event")

    # Verify telegram did NOT receive it
    try:
        await asyncio.wait_for(conn_telegram.queue.get(), timeout=0.1)
        print(f"  ❌ telegram-1 should not have received excluded event")
        return False
    except asyncio.TimeoutError:
        print(f"  ✅ telegram-1 correctly excluded")

    # Test session targeting (all surfaces in session)
    session_event = SSEEvent(
        event_type=EventType.TOPIC_UPDATED,
        data={"topic_id": "topic-1"},
        target_session_id="session-1"
    )

    sent_count = await broadcaster.broadcast(session_event)
    assert sent_count == 3, f"Expected 3 recipients for session-1, got {sent_count}"
    print(f"  ✅ Event sent to all 3 surfaces in session-1")

    # Test cross-surface exclusion (send to all except origin)
    exclude_origin_event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={"message": "Broadcast from canvas-1"},
        target_session_id="session-1",
        exclude_surface_id="canvas-1"
    )

    sent_count = await broadcaster.broadcast(exclude_origin_event)
    assert sent_count == 2, f"Expected 2 recipients (excluding origin), got {sent_count}"
    print(f"  ✅ Event sent to 2 surfaces (excluding origin canvas-1)")

    await broadcaster.stop()
    print("✅ Surface_id targeting test PASSED")
    return True


async def test_end_to_end_dispatch_flow():
    """Test end-to-end dispatch flow with persistence and SSE."""
    print("\nTesting: End-to-end dispatch flow...")

    test_db_path = Path("/tmp/test_dispatch_flow.db")
    if test_db_path.exists():
        test_db_path.unlink()

    store = SessionStore(test_db_path)
    await store.initialize()

    # Use the global broadcaster (same instance used by broadcast_result)
    from src.sse.broadcaster import get_broadcaster
    broadcaster = get_broadcaster()
    await broadcaster.start()

    # Simulate dispatch flow
    session_id = await store.create_session()
    surface_id = await store.register_surface(session_id, "canvas")

    # Register SSE connection
    conn = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )
    print(f"  ✅ Setup: session={session_id}, surface={surface_id}")

    # Simulate utterance -> intent -> result flow
    utterance_id = await store.create_utterance(session_id, "check pods")
    print(f"  ✅ Created utterance: {utterance_id}")

    # Find or create topic
    topic_id, created = await store.find_or_create_topic(
        label="Kubernetes Status",
        session_id=session_id,
        topic_type="project",
        project_slugs=["k8s-status"]
    )
    print(f"  ✅ {'Created' if created else 'Found'} topic: {topic_id}")

    # Create intent
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="k8s-status",
        intent_type="lookup"
    )
    print(f"  ✅ Created intent: {intent_id}")

    # Update intent status to dispatched
    await store.update_intent_status(intent_id, "dispatched")
    print(f"  ✅ Updated intent status to dispatched")

    # Simulate fetch/synthesize result
    result_data = {
        "pods": [
            {"name": "pod-1", "status": "running"},
            {"name": "pod-2", "status": "pending"}
        ],
        "total": 2
    }

    result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Pod status retrieved",
        data=result_data,
        urgency="normal"
    )
    print(f"  ✅ Created result: {result_id}")

    # Update intent to resolved
    await store.update_intent_status(intent_id, "resolved")
    print(f"  ✅ Updated intent status to resolved")

    # Broadcast result via SSE
    from src.sse.broadcaster import broadcast_result

    broadcast_data = {
        "result_id": result_id,
        "intent_id": intent_id,
        "topic_id": topic_id,
        "summary": "Pod status retrieved",
        "data": result_data,
        "urgency": "normal"
    }

    sent_count = await broadcast_result(
        result=broadcast_data,
        session_id=session_id,
        target_surface_id=surface_id
    )
    assert sent_count == 1, f"Expected 1 recipient, got {sent_count}"
    print(f"  ✅ Broadcasted result to {sent_count} connection(s)")

    # Verify SSE event received
    sse_event = await conn.queue.get()
    assert sse_event.event_type == EventType.RESULT_CREATED, "Event type mismatch"
    assert sse_event.data["result_id"] == result_id, "Result ID mismatch"
    assert sse_event.data["summary"] == "Pod status retrieved", "Summary mismatch"
    print(f"  ✅ SSE event received with correct data")

    # Verify persistence
    topics = await store.get_active_topics(session_id)
    assert len(topics) == 1, "Should have 1 topic"
    assert topics[0]["result_count"] == 1, "Topic should have 1 result"
    print(f"  ✅ Persistence verified: {topics[0]['result_count']} result(s) for topic")

    result = await store.get_latest_result_for_topic(topic_id)
    assert result is not None, "Result should exist"
    assert result["id"] == result_id, "Result ID mismatch"
    print(f"  ✅ Result retrieved from database")

    # Don't stop the global broadcaster - it may be used by other code
    await store.close()
    test_db_path.unlink()

    print("✅ End-to-end dispatch flow test PASSED")
    return True


async def main():
    """Run all persistence and SSE verification tests."""
    print("="*50)
    print("PERSISTENCE & SSE VERIFICATION TEST SUITE")
    print("="*50)

    tests = [
        test_topic_creation_persistence,
        test_result_persistence,
        test_sse_event_broadcast,
        test_surface_id_targeting,
        test_end_to_end_dispatch_flow,
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "="*50)
    passed = sum(results)
    total = len(results)

    if all(results):
        print(f"✅ ALL {total} TESTS PASSED")
        print("="*50)
        return 0
    else:
        print(f"❌ {total - passed}/{total} TESTS FAILED")
        print("="*50)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
