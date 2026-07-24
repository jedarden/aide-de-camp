"""
Performance comparison to verify 30% improvement optimization target.

This benchmark compares the old approach (what was in the router before)
vs the new optimized approach using centralized parse_llm_response.
"""

import json
import time
from src.llm.response_parser import parse_llm_response

# Typical router response
ROUTER_RESPONSE = """```json
[
    {
        "intent_type": "status",
        "project_slug": "aide-de-camp",
        "confidence": 0.95,
        "utterance_fragment": "how are the pods doing?",
        "reasoning": "User wants pod status",
        "urgency": "normal"
    }
]
```"""


def old_approach_parsing(response: str) -> dict:
    """
    The OLD approach that was in src/intent/router.py before optimization.
    Uses split() and rsplit() which creates intermediate string allocations.
    """
    raw = response.strip()
    if raw.startswith("```"):
        # OLD approach: using split() and rsplit()
        text = raw.split("\n", 1)[-1]
        raw = text.rsplit("```", 1)[0].strip()
    return json.loads(raw)


def new_approach_parsing(response: str) -> dict:
    """
    The NEW optimized approach using centralized parse_llm_response.
    Uses find() and rfind() for position-based slicing without intermediate allocations.
    """
    return parse_llm_response(response, strip_fences=True, expect_json=True)


def benchmark_function(func: callable, description: str, iterations: int = 10000):
    """Benchmark a function and return timing metrics."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(ROUTER_RESPONSE)
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms

    avg_ms = sum(times) / len(times)
    min_ms = min(times)
    max_ms = max(times)

    print(f"{description}:")
    print(f"  Average: {avg_ms:.4f}ms")
    print(f"  Min:     {min_ms:.4f}ms")
    print(f"  Max:     {max_ms:.4f}ms")
    print()

    return avg_ms


def main():
    print("=" * 60)
    print("JSON Parsing Optimization Verification")
    print("Target: 30% reduction in parsing time")
    print("=" * 60)
    print()

    # Benchmark both approaches
    old_avg = benchmark_function(
        old_approach_parsing,
        "OLD Approach (split/rsplit with intermediate allocations)"
    )

    new_avg = benchmark_function(
        new_approach_parsing,
        "NEW Approach (find/rfind with centralized parser)"
    )

    # Calculate improvement
    improvement_percent = ((old_avg - new_avg) / old_avg) * 100

    print("=" * 60)
    print("Optimization Results")
    print("=" * 60)
    print(f"Old average: {old_avg:.4f}ms")
    print(f"New average: {new_avg:.4f}ms")
    print(f"Improvement: {improvement_percent:.1f}%")
    print()

    # Verify against acceptance criteria
    if improvement_percent >= 30:
        print("✅ SUCCESS: Achieved 30%+ performance improvement!")
        print(f"   ({improvement_percent:.1f}% > 30%)")
        return 0
    else:
        print(f"⚠️  WARNING: Did not reach 30% target")
        print(f"   ({improvement_percent:.1f}% < 30%)")
        return 1


if __name__ == "__main__":
    exit(main())
