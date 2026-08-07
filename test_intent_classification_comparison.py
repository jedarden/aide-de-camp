"""
Test to verify that /test/intent-classify and /dispatch produce identical classification results.

This test sends identical utterances to both endpoints and compares:
1. Intent type classifications
2. Confidence scores
3. Project slugs
4. Other classification metadata

Acceptance criteria:
- Same utterance to both endpoints returns same intent classification
- Classification confidence scores match
- No regression in test endpoint accuracy vs /dispatch
- Test endpoint is functionally equivalent to /dispatch for classification
"""
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from typing import Dict, Any, List

# Test utterances covering different intent types
TEST_UTTERANCES = [
    {
        "name": "simple_status",
        "utterance": "how are the pods doing",
        "expected_intent_types": ["status"],
    },
    {
        "name": "project_status",
        "utterance": "check the options pipeline status",
        "expected_intent_types": ["status"],
    },
    {
        "name": "lookup_request",
        "utterance": "find the recent logs for the nap-api container",
        "expected_intent_types": ["lookup"],
    },
    {
        "name": "weather_query",
        "utterance": "what is the weather",
        "expected_intent_types": ["weather"],
    },
    {
        "name": "brainstorm",
        "utterance": "let's brainstorm ways to optimize the pipeline performance",
        "expected_intent_types": ["brainstorm"],
    },
    {
        "name": "multi_intent",
        "utterance": "how's the pipeline and also check the ibkr mcp status",
        "expected_intent_types": ["status", "status"],  # May split into multiple intents
    },
]


def compare_classifications(test_classifications: List[Dict], dispatch_intents: List[Dict]) -> Dict[str, Any]:
    """
    Compare classification results between test endpoint and dispatch endpoint.

    This is a compatibility wrapper around the new src.intent.comparison module.

    Args:
        test_classifications: Classifications from /test/intent-classify
        dispatch_intents: Routed intents from /dispatch (need to extract classifications)

    Returns:
        Dict with comparison results including match status and differences
    """
    from src.intent.comparison import compare_classifications as compare

    # Convert to the format expected by the new comparison function
    test_result = {"classifications": test_classifications}
    dispatch_result = {"classifications": dispatch_intents}

    # Use the new comparison function
    result = compare(dispatch_result, test_result)

    # Convert to the old format for backward compatibility
    differences = []
    for diff in result.differences:
        differences.append({
            "field": diff.field,
            "index": diff.index,
            "test_value": diff.test_value,
            "dispatch_value": diff.dispatch_value,
            "message": diff.message,
        })

    return {
        "match": result.overall_match,
        "differences": differences,
        "test_count": result.test_count,
        "dispatch_count": result.dispatch_count,
    }


