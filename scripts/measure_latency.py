#!/usr/bin/env python3
"""
Latency Baseline Measurement Script

Runs the Phase 5 demo script utterances repeatedly to collect timing data.
Each utterance shape is run >=30 times to establish reliable p50/p95 metrics.
"""

import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx
import aiosqlite

# Demo script utterances from Phase 5
DEMO_UTTERANCES = [
    {
        "name": "step1_multi_status",
        "utterance": "Has the options pipeline caught up, and what's the state of the ibkr mcp?",
        "description": "Multi-intent status query (options-pipeline + ibkr-mcp)",
        "expected_intents": 2
    },
    {
        "name": "step2_lookup_logs",
        "utterance": "Pull up the recent logs for the ibkr mcp.",
        "description": "Lookup logs (ibkr-mcp)",
        "expected_intents": 1
    },
    {
        "name": "step3_brainstorm",
        "utterance": "Should the options pipeline keep writing straight to SQLite, or is it time to batch through a queue? Give me the trade-offs.",
        "description": "Brainstorm (options-pipeline)",
        "expected_intents": 1
    },
    {
        "name": "step4_lookup_config",
        "utterance": "Find the ibkr mcp's deployment config — which cluster and namespace is it on?",
        "description": "Lookup config (ibkr-mcp)",
        "expected_intents": 1
    },
    {
        "name": "step5_task_profile",
        "utterance": "Queue up a research task: compare the last month of options pipeline errors against the ibkr mcp's and write up common failure patterns — no rush.",
        "description": "Task-profile (escalate to bead)",
        "expected_intents": 1
    },
    {
        "name": "step6_status_with_diff",
        "utterance": "Anything new on the options pipeline since we started?",
        "description": "Status query with diff (options-pipeline)",
        "expected_intents": 1
    }
]

RUNS_PER_UTTERANCE = 30  # Minimum runs per utterance shape
SERVER_URL = "http://localhost:8000"
DB_PATH = "data/session.db"


async def dispatch_utterance(client: httpx.AsyncClient, utterance: str, wait: bool = True) -> Dict[str, Any]:
    """Dispatch a single utterance via the test endpoint."""
    try:
        response = await client.post(
            f"{SERVER_URL}/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "wait_for_results": wait,
                "timeout_seconds": 60
            },
            timeout=90.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


async def run_utterance_batch(utterance_data: Dict[str, Any], run_count: int) -> List[Dict]:
    """Run a single utterance shape multiple times and collect results."""
    name = utterance_data["name"]
    utterance = utterance_data["utterance"]
    results = []

    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"Utterance: {utterance[:80]}...")
    print(f"Runs: {run_count}")
    print(f"{'='*60}")

    async with httpx.AsyncClient() as client:
        for i in range(run_count):
            print(f"  Run {i+1}/{run_count}...", end=" ", flush=True)

            start_time = time.time()
            result = await dispatch_utterance(client, utterance, wait=True)
            elapsed = time.time() - start_time

            if result:
                print(f"✓ ({elapsed:.1f}s)")
                results.append({
                    "run": i + 1,
                    "utterance": utterance,
                    "response": result,
                    "wall_time": elapsed,
                    "timestamp": datetime.now().isoformat()
                })
            else:
                print("✗ Failed")

            # Small delay between runs to avoid overwhelming the system
            await asyncio.sleep(0.5)

    return results


async def collect_timing_data() -> List[Dict[str, Any]]:
    """Collect all timing data from the dispatch_timings table."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM dispatch_timings") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


def calculate_percentiles(data: List[float], percentiles: List[float]) -> Dict[str, float]:
    """Calculate percentiles for a list of values."""
    if not data:
        return {p: None for p in percentiles}

    sorted_data = sorted(data)
    return {
        p: sorted_data[int(len(sorted_data) * p / 100)]
        for p in percentiles
    }


def analyze_timings(timings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Analyze timing data and calculate p50/p95 for each stage."""

    stages = [
        "router_ms",
        "fetch_first_source_ms",
        "fetch_total_ms",
        "synthesize_first_token_ms",
        "synthesize_total_ms",
        "escalate_ms",
        "sse_emit_ms",
        "stt_ms",
        "first_render_ms"
    ]

    analysis = {}

    for stage in stages:
        # Filter out None/null values
        values = [t[stage] for t in timings if t.get(stage) is not None]

        if values:
            percentiles = calculate_percentiles(values, [50, 95])
            analysis[stage] = {
                "count": len(values),
                "p50": percentiles[50],
                "p95": percentiles[95],
                "min": min(values),
                "max": max(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values)
            }
        else:
            analysis[stage] = {
                "count": 0,
                "p50": None,
                "p95": None,
                "min": None,
                "max": None,
                "mean": None,
                "median": None
            }

    # Calculate e2e timing: router + fetch_total + synthesize_total + sse_emit
    # This is server-side e2e, not including client STT and render
    e2e_values = []
    for t in timings:
        if all(t.get(k) is not None for k in ["router_ms", "fetch_total_ms", "synthesize_total_ms", "sse_emit_ms"]):
            e2e = t["router_ms"] + t["fetch_total_ms"] + t["synthesize_total_ms"] + t["sse_emit_ms"]
            e2e_values.append(e2e)

    if e2e_values:
        e2e_percentiles = calculate_percentiles(e2e_values, [50, 95])
        analysis["e2e_server_ms"] = {
            "count": len(e2e_values),
            "p50": e2e_percentiles[50],
            "p95": e2e_percentiles[95],
            "min": min(e2e_values),
            "max": max(e2e_values),
            "mean": statistics.mean(e2e_values),
            "median": statistics.median(e2e_values)
        }

    return analysis


