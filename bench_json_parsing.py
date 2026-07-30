#!/usr/bin/env python3
"""
JSON Parsing Performance Benchmark (bead adc-3e5gg)

Benchmarks the different JSON parsing approaches in aide-de-camp:

1. Manual fence stripping (as used in router.py and synthesize.py)
2. Centralized response_parser utilities (strip_markdown_fences, parse_llm_response)
3. Different fence formats (```json, ```, no fence)
4. Different payload sizes (small, medium, large)

Measures:
- Latency per operation
- Hot path identification
- Comparison between approaches

Run: .venv/bin/python bench_json_parsing.py
"""

import json
import re
import statistics
import time
from dataclasses import dataclass
from typing import Callable
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.llm.response_parser import (
    strip_markdown_fences,
    parse_llm_response,
    unwrap_zai_response,
    extract_text_from_response,
)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    operation: str
    total_time_ms: float
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float
    median_ms: float
    ops_per_sec: float
    iterations: int


# ============================================================================
# Test Data Fixtures
# ============================================================================

# Precompile fence pattern for manual benchmarking (matches response_parser pattern)
_FENCE_PATTERN = re.compile(r"^```(?:\w+)?\n([\s\S]+?)\n```$")


# Small payload (typical router response)
_SMALL_PAYLOAD = {
    "intents": [
        {
            "intent_type": "status",
            "project_slug": "aide-de-camp",
            "confidence": 0.95,
            "utterance_fragment": "how are the pods doing?",
            "reasoning": "User wants pod status",
            "urgency": "normal"
        }
    ]
}

# Medium payload (typical synthesize response)
_MEDIUM_PAYLOAD = {
    "data": {
        "type": "pod-status",
        "items": [
            {"name": "web-0", "phase": "Running", "ready": "1/1", "restarts": 0},
            {"name": "web-1", "phase": "Running", "ready": "1/1", "restarts": 0},
            {"name": "worker-0", "phase": "Running", "ready": "1/1", "restarts": 2},
            {"name": "worker-1", "phase": "Pending", "ready": "0/1", "restarts": 0},
        ],
        "summary_fields": {
            "total": 4,
            "running": 3,
            "pending": 1,
            "restarts": 2
        }
    },
    "summary": "Cluster has 4 pods: 3 running, 1 pending. Total restarts: 2.",
    "urgency": "normal"
}

# Large payload (complex fetch result with many sources)
_LARGE_PAYLOAD = {
    "data": {
        "type": "comprehensive-status",
        "cluster": {
            "name": "production",
            "pods": [
                {
                    "name": f"web-{i}",
                    "namespace": "default",
                    "phase": "Running" if i % 10 != 0 else "Pending",
                    "ready": f"1/1",
                    "restarts": i % 5,
                    "age": f"{i}d",
                    "node": f"node-{i % 3}",
                }
                for i in range(50)
            ],
            "deployments": [
                {
                    "name": f"app-{j}",
                    "ready": f"{j}/{j}",
                    "up_to_date": j,
                    "available": j,
                    "age": f"{j}d",
                }
                for j in range(20)
            ],
            "services": [
                {
                    "name": f"svc-{k}",
                    "type": "ClusterIP",
                    "cluster_ip": f"10.0.0.{k}",
                    "ports": [{"port": 8080 + k, "target_port": 8080 + k}]
                }
                for k in range(15)
            ]
        },
        "git": {
            "repo": "example/app",
            "branch": "main",
            "commits": [
                {
                    "hash": f"abc{m}",
                    "message": f"Commit {m}",
                    "author": "dev",
                    "timestamp": f"2024-01-{m:02d}T12:00:00Z"
                }
                for m in range(1, 31)
            ],
            "behind_by": 3,
            "ahead_by": 0
        },
        "argo_cd": {
            "app": "app-prod",
            "health": "Healthy",
            "sync": "Synced",
            "revision": "abc123",
            "deployed_at": "2024-01-15T10:30:00Z"
        }
    },
    "summary": "Production cluster has 50 pods (45 running, 5 pending), 20 deployments, 15 services. Git is 3 commits behind main. ArgoCD app is Healthy and Synced.",
    "urgency": "normal"
}


