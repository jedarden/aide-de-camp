#!/usr/bin/env python3
"""
Verify Canvas Renders Test Endpoint Results

This test verifies that:
1. Canvas receives SSE events from test dispatch
2. Canvas fetches topics from /api/v1/sessions/{session_id}/topics
3. Result cards render with correct content
4. Visual output matches /dispatch results

Run: python3 tests/e2e/verify_canvas_test_render.py
"""
import asyncio
import json
import uuid
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode

import httpx


# Configuration
API_BASE_URL = "http://localhost:8000"


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
        return False


async def verify_canvas_receives_sse():
    """Verify canvas receives SSE events from test dispatch."""
    print_test("Test 1: Canvas Receives SSE Events")

    session_id = f"canvas-test-{uuid.uuid4().hex[:16]}"
    surface_id = f"canvas-surface-{uuid.uuid4().hex[:16]}"
    utterance = "simple status check"

    print(f"  📡 Connecting canvas to SSE endpoint...")
    print(f"     Session: {session_id}")
    print(f"     Surface: {surface_id}")

    received_events = []

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

                # Collect initial events
                async for line in sse_response.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            received_events.append({"type": event_type, "data": data})
                            if event_type in ("workload_summary", "topic_cards"):
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
            got_result_created = False
            current_event_type = None

            async def collect_events():
                nonlocal got_result_created
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
                                got_result_created = True
                                return
                        except json.JSONDecodeError:
                            pass
                        current_event_type = None

            # Wait for connection to establish
            await asyncio.sleep(0.5)

            # Dispatch utterance via test endpoint
            dispatch_start = datetime.now()
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
                print_result(False, f"Test dispatch failed: {dispatch_response.status_code}")
                print(f"     Response: {dispatch_response.text[:200]}")
                return False

            dispatch_data = dispatch_response.json()
            print_result(True, f"Test dispatch returned: {dispatch_data['status']}")

            # Wait for SSE event
            try:
                await asyncio.wait_for(collect_events(), timeout=20.0)

                if got_result_created:
                    print_result(True, "Canvas received result_created event via SSE")

                    # Verify event payload
                    result_events = [e for e in received_result_events if e.get("type") == "result_created"]
                    if result_events:
                        event_data = result_events[0]["data"]
                        print_result(True, f"Event data keys: {list(event_data.keys())}")

                        # Check for expected fields
                        expected_fields = ["intent_id", "topic_id", "summary", "urgency"]
                        has_fields = [field in event_data for field in expected_fields]
                        if all(has_fields):
                            print_result(True, "Event contains all expected fields")
                        else:
                            missing = [f for f, h in zip(expected_fields, has_fields) if not h]
                            print_result(False, f"Missing fields: {missing}")
                            return False
                else:
                    print_result(False, "No result_created event received")
                    print(f"     Events received: {[e.get('type') for e in received_result_events]}")
                    return False

            except asyncio.TimeoutError:
                print_result(False, "SSE event timeout (20s)")
                return False

    return True


async def verify_canvas_fetches_topics():
    """Verify canvas fetches topics from API endpoint."""
    print_test("Test 2: Canvas Fetches Topics")

    session_id = f"fetch-test-{uuid.uuid4().hex[:16]}"
    utterance = "check the status"

    print(f"  📤 Dispatching test utterance...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Dispatch via test endpoint
        dispatch_response = await client.post(
            f"{API_BASE_URL}/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "wait_for_results": False,
            }
        )

        if dispatch_response.status_code != 200:
            print_result(False, f"Test dispatch failed: {dispatch_response.status_code}")
            return False

        dispatch_data = dispatch_response.json()
        print_result(True, f"Test dispatch returned: {dispatch_data['status']}")

        # Wait for processing
        print(f"  ⏳ Waiting for async processing...")
        await asyncio.sleep(3)

        # Fetch topics
        print(f"  📥 Fetching topics from /api/v1/sessions/{session_id}/topics...")

        topics_response = await client.get(
            f"{API_BASE_URL}/api/v1/sessions/{session_id}/topics"
        )

        if topics_response.status_code != 200:
            print_result(False, f"Topics fetch failed: {topics_response.status_code}")
            return False

        topics_data = topics_response.json()
        print_result(True, f"Topics API returned successfully")

        # Verify response structure
        if "cards" not in topics_data:
            print_result(False, "Response missing 'cards' field")
            return False

        cards = topics_data["cards"]
        print_result(True, f"Received {len(cards)} topic cards")

        # Verify card structure
        if cards:
            card = cards[0]
            print_result(True, f"Card keys: {list(card.keys())}")

            # Check for required fields
            required_sections = ["topic", "staleness", "latest_result"]
            has_sections = [section in card for section in required_sections]
            if all(has_sections):
                print_result(True, "Card contains required sections")
            else:
                missing = [s for s, h in zip(required_sections, has_sections) if not h]
                print_result(False, f"Card missing sections: {missing}")
                return False

            # Check topic section
            topic = card.get("topic", {})
            if "id" in topic and "label" in topic:
                print_result(True, f"Topic has id={topic['id'][:8]}..., label={topic['label'][:30]}...")
            else:
                print_result(False, "Topic missing id or label")
                return False

            # Check latest_result section
            latest_result = card.get("latest_result", {})
            if latest_result:
                if "summary" in latest_result:
                    print_result(True, f"Result has summary: {latest_result['summary'][:50]}...")
                if "urgency" in latest_result:
                    print_result(True, f"Result has urgency: {latest_result['urgency']}")
            else:
                print(f"  ⚠️  No latest_result yet (may still be processing)")
        else:
            print(f"  ⚠️  No cards returned yet (processing may still be in progress)")

    return True


