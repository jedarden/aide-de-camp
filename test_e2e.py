#!/usr/bin/env python3
"""
End-to-end pipeline test: register surface → open SSE → dispatch → wait for result_created.

Usage:
    python3 test_e2e.py [utterance]

Exits 0 on success, 1 on timeout or error.
"""
import asyncio
import json
import sys
import time
import httpx

BASE = "http://localhost:8000"
TIMEOUT = 30  # seconds to wait for result_created


async def run(utterance: str) -> bool:
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as client:
        # 1. Register a surface
        session_id = f"e2e-test-{int(time.time())}"
        reg = await client.post("/api/v1/surfaces/register", json={
            "session_id": session_id,
            "surface_type": "canvas",
        })
        reg.raise_for_status()
        surface_id = reg.json()["surface_id"]
        print(f"  session:  {session_id}")
        print(f"  surface:  {surface_id}")

    # 2. Open SSE stream and dispatch concurrently
    result_event = asyncio.Event()
    received: dict = {}

    async def listen_sse():
        url = f"{BASE}/api/v1/sse?surface_id={surface_id}&session_id={session_id}&surface_type=canvas"
        async with httpx.AsyncClient(timeout=None) as sse_client:
            async with sse_client.stream("GET", url) as resp:
                event_type = None
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and event_type == "result_created":
                        received.update(json.loads(line.split(":", 1)[1].strip()))
                        result_event.set()
                        return
                    elif not line:
                        event_type = None

    async def dispatch():
        await asyncio.sleep(0.5)  # let SSE connect first
        async with httpx.AsyncClient(base_url=BASE, timeout=60) as client:
            resp = await client.post("/dispatch", json={
                "utterance": utterance,
                "session_id": session_id,
            })
            resp.raise_for_status()
            ack = resp.json()
            print(f"  dispatch: {ack.get('intent_count', 0)} intent(s) → {ack.get('intent_ids', [])}")

    sse_task = asyncio.create_task(listen_sse())
    dispatch_task = asyncio.create_task(dispatch())

    try:
        await asyncio.wait_for(result_event.wait(), timeout=TIMEOUT)
        sse_task.cancel()
        print(f"\n  PASS — result_created received")
        print(f"  summary:  {received.get('summary', '(none)')}")
        print(f"  urgency:  {received.get('urgency', '?')}")
        data = received.get('data', {})
        if data:
            print(f"  data:     {json.dumps(data, indent=4)[:400]}")
        return True
    except asyncio.TimeoutError:
        sse_task.cancel()
        print(f"\n  FAIL — no result_created within {TIMEOUT}s")
        return False
    finally:
        dispatch_task.cancel()


async def main():
    utterance = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is the status of the native ads project?"
    print(f"\nE2E test: {utterance!r}\n")
    ok = await run(utterance)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
