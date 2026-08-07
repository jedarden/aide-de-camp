#!/usr/bin/env python3
"""
Test script to verify that /api/v1/test/intent-classify and /dispatch
produce identical classification results for the same inputs.

This addresses bead adc-5rjc46: "Compare test vs dispatch classification results"
"""
import asyncio
import httpx
import json
import sys
from typing import Dict, Any


# Test server URL
TEST_SERVER_URL = "http://localhost:8000"


# Test utterances covering different intent types
TEST_UTTERANCES = [
    {
        "name": "status_query",
        "utterance": "how are the pods doing",
        "description": "Simple status query without project context",
    },
    {
        "name": "project_status",
        "utterance": "check the options pipeline status",
        "description": "Status query for specific project",
    },
    {
        "name": "action_request",
        "utterance": "deploy the latest version of nap-api",
        "description": "Action request to deploy a service",
    },
    {
        "name": "lookup_request",
        "utterance": "find the recent logs for the nap-api container",
        "description": "Lookup request for logs",
    },
    {
        "name": "weather_query",
        "utterance": "what is the weather",
        "description": "Weather query for current conditions",
    },
    {
        "name": "research_query",
        "utterance": "tell me about Kubernetes architecture patterns",
        "description": "Research query for information gathering",
    },
    {
        "name": "brainstorm",
        "utterance": "let's brainstorm ways to optimize the pipeline performance",
        "description": "Brainstorming request",
    },
    {
        "name": "task_profile",
        "utterance": "create a bead for implementing the new monitoring feature",
        "description": "Task profile that should escalate to NEEDLE bead",
    },
    {
        "name": "multi_intent",
        "utterance": "how's the pipeline and also check the ibkr mcp status",
        "description": "Multi-intent utterance that should split into multiple intents",
    },
]


async def test_intent_classify(utterance: str, session_id: str) -> Dict[str, Any]:
    """
    Call the /api/v1/test/intent-classify endpoint.

    Returns:
        Dict with utterance and classifications
    """
    url = f"{TEST_SERVER_URL}/api/v1/test/intent-classify"
    payload = {"utterance": utterance}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()


async def test_dispatch(utterance: str, session_id: str, surface_id: str) -> Dict[str, Any]:
    """
    Call the /api/v1/test/dispatch endpoint with wait_for_results=True.

    Returns:
        Dict with utterance, intent_count, intent_ids, and results
    """
    url = f"{TEST_SERVER_URL}/api/v1/test/dispatch"
    payload = {
        "utterance": utterance,
        "session_id": session_id,
        "surface_id": surface_id,
        "wait_for_results": True,
        "timeout_seconds": 30,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=60.0)
        response.raise_for_status()
        return response.json()


