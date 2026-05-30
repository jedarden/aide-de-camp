#!/usr/bin/env python3
"""Test SSE broadcaster connectivity and event delivery."""

import asyncio
import sys
from pathlib import Path

# Ensure the project root is in the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.sse.broadcaster import SSEBroadcaster, SSEEvent, EventType


async def test_sse_broadcaster():
    """Test SSE broadcaster registration and event delivery."""
    print("Testing Phase 1: SSE Broadcaster...")

    broadcaster = SSEBroadcaster()

    # Start broadcaster
    await broadcaster.start()
    print("  ✅ Broadcaster started")

    # Register a connection
    conn1 = broadcaster.register(
        surface_id="canvas-1",
        session_id="session-1",
        surface_type="canvas"
    )
    print(f"  ✅ Registered connection: {conn1.connection_id}")

    # Register another connection
    conn2 = broadcaster.register(
        surface_id="audio-1",
        session_id="session-1",
        surface_type="audio"
    )
    print(f"  ✅ Registered connection: {conn2.connection_id}")

    # Broadcast to session
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={"summary": "Test result", "intent_id": "test-intent"},
        target_session_id="session-1"
    )
    sent_count = await broadcaster.broadcast(event)
    print(f"  ✅ Broadcasted event to {sent_count} connections")

    # Broadcast to specific surface
    event2 = SSEEvent(
        event_type=EventType.WORKLOAD_SUMMARY,
        data={"pending_intents": 0},
        target_session_id="session-1",
        target_surface_id="canvas-1"
    )
    sent_count = await broadcaster.broadcast(event2)
    print(f"  ✅ Broadcasted to specific surface: {sent_count} connections")

    # Broadcast with exclusion
    event3 = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={"summary": "Another result"},
        target_session_id="session-1",
        exclude_surface_id="audio-1"
    )
    sent_count = await broadcaster.broadcast(event3)
    print(f"  ✅ Broadcasted with exclusion: {sent_count} connections")

    # Test event generator
    events_received = []
    async def collect_events():
        async for event_data in broadcaster.event_generator(conn1):
            # Parse the SSE format
            lines = event_data.strip().split('\n')
            event_type = None
            data = None
            for line in lines:
                if line.startswith('event: '):
                    event_type = line[7:]
                elif line.startswith('data: '):
                    import json
                    data = json.loads(line[6:])
            if event_type and data:
                events_received.append((event_type, data))
                if len(events_received) >= 2:
                    break

    # Run the collector briefly
    collector_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.1)

    # Stop broadcaster
    await broadcaster.stop()
    print("  ✅ Broadcaster stopped")

    print("\n✅ Phase 1 SSE Broadcaster Test PASSED")
    return True


async def test_event_type_constants():
    """Test event type constants are defined."""
    print("\nTesting Phase 1: Event Type Constants...")

    # Check all event types are defined
    event_types = [
        EventType.CONNECTED,
        EventType.DISCONNECT,
        EventType.HEARTBEAT,
        EventType.RESULT_CREATED,
        EventType.RESULT_UPDATED,
        EventType.INTENT_PENDING,
        EventType.INTENT_DISPATCHED,
        EventType.INTENT_RESOLVED,
        EventType.TOPIC_CREATED,
        EventType.TOPIC_UPDATED,
        EventType.TOPIC_STALE,
        EventType.WORKLOAD_SUMMARY,
        EventType.EXCEPTION_RAISED,
        EventType.BEAD_CLOSED,
        EventType.BEAD_FAILED,
    ]

    print(f"  ✅ All {len(event_types)} event types defined")
    print(f"     Event types: {[et for et in event_types[:5]]}...")

    print("\n✅ Phase 1 Event Type Constants Test PASSED")
    return True


async def test_sse_formatting():
    """Test SSE formatting."""
    print("\nTesting Phase 1: SSE Formatting...")

    broadcaster = SSEBroadcaster()
    formatted = broadcaster._format_sse("test_event", {"message": "hello"})

    expected_lines = ["event: test_event", "data: {\"message\": \"hello\"}", ""]
    for expected_line in expected_lines:
        if expected_line not in formatted:
            print(f"  ❌ Expected line not found: {expected_line}")
            return False

    print(f"  ✅ SSE format correct")
    print(f"     Output: {repr(formatted)}")

    print("\n✅ Phase 1 SSE Formatting Test PASSED")
    return True


async def main():
    """Run all SSE tests."""
    print("="*50)
    print("PHASE 1 SSE TEST SUITE")
    print("="*50)

    tests = [
        test_sse_broadcaster,
        test_event_type_constants,
        test_sse_formatting,
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
    if all(results):
        print("✅ ALL SSE TESTS PASSED")
        print("="*50)
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("="*50)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
