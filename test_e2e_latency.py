#!/usr/bin/env python3
"""
End-to-end latency test script for ADC intent router.

Tests three shapes:
1. Multi-intent status: "Has the pbx web caught up, and what's the state of whisper stt?"
2. Lookup logs: "Pull up the recent logs for whisper stt"
3. Brainstorm: "Brainstorm improvements to the pbx web deployment pipeline"

Collects timing data for 30 runs per shape.
"""
import asyncio
import json
import time
import httpx
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List


# Test shapes from baseline analysis
TEST_SHAPES = {
    "multi-intent": "Has the pbx web caught up, and what's the state of whisper stt?",
    "lookup": "Pull up the recent logs for whisper stt",
    "brainstorm": "Brainstorm improvements to the pbx web deployment pipeline",
}

RUNS_PER_SHAPE = 30
API_BASE = "http://localhost:8000"


async def run_dispatch(utterance: str, session_id: str) -> Dict:
    """Run a single dispatch and collect timing data."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        start = time.monotonic()

        response = await client.post(
            f"{API_BASE}/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "surface_id": f"test-{session_id}",
            },
        )
        dispatch_time = (time.monotonic() - start) * 1000

        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "dispatch_ms": dispatch_time}

        data = response.json()
        intent_ids = data.get("intent_ids", [])

        if not intent_ids:
            return {"error": "No intents returned", "dispatch_ms": dispatch_time}

        # Wait a bit for processing to complete
        await asyncio.sleep(0.5)

        # Fetch timing data for the intents
        timings = []
        for intent_id in intent_ids[:3]:  # Limit to first 3 intents
            try:
                timing_response = await client.get(
                    f"{API_BASE}/api/v1/timings/percentiles",
                )
                if timing_response.status_code == 200:
                    all_percentiles = timing_response.json()
                    # Extract relevant timing info
                    timings.append({
                        "intent_id": intent_id,
                        "router_ms": all_percentiles.get("router_ms", {}).get("p50"),
                        "fetch_total_ms": all_percentiles.get("fetch_total_ms", {}).get("p50"),
                        "synthesize_total_ms": all_percentiles.get("synthesize_total_ms", {}).get("p50"),
                    })
            except Exception:
                pass

        return {
            "dispatch_ms": dispatch_time,
            "intent_count": len(intent_ids),
            "intent_ids": intent_ids,
            "sample_timings": timings,
        }


async def test_shape(shape_name: str, utterance: str, runs: int) -> List[Dict]:
    """Run multiple tests for a single shape."""
    print(f"\nTesting {shape_name} ({runs} runs)...")
    results = []

    for i in range(runs):
        session_id = f"test-{shape_name}-{int(time.time())}-{i}"
        try:
            result = await run_dispatch(utterance, session_id)
            result["run"] = i
            result["shape"] = shape_name
            result["timestamp"] = datetime.utcnow().isoformat()
            results.append(result)

            if i % 5 == 0:
                print(f"  {i}/{runs} runs complete...")
        except Exception as e:
            print(f"  Run {i} failed: {e}")
            results.append({
                "run": i,
                "shape": shape_name,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            })

    return results


def compute_stats(timings_ms: List[float]) -> Dict:
    """Compute percentile statistics from a list of millisecond values."""
    if not timings_ms:
        return {"p50": None, "p95": None, "min": None, "max": None, "mean": None, "count": 0}

    sorted_vals = sorted(timings_ms)
    n = len(sorted_vals)

    return {
        "p50": sorted_vals[n // 2],
        "p95": sorted_vals[int(n * 0.95)] if n >= 20 else sorted_vals[-1],
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "mean": sum(sorted_vals) / n,
        "count": n,
    }


async def main():
    """Run all latency tests."""
    print("Starting end-to-end latency tests...")
    print(f"Target: {RUNS_PER_SHAPE} runs per shape")
    print(f"API endpoint: {API_BASE}")

    all_results = []
    shape_results = {}

    for shape_name, utterance in TEST_SHAPES.items():
        results = await test_shape(shape_name, utterance, RUNS_PER_SHAPE)
        shape_results[shape_name] = results
        all_results.extend(results)

    # Compute statistics per shape
    summary = {}
    for shape_name, results in shape_results.items():
        dispatch_times = [r.get("dispatch_ms") for r in results if r.get("dispatch_ms") is not None]

        stats = compute_stats(dispatch_times)
        stats["successful_runs"] = len([r for r in results if "error" not in r])
        stats["failed_runs"] = len([r for r in results if "error" in r])

        summary[shape_name] = stats

    # Print summary
    print("\n" + "="*60)
    print("LATENCY TEST SUMMARY")
    print("="*60)

    for shape_name, stats in summary.items():
        print(f"\n{shape_name.upper()}:")
        print(f"  Successful runs: {stats['successful_runs']}/{stats['count']}")
        print(f"  Dispatch latency (p50): {stats['p50']:.0f}ms")
        print(f"  Dispatch latency (p95): {stats['p95']:.0f}ms")
        print(f"  Dispatch latency (min): {stats['min']:.0f}ms")
        print(f"  Dispatch latency (max): {stats['max']:.0f}ms")
        print(f"  Dispatch latency (mean): {stats['mean']:.0f}ms")

    # Budget comparison
    print("\n" + "="*60)
    print("BUDGET COMPARISON")
    print("="*60)

    router_target = 500  # ms
    e2e_target = 3000  # ms

    print(f"\nRouter budget: ~{router_target}ms")
    print(f"E2E budget: <{e2e_target}ms")

    for shape_name, stats in summary.items():
        p50 = stats.get("p50", 0)
        p95 = stats.get("p95", 0)
        p50_status = "✅" if p50 < router_target else "❌"
        p95_status = "✅" if p95 < router_target else "❌"
        print(f"\n{shape_name}:")
        print(f"  p50: {p50:.0f}ms {p50_status} ({p50/router_target:.1f}x budget)")
        print(f"  p95: {p95:.0f}ms {p95_status} ({p95/router_target:.1f}x budget)")

    # Save results
    output_file = Path("/tmp/e2e-latency-test-results.json")
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.utcnow().isoformat(),
            "runs_per_shape": RUNS_PER_SHAPE,
            "shapes": TEST_SHAPES,
            "summary": summary,
            "all_results": all_results,
        }, f, indent=2)

    print(f"\nResults saved to {output_file}")

    # Compare with baseline
    print("\n" + "="*60)
    print("COMPARISON WITH JULY 2026 BASELINE")
    print("="*60)

    baseline = {
        "multi-intent": {"p50": 2074, "p95": 4301},
        "lookup": {"p50": 1640, "p95": 3298},
        "brainstorm": {"p50": 1587, "p95": 2527},
    }

    for shape_name, stats in summary.items():
        if shape_name in baseline:
            base_p50 = baseline[shape_name]["p50"]
            base_p95 = baseline[shape_name]["p95"]
            curr_p50 = stats.get("p50", 0)
            curr_p95 = stats.get("p95", 0)

            p50_change = ((curr_p50 - base_p50) / base_p50) * 100
            p95_change = ((curr_p95 - base_p95) / base_p95) * 100

            print(f"\n{shape_name}:")
            print(f"  p50: {base_p50}ms → {curr_p50:.0f}ms ({p50_change:+.1f}%)")
            print(f"  p95: {base_p95}ms → {curr_p95:.0f}ms ({p95_change:+.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
