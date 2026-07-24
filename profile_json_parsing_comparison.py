#!/usr/bin/env python3
"""
Profile JSON parsing comparison - Old vs New Implementation.

This script compares the old implementation (before commit b0c3d3e) against
the new optimized implementation to verify the 30% performance improvement.
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


def strip_markdown_fences_old(raw: str) -> str:
    """
    OLD implementation (before commit b0c3d3e).

    Uses find()/rfind() for position-based fence removal.
    This version did NOT properly handle incomplete fences.
    """
    if not raw or not raw.strip():
        return raw

    # Optimized: single strip at start, avoid redundant operations
    text = raw.strip()

    # Fast manual fence stripping using position-based search
    # Pattern: ```optional_lang\n content \n```
    # Uses find()/rfind() instead of split()/rsplit() to avoid intermediate allocations
    if text.startswith("```"):
        # Find first newline after opening fence (position-based, no split)
        nl_pos = text.find("\n")
        # Find closing fence from end (search backwards for last ```)
        fence_end = text.rfind("```")

        # Direct slice extraction with single strip
        if nl_pos != -1 and fence_end > nl_pos:
            text = text[nl_pos + 1:fence_end].strip()

    return text


def strip_markdown_fences_new(raw: str) -> str:
    """
    NEW implementation (after commit b0c3d3e).

    Uses find()/rfind() for position-based fence removal.
    This version properly handles incomplete fences and embedded backticks.
    """
    if not raw or not raw.strip():
        return raw

    # Optimized: single strip at start, avoid redundant operations
    text = raw.strip()

    # Fast manual fence stripping using position-based search
    # Pattern: ```optional_lang\n content \n```
    # Uses rfind() to find LAST ``` (closing fence), which handles content with embedded ```
    if text.startswith("```"):
        # Find first newline after opening fence
        first_newline = text.find("\n")

        # Find closing fence from END (last ``` in the text)
        # This correctly handles content with ``` embedded in it
        fence_end = text.rfind("```")

        if fence_end != -1 and fence_end > 3:  # Must be after opening fence
            # Complete fence: extract content between opening and closing
            # Content is after first newline, before closing fence
            if first_newline != -1 and fence_end > first_newline:
                text = text[first_newline + 1:fence_end].strip()
            else:
                # No newline after opening fence or fence before newline (malformed)
                text = ""
        else:
            # Incomplete fence: only opening fence present
            # Strip opening fence and return the rest
            if first_newline != -1:
                text = text[first_newline + 1:].strip()
            else:
                # Opening fence with no content
                text = ""

    return text


def parse_with_fence_func(raw: str, fence_func) -> ParseSample:
    """
    Parse a router response and measure timing.

    Mirrors the flow in src/intent/router.py line 229-240.
    """
    # Measure fence removal
    fence_start = time.perf_counter()
    try:
        stripped = fence_func(raw)
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

# Additional edge case test with embedded backticks
SAMPLE_EMBEDDED_BACKTICKS = """```json
{
  "intent_type": "status",
  "code": "```hello```",
  "explanation": "This has embedded backticks"
}
```"""

# Incomplete fence (no closing ```)
SAMPLE_INCOMPLETE_FENCE = """```json
{
  "intent_type": "status",
  "project_slug": "aide-de-camp",
  "confidence": 0.9
}"""


def run_profiling_sample(raw_response: str, fence_func, iterations: int = 50) -> List[ParseSample]:
    """
    Run profiling iterations on a single response.

    Args:
        raw_response: The raw response text to parse
        fence_func: The fence stripping function to use
        iterations: Number of parse operations to sample

    Returns:
        List of ParseSample results
    """
    samples = []
    for _ in range(iterations):
        sample = parse_with_fence_func(raw_response, fence_func)
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
    print(f"  Samples:          {stats.samples}")
    print(f"  Average:          {stats.avg_ms:.4f} ms")
    print(f"  Median:           {stats.median_ms:.4f} ms")
    print(f"  Min:              {stats.min_ms:.4f} ms")
    print(f"  Max:              {stats.max_ms:.4f} ms")
    print(f"  Std Dev:          {stats.stdev_ms:.4f} ms")
    print(f"  95th percentile:  {stats.percentile_95_ms:.4f} ms")


def main():
    """Run comparison profiling between old and new implementations."""
    print("=" * 80)
    print("JSON PARSING PERFORMANCE COMPARISON: OLD vs NEW")
    print("=" * 80)
    print("\nOLD: Implementation before commit b0c3d3e (incomplete fence handling)")
    print("NEW: Implementation after commit b0c3d3e (improved single-pass stripping)")
    print("=" * 80)

    test_cases = [
        ("Simple fenced JSON", SAMPLE_FENCED),
        ("Simple bare JSON", SAMPLE_BARE),
        ("Complex fenced JSON (multiple intents)", SAMPLE_COMPLEX_FENCED),
        ("Embedded backticks", SAMPLE_EMBEDDED_BACKTICKS),
        ("Incomplete fence", SAMPLE_INCOMPLETE_FENCE),
    ]

    iterations = 50

    results = {}

    for impl_name, fence_func in [("OLD", strip_markdown_fences_old), ("NEW", strip_markdown_fences_new)]:
        print(f"\n{'=' * 80}")
        print(f"{impl_name} IMPLEMENTATION")
        print(f"{'=' * 80}")

        impl_results = []

        for name, response in test_cases:
            print(f"\nTest Case: {name}")

            samples = run_profiling_sample(response, fence_func, iterations)

            # Filter successful samples
            successful = [s for s in samples if s.success]
            failed = [s for s in samples if not s.success]

            print(f"Success rate: {len(successful)}/{iterations} ({len(successful)/iterations*100:.1f}%)")

            if failed:
                print(f"Failed samples: {len(failed)}")
                for f in failed[:3]:
                    print(f"  - {f.error}")

            if successful:
                # Calculate statistics
                total_times = [s.total_ms for s in successful]
                fence_times = [s.fence_ms for s in successful]
                json_times = [s.json_ms for s in successful]

                total_stats = calculate_stats(total_times, "Total Parse Time")

                print(f"  Average total: {total_stats.avg_ms:.4f} ms")
                print(f"  Average fence: {statistics.mean(fence_times):.4f} ms")
                print(f"  Average JSON:  {statistics.mean(json_times):.4f} ms")

                impl_results.append({
                    "name": name,
                    "avg_total_ms": total_stats.avg_ms,
                    "success_rate": len(successful) / iterations,
                })

        results[impl_name] = impl_results

    # Comparison table
    print(f"\n{'=' * 80}")
    print("COMPARISON TABLE")
    print(f"{'=' * 80}")
    print(f"\n{'Test Case':<45} {'OLD (ms)':>12} {'NEW (ms)':>12} {'Improvement':>15} {'OLD Success':>14}")
    print("-" * 110)

    for i, name in enumerate([tc[0] for tc in test_cases]):
        if i < len(results["OLD"]):
            old_result = results["OLD"][i]
            old_time = old_result["avg_total_ms"]
            old_success = f"{old_result['success_rate']*100:.0f}%"
        else:
            old_time = 0.0
            old_success = "FAIL"

        new_result = results["NEW"][i]
        new_time = new_result["avg_total_ms"]
        new_success = f"{new_result['success_rate']*100:.0f}%"

        improvement = ((old_time - new_time) / old_time * 100) if old_time > 0 else 0

        if old_time > 0:
            print(f"{name:<45} {old_time:>12.4f} {new_time:>12.4f} {improvement:>14.2f}% {old_success:>14}")
        else:
            print(f"{name:<45} {'FAIL':>12} {new_time:>12.4f} {'N/A':>14} {old_success:>14}")

    # Overall comparison (main test cases only - both implementations succeed)
    print(f"\n{'=' * 80}")
    print("OVERALL PERFORMANCE SUMMARY")
    print(f"{'=' * 80}")

    main_test_names = [tc[0] for tc in test_cases[:3]]  # First 3 are the main test cases

    old_results = [r for r in results["OLD"] if r["name"] in main_test_names]
    new_results = [r for r in results["NEW"] if r["name"] in main_test_names]

    old_avg = statistics.mean([r["avg_total_ms"] for r in old_results])
    new_avg = statistics.mean([r["avg_total_ms"] for r in new_results])
    overall_improvement = ((old_avg - new_avg) / old_avg * 100) if old_avg > 0 else 0

    print(f"\nAverage parsing time (main test cases: {', '.join(main_test_names)}):")
    print(f"  OLD: {old_avg:.4f} ms")
    print(f"  NEW: {new_avg:.4f} ms")
    print(f"  Improvement: {overall_improvement:.2f}%")

    # Edge case analysis
    print(f"\n{'=' * 80}")
    print("EDGE CASE ANALYSIS")
    print(f"{'=' * 80}")

    print(f"\n1. Incomplete Fence Handling:")
    if len(results['OLD']) > 4:
        print(f"   OLD success rate: {results['OLD'][4]['success_rate']*100:.1f}%")
    else:
        print(f"   OLD success rate: 0.0% (FAIL - all samples failed)")
    print(f"   NEW success rate: {results['NEW'][4]['success_rate']*100:.1f}%")
    if len(results['OLD']) > 4 and results['NEW'][4]['success_rate'] > results['OLD'][4]['success_rate']:
        print(f"   ✓ NEW implementation correctly handles incomplete fences")
    elif len(results['OLD']) <= 4:
        print(f"   ✓ NEW implementation correctly handles incomplete fences (OLD failed completely)")

    print(f"\n2. Embedded Backticks:")
    if len(results['OLD']) > 3:
        print(f"   OLD success rate: {results['OLD'][3]['success_rate']*100:.1f}%")
        print(f"   NEW success rate: {results['NEW'][3]['success_rate']*100:.1f}%")

    # Verify 30% target
    print(f"\n{'=' * 80}")
    print("VERIFICATION RESULTS")
    print(f"{'=' * 80}")

    target = 30.0
    print(f"\nTarget: {target}% improvement in JSON parsing performance")

    if overall_improvement >= target:
        print(f"\n✓ PASS: Achieved {overall_improvement:.2f}% improvement (target: {target}%)")
        return 0
    else:
        print(f"\n✗ FAIL: Only {overall_improvement:.2f}% improvement achieved (target: {target}%)")
        print(f"\nNote: The optimization focuses on correctness for edge cases (incomplete fences)")
        print(f"      rather than raw performance on already-fast (< 5μs) operations.")
        print(f"      Both implementations are extremely fast compared to LLM latency (200-500ms).")
        return 1


if __name__ == "__main__":
    exit(main())
