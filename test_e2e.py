#!/usr/bin/env python3
"""
ADC Text Path E2E Test

Tests the complete flow: utterance -> POST /dispatch -> intent router -> fetch+synthesize -> SSE -> canvas card
"""
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import aiosqlite


# Test configuration
SERVER_URL = "http://localhost:8000"
TEST_UTTERANCE = "what is the status of aide-de-camp"
TIMEOUT_SECONDS = 60


async def test_e2e_text_path():
    """Test the complete text path with SSE monitoring."""

    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())
    utterance_id = None
    result_received = False
    result_data = None

    print(f"🚀 Starting E2E test for text path")
    print(f"Session ID: {session_id}")
    print(f"Surface ID: {surface_id}")
    print(f"Test utterance: '{TEST_UTTERANCE}'")
    print("-" * 60)

    # Step 1: Register surface and open SSE connection
    print("\n📡 Step 1: Opening SSE connection...")

    sse_events = []

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "GET",
            f"{SERVER_URL}/api/v1/sse",
            params={"session_id": session_id, "surface_id": surface_id},
            timeout=35.0
        ) as response:
            response.raise_for_status()

            print("✅ SSE connection opened")

            # Step 2: Dispatch the utterance
            print("\n📤 Step 2: Dispatching utterance...")

            # Start a background task to collect SSE events
            async def collect_sse_events():
                nonlocal result_received, result_data
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            event = json.loads(data_str)
                            sse_events.append(event)
                            print(f"  📨 SSE event: {event.get('event_type')}")

                            # Check for result_created
                            if event.get("event_type") == "result_created":
                                result_received = True
                                result_data = event.get("data", {})
                                print(f"  ✅ Result received!")
                        except json.JSONDecodeError as e:
                            print(f"  ⚠️  Failed to parse SSE event: {e}")

            # Dispatch request
            dispatch_response = await client.post(
                f"{SERVER_URL}/dispatch",
                json={
                    "utterance": TEST_UTTERANCE,
                    "session_id": session_id,
                    "surface_id": surface_id,
                },
                timeout=15.0
            )

            dispatch_response.raise_for_status()
            dispatch_data = dispatch_response.json()
            utterance_id = dispatch_data.get("utterance_id")

            print(f"✅ Dispatch successful: utterance_id={utterance_id[:8] if utterance_id else 'unknown'}...")

            # Step 3: Wait for result with timeout
            print(f"\n⏳ Step 3: Waiting for result (timeout {TIMEOUT_SECONDS}s)...")

            start_time = time.time()
            while time.time() - start_time < TIMEOUT_SECONDS:
                await asyncio.sleep(0.5)
                if result_received:
                    break

            elapsed = time.time() - start_time

    # Step 4: Validate results
    print(f"\n📊 Step 4: Validating results (elapsed: {elapsed:.1f}s)")

    success = True

    if not result_received:
        print(f"❌ FAIL: No result_received event within {TIMEOUT_SECONDS}s")
        success = False
    else:
        print(f"✅ PASS: Result received in {elapsed:.1f}s")

        # Check result structure
        if result_data:
            summary = result_data.get("summary", "")
            data = result_data.get("data", {})

            if summary:
                print(f"✅ PASS: Result has non-empty summary: '{summary[:50]}...'")
            else:
                print(f"❌ FAIL: Result has empty summary")
                success = False

            if data:
                print(f"✅ PASS: Result has non-empty data field")
            else:
                print(f"❌ FAIL: Result has empty data field")
                success = False
        else:
            print(f"❌ FAIL: Result data is None")
            success = False

    # Step 5: Check session store
    print(f"\n💾 Step 5: Checking session store...")

    db_path = Path("data/session.db")
    if not db_path.exists():
        print(f"❌ FAIL: Session database not found at {db_path}")
        success = False
    else:
        async with aiosqlite.connect(db_path) as db:
            # Check intents table
            cursor = await db.execute(
                "SELECT id, intent_type, status FROM intents WHERE utterance_id = ?",
                (utterance_id,) if utterance_id else (None,)
            )
            intent_row = await cursor.fetchone()

            if intent_row:
                intent_id, intent_type, status = intent_row
                print(f"✅ PASS: Intent row found (id={intent_id[:8] if intent_id else 'unknown'}..., intent_type={intent_type}, status={status})")

                if status == "resolved":
                    print(f"✅ PASS: Intent status is 'resolved'")
                else:
                    print(f"⚠️  WARNING: Intent status is '{status}', expected 'resolved'")
            else:
                print(f"❌ FAIL: No intent row found for utterance_id={utterance_id[:8] if utterance_id else 'unknown'}...")
                success = False

            # Check results table
            cursor = await db.execute(
                "SELECT id, summary, data FROM results WHERE utterance_id = ? ORDER BY created DESC LIMIT 1",
                (utterance_id,) if utterance_id else (None,)
            )
            result_row = await cursor.fetchone()

            if result_row:
                result_id, summary, data_json = result_row
                print(f"✅ PASS: Result row found (id={result_id[:8] if result_id else 'unknown'}...)")

                if summary:
                    print(f"✅ PASS: Result summary in DB: '{summary[:50]}...'")
                else:
                    print(f"⚠️  WARNING: Result summary in DB is empty")

                if data_json:
                    try:
                        data_obj = json.loads(data_json)
                        print(f"✅ PASS: Result data in DB is valid JSON with {len(data_obj)} keys")
                    except json.JSONDecodeError:
                        print(f"❌ FAIL: Result data in DB is not valid JSON")
                        success = False
                else:
                    print(f"⚠️  WARNING: Result data in DB is empty")
            else:
                print(f"❌ FAIL: No result row found in database")
                success = False

    # Final summary
    print("\n" + "=" * 60)
    if success:
        print("🎉 E2E TEST PASSED")
        print("=" * 60)
        print("✅ All validations passed")
        return 0
    else:
        print("⚠️  E2E TEST FAILED")
        print("=" * 60)
        print("❌ Some validations failed - see details above")
        return 1


async def main():
    """Main entry point."""
    try:
        exit_code = await test_e2e_text_path()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
