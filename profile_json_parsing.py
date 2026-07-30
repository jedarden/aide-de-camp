#!/usr/bin/env python3
"""
Profile JSON parsing baseline for intent router.

Measures time spent on:
1. Fence removal (strip_markdown_fences)
2. JSON parsing (json.loads)
3. Total parsing time

Samples both fenced and bare JSON with statistical significance.
"""
import json
import statistics
import time
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class ParseSample:
    """Result of a single parse operation."""
    total_ms: float
    fence_ms: float
    json_ms: float
    success: bool
    error: str = ""


@dataclass
class BaselineStats:
    """Statistical summary of parsing performance."""
    metric_name: str
    samples: int
    avg_ms: float
    median_ms: float
    min_ms: float
    max_ms: float
    stdev_ms: float
    percentile_95_ms: float


def strip_markdown_fences(raw: str) -> str:
    """
    Current implementation: optimized position-based fence removal.

    Uses find()/rfind() for single-pass fence removal.
    Copied from src/llm/response_parser.py for profiling.
    """
    if not raw or not raw.strip():
        return raw

    text = raw.strip()

    if text.startswith("```"):
        nl_pos = text.find("\n")
        fence_end = text.rfind("```")

        if nl_pos != -1 and fence_end > nl_pos:
            text = text[nl_pos + 1:fence_end].strip()

    return text


def parse_router_response(raw: str) -> ParseSample:
    """
    Parse a router response and measure timing.

    Mirrors the flow in src/intent/router.py line 229-240.
    """
    # Measure fence removal
    fence_start = time.perf_counter()
    try:
        stripped = strip_markdown_fences(raw)
        fence_ms = (time.perf_counter() - fence_start) * 1000
    except Exception as e:
        return ParseSample(0, 0, 0, False, f"Fence removal failed: {e}")

    # Measure JSON parsing
    json_start = time.perf_counter()
    try:
        parsed = json.loads(stripped)
        json_ms = (time.perf_counter() - json_start) * 1000
        total_ms = fence_ms + json_ms
        return ParseSample(total_ms, fence_ms, json_ms, True)
    except json.JSONDecodeError as e:
        return ParseSample(0, fence_ms, 0, False, f"JSON parse failed: {e}")


# Sample router responses - realistic test data
SAMPLE_FENCED = """```json
[
  {
    "intent_type": "status",
    "project_slug": "aide-de-camp",
    "confidence": 0.9,
    "utterance_fragment": "check the server logs",
    "reasoning": "User wants to check server logs for aide-de-camp",
    "urgency": "normal"
  }
]
```"""

SAMPLE_BARE = """[
  {
    "intent_type": "status",
    "project_slug": "aide-de-camp",
    "confidence": 0.9,
    "utterance_fragment": "check the server logs",
    "reasoning": "User wants to check server logs for aide-de-camp",
    "urgency": "normal"
  }
]"""

SAMPLE_COMPLEX_FENCED = """```json
[
  {
    "intent_type": "action",
    "project_slug": "needle",
    "confidence": 0.85,
    "utterance_fragment": "deploy the new bead-forge version to production",
    "reasoning": "User wants to deploy a new version of bead-forge to production",
    "urgency": "high"
  },
  {
    "intent_type": "lookup",
    "project_slug": "aide-de-camp",
    "confidence": 0.95,
    "utterance_fragment": "find recent router timeouts",
    "reasoning": "User is looking up recent router timeout events",
    "urgency": "normal",
    "lookup_kind": "logs"
  }
]
```"""


def run_profiling_sample(raw_response: str, iterations: int = 50) -> List[ParseSample]:
    """
    Run profiling iterations on a single response.

    Args:
        raw_response: The raw response text to parse
        iterations: Number of parse operations to sample

    Returns:
        List of ParseSample results
    """
    samples = []
    for _ in range(iterations):
        sample = parse_router_response(raw_response)
        samples.append(sample)
    return samples


