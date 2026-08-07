#!/usr/bin/env .venv/bin/python
"""
Storage and SSE Broadcast Verification for Test Endpoint (bead: adc-3mc5)

Verifies that results from the test endpoint are correctly stored in the
session database and broadcast via SSE to connected canvas surfaces.

Acceptance Criteria:
1. Result stored in data/session.db
2. SSE event with type='result_created' broadcast
3. Canvas receives event at surface_id
4. Storage payload matches /dispatch payload
"""
import asyncio
import json
import uuid
import sqlite3
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from src.main import app
from src.sse.broadcaster import get_broadcaster, SSEEvent, EventType
from src.session.store import get_store


def verify_database_storage(result_id: str, session_id: str, intent_id: str, topic_id: str) -> dict:
    """Verify that data is correctly stored in the database."""
    db_path = Path("/home/coding/aide-de-camp/data/session.db")

    if not db_path.exists():
        return {"stored": False, "reason": "Database file does not exist"}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check result record
        cursor.execute(
            "SELECT id, intent_id, topic_id, session_id, result_type, summary FROM results WHERE id = ?",
            (result_id,)
        )
        result = cursor.fetchone()

        if not result:
            conn.close()
            return {"stored": False, "reason": "Result not found in database"}

        # Verify foreign keys exist
        cursor.execute("SELECT id FROM intents WHERE id = ?", (intent_id,))
        intent_exists = cursor.fetchone() is not None

        cursor.execute("SELECT id FROM topics WHERE id = ?", (topic_id,))
        topic_exists = cursor.fetchone() is not None

        cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        session_exists = cursor.fetchone() is not None

        conn.close()

        return {
            "stored": True,
            "result_exists": True,
            "intent_exists": intent_exists,
            "topic_exists": topic_exists,
            "session_exists": session_exists,
            "result_type": result[4],
            "summary": result[5]
        }

    except Exception as e:
        return {"stored": False, "reason": f"Database error: {e}"}


async def verify_sse_broadcast_and_storage():
    """Main verification test for storage and SSE broadcast."""
    print("\n" + "="*70)
    print("Storage and SSE Broadcast Verification Test")
    print("Bead: adc-3mc5")
    print("="*70)

    # Generate test IDs
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())
    test_utterance = "Storage and SSE broadcast verification test"

    print(f"\nTest Configuration:")
    print(f"  Session ID: {session_id[:8]}...")
    print(f"  Surface ID: {surface_id[:8]}...")
    print(f"  Utterance: {test_utterance}")

    # Initialize broadcaster
    broadcaster = get_broadcaster()
    await broadcaster.start()
    print(f"\n✓ Initialized SSE broadcaster")

    # Register SSE listener
    test_connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )
    print(f"✓ Registered SSE connection for surface {surface_id[:8]}...")

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
                        print(f"  ✓ Collected event: {event.event_type}")
                        if event.event_type == EventType.RESULT_CREATED:
                            break
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

    # Extract IDs from response
    stored_ids = response_data.get("stored", {})
    result_id = stored_ids.get("result_id")
    intent_id = stored_ids.get("intent_id")
    topic_id = stored_ids.get("topic_id")

    print(f"\n2. Stored IDs:")
    print(f"  result_id: {result_id[:8]}...")
    print(f"  intent_id: {intent_id[:8]}...")
    print(f"  topic_id: {topic_id[:8]}...")

    # Collect SSE events
    print(f"\n3. Collecting SSE events...")
    await collect_events()

    # Verify acceptance criteria
    print(f"\n" + "="*70)
    print("ACCEPTANCE CRITERIA VERIFICATION")
    print("="*70)

    all_passed = True
    results = {}

    # Criterion 1: Result stored in data/session.db
    print(f"\n[1] Result stored in data/session.db")
    db_verification = verify_database_storage(result_id, session_id, intent_id, topic_id)

    if db_verification.get("stored"):
        print(f"  ✓ PASS: Result stored in database")
        print(f"    Result exists: {db_verification.get('result_exists')}")
        print(f"    Intent exists: {db_verification.get('intent_exists')}")
        print(f"    Topic exists: {db_verification.get('topic_exists')}")
        print(f"    Session exists: {db_verification.get('session_exists')}")
        print(f"    Result type: {db_verification.get('result_type')}")
        results["criterion_1"] = True
    else:
        print(f"  ✗ FAIL: {db_verification.get('reason')}")
        all_passed = False
        results["criterion_1"] = False

    # Criterion 2: SSE event with type='result_created' broadcast
    print(f"\n[2] SSE event with type='result_created' broadcast")
    result_created_events = [e for e in events_received if e.event_type == EventType.RESULT_CREATED]

    if result_created_events:
        print(f"  ✓ PASS: SSE event with type='result_created' broadcast")
        print(f"    Event count: {len(result_created_events)}")
        results["criterion_2"] = True
    else:
        print(f"  ✗ FAIL: No result_created events found")
        print(f"    Events received: {[e.event_type for e in events_received]}")
        all_passed = False
        results["criterion_2"] = False

    # Criterion 3: Canvas receives event at surface_id
    print(f"\n[3] Canvas receives event at surface_id")

    if result_created_events:
        event = result_created_events[0]
        target_matches = event.target_surface_id == surface_id
        connection_matches = test_connection.surface_id == surface_id

        print(f"  Event target_surface_id: {event.target_surface_id[:8]}...")
        print(f"  Connection surface_id: {test_connection.surface_id[:8]}...")
        print(f"  Target matches: {target_matches}")

        if target_matches and connection_matches:
            print(f"  ✓ PASS: Canvas received event at correct surface_id")
            results["criterion_3"] = True
        else:
            print(f"  ✗ FAIL: Surface ID mismatch")
            all_passed = False
            results["criterion_3"] = False
    else:
        print(f"  ✗ FAIL: No event received")
        all_passed = False
        results["criterion_3"] = False

    # Criterion 4: Storage payload matches /dispatch payload
    print(f"\n[4] Storage payload matches /dispatch payload")

    # Check response structure
    has_required_fields = all(key in response_data for key in [
        "status", "stored", "verification"
    ])

    stored_fields = all(key in stored_ids for key in [
        "utterance_id", "intent_id", "topic_id", "result_id", "session_id"
    ])

    verification = response_data.get("verification", {})
    has_storage_match = verification.get("storage_match", False)
    has_payload_match = verification.get("payload_match", False)

    print(f"  Response has required fields: {has_required_fields}")
    print(f"  Stored has all ID fields: {stored_fields}")
    print(f"  Storage match: {has_storage_match}")
    print(f"  Payload match: {has_payload_match}")

    if has_required_fields and stored_fields and has_storage_match and has_payload_match:
        print(f"  ✓ PASS: Storage payload matches /dispatch structure")
        results["criterion_4"] = True
    else:
        print(f"  ✗ FAIL: Storage payload does not match /dispatch structure")
        all_passed = False
        results["criterion_4"] = False

    # Cleanup
    broadcaster.unregister(test_connection.connection_id)
    await broadcaster.stop()
    print(f"\n✓ Stopped SSE broadcaster")

    # Final result
    print(f"\n" + "="*70)
    if all_passed:
        print("✓ ALL ACCEPTANCE CRITERIA PASSED")
        print("="*70)
        return True
    else:
        print("✗ SOME ACCEPTANCE CRITERIA FAILED")
        print("="*70)
        return False


async def main():
    """Run the verification test."""
    try:
        passed = await verify_sse_broadcast_and_storage()
        return 0 if passed else 1
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