def _wrap_in_fence(payload: dict, fence_type: str) -> str:
    """Wrap a payload in different fence formats."""
    body = json.dumps(payload)
    if fence_type == "json":
        return f"```json\n{body}\n```"
    elif fence_type == "plain":
        return f"```\n{body}\n```"
    elif fence_type == "bare":
        return body
    else:
        raise ValueError(f"Unknown fence type: {fence_type}")


# ============================================================================
# Parsing Implementations
# ============================================================================

def manual_fence_strip_current(text: str) -> str:
    """
    Manual fence stripping as used in router.py and synthesize.py.

    This is the CURRENT implementation in those files (lines 251-254 in router.py,
    lines 143-147 in synthesize.py).
    """
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    return raw


def manual_fence_strip_regex(text: str) -> str:
    """Manual fence stripping using regex pattern."""
    text = text.strip()
    match = _FENCE_PATTERN.match(text)
    if match:
        return match.group(1)
    return text


def centralized_parse_llm(text: str, expect_json: bool = True) -> dict:
    """
    Full parsing using centralized response_parser utilities.

    This uses strip_markdown_fences() + parse_llm_response().
    """
    return parse_llm_response(text, strip_fences=True, expect_json=expect_json)


def direct_json_loads(text: str) -> dict:
    """Direct json.loads() without any fence stripping."""
    return json.loads(text)


# ============================================================================
# Benchmark Runner
# ============================================================================

def benchmark_operation(
    operation: Callable,
    text: str,
    iterations: int = 1000,
) -> BenchmarkResult:
    """
    Benchmark a single operation.

    Args:
        operation: Callable that takes text and returns parsed result
        text: Input text to parse
        iterations: Number of times to run the operation

    Returns:
        BenchmarkResult with timing statistics
    """
    times = []

    # Warmup run (not measured)
    try:
        operation(text)
    except Exception:
        pass  # Ignore warmup errors

    for _ in range(iterations):
        start = time.perf_counter()
        try:
            result = operation(text)
            _ = result  # Use result to avoid optimization
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms

    if not times:
        raise RuntimeError("All iterations failed")

    total = sum(times)
    avg = statistics.mean(times)
    median = statistics.median(times)
    min_t = min(times)
    max_t = max(times)
    ops_per_sec = iterations / (total / 1000)

    operation_name = operation.__name__

    return BenchmarkResult(
        operation=operation_name,
        total_time_ms=total,
        avg_time_ms=avg,
        min_time_ms=min_t,
        max_time_ms=max_t,
        median_ms=median,
        ops_per_sec=ops_per_sec,
        iterations=len(times)
    )


def run_benchmark_suite():
    """Run comprehensive benchmark suite across all approaches and payloads."""

    iterations = 1000

    print("=" * 80)
    print("JSON PARSING PERFORMANCE BENCHMARK")
    print("=" * 80)
    print(f"Iterations per operation: {iterations}")
    print()

    all_results = []

    # Test configurations
    payloads = [
        ("small", _SMALL_PAYLOAD),
        ("medium", _MEDIUM_PAYLOAD),
        ("large", _LARGE_PAYLOAD),
    ]

    fence_types = ["json", "plain", "bare"]

    operations = [
        ("Current Manual (router/synth)", manual_fence_strip_current),
        ("Manual with Regex", manual_fence_strip_regex),
        ("Centralized strip_markdown_fences", strip_markdown_fences),
        ("Full parse_llm_response", lambda t: centralized_parse_llm(t, expect_json=True)),
        ("Direct json.loads (no fence)", direct_json_loads),
    ]

    # Run benchmarks
    for payload_name, payload in payloads:
        print(f"\n{'=' * 80}")
        print(f"PAYLOAD: {payload_name.upper()} (~{len(json.dumps(payload))} bytes)")
        print(f"{'=' * 80}")

        for fence_type in fence_types:
            fenced_text = _wrap_in_fence(payload, fence_type)

            print(f"\n--- Fence format: {fence_type.upper()} ---")
            print(f"{'Operation':<40} | {'Avg (ms)':<10} | {'Median (ms)':<12} | {'Min/Max (ms)':<15} | {'Ops/sec':<12}")
            print("-" * 100)

            for op_name, op_func in operations:
                # Skip direct json.loads for fenced payloads (will fail)
                if fence_type != "bare" and op_name == "Direct json.loads (no fence)":
                    continue

                try:
                    result = benchmark_operation(op_func, fenced_text, iterations)
                    all_results.append((payload_name, fence_type, result))

                    print(
                        f"{result.operation:<40} | "
                        f"{result.avg_time_ms:<10.4f} | "
                        f"{result.median_ms:<12.4f} | "
                        f"{result.min_time_ms:.4f}/{result.max_time_ms:.4f} | "
                        f"{result.ops_per_sec:<12.0f}"
                    )
                except Exception as e:
                    print(f"{op_name:<40} | ERROR: {e}")

    return all_results


