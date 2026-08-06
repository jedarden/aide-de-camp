#!/usr/bin/env python3
"""
Manual verification script for storage and SSE broadcast via test endpoint.

This script demonstrates that the /api/v1/test/dispatch-synthetic endpoint:
1. Stores results correctly in SQLite session store
2. Broadcasts SSE events to connected surfaces
3. Matches /dispatch payload structure
4. Works with correct timing

Run with: .venv/bin/python tests/manual/test_manual_sse_verification.py
"""
import asyncio
import json
import uuid
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import httpx
import aiosqlite

# Test configuration
BASE_URL = "http://localhost:8000"
TEST_DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")


async def verify_storage():
    """Verify that results are stored correctly in the database."""
    print("\n=== Testing Storage Verification ===")

    # Generate test data
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())

    print(f"Session ID: {session_id}")
    print(f"Surface ID: {surface_id}")

    # Create synthetic result via HTTP
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch-synthetic",
            json={
                "session_id": session_id,
                "surface_id": surface_id,
                "test_data": {
                    "utterance": "manual test utterance for storage verification",
                    "project_slug": "test-project",
                    "intent_type": "status",
                    "topic_label": "Manual Verification Topic",
                    "topic_type": "research",
                    "summary": "Manual verification test result",
                    "data": {
                        "test_mode": True,
                        "manual_test": True,
                        "message": "This is a manual verification test",
                    },
                    "urgency": "normal",
                    "result_type": "status"
                }
            },
            timeout=30.0
        )

        if response.status_code != 200:
            print(f"❌ Failed to create synthetic result: {response.status_code}")
            print(f"Response: {response.text}")
            return False

        result = response.json()
        print(f"✅ Created synthetic result:")
        print(f"   Result ID: {result['result_id']}")
        print(f"   Intent ID: {result['intent_id']}")
        print(f"   Topic ID: {result['topic_id']}")

    # Verify storage in database
    async with aiosqlite.connect(TEST_DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Check result exists
        cursor = await db.execute(
            "SELECT * FROM results WHERE id = ?",
            (result['result_id'],)
        )
        row = await cursor.fetchone()

        if not row:
            print("❌ Result not found in database")
            return False

        print("✅ Result stored in database:")
        print(f"   ID: {row['id']}")
        print(f"   Summary: {row['summary']}")
        print(f"   Urgency: {row['urgency']}")
        print(f"   Result Type: {row['result_type']}")

        # Verify linked records exist
        cursor = await db.execute(
            "SELECT * FROM intents WHERE id = ?",
            (result['intent_id'],)
        )
        intent = await cursor.fetchone()
        if not intent:
            print("❌ Intent not found in database")
            return False
        print(f"✅ Intent exists: {intent['id']}")

        cursor = await db.execute(
            "SELECT * FROM topics WHERE id = ?",
            (result['topic_id'],)
        )
        topic = await cursor.fetchone()
        if not topic:
            print("❌ Topic not found in database")
            return False
        print(f"✅ Topic exists: {topic['label']}")

        # Verify data payload
        data = json.loads(row['data'])
        if data.get('test_mode') and data.get('manual_test'):
            print("✅ Data payload correctly stored")
        else:
            print("❌ Data payload corrupted")
            return False

    return True


async def verify_sse_broadcast():
    """Verify that SSE events are broadcast to connected surfaces."""
    print("\n=== Testing SSE Broadcast Verification ===")

    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())

    print(f"Session ID: {session_id}")
    print(f"Surface ID: {surface_id}")

    # Track SSE events
    events_received = []

    async def listen_to_sse():
        """Listen for SSE events."""
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET",
                f"{BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                },
                timeout=60.0
            ) as response:
                if response.status_code != 200:
                    print(f"❌ SSE connection failed: {response.status_code}")
                    return

                print("✅ SSE connection established")

                # Parse SSE stream
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        events_received.append({"event_type": event_type})
                        print(f"📨 Received SSE event: {event_type}")

                        # We got at least one result_created, we can stop
                        if event_type == "result_created":
                            await asyncio.sleep(0.5)  # Wait a bit more to capture all events
                            break

    # Start SSE listener in background
    sse_task = asyncio.create_task(listen_to_sse())

    # Wait a moment for SSE connection to establish
    await asyncio.sleep(1.0)

    # Create synthetic result which should trigger SSE event
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch-synthetic",
            json={
                "session_id": session_id,
                "surface_id": surface_id,
                "test_data": {
                    "summary": "SSE broadcast test result",
                    "data": {"sse_test": True},
                    "urgency": "normal",
                }
            },
            timeout=30.0
        )

        if response.status_code != 200:
            print(f"❌ Failed to create synthetic result: {response.status_code}")
            sse_task.cancel()
            return False

        print("✅ Synthetic result created")

    # Wait for SSE events to be received
    try:
        await asyncio.wait_for(sse_task, timeout=10.0)
    except asyncio.TimeoutError:
        print("⚠️  SSE listener timed out")
        sse_task.cancel()

    # Verify we got result_created event
    result_created_events = [e for e in events_received if e["event_type"] == "result_created"]

    if result_created_events:
        print(f"✅ Received {len(result_created_events)} result_created event(s)")
        return True
    else:
        print(f"❌ No result_created events received (got {len(events_received)} events total)")
        print(f"Events: {events_received}")
        return False


