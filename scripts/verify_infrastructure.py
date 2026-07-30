#!/usr/bin/env python3
"""
Infrastructure Verification Script

Verifies that all components needed for latency testing are in place:
1. Server is running and healthy
2. ZAI proxy is reachable
3. Database is accessible
4. dispatch_timings table exists and is being populated
5. Test endpoints are working

Run this before starting latency measurements to ensure everything is ready.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import httpx
import aiosqlite

SERVER_URL = "http://localhost:8000"
DB_PATH = "data/session.db"
ZAI_PROXY_URL = "https://zai-proxy-mcp-apexalgo-iad-ts.ardenone.com:8444/v1/messages"


async def check_server_health() -> dict:
    """Check if ADC server is running and healthy."""
    print(f"\n1. Checking ADC server: {SERVER_URL}/health")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SERVER_URL}/health", timeout=5.0)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            watcher = data.get("watcher", {})

            print(f"   ✓ Server status: {status}")
            print(f"   ✓ Watcher alive: {watcher.get('alive', False)}")
            if watcher.get("last_tick_at"):
                print(f"   ✓ Watcher last tick: {watcher['last_tick_at']}")

            return {
                "server_healthy": True,
                "status": status,
                "watcher_alive": watcher.get("alive", False),
            }
    except Exception as e:
        print(f"   ✗ Server check failed: {e}")
        return {"server_healthy": False, "error": str(e)}


async def check_zai_proxy() -> dict:
    """Check if ZAI proxy is reachable."""
    print(f"\n2. Checking ZAI proxy: {ZAI_PROXY_URL}")
    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            # Try a minimal request to check connectivity
            # We expect auth failure, but any response means proxy is reachable
            response = await client.post(
                ZAI_PROXY_URL,
                json={
                    "model": "claude-haiku-4-20250514",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "test"}]
                },
                headers={"x-api-key": "test"}
            )

            # Any response (even error) means connectivity is OK
            print(f"   ✓ Proxy reachable (status: {response.status_code})")
            return {"proxy_reachable": True, "status_code": response.status_code}

    except httpx.ConnectError as e:
        print(f"   ✗ Proxy connection failed: {e}")
        return {"proxy_reachable": False, "error": "connect_error"}
    except httpx.TimeoutException:
        print(f"   ✗ Proxy timeout")
        return {"proxy_reachable": False, "error": "timeout"}
    except Exception as e:
        print(f"   ✗ Proxy check failed: {e}")
        return {"proxy_reachable": False, "error": str(e)}


async def check_database() -> dict:
    """Check if database exists and is accessible."""
    print(f"\n3. Checking database: {DB_PATH}")

    db_file = Path(DB_PATH)
    if not db_file.exists():
        print(f"   ✗ Database file not found: {DB_FILE}")
        return {"db_accessible": False, "error": "file_not_found"}

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if dispatch_timings table exists
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='dispatch_timings'
            """)
            result = await cursor.fetchone()

            if result:
                print(f"   ✓ Database accessible")
                print(f"   ✓ dispatch_timings table exists")

                # Check if there are any recent timings
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM dispatch_timings
                """)
                count = (await cursor.fetchone())[0]
                print(f"   ✓ Existing timing records: {count}")

                return {
                    "db_accessible": True,
                    "dispatch_timings_exists": True,
                    "existing_records": count,
                }
            else:
                print(f"   ✗ dispatch_timings table not found")
                return {
                    "db_accessible": True,
                    "dispatch_timings_exists": False,
                }

    except Exception as e:
        print(f"   ✗ Database check failed: {e}")
        return {"db_accessible": False, "error": str(e)}


async def check_test_endpoint() -> dict:
    """Check if test dispatch endpoint works."""
    print(f"\n4. Checking test dispatch endpoint")

    try:
        async with httpx.AsyncClient() as client:
            # Try a simple test dispatch
            response = await client.post(
                f"{SERVER_URL}/api/v1/test/dispatch",
                json={
                    "utterance": "test",
                    "wait_for_results": False,
                    "timeout_seconds": 5,
                },
                timeout=10.0
            )

            if response.status_code in (200, 400):  # 400 is OK (might be malformed utterance)
                print(f"   ✓ Test endpoint responding (status: {response.status_code})")
                return {"endpoint_working": True, "status_code": response.status_code}
            else:
                print(f"   ⚠ Unexpected status: {response.status_code}")
                return {"endpoint_working": False, "status_code": response.status_code}

    except Exception as e:
        print(f"   ✗ Test endpoint check failed: {e}")
        return {"endpoint_working": False, "error": str(e)}


async def check_timings_endpoint() -> dict:
    """Check if timings percentiles endpoint works."""
    print(f"\n5. Checking timings percentiles endpoint")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVER_URL}/api/v1/timings/percentiles",
                timeout=5.0
            )
            response.raise_for_status()

            data = response.json()
            print(f"   ✓ Timings endpoint working")
            print(f"   ✓ Stages available: {len(data)}")

            return {"endpoint_working": True, "stages": len(data)}

    except Exception as e:
        print(f"   ✗ Timings endpoint check failed: {e}")
        return {"endpoint_working": False, "error": str(e)}


async def run_test_dispatch() -> dict:
    """Run a single test dispatch to verify timing capture."""
    print(f"\n6. Running test dispatch to verify timing capture")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVER_URL}/api/v1/test/dispatch",
                json={
                    "utterance": "What's the status of pbx web?",
                    "wait_for_results": True,
                    "timeout_seconds": 30,
                },
                timeout=45.0
            )
            response.raise_for_status()
            data = response.json()

            utterance_id = data.get("utterance_id")
            intent_ids = data.get("intent_ids", [])

            print(f"   ✓ Test dispatch completed")
            print(f"   ✓ Utterance ID: {utterance_id[:8] if utterance_id else 'N/A'}...")
            print(f"   ✓ Intent IDs: {[iid[:8] for iid in intent_ids]}")

            # Wait a moment for timings to be written
            await asyncio.sleep(1)

            # Check if timings were recorded
            async with aiosqlite.connect(DB_PATH) as db:
                for intent_id in intent_ids[:1]:  # Check first intent only
                    cursor = await db.execute(
                        "SELECT * FROM dispatch_timings WHERE intent_id = ?",
                        (intent_id,)
                    )
                    timing_row = await cursor.fetchone()

                    if timing_row:
                        print(f"   ✓ Timing record found for intent {intent_id[:8]}...")

                        # Decode row
                        columns = [
                            "intent_id", "router_ms", "fetch_first_source_ms",
                            "fetch_total_ms", "synthesize_first_token_ms",
                            "synthesize_total_ms", "escalate_ms", "sse_emit_ms",
                            "stt_ms", "first_render_ms", "created_at"
                        ]
                        timing = dict(zip(columns, timing_row))

                        # Show non-null timings
                        for key, value in timing.items():
                            if value is not None and key.endswith("_ms"):
                                print(f"      - {key}: {value}ms")

                        return {"timings_captured": True, "timing": timing}
                    else:
                        print(f"   ✗ No timing record found for intent {intent_id[:8]}...")
                        return {"timings_captured": False}

            return {"timings_captured": False, "error": "no_intent_ids"}

    except Exception as e:
        print(f"   ✗ Test dispatch failed: {e}")
        return {"timings_captured": False, "error": str(e)}


async def main():
    """Main verification."""
    print("="*60)
    print("INFRASTRUCTURE VERIFICATION")
    print("="*60)
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Server: {SERVER_URL}")
    print(f"Database: {DB_PATH}")
    print(f"ZAI Proxy: {ZAI_PROXY_URL}")

    results = {}

    # Run all checks
    results["server"] = await check_server_health()
    results["proxy"] = await check_zai_proxy()
    results["database"] = await check_database()
    results["test_endpoint"] = await check_test_endpoint()
    results["timings_endpoint"] = await check_timings_endpoint()

    # Only run test dispatch if server is healthy
    if results["server"].get("server_healthy"):
        results["test_dispatch"] = await run_test_dispatch()
    else:
        print("\n⚠ Skipping test dispatch (server not healthy)")
        results["test_dispatch"] = {"skipped": True}

    # Summary
    print(f"\n{'='*60}")
    print("VERIFICATION SUMMARY")
    print(f"{'='*60}")

    checks = [
        ("Server Health", results["server"].get("server_healthy", False)),
        ("ZAI Proxy Reachable", results["proxy"].get("proxy_reachable", False)),
        ("Database Accessible", results["database"].get("db_accessible", False)),
        ("dispatch_timings Table", results["database"].get("dispatch_timings_exists", False)),
        ("Test Endpoint", results["test_endpoint"].get("endpoint_working", False)),
        ("Timings Endpoint", results["timings_endpoint"].get("endpoint_working", False)),
        ("Timing Capture", results.get("test_dispatch", {}).get("timings_captured", False)),
    ]

    all_passed = True
    for name, passed in checks:
        status = "✓" if passed else "✗"
        print(f"{status} {name}")
        if not passed:
            all_passed = False

    print(f"\n{'='*60}")
    if all_passed:
        print("✓ ALL CHECKS PASSED")
        print("Infrastructure is ready for latency testing.")
        return 0
    else:
        print("✗ SOME CHECKS FAILED")
        print("Please fix the issues above before running latency tests.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
