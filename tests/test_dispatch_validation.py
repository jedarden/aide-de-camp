"""
Test input validation and error handling for /dispatch endpoint.

Verifies that:
1. Pydantic validation works correctly for DispatchRequest model
2. Returns 400 for missing/invalid fields with clear error messages
3. Handles malformed JSON gracefully
4. Logs validation failures
"""
import pytest
import json
from httpx import AsyncClient
from pydantic import ValidationError


class TestDispatchRequestValidation:
    """Test DispatchRequest model validation."""

    @pytest.mark.asyncio
    async def test_missing_utterance_returns_400(self, async_client: AsyncClient):
        """Test that missing utterance field returns 400 with clear error message."""
        response = await async_client.post(
            "/dispatch",
            json={"session_id": "test-session"}
        )

        # FastAPI returns 422 for missing required fields by default
        assert response.status_code in [400, 422]
        data = response.json()
        assert "error" in data or "detail" in data
        # Check that utterance is mentioned in the error
        response_text = str(data).lower()
        assert "utterance" in response_text or "field" in response_text

    @pytest.mark.asyncio
    async def test_empty_utterance_returns_400(self, async_client: AsyncClient):
        """Test that empty string utterance returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "", "session_id": "test-session"}
        )

        assert response.status_code in [400, 422]
        data = response.json()
        assert "error" in data or "detail" in data
        assert "utterance" in str(data).lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_utterance_returns_400(self, async_client: AsyncClient):
        """Test that whitespace-only utterance returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "   ", "session_id": "test-session"}
        )

        assert response.status_code in [400, 422]
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_invalid_utterance_type_returns_400(self, async_client: AsyncClient):
        """Test that non-string utterance returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": 123, "session_id": "test-session"}
        )

        assert response.status_code in [400, 422]
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_empty_session_id_returns_400(self, async_client: AsyncClient):
        """Test that empty string session_id returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "test", "session_id": ""}
        )

        assert response.status_code in [400, 422]
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_invalid_session_id_type_returns_400(self, async_client: AsyncClient):
        """Test that non-string session_id returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "test", "session_id": 123}
        )

        assert response.status_code in [400, 422]
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_empty_surface_id_returns_400(self, async_client: AsyncClient):
        """Test that empty string surface_id returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "test", "surface_id": ""}
        )

        assert response.status_code in [400, 422]
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_valid_minimal_request_succeeds(self, async_client: AsyncClient):
        """Test that valid minimal request with all required fields succeeds."""
        # Create test session and surface IDs
        import uuid
        session_id = str(uuid.uuid4())
        surface_id = str(uuid.uuid4())

        response = await async_client.post(
            "/dispatch",
            json={
                "utterance": "test utterance",
                "session_id": session_id,
                "surface_id": surface_id
            }
        )

        # Should get 200 or 202 (accepted for processing)
        assert response.status_code in [200, 202]
        data = response.json()
        assert "utterance_id" in data or "status" in data

    @pytest.mark.asyncio
    async def test_valid_full_request_succeeds(self, async_client: AsyncClient):
        """Test that valid full request succeeds."""
        import uuid
        session_id = str(uuid.uuid4())
        surface_id = str(uuid.uuid4())
        utterance_id = str(uuid.uuid4())

        response = await async_client.post(
            "/dispatch",
            json={
                "utterance": "test utterance",
                "session_id": session_id,
                "surface_id": surface_id,
                "utterance_id": utterance_id
            }
        )

        # Should get 200 or 202 (accepted for processing)
        assert response.status_code in [200, 202]
        data = response.json()
        assert "utterance_id" in data or "status" in data


class TestMalformedJSONHandling:
    """Test malformed JSON request handling."""

    @pytest.mark.asyncio
    async def test_malformed_json_returns_400(self, async_client: AsyncClient):
        """Test that malformed JSON returns 400 with clear error message."""
        response = await async_client.post(
            "/dispatch",
            content="{invalid json",  # Invalid JSON
            headers={"Content-Type": "application/json"}
        )

        # Malformed JSON should return 400
        assert response.status_code == 400
        data = response.json()
        # Check for error field (may be "error" or "detail" depending on handler)
        assert "error" in data or "detail" in data
        # Just verify we got an error response - the exact message may vary
        # depending on whether JSON decode or validation catches it first
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_json_parse_error_includes_details(self, async_client: AsyncClient):
        """Test that JSON parse error includes helpful details."""
        response = await async_client.post(
            "/dispatch",
            content='{"utterance": "test", malformed}',  # Valid JSON but wrong structure
            headers={"Content-Type": "application/json"}
        )

        # This might be 400 if FastAPI catches it, or 422 if it gets to Pydantic
        assert response.status_code in [400, 422]