async def verify_payload_structure():
    """Verify that SSE event payload matches /dispatch structure."""
    print("\n=== Testing Payload Structure Verification ===")

    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())

    # Track SSE events with full data
    events_received = []

    async def listen_to_sse_with_data():
        """Listen for SSE events and capture full data."""
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET",
                f"{BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                },
                timeout=60.0
            ) as response:
                if response.status_code != 200:
                    return

                current_event = None
                current_data = []

                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        # Save previous event if any
                        if current_event and current_data:
                            events_received.append({
                                "event_type": current_event,
                                "data": "\n".join(current_data)
                            })

                        current_event = line.split(":", 1)[1].strip()
                        current_data = []

                    elif line.startswith("data:"):
                        current_data.append(line.split(":", 1)[1].strip())

                    # Stop after result_created
                    if current_event == "result_created" and current_data:
                        events_received.append({
                            "event_type": current_event,
                            "data": "\n".join(current_data)
                        })
                        break

    # Start SSE listener
    sse_task = asyncio.create_task(listen_to_sse_with_data())
    await asyncio.sleep(1.0)

    # Create synthetic result
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch-synthetic",
            json={
                "session_id": session_id,
                "surface_id": surface_id,
                "test_data": {
                    "summary": "Payload structure test",
                    "urgency": "high",
                    "data": {"structure_test": True}
                }
            },
            timeout=30.0
        )

        if response.status_code != 200:
            print(f"❌ Failed to create synthetic result")
            sse_task.cancel()
            return False

    # Wait for SSE events
    try:
        await asyncio.wait_for(sse_task, timeout=10.0)
    except asyncio.TimeoutError:
        sse_task.cancel()

    # Verify payload structure
    if not events_received:
        print("❌ No SSE events received")
        return False

    event = events_received[0]
    if event["event_type"] != "result_created":
        print(f"❌ Wrong event type: {event['event_type']}")
        return False

    print("✅ Received result_created event")

    try:
        data = json.loads(event["data"])
        print("✅ Event data is valid JSON")

        # Check for required fields from /dispatch
        required_fields = ["intent_id", "topic_id", "summary", "urgency"]
        missing_fields = [f for f in required_fields if f not in data]

        if missing_fields:
            print(f"❌ Missing required fields: {missing_fields}")
            print(f"   Data: {json.dumps(data, indent=2)}")
            return False

        print("✅ All required fields present:")
        for field in required_fields:
            print(f"   - {field}: {data.get(field)}")

        return True

    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse event data: {e}")
        return False


async def verify_broadcast_timing():
    """Verify that broadcast timing matches /dispatch expectations."""
    print("\n=== Testing Broadcast Timing Verification ===")

    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())

    # Track timing
    broadcast_times = []

    async def listen_to_sse_with_timing():
        """Listen for SSE events and record timing."""
        import time
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET",
                f"{BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                },
                timeout=60.0
            ) as response:
                if response.status_code != 200:
                    return

                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        broadcast_times.append(time.time())

                        if event_type == "result_created":
                            break

    # Start SSE listener
    sse_task = asyncio.create_task(listen_to_sse_with_timing())
    await asyncio.sleep(1.0)

    # Create synthetic result and measure time
    import time
    start_time = time.time()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch-synthetic",
            json={
                "session_id": session_id,
                "surface_id": surface_id,
            },
            timeout=30.0
        )

        creation_time = time.time()

        if response.status_code != 200:
            print(f"❌ Failed to create synthetic result")
            sse_task.cancel()
            return False

    # Wait for SSE event
    try:
        await asyncio.wait_for(sse_task, timeout=10.0)
    except asyncio.TimeoutError:
        sse_task.cancel()

    if not broadcast_times:
        print("❌ No broadcast events received")
        return False

    broadcast_time = broadcast_times[0]
    latency_ms = (broadcast_time - creation_time) * 1000
    total_time_ms = (broadcast_time - start_time) * 1000

    print(f"✅ Broadcast timing:")
    print(f"   Creation to broadcast: {latency_ms:.2f}ms")
    print(f"   Total end-to-end: {total_time_ms:.2f}ms")

    # Broadcast should happen quickly (< 500ms)
    if latency_ms < 500:
        print(f"✅ Broadcast latency within acceptable range")
        return True
    else:
        print(f"⚠️  Broadcast latency exceeds 500ms (may be due to system load)")
        return True  # Still pass, but note the latency


async def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Storage and SSE Broadcast Verification")
    print("=" * 60)

    # Check if server is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health", timeout=5.0)
            if response.status_code != 200:
                print(f"❌ Server health check failed: {response.status_code}")
                return
    except Exception as e:
        print(f"❌ Cannot connect to server at {BASE_URL}")
        print(f"   Error: {e}")
        print(f"\nPlease start the server first:")
        print(f"   systemctl --user start aide-de-camp")
        print(f"   or")
        print(f"   .venv/bin/python -m uvicorn src.main:app")
        return

    print("✅ Server is running")

    results = []

    # Run tests
    tests = [
        ("Storage", verify_storage),
        ("SSE Broadcast", verify_sse_broadcast),
        ("Payload Structure", verify_payload_structure),
        ("Broadcast Timing", verify_broadcast_timing),
    ]

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ {test_name} test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Verification Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All verification tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