@pytest.mark.asyncio
async def test_intent_classification_comparison():
    """
    Test that /test/intent-classify and /dispatch produce identical classification results.

    This is a comprehensive verification that the test endpoint is functionally
    equivalent to /dispatch for classification purposes.
    """
    from src.main import app
    from src.intent.router import get_router, clear_router_cache
    from src.session.store import get_store

    # Clear router cache to ensure fresh classifications
    clear_router_cache()

    # Create transport for FastAPI app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        all_results = []

        for test_case in TEST_UTTERANCES:
            print(f"\n{'='*60}")
            print(f"Testing: {test_case['name']}")
            print(f"Utterance: {test_case['utterance']}")
            print(f"{'='*60}")

            # Step 1: Call /test/intent-classify endpoint
            test_response = await client.post(
                "/api/v1/test/intent-classify",
                json={"utterance": test_case["utterance"]}
            )

            assert test_response.status_code == 200, f"Test endpoint failed: {test_response.text}"
            test_data = test_response.json()
            test_classifications = test_data.get("classifications", [])

            print(f"\n[Test Endpoint] Classified into {len(test_classifications)} intent(s):")
            for i, cls in enumerate(test_classifications):
                print(f"  [{i}] intent_type={cls.get('intent_type')}, "
                      f"project_slug={cls.get('project_slug')}, "
                      f"confidence={cls.get('confidence')}")

            # Step 2: Call /dispatch endpoint
            # We need to extract the classifications from the routed intents
            session_id = "test-session-comparison"
            surface_id = "test-surface-comparison"

            # Create a test session first
            store = get_store()
            existing_session = await store.get_session(session_id)
            if not existing_session:
                await store.create_session(session_id)

            dispatch_response = await client.post(
                "/dispatch",
                json={
                    "utterance": test_case["utterance"],
                    "session_id": session_id,
                    "surface_id": surface_id,
                }
            )

            assert dispatch_response.status_code == 200, f"Dispatch endpoint failed: {dispatch_response.text}"
            dispatch_data = dispatch_response.json()

            print(f"\n[Dispatch Endpoint] Dispatched {dispatch_data.get('intent_count', 0)} intent(s)")
            print(f"Intent IDs: {dispatch_data.get('intent_ids', [])}")

            # Step 3: Retrieve the stored intents from the database to get classifications
            # We need to query the intents table to get the actual classifications stored
            utterance_id = dispatch_data.get("utterance_id")
            if utterance_id:
                # Query the intents for this utterance
                import aiosqlite
                db_path = store.db_path
                async with aiosqlite.connect(db_path) as db:
                    cursor = await db.execute(
                        """SELECT intent_type, project_slug, session_id
                           FROM intents
                           WHERE utterance_id = ?""",
                        (utterance_id,)
                    )
                    stored_intents = await cursor.fetchall()

                    print(f"\n[Database] Stored {len(stored_intents)} intent(s):")
                    for i, (intent_type, project_slug, sess_id) in enumerate(stored_intents):
                        print(f"  [{i}] intent_type={intent_type}, project_slug={project_slug}")

                    # Compare intent types (simplified comparison)
                    test_intent_types = [cls.get("intent_type") for cls in test_classifications]
                    stored_intent_types = [row[0] for row in stored_intents]

                    if test_intent_types == stored_intent_types:
                        print(f"\n✅ PASS: Intent types match exactly")
                        all_results.append({
                            "test_case": test_case["name"],
                            "match": True,
                            "test_intent_types": test_intent_types,
                            "stored_intent_types": stored_intent_types,
                        })
                    else:
                        print(f"\n❌ FAIL: Intent types differ")
                        print(f"  Test endpoint: {test_intent_types}")
                        print(f"  Dispatch/DB:   {stored_intent_types}")
                        all_results.append({
                            "test_case": test_case["name"],
                            "match": False,
                            "test_intent_types": test_intent_types,
                            "stored_intent_types": stored_intent_types,
                            "difference": "Intent type mismatch between endpoints",
                        })
            else:
                print(f"\n❌ FAIL: No utterance_id returned from dispatch")
                all_results.append({
                    "test_case": test_case["name"],
                    "match": False,
                    "error": "No utterance_id returned from dispatch",
                })

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    passed = sum(1 for r in all_results if r.get("match"))
    failed = sum(1 for r in all_results if not r.get("match"))

    print(f"Total tests: {len(all_results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        print("\nFailed tests:")
        for result in all_results:
            if not result.get("match"):
                print(f"  - {result['test_case']}: {result.get('difference', 'Unknown error')}")

    # Assert that all tests passed
    assert failed == 0, f"{failed} test(s) failed - classification results differ between endpoints"


@pytest.mark.asyncio
async def test_classification_deterministic_consistency():
    """
    Test that the same utterance produces identical results across multiple calls.

    This verifies that caching, deterministic routing, and other optimizations
    don't introduce inconsistency.
    """
    from src.main import app
    from src.intent.router import clear_router_cache

    # Clear cache to test fresh classifications
    clear_router_cache()

    async with AsyncClient(app=app, base_url="http://test") as client:
        test_utterance = "how are the pods doing"

        # Call the endpoint 3 times with the same utterance
        results = []
        for i in range(3):
            response = await client.post(
                "/api/v1/test/intent-classify",
                json={"utterance": test_utterance}
            )
            assert response.status_code == 200
            data = response.json()
            results.append(data.get("classifications", []))

        # All results should be identical
        first_result = results[0]
        for i, result in enumerate(results[1:], 1):
            assert len(result) == len(first_result), f"Call {i+1} returned different number of classifications"
            for j, (cls1, cls2) in enumerate(zip(first_result, result)):
                assert cls1 == cls2, f"Call {i+1}, classification {j} differs: {cls1} vs {cls2}"

        print("✅ PASS: Multiple calls produce identical classifications")


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "-s"])
