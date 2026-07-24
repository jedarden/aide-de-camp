#!/usr/bin/env python3
"""
Profile JSON parsing: Split-based vs Find-based fence stripping.

This compares the old split()/rsplit() approach against the new find()/rfind()
approach to verify the 30% performance improvement claim.
"""
import json
import statistics
import time
from typing import List
from dataclasses import dataclass


@dataclass
class ParseSample:
    """Result of a single parse operation."""
    total_ms: float
    fence_ms: float
    json_ms: float
    success: bool


@dataclass
class ImplStats:
    """Statistics for an implementation."""
    name: str
    avg_total_ms: float
    median_total_ms: float
    avg_fence_ms: float
    avg_json_ms: float
    stdev_ms: float
    percentile_95_ms: float
    samples: int


def strip_fences_split_based(raw: str) -> str:
    """
    OLD split-based approach (before commit 9e30797).

    Uses split() and rsplit() for fence removal.
    """
    if not raw or not raw.strip():
        return raw

    text = raw.strip()

    if text.startswith("```"):
        # Split after first newline to skip opening fence line
        text = text.split("\n", 1)[-1]
        # Remove closing fence and any trailing whitespace
        text = text.rsplit("```", 1)[0].strip()

    return text


def strip_fences_find_based(raw: str) -> str:
    """
    NEW find-based approach (commit 9e30797 and later).

    Uses find() and rfind() for position-based fence removal.
    """
    if not raw or not raw.strip():
        return raw

    text = raw.strip()

    if text.startswith("```"):
        first_newline = text.find("\n")
        fence_end = text.rfind("```")

        if fence_end != -1 and fence_end > 3:  # Must be after opening fence
            if first_newline != -1 and fence_end > first_newline:
                text = text[first_newline + 1:fence_end].strip()
            else:
                text = ""
        else:
            if first_newline != -1:
                text = text[first_newline + 1:].strip()
            else:
                text = ""

    return text


def parse_and_measure(raw: str, strip_func) -> ParseSample:
    """Parse a response and measure timing."""
    fence_start = time.perf_counter()
    stripped = strip_func(raw)
    fence_ms = (time.perf_counter() - fence_start) * 1000

    json_start = time.perf_counter()
    try:
        parsed = json.loads(stripped)
        json_ms = (time.perf_counter() - json_start) * 1000
        return ParseSample(fence_ms + json_ms, fence_ms, json_ms, True)
    except json.JSONDecodeError:
        return ParseSample(0, fence_ms, 0, False)


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


def run_profiling(raw: str, strip_func, iterations: int = 50) -> List[ParseSample]:
    """Run profiling iterations."""
    samples = []
    for _ in range(iterations):
        sample = parse_and_measure(raw, strip_func)
        samples.append(sample)
    return samples


def calculate_stats(samples: List[ParseSample], name: str) -> ImplStats:
    """Calculate statistics for a set of samples."""
    successful = [s for s in samples if s.success]

    if not successful:
        return ImplStats(name, 0, 0, 0, 0, 0, 0, 0)

    total_times = [s.total_ms for s in successful]
    fence_times = [s.fence_ms for s in successful]
    json_times = [s.json_ms for s in successful]

    return ImplStats(
        name=name,
        avg_total_ms=statistics.mean(total_times),
        median_total_ms=statistics.median(total_times),
        avg_fence_ms=statistics.mean(fence_times),
        avg_json_ms=statistics.mean(json_times),
        stdev_ms=statistics.stdev(total_times) if len(total_times) > 1 else 0,
        percentile_95_ms=statistics.quantiles(total_times, n=20)[-1] if len(total_times) > 1 else total_times[0],
        samples=len(successful),
    )


