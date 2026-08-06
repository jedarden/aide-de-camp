#!/usr/bin/env python3
"""
Simple verification script for storage and SSE broadcast functionality.

This demonstrates that:
1. Results are stored in the session database
2. SSE events are broadcast to connected surfaces
3. Payload structure matches /dispatch
"""
import asyncio
import json
import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import httpx
import aiosqlite

BASE_URL = "http://localhost:8000"
TEST_DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")


async def test_storage():
    """Test that results are stored in the database."""
    print("\n=== Storage Verification ===")

    # Create a synthetic result
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch-synthetic",
            json={
                "session_id": session_id,
                "surface_id": surface_id,
                "test_data": {
                    "summary": "Storage test result",
                    "data": {"storage_test": True},
                    "urgency": "normal",
                    "result_type": "status"
                }
            }
        )

        if response.status_code != 200:
            print(f"❌ Failed to create result: {response.status_code}")
            return False

        result_data = response.json()
        result_id = result_data["result_id"]
        intent_id = result_data["intent_id"]
        topic_id = result_data["topic_id"]
        print(f"✅ Created result: {result_id}")

    # Check database with retry logic
    max_retries = 5
    found = False

    for attempt in range(max_retries):
        await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff

        async with aiosqlite.connect(TEST_DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Check result
            cursor = await db.execute(
                "SELECT * FROM results WHERE id = ?", (result_id,)
            )
            result = await cursor.fetchone()

        if result:
            print(f"✅ Result found in database")
            print(f"   Summary: {result['summary']}")
            print(f"   Urgency: {result['urgency']}")
            print(f"   Result Type: {result['result_type']}")

            # Verify data payload
            data = json.loads(result['data'])
            if data.get('storage_test'):
                print(f"✅ Data payload correctly stored")
            else:
                print(f"❌ Data payload corrupted")
                return False
        else:
            print(f"❌ Result not found in database")
            return False

        # Check linked intent
        cursor = await db.execute(
            "SELECT * FROM intents WHERE id = ?", (intent_id,)
        )
        intent = await cursor.fetchone()
        if intent:
            print(f"✅ Intent exists: {intent['id']}")
        else:
            print(f"❌ Intent not found")
            return False

        # Check linked topic
        cursor = await db.execute(
            "SELECT * FROM topics WHERE id = ?", (topic_id,)
        )
        topic = await cursor.fetchone()
        if topic:
            print(f"✅ Topic exists: {topic['label']}")
        else:
            print(f"❌ Topic not found")
            return False

    return True


async def test_sse():
    """Test that SSE events are broadcast."""
    print("\n=== SSE Broadcast Verification ===")

    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())

    events = []

    async def listen_for_events():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET",
                f"{BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                },
                timeout=30.0
            ) as response:
                if response.status_code != 200:
                    print(f"❌ SSE connection failed")
                    return

                print("✅ SSE connected")

                # Listen for events
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                        events.append(event_type)
                        print(f"📨 Event: {event_type}")

                        if event_type == "result_created":
                            break

    # Start listener
    listener = asyncio.create_task(listen_for_events())
    await asyncio.sleep(1.0)

    # Create result (should trigger SSE event)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch-synthetic",
            json={
                "session_id": session_id,
                "surface_id": surface_id,
                "test_data": {
                    "summary": "SSE test result",
                    "urgency": "normal"
                }
            }
        )

        if response.status_code != 200:
            print(f"❌ Failed to create result")
            listener.cancel()
            return False

        print("✅ Created result")

    # Wait for events
    try:
        await asyncio.wait_for(listener, timeout=10.0)
    except asyncio.TimeoutError:
        listener.cancel()

    # Check for result_created event
    if "result_created" in events:
        print("✅ result_created event received")
        return True
    else:
        print(f"❌ No result_created event (got: {events})")
        return False


async def test_payload_structure():
    """Test that SSE payload matches /dispatch structure."""
    print("\n=== Payload Structure Verification ===")

    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())

    payload_data = []

    async def capture_payload():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET",
                f"{BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                },
                timeout=30.0
            ) as response:
                if response.status_code != 200:
                    return

                current_event = None
                current_data = []

                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        if current_event and current_data:
                            payload_data.append({
                                "event": current_event,
                                "data": json.loads(current_data[0] if current_data else "{}")
                            })
                        current_event = line.split(":", 1)[1].strip()
                        current_data = []
                    elif line.startswith("data:"):
                        current_data.append(line.split(":", 1)[1].strip())
                    if current_event == "result_created" and current_data:
                        payload_data.append({
                            "event": current_event,
                            "data": json.loads(current_data[0])
                        })
                        break

    # Start capture
    capturer = asyncio.create_task(capture_payload())
    await asyncio.sleep(1.0)

    # Create result
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch-synthetic",
            json={
                "session_id": session_id,
                "surface_id": surface_id,
                "test_data": {
                    "summary": "Payload test",
                    "urgency": "high"
                }
            }
        )

        if response.status_code != 200:
            print(f"❌ Failed to create result")
            capturer.cancel()
            return False

    # Wait for capture
    try:
        await asyncio.wait_for(capturer, timeout=10.0)
    except asyncio.TimeoutError:
        capturer.cancel()

    # Verify payload
    result_events = [p for p in payload_data if p["event"] == "result_created"]

    if not result_events:
        print(f"❌ No result_created event captured")
        return False

    payload = result_events[0]["data"]
    print("✅ Captured result_created payload")

    # Check required fields
    required_fields = ["intent_id", "topic_id", "summary", "urgency"]
    missing = [f for f in required_fields if f not in payload]

    if missing:
        print(f"❌ Missing fields: {missing}")
        print(f"   Payload: {json.dumps(payload, indent=2)}")
        return False

    print(f"✅ All required fields present:")
    for field in required_fields:
        print(f"   - {field}: {payload[field]}")

    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Storage and SSE Verification")
    print("=" * 60)

    # Check server
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health", timeout=5.0)
            if response.status_code != 200:
                print(f"❌ Server unhealthy: {response.status_code}")
                return 1
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        return 1

    print("✅ Server is running")

    # Run tests
    tests = [
        ("Storage", test_storage),
        ("SSE Broadcast", test_sse),
        ("Payload Structure", test_payload_structure),
    ]

    results = []
    for name, func in tests:
        try:
            result = await func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nPassed: {passed}/{total}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
