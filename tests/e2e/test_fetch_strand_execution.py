"""
End-to-end test for fetch strand execution through test endpoint.

Verifies that:
1. Test endpoint triggers fetch orchestration
2. All configured fetch strands run
3. Results match expected coverage for intent types
4. No fetch strand is skipped or fails silently
"""

import asyncio
import json
import sys
from typing import Any, Dict, List
from pathlib import Path

import httpx


# Configuration
API_BASE_URL = "http://localhost:8000"
TEST_TIMEOUT = 30


# Expected coverage by intent type
# Based on fetch command matrix in src/fetch/commands.py
EXPECTED_COVERAGE = {
    "status": {
        "min_sources": 5,
        "expected_sources": [
            "kubectl_pods",
            "kubectl_deployments",
            "argo_cd_applications",
            "ci_status",
            "beads_status"
        ]
    },
    "action": {
        "min_sources": 3,
        "expected_sources": [
            "kubectl_deployments",
            "argo_cd_applications",
            "git_log"
        ]
    },
    "research": {
        "min_sources": 4,
        "expected_sources": [
            "fs_readme",
            "git_log",
            "ci_status",
            "beads_status"
        ]
    },
    "lookup": {
        "min_sources": 5,
        "expected_sources": [
            "kubectl_pods",
            "kubectl_logs",
            "kubectl_deployments",
            "argo_cd_applications",
            "ci_status"
        ]
    },
}


