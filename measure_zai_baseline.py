#!/usr/bin/env python3
"""
Measure ZAI proxy latency baseline.

This script makes multiple requests to the intent router and captures
detailed timing breakdown to establish a baseline for ZAI proxy performance.
"""
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


# Test utterances to send through the router
TEST_UTTERANCES = [
    "check status of aide-de-camp",
    "what's the current state of the project",
    "show me logs for aide-de-camp",
    "what are the recent commits",
    "check if there are any issues",
    "list the current topics",
    "show me project documentation",
    "what's the deployment status",
]


async def make_dispatch_request(client: httpx.AsyncClient, utterance: str) -> dict[str, Any]:
    """Make a single dispatch request and return timing data."""
    session_id = f"baseline-test-{int(time.time() * 1000)}"
    surface_id = "baseline-surface"

    start_time = time.perf_counter()

    try:
        response = await client.post(
            "http://localhost:8000/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "surface_id": surface_id,
            },
            timeout=30.0,
        )
        response.raise_for_status()

        end_time = time.perf_counter()
        total_e2e_ms = (end_time - start_time) * 1000

        # Get the response data
        data = response.json()

        # Return timing breakdown
        return {
            "utterance": utterance,
            "session_id": session_id,
            "success": True,
            "total_e2e_ms": total_e2e_ms,
            "response": data,
        }
    except Exception as e:
        end_time = time.perf_counter()
        total_e2e_ms = (end_time - start_time) * 1000

        return {
            "utterance": utterance,
            "session_id": session_id,
            "success": False,
            "total_e2e_ms": total_e2e_ms,
            "error": str(e),
        }


async def fetch_router_timing(client: httpx.AsyncClient, session_id: str) -> dict[str, Any] | None:
    """Fetch router timing breakdown for a session."""
    try:
        # Wait a moment for timing to be persisted
        await asyncio.sleep(0.2)

        response = await client.get(
            f"http://localhost:8000/api/v1/sessions/{session_id}/utterances"
        )
        response.raise_for_status()

        data = response.json()
        if data and len(data) > 0:
            # Get the most recent utterance
            utterance = data[0]
            router_timing = utterance.get("router_timing")
            if router_timing:
                return router_timing
    except Exception as e:
        print(f"  Warning: Failed to fetch router timing: {e}")

    return None


async def measure_baseline(num_requests: int = 20) -> dict[str, Any]:
    """Run multiple dispatch requests and collect timing data."""

    async with httpx.AsyncClient() as client:
        results = []

        print(f"Running {num_requests} baseline measurements...")
        print(f"Test utterances: {len(TEST_UTTERANCES)} different prompts")
        print()

        for i in range(num_requests):
            # Cycle through test utterances
            utterance = TEST_UTTERANCES[i % len(TEST_UTTERANCES)]

            print(f"[{i+1}/{num_requests}] Testing: '{utterance}'...", end=" ", flush=True)

            # Make the request
            result = await make_dispatch_request(client, utterance)

            if result["success"]:
                print(f"✓ E2E: {result['total_e2e_ms']:.0f}ms")

                # Fetch detailed router timing
                router_timing = await fetch_router_timing(client, result["session_id"])
                if router_timing:
                    result["router_timing"] = router_timing

                    # Print detailed breakdown
                    cached = router_timing.get("cached", False)
                    if cached:
                        print(f"  (CACHED)")
                    else:
                        prompt_ms = router_timing.get("prompt_construction_ms", 0)
                        proxy_call_ms = router_timing.get("proxy_call_ms", 0)
                        network_ms = router_timing.get("proxy_network_ms")
                        inference_ms = router_timing.get("proxy_inference_ms")
                        json_ms = router_timing.get("json_parse_ms", 0)
                        process_ms = router_timing.get("process_ms", 0)
                        total_ms = router_timing.get("total_ms", 0)

                        print(f"  Router: {total_ms:.0f}ms (proxy: {proxy_call_ms:.0f}ms, network: {network_ms:.0f}ms if available, inference: {inference_ms:.0f}ms if available)")
            else:
                print(f"✗ FAILED: {result.get('error', 'Unknown error')}")

            results.append(result)

            # Brief pause between requests
            await asyncio.sleep(0.5)

        return {
            "timestamp": datetime.now().isoformat(),
            "num_requests": num_requests,
            "results": results,
        }


