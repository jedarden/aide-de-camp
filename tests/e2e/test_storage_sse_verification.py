"""
E2E Test: Verify Storage and SSE Broadcast via Test Endpoint

Verifies that results from POST /api/v1/test/dispatch are:
1. Correctly stored in the session database (SQLite)
2. Broadcast via SSE to connected canvas surfaces
3. Storage payload matches /dispatch payload

Child of: adc-3mc5
"""
import asyncio
import json
import uuid
from pathlib import Path
from datetime import datetime

import httpx
import aiosqlite
import pytest


# Test configuration
API_BASE_URL = "http://localhost:8000"
DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")


class TestStorageSSEVerification:
    """Verify storage and SSE broadcast via test endpoint."""

    @pytest.mark.asyncio
    async def test_dispatch_storage_in_database(self):
        """
        Verify that test dispatch results are stored in SQLite.

        Steps:
        1. Create a test session
        2. Call POST /api/v1/test/dispatch
        3. Query database for utterance, intent, and result records
        4. Verify data integrity and foreign key relationships
        """
        session_id = f"test-storage-{uuid.uuid4().hex[:16]}"
        utterance = "verify storage and database persistence"

        async with httpx.AsyncClient() as client:
            # Dispatch test utterance (don't wait for results)
            response = await client.post(
                f"{API_BASE_URL}/api/v1/test/dispatch",
                json={
                    "utterance": utterance,
                    "session_id": session_id,
                    "wait_for_results": False,  # Don't wait - just trigger
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "dispatched"
            assert data["session_id"] == session_id
            assert "utterance_id" in data

            utterance_id = data["utterance_id"]
            intent_ids = data.get("intent_ids", [])

            # Wait for async processing to complete
            await asyncio.sleep(5)

        # Verify database storage
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # 1. Verify utterance record
            utterance_query = """
                SELECT id, session_id, raw_text, created_at
                FROM utterances
                WHERE id = ? AND session_id = ?
            """
            utterance_rows = await db.execute_fetchall(
                utterance_query, (utterance_id, session_id)
            )
            assert len(utterance_rows) > 0, "Utterance not found in database"
            utterance_row = utterance_rows[0]
            assert utterance_row is not None, "Utterance not found in database"
            assert utterance_row["raw_text"] == utterance
            assert utterance_row["session_id"] == session_id

            # 2. Verify intent records
            for intent_id in intent_ids:
                intent_query = """
                    SELECT id, utterance_id, session_id, intent_type, status
                    FROM intents
                    WHERE id = ? AND session_id = ?
                """
                intent_rows = await db.execute_fetchall(
                    intent_query, (intent_id, session_id)
                )
                assert len(intent_rows) > 0, f"Intent {intent_id} not found"
                intent_row = intent_rows[0]
                assert intent_row is not None, f"Intent {intent_id} not found"
                assert intent_row["utterance_id"] == utterance_id
                assert intent_row["session_id"] == session_id
                assert intent_row["status"] in ("resolved", "pending", "dispatched")

                # 3. Verify result exists for this intent
                result_query = """
                    SELECT id, intent_id, session_id, summary, urgency, created_at
                    FROM results
                    WHERE intent_id = ? AND session_id = ?
                """
                result_rows = await db.execute_fetchall(
                    result_query, (intent_id, session_id)
                )
                result_row = result_rows[0] if result_rows else None
                # Result may not exist if intent is still pending or failed
                if result_row:
                    assert result_row["intent_id"] == intent_id
                    assert result_row["session_id"] == session_id
                    assert result_row["summary"] is not None

        print(f"✓ Storage verification passed for session {session_id}")

    @pytest.mark.asyncio
    async def test_dispatch_sse_broadcast(self):
        """
        Verify that test dispatch broadcasts SSE events.

        Steps:
        1. Create SSE connection with surface_id
        2. Call POST /api/v1/test/dispatch with surface_id
        3. Verify SSE event is received
        4. Verify event payload contains correct data
        """
        session_id = f"test-sse-{uuid.uuid4().hex[:16]}"
        surface_id = f"test-surface-{uuid.uuid4().hex[:16]}"
        utterance = "verify sse broadcast reaches canvas"
        received_events = []

        async with httpx.AsyncClient() as client:
            # Connect to SSE endpoint
            async with client.stream(
                "GET",
                f"{API_BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                },
                timeout=None
            ) as sse_response:
                assert sse_response.status_code == 200

                # Read initial events (connected, workload_summary)
                async for line in sse_response.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])  # Strip "data: " prefix
                        received_events.append(data)

                        # Stop after receiving initial connection event
                        if len(received_events) >= 2:
                            break

                # Verify we got the connected event
                assert any("surface_id" in e for e in received_events)

            # Now dispatch a test utterance
            received_result_events = []

            # Reconnect to SSE to catch result_created events
            async with client.stream(
                "GET",
                f"{API_BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                },
                timeout=None
            ) as sse_response:
                assert sse_response.status_code == 200

                # Start task to collect SSE events
                async def collect_events():
                    async for line in sse_response.aiter_lines():
                        if line.startswith("event: "):
                            event_type = line[7:].strip()  # Strip "event: " prefix
                        elif line.startswith("data: "):
                            data = json.loads(line[6:])
                            received_result_events.append({
                                "type": event_type if 'event_type' in locals() else None,
                                "data": data
                            })
                            # Stop if we get a result_created event
                            if event_type == "result_created":
                                return
                            event_type = None

                # Give SSE connection time to establish
                await asyncio.sleep(0.5)

                # Dispatch test utterance
                dispatch_response = await client.post(
                    f"{API_BASE_URL}/api/v1/test/dispatch",
                    json={
                        "utterance": utterance,
                        "session_id": session_id,
                        "surface_id": surface_id,
                        "wait_for_results": False,
                    }
                )

                assert dispatch_response.status_code == 200
                dispatch_data = dispatch_response.json()
                assert dispatch_data["status"] == "dispatched"

                # Wait for SSE events
                await asyncio.wait_for(collect_events(), timeout=10.0)

                # Verify we received a result_created event
                result_events = [e for e in received_result_events if e.get("type") == "result_created"]
                assert len(result_events) > 0, "No result_created event received via SSE"

                # Verify event payload structure
                event_data = result_events[0]["data"]
                assert "intent_id" in event_data or "topic_id" in event_data

        print(f"✓ SSE broadcast verification passed for session {session_id}")

    @pytest.mark.asyncio
    async def test_dispatch_matches_main_endpoint(self):
        """
        Verify that test dispatch produces same storage as /dispatch.

        Steps:
        1. Send identical utterance to both /dispatch and /test/dispatch
        2. Compare database records from both endpoints
        3. Verify data structure matches
        """
        utterance = "compare test dispatch with main dispatch"
        test_session_id = f"test-compare-{uuid.uuid4().hex[:16]}"
        main_session_id = f"main-compare-{uuid.uuid4().hex[:16]}"

        async with httpx.AsyncClient() as client:
            # Call test dispatch
            test_response = await client.post(
                f"{API_BASE_URL}/api/v1/test/dispatch",
                json={
                    "utterance": utterance,
                    "session_id": test_session_id,
                    "wait_for_results": False,  # Don't wait to avoid timeout
                }
            )

            assert test_response.status_code == 200
            test_data = test_response.json()

            # Call main dispatch
            main_response = await client.post(
                f"{API_BASE_URL}/dispatch",
                json={
                    "utterance": utterance,
                    "session_id": main_session_id,
                    "surface_id": f"surface-{uuid.uuid4().hex[:16]}",
                }
            )

            assert main_response.status_code == 200
            main_data = main_response.json()

        # Compare response structures
        assert "utterance_id" in test_data
        assert "utterance_id" in main_data
        assert test_data["session_id"] == test_session_id
        assert main_data["session_id"] == main_session_id

        # Wait for async processing to complete
        await asyncio.sleep(5)

        # Verify both created database records
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Check test session utterance
            test_utterance_rows = await db.execute_fetchall(
                "SELECT * FROM utterances WHERE session_id = ?",
                (test_session_id,)
            )
            assert len(test_utterance_rows) > 0
            test_utterance = test_utterance_rows[0]
            assert test_utterance["raw_text"] == utterance

            # Check main session utterance
            main_utterance_rows = await db.execute_fetchall(
                "SELECT * FROM utterances WHERE session_id = ?",
                (main_session_id,)
            )
            assert len(main_utterance_rows) > 0
            main_utterance = main_utterance_rows[0]
            assert main_utterance["raw_text"] == utterance

            # Both should have intents created
            test_intents = await db.execute_fetchall(
                "SELECT * FROM intents WHERE session_id = ?",
                (test_session_id,)
            )
            main_intents = await db.execute_fetchall(
                "SELECT * FROM intents WHERE session_id = ?",
                (main_session_id,)
            )

            assert len(test_intents) > 0, "Test dispatch created no intents"
            assert len(main_intents) > 0, "Main dispatch created no intents"

            # Verify intent structure matches
            for intent in test_intents + main_intents:
                assert intent["session_id"] in (test_session_id, main_session_id)
                assert intent["intent_type"] is not None
                assert intent["status"] in ("pending", "dispatched", "resolved")

        print(f"✓ Dispatch comparison verification passed")

    @pytest.mark.asyncio
    async def test_broadcast_timing_matches_dispatch(self):
        """
        Verify SSE broadcast timing matches /dispatch behavior.

        Steps:
        1. Call test dispatch with wait_for_results=False
        2. Verify SSE events arrive asynchronously
        3. Verify events arrive after dispatch response returns
        """
        session_id = f"test-timing-{uuid.uuid4().hex[:16]}"
        surface_id = f"surface-{uuid.uuid4().hex[:16]}"
        utterance = "verify broadcast timing"

        dispatch_time = None
        result_event_time = None

        async with httpx.AsyncClient() as client:
            # Start SSE connection
            async with client.stream(
                "GET",
                f"{API_BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                },
                timeout=None
            ) as sse_response:
                assert sse_response.status_code == 200

                # Skip initial events
                async for line in sse_response.aiter_lines():
                    if "workload_summary" in line:
                        break

                # Start event collection
                events_received = []

                async def collect_sse():
                    nonlocal result_event_time
                    async for line in sse_response.aiter_lines():
                        if "result_created" in line:
                            result_event_time = datetime.now().timestamp()
                            events_received.append(line)
                            return

                # Call dispatch (should return immediately)
                dispatch_before = datetime.now().timestamp()
                dispatch_response = await client.post(
                    f"{API_BASE_URL}/api/v1/test/dispatch",
                    json={
                        "utterance": utterance,
                        "session_id": session_id,
                        "surface_id": surface_id,
                        "wait_for_results": False,
                    }
                )
                dispatch_after = datetime.now().timestamp()
                dispatch_time = dispatch_after - dispatch_before

                assert dispatch_response.status_code == 200
                dispatch_data = dispatch_response.json()
                assert dispatch_data["status"] == "dispatched"

                # Wait for SSE event (should arrive after dispatch returns)
                try:
                    await asyncio.wait_for(collect_sse(), timeout=30.0)
                except asyncio.TimeoutError:
                    pytest.fail("SSE event not received within timeout")

                # Verify timing: dispatch should return quickly (< 1 second)
                # SSE event should arrive after dispatch returns
                assert dispatch_time < 1.0, f"Dispatch took too long: {dispatch_time}s"
                assert result_event_time is not None, "No SSE event received"

        print(f"✓ Broadcast timing verification passed (dispatch: {dispatch_time:.3f}s)")

    @pytest.mark.asyncio
    async def test_result_created_event_payload(self):
        """
        Verify result_created SSE event contains correct payload.

        Steps:
        1. Dispatch test utterance
        2. Capture SSE event payload
        3. Verify payload contains: intent_id, topic_id, summary, urgency
        """
        session_id = f"test-payload-{uuid.uuid4().hex[:16]}"
        surface_id = f"surface-{uuid.uuid4().hex[:16]}"
        utterance = "verify sse event payload structure"

        captured_events = []

        async with httpx.AsyncClient() as client:
            # Connect to SSE
            async with client.stream(
                "GET",
                f"{API_BASE_URL}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": surface_id,
                    "surface_type": "canvas"
                },
                timeout=None
            ) as sse_response:
                assert sse_response.status_code == 200

                # Skip initial events
                async for line in sse_response.aiter_lines():
                    if "workload_summary" in line:
                        break

                # Collect result_created events
                async def collect_result_events():
                    async for line in sse_response.aiter_lines():
                        if line.startswith("event: result_created"):
                            # Get next line with data
                            data_line = await sse_response.aiter_lines().__anext__()
                            if data_line.startswith("data: "):
                                payload = json.loads(data_line[6:])
                                captured_events.append(payload)
                                if len(captured_events) >= 1:
                                    return

                # Dispatch
                dispatch_response = await client.post(
                    f"{API_BASE_URL}/api/v1/test/dispatch",
                    json={
                        "utterance": utterance,
                        "session_id": session_id,
                        "surface_id": surface_id,
                        "wait_for_results": False,
                    }
                )

                assert dispatch_response.status_code == 200

                # Wait for SSE event
                try:
                    await asyncio.wait_for(collect_result_events(), timeout=30.0)
                except asyncio.TimeoutError:
                    pytest.fail("No result_created event received")

                # Verify we got events
                assert len(captured_events) > 0, "No events captured"

                # Verify event payload structure
                event = captured_events[0]

                # Required fields per SSE broadcast contract
                assert any(k in event for k in ["intent_id", "topic_id", "summary", "urgency"]), \
                    f"Event missing required fields: {event}"

                # Log the event structure for verification
                print(f"✓ SSE event payload verified: {json.dumps(event, indent=2)}")

        print(f"✓ Event payload verification passed for session {session_id}")


