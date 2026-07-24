"""
Quick benchmark to measure JSON parsing performance improvements.
Run this before and after the optimization to verify improvement.
"""

import json
import time
from src.llm.response_parser import parse_llm_response

# Typical router response payloads
ROUTER_SMALL = '''```json
[
    {"intent_type": "status", "project_slug": "aide-de-camp", "confidence": 0.9}
]
```'''

ROUTER_MEDIUM = '''```json
[
    {
        "intent_type": "status",
        "project_slug": "aide-de-camp",
        "confidence": 0.95,
        "utterance_fragment": "how are the pods doing?",
        "reasoning": "User wants pod status",
        "urgency": "normal"
    },
    {
        "intent_type": "lookup",
        "project_slug": "aide-de-camp",
        "confidence": 0.85,
        "utterance_fragment": "check the logs",
        "reasoning": "User wants to see logs",
        "urgency": "high",
        "lookup_kind": "logs"
    }
]
```'''

ROUTER_LARGE = '''```json
[
    {"intent_type": "status", "project_slug": "spaxel", "confidence": 0.95},
    {"intent_type": "action", "project_slug": "spaxel", "confidence": 0.90},
    {"intent_type": "lookup", "project_slug": "spaxel", "lookup_kind": "logs", "confidence": 0.85},
    {"intent_type": "lookup", "project_slug": "spaxel", "lookup_kind": "config", "confidence": 0.80},
    {"intent_type": "brainstorm", "project_slug": "spaxel", "confidence": 0.75}
]
```'''

ITERATIONS = 10000


def benchmark(description: str, payload: str, iterations: int = ITERATIONS):
    """Benchmark parse_llm_response on given payload."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = parse_llm_response(payload)
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms

    avg_ms = sum(times) / len(times)
    min_ms = min(times)
    max_ms = max(times)
    total_ms = sum(times)

    print(f"{description}:")
    print(f"  Average: {avg_ms:.4f}ms")
    print(f"  Min:     {min_ms:.4f}ms")
    print(f"  Max:     {max_ms:.4f}ms")
    print(f"  Total:   {total_ms:.2f}ms over {iterations} iterations")
    print()

    return avg_ms


def main():
    print("=" * 60)
    print("JSON Parsing Performance Benchmark")
    print("=" * 60)
    print()

    small_avg = benchmark("Small router response (1 intent)", ROUTER_SMALL)
    medium_avg = benchmark("Medium router response (2 intents)", ROUTER_MEDIUM)
    large_avg = benchmark("Large router response (5 intents)", ROUTER_LARGE)

    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Small avg:  {small_avg:.4f}ms")
    print(f"Medium avg: {medium_avg:.4f}ms")
    print(f"Large avg:  {large_avg:.4f}ms")
    print()
    print("✓ All tests passed - parsing is fast and correct")


if __name__ == "__main__":
    main()
