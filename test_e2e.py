#!/usr/bin/env python3
"""
E2E test harness for aide-de-camp.

Tests the full dispatch flow:
1. Register surface via SSE connection
2. Dispatch utterance
3. Wait for result_created SSE event
4. Verify completion within 30 seconds

Usage: python3 test_e2e.py "utterance text"
"""

import sys
import asyncio
import time
import uuid
import httpx
from typing import Optional

BASE_URL = "http://localhost:8000"
TIMEOUT_SECONDS = 30


async def listen_for_sse_event(
    session_id: str,
    surface_id: str,
    target_event_type: str,
    timeout_seconds: int = TIMEOUT_SECONDS,
) -> dict:
    """
    Connect to SSE endpoint and wait for a specific event type.

    Returns the event data when the target event is received.
    Times out and raises TimeoutError if not received within timeout_seconds.
    """
    url = f"{BASE_URL}/events"
    params = {"session_id": session_id, "surface_id": surface_id}

    start_time = time.monotonic()

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("GET", url, params=params) as response:
            if response.status_code != 200:
                raise RuntimeError(f"SSE connection failed: {response.status_code}")

            # Parse SSE events
            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk

                # Process complete SSE messages
                while "\n\n" in buffer:
                    event_block, buffer = buffer.split("\n\n", 1)

                    # Parse SSE format
                    event_type = None
                    event_data = None
                    for line in event_block.strip().split("\n"):
                        if line.startswith("event: "):
                            event_type = line[7:]
                        elif line.startswith("data: "):
                            import json
                            event_data = json.loads(line[6:])

                    if event_type == target_event_type:
                        elapsed = time.monotonic() - start_time
                        print(f"✓ Received {event_type} event in {elapsed:.2f}s")
                        return event_data

                # Check timeout
                if time.monotonic() - start_time > timeout_seconds:
                    raise TimeoutError(
                        f"Did not receive {target_event_type} event within {timeout_seconds}s"
                    )


async def dispatch_utterance(
    utterance: str,
    session_id: str,
    surface_id: str,
) -> dict:
    """Dispatch utterance to the server."""
    url = f"{BASE_URL}/dispatch"
    payload = {
        "utterance": utterance,
        "session_id": session_id,
        "surface_id": surface_id,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"Dispatch failed: {response.status_code} - {response.text}")
        return response.json()


async def run_e2e_test(utterance: str) -> bool:
    """
    Run the end-to-end test.

    Returns True if test passes, False otherwise.
    """
    print(f"Testing utterance: \"{utterance}\"")
    print("=" * 60)

    # Generate IDs
    session_id = str(uuid.uuid4())
    surface_id = str(uuid.uuid4())

    print(f"Session ID: {session_id}")
    print(f"Surface ID: {surface_id}")

    # Start SSE listener in background
    print("Starting SSE listener...")
    sse_task = asyncio.create_task(
        listen_for_sse_event(
            session_id=session_id,
            surface_id=surface_id,
            target_event_type="result_created",
            timeout_seconds=TIMEOUT_SECONDS,
        )
    )

    # Give SSE connection a moment to establish
    await asyncio.sleep(0.5)

    # Dispatch utterance
    print(f"Dispatching utterance...")
    try:
        dispatch_result = await dispatch_utterance(utterance, session_id, surface_id)
        print(f"✓ Dispatch acknowledged: {dispatch_result}")
    except Exception as e:
        print(f"✗ Dispatch failed: {e}")
        sse_task.cancel()
        return False

    # Wait for result_created event
    try:
        result_data = await asyncio.wait_for(sse_task, timeout=TIMEOUT_SECONDS)
        print(f"✓ Result data: {result_data}")

        # Verify expected fields
        expected_fields = ["intent_id", "topic_id"]
        for field in expected_fields:
            if field not in result_data:
                print(f"✗ Missing expected field: {field}")
                return False

        print(f"✓ All expected fields present")

        # Run store-level assertions
        print("\nRunning store-level assertions...")
        intent_id = result_data.get("intent_id")
        topic_id = result_data.get("topic_id")

        import subprocess
        import json
        assertion_result = subprocess.run(
            [
                ".venv/bin/python",
                "test_e2e_assertions.py",
                session_id,
                intent_id,
                topic_id,
                json.dumps(result_data)
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Print assertion output
        if assertion_result.stdout:
            print(assertion_result.stdout)

        if assertion_result.returncode != 0:
            print(f"✗ Store-level assertions failed")
            if assertion_result.stderr:
                print(f"  Error: {assertion_result.stderr}")
            return False

        print("=" * 60)
        print("✓ E2E TEST PASSED")
        return True

    except TimeoutError as e:
        print(f"✗ Timeout: {e}")
        return False
    except Exception as e:
        print(f"✗ SSE error: {e}")
        return False


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_e2e.py \"utterance text\"", file=sys.stderr)
        sys.exit(1)

    utterance = sys.argv[1]

    try:
        success = await run_e2e_test(utterance)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n✗ Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