def calculate_stats(values: List[float], metric_name: str) -> BaselineStats:
    """Calculate statistics from timing values."""
    if not values:
        return BaselineStats(metric_name, 0, 0, 0, 0, 0, 0)

    return BaselineStats(
        metric_name=metric_name,
        samples=len(values),
        avg_ms=statistics.mean(values),
        median_ms=statistics.median(values),
        min_ms=min(values),
        max_ms=max(values),
        stdev_ms=statistics.stdev(values) if len(values) > 1 else 0,
        percentile_95_ms=statistics.quantiles(values, n=20)[-1] if len(values) > 1 else values[0],
    )


def print_stats(stats: BaselineStats) -> None:
    """Print statistics in a readable format."""
    print(f"\n{stats.metric_name}:")
    print(f"  Samples:          {stats.samples}")
    print(f"  Average:          {stats.avg_ms:.4f} ms")
    print(f"  Median:           {stats.median_ms:.4f} ms")
    print(f"  Min:              {stats.min_ms:.4f} ms")
    print(f"  Max:              {stats.max_ms:.4f} ms")
    print(f"  Std Dev:          {stats.stdev_ms:.4f} ms")
    print(f"  95th percentile:  {stats.percentile_95_ms:.4f} ms")


def main():
    """Run profiling on multiple response types."""
    print("=" * 80)
    print("JSON PARSING BASELINE PROFILING")
    print("=" * 80)

    test_cases = [
        ("Simple fenced JSON", SAMPLE_FENCED),
        ("Simple bare JSON", SAMPLE_BARE),
        ("Complex fenced JSON (multiple intents)", SAMPLE_COMPLEX_FENCED),
    ]

    iterations = 50

    for name, response in test_cases:
        print(f"\n{'=' * 80}")
        print(f"Test Case: {name}")
        print(f"{'=' * 80}")

        samples = run_profiling_sample(response, iterations)

        # Filter successful samples
        successful = [s for s in samples if s.success]
        failed = [s for s in samples if not s.success]

        print(f"\nSuccess rate: {len(successful)}/{iterations} ({len(successful)/iterations*100:.1f}%)")

        if failed:
            print(f"\nFailed samples: {len(failed)}")
            for f in failed[:3]:  # Show first 3 failures
                print(f"  - {f.error}")

        if successful:
            # Calculate statistics
            total_times = [s.total_ms for s in successful]
            fence_times = [s.fence_ms for s in successful]
            json_times = [s.json_ms for s in successful]

            total_stats = calculate_stats(total_times, "Total Parse Time")
            fence_stats = calculate_stats(fence_times, "Fence Removal Time")
            json_stats = calculate_stats(json_times, "JSON Parse Time")

            print_stats(total_stats)
            print_stats(fence_stats)
            print_stats(json_stats)

            # Show breakdown percentage
            avg_fence_pct = (fence_stats.avg_ms / total_stats.avg_ms) * 100
            avg_json_pct = (json_stats.avg_ms / total_stats.avg_ms) * 100
            print(f"\nAverage time breakdown:")
            print(f"  Fence removal:  {avg_fence_pct:.1f}%")
            print(f"  JSON parsing:   {avg_json_pct:.1f}%")

    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")

    # Run aggregated comparison
    print("\nAggregated comparison across all test types:")
    all_results = []

    for name, response in test_cases:
        samples = run_profiling_sample(response, iterations)
        successful = [s for s in samples if s.success]
        if successful:
            avg_total = statistics.mean([s.total_ms for s in successful])
            avg_fence = statistics.mean([s.fence_ms for s in successful])
            avg_json = statistics.mean([s.json_ms for s in successful])
            all_results.append({
                "name": name,
                "avg_total_ms": avg_total,
                "avg_fence_ms": avg_fence,
                "avg_json_ms": avg_json,
            })

    # Print comparison table
    print(f"\n{'Test Case':<40} {'Total (ms)':>12} {'Fence (ms)':>12} {'JSON (ms)':>12}")
    print("-" * 80)
    for result in sorted(all_results, key=lambda x: x["avg_total_ms"]):
        print(f"{result['name']:<40} {result['avg_total_ms']:>12.4f} {result['avg_fence_ms']:>12.4f} {result['avg_json_ms']:>12.4f}")

    print(f"\n{'=' * 80}")
    print("Profiling complete.")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
