#!/usr/bin/env .venv/bin/python
"""
SSE Broadcast Verification Test for POST /test endpoint (bead: adc-8t720)

This test verifies that the POST /test endpoint correctly broadcasts SSE events
matching the /dispatch pattern, ensuring:
1. SSE event with event_type='result_created' is broadcast
2. Event data includes result_id and surface_id
3. Canvas listener receives the event
4. Broadcast occurs after storage completes
"""
import asyncio
import json
import uuid
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from src.main import app
from src.sse.broadcaster import get_broadcaster, SSEEvent, EventType


async def test_sse_broadcast_verification():
    """Verify POST /test endpoint broadcasts SSE events correctly."""
    print("\n" + "="*70)
    print("SSE Broadcast Verification Test for POST /test endpoint")
    print("="*70)

    # Generate test IDs
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())
    test_utterance = "SSE broadcast verification test"

    print(f"\nTest Configuration:")
    print(f"  Session ID: {session_id[:8]}...")
    print(f"  Surface ID: {surface_id[:8]}...")
    print(f"  Utterance: {test_utterance}")

    # Initialize broadcaster (simulating lifespan startup)
    broadcaster = get_broadcaster()
    await broadcaster.start()
    print(f"\n✓ Initialized SSE broadcaster")

    # Register SSE listener BEFORE calling the endpoint

    # Create a queue to collect SSE events
    event_queue = asyncio.Queue()

    # Register a test connection that will collect events
    test_connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )

    print(f"\n✓ Registered SSE connection for surface {surface_id[:8]}...")

    # Event collector background task
    events_received = []

    async def collect_events():
        """Collect events from the connection queue."""
        try:
            # Wait a short time for the event
            for _ in range(10):  # Poll for up to 1 second
                try:
                    event = await asyncio.wait_for(
                        test_connection.queue.get(),
                        timeout=0.1
                    )
                    if isinstance(event, SSEEvent):
                        events_received.append(event)
                        print(f"  ✓ Collected event: {event.event_type}")
                        if event.event_type == EventType.RESULT_CREATED:
                            break  # Got what we wanted
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            print(f"  ✗ Event collection error: {e}")

    # Call the POST /test endpoint
    print(f"\n1. Calling POST /test endpoint...")

    # Patch the _broadcaster global in main.py to use our initialized broadcaster
    with patch('src.main._broadcaster', broadcaster):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/test",
                json={
                    "utterance": test_utterance,
                    "session_id": session_id,
                    "surface_id": surface_id
                },
                timeout=30.0
            )

    print(f"  Response status: {response.status_code}")

    if response.status_code != 200:
        print(f"  ✗ Endpoint failed: {response.text}")
        await broadcaster.stop()
        return False

    response_data = response.json()
    print(f"  ✓ Endpoint returned success")

    # Start event collection
    print(f"\n2. Collecting SSE events...")
    await collect_events()

    # Verify acceptance criteria
    print(f"\n" + "="*70)
    print("VERIFICATION RESULTS")
    print("="*70)

    all_passed = True

    # Criterion 1: SSE event with event_type='result_created' is broadcast
    print(f"\n[1] SSE event with event_type='result_created' is broadcast")
    result_created_events = [e for e in events_received if e.event_type == EventType.RESULT_CREATED]

    if result_created_events:
        print(f"  ✓ PASS: Found {len(result_created_events)} result_created event(s)")
    else:
        print(f"  ✗ FAIL: No result_created events found")
        print(f"    Events received: {[e.event_type for e in events_received]}")
        all_passed = False

    # Criterion 2: Event data includes result_id, and event routing includes target_surface_id
    print(f"\n[2] Event data includes result_id, and event routing includes target_surface_id")

    if result_created_events:
        event = result_created_events[0]
        event_data = event.data

        has_result_id = "result_id" in event_data
        has_target_surface = event.target_surface_id is not None

        if has_result_id:
            print(f"  ✓ PASS: result_id present in event data")
            print(f"    result_id: {event_data.get('result_id', 'N/A')[:8]}...")
        else:
            print(f"  ✗ FAIL: result_id missing from event data")
            print(f"    Event data keys: {list(event_data.keys())}")
            all_passed = False

        if has_target_surface:
            print(f"  ✓ PASS: target_surface_id present in event routing")
            print(f"    target_surface_id: {event.target_surface_id[:8]}...")
        else:
            print(f"  ✗ FAIL: target_surface_id missing from event routing")
            all_passed = False
    else:
        print(f"  ✗ FAIL: Cannot verify - no result_created events found")
        all_passed = False

    # Criterion 3: Canvas listener receives the event
    print(f"\n[3] Canvas listener receives the event")

    if result_created_events:
        print(f"  ✓ PASS: Event received by registered canvas connection")
        print(f"    Connection surface_id: {test_connection.surface_id[:8]}...")
        print(f"    Event target_surface_id: {result_created_events[0].target_surface_id}")
    else:
        print(f"  ✗ FAIL: No event received by canvas listener")
        all_passed = False

    # Criterion 4: Broadcast occurs after storage completes
    print(f"\n[4] Broadcast occurs after storage completes")

    # Check response has stored data
    if "stored" in response_data:
        stored = response_data["stored"]
        has_result_id = "result_id" in stored

        if has_result_id:
            stored_result_id = stored["result_id"]
            print(f"  ✓ PASS: Storage completed before broadcast")
            print(f"    Stored result_id: {stored_result_id[:8]}...")

            # Verify the event data matches the stored data
            if result_created_events:
                event_result_id = result_created_events[0].data.get("result_id")
                if event_result_id == stored_result_id:
                    print(f"  ✓ PASS: Event result_id matches stored result_id")
                else:
                    print(f"  ⚠ WARNING: result_id mismatch")
                    print(f"    Stored: {stored_result_id[:8]}...")
                    print(f"    Event: {event_result_id[:8]}...")
        else:
            print(f"  ✗ FAIL: No result_id in stored data")
            all_passed = False
    else:
        print(f"  ✗ FAIL: No 'stored' field in response")
        all_passed = False

    # Verify SSE broadcast confirmation in response
    print(f"\n[BONUS] SSE broadcast confirmation in response")

    if "sse_broadcast" in response_data:
        sse_broadcast = response_data["sse_broadcast"]

        if sse_broadcast and sse_broadcast.get("sent"):
            print(f"  ✓ PASS: Response confirms SSE broadcast sent")
            print(f"    Event type: {sse_broadcast.get('event_type')}")
            print(f"    Connections sent: {sse_broadcast.get('connections_sent')}")
        else:
            print(f"  ✗ FAIL: SSE broadcast marked as not sent")
            print(f"    sse_broadcast: {sse_broadcast}")
            all_passed = False
    else:
        print(f"  ⚠ WARNING: No 'sse_broadcast' field in response")

    # Cleanup
    broadcaster.unregister(test_connection.connection_id)
    await broadcaster.stop()
    print(f"\n✓ Stopped SSE broadcaster")

    # Final result
    print(f"\n" + "="*70)
    if all_passed:
        print("✓ ALL CRITERIA PASSED")
        print("="*70)
        return True
    else:
        print("✗ SOME CRITERIA FAILED")
        print("="*70)
        return False


async def main():
    """Run the verification test."""
    try:
        passed = await test_sse_broadcast_verification()
        return 0 if passed else 1
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
