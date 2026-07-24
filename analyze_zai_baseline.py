#!/usr/bin/env python3
"""
Analyze ZAI proxy latency baseline from database records.

This script queries the session database for router timing breakdowns
and calculates statistics to establish a baseline for ZAI proxy performance.
"""
import json
import sqlite3
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


def get_router_timing_data(db_path: str, limit: int = 100) -> list[dict[str, Any]]:
    """Fetch router timing breakdowns from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
    SELECT id, raw_text, router_timing_breakdown, created_at
    FROM utterances
    WHERE router_timing_breakdown IS NOT NULL
    ORDER BY created_at DESC
    LIMIT ?
    """

    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        utterance_id, raw_text, timing_json, created_at = row
        try:
            timing = json.loads(timing_json)
            results.append({
                "id": utterance_id,
                "utterance": raw_text,
                "timing": timing,
                "created_at": created_at,
            })
        except json.JSONDecodeError:
            continue

    return results


def calculate_statistics(values: list[float]) -> dict[str, Any]:
    """Calculate latency statistics from a list of values."""
    if not values:
        return {
            "count": 0,
            "avg": 0,
            "median": 0,
            "p95": 0,
            "p99": 0,
            "min": 0,
            "max": 0,
        }

    sorted_values = sorted(values)
    n = len(sorted_values)

    return {
        "count": n,
        "avg": statistics.mean(values),
        "median": statistics.median(values),
        "p95": sorted_values[int(n * 0.95)] if n >= 20 else sorted_values[-1],
        "p99": sorted_values[int(n * 0.99)] if n >= 100 else sorted_values[-1],
        "min": min(values),
        "max": max(values),
    }


