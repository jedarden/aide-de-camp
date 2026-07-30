#!/usr/bin/env python3
"""
Detailed JSON parsing profiling with warmup and more iterations.

This script provides more accurate measurements by:
1. Including warmup iterations to account for Python interpreter warmup
2. Running more iterations for better statistical significance
3. Showing detailed breakdowns by operation
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


def strip_fences_split_based(raw: str) -> str:
    """Split-based fence removal."""
    if not raw or not raw.strip():
        return raw
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0].strip()
    return text


def strip_fences_find_based(raw: str) -> str:
    """Find-based fence removal."""
    if not raw or not raw.strip():
        return raw
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        fence_end = text.rfind("```")
        if fence_end != -1 and fence_end > 3:
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


# Sample router responses
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


def run_profiling_with_warmup(raw: str, strip_func, warmup: int = 10, iterations: int = 200) -> List[ParseSample]:
    """Run profiling with warmup iterations."""
    # Warmup
    for _ in range(warmup):
        parse_and_measure(raw, strip_func)

    # Real measurements
    samples = []
    for _ in range(iterations):
        sample = parse_and_measure(raw, strip_func)
        samples.append(sample)
    return samples


def main():
    """Run detailed profiling."""
    print("=" * 80)
    print("DETAILED JSON PARSING PROFILING (with warmup, 200 iterations)")
    print("=" * 80)

    test_cases = [
        ("Simple fenced JSON", SAMPLE_FENCED),
        ("Simple bare JSON", SAMPLE_BARE),
    ]

    warmup = 10
    iterations = 200

    for impl_name, strip_func in [("SPLIT-based", strip_fences_split_based), ("FIND-based", strip_fences_find_based)]:
        print(f"\n{'=' * 80}")
        print(f"{impl_name} IMPLEMENTATION")
        print(f"{'=' * 80}")

        for name, response in test_cases:
            print(f"\n{name}:")

            samples = run_profiling_with_warmup(response, strip_func, warmup, iterations)
            successful = [s for s in samples if s.success]

            if not successful:
                print(f"  FAIL: No successful parses")
                continue

            total_times = [s.total_ms for s in successful]
            fence_times = [s.fence_ms for s in successful]
            json_times = [s.json_ms for s in successful]

            print(f"  Total parse time:")
            print(f"    Average:   {statistics.mean(total_times):.4f} ms")
            print(f"    Median:    {statistics.median(total_times):.4f} ms")
            print(f"    Min:       {min(total_times):.4f} ms")
            print(f"    Max:       {max(total_times):.4f} ms")
            print(f"    Std Dev:   {statistics.stdev(total_times):.4f} ms")

            print(f"  Fence removal time:")
            print(f"    Average:   {statistics.mean(fence_times):.4f} ms")
            print(f"    Median:    {statistics.median(fence_times):.4f} ms")
            print(f"    % of total: {(statistics.mean(fence_times) / statistics.mean(total_times)) * 100:.1f}%")

            print(f"  JSON parse time:")
            print(f"    Average:   {statistics.mean(json_times):.4f} ms")
            print(f"    Median:    {statistics.median(json_times):.4f} ms")
            print(f"    % of total: {(statistics.mean(json_times) / statistics.mean(total_times)) * 100:.1f}%")

    # Comparison
    print(f"\n{'=' * 80}")
    print("COMPARISON")
    print(f"{'=' * 80}")

    for name, response in test_cases:
        print(f"\n{name}:")

        split_samples = run_profiling_with_warmup(response, strip_fences_split_based, warmup, iterations)
        find_samples = run_profiling_with_warmup(response, strip_fences_find_based, warmup, iterations)

        split_successful = [s for s in split_samples if s.success]
        find_successful = [s for s in find_samples if s.success]

        split_total = statistics.mean([s.total_ms for s in split_successful])
        find_total = statistics.mean([s.total_ms for s in find_successful])

        split_fence = statistics.mean([s.fence_ms for s in split_successful])
        find_fence = statistics.mean([s.fence_ms for s in find_successful])

        total_improvement = ((split_total - find_total) / split_total * 100) if split_total > 0 else 0
        fence_improvement = ((split_fence - find_fence) / split_fence * 100) if split_fence > 0 else 0

        print(f"  Total time:  SPLIT={split_total:.4f}ms, FIND={find_total:.4f}ms, improvement={total_improvement:.2f}%")
        print(f"  Fence time:  SPLIT={split_fence:.4f}ms, FIND={find_fence:.4f}ms, improvement={fence_improvement:.2f}%")


if __name__ == "__main__":
    main()