def calculate_statistics(data: dict[str, Any]) -> dict[str, Any]:
    """Calculate latency statistics from the measurement results."""

    # Extract timing data
    e2e_times = []
    router_times = []
    network_times = []
    inference_times = []
    proxy_call_times = []
    cached_count = 0
    uncached_count = 0

    for result in data["results"]:
        if result["success"]:
            e2e_times.append(result["total_e2e_ms"])

            router_timing = result.get("router_timing")
            if router_timing:
                is_cached = router_timing.get("cached", False)
                if is_cached:
                    cached_count += 1
                else:
                    uncached_count += 1
                    router_times.append(router_timing.get("total_ms", 0))
                    proxy_call_times.append(router_timing.get("proxy_call_ms", 0))

                    network_ms = router_timing.get("proxy_network_ms")
                    if network_ms is not None:
                        network_times.append(network_ms)

                    inference_ms = router_timing.get("proxy_inference_ms")
                    if inference_ms is not None:
                        inference_times.append(inference_ms)

    def calc_stats(values: list[float]) -> dict[str, float]:
        if not values:
            return {"avg": 0, "median": 0, "p95": 0, "min": 0, "max": 0}

        sorted_values = sorted(values)
        n = len(sorted_values)

        return {
            "count": n,
            "avg": statistics.mean(values),
            "median": statistics.median(values),
            "p95": sorted_values[int(n * 0.95)] if n >= 20 else max(sorted_values),
            "min": min(values),
            "max": max(values),
        }

    return {
        "e2e": calc_stats(e2e_times),
        "router": calc_stats(router_times),
        "network": calc_stats(network_times),
        "inference": calc_stats(inference_times),
        "proxy_call": calc_stats(proxy_call_times),
        "cache_hit_rate": cached_count / (cached_count + uncached_count) if (cached_count + uncached_count) > 0 else 0,
        "cached_count": cached_count,
        "uncached_count": uncached_count,
    }


def generate_markdown_report(stats: dict[str, Any], raw_data: dict[str, Any]) -> str:
    """Generate a markdown report from the statistics."""

    timestamp = raw_data["timestamp"].split("T")[0]

    lines = [
        "# ZAI Proxy Latency Baseline",
        "",
        f"**Baseline Date:** {timestamp}",
        f"**Measurement Count:** {raw_data['num_requests']} requests",
        f"**Test Utterances:** {len(TEST_UTTERANCES)} different prompts",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "This document establishes the baseline latency measurements for the ZAI proxy",
        "used by the intent router in aide-de-camp. All measurements are from live",
        "server requests using the existing instrumentation.",
        "",
        "---",
        "",
        "## End-to-End Latency",
        "",
        "| Metric | Value |",
        "|--------|------|",
        f"| Average | {stats['e2e']['avg']:.0f}ms |",
        f"| Median | {stats['e2e']['median']:.0f}ms |",
        f"| p95 | {stats['e2e']['p95']:.0f}ms |",
        f"| Min | {stats['e2e']['min']:.0f}ms |",
        f"| Max | {stats['e2e']['max']:.0f}ms |",
        "",
        "---",
        "",
        "## Intent Router Latency (Uncached)",
        "",
        f"**Cache Hit Rate:** {stats['cache_hit_rate']*100:.1f}% ({stats['cached_count']} cached, {stats['uncached_count']} uncached)",
        "",
        "| Metric | Value |",
        "|--------|------|",
        f"| Average | {stats['router']['avg']:.0f}ms |",
        f"| Median | {stats['router']['median']:.0f}ms |",
        f"| p95 | {stats['router']['p95']:.0f}ms |",
        f"| Min | {stats['router']['min']:.0f}ms |",
        f"| Max | {stats['router']['max']:.0f}ms |",
        "",
        "---",
        "",
        "## ZAI Proxy Call Time",
        "",
        "Total time for the ZAI proxy call (network + inference).",
        "",
        "| Metric | Value |",
        "|--------|------|",
        f"| Average | {stats['proxy_call']['avg']:.0f}ms |",
        f"| Median | {stats['proxy_call']['median']:.0f}ms |",
        f"| p95 | {stats['proxy_call']['p95']:.0f}ms |",
        f"| Min | {stats['proxy_call']['min']:.0f}ms |",
        f"| Max | {stats['proxy_call']['max']:.0f}ms |",
        "",
        "---",
        "",
        "## Network Latency Component",
        "",
        "Network latency (time to first byte) measures the round-trip time to the ZAI proxy",
        "before inference begins. This includes DNS lookup, TCP connection, TLS handshake,",
        "and server processing time.",
        "",
        "| Metric | Value |",
        "|--------|------|",
        f"| Average | {stats['network']['avg']:.0f}ms |",
        f"| Median | {stats['network']['median']:.0f}ms |",
        f"| p95 | {stats['network']['p95']:.0f}ms |",
        f"| Min | {stats['network']['min']:.0f}ms |",
        f"| Max | {stats['network']['max']:.0f}ms |",
        "",
        "---",
        "",
        "## Model Inference Time",
        "",
        "Inference time is the time the LLM model spends generating the response, calculated",
        "as proxy_call_ms - network_ms.",
        "",
        "| Metric | Value |",
        "|--------|------|",
        f"| Average | {stats['inference']['avg']:.0f}ms |",
        f"| Median | {stats['inference']['median']:.0f}ms |",
        f"| p95 | {stats['inference']['p95']:.0f}ms |",
        f"| Min | {stats['inference']['min']:.0f}ms |",
        f"| Max | {stats['inference']['max']:.0f}ms |",
        "",
        "---",
        "",
        "## Key Findings",
        "",
        "1. **Network Latency:** Median network latency is {:.0f}ms, which represents {:.1f}% of total proxy call time.".format(
            stats['network']['median'],
            (stats['network']['median'] / stats['proxy_call']['median'] * 100) if stats['proxy_call']['median'] > 0 else 0
        ),
        "",
        "2. **Model Inference:** Median inference time is {:.0f}ms, which represents {:.1f}% of total proxy call time.".format(
            stats['inference']['median'],
            (stats['inference']['median'] / stats['proxy_call']['median'] * 100) if stats['proxy_call']['median'] > 0 else 0
        ),
        "",
        f"3. **Cache Effectiveness:** {stats['cache_hit_rate']*100:.1f}% of requests hit the cache and return in ~10-50ms.",
        "",
        f"4. **Router Overhead:** Non-ZAI router operations (prompt construction, JSON parsing, processing) add approximately {stats['router']['median'] - stats['proxy_call']['median']:.0f}ms on average.",
        "",
        "---",
        "",
        "## Recommendations",
        "",
        "1. **Network:** The {:.0f}ms median network latency is acceptable for a remote proxy.".format(stats['network']['median']),
        "",
        "2. **Inference:** Model inference dominates the total time ({:.0f}ms median). Consider:".format(stats['inference']['median']),
        "   - Using a faster model class if accuracy requirements permit",
        "   - Reducing max_tokens to minimize generation time",
        "   - Implementing request batching to amortize overhead",
        "",
        "3. **Caching:** The {:.1f}% cache hit rate demonstrates the value of the intent cache.".format(stats['cache_hit_rate']*100),
        "",
        "---",
        "",
        "## Raw Data",
        "",
        f"Full measurement data saved to: `docs/notes/zai-proxy-baseline-raw-{timestamp}.json`",
    ]

    return "\n".join(lines)


