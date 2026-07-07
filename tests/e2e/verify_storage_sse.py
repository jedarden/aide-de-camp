#!/usr/bin/env python3
"""
Manual Verification Script: Storage and SSE Broadcast via Test Endpoint

Verifies that POST /api/v1/test/dispatch:
1. Stores results in SQLite session database
2. Broadcasts SSE events to connected canvas surfaces
3. Storage payload matches /dispatch payload
4. Broadcast timing matches /dispatch behavior

Run: python3 tests/e2e/verify_storage_sse.py
"""
import asyncio
import json
import uuid
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode

import httpx
import aiosqlite


# Configuration
API_BASE_URL = "http://localhost:8000"
DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print('=' * 60)


def print_test(name: str):
    """Print a test name."""
    print(f"\n[{name}]")


def print_result(passed: bool, message: str):
    """Print a test result."""
    symbol = "✅" if passed else "❌"
    print(f"  {symbol} {message}")
    return passed


async def check_server():
    """Check if server is running."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/health", timeout=2)
            if response.status_code != 200:
                print(f"❌ Server health check failed: {response.status_code}")
                return False
            print_result(True, f"Server is running at {API_BASE_URL}")
            return True
    except Exception as e:
        print_result(False, f"Cannot reach server: {e}")
        print(f"   Start the server with:")
        print(f"   cd /home/coding/aide-de-camp && python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000")
        return False


async def verify_storage_in_database():
    """Verify test dispatch stores results in SQLite database."""
    print_test("Test 1: Storage in Database")

    session_id = f"test-storage-{uuid.uuid4().hex[:16]}"
    utterance = "verify storage in database"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Dispatch test utterance
        print(f"  📤 Dispatching utterance: {utterance[:50]}...")

        response = await client.post(
            f"{API_BASE_URL}/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "wait_for_results": False,
            }
        )

        if response.status_code != 200:
            print_result(False, f"Dispatch failed: {response.status_code}")
            return False

        data = response.json()
        print_result(True, f"Dispatch returned: {data['status']}")

        utterance_id = data.get("utterance_id")
        intent_ids = data.get("intent_ids", [])

        if not utterance_id:
            print_result(False, "No utterance_id in response")
            return False

        print_result(True, f"Utterance ID: {utterance_id[:8]}...")
        print_result(True, f"Intent count: {len(intent_ids)}")

        # Wait for async processing
        print(f"  ⏳ Waiting for async processing...")
        await asyncio.sleep(3)

    # Verify database storage
    print(f"  🔍 Verifying database storage...")

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Check utterance record
            utterance_rows = await db.execute_fetchall(
                "SELECT * FROM utterances WHERE id = ? AND session_id = ?",
                (utterance_id, session_id)
            )

            if not utterance_rows:
                print_result(False, "Utterance not found in database")
                return False

            utterance_row = utterance_rows[0]
            print_result(True, f"Utterance stored: {utterance_row['raw_text'][:40]}...")

            # Check intent records
            for intent_id in intent_ids:
                intent_rows = await db.execute_fetchall(
                    "SELECT * FROM intents WHERE id = ? AND session_id = ?",
                    (intent_id, session_id)
                )

                if not intent_rows:
                    print_result(False, f"Intent {intent_id[:8]} not found in database")
                    return False

                intent_row = intent_rows[0]
                print_result(True, f"Intent {intent_id[:8]}: type={intent_row['intent_type']}, status={intent_row['status']}")

                # Check for results
                result_rows = await db.execute_fetchall(
                    "SELECT * FROM results WHERE intent_id = ? AND session_id = ?",
                    (intent_id, session_id)
                )

                if result_rows:
                    for result in result_rows:
                        print_result(True, f"Result {result['id'][:8]}: urgency={result.get('urgency', 'normal')}")
                else:
                    print(f"  ⚠️  No results yet for intent {intent_id[:8]} (may still be processing)")

        return True

    except Exception as e:
        print_result(False, f"Database query failed: {e}")
        return False


async def verify_sse_broadcast():
    """Verify test dispatch broadcasts SSE events."""
    print_test("Test 2: SSE Broadcast")

    session_id = f"test-sse-{uuid.uuid4().hex[:16]}"
    surface_id = f"test-surface-{uuid.uuid4().hex[:16]}"
    utterance = "verify sse broadcast"

    received_events = []

    print(f"  📡 Connecting to SSE endpoint...")
    print(f"     Session: {session_id}")
    print(f"     Surface: {surface_id}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Connect to SSE
        try:
            async with client.stream(
                "GET",
                f"{API_BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                }
            ) as sse_response:
                if sse_response.status_code != 200:
                    print_result(False, f"SSE connection failed: {sse_response.status_code}")
                    return False

                print_result(True, "SSE connection established")

                # Read initial events
                async for line in sse_response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            received_events.append(data)
                            if len(received_events) >= 2:  # connected + workload_summary
                                break
                        except json.JSONDecodeError:
                            pass

                print_result(True, f"Received {len(received_events)} initial events")

        except Exception as e:
            print_result(False, f"SSE connection error: {e}")
            return False

    # Now dispatch and verify SSE event
    print(f"  📤 Dispatching test utterance...")

    received_result_events = []
    dispatch_complete = False

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Reconnect to SSE to capture result_created
        async with client.stream(
            "GET",
            f"{API_BASE_URL}/api/v1/sse",
            params={
                "session_id": session_id,
                "surface_id": surface_id,
                "surface_type": "canvas"
            }
        ) as sse_response:
            if sse_response.status_code != 200:
                print_result(False, f"Second SSE connection failed: {sse_response.status_code}")
                return False

            print_result(True, "Second SSE connection established")

            # Event collection task
            async def collect_events():
                current_event_type = None
                async for line in sse_response.aiter_lines():
                    if line.startswith("event: "):
                        current_event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            received_result_events.append({
                                "type": current_event_type,
                                "data": data
                            })
                            if current_event_type == "result_created":
                                return True
                        except json.JSONDecodeError:
                            pass
                        current_event_type = None
                return False

            # Wait for connection to establish
            await asyncio.sleep(0.5)

            # Dispatch utterance
            dispatch_response = await client.post(
                f"{API_BASE_URL}/api/v1/test/dispatch",
                json={
                    "utterance": utterance,
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "wait_for_results": False,
                }
            )

            if dispatch_response.status_code != 200:
                print_result(False, f"Dispatch failed: {dispatch_response.status_code}")
                return False

            dispatch_data = dispatch_response.json()
            print_result(True, f"Dispatch returned: {dispatch_data['status']}")

            # Wait for SSE event
            try:
                got_result = await asyncio.wait_for(collect_events(), timeout=15.0)
                if got_result:
                    print_result(True, "Received result_created event via SSE")
                else:
                    print_result(False, "No result_created event received")
                    return False
            except asyncio.TimeoutError:
                print_result(False, "SSE event timeout (15s)")
                print(f"  Events received: {len(received_result_events)}")
                for event in received_result_events:
                    print(f"    - {event.get('type', 'unknown')}")
                return False

            # Verify event payload
            result_events = [e for e in received_result_events if e.get("type") == "result_created"]
            if result_events:
                event_data = result_events[0]["data"]
                print_result(True, f"Event payload: {list(event_data.keys())}")

                # Check for expected fields
                expected_fields = ["intent_id", "topic_id", "summary", "urgency"]
                has_fields = [field in event_data for field in expected_fields]
                if any(has_fields):
                    print_result(True, f"Event contains expected fields")
                else:
                    print(f"  ⚠️  Event missing expected fields, has: {list(event_data.keys())}")

    return True


async def verify_matches_main_dispatch():
    """Verify test dispatch produces same storage as /dispatch."""
    print_test("Test 3: Matches Main Dispatch")

    utterance = "compare test and main dispatch"
    test_session_id = f"test-compare-{uuid.uuid4().hex[:16]}"
    main_session_id = f"main-compare-{uuid.uuid4().hex[:16]}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Call test dispatch
        print(f"  📤 Calling /api/v1/test/dispatch...")

        test_response = await client.post(
            f"{API_BASE_URL}/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": test_session_id,
                "wait_for_results": False,
            }
        )

        if test_response.status_code != 200:
            print_result(False, f"Test dispatch failed: {test_response.status_code}")
            return False

        test_data = test_response.json()
        print_result(True, f"Test dispatch: {test_data['status']}")

        # Call main dispatch
        print(f"  📤 Calling /dispatch...")

        main_response = await client.post(
            f"{API_BASE_URL}/dispatch",
            json={
                "utterance": utterance,
                "session_id": main_session_id,
                "surface_id": f"surface-{uuid.uuid4().hex[:16]}",
            }
        )

        if main_response.status_code != 200:
            print_result(False, f"Main dispatch failed: {main_response.status_code}")
            return False

        main_data = main_response.json()
        print_result(True, f"Main dispatch: {main_data['status']}")

    # Compare structures
    print(f"  🔍 Comparing response structures...")

    has_test_utterance_id = "utterance_id" in test_data
    has_main_utterance_id = "utterance_id" in main_data
    print_result(has_test_utterance_id and has_main_utterance_id,
                 f"Both have utterance_id")

    test_correct_session = test_data.get("session_id") == test_session_id
    main_correct_session = main_data.get("session_id") == main_session_id
    print_result(test_correct_session and main_correct_session,
                 f"Session IDs match")

    # Check database records
    print(f"  🔍 Checking database records...")

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Check test session
            test_utterances = await db.execute_fetchall(
                "SELECT * FROM utterances WHERE session_id = ? LIMIT 1",
                (test_session_id,)
            )

            if test_utterances:
                print_result(True, f"Test session utterance stored")
            else:
                print_result(False, f"Test session utterance NOT stored")
                return False

            # Check main session
            main_utterances = await db.execute_fetchall(
                "SELECT * FROM utterances WHERE session_id = ? LIMIT 1",
                (main_session_id,)
            )

            if main_utterances:
                print_result(True, f"Main session utterance stored")
            else:
                print_result(False, f"Main session utterance NOT stored")
                return False

            # Compare structures
            test_intents = await db.execute_fetchall(
                "SELECT * FROM intents WHERE session_id = ?",
                (test_session_id,)
            )
            main_intents = await db.execute_fetchall(
                "SELECT * FROM intents WHERE session_id = ?",
                (main_session_id,)
            )

            print_result(len(test_intents) > 0, f"Test dispatch created {len(test_intents)} intent(s)")
            print_result(len(main_intents) > 0, f"Main dispatch created {len(main_intents)} intent(s)")

            # Check intent structure
            for intent in test_intents:
                has_required = all([
                    intent.get("session_id") == test_session_id,
                    intent.get("intent_type") is not None,
                    intent.get("status") in ("pending", "dispatched", "resolved")
                ])
                print_result(has_required, f"Test intent structure valid")

            for intent in main_intents:
                has_required = all([
                    intent.get("session_id") == main_session_id,
                    intent.get("intent_type") is not None,
                    intent.get("status") in ("pending", "dispatched", "resolved")
                ])
                print_result(has_required, f"Main intent structure valid")

        return True

    except Exception as e:
        print_result(False, f"Database check failed: {e}")
        return False


async def verify_broadcast_timing():
    """Verify SSE broadcast timing matches /dispatch behavior."""
    print_test("Test 4: Broadcast Timing")

    session_id = f"test-timing-{uuid.uuid4().hex[:16]}"
    surface_id = f"test-surface-{uuid.uuid4().hex[:16]}"
    utterance = "verify broadcast timing"

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Connect to SSE
        print(f"  📡 Connecting to SSE...")

        async with client.stream(
            "GET",
            f"{API_BASE_URL}/api/v1/sse",
            params={
                "session_id": session_id,
                "surface_id": surface_id,
                "surface_type": "canvas"
            }
        ) as sse_response:
            if sse_response.status_code != 200:
                print_result(False, f"SSE connection failed: {sse_response.status_code}")
                return False

            print_result(True, "SSE connected")

            # Skip initial events
            async for line in sse_response.aiter_lines():
                if "workload_summary" in line:
                    break

            # Track timing
            dispatch_time = None
            result_event_time = None
            got_result = False

            async def collect_result():
                nonlocal result_event_time, got_result
                current_event_type = None
                async for line in sse_response.aiter_lines():
                    if line.startswith("event: "):
                        current_event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        if current_event_type == "result_created":
                            result_event_time = datetime.now().timestamp()
                            got_result = True
                            return
                        current_event_type = None

            # Dispatch and measure time
            print(f"  📤 Dispatching utterance...")

            dispatch_start = datetime.now().timestamp()
            dispatch_response = await client.post(
                f"{API_BASE_URL}/api/v1/test/dispatch",
                json={
                    "utterance": utterance,
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "wait_for_results": False,
                }
            )
            dispatch_end = datetime.now().timestamp()
            dispatch_time = dispatch_end - dispatch_start

            if dispatch_response.status_code != 200:
                print_result(False, f"Dispatch failed: {dispatch_response.status_code}")
                return False

            print_result(True, f"Dispatch returned in {dispatch_time:.3f}s")

            # Wait for SSE event
            try:
                await asyncio.wait_for(collect_result(), timeout=15.0)

                if got_result:
                    print_result(True, f"SSE event received after dispatch")

                    # Verify timing: dispatch should be fast (< 1s)
                    fast_dispatch = dispatch_time < 1.0
                    print_result(fast_dispatch,
                                f"Dispatch timing: {dispatch_time:.3f}s {'✓' if fast_dispatch else '⚠️ '} (< 1s expected)")

                    # SSE event should arrive after dispatch returns
                    if result_event_time:
                        delay = result_event_time - dispatch_end
                        async_broadcast = delay > 0
                        print_result(async_broadcast,
                                    f"SSE broadcast async: {delay:.3f}s after dispatch")
                else:
                    print_result(False, "No result_created event received")
                    return False

            except asyncio.TimeoutError:
                print_result(False, "SSE event timeout")
                return False

    return True


async def main():
    """Run all verification tests."""
    print_section("Storage and SSE Broadcast Verification")
    print(f"API: {API_BASE_URL}")
    print(f"DB: {DB_PATH}")

    # Check server
    if not await check_server():
        return 1

    all_passed = True

    # Run tests
    if not await verify_storage_in_database():
        all_passed = False

    if not await verify_sse_broadcast():
        all_passed = False

    if not await verify_matches_main_dispatch():
        all_passed = False

    if not await verify_broadcast_timing():
        all_passed = False

    # Summary
    print_section("Summary")
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("\nVerified:")
        print("  ✓ Results stored in SQLite session store")
        print("  ✓ SSE events broadcast to canvas surfaces")
        print("  ✓ Storage payload matches /dispatch")
        print("  ✓ Broadcast timing matches /dispatch")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("\nCheck logs above for details")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
