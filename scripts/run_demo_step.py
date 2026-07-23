#!/usr/bin/env python3
"""
Demo Step Runner

Run individual demo steps from the Phase 5 golden path script.
Useful for testing specific shapes or for manual rehearsal.

Usage:
    python scripts/run_demo_step.py 1          # Run step 1
    python scripts/run_demo_step.py 1-3       # Run steps 1-3
    python scripts/run_demo_step.py all        # Run all steps
"""

import asyncio
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

# Demo script utterances from Phase 5 plan.md (golden path)
# Uses pbx-web and whisper-stt projects (both on ardenone-cluster)
DEMO_SCRIPT = {
    1: {
        "utterance": "Has the pbx web caught up, and what's the state of whisper stt?",
        "description": "Multi-intent status query (pbx-web + whisper-stt)",
    },
    2: {
        "utterance": "Pull up the recent logs for whisper stt.",
        "description": "Lookup logs (whisper-stt)",
    },
    3: {
        "utterance": "Should pbx web keep using the static site generator, or is it time to move to a dynamic frontend? Give me the trade-offs.",
        "description": "Brainstorm (pbx-web)",
    },
    4: {
        "utterance": "Find whisper stt's deployment config — which cluster and namespace is it on?",
        "description": "Lookup config (whisper-stt)",
    },
    5: {
        "utterance": "Queue up a research task: compare the last month of pbx web deployment patterns against whisper stt's and write up common failure patterns — no rush.",
        "description": "Task-profile (escalate to bead)",
    },
    6: {
        "utterance": "Anything new on pbx web since we started?",
        "description": "Status with diff (pbx-web)",
    },
}

SERVER_URL = "http://localhost:8000"


async def run_step(step_num: int, session_id: str, client: httpx.AsyncClient) -> dict:
    """Run a single demo step."""
    if step_num not in DEMO_SCRIPT:
        print(f"❌ Invalid step number: {step_num}")
        print(f"   Valid steps: {', '.join(map(str, DEMO_SCRIPT.keys()))}")
        sys.exit(1)

    step_data = DEMO_SCRIPT[step_num]
    utterance = step_data["utterance"]
    description = step_data["description"]

    print(f"\n{'='*60}")
    print(f"Step {step_num}: {description}")
    print(f"{'='*60}")
    print(f"Utterance: {utterance}")
    print()

    start_time = time.time()

    try:
        response = await client.post(
            f"{SERVER_URL}/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "wait_for_results": True,
                "timeout_seconds": 60,
            },
            timeout=90.0
        )
        response.raise_for_status()

        elapsed = time.time() - start_time
        data = response.json()

        print(f"✓ Completed in {elapsed:.2f}s")
        print(f"  Utterance ID: {data.get('utterance_id', 'N/A')[:8]}...")
        print(f"  Intent count: {data.get('intent_count', 0)}")
        print(f"  Intent IDs: {[iid[:8] for iid in data.get('intent_ids', [])]}")

        return {"success": True, "data": data, "elapsed": elapsed}

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"✗ Failed after {elapsed:.2f}s: {e}")
        return {"success": False, "error": str(e), "elapsed": elapsed}


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python run_demo_step.py <step_number|range|all>")
        print("Examples:")
        print("  python run_demo_step.py 1")
        print("  python run_demo_step.py 1-3")
        print("  python run_demo_step.py all")
        sys.exit(1)

    arg = sys.argv[1]

    # Parse steps to run
    if arg == "all":
        steps_to_run = list(DEMO_SCRIPT.keys())
    elif "-" in arg:
        # Range: 1-3
        start, end = arg.split("-")
        steps_to_run = list(range(int(start), int(end) + 1))
    else:
        # Single step
        steps_to_run = [int(arg)]

    print("="*60)
    print("DEMO STEP RUNNER")
    print("="*60)
    print(f"Server: {SERVER_URL}")
    print(f"Steps to run: {steps_to_run}")
    print(f"Started: {datetime.now().isoformat()}")

    # Check server health
    try:
        async with httpx.AsyncClient() as client:
            health = await client.get(f"{SERVER_URL}/health", timeout=5.0)
            health.raise_for_status()
            print(f"✓ Server healthy: {health.json().get('status')}")
    except Exception as e:
        print(f"✗ Server not healthy: {e}")
        sys.exit(1)

    # Create session
    session_id = str(uuid.uuid4())
    print(f"Session ID: {session_id[:8]}...")

    # Run steps
    async with httpx.AsyncClient(timeout=90.0) as client:
        results = []
        for step_num in steps_to_run:
            result = await run_step(step_num, session_id, client)
            results.append({"step": step_num, **result})

            # Small delay between steps
            if step_num != steps_to_run[-1]:
                await asyncio.sleep(1)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    successful = sum(1 for r in results if r["success"])
    print(f"Steps run: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {len(results) - successful}")

    if successful < len(results):
        print("\nFailed steps:")
        for r in results:
            if not r["success"]:
                print(f"  Step {r['step']}: {r.get('error', 'Unknown error')}")
        sys.exit(1)
    else:
        print("\n✓ All steps completed successfully")


if __name__ == "__main__":
    asyncio.run(main())