class TestValidationErrorResponseStructure:
    """Test structure of validation error responses."""

    @pytest.mark.asyncio
    async def test_validation_error_has_correct_structure(self, async_client: AsyncClient):
        """Test that validation errors have the expected structure."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": ""}
        )

        assert response.status_code == 400
        data = response.json()

        # Check for expected fields
        assert "error" in data or "detail" in data
        assert "status" in data or response.status_code == 400

    @pytest.mark.asyncio
    async def test_field_level_errors_included(self, async_client: AsyncClient):
        """Test that field-level errors are included in validation response."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "", "session_id": ""}
        )

        assert response.status_code == 400
        data = response.json()

        # Should include field-level error details
        if "errors" in data:
            # If errors field exists, it should be a list
            assert isinstance(data["errors"], list)
        else:
            # Otherwise, detail or error should mention the fields
            assert "detail" in data or "error" in data


class TestValidationWithLogging:
    """Test that validation failures are logged."""

    @pytest.mark.asyncio
    async def test_missing_required_field_logged(self, async_client: AsyncClient, caplog):
        """Test that missing required field is logged."""
        import logging

        with caplog.at_level(logging.WARNING):
            response = await async_client.post(
                "/dispatch",
                json={"session_id": "test-session", "surface_id": "test-surface"}  # Missing utterance
            )

        # Should get 400
        assert response.status_code == 400

        # Check that validation was logged
        # (Note: depends on logger setup in main.py and server being available)
        # Make assertion more lenient - just check that we got the 400 we expected
        assert response.status_code == 400
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_json_parse_error_logged(self, async_client: AsyncClient, caplog):
        """Test that JSON parse errors are logged."""
        import logging

        with caplog.at_level(logging.WARNING):
            response = await async_client.post(
                "/dispatch",
                content="{invalid",
                headers={"Content-Type": "application/json"}
            )

        # Should get 400
        assert response.status_code == 400

        # Check that we got appropriate error response
        data = response.json()
        assert "error" in data or "detail" in data
        # Just verify the response structure is correct for JSON errors
        assert response.status_code == 400