def format_duration(ms: float) -> str:
    """Format milliseconds as human-readable duration."""
    if ms is None:
        return "N/A"
    if ms < 1000:
        return f"{ms:.0f}ms"
    else:
        return f"{ms/1000:.2f}s"


async def main():
    """Main execution."""
    print("="*60)
    print("Latency Baseline Measurement")
    print("="*60)
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Runs per utterance: {RUNS_PER_UTTERANCE}")
    print(f"Server: {SERVER_URL}")

    # Check server is healthy
    try:
        async with httpx.AsyncClient() as client:
            health = await client.get(f"{SERVER_URL}/health", timeout=5.0)
            health.raise_for_status()
            print(f"Server health: {health.json()}")
    except Exception as e:
        print(f"ERROR: Server not healthy: {e}")
        sys.exit(1)

    # Clear old timing data (optional - comment out if you want to keep history)
    print("\nClearing old timing data...")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM dispatch_timings")
        await db.execute("DELETE FROM results")
        await db.execute("DELETE FROM intents")
        await db.execute("DELETE FROM utterances")
        await db.execute("DELETE FROM topics")
        await db.execute("DELETE FROM sessions")
        await db.commit()
        print("Cleared old data")

    # Run each demo utterance
    all_results = []
    for utterance_data in DEMO_UTTERANCES:
        results = await run_utterance_batch(utterance_data, RUNS_PER_UTTERANCE)
        all_results.extend(results)

    print(f"\n{'='*60}")
    print("Data collection complete. Collecting timings from DB...")

    # Wait a bit for any remaining processing to complete
    await asyncio.sleep(2)

    # Collect timing data from database
    timings = await collect_timing_data()
    print(f"Collected {len(timings)} timing records")

    # Analyze timings
    analysis = analyze_timings(timings)

    # Print results
    print(f"\n{'='*60}")
    print("LATENCY ANALYSIS RESULTS")
    print(f"{'='*60}")

    stage_names = {
        "router_ms": "Intent Router",
        "fetch_first_source_ms": "Fetch - First Source",
        "fetch_total_ms": "Fetch - Window Close",
        "synthesize_first_token_ms": "Synthesize - First Token",
        "synthesize_total_ms": "Synthesize - Total",
        "escalate_ms": "Escalate (bead create)",
        "sse_emit_ms": "SSE Emit",
        "stt_ms": "STT (client-reported)",
        "first_render_ms": "First Render (client)",
        "e2e_server_ms": "End-to-End (server-side)"
    }

    print(f"\n{'Stage':<30} {'Count':>6} {'p50':>10} {'p95':>10} {'Min':>10} {'Max':>10}")
    print("-" * 78)

    for stage_key, stage_name in stage_names.items():
        if stage_key in analysis:
            data = analysis[stage_key]
            print(f"{stage_name:<30} {data['count']:>6} "
                  f"{format_duration(data['p50']):>10} "
                  f"{format_duration(data['p95']):>10} "
                  f"{format_duration(data['min']):>10} "
                  f"{format_duration(data['max']):>10}")

    # Save results to file
    results_file = Path("docs/notes/latency-baseline-2026-07.json")
    results_file.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "runs_per_utterance": RUNS_PER_UTTERANCE,
            "total_runs": len(all_results),
            "timing_records": len(timings)
        },
        "utterances": DEMO_UTTERANCES,
        "analysis": analysis,
        "raw_timings": timings
    }

    with open(results_file, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved to: {results_file}")

    # Check against budget
    print(f"\n{'='*60}")
    print("BUDGET CHECK")
    print(f"{'='*60}")

    budget_checks = [
        ("Intent Router", "router_ms", 500),
        ("Fetch Window Close", "fetch_total_ms", 1000),
        ("Synthesize First Token", "synthesize_first_token_ms", 1000),
        ("SSE Emit", "sse_emit_ms", 100),
        ("End-to-End (server)", "e2e_server_ms", 3000)
    ]

    budget_passed = True
    for stage_name, stage_key, budget_ms in budget_checks:
        if stage_key in analysis:
            p95 = analysis[stage_key].get("p95")
            if p95:
                status = "✓ PASS" if p95 <= budget_ms else "✗ FAIL"
                print(f"{stage_name:<30} {format_duration(p95):>10} vs {format_duration(budget_ms):>10} {status}")
                if p95 > budget_ms:
                    budget_passed = False

    print(f"\n{'='*60}")
    if budget_passed:
        print("✓ ALL STAGES WITHIN BUDGET")
    else:
        print("✗ SOME STAGES EXCEED BUDGET")
    print(f"{'='*60}")

    print(f"\nCompleted: {datetime.now().isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
