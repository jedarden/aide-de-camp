#!/usr/bin/env python3
"""Test STT fallback endpoint with mocked whisper-stt backend."""

import asyncio
import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

# Ensure the project root is in the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


# Mock audio data for testing
MOCK_AUDIO_BYTES = b"mock audio data"
MOCK_AUDIO_BASE64 = base64.b64encode(MOCK_AUDIO_BYTES).decode("utf-8")


async def test_stt_endpoint_success():
    """Test POST /api/v1/stt with successful transcription."""
    print("\nTesting STT endpoint: successful transcription...")

    from src.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # Mock the STT fallback service
    mock_stt = AsyncMock()
    mock_stt.transcribe.return_value = "Hello world"

    with patch("src.main.get_stt_fallback", return_value=mock_stt):
        response = client.post(
            "/api/v1/stt",
            json={
                "audio_data": MOCK_AUDIO_BASE64,
                "format": "webm"
            }
        )

    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Hello world"
    assert data["status"] == "success"

    # Verify the STT fallback was called with correct parameters
    mock_stt.transcribe.assert_called_once()
    call_args = mock_stt.transcribe.call_args
    assert call_args[0][0] == MOCK_AUDIO_BYTES
    assert call_args[0][1] == "webm"

    print("  ✅ STT endpoint returns transcribed text")
    return True


async def test_stt_endpoint_missing_audio():
    """Test POST /api/v1/stt with missing audio_data."""
    print("\nTesting STT endpoint: missing audio_data...")

    from src.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    response = client.post(
        "/api/v1/stt",
        json={"format": "webm"}
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Missing audio_data" in data["error"]

    print("  ✅ STT endpoint returns 400 for missing audio_data")
    return True


async def test_stt_endpoint_invalid_base64():
    """Test POST /api/v1/stt with invalid base64 data."""
    print("\nTesting STT endpoint: invalid base64...")

    from src.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    response = client.post(
        "/api/v1/stt",
        json={
            "audio_data": "not-valid-base64!!!",
            "format": "webm"
        }
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid base64" in data["error"]

    print("  ✅ STT endpoint returns 400 for invalid base64")
    return True


async def test_stt_endpoint_transcription_fails():
    """Test POST /api/v1/stt when transcription fails."""
    print("\nTesting STT endpoint: transcription failure...")

    from src.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # Mock the STT fallback service to return None (transcription failure)
    mock_stt = AsyncMock()
    mock_stt.transcribe.return_value = None

    with patch("src.main.get_stt_fallback", return_value=mock_stt):
        response = client.post(
            "/api/v1/stt",
            json={
                "audio_data": MOCK_AUDIO_BASE64,
                "format": "webm"
            }
        )

    assert response.status_code == 500
    data = response.json()
    assert "error" in data
    assert "Transcription failed" in data["error"]

    print("  ✅ STT endpoint returns 500 when transcription fails")
    return True


async def test_stt_fallback_transcribe():
    """Test STTFallback.transcribe() with mocked httpx client."""
    print("\nTesting STTFallback.transcribe()...")

    from src.stt.fallback import STTFallback

    stt = STTFallback()

    # Mock successful httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"text": "Test transcript"}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = await stt.transcribe(MOCK_AUDIO_BYTES, "webm")

    assert result == "Test transcript"
    assert stt._is_available == True

    print("  ✅ STTFallback.transcribe() returns text")
    return True


async def test_stt_fallback_check_available():
    """Test STTFallback.check_available() with mocked httpx client."""
    print("\nTesting STTFallback.check_available()...")

    from src.stt.fallback import STTFallback

    stt = STTFallback()

    # Mock successful health check
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = await stt.check_available()

    assert result == True
    assert stt._is_available == True

    print("  ✅ STTFallback.check_available() returns True")
    return True


async def test_stt_status_endpoint():
    """Test GET /api/v1/status/stt."""
    print("\nTesting STT status endpoint...")

    from src.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # Mock the STT fallback service
    mock_stt = MagicMock()
    mock_stt.get_status.return_value = {
        "available": True,
        "stt_url": "https://whisper.ardenone.com",
        "failure_count": 0
    }

    with patch("src.main.get_stt_fallback", return_value=mock_stt):
        response = client.get("/api/v1/status/stt")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] == True
    assert data["stt_url"] == "https://whisper.ardenone.com"
    assert data["failure_count"] == 0

    print("  ✅ STT status endpoint returns status")
    return True


async def main():
    """Run all STT tests."""
    print("\n" + "="*60)
    print("STT Fallback Endpoint Tests")
    print("="*60)

    tests = [
        test_stt_endpoint_success,
        test_stt_endpoint_missing_audio,
        test_stt_endpoint_invalid_base64,
        test_stt_endpoint_transcription_fails,
        test_stt_fallback_transcribe,
        test_stt_fallback_check_available,
        test_stt_status_endpoint,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            result = await test()
            if result:
                passed += 1
            else:
                failed += 1
        except AssertionError as e:
            print(f"  ❌ Test failed: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ Test error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
