#!/usr/bin/env python3
"""
Test research classification via /api/v1/test/dispatch endpoint.

Verifies that the research utterance from TEST_UTTERANCES is correctly
classified when sent through the test dispatch endpoint.

Acceptance Criteria:
- Research utterance is dispatched via test endpoint
- Response contains results with research intent type
- Classification matches expected_intent_type from TEST_UTTERANCES
- Test is automated and passes consistently
"""
import asyncio
import sys
import pytest
import httpx
from typing import Dict, Any


# Research test utterance from TEST_UTTERANCES
RESEARCH_UTTERANCE = "tell me about Kubernetes architecture patterns"
EXPECTED_INTENT_TYPE = "lookup"  # Research queries are classified as lookup


class TestResearchClassification:
    """Test suite for research classification via test endpoint."""

    @pytest.mark.asyncio
    async def test_research_utterance_classification_via_endpoint(self):
        """
        Test that the research utterance is correctly classified as lookup intent.

        This test verifies the acceptance criteria for adc-62lbp:
        1. Research utterance is dispatched via test endpoint
        2. Response contains results with research intent type
        3. Classification matches expected_intent_type from TEST_UTTERANCES
        """
        async with httpx.AsyncClient() as client:
            # Dispatch the research utterance
            response = await client.post(
                "http://localhost:8000/api/v1/test/dispatch",
                json={
                    "utterance": RESEARCH_UTTERANCE,
                    "wait_for_results": True,
                    "timeout_seconds": 30,
                },
                timeout=60.0,
            )

            # Verify successful dispatch
            assert response.status_code == 200, f"Dispatch failed: {response.text}"
            data = response.json()

            # Verify response structure
            assert data["status"] == "completed", f"Expected completed status, got {data['status']}"
            assert data["intent_count"] >= 1, "Expected at least 1 intent"
            assert len(data["intent_ids"]) >= 1, "Expected at least 1 intent ID"

            # Verify results are present
            assert "results" in data, "Response should contain results"
            assert len(data["results"]) >= 1, "Expected at least 1 result"

            # Get the first result (for single-intent utterances)
            result = data["results"][0]

            # Verify classification matches expected
            actual_intent_type = result.get("intent_type")
            assert actual_intent_type == EXPECTED_INTENT_TYPE, \
                f"Expected intent_type '{EXPECTED_INTENT_TYPE}', got '{actual_intent_type}'"

            # Verify the result was successfully processed
            assert result.get("status") == "resolved", \
                f"Expected resolved status, got {result.get('status')}"

            # Verify topic and result IDs are present
            assert result.get("topic_id"), "Result should have a topic_id"
            assert result.get("result_id"), "Result should have a result_id"

            print(f"✓ Research utterance correctly classified as '{actual_intent_type}'")
            print(f"✓ Topic ID: {result.get('topic_id')}")
            print(f"✓ Result ID: {result.get('result_id')}")

    @pytest.mark.asyncio
    async def test_research_utterance_consistency(self):
        """
        Test that research classification is consistent across multiple calls.

        This ensures the classification is stable and doesn't randomly change.
        """
        async with httpx.AsyncClient() as client:
            # Make multiple requests to verify consistency
            results = []
            num_trials = 3

            for i in range(num_trials):
                response = await client.post(
                    "http://localhost:8000/api/v1/test/dispatch",
                    json={
                        "utterance": RESEARCH_UTTERANCE,
                        "wait_for_results": True,
                        "timeout_seconds": 30,
                    },
                    timeout=60.0,
                )

                assert response.status_code == 200, f"Trial {i+1} failed: {response.text}"
                data = response.json()

                # Extract intent type from first result
                if data.get("results") and len(data["results"]) > 0:
                    intent_type = data["results"][0].get("intent_type")
                    results.append(intent_type)

            # Verify all results are consistent
            assert len(results) == num_trials, f"Expected {num_trials} results, got {len(results)}"
            assert all(intent_type == EXPECTED_INTENT_TYPE for intent_type in results), \
                f"Inconsistent classification: {results}"

            print(f"✓ Research classification consistent across {num_trials} trials")

    @pytest.mark.asyncio
    async def test_research_via_named_endpoint(self):
        """
        Test research classification using the named utterance endpoint.

        This tests the convenience endpoint /api/v1/test/dispatch/{utterance_name}.
        """
        async with httpx.AsyncClient() as client:
            # First verify the research_query utterance exists
            list_response = await client.get(
                "http://localhost:8000/api/v1/test/utterances"
            )
            assert list_response.status_code == 200

            utterances = list_response.json().get("utterances", [])
            research_utterance = next(
                (u for u in utterances if u.get("name") == "research_query"),
                None
            )
            assert research_utterance is not None, "research_query utterance not found"

            # Verify expected intent type
            assert research_utterance.get("expected_intent_type") == EXPECTED_INTENT_TYPE, \
                f"Expected expected_intent_type '{EXPECTED_INTENT_TYPE}', got '{research_utterance.get('expected_intent_type')}'"

            # Test using the named endpoint
            response = await client.post(
                "http://localhost:8000/api/v1/test/dispatch/research_query",
                params={
                    "wait_for_results": True,
                    "timeout_seconds": 30,
                },
                timeout=60.0,
            )

            assert response.status_code == 200, f"Named endpoint failed: {response.text}"
            data = response.json()

            # Verify classification
            assert data.get("status") == "completed"
            if data.get("results") and len(data["results"]) > 0:
                actual_intent_type = data["results"][0].get("intent_type")
                assert actual_intent_type == EXPECTED_INTENT_TYPE, \
                    f"Named endpoint: Expected '{EXPECTED_INTENT_TYPE}', got '{actual_intent_type}'"

            print(f"✓ Research classification works via named endpoint")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