def print_summary(all_results):
    """Print summary of results with recommendations."""

    print("\n" + "=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)

    # Group by operation type
    by_operation = {}
    for payload_name, fence_type, result in all_results:
        key = result.operation
        if key not in by_operation:
            by_operation[key] = []
        by_operation[key].append(result.avg_time_ms)

    print("\nAverage latency across all payloads and fence formats:")
    print(f"{'Operation':<40} | {'Avg (ms)':<10} | {'Relative to slowest':<20}")
    print("-" * 80)

    averages = {op: sum(times) / len(times) for op, times in by_operation.items()}
    max_avg = max(averages.values())

    for op, avg in sorted(averages.items(), key=lambda x: x[1]):
        relative = avg / max_avg if max_avg > 0 else 0
        print(f"{op:<40} | {avg:<10.4f} | {relative:<20.2%}")

    print("\n" + "=" * 80)
    print("KEY FINDINGS")
    print("=" * 80)

    # Find fastest and slowest
    fastest_op = min(averages.items(), key=lambda x: x[1])
    slowest_op = max(averages.items(), key=lambda x: x[1])

    print(f"✓ Fastest: {fastest_op[0]} ({fastest_op[1]:.4f} ms avg)")
    print(f"✗ Slowest: {slowest_op[0]} ({slowest_op[1]:.4f} ms avg)")
    print(f"✓ Speedup: {slowest_op[1] / fastest_op[1]:.2f}x")

    # Compare current implementation vs alternatives
    if "Current Manual (router/synth)" in averages:
        current_avg = averages["Current Manual (router/synth)"]

        print(f"\nCurrent manual implementation (router.py, synthesize.py): {current_avg:.4f} ms")

        if "Manual with Regex" in averages:
            regex_avg = averages["Manual with Regex"]
            speedup = current_avg / regex_avg
            if speedup > 1:
                print(f"  → Regex pattern is {speedup:.2f}x FASTER than current")
            else:
                print(f"  → Regex pattern is {1/speedup:.2f}x SLOWER than current")

        if "Centralized strip_markdown_fences" in averages:
            centralized_avg = averages["Centralized strip_markdown_fences"]
            speedup = current_avg / centralized_avg
            if speedup > 1:
                print(f"  → Centralized strip_markdown_fences is {speedup:.2f}x FASTER")
            else:
                print(f"  → Centralized strip_markdown_fences is {1/speedup:.2f}x SLOWER")

        if "Full parse_llm_response" in averages:
            full_avg = averages["Full parse_llm_response"]
            speedup = current_avg / full_avg
            if speedup > 1:
                print(f"  → Full parse_llm_response is {speedup:.2f}x FASTER")
            else:
                print(f"  → Full parse_llm_response is {1/speedup:.2f}x SLOWER")


def main():
    """Main benchmark entry point."""
    all_results = run_benchmark_suite()
    print_summary(all_results)

    print("\n" + "=" * 80)
    print("HOT PATHS IDENTIFIED")
    print("=" * 80)
    print("\nJSON parsing is executed on EVERY dispatch through:")
    print("  1. src/intent/router.py (classify_utterance) - lines 251-257")
    print("  2. src/synthesize/strand.py (synthesize) - lines 143-150")
    print("  3. src/fetch/orchestrator.py (br CLI output parsing)")
    print("\nThese are HOT PATHS - optimizations here affect every request.")


if __name__ == "__main__":
    main()