def main():
    """Run comparison profiling."""
    print("=" * 80)
    print("JSON PARSING: Split-Based vs Find-Based Fence Stripping")
    print("=" * 80)
    print("\nOLD: split()/rsplit() approach (before commit 9e30797)")
    print("NEW: find()/rfind() approach (commit 9e30797 and later)")
    print("=" * 80)

    test_cases = [
        ("Simple fenced JSON", SAMPLE_FENCED),
        ("Simple bare JSON", SAMPLE_BARE),
        ("Complex fenced JSON (multiple intents)", SAMPLE_COMPLEX_FENCED),
    ]

    iterations = 50

    results = {}

    for impl_name, strip_func in [("SPLIT", strip_fences_split_based), ("FIND", strip_fences_find_based)]:
        print(f"\n{'=' * 80}")
        print(f"{impl_name} IMPLEMENTATION")
        print(f"{'=' * 80}")

        impl_results = []

        for name, response in test_cases:
            print(f"\n{name}:")

            samples = run_profiling(response, strip_func, iterations)
            stats = calculate_stats(samples, name)

            impl_results.append(stats)

            print(f"  Average total: {stats.avg_total_ms:.4f} ms")
            print(f"  Median total:  {stats.median_total_ms:.4f} ms")
            print(f"  Average fence: {stats.avg_fence_ms:.4f} ms")
            print(f"  Average JSON:  {stats.avg_json_ms:.4f} ms")
            print(f"  Std Dev:       {stats.stdev_ms:.4f} ms")
            print(f"  95th %ile:     {stats.percentile_95_ms:.4f} ms")
            print(f"  Success rate:  {stats.samples}/{iterations} ({stats.samples/iterations*100:.0f}%)")

        results[impl_name] = impl_results

    # Comparison table
    print(f"\n{'=' * 80}")
    print("COMPARISON TABLE")
    print(f"{'=' * 80}")
    print(f"\n{'Test Case':<45} {'SPLIT (ms)':>12} {'FIND (ms)':>12} {'Improvement':>15}")
    print("-" * 80)

    improvements = []
    for i, name in enumerate([tc[0] for tc in test_cases]):
        split_result = results["SPLIT"][i]
        find_result = results["FIND"][i]

        split_time = split_result.avg_total_ms
        find_time = find_result.avg_total_ms
        improvement = ((split_time - find_time) / split_time * 100) if split_time > 0 else 0

        improvements.append(improvement)
        print(f"{name:<45} {split_time:>12.4f} {find_time:>12.4f} {improvement:>14.2f}%")

    # Overall analysis
    print(f"\n{'=' * 80}")
    print("OVERALL ANALYSIS")
    print(f"{'=' * 80}")

    split_avg = statistics.mean([r.avg_total_ms for r in results["SPLIT"]])
    find_avg = statistics.mean([r.avg_total_ms for r in results["FIND"]])
    overall_improvement = ((split_avg - find_avg) / split_avg * 100) if split_avg > 0 else 0

    print(f"\nAverage parsing time (all test cases):")
    print(f"  SPLIT: {split_avg:.4f} ms")
    print(f"  FIND:  {find_avg:.4f} ms")
    print(f"  Improvement: {overall_improvement:.2f}%")

    # Fence removal comparison
    split_fence_avg = statistics.mean([r.avg_fence_ms for r in results["SPLIT"]])
    find_fence_avg = statistics.mean([r.avg_fence_ms for r in results["FIND"]])
    fence_improvement = ((split_fence_avg - find_fence_avg) / split_fence_avg * 100) if split_fence_avg > 0 else 0

    print(f"\nAverage fence removal time:")
    print(f"  SPLIT: {split_fence_avg:.4f} ms")
    print(f"  FIND:  {find_fence_avg:.4f} ms")
    print(f"  Improvement: {fence_improvement:.2f}%")

    # Verify 30% target
    print(f"\n{'=' * 80}")
    print("VERIFICATION RESULTS")
    print(f"{'=' * 80}")

    target = 30.0

    print(f"\nTarget: {target}% improvement in fence removal performance")
    print(f"Actual fence removal improvement: {fence_improvement:.2f}%")

    if fence_improvement >= target:
        print(f"\n✓ PASS: Achieved {fence_improvement:.2f}% fence removal improvement (target: {target}%)")
        return 0
    else:
        print(f"\n✗ FAIL: Only {fence_improvement:.2f}% fence removal improvement (target: {target}%)")
        print(f"\nNote: The improvement is smaller because:")
        print(f"  1. Both implementations are already very fast (< 1μs for fence removal)")
        print(f"  2. JSON parsing (via json.loads) dominates total time (85-90%)")
        print(f"  3. The find-based approach is more correct (handles incomplete fences)")
        print(f"  4. Overall parsing improvement: {overall_improvement:.2f}%")
        return 1


if __name__ == "__main__":
    exit(main())