def analyze_router_timing(data: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze router timing data and calculate statistics."""

    # Extract timing components
    total_times = []
    proxy_call_times = []
    network_times = []
    inference_times = []
    prompt_times = []
    json_parse_times = []
    process_times = []

    cached_count = 0
    uncached_count = 0

    for entry in data:
        timing = entry["timing"]

        is_cached = timing.get("cached", False)
        if is_cached:
            cached_count += 1
            continue

        uncached_count += 1

        # Extract timing values (skip if cached)
        total_times.append(timing.get("total_ms", 0))
        proxy_call_times.append(timing.get("proxy_call_ms", 0))

        network_ms = timing.get("proxy_network_ms")
        if network_ms is not None:
            network_times.append(network_ms)

        inference_ms = timing.get("proxy_inference_ms")
        if inference_ms is not None:
            inference_times.append(inference_ms)

        prompt_times.append(timing.get("prompt_construction_ms", 0))
        json_parse_times.append(timing.get("json_parse_ms", 0))
        process_times.append(timing.get("process_ms", 0))

    return {
        "total_ms": calculate_statistics(total_times),
        "proxy_call_ms": calculate_statistics(proxy_call_times),
        "network_ms": calculate_statistics(network_times),
        "inference_ms": calculate_statistics(inference_times),
        "prompt_construction_ms": calculate_statistics(prompt_times),
        "json_parse_ms": calculate_statistics(json_parse_times),
        "process_ms": calculate_statistics(process_times),
        "cache_stats": {
            "cached_count": cached_count,
            "uncached_count": uncached_count,
            "cache_hit_rate": cached_count / (cached_count + uncached_count) if (cached_count + uncached_count) > 0 else 0,
        }
    }


def generate_markdown_report(stats: dict[str, Any], sample_count: int) -> str:
    """Generate a markdown report from the statistics."""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# ZAI Proxy Latency Baseline",
        "",
        f"**Baseline Date:** {timestamp}",
        f"**Analysis Type:** Database record analysis",
        f"**Sample Count:** {stats['total_ms']['count']} uncached router calls",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "This document establishes the baseline latency measurements for the ZAI proxy",
        "used by the intent router in aide-de-camp. Measurements are from actual router",
        "timing breakdowns stored in the session database.",
        "",
        "---",
        "",
        "## Intent Router Total Time",
        "",
        "Total router time includes prompt construction, ZAI proxy call, JSON parsing,",
        "and intent processing.",
        "",
        f"| Metric | Value |",
        f"|--------|------|",
        f"| Count | {stats['total_ms']['count']} samples |",
        f"| Average | {stats['total_ms']['avg']:.0f}ms |",
        f"| Median | {stats['total_ms']['median']:.0f}ms |",
        f"| p95 | {stats['total_ms']['p95']:.0f}ms |",
        f"| p99 | {stats['total_ms']['p99']:.0f}ms |",
        f"| Min | {stats['total_ms']['min']:.0f}ms |",
        f"| Max | {stats['total_ms']['max']:.0f}ms |",
        "",
        "---",
        "",
        "## ZAI Proxy Call Time",
        "",
        "Total time for the ZAI proxy call (network + inference).",
        "",
        f"| Metric | Value |",
        f"|--------|------|",
        f"| Average | {stats['proxy_call_ms']['avg']:.0f}ms |",
        f"| Median | {stats['proxy_call_ms']['median']:.0f}ms |",
        f"| p95 | {stats['proxy_call_ms']['p95']:.0f}ms |",
        f"| p99 | {stats['proxy_call_ms']['p99']:.0f}ms |",
        f"| Min | {stats['proxy_call_ms']['min']:.0f}ms |",
        f"| Max | {stats['proxy_call_ms']['max']:.0f}ms |",
        "",
        "---",
        "",
        "## Network Latency Component",
        "",
        "Network latency (time to first byte) measures the round-trip time to the ZAI proxy",
        "before inference begins. This includes DNS lookup, TCP connection, TLS handshake,",
        "and server processing time.",
        "",
        f"| Metric | Value |",
        f"|--------|------|",
        f"| Average | {stats['network_ms']['avg']:.0f}ms |",
        f"| Median | {stats['network_ms']['median']:.0f}ms |",
        f"| p95 | {stats['network_ms']['p95']:.0f}ms |",
        f"| p99 | {stats['network_ms']['p99']:.0f}ms |",
        f"| Min | {stats['network_ms']['min']:.0f}ms |",
        f"| Max | {stats['network_ms']['max']:.0f}ms |",
        "",
        "---",
        "",
        "## Model Inference Time",
        "",
        "Inference time is the time the LLM model spends generating the response, calculated",
        "as proxy_call_ms - network_ms.",
        "",
        f"| Metric | Value |",
        f"|--------|------|",
        f"| Average | {stats['inference_ms']['avg']:.0f}ms |",
        f"| Median | {stats['inference_ms']['median']:.0f}ms |",
        f"| p95 | {stats['inference_ms']['p95']:.0f}ms |",
        f"| p99 | {stats['inference_ms']['p99']:.0f}ms |",
        f"| Min | {stats['inference_ms']['min']:.0f}ms |",
        f"| Max | {stats['inference_ms']['max']:.0f}ms |",
        "",
        "---",
        "",
        "## Router Overhead Breakdown",
        "",
        "Non-ZAI router operations: prompt construction, JSON parsing, and intent processing.",
        "",
        "| Component | Median | p95 |",
        "|-----------|--------|-----|",
        f"| Prompt Construction | {stats['prompt_construction_ms']['median']:.2f}ms | {stats['prompt_construction_ms']['p95']:.2f}ms |",
        f"| JSON Parsing | {stats['json_parse_ms']['median']:.2f}ms | {stats['json_parse_ms']['p95']:.2f}ms |",
        f"| Intent Processing | {stats['process_ms']['median']:.2f}ms | {stats['process_ms']['p95']:.2f}ms |",
        "",
        "---",
        "",
        "## Cache Statistics",
        "",
        f"| Metric | Value |",
        f"|--------|------|",
        f"| Cached Requests | {stats['cache_stats']['cached_count']} |",
        f"| Uncached Requests | {stats['cache_stats']['uncached_count']} |",
        f"| Cache Hit Rate | {stats['cache_stats']['cache_hit_rate']*100:.1f}% |",
        "",
        "---",
        "",
        "## Key Findings",
        "",
        "### Network vs. Inference Breakdown",
        "",
        "The ZAI proxy call consists of two components:",
        "",
        f"1. **Network Latency:** Median {stats['network_ms']['median']:.0f}ms, which represents",
        f"   {stats['network_ms']['median'] / stats['proxy_call_ms']['median'] * 100:.1f}% of total proxy call time.",
        "",
        f"2. **Model Inference:** Median {stats['inference_ms']['median']:.0f}ms, which represents",
        f"   {stats['inference_ms']['median'] / stats['proxy_call_ms']['median'] * 100:.1f}% of total proxy call time.",
        "",
        "### Performance Analysis",
        "",
    ]

    # Add performance analysis
    if stats['inference_ms']['median'] < 10:
        lines.extend([
            "",
            "⚠️ **UNUSUAL INFERENCE TIME:** The measured inference time (<10ms median) is",
            "significantly lower than expected for LLM inference. This suggests that the",
            "timing measurement may be capturing only the token streaming setup time, not",
            "the actual model inference duration. The network latency component dominates",
            "the measured time, which may indicate that the 'first byte' measurement includes",
            "most of the inference work.",
        ])
    else:
        lines.extend([
            "",
            f"✓ **Expected Inference Time:** The {stats['inference_ms']['median']:.0f}ms median",
            "inference time is consistent with LLM model processing expectations.",
        ])

    lines.extend([
        "",
        f"✓ **Cache Effectiveness:** {stats['cache_stats']['cache_hit_rate']*100:.1f}% cache hit rate",
        "   demonstrates the value of the intent cache for repeated queries.",
        "",
        f"✓ **Router Overhead:** Non-proxy operations (prompt construction + JSON parsing +",
        f"   processing) add only ~{stats['prompt_construction_ms']['median'] + stats['json_parse_ms']['median'] + stats['process_ms']['median']:.2f}ms",
        "   median, which is negligible compared to proxy call time.",
        "",
        "---",
        "",
        "## Comparison with Budget",
        "",
        "Based on the latency budget from plan.md:",
        "",
        f"| Metric | Budget | Measured | Status |",
        f"|--------|--------|----------|--------|",
        f"| Router p50 | ~500ms | {stats['total_ms']['median']:.0f}ms | {'✓ PASS' if stats['total_ms']['median'] <= 500 else '❌ FAIL'} | {stats['total_ms']['median']/500:.1f}× |",
        f"| Router p95 | ~1500ms | {stats['total_ms']['p95']:.0f}ms | {'✓ PASS' if stats['total_ms']['p95'] <= 1500 else '❌ FAIL'} | {stats['total_ms']['p95']/1500:.1f}× |",
        "",
    ])

    # Add recommendations
    if stats['total_ms']['median'] > 500 or stats['total_ms']['p95'] > 1500:
        lines.extend([
            "",
            "### Recommendations",
            "",
            "1. **Investigate Timing Measurement:** The unusually low inference time suggests",
            "   the timing instrumentation may not be capturing the full model inference",
            "   duration. Consider adding token-stream timing to measure true inference time.",
            "",
            "2. **Consider Faster Model:** If actual router time is indeed {0:.0f}ms median,"     .format(stats['total_ms']['median']),
            "   consider using a faster model class (Haiku) or optimizing the prompt to",
            "   reduce processing time.",
            "",
            "3. **Leverage Cache:** The {:.1f}% cache hit rate shows caching is effective.".format(stats['cache_stats']['cache_hit_rate']*100),
            "   Consider expanding cache TTL or implementing smarter cache keys.",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Data Source",
        "",
        f"Analysis based on {stats['total_ms']['count']} router timing records from the",
        "session database (`data/session.db`). Only uncached requests are included in",
        "statistics.",
        "",
        "---",
        "",
        f"**Generated:** {timestamp}",
    ])

    return "\n".join(lines)


def main():
    """Main entry point."""
    print("=" * 60)
    print("ZAI Proxy Latency Baseline Analysis")
    print("=" * 60)
    print()

    db_path = "/home/coding/aide-de-camp/data/session.db"
    sample_limit = 100

    # Fetch timing data from database
    print(f"Fetching up to {sample_limit} recent router timing records...")
    data = get_router_timing_data(db_path, limit=sample_limit)

    print(f"Found {len(data)} total records")
    print()

    # Analyze timing data
    print("Analyzing timing breakdowns...")
    stats = analyze_router_timing(data)

    # Print summary
    print("Statistics Summary:")
    print("-" * 60)
    print(f"Total Samples: {stats['total_ms']['count']} uncached requests")
    print(f"Cache Hit Rate: {stats['cache_stats']['cache_hit_rate']*100:.1f}%")
    print()
    print("Router Total Time:")
    print(f"  Median: {stats['total_ms']['median']:.0f}ms (p95: {stats['total_ms']['p95']:.0f}ms)")
    print()
    print("ZAI Proxy Call:")
    print(f"  Median: {stats['proxy_call_ms']['median']:.0f}ms (p95: {stats['proxy_call_ms']['p95']:.0f}ms)")
    print()
    print("Network Latency:")
    print(f"  Median: {stats['network_ms']['median']:.0f}ms (p95: {stats['network_ms']['p95']:.0f}ms)")
    print()
    print("Model Inference:")
    print(f"  Median: {stats['inference_ms']['median']:.0f}ms (p95: {stats['inference_ms']['p95']:.0f}ms)")
    print()

    # Generate markdown report
    print("Generating markdown report...")
    markdown = generate_markdown_report(stats, len(data))

    # Save markdown report
    output_path = Path("/home/coding/aide-de-camp/docs/notes/zai-proxy-baseline.md")
    with open(output_path, "w") as f:
        f.write(markdown)

    print(f"Report saved to: {output_path}")
    print()
    print("✓ Baseline analysis complete")


if __name__ == "__main__":
    main()
