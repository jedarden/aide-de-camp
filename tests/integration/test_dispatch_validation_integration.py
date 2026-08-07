"""
Integration tests for /dispatch 400 validation responses.

Tests that the /dispatch endpoint returns proper 400 HTTP responses for:
- Missing required fields
- Empty string fields
- Invalid types
- Malformed JSON requests

Verifies error response structure matches Pydantic validation error format.
Uses httpx.AsyncClient to hit the actual endpoint.
"""
import json
import pytest
import httpx
from typing import Dict, Any


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_missing_utterance_field(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when utterance field is missing."""
    # Arrange - Missing utterance field
    request_body = {
        "session_id": "test-session-123",
        "surface_id": "test-surface-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert error_data["status"] == 400
    assert "errors" in error_data

    # Verify utterance field is mentioned in errors
    error_fields = [error["field"] for error in error_data["errors"]]
    assert any("utterance" in field for field in error_fields)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_missing_session_id_field(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when session_id field is missing."""
    # Arrange - Missing session_id field
    request_body = {
        "utterance": "Test utterance",
        "surface_id": "test-surface-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert error_data["status"] == 400
    assert "errors" in error_data

    # Verify session_id field is mentioned in errors
    error_fields = [error["field"] for error in error_data["errors"]]
    assert any("session_id" in field for field in error_fields)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_missing_surface_id_field(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when surface_id field is missing."""
    # Arrange - Missing surface_id field
    request_body = {
        "utterance": "Test utterance",
        "session_id": "test-session-123"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert error_data["status"] == 400
    assert "errors" in error_data

    # Verify surface_id field is mentioned in errors
    error_fields = [error["field"] for error in error_data["errors"]]
    assert any("surface_id" in field for field in error_fields)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_empty_utterance_string(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when utterance is an empty string."""
    # Arrange - Empty utterance
    request_body = {
        "utterance": "",
        "session_id": "test-session-123",
        "surface_id": "test-surface-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert error_data["status"] == 400
    assert "errors" in error_data

    # Verify utterance error message mentions string length requirement
    utterance_errors = [
        error for error in error_data["errors"]
        if "utterance" in error["field"]
    ]
    assert len(utterance_errors) > 0
    # Pydantic error message for min_length validation
    assert "at least 1 character" in utterance_errors[0]["message"].lower() or "non-empty" in utterance_errors[0]["message"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_whitespace_only_utterance(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when utterance contains only whitespace."""
    # Arrange - Whitespace-only utterance
    request_body = {
        "utterance": "   \t\n  ",
        "session_id": "test-session-123",
        "surface_id": "test-surface-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert "errors" in error_data

    # Verify utterance error message
    utterance_errors = [
        error for error in error_data["errors"]
        if "utterance" in error["field"]
    ]
    assert len(utterance_errors) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_empty_session_id(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when session_id is an empty string."""
    # Arrange - Empty session_id
    request_body = {
        "utterance": "Test utterance",
        "session_id": "",
        "surface_id": "test-surface-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert "errors" in error_data

    # Verify session_id error message mentions string length requirement
    session_id_errors = [
        error for error in error_data["errors"]
        if "session_id" in error["field"]
    ]
    assert len(session_id_errors) > 0
    # Pydantic error message for min_length validation
    assert "at least 1 character" in session_id_errors[0]["message"].lower() or "non-empty" in session_id_errors[0]["message"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_empty_surface_id(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when surface_id is an empty string."""
    # Arrange - Empty surface_id
    request_body = {
        "utterance": "Test utterance",
        "session_id": "test-session-123",
        "surface_id": ""
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert "errors" in error_data

    # Verify surface_id error message mentions string length requirement
    surface_id_errors = [
        error for error in error_data["errors"]
        if "surface_id" in error["field"]
    ]
    assert len(surface_id_errors) > 0
    # Pydantic error message for min_length validation
    assert "at least 1 character" in surface_id_errors[0]["message"].lower() or "non-empty" in surface_id_errors[0]["message"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_invalid_utterance_type(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when utterance is not a string."""
    # Arrange - Integer instead of string
    request_body = {
        "utterance": 12345,
        "session_id": "test-session-123",
        "surface_id": "test-surface-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert "errors" in error_data

    # Verify type error for utterance
    utterance_errors = [
        error for error in error_data["errors"]
        if "utterance" in error["field"]
    ]
    assert len(utterance_errors) > 0
    # Error should mention string type
    error_message = utterance_errors[0]["message"].lower()
    assert "string" in error_message or "str" in error_message


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_invalid_session_id_type(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when session_id is not a string."""
    # Arrange - Boolean instead of string
    request_body = {
        "utterance": "Test utterance",
        "session_id": True,
        "surface_id": "test-surface-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert "errors" in error_data

    # Verify type error for session_id
    session_id_errors = [
        error for error in error_data["errors"]
        if "session_id" in error["field"]
    ]
    assert len(session_id_errors) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_invalid_surface_id_type(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when surface_id is not a string."""
    # Arrange - List instead of string
    request_body = {
        "utterance": "Test utterance",
        "session_id": "test-session-123",
        "surface_id": ["not", "a", "string"]
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert "errors" in error_data

    # Verify type error for surface_id
    surface_id_errors = [
        error for error in error_data["errors"]
        if "surface_id" in error["field"]
    ]
    assert len(surface_id_errors) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_invalid_utterance_id_type(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when utterance_id is provided but not a string."""
    # Arrange - Object instead of string (utterance_id is optional but must be string if provided)
    request_body = {
        "utterance": "Test utterance",
        "session_id": "test-session-123",
        "surface_id": "test-surface-456",
        "utterance_id": {"invalid": "object"}
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert "errors" in error_data

    # Verify type error for utterance_id
    utterance_id_errors = [
        error for error in error_data["errors"]
        if "utterance_id" in error["field"]
    ]
    assert len(utterance_id_errors) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_empty_utterance_id(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 when utterance_id is provided but empty."""
    # Arrange - Empty string for optional utterance_id
    request_body = {
        "utterance": "Test utterance",
        "session_id": "test-session-123",
        "surface_id": "test-surface-456",
        "utterance_id": ""
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    assert error_data["error"] == "Validation failed"
    assert "errors" in error_data

    # Verify empty string error for utterance_id
    utterance_id_errors = [
        error for error in error_data["errors"]
        if "utterance_id" in error["field"]
    ]
    assert len(utterance_id_errors) > 0
    assert "non-empty" in utterance_id_errors[0]["message"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_malformed_json(async_client: httpx.AsyncClient):
    """Test that /dispatch returns 400 for malformed JSON request."""
    # Arrange - Invalid JSON string (trailing comma makes it invalid)
    malformed_json = '{"utterance": "test", "session_id": "123", "surface_id": "456",}'

    # Act
    response = await async_client.post(
        "/dispatch",
        content=malformed_json,
        headers={"Content-Type": "application/json"}
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    # FastAPI may catch this as a validation error or JSON decode error
    assert error_data["status"] == 400
    assert "error" in error_data
    # Either validation failed or invalid JSON is acceptable
    assert error_data["error"] in ["Validation failed", "Invalid JSON"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_validation_error_response_structure(async_client: httpx.AsyncClient):
    """Test that validation error response matches Pydantic error structure."""
    # Arrange - Trigger multiple validation errors
    request_body = {
        "utterance": "",
        "session_id": 123,
        "surface_id": None
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()

    # Verify top-level structure
    assert "error" in error_data
    assert error_data["error"] == "Validation failed"
    assert "detail" in error_data
    assert "errors" in error_data
    assert "status" in error_data
    assert error_data["status"] == 400

    # Verify individual error structure
    errors = error_data["errors"]
    assert len(errors) > 0

    for error in errors:
        # Each error should have these fields
        assert "field" in error
        assert "message" in error
        assert "type" in error

        # Field should be a string
        assert isinstance(error["field"], str)
        # Message should be a string
        assert isinstance(error["message"], str)
        # Type should be a string
        assert isinstance(error["type"], str)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_multiple_validation_errors(async_client: httpx.AsyncClient):
    """Test that /dispatch returns all validation errors at once."""
    # Arrange - Trigger multiple errors
    request_body = {
        "utterance": 456,
        "session_id": "",
        "surface_id": ["invalid"]
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert
    assert response.status_code == 400

    error_data = response.json()
    errors = error_data["errors"]

    # Should have multiple errors (one for each field)
    assert len(errors) >= 3

    # Verify each field has an error
    error_fields = [error["field"] for error in errors]
    assert any("utterance" in field for field in error_fields)
    assert any("session_id" in field for field in error_fields)
    assert any("surface_id" in field for field in error_fields)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_valid_request_with_optional_fields(async_client: httpx.AsyncClient):
    """Test that valid request without optional utterance_id is accepted."""
    # Arrange - Valid minimal request
    request_body = {
        "utterance": "Test utterance",
        "session_id": "test-session-123",
        "surface_id": "test-surface-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert - Should not get validation error (may get other errors if service not fully running)
    # We only care that it's not a 400 validation error
    if response.status_code == 400:
        # If it is 400, it should not be a validation error
        error_data = response.json()
        assert error_data["error"] != "Validation failed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_valid_request_with_all_fields(async_client: httpx.AsyncClient):
    """Test that valid request with all fields including optional utterance_id is accepted."""
    # Arrange - Valid complete request
    request_body = {
        "utterance": "Test utterance",
        "session_id": "test-session-123",
        "surface_id": "test-surface-456",
        "utterance_id": "optional-utterance-id-789"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert - Should not get validation error
    if response.status_code == 400:
        error_data = response.json()
        assert error_data["error"] != "Validation failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "integration"])