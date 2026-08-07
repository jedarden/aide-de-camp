#!/usr/bin/env .venv/bin/python
"""
Integration Test: POST /test Payload Matching and Verification (bead: adc-2zi7q)

This test verifies end-to-end integration:
1. POST /test accepts session_id and surface_id as query parameters
2. Storage payload matches /dispatch payload structure (same fields)
3. SSE broadcast is sent successfully
4. Verification report returns all checks passing

Acceptance criteria:
- Storage payload matches /dispatch payload (same fields)
- Test endpoint accepts session_id and surface_id query params
- Returns {"storage_match": true, "sse_broadcast": true, "payload_match": true}
- Integration test confirms full pipeline works
"""
import asyncio
import json
import uuid
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from src.main import app
from src.sse.broadcaster import get_broadcaster, SSEEvent, EventType


async def test_query_parameters():
    """Verify POST /test accepts session_id and surface_id as query parameters."""
    print("\n" + "="*70)
    print("Query Parameters Test")
    print("="*70)

    # Generate test IDs
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())
    test_utterance = "Query parameters verification test"

    print(f"\nTest Configuration:")
    print(f"  Session ID: {session_id[:8]}...")
    print(f"  Surface ID: {surface_id[:8]}...")
    print(f"  Utterance: {test_utterance}")

    # Initialize broadcaster for SSE broadcast
    broadcaster = get_broadcaster()
    await broadcaster.start()
    print(f"\n✓ Initialized SSE broadcaster")

    # Register connection for surface
    test_connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )
    print(f"✓ Registered SSE connection for surface {surface_id[:8]}...")

    # Call POST /test with query parameters (not in body)
    print(f"\n1. Calling POST /test with query parameters...")

    with patch('src.main._broadcaster', broadcaster):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/test?session_id={session_id}&surface_id={surface_id}",
                json={
                    "utterance": test_utterance,
                    # Note: session_id and surface_id NOT in body
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

    # Verify session_id and surface_id were used from query params
    print(f"\n2. Verifying query parameters were used...")

    if response_data.get("received", {}).get("session_id") == session_id:
        print(f"  ✓ PASS: session_id from query parameter used")
    else:
        print(f"  ✗ FAIL: session_id not from query parameter")
        print(f"    Expected: {session_id[:8]}...")
        print(f"    Got: {response_data.get('received', {}).get('session_id')}")
        await broadcaster.stop()
        return False

    # Verify SSE broadcast was sent (surface_id from query param)
    verification = response_data.get("verification", {})
    sse_broadcast = response_data.get("sse_broadcast", {})

    print(f"\n3. Verifying SSE broadcast...")
    print(f"  Verification: {verification}")
    print(f"  SSE broadcast: {sse_broadcast}")

    if verification.get("sse_broadcast") and sse_broadcast.get("sent"):
        print(f"  ✓ PASS: SSE broadcast sent using surface_id from query parameter")
    else:
        print(f"  ✗ FAIL: SSE broadcast not sent")
        await broadcaster.stop()
        return False

    # Cleanup
    broadcaster.unregister(test_connection.connection_id)
    await broadcaster.stop()
    print(f"\n✓ Stopped SSE broadcaster")

    print(f"\n" + "="*70)
    print("✓ QUERY PARAMETERS TEST PASSED")
    print("="*70)
    return True


async def test_storage_payload_structure():
    """Verify storage payload matches /dispatch payload structure."""
    print("\n" + "="*70)
    print("Storage Payload Structure Test")
    print("="*70)

    # Generate test IDs
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())
    test_utterance = "Storage payload structure verification"

    print(f"\nTest Configuration:")
    print(f"  Session ID: {session_id[:8]}...")
    print(f"  Surface ID: {surface_id[:8]}...")
    print(f"  Utterance: {test_utterance}")

    # Call POST /test
    print(f"\n1. Calling POST /test endpoint...")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/test",
            json={
                "utterance": test_utterance,
                "session_id": session_id,
                "surface_id": surface_id,
            },
            timeout=30.0
        )

    print(f"  Response status: {response.status_code}")

    if response.status_code != 200:
        print(f"  ✗ Endpoint failed: {response.text}")
        return False

    response_data = response.json()
    print(f"  ✓ Endpoint returned success")

    # Verify stored data structure matches /dispatch
    print(f"\n2. Verifying storage payload structure...")

    # Get the stored IDs
    stored = response_data.get("stored", {})
    utterance_id = stored.get("utterance_id")
    intent_id = stored.get("intent_id")
    topic_id = stored.get("topic_id")
    result_id = stored.get("result_id")

    if not all([utterance_id, intent_id, topic_id, result_id]):
        print(f"  ✗ FAIL: Missing stored IDs")
        print(f"    Stored: {stored}")
        return False

    print(f"  ✓ All storage IDs present")

    # Verify storage_match flag
    verification = response_data.get("verification", {})
    storage_match = verification.get("storage_match")

    print(f"\n3. Verifying storage_match flag...")

    if storage_match:
        print(f"  ✓ PASS: storage_match = true")
    else:
        print(f"  ✗ FAIL: storage_match = false")
        print(f"    Verification: {verification}")
        return False

    # Verify payload_match flag
    payload_match = verification.get("payload_match")

    print(f"\n4. Verifying payload_match flag...")

    if payload_match:
        print(f"  ✓ PASS: payload_match = true")
    else:
        print(f"  ✗ FAIL: payload_match = false")
        print(f"    Verification: {verification}")
        return False

    print(f"\n" + "="*70)
    print("✓ STORAGE PAYLOAD STRUCTURE TEST PASSED")
    print("="*70)
    return True