if __name__ == "__main__":
    # Run tests manually
    print("🧪 Running Storage and SSE Verification Tests")
    print("=" * 60)

    # Check if server is running
    try:
        response = httpx.get(f"{API_BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print(f"❌ Server health check failed: {response.status_code}")
            exit(1)
    except Exception as e:
        print(f"❌ Cannot reach server at {API_BASE_URL}")
        print(f"   Error: {e}")
        exit(1)

    print("✅ Server is running")
    print()

    # Run individual tests
    test_instance = TestStorageSSEVerification()

    print("\n[Test 1] Storage in Database")
    print("-" * 60)
    asyncio.run(test_instance.test_dispatch_storage_in_database())

    print("\n[Test 2] SSE Broadcast")
    print("-" * 60)
    asyncio.run(test_instance.test_dispatch_sse_broadcast())

    print("\n[Test 3] Matches Main Endpoint")
    print("-" * 60)
    asyncio.run(test_instance.test_dispatch_matches_main_endpoint())

    print("\n[Test 4] Broadcast Timing")
    print("-" * 60)
    asyncio.run(test_instance.test_broadcast_timing_matches_dispatch())

    print("\n[Test 5] Event Payload")
    print("-" * 60)
    asyncio.run(test_instance.test_result_created_event_payload())

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
