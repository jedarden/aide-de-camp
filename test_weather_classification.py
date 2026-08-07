"""
Test weather classification via /api/v1/test/dispatch endpoint.

This test verifies that the weather utterance is correctly classified
when sent through the test dispatch endpoint, as required by bead adc-1p19m.

The test verifies:
1. Weather utterance can be dispatched via the named test endpoint
2. Response contains results with the correct intent type (lookup)
3. Classification matches the expected behavior (informational query → lookup)
"""
import asyncio
import pytest
import httpx


BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
async def test_weather_utterance_exists():
    """Verify the weather_query utterance is available in TEST_UTTERANCES."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/v1/test/utterances")
        assert response.status_code == 200

        utterances = response.json()["utterances"]
        weather_utterance = next(
            (u for u in utterances if u["name"] == "weather_query"),
            None
        )
        assert weather_utterance is not None, "weather_query utterance not found"
        assert weather_utterance["utterance"] == "what is the weather"


@pytest.mark.asyncio
async def test_weather_classification_via_named_endpoint():
    """
    Test weather classification using the named test endpoint.

    This tests the complete flow:
    - POST /api/v1/test/dispatch/weather_query
    - Verifies intent_type is correctly classified as "lookup"
    - Verifies the response contains expected fields
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch/weather_query",
            params={
                "wait_for_results": True,
                "timeout_seconds": 30
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data["status"] == "completed"
        assert data["intent_count"] == 1
        assert len(data["intent_ids"]) == 1
        assert "results" in data
        assert len(data["results"]) == 1

        # Verify the classification
        result = data["results"][0]
        assert result["intent_type"] == "lookup"
        assert result["status"] in ("resolved", "error", "timeout")

        # Verify expected fields are present
        assert "intent_id" in result
        assert "topic_id" in result
        assert "result_id" in result
        assert "summary" in result
        assert "urgency" in result
        assert "coverage" in result


@pytest.mark.asyncio
async def test_weather_classification_via_direct_dispatch():
    """
    Test weather classification using the direct dispatch endpoint.

    This tests that the utterance text "what is the weather" is correctly
    classified when sent directly to POST /api/v1/test/dispatch.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch",
            json={
                "utterance": "what is the weather",
                "wait_for_results": True,
                "timeout_seconds": 30
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify classification
        assert data["status"] == "completed"
        assert len(data["results"]) >= 1

        # Find the lookup intent (weather queries classify as lookup)
        lookup_result = next(
            (r for r in data["results"] if r["intent_type"] == "lookup"),
            None
        )
        assert lookup_result is not None, "No lookup intent found in results"


@pytest.mark.asyncio
async def test_weather_classification_matches_expected_intent_type():
    """
    Test that weather classification matches the expected intent type.

    NOTE: "weather" is NOT a valid IntentType in the codebase. Weather
    queries like "what is the weather" are classified as "lookup" intent.
    This test verifies that the actual classification matches this expected
    behavior.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch/weather_query",
            params={
                "wait_for_results": True,
                "timeout_seconds": 30
            }
        )

        assert response.status_code == 200
        data = response.json()

        result = data["results"][0]

        # The actual classification is "lookup", not "weather"
        # "weather" is not a valid IntentType enum value
        assert result["intent_type"] == "lookup", (
            f"Expected intent_type 'lookup' for weather query, "
            f"got '{result['intent_type']}'"
        )


@pytest.mark.asyncio
async def test_weather_utterance_text_classification():
    """
    Test that the exact utterance text "what is the weather" is correctly
    classified regardless of how it's sent (named endpoint vs direct).
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Test via named endpoint
        named_response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch/weather_query",
            params={"wait_for_results": True, "timeout_seconds": 30}
        )
        assert named_response.status_code == 200
        named_result = named_response.json()["results"][0]

        # Test via direct dispatch
        direct_response = await client.post(
            f"{BASE_URL}/api/v1/test/dispatch",
            json={
                "utterance": "what is the weather",
                "wait_for_results": True,
                "timeout_seconds": 30
            }
        )
        assert direct_response.status_code == 200
        direct_result = direct_response.json()["results"][0]

        # Both should have the same classification
        assert named_result["intent_type"] == direct_result["intent_type"]
        assert named_result["intent_type"] == "lookup"


async def run_all_tests():
    """Run all tests manually for verification."""
    print("Testing weather classification via test endpoint...")

    try:
        await test_weather_utterance_exists()
        print("✓ weather_query utterance exists")

        await test_weather_classification_via_named_endpoint()
        print("✓ Weather classification via named endpoint works")

        await test_weather_classification_via_direct_dispatch()
        print("✓ Weather classification via direct dispatch works")

        await test_weather_classification_matches_expected_intent_type()
        print("✓ Weather classification matches expected intent_type (lookup)")

        await test_weather_utterance_text_classification()
        print("✓ Weather utterance text classification is consistent")

        print("\n✅ All weather classification tests passed!")

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())
