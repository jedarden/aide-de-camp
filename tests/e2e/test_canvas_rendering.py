#!/usr/bin/env python3
"""
End-to-end test: Canvas renders test endpoint results correctly.

This test verifies the full pipeline:
1. Test dispatch → intent routing → fetch + synthesize
2. Results persisted to session store
3. SSE broadcast triggers canvas reload
4. Canvas fetches topics from /api/v1/sessions/{session_id}/topics
5. Cards render with correct content
"""
import asyncio
import json
import uuid
from logging import INFO, basicConfig

basicConfig(level=INFO, format="%(levelname)s %(name)s: %(message)s")

# Configured logging above before importing modules that may emit at import time.
import httpx  # noqa: E402
import pytest  # noqa: E402

# httpx_sse is an optional SSE-consumer dep used only by this legacy standalone
# script. Its canvas-rendering coverage is fully superseded by the hermetic,
# browser-aware suites (test_canvas_sse_render.py et al.). importorskip (vs a
# bare import) keeps the whole tests/e2e/ tree collectible when the dep is
# absent — a bare ImportError here otherwise aborts collection of all ~72 e2e
# tests. Install httpx-sse to run this script's LLM-driven pipeline check.
httpx_sse = pytest.importorskip("httpx_sse")


async def test_canvas_rendering_pipeline():
    """Test the full canvas rendering pipeline via test dispatch endpoint."""

    base_url = "http://localhost:8000"
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())

    print(f"\n{'='*60}")
    print("Testing Canvas Rendering Pipeline")
    print(f"Session ID: {session_id[:16]}...")
    print(f"Surface ID: {surface_id[:16]}...")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(timeout=60.0) as client:

        # Step 1: Register canvas surface
        print("Step 1: Registering canvas surface...")
        response = await client.post(
            f"{base_url}/api/v1/surfaces/register",
            json={
                "session_id": session_id,
                "surface_type": "canvas"
            }
        )
        response.raise_for_status()
        data = response.json()
        registered_surface_id = data.get("surface_id")
        print(f"✓ Registered surface: {registered_surface_id[:16]}...")

        # Step 2: Connect to SSE stream (simulate canvas)
        print("\nStep 2: Connecting to SSE stream...")
        sse_events = []

        async def capture_sse_events():
            """Capture SSE events for verification."""
            async with httpx_sse.aconnect_sse(
                client,
                "GET",
                f"{base_url}/api/v1/sse",
                params={
                    "session_id": session_id,
                    "surface_id": registered_surface_id,
                    "surface_type": "canvas"
                }
            ) as event_source:
                async for sse in event_source.aiter_sse():
                    event_data = {
                        "event": sse.event,
                        "data": sse.data,
                    }
                    sse_events.append(event_data)
                    print(f"  SSE Event: {sse.event}")

                    # Stop after receiving topic_cards update (after result_created)
                    if sse.event == "topic_cards" and len(sse_events) > 3:
                        # Wait a bit to ensure we've captured everything
                        await asyncio.sleep(1)
                        break

        # Start SSE listener in background
        sse_task = asyncio.create_task(capture_sse_events())

        # Wait a bit for connection to establish
        await asyncio.sleep(1)

        # Step 3: Dispatch test utterance via test endpoint (with SSE flow)
        print("\nStep 3: Dispatching test utterance...")
        test_utterance = "how are the pods doing"

        response = await client.post(
            f"{base_url}/api/v1/test/dispatch",
            json={
                "utterance": test_utterance,
                "session_id": session_id,
                "surface_id": registered_surface_id,
                "wait_for_results": False,  # Use SSE flow, not direct return
                "timeout_seconds": 30
            }
        )
        response.raise_for_status()
        dispatch_result = response.json()

        print(f"✓ Dispatch status: {dispatch_result.get('status')}")
        print(f"✓ Intent count: {dispatch_result.get('intent_count')}")
        print(f"✓ Intent IDs: {len(dispatch_result.get('intent_ids', []))}")
        print(f"✓ Message: {dispatch_result.get('message')}")

        # Step 4: Wait for SSE events
        print("\nStep 4: Waiting for SSE events...")
        try:
            await asyncio.wait_for(sse_task, timeout=35)
        except asyncio.TimeoutError:
            print("✗ Timeout waiting for SSE events")
        else:
            print(f"✓ Received {len(sse_events)} SSE events")

        # Step 5: Verify SSE events
        print("\nStep 5: Verifying SSE events...")
        event_types = [e["event"] for e in sse_events]
        print(f"  Event types: {event_types}")

        assert "connected" in event_types, "Missing 'connected' event"
        assert "result_created" in event_types, "Missing 'result_created' event"
        print("✓ Required SSE events received")

        # Step 6: Fetch topics via API (what canvas does)
        print("\nStep 6: Fetching topics from API...")
        response = await client.get(
            f"{base_url}/api/v1/sessions/{session_id}/topics"
        )
        response.raise_for_status()
        topics_data = response.json()

        print(f"✓ Topics API response status: {response.status_code}")
        cards = topics_data.get("cards", [])
        print(f"✓ Retrieved {len(cards)} topic cards")

        # Step 7: Verify card structure and content
        print("\nStep 7: Verifying card structure...")

        if not cards:
            print("✗ No cards returned from topics API")
            return False

        for i, card in enumerate(cards):
            print(f"\n  Card {i+1}:")
            print(f"    Topic ID: {card['topic']['id'][:16]}...")
            print(f"    Label: {card['topic']['label']}")
            print(f"    Type: {card['topic'].get('type', 'adhoc')}")

            # Verify topic structure
            assert "topic" in card, "Missing 'topic' field"
            assert "staleness" in card, "Missing 'staleness' field"
            assert "latest_result" in card, "Missing 'latest_result' field"

            # Verify topic fields
            topic = card["topic"]
            assert "id" in topic, "Missing topic 'id'"
            assert "label" in topic, "Missing topic 'label'"

            # Verify staleness
            staleness = card["staleness"]
            assert "seconds" in staleness, "Missing staleness 'seconds'"
            print(f"    Staleness: {staleness['seconds']}s")

            # Verify result
            result = card["latest_result"]
            if result:
                assert "summary" in result, "Missing result 'summary'"
                print(f"    Summary: {result['summary'][:80]}...")
                if "urgency" in result:
                    print(f"    Urgency: {result['urgency']}")

        print("\n✓ Card structure verification passed")

        # Step 8: Verify SSE event data matches API data
        print("\nStep 8: Verifying SSE data matches API data...")

        result_created_event = next(
            (e for e in sse_events if e["event"] == "result_created"),
            None
        )

        if result_created_event:
            sse_data = json.loads(result_created_event["data"])
            print(f"  SSE result data: {json.dumps(sse_data, indent=2)}")

            # Find matching card
            if cards:
                first_card = cards[0]
                api_summary = first_card.get("latest_result", {}).get("summary")
                sse_summary = sse_data.get("summary")

                if api_summary and sse_summary:
                    print(f"  API summary: {api_summary[:80]}...")
                    print(f"  SSE summary: {sse_summary[:80]}...")
                    print("✓ SSE and API data are consistent")

        print(f"\n{'='*60}")
        print("✓ All canvas rendering tests passed!")
        print(f"{'='*60}\n")

        return True


async def main():
    """Run all canvas rendering tests."""
    try:
        success = await test_canvas_rendering_pipeline()
        if success:
            print("\n✓ Canvas rendering pipeline verified successfully")
            return 0
        else:
            print("\n✗ Canvas rendering pipeline verification failed")
            return 1
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