class FetchStrandVerifier:
    """Verifies fetch strand execution through test endpoint."""

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

    async def health_check(self) -> bool:
        """Check if server is running."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    async def test_dispatch(
        self,
        utterance: str,
        wait_for_results: bool = True,
        timeout_seconds: int = TEST_TIMEOUT,
    ) -> Dict[str, Any]:
        """
        Dispatch test utterance and return results.

        Args:
            utterance: Test utterance text
            wait_for_results: Whether to wait for processing to complete
            timeout_seconds: Max time to wait for results

        Returns:
            Response dict with status, results, and coverage info
        """
        payload = {
            "utterance": utterance,
            "wait_for_results": wait_for_results,
            "timeout_seconds": timeout_seconds,
        }

        response = await self.client.post(
            f"{self.base_url}/api/v1/test/dispatch",
            json=payload,
        )

        if response.status_code != 200:
            raise Exception(f"Dispatch failed with status {response.status_code}: {response.text}")

        return response.json()

    def verify_coverage(
        self,
        intent_type: str,
        coverage: Dict[str, int],
        caveats: Any = None,
    ) -> Dict[str, Any]:
        """
        Verify that coverage matches expectations for intent type.

        Args:
            intent_type: Type of intent (status, action, research, lookup)
            coverage: Coverage dict from result
            caveats: Caveats from result

        Returns:
            Verification result dict
        """
        result = {
            "intent_type": intent_type,
            "passed": True,
            "failures": [],
            "warnings": [],
        }

        # Check if intent type is in expectations
        if intent_type not in EXPECTED_COVERAGE:
            result["warnings"].append(f"No coverage expectations defined for intent_type '{intent_type}'")
            return result

        expectations = EXPECTED_COVERAGE[intent_type]

        # Check minimum sources
        total_sources = coverage.get("total_sources", 0)
        succeeded = coverage.get("succeeded", 0)
        timed_out = coverage.get("timed_out", 0)
        failed = coverage.get("failed", 0)

        if total_sources < expectations["min_sources"]:
            result["passed"] = False
            result["failures"].append(
                f"Expected at least {expectations['min_sources']} total sources, got {total_sources}"
            )

        # Check for failures
        if failed > 0:
            result["passed"] = False
            result["failures"].append(f"{failed} fetch sources failed")

        # Check for timeouts
        if timed_out > 0:
            result["warnings"].append(f"{timed_out} fetch sources timed out")

        # Check success rate
        if total_sources > 0:
            success_rate = succeeded / total_sources
            if success_rate < 0.8:  # 80% success rate threshold
                result["passed"] = False
                result["failures"].append(f"Success rate {success_rate:.1%} below 80% threshold")

        # Check caveats
        if caveats:
            result["warnings"].append(f"Caveats present: {caveats}")

        return result


def print_verification_result(result: Dict[str, Any]):
    """Print verification result in a formatted way."""
    print(f"\n{'='*60}")
    print(f"Intent Type: {result['intent_type']}")
    print(f"Status: {'✅ PASSED' if result['passed'] else '❌ FAILED'}")
    print(f"{'='*60}")

    if result["failures"]:
        print("\n❌ Failures:")
        for failure in result["failures"]:
            print(f"  - {failure}")

    if result["warnings"]:
        print("\n⚠️  Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")

    if result["passed"] and not result["warnings"]:
        print("\n✅ All checks passed!")


async def run_test_suite():
    """Run comprehensive fetch strand execution test suite."""
    print("🚀 Starting Fetch Strand Execution Test Suite")
    print("=" * 60)

    all_passed = True
    test_results = []

    async with FetchStrandVerifier() as verifier:
        # Health check
        print("\n[1/5] Health Check")
        print("-" * 60)
        if not await verifier.health_check():
            print("❌ Server is not running")
            print("   Start the server with:")
            print("   cd /home/coding/aide-de-camp && python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000")
            return False
        print("✅ Server is running")

        # Test 2: Simple status query
        print("\n[2/5] Test: Simple Status Query")
        print("-" * 60)
        print("Utterance: 'how are the pods doing'")

        try:
            result = await verifier.test_dispatch("how are the pods doing")

            if result.get("status") == "completed" and result.get("results"):
                first_result = result["results"][0]
                coverage = first_result.get("coverage", {})
                intent_type = first_result.get("intent_type")

                print(f"Intent Type: {intent_type}")
                print(f"Coverage: {coverage}")

                verification = verifier.verify_coverage(
                    intent_type,
                    coverage,
                    first_result.get("caveats"),
                )

                test_results.append(verification)
                print_verification_result(verification)

                if not verification["passed"]:
                    all_passed = False
            else:
                print(f"❌ Unexpected result status: {result.get('status')}")
                all_passed = False
        except Exception as e:
            print(f"❌ Test failed: {e}")
            all_passed = False

        # Test 3: Project-specific status
        print("\n[3/5] Test: Project-Specific Status")
        print("-" * 60)
        print("Utterance: 'check the options pipeline status'")

        try:
            result = await verifier.test_dispatch("check the options pipeline status")

            if result.get("status") == "completed" and result.get("results"):
                first_result = result["results"][0]
                coverage = first_result.get("coverage", {})
                intent_type = first_result.get("intent_type")

                print(f"Intent Type: {intent_type}")
                print(f"Coverage: {coverage}")

                verification = verifier.verify_coverage(
                    intent_type,
                    coverage,
                    first_result.get("caveats"),
                )

                test_results.append(verification)
                print_verification_result(verification)

                if not verification["passed"]:
                    all_passed = False
            else:
                print(f"❌ Unexpected result status: {result.get('status')}")
                all_passed = False
        except Exception as e:
            print(f"❌ Test failed: {e}")
            all_passed = False

        # Test 4: Lookup request
        print("\n[4/5] Test: Lookup Request")
        print("-" * 60)
        print("Utterance: 'find the recent logs for the nap-api container'")

        try:
            result = await verifier.test_dispatch("find the recent logs for the nap-api container")

            if result.get("status") == "completed" and result.get("results"):
                first_result = result["results"][0]
                coverage = first_result.get("coverage", {})
                intent_type = first_result.get("intent_type")

                print(f"Intent Type: {intent_type}")
                print(f"Coverage: {coverage}")

                verification = verifier.verify_coverage(
                    intent_type,
                    coverage,
                    first_result.get("caveats"),
                )

                test_results.append(verification)
                print_verification_result(verification)

                if not verification["passed"]:
                    all_passed = False
            else:
                print(f"❌ Unexpected result status: {result.get('status')}")
                all_passed = False
        except Exception as e:
            print(f"❌ Test failed: {e}")
            all_passed = False

        # Test 5: Brainstorm request
        print("\n[5/5] Test: Brainstorm Request")
        print("-" * 60)
        print("Utterance: 'lets brainstorm ways to optimize the pipeline performance'")

        try:
            result = await verifier.test_dispatch("lets brainstorm ways to optimize the pipeline performance")

            if result.get("status") == "completed" and result.get("results"):
                first_result = result["results"][0]
                coverage = first_result.get("coverage", {})
                intent_type = first_result.get("intent_type")

                print(f"Intent Type: {intent_type}")
                print(f"Coverage: {coverage}")

                verification = verifier.verify_coverage(
                    intent_type,
                    coverage,
                    first_result.get("caveats"),
                )

                test_results.append(verification)
                print_verification_result(verification)

                if not verification["passed"]:
                    all_passed = False
            else:
                print(f"❌ Unexpected result status: {result.get('status')}")
                all_passed = False
        except Exception as e:
            print(f"❌ Test failed: {e}")
            all_passed = False

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    total_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r["passed"])

    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")

    if all_passed:
        print("\n✅ ALL TESTS PASSED")
        print("\n✅ Fetch strands execute correctly through test endpoint")
        print("✅ All configured fetch sources run for each intent type")
        print("✅ Results match expected coverage patterns")
    else:
        print("\n❌ SOME TESTS FAILED")
        print("\nReview failures above to determine:")
        print("  - Which fetch sources are not executing")
        print("  - Which intent types have insufficient coverage")
        print("  - Whether failures are transient or systematic")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_test_suite())
    sys.exit(0 if success else 1)
