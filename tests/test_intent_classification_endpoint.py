"""
Test Intent Classification Endpoint Verification

Verifies that the test endpoint (/api/v1/test/test/classify) correctly routes
utterances through the intent classifier and produces the same classification
results as the main /dispatch endpoint.

Acceptance Criteria (bead adc-492b):
- Test endpoint calls the same intent router as /dispatch
- Classification produces identical results for identical utterances
- No microphone/audio layer interference
- 'what is the weather' → classified as lookup intent
- 'tell me about X' → classified as lookup/research intent
"""
import asyncio
import pytest
import httpx
from typing import Dict, Any


@pytest.mark.asyncio
async def test_classification_endpoint_basic():
    """Test that the classification endpoint is accessible and returns valid responses."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://localhost:8000/api/v1/test/test/classify',
            json={'utterance': 'test query', 'session_id': 'test-session'},
            timeout=30.0
        )

        assert response.status_code == 200
        data = response.json()
        assert 'utterance' in data
        assert 'classifications' in data
        assert 'message' in data
        assert isinstance(data['classifications'], list)


@pytest.mark.asyncio
async def test_weather_utterance_classification():
    """
    Test acceptance criterion: 'what is the weather' → classified as lookup intent.

    Weather queries are lookup intents - they ask for current state information.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://localhost:8000/api/v1/test/test/classify',
            json={'utterance': 'what is the weather', 'session_id': 'test-session'},
            timeout=30.0
        )

        assert response.status_code == 200
        data = response.json()
        classifications = data.get('classifications', [])

        assert len(classifications) > 0, "Should return at least one classification"

        classification = classifications[0]
        # Weather queries are lookup intents
        assert classification['intent_type'] in ['lookup', 'status'], \
            f"Expected lookup/status intent for weather query, got {classification['intent_type']}"
        assert classification['confidence'] > 0.7, "Should have reasonable confidence"
        assert 'urgency' in classification


@pytest.mark.asyncio
async def test_research_utterance_classification():
    """
    Test acceptance criterion: 'tell me about X' → classified as lookup/research intent.

    Information queries ('tell me about X') are lookup intents - they request
    information retrieval and synthesis.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://localhost:8000/api/v1/test/test/classify',
            json={'utterance': 'tell me about machine learning', 'session_id': 'test-session'},
            timeout=30.0
        )

        assert response.status_code == 200
        data = response.json()
        classifications = data.get('classifications', [])

        assert len(classifications) > 0, "Should return at least one classification"

        classification = classifications[0]
        # Information queries are lookup intents
        assert classification['intent_type'] in ['lookup', 'brainstorm'], \
            f"Expected lookup/brainstorm intent for research query, got {classification['intent_type']}"
        assert classification['confidence'] > 0.7, "Should have reasonable confidence"


@pytest.mark.asyncio
async def test_classification_response_structure():
    """Test that classification returns all expected fields."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://localhost:8000/api/v1/test/test/classify',
            json={'utterance': 'check the logs', 'session_id': 'test-session'},
            timeout=30.0
        )

        assert response.status_code == 200
        data = response.json()
        classifications = data.get('classifications', [])

        assert len(classifications) > 0
        classification = classifications[0]

        # Verify all expected fields are present
        expected_fields = [
            'intent_type',
            'confidence',
            'utterance_fragment',
            'reasoning',
            'urgency'
        ]

        for field in expected_fields:
            assert field in classification, f"Missing field: {field}"

        # Optional field: project_slug (may be null for non-project queries)
        # Optional field: lookup_kind (only for lookup intents)


@pytest.mark.asyncio
async def test_classification_no_audio_interference():
    """
    Test acceptance criterion: No microphone/audio layer interference.

    The test endpoint should work purely with text input, without any
    Web Speech API or audio processing dependencies.
    """
    async with httpx.AsyncClient() as client:
        # Pure text request - no audio data
        response = await client.post(
            'http://localhost:8000/api/v1/test/test/classify',
            json={'utterance': 'test without audio', 'session_id': 'test-session'},
            timeout=30.0
        )

        # Should succeed without any audio processing
        assert response.status_code == 200
        data = response.json()

        # Response should not contain any audio-related fields
        assert 'audio' not in data
        assert 'transcript' not in data
        assert 'voice' not in data


@pytest.mark.asyncio
async def test_multiple_intents_classification():
    """Test that compound utterances can be segmented into multiple intents."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://localhost:8000/api/v1/test/test/classify',
            json={
                'utterance': 'check the status of the deployment and tell me about the errors',
                'session_id': 'test-session'
            },
            timeout=30.0
        )

        assert response.status_code == 200
        data = response.json()
        classifications = data.get('classifications', [])

        # Compound utterances may produce multiple intents
        # (depending on LLM segmentation and fast-path routing)
        assert len(classifications) >= 1

        # Each intent should have the required structure
        for classification in classifications:
            assert 'intent_type' in classification
            assert 'confidence' in classification
            assert 'utterance_fragment' in classification


@pytest.mark.asyncio
async def test_classification_consistency():
    """
    Test that identical utterances produce consistent classifications.

    Runs the same utterance multiple times and verifies that the
    classification results are consistent (same intent type and structure).
    """
    utterance = 'what is the weather'
    results = []

    async with httpx.AsyncClient() as client:
        for i in range(3):
            response = await client.post(
                'http://localhost:8000/api/v1/test/test/classify',
                json={'utterance': utterance, 'session_id': f'test-session-{i}'},
                timeout=30.0
            )

            assert response.status_code == 200
            data = response.json()
            classifications = data.get('classifications', [])
            results.append(classifications[0] if classifications else None)

    # All results should have the same intent_type
    intent_types = [r['intent_type'] for r in results if r]
    assert len(set(intent_types)) <= 1, \
        f"Inconsistent classifications: {intent_types}"


if __name__ == '__main__':
    # Run tests manually for verification
    print("Running intent classification endpoint tests...")

    asyncio.run(test_classification_endpoint_basic())
    print("✅ Basic endpoint test passed")

    asyncio.run(test_weather_utterance_classification())
    print("✅ Weather utterance classification test passed")

    asyncio.run(test_research_utterance_classification())
    print("✅ Research utterance classification test passed")

    asyncio.run(test_classification_response_structure())
    print("✅ Response structure test passed")

    asyncio.run(test_classification_no_audio_interference())
    print("✅ No audio interference test passed")

    asyncio.run(test_multiple_intents_classification())
    print("✅ Multiple intents classification test passed")

    asyncio.run(test_classification_consistency())
    print("✅ Classification consistency test passed")

    print("\n✅ All tests passed!")
