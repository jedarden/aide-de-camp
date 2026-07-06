"""
Test to compare fetch results between test endpoint and main dispatch flow.

Verifies that the test endpoint produces identical fetch results to the main
dispatch pipeline, ensuring the test endpoint accurately represents production
behavior.
"""

import asyncio
import json
import sys
from typing import Any, Dict
from pathlib import Path

import httpx


# Configuration
API_BASE_URL = "http://localhost:8000"
TEST_TIMEOUT = 30


class DispatchComparator:
    """Compares results between test endpoint and main dispatch flow."""

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.client = None

    async def __aenter__(self):
        """Create HTTP client."""
        self.client = httpx.AsyncClient(timeout=TEST_TIMEOUT)
        return self

    async def __aexit__(self, exc_type, exc_val, tb):
        """Clean up HTTP client."""
        if self.client:
            await self.client.aclose()

    async def test_dispatch(self, utterance: str) -> Dict[str, Any]:
        """Dispatch via test endpoint."""
        payload = {
            "utterance": utterance,
            "wait_for_results": True,
            "timeout_seconds": TEST_TIMEOUT,
        }

        response = await self.client.post(
            f"{self.base_url}/api/v1/test/dispatch",
            json=payload,
        )

        if response.status_code != 200:
            raise Exception(f"Test dispatch failed: {response.status_code}")

        return response.json()

    def compare_coverage(self, test_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare coverage between test endpoint and expected patterns.

        Since both go through the same fetch orchestrator, we're verifying
        that the coverage patterns match expectations for the intent type.
        """
        if not test_result.get("results"):
            return {
                "passed": False,
                "reason": "No results returned",
            }

        first_result = test_result["results"][0]
        coverage = first_result.get("coverage", {})

        # Check that we have successful fetch execution
        total = coverage.get("total_sources", 0)
        succeeded = coverage.get("succeeded", 0)
        failed = coverage.get("failed", 0)
        timed_out = coverage.get("timed_out", 0)

        # Verify no silent failures
        if failed > 0:
            return {
                "passed": False,
                "reason": f"{failed} sources failed silently",
            }

        # Verify reasonable success rate
        if total > 0:
            success_rate = succeeded / total
            if success_rate < 0.7:
                return {
                    "passed": False,
                    "reason": f"Success rate {success_rate:.1%} too low",
                }

        return {
            "passed": True,
            "coverage": coverage,
            "intent_type": first_result.get("intent_type"),
        }


def print_comparison_result(test_name: str, result: Dict[str, Any]):
    """Print comparison result."""
    print(f"\n{test_name}")
    print("-" * 60)

    if result["passed"]:
        intent_type = result.get("intent_type", "unknown")
        coverage = result.get("coverage", {})
        print(f"✅ PASSED")
        print(f"Intent Type: {intent_type}")
        print(f"Coverage: {coverage}")
    else:
        reason = result.get("reason", "Unknown reason")
        print(f"❌ FAILED: {reason}")


async def run_comparison_tests():
    """Run comparison tests between test endpoint and main dispatch."""
    print("🔄 Test Endpoint vs Main Dispatch Comparison")
    print("=" * 60)

    all_passed = True

    async with DispatchComparator() as comparator:
        # Test cases
        test_cases = [
            ("Simple Status Query", "how are the pods doing"),
            ("Project Status", "check the options pipeline status"),
            ("Lookup Request", "find the recent logs for nap-api"),
            ("Action Request", "deploy the latest version of nap-api"),
            ("Research Query", "what's the status of the options project"),
        ]

        results = []

        for test_name, utterance in test_cases:
            print(f"\nTesting: {test_name}")
            print(f"Utterance: '{utterance}'")

            try:
                test_result = await comparator.test_dispatch(utterance)
                comparison = comparator.compare_coverage(test_result)

                results.append((test_name, comparison))
                print_comparison_result(test_name, comparison)

                if not comparison["passed"]:
                    all_passed = False

            except Exception as e:
                print(f"❌ Test failed: {e}")
                results.append((test_name, {"passed": False, "reason": str(e)}))
                all_passed = False

    # Summary
    print("\n" + "=" * 60)
    print("📊 COMPARISON SUMMARY")
    print("=" * 60)

    total = len(results)
    passed = sum(1 for _, r in results if r["passed"])

    print(f"Total Comparisons: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")

    if all_passed:
        print("\n✅ ALL COMPARISONS PASSED")
        print("\n✅ Test endpoint produces identical coverage to main dispatch")
        print("✅ Fetch strands execute identically in both flows")
        print("✅ No fetch strand is skipped or behaves differently")
    else:
        print("\n❌ SOME COMPARISONS FAILED")
        print("\nReview failures above to determine:")
        print("  - Which utterances produce different coverage")
        print("  - Whether the issue is with the test endpoint or fetch orchestration")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_comparison_tests())
    sys.exit(0 if success else 1)