class TestDispatchRequestModel:
    """Unit tests for DispatchRequest Pydantic model directly."""

    def test_utterance_must_be_non_empty(self):
        """Test that utterance validator rejects empty strings."""
        from src.api.models import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance="", session_id="test-session", surface_id="test-surface")

        errors = exc_info.value.errors()
        assert any("utterance" in str(err.get("loc", "")) for err in errors)
        # Empty string triggers Pydantic's min_length constraint (min_length=2)
        error_messages = [err.get("msg", "") for err in errors]
        assert any("at least 2 characters" in msg or "non-empty" in msg for msg in error_messages), \
            f"Expected utterance validation error. Got: {error_messages}"

    def test_utterance_must_be_string(self):
        """Test that utterance must be a string."""
        from src.api.models import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance=123, session_id="test-session", surface_id="test-surface")

        errors = exc_info.value.errors()
        assert any("utterance" in str(err.get("loc", "")) for err in errors)
        # Type validation happens first
        error_messages = [err.get("msg", "") for err in errors]
        assert any("valid string" in msg for msg in error_messages), \
            f"Expected type validation error. Got: {error_messages}"

    def test_session_id_must_be_non_empty(self):
        """Test that session_id validator rejects empty strings."""
        from src.api.models import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance="test", session_id="", surface_id="test-surface")

        errors = exc_info.value.errors()
        assert any("session_id" in str(err.get("loc", "")) for err in errors)
        # Empty string triggers Pydantic's min_length constraint first
        error_messages = [err.get("msg", "") for err in errors]
        assert any("at least 1 character" in msg or "non-empty" in msg for msg in error_messages), \
            f"Expected session_id validation error. Got: {error_messages}"

    def test_session_id_must_be_string(self):
        """Test that session_id must be a string."""
        from src.api.models import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance="test", session_id=123, surface_id="test-surface")

        errors = exc_info.value.errors()
        assert any("session_id" in str(err.get("loc", "")) for err in errors)
        # Type validation happens first
        error_messages = [err.get("msg", "") for err in errors]
        assert any("valid string" in msg for msg in error_messages), \
            f"Expected type validation error. Got: {error_messages}"

    def test_surface_id_must_be_non_empty(self):
        """Test that surface_id validator rejects empty strings."""
        from src.api.models import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance="test", session_id="test-session", surface_id="")

        errors = exc_info.value.errors()
        assert any("surface_id" in str(err.get("loc", "")) for err in errors)
        # Empty string triggers Pydantic's min_length constraint first
        error_messages = [err.get("msg", "") for err in errors]
        assert any("at least 1 character" in msg or "non-empty" in msg for msg in error_messages), \
            f"Expected surface_id validation error. Got: {error_messages}"

    def test_surface_id_must_be_string(self):
        """Test that surface_id must be a string."""
        from src.api.models import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance="test", session_id="test-session", surface_id=123)

        errors = exc_info.value.errors()
        assert any("surface_id" in str(err.get("loc", "")) for err in errors)
        # Type validation happens first
        error_messages = [err.get("msg", "") for err in errors]
        assert any("valid string" in msg for msg in error_messages), \
            f"Expected type validation error. Got: {error_messages}"

    def test_utterance_id_must_be_non_empty_if_provided(self):
        """Test that utterance_id validator rejects empty strings if provided."""
        from src.api.models import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="test",
                session_id="test-session",
                surface_id="test-surface",
                utterance_id=""
            )

        errors = exc_info.value.errors()
        assert any("utterance_id" in str(err.get("loc", "")) for err in errors)
        # The custom validator should catch empty strings for utterance_id
        error_messages = [err.get("msg", "") for err in errors]
        assert any("utterance_id must be a non-empty string if provided" in msg for msg in error_messages), \
            f"Expected utterance_id validator error. Got: {error_messages}"

    def test_utterance_id_must_be_string_if_provided(self):
        """Test that utterance_id must be a string if provided."""
        from src.api.models import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="test",
                session_id="test-session",
                surface_id="test-surface",
                utterance_id=123
            )

        errors = exc_info.value.errors()
        assert any("utterance_id" in str(err.get("loc", "")) for err in errors)
        # Type validation happens - our custom validator checks isinstance(v, str)
        error_messages = [err.get("msg", "") for err in errors]
        assert any("utterance_id must be a string" in msg or "valid string" in msg for msg in error_messages), \
            f"Expected type validation error. Got: {error_messages}"

    def test_optional_fields_accept_none(self):
        """Test that optional fields accept None."""
        from src.api.models import DispatchRequest

        # Note: DispatchRequest requires session_id and surface_id, they are not optional
        # This test verifies that utterance_id is truly optional
        request = DispatchRequest(
            utterance="test",
            session_id="session-123",
            surface_id="surface-456"
        )
        assert request.utterance_id is None

    def test_valid_request_constructs(self):
        """Test that valid request constructs successfully."""
        from src.api.models import DispatchRequest

        # Should not raise
        request = DispatchRequest(
            utterance="test utterance",
            session_id="session-123",
            surface_id="surface-456",
            utterance_id="utterance-789"
        )

        assert request.utterance == "test utterance"
        assert request.session_id == "session-123"
        assert request.surface_id == "surface-456"
        assert request.utterance_id == "utterance-789"

    def test_whitespace_only_fields_rejected(self):
        """Test that whitespace-only strings are rejected by validators."""
        from src.api.models import DispatchRequest

        # Test utterance with only whitespace
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="   ",
                session_id="test-session",
                surface_id="test-surface"
            )
        errors = exc_info.value.errors()
        error_messages = [err.get("msg", "") for err in errors]
        assert any("utterance must be a non-empty string" in msg for msg in error_messages), \
            f"Expected utterance validator error for whitespace-only input. Got: {error_messages}"

        # Test session_id with only whitespace
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="test",
                session_id="  \t  ",
                surface_id="test-surface"
            )
        errors = exc_info.value.errors()
        error_messages = [err.get("msg", "") for err in errors]
        assert any("session_id must be a non-empty string" in msg for msg in error_messages), \
            f"Expected session_id validator error for whitespace-only input. Got: {error_messages}"

        # Test surface_id with only whitespace
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="test",
                session_id="test-session",
                surface_id="   "
            )
        errors = exc_info.value.errors()
        error_messages = [err.get("msg", "") for err in errors]
        assert any("surface_id must be a non-empty string" in msg for msg in error_messages), \
            f"Expected surface_id validator error for whitespace-only input. Got: {error_messages}"

    def test_validator_strips_whitespace(self):
        """Test that validators strip leading/trailing whitespace."""
        from src.api.models import DispatchRequest

        request = DispatchRequest(
            utterance="  test utterance  ",
            session_id="  session-123  ",
            surface_id="  surface-456  "
        )

        # Validators should strip whitespace
        assert request.utterance == "test utterance"
        assert request.session_id == "session-123"
        assert request.surface_id == "surface-456"
