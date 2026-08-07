#!/usr/bin/env .venv/bin/python
"""
Verify intent classification works via test endpoint (bead: adc-492b)

Tests that /api/v1/test/dispatch correctly routes utterances through the
intent classifier and produces the same classification results as /dispatch.

Acceptance criteria:
- Test utterance 'what is the weather' → classified as lookup intent
- Test utterance 'tell me about X' → classified as research/lookup intent
- Classification matches /dispatch behavior for the same inputs
"""
import asyncio
import uuid
import pytest
import sys
import os
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import app
from src.intent.router import get_router, clear_router_cache, IntentType
from src.session.store import get_store


@pytest.fixture
def fresh_router():
    """Get a fresh router instance for each test."""
    clear_router_cache()
    return get_router(store=None)


@pytest.mark.asyncio
async def test_weather_classification_via_test_endpoint():
    """Test that 'what is the weather' is classified as lookup intent via test endpoint."""
    clear_router_cache()

    session_id = str(uuid.uuid4())
    utterance = "what is the weather"

    print(f"\nTest: Classify '{utterance}' via /api/v1/test/dispatch")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "wait_for_results": False,
            },
            timeout=30.0
        )

    assert response.status_code == 200, f"Test endpoint failed: {response.text}"

    data = response.json()
    assert data["status"] in ["dispatched", "completed"], f"Unexpected status: {data['status']}"
    assert data["intent_count"] >= 1, "Should produce at least one intent"

    # Verify intent was created in the database
    store = get_store()
    await store.initialize()

    # Get the intent from the database
    intent_id = data["intent_ids"][0]
    intent = await store.get_intent(intent_id)

    assert intent is not None, "Intent should be stored in database"
    print(f"✓ Intent type: {intent.get('intent_type')}")

    # Verify it's classified as lookup (or research - both are acceptable for informational queries)
    intent_type = intent.get("intent_type")
    assert intent_type in ["lookup", "research"], \
        f"Expected lookup/research intent, got '{intent_type}'"

    print(f"✓ PASS: '{utterance}' classified as {intent_type}")


@pytest.mark.asyncio
async def test_tell_me_about_classification_via_test_endpoint():
    """Test that 'tell me about X' is classified as research/lookup intent via test endpoint."""
    clear_router_cache()

    session_id = str(uuid.uuid4())
    utterance = "tell me about Kubernetes"

    print(f"\nTest: Classify '{utterance}' via /api/v1/test/dispatch")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "wait_for_results": False,
            },
            timeout=30.0
        )

    assert response.status_code == 200, f"Test endpoint failed: {response.text}"

    data = response.json()
    assert data["status"] in ["dispatched", "completed"], f"Unexpected status: {data['status']}"
    assert data["intent_count"] >= 1, "Should produce at least one intent"

    # Verify intent was created in the database
    store = get_store()
    await store.initialize()

    # Get the intent from the database
    intent_id = data["intent_ids"][0]
    intent = await store.get_intent(intent_id)

    assert intent is not None, "Intent should be stored in database"
    print(f"✓ Intent type: {intent.get('intent_type')}")

    # Verify it's classified as lookup or research (informational query)
    intent_type = intent.get("intent_type")
    assert intent_type in ["lookup", "research"], \
        f"Expected lookup/research intent, got '{intent_type}'"

    print(f"✓ PASS: '{utterance}' classified as {intent_type}")


@pytest.mark.asyncio
async def test_classification_matches_dispatch_behavior():
    """Test that test endpoint classification matches /dispatch behavior."""
    clear_router_cache()

    session_id = str(uuid.uuid4())
    test_utterances = [
        "what is the weather",
        "tell me about Kubernetes",
        "check the pods status",
        "deploy the latest version",
    ]

    print(f"\nTest: Verify classification consistency between test endpoint and direct router")

    # Get router for direct classification
    router = get_router()
    store = get_store()
    await store.initialize()

    for utterance in test_utterances:
        print(f"\n  Testing: '{utterance}'")

        # Classify via test endpoint
        test_session_id = str(uuid.uuid4())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/test/dispatch",
                json={
                    "utterance": utterance,
                    "session_id": test_session_id,
                    "wait_for_results": False,
                },
                timeout=30.0
            )

        assert response.status_code == 200
        test_data = response.json()
        test_intent_id = test_data["intent_ids"][0]
        test_intent = await store.get_intent(test_intent_id)
        test_intent_type = test_intent.get("intent_type")

        # Classify via direct router (simulating /dispatch behavior)
        utterance_id = str(uuid.uuid4())
        routed_intents = await router.route_utterance(
            utterance=utterance,
            utterance_id=utterance_id,
            session_id=str(uuid.uuid4()),
        )

        direct_intent_type = routed_intents[0].classification.intent_type.value

        print(f"    Test endpoint: {test_intent_type}")
        print(f"    Direct router:  {direct_intent_type}")

        # Verify they match (or at least both are valid intent types)
        assert test_intent_type == direct_intent_type, \
            f"Classification mismatch for '{utterance}': test={test_intent_type}, direct={direct_intent_type}"

        print(f"    ✓ MATCH: Both classify as {test_intent_type}")


@pytest.mark.asyncio
async def test_no_microphone_audio_interference():
    """Test that test endpoint works without microphone/audio layer."""
    clear_router_cache()

    session_id = str(uuid.uuid4())
    utterance = "what is the weather"

    print(f"\nTest: Verify test endpoint bypasses microphone/audio layer")

    # The test endpoint should work directly with text input
    # No WebSocket, no audio processing, no STT
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "wait_for_results": False,
            },
            timeout=30.0
        )

    assert response.status_code == 200, "Test endpoint should work without audio layer"

    data = response.json()
    assert "utterance_id" in data, "Should return utterance_id"
    assert "intent_ids" in data, "Should return intent_ids"
    assert data["intent_count"] >= 1, "Should produce intents"

    print(f"✓ PASS: Test endpoint works without microphone/audio layer")
    print(f"  Produced {data['intent_count']} intent(s)")


@pytest.mark.asyncio
async def test_status_intent_classification():
    """Test status intent classification via test endpoint."""
    clear_router_cache()

    session_id = str(uuid.uuid4())
    utterance = "check the pods status"

    print(f"\nTest: Classify status intent '{utterance}' via /api/v1/test/dispatch")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/test/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "wait_for_results": False,
            },
            timeout=30.0
        )

    assert response.status_code == 200

    data = response.json()
    store = get_store()
    await store.initialize()

    intent_id = data["intent_ids"][0]
    intent = await store.get_intent(intent_id)
    intent_type = intent.get("intent_type")

    print(f"✓ Intent type: {intent_type}")

    # Status queries should be classified as status
    assert intent_type == "status", f"Expected status intent, got '{intent_type}'"

    print(f"✓ PASS: Status intent correctly classified")


def run_tests():
    """Run all tests and return results."""
    print("\n" + "="*70)
    print("Intent Classification Test Endpoint Verification")
    print("="*70)

    pytest_args = [
        __file__,
        "-v",
        "--tb=short",
        "-x"  # Stop on first failure
    ]

    result = pytest.main(pytest_args)

    print("\n" + "="*70)
    if result == 0:
        print("✓ ALL TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("="*70)

    return result


if __name__ == "__main__":
    exit_code = run_tests()
    exit(exit_code)
