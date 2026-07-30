#!/usr/bin/env python3
"""Test script to verify router timing breakdown logging and storage."""

import asyncio
import httpx
import json
import sqlite3
import sys
from pathlib import Path

# Test configuration
API_URL = "http://localhost:8000"
DB_PATH = Path("/home/coding/aide-de-camp/data/session.db")
TEST_UTTERANCE = "What's the status of pbx-web?"


async def test_timing_breakdown():
    """Test that timing breakdown is logged and stored."""

    print("=" * 60)
    print("Testing Router Timing Breakdown")
    print("=" * 60)

    # Create a new session
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Create a new session
        print("\n1. Creating test session...")
        response = await client.post(
            f"{API_URL}/api/v1/sessions",
            json={}
        )
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"   ✓ Session created: {session_id[:8]}...")

        # Step 2: Create a surface
        print("\n2. Creating surface...")
        surface_response = await client.post(
            f"{API_URL}/api/v1/sessions/{session_id}/surfaces",
            json={"type": "canvas"}
        )
        surface_data = surface_response.json()
        surface_id = surface_data["surface_id"]
        print(f"   ✓ Surface created: {surface_id[:8]}...")

        # Step 3: Send test utterance
        print(f"\n3. Sending test utterance: '{TEST_UTTERANCE}'")
        dispatch_start = asyncio.get_event_loop().time()

        dispatch_response = await client.post(
            f"{API_URL}/dispatch",
            json={
                "utterance": TEST_UTTERANCE,
                "session_id": session_id,
                "surface_id": surface_id
            }
        )

        dispatch_ms = (asyncio.get_event_loop().time() - dispatch_start) * 1000
        print(f"   ✓ Dispatch completed in {dispatch_ms:.0f}ms")

        # Step 4: Check database for timing breakdown
        print("\n4. Checking database for timing breakdown...")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get the most recent utterance for this session
        cursor.execute(
            """
            SELECT id, raw_text, router_timing_breakdown, created_at
            FROM utterances
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id,)
        )
        utterance = cursor.fetchone()
        conn.close()

        if not utterance:
            print("   ✗ FAIL: No utterance found in database")
            return False

        print(f"   ✓ Utterance found: {utterance['id'][:8]}...")

        timing_breakdown = utterance["router_timing_breakdown"]
        if not timing_breakdown:
            print("   ✗ FAIL: router_timing_breakdown is NULL")
            print(f"   Database state: {dict(utterance)}")
            return False

        try:
            timing_data = json.loads(timing_breakdown)
        except json.JSONDecodeError as e:
            print(f"   ✗ FAIL: Invalid JSON in timing breakdown: {e}")
            print(f"   Raw data: {timing_breakdown[:200]}")
            return False

        print(f"   ✓ Timing breakdown parsed successfully")

        # Step 5: Verify all required timing components exist
        print("\n5. Verifying timing components...")

        required_components = [
            ("prompt_construction_ms", "Prompt build time"),
            ("proxy_network_ms", "Network latency"),
            ("proxy_inference_ms", "LLM inference time"),
            ("json_parse_ms", "JSON parsing time"),
        ]

        all_present = True
        for component_key, component_name in required_components:
            value = timing_data.get(component_key)
            if value is None:
                print(f"   ✗ MISSING: {component_name} ({component_key})")
                all_present = False
            else:
                print(f"   ✓ {component_name}: {value:.2f}ms")

        if not all_present:
            print("\n   Full timing data:")
            print(f"   {json.dumps(timing_data, indent=2)}")
            return False

        # Step 6: Verify total_ms is reasonable
        print("\n6. Validating total time...")
        total_ms = timing_data.get("total_ms")
        if total_ms is None:
            print("   ✗ FAIL: total_ms missing from timing breakdown")
            return False

        # Sum the components (excluding cached results)
        if timing_data.get("cached", False):
            print(f"   ✓ Result from cache (total: {total_ms:.2f}ms)")
        else:
            prompt = timing_data.get("prompt_construction_ms", 0)
            network = timing_data.get("proxy_network_ms", 0) or 0
            inference = timing_data.get("proxy_inference_ms", 0) or 0
            parse = timing_data.get("json_parse_ms", 0)
            process = timing_data.get("process_ms", 0)

            # Total should be sum of all components (within tolerance)
            expected_total = prompt + network + inference + parse + process
            tolerance = 50  # 50ms tolerance for timing measurement overhead

            if abs(total_ms - expected_total) > tolerance:
                print(f"   ⚠ WARNING: total_ms ({total_ms:.2f}) doesn't match sum of components ({expected_total:.2f})")
            else:
                print(f"   ✓ Total time consistent: {total_ms:.2f}ms")

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print(f"\nSummary:")
        print(f"  • All 4 timing components present and logged")
        print(f"  • Timing breakdown stored in utterances.router_timing_breakdown")
        print(f"  • Total classification time: {total_ms:.2f}ms")
        print(f"  • Intent count: {timing_data.get('intents_count', 'N/A')}")
        return True


async def check_logs():
    """Check server logs for timing breakdown output."""
    print("\n7. Checking server logs...")
    log_path = Path("/tmp/adc.log")

    if not log_path.exists():
        print("   ⚠ Log file not found")
        return

    # Read the last 100 lines of the log
    lines = log_path.read_text().splitlines()[-100:]

    timing_lines = [line for line in lines if "router_timing breakdown:" in line]

    if not timing_lines:
        print("   ⚠ No timing breakdown logs found in recent output")
        return

    print(f"   ✓ Found {len(timing_lines)} timing log entries")
    most_recent = timing_lines[-1]
    print(f"   Latest: {most_recent.strip()}")


async def main():
    """Run the timing breakdown test."""
    try:
        success = await test_timing_breakdown()
        await check_logs()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ TEST FAILED WITH ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