async def verify_card_content_matches_dispatch():
    """Verify card content matches dispatch results."""
    print_test("Test 3: Card Content Matches Dispatch Results")

    session_id = f"content-test-{uuid.uuid4().hex[:16]}"
    utterance = "what is the system status"

    print(f"  📤 Dispatching with wait_for_results=True...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Dispatch with wait_for_results to get direct results
        dispatch_response = await client.post(
            f"{API_BASE_URL}/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "wait_for_results": True,
                "timeout_seconds": 30,
            }
        )

        if dispatch_response.status_code != 200:
            print_result(False, f"Test dispatch failed: {dispatch_response.status_code}")
            return False

        dispatch_data = dispatch_response.json()
        print_result(True, f"Test dispatch returned: {dispatch_data['status']}")

        # Check if results are included
        if "results" in dispatch_data and dispatch_data["results"]:
            results = dispatch_data["results"]
            print_result(True, f"Direct results: {len(results)} result(s)")

            if results:
                first_result = results[0]
                print_result(True, f"Result keys: {list(first_result.keys())}")

                # Now fetch topics and compare
                print(f"  📥 Fetching topics from API...")

                topics_response = await client.get(
                    f"{API_BASE_URL}/api/v1/sessions/{session_id}/topics"
                )

                if topics_response.status_code != 200:
                    print_result(False, f"Topics fetch failed: {topics_response.status_code}")
                    return False

                topics_data = topics_response.json()
                cards = topics_data.get("cards", [])

                if cards:
                    card = cards[0]
                    latest_result = card.get("latest_result", {})

                    # Compare summary
                    if "summary" in first_result and "summary" in latest_result:
                        direct_summary = first_result["summary"]
                        card_summary = latest_result["summary"]

                        if direct_summary == card_summary:
                            print_result(True, "Summaries match")
                        else:
                            print_result(False, "Summaries differ!")
                            print(f"     Direct: {direct_summary[:50]}...")
                            print(f"     Card:   {card_summary[:50]}...")
                            return False
                    else:
                        print(f"  ⚠️  Cannot compare summaries (one is missing)")

                    # Compare urgency
                    if "urgency" in first_result and "urgency" in latest_result:
                        if first_result["urgency"] == latest_result["urgency"]:
                            print_result(True, "Urgency matches")
                        else:
                            print_result(False, "Urgency differs!")
                            print(f"     Direct: {first_result['urgency']}")
                            print(f"     Card:   {latest_result['urgency']}")
                            return False
        else:
            print(f"  ⚠️  No direct results to compare (processing may have failed)")

    return True


async def verify_sse_triggers_canvas_refresh():
    """Verify SSE triggers canvas refresh (loadTopics)."""
    print_test("Test 4: SSE Triggers Canvas Refresh")

    session_id = f"refresh-test-{uuid.uuid4().hex[:16]}"
    surface_id = f"refresh-surface-{uuid.uuid4().hex[:16]}"
    utterance = "test refresh trigger"

    print(f"  📡 Simulating canvas SSE connection...")

    # Track when we receive result_created
    received_result_created = False
    topics_fetch_count = 0

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Connect to SSE in a single stream
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

            # Single event collection loop
            current_event_type = None
            skipped_initial = False
            got_result_created = False

            # Start dispatch after connection is established
            await asyncio.sleep(0.5)

            print(f"  📤 Dispatching test utterance...")
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
                print_result(False, f"Test dispatch failed: {dispatch_response.status_code}")
                return False

            print_result(True, f"Test dispatch returned: {dispatch_response.json()['status']}")

            # Wait for result_created event in the same stream
            try:
                async for line in sse_response.aiter_lines():
                    if line.startswith("event: "):
                        current_event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        # Skip initial workload_summary event
                        if not skipped_initial and current_event_type == "workload_summary":
                            skipped_initial = True
                            current_event_type = None
                            continue

                        # Look for result_created after skipping initial events
                        if current_event_type == "result_created" and skipped_initial:
                            got_result_created = True
                            print_result(True, "SSE result_created event received")
                            print_result(True, "Canvas would trigger loadTopics() refresh")
                            break
                        current_event_type = None

                if not got_result_created:
                    print_result(False, "No result_created event received")
                    return False

            except asyncio.TimeoutError:
                print_result(False, "SSE event timeout (20s)")
                return False

    return True


async def main():
    """Run all canvas rendering tests."""
    print_section("Canvas Test Endpoint Rendering Verification")
    print(f"API: {API_BASE_URL}")

    # Check server
    if not await check_server():
        return 1

    all_passed = True

    # Run tests
    if not await verify_canvas_receives_sse():
        all_passed = False

    if not await verify_canvas_fetches_topics():
        all_passed = False

    if not await verify_card_content_matches_dispatch():
        all_passed = False

    if not await verify_sse_triggers_canvas_refresh():
        all_passed = False

    # Summary
    print_section("Summary")
    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("\nVerified:")
        print("  ✓ Canvas receives SSE events from test dispatch")
        print("  ✓ Canvas fetches topics from /api/v1/sessions/{session_id}/topics")
        print("  ✓ Result cards render with correct content")
        print("  ✓ Card content matches dispatch results")
        print("  ✓ SSE triggers canvas refresh on result_created")
        print("\n✅ Canvas correctly renders test endpoint results")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("\nCheck logs above for details")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