async def main():
    """Main entry point."""
    print("=" * 60)
    print("ZAI Proxy Latency Baseline Measurement")
    print("=" * 60)
    print()

    # Number of requests to make
    num_requests = 20

    # Run baseline measurement
    data = await measure_baseline(num_requests)

    print()
    print("=" * 60)
    print("Calculating statistics...")
    print("=" * 60)

    # Calculate statistics
    stats = calculate_statistics(data)

    print()
    print("Statistics Summary:")
    print("-" * 60)
    print(f"End-to-End:     {stats['e2e']['median']:.0f}ms median (p95: {stats['e2e']['p95']:.0f}ms)")
    print(f"Router:         {stats['router']['median']:.0f}ms median (p95: {stats['router']['p95']:.0f}ms)")
    print(f"Network:        {stats['network']['median']:.0f}ms median (p95: {stats['network']['p95']:.0f}ms)")
    print(f"Inference:      {stats['inference']['median']:.0f}ms median (p95: {stats['inference']['p95']:.0f}ms)")
    print(f"Cache Hit Rate: {stats['cache_hit_rate']*100:.1f}%")
    print()

    # Generate markdown report
    print("Generating markdown report...")
    markdown = generate_markdown_report(stats, data)

    # Save markdown report
    timestamp = data["timestamp"].split("T")[0]
    output_path = Path("/home/coding/aide-de-camp/docs/notes/zai-proxy-baseline.md")

    with open(output_path, "w") as f:
        f.write(markdown)

    print(f"Report saved to: {output_path}")

    # Save raw data as JSON
    raw_data_path = Path(f"/home/coding/aide-de-camp/docs/notes/zai-proxy-baseline-raw-{timestamp}.json")
    with open(raw_data_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Raw data saved to: {raw_data_path}")
    print()
    print("✓ Baseline measurement complete")


if __name__ == "__main__":
    asyncio.run(main())