def normalize_classification(classification: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a classification for comparison.

    Handles small differences in field names and types.
    """
    return {
        "intent_type": classification.get("intent_type"),
        "project_slug": classification.get("project_slug"),
        "confidence": round(float(classification.get("confidence", 1.0)), 2),
        "utterance_fragment": classification.get("utterance_fragment", ""),
        "reasoning": classification.get("reasoning", ""),
        "urgency": classification.get("urgency", "normal"),
        # lookup_kind is optional
        "lookup_kind": classification.get("lookup_kind"),
    }


def compare_classifications(
    test_classify: list[Dict[str, Any]],
    test_dispatch: list[Dict[str, Any]],
    utterance: str,
) -> tuple[bool, str]:
    """
    Compare two sets of classifications.

    Returns:
        (match: bool, message: str)
    """
    # Normalize both sets
    normalized_classify = [normalize_classification(c) for c in test_classify]
    normalized_dispatch = [normalize_classification(c) for c in test_dispatch]

    # Check count
    if len(normalized_classify) != len(normalized_dispatch):
        return False, (
            f"Mismatch in intent count: "
            f"/api/v1/test/intent-classify returned {len(normalized_classify)} intents, "
            f"/api/v1/test/dispatch returned {len(normalized_dispatch)} intents"
        )

    # Sort by intent_type for consistent comparison
    sorted_classify = sorted(normalized_classify, key=lambda x: x["intent_type"])
    sorted_dispatch = sorted(normalized_dispatch, key=lambda x: x["intent_type"])

    # Compare each classification
    for i, (classify, dispatch) in enumerate(zip(sorted_classify, sorted_dispatch)):
        # Check intent_type
        if classify["intent_type"] != dispatch["intent_type"]:
            return False, (
                f"Mismatch in intent {i+1} intent_type: "
                f"classify={classify['intent_type']}, dispatch={dispatch['intent_type']}"
            )

        # Check project_slug (allow None vs "" differences)
        classify_slug = classify["project_slug"] or None
        dispatch_slug = dispatch["project_slug"] or None
        if classify_slug != dispatch_slug:
            return False, (
                f"Mismatch in intent {i+1} project_slug: "
                f"classify={classify_slug}, dispatch={dispatch_slug}"
            )

        # Check confidence (allow 0.05 difference for floating point)
        if abs(classify["confidence"] - dispatch["confidence"]) > 0.05:
            return False, (
                f"Mismatch in intent {i+1} confidence: "
                f"classify={classify['confidence']}, dispatch={dispatch['confidence']}"
            )

        # Check urgency
        if classify["urgency"] != dispatch["urgency"]:
            return False, (
                f"Mismatch in intent {i+1} urgency: "
                f"classify={classify['urgency']}, dispatch={dispatch['urgency']}"
            )

        # Check lookup_kind (optional field)
        classify_lookup = classify.get("lookup_kind")
        dispatch_lookup = dispatch.get("lookup_kind")
        if classify_lookup != dispatch_lookup:
            return False, (
                f"Mismatch in intent {i+1} lookup_kind: "
                f"classify={classify_lookup}, dispatch={dispatch_lookup}"
            )

    return True, "Classifications match perfectly"


async def test_single_utterance(test_case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test a single utterance against both endpoints.

    Returns:
        Dict with test results
    """
    utterance = test_case["utterance"]
    test_name = test_case["name"]
    session_id = f"test-consistency-{test_name}"
    surface_id = f"surface-{test_name}"

    print(f"\n{'='*80}")
    print(f"Testing: {test_name}")
    print(f"Utterance: {utterance}")
    print(f"{'='*80}")

    try:
        # Call /api/v1/test/intent-classify
        print("Calling /api/v1/test/intent-classify...")
        classify_result = await test_intent_classify(utterance, session_id)
        print(f"Result: {classify_result['message']}")
        print(f"Classifications: {json.dumps(classify_result['classifications'], indent=2)}")

        # Call /api/v1/test/dispatch
        print(f"\nCalling /api/v1/test/dispatch...")
        dispatch_result = await test_dispatch(utterance, session_id, surface_id)
        print(f"Result: {dispatch_result['message']}")
        print(f"DEBUG: Full dispatch_result keys: {list(dispatch_result.keys())}")
        if dispatch_result.get("results"):
            print(f"DEBUG: First result keys: {list(dispatch_result['results'][0].keys())}")
            print(f"DEBUG: First result sample: {json.dumps(dispatch_result['results'][0], indent=2)[:500]}")

        # Extract classifications from dispatch results
        # The dispatch endpoint returns results with intent_type at the top level
        dispatch_classifications = []
        if dispatch_result.get("results"):
            for result in dispatch_result["results"]:
                # Extract classification fields from result
                # The result object contains the final intent_type after processing
                dispatch_classifications.append({
                    "intent_type": result.get("intent_type"),
                    "project_slug": result.get("project_slug"),
                    "confidence": result.get("confidence", 1.0),
                    "utterance_fragment": result.get("utterance_fragment", utterance),
                    "reasoning": result.get("reasoning", ""),
                    "urgency": result.get("urgency", "normal"),
                    "lookup_kind": result.get("lookup_kind"),
                })
                print(f"DEBUG: Extracted from result: intent_type={result.get('intent_type')}, project_slug={result.get('project_slug')}")

        print(f"Dispatch classifications: {json.dumps(dispatch_classifications, indent=2)}")

        # Compare classifications
        match, message = compare_classifications(
            classify_result["classifications"],
            dispatch_classifications,
            utterance,
        )

        print(f"\nComparison: {'✓ PASS' if match else '✗ FAIL'}")
        print(f"Message: {message}")

        return {
            "name": test_name,
            "utterance": utterance,
            "match": match,
            "message": message,
            "classify_count": len(classify_result["classifications"]),
            "dispatch_count": len(dispatch_classifications),
            "classify_result": classify_result,
            "dispatch_result": dispatch_result,
        }

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            "name": test_name,
            "utterance": utterance,
            "match": False,
            "message": f"Exception: {str(e)}",
            "error": str(e),
        }


async def main():
    """Run all consistency tests."""
    print("="*80)
    print("Intent Classification Consistency Test")
    print("Verifying /api/v1/test/intent-classify vs /api/v1/test/dispatch")
    print("="*80)

    results = []

    for test_case in TEST_UTTERANCES:
        result = await test_single_utterance(test_case)
        results.append(result)

    # Print summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    passed = sum(1 for r in results if r["match"])
    failed = sum(1 for r in results if not r["match"])

    print(f"Total tests: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {passed/len(results)*100:.1f}%")

    if failed > 0:
        print("\nFailed tests:")
        for result in results:
            if not result["match"]:
                print(f"  - {result['name']}: {result['message']}")

    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