async def test_sse_broadcast_verification():
    """Verify SSE broadcast is sent and contains correct data."""
    print("\n" + "="*70)
    print("SSE Broadcast Verification Test")
    print("="*70)

    # Generate test IDs
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())
    test_utterance = "SSE broadcast verification test"

    print(f"\nTest Configuration:")
    print(f"  Session ID: {session_id[:8]}...")
    print(f"  Surface ID: {surface_id[:8]}...")
    print(f"  Utterance: {test_utterance}")

    # Initialize broadcaster
    broadcaster = get_broadcaster()
    await broadcaster.start()
    print(f"\n✓ Initialized SSE broadcaster")

    # Register SSE listener BEFORE calling the endpoint
    event_queue = asyncio.Queue()

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

    # Call POST /test endpoint
    print(f"\n1. Calling POST /test endpoint...")

    with patch('src.main._broadcaster', broadcaster):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/test",
                json={
                    "utterance": test_utterance,
                    "session_id": session_id,
                    "surface_id": surface_id,
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

    # Verify SSE broadcast
    print(f"\n3. Verifying SSE broadcast...")

    verification = response_data.get("verification", {})
    sse_broadcast = response_data.get("sse_broadcast", {})

    print(f"  Verification: {verification}")
    print(f"  SSE broadcast: {sse_broadcast}")

    if not verification.get("sse_broadcast"):
        print(f"  ✗ FAIL: sse_broadcast flag is false")
        await broadcaster.stop()
        return False

    if not sse_broadcast.get("sent"):
        print(f"  ✗ FAIL: sse_broadcast.sent is false")
        await broadcaster.stop()
        return False

    print(f"  ✓ PASS: SSE broadcast sent")

    # Verify event data
    print(f"\n4. Verifying SSE event data...")

    result_created_events = [e for e in events_received if e.event_type == EventType.RESULT_CREATED]

    if not result_created_events:
        print(f"  ✗ FAIL: No result_created events received")
        await broadcaster.stop()
        return False

    event = result_created_events[0]
    event_data = event.data

    # Verify event has expected fields
    expected_fields = ["intent_id", "topic_id", "result_id", "summary", "urgency"]
    missing_fields = [f for f in expected_fields if f not in event_data]

    if missing_fields:
        print(f"  ✗ FAIL: Missing fields in event data: {missing_fields}")
        print(f"    Event data: {event_data}")
        await broadcaster.stop()
        return False

    print(f"  ✓ PASS: Event data has all expected fields")

    # Verify surface_id targeting
    if event.target_surface_id == surface_id:
        print(f"  ✓ PASS: Event targeted to correct surface_id")
    else:
        print(f"  ✗ FAIL: Event targeted to wrong surface")
        print(f"    Expected: {surface_id[:8]}...")
        print(f"    Got: {event.target_surface_id}")
        await broadcaster.stop()
        return False

    # Cleanup
    broadcaster.unregister(test_connection.connection_id)
    await broadcaster.stop()
    print(f"\n✓ Stopped SSE broadcaster")

    print(f"\n" + "="*70)
    print("✓ SSE BROADCAST VERIFICATION TEST PASSED")
    print("="*70)
    return True


async def test_verification_report():
    """Verify verification report returns all checks passing."""
    print("\n" + "="*70)
    print("Verification Report Test")
    print("="*70)

    # Generate test IDs
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())
    test_utterance = "Verification report test"

    print(f"\nTest Configuration:")
    print(f"  Session ID: {session_id[:8]}...")
    print(f"  Surface ID: {surface_id[:8]}...")
    print(f"  Utterance: {test_utterance}")

    # Initialize broadcaster for SSE broadcast test
    broadcaster = get_broadcaster()
    await broadcaster.start()

    # Register connection
    test_connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )

    # Call POST /test endpoint
    print(f"\n1. Calling POST /test endpoint...")

    with patch('src.main._broadcaster', broadcaster):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/test",
                json={
                    "utterance": test_utterance,
                    "session_id": session_id,
                    "surface_id": surface_id,
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

    # Verify verification report structure
    print(f"\n2. Verifying verification report...")

    verification = response_data.get("verification")

    if not verification:
        print(f"  ✗ FAIL: No verification field in response")
        await broadcaster.stop()
        return False

    print(f"  Verification report: {verification}")

    # Check all three flags are true
    print(f"\n3. Checking all verification flags...")

    expected_flags = {
        "storage_match": True,
        "sse_broadcast": True,
        "payload_match": True,
    }

    all_pass = True

    for flag, expected_value in expected_flags.items():
        actual_value = verification.get(flag)

        if actual_value == expected_value:
            print(f"  ✓ PASS: {flag} = {actual_value}")
        else:
            print(f"  ✗ FAIL: {flag} = {actual_value} (expected {expected_value})")
            all_pass = False

    # Cleanup
    broadcaster.unregister(test_connection.connection_id)
    await broadcaster.stop()

    if not all_pass:
        print(f"\n" + "="*70)
        print("✗ VERIFICATION REPORT TEST FAILED")
        print("="*70)
        return False

    print(f"\n" + "="*70)
    print("✓ VERIFICATION REPORT TEST PASSED")
    print("="*70)
    return True


async def test_full_pipeline_integration():
    """End-to-end integration test confirming full pipeline works."""
    print("\n" + "="*70)
    print("Full Pipeline Integration Test")
    print("="*70)

    # Generate test IDs
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())
    test_utterance = "Full pipeline integration test"

    print(f"\nTest Configuration:")
    print(f"  Session ID: {session_id[:8]}...")
    print(f"  Surface ID: {surface_id[:8]}...")
    print(f"  Utterance: {test_utterance}")

    # Initialize broadcaster
    broadcaster = get_broadcaster()
    await broadcaster.start()

    # Register SSE listener
    test_connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )

    print(f"\n✓ Registered SSE connection")

    # Event collector
    events_received = []

    async def collect_events():
        """Collect events from the connection queue."""
        try:
            for _ in range(10):
                try:
                    event = await asyncio.wait_for(
                        test_connection.queue.get(),
                        timeout=0.1
                    )
                    if isinstance(event, SSEEvent):
                        events_received.append(event)
                        if event.event_type == EventType.RESULT_CREATED:
                            break
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            print(f"  ✗ Event collection error: {e}")

    # Test 1: Query parameters work
    print(f"\n1. Testing query parameters...")

    with patch('src.main._broadcaster', broadcaster):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/test?session_id={session_id}&surface_id={surface_id}",
                json={"utterance": test_utterance},
                timeout=30.0
            )

    if response.status_code != 200:
        print(f"  ✗ Query parameters test failed")
        await broadcaster.stop()
        return False

    print(f"  ✓ Query parameters accepted")

    # Test 2: SSE broadcast received
    print(f"\n2. Testing SSE broadcast...")
    await collect_events()

    if not events_received:
        print(f"  ✗ No SSE events received")
        await broadcaster.stop()
        return False

    print(f"  ✓ SSE broadcast received")

    # Test 3: Storage structure verified
    print(f"\n3. Testing storage structure...")

    response_data = response.json()
    verification = response_data.get("verification", {})

    if not verification.get("storage_match"):
        print(f"  ✗ Storage structure mismatch")
        await broadcaster.stop()
        return False

    print(f"  ✓ Storage structure verified")

    # Test 4: Payload types verified
    print(f"\n4. Testing payload types...")

    if not verification.get("payload_match"):
        print(f"  ✗ Payload types mismatch")
        await broadcaster.stop()
        return False

    print(f"  ✓ Payload types verified")

    # Test 5: All verification flags pass
    print(f"\n5. Testing all verification flags...")

    if not all(verification.get(k) for k in ["storage_match", "sse_broadcast", "payload_match"]):
        print(f"  ✗ Not all verification flags passed")
        print(f"    Verification: {verification}")
        await broadcaster.stop()
        return False

    print(f"  ✓ All verification flags passed")

    # Cleanup
    broadcaster.unregister(test_connection.connection_id)
    await broadcaster.stop()

    print(f"\n" + "="*70)
    print("✓ FULL PIPELINE INTEGRATION TEST PASSED")
    print("="*70)
    return True


async def main():
    """Run all integration tests."""
    print("\n" + "="*70)
    print("POST /test Payload Matching Integration Test Suite")
    print("Bead: adc-2zi7q")
    print("="*70)

    tests = [
        ("Query Parameters", test_query_parameters),
        ("Storage Payload Structure", test_storage_payload_structure),
        ("SSE Broadcast Verification", test_sse_broadcast_verification),
        ("Verification Report", test_verification_report),
        ("Full Pipeline Integration", test_full_pipeline_integration),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            print(f"\n\n{'='*70}")
            print(f"Running: {test_name}")
            print(f"{'='*70}")
            passed = await test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n✓ ALL INTEGRATION TESTS PASSED")
        print("="*70)
        return 0
    else:
        print(f"\n✗ {total_count - passed_count} INTEGRATION TEST(S) FAILED")
        print("="*70)
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
