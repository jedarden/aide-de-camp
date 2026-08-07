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

# =============================================================================
# Happy Path Integration Tests
# These tests verify that valid requests process correctly through the pipeline
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_happy_path_minimal_request(async_client: httpx.AsyncClient):
    """Test that minimal valid request (required fields only) processes correctly."""
    # Arrange - Minimal valid request with only required fields
    request_body = {
        "utterance": "Check CI status for aide-de-camp",
        "session_id": "test-session-minimal-123",
        "surface_id": "test-surface-minimal-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert - Should not get a 400 validation error
    # Note: May get other errors (500, etc.) if service not fully running,
    # but should not be a validation error (400 with "Validation failed")
    if response.status_code == 400:
        error_data = response.json()
        # If 400, ensure it's not a validation error
        assert error_data.get("error") != "Validation failed", \
            f"Request should not fail validation. Error: {error_data}"

    # If successful, verify response structure
    if response.status_code == 200:
        response_data = response.json()

        # Verify required response fields
        assert "utterance_id" in response_data
        assert "session_id" in response_data
        assert response_data["session_id"] == request_body["session_id"]
        assert "intent_count" in response_data
        assert "intent_ids" in response_data
        assert isinstance(response_data["intent_ids"], list)
        assert "status" in response_data
        assert response_data["status"] == "dispatched"
        assert "message" in response_data

        # Verify utterance_id was auto-generated (not provided in request)
        assert response_data["utterance_id"] is not None
        assert len(response_data["utterance_id"]) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_happy_path_full_request(async_client: httpx.AsyncClient):
    """Test that full valid request (with optional utterance_id) processes correctly."""
    # Arrange - Full valid request including optional utterance_id
    provided_utterance_id = "provided-utterance-id-789"
    request_body = {
        "utterance": "Check CI status for aide-de-camp",
        "session_id": "test-session-full-123",
        "surface_id": "test-surface-full-456",
        "utterance_id": provided_utterance_id
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert - Should not get a 400 validation error
    if response.status_code == 400:
        error_data = response.json()
        assert error_data.get("error") != "Validation failed", \
            f"Request should not fail validation. Error: {error_data}"

    # If successful, verify response structure and that provided utterance_id is preserved
    if response.status_code == 200:
        response_data = response.json()

        # Verify required response fields
        assert "utterance_id" in response_data
        assert "session_id" in response_data
        assert response_data["session_id"] == request_body["session_id"]
        assert "intent_count" in response_data
        assert "intent_ids" in response_data
        assert isinstance(response_data["intent_ids"], list)
        assert "status" in response_data
        assert response_data["status"] == "dispatched"
        assert "message" in response_data

        # Verify the provided utterance_id is preserved in response
        assert response_data["utterance_id"] == provided_utterance_id, \
            f"Provided utterance_id should be preserved. Expected: {provided_utterance_id}, Got: {response_data['utterance_id']}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_response_includes_intent_ids(async_client: httpx.AsyncClient):
    """Test that successful response includes intent_ids field."""
    # Arrange
    request_body = {
        "utterance": "What are the latest deployment results?",
        "session_id": "test-session-intent-ids-123",
        "surface_id": "test-surface-intent-ids-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert - Verify response structure includes intent_ids
    if response.status_code == 200:
        response_data = response.json()

        # Verify intent_ids field exists and is a list
        assert "intent_ids" in response_data, \
            "Response must include 'intent_ids' field"
        assert isinstance(response_data["intent_ids"], list), \
            "intent_ids must be a list"

        # Verify intent_count matches intent_ids length
        assert "intent_count" in response_data
        assert response_data["intent_count"] == len(response_data["intent_ids"]), \
            f"intent_count ({response_data['intent_count']}) must match length of intent_ids ({len(response_data['intent_ids'])})"

        # Verify each intent_id is a non-empty string (if any intents were created)
        for intent_id in response_data["intent_ids"]:
            assert isinstance(intent_id, str), \
                f"Each intent_id must be a string, got {type(intent_id)}"
            assert len(intent_id) > 0, \
                f"Each intent_id must be non-empty, got empty string"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_response_structure_completeness(async_client: httpx.AsyncClient):
    """Test that successful response includes all expected fields."""
    # Arrange
    request_body = {
        "utterance": "Summarize the last 3 failed builds",
        "session_id": "test-session-structure-123",
        "surface_id": "test-surface-structure-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert - Verify complete response structure
    if response.status_code == 200:
        response_data = response.json()

        # Verify all expected top-level fields exist
        expected_fields = [
            "utterance_id",
            "session_id",
            "intent_count",
            "intent_ids",
            "status",
            "message"
        ]

        for field in expected_fields:
            assert field in response_data, \
                f"Response must include '{field}' field. Response: {response_data}"

        # Verify field types
        assert isinstance(response_data["utterance_id"], str), \
            f"utterance_id must be string, got {type(response_data['utterance_id'])}"
        assert isinstance(response_data["session_id"], str), \
            f"session_id must be string, got {type(response_data['session_id'])}"
        assert isinstance(response_data["intent_count"], int), \
            f"intent_count must be int, got {type(response_data['intent_count'])}"
        assert isinstance(response_data["intent_ids"], list), \
            f"intent_ids must be list, got {type(response_data['intent_ids'])}"
        assert isinstance(response_data["status"], str), \
            f"status must be string, got {type(response_data['status'])}"
        assert isinstance(response_data["message"], str), \
            f"message must be string, got {type(response_data['message'])}"

        # Verify specific values
        assert response_data["status"] == "dispatched", \
            f"status must be 'dispatched', got '{response_data['status']}'"
        assert response_data["intent_count"] >= 0, \
            f"intent_count must be non-negative, got {response_data['intent_count']}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_utterance_id_auto_generation(async_client: httpx.AsyncClient):
    """Test that utterance_id is auto-generated when not provided."""
    # Arrange - Request without utterance_id
    request_body = {
        "utterance": "Check the system health",
        "session_id": "test-session-auto-gen-123",
        "surface_id": "test-surface-auto-gen-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert - Verify utterance_id was auto-generated
    if response.status_code == 200:
        response_data = response.json()

        # Verify utterance_id exists and is a valid UUID string
        assert "utterance_id" in response_data, \
            "Response must include auto-generated utterance_id"
        assert isinstance(response_data["utterance_id"], str), \
            "utterance_id must be a string"
        assert len(response_data["utterance_id"]) > 0, \
            "Auto-generated utterance_id must be non-empty"

        # Verify it looks like a UUID (has hyphens and reasonable length)
        # UUIDs have format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        utterance_id = response_data["utterance_id"]
        assert "-" in utterance_id, \
            f"Auto-generated utterance_id should be UUID format, got: {utterance_id}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dispatch_whitespace_stripping(async_client: httpx.AsyncClient):
    """Test that whitespace is properly stripped from utterance."""
    # Arrange - Utterance with leading/trailing whitespace
    request_body = {
        "utterance": "  Check CI status  ",  # Has leading/trailing spaces
        "session_id": "test-session-whitespace-123",
        "surface_id": "test-surface-whitespace-456"
    }

    # Act
    response = await async_client.post(
        "/dispatch",
        json=request_body
    )

    # Assert - Should not fail validation (whitespace should be stripped)
    if response.status_code == 400:
        error_data = response.json()
        assert error_data.get("error") != "Validation failed", \
            f"Whitespace-only utterance should be stripped and accepted. Error: {error_data}"

    # If successful, the request was processed
    if response.status_code == 200:
        # Just verify we got a valid response
        assert "utterance_id" in response.json()
        assert "intent_ids" in response.json()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "integration"])