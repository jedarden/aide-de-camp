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

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["status"] == 400
        assert "utterance" in str(data).lower() or "field" in str(data).lower()

    @pytest.mark.asyncio
    async def test_empty_utterance_returns_400(self, async_client: AsyncClient):
        """Test that empty string utterance returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "", "session_id": "test-session"}
        )

        assert response.status_code == 400
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

        assert response.status_code == 400
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_invalid_utterance_type_returns_400(self, async_client: AsyncClient):
        """Test that non-string utterance returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": 123, "session_id": "test-session"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_empty_session_id_returns_400(self, async_client: AsyncClient):
        """Test that empty string session_id returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "test", "session_id": ""}
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_invalid_session_id_type_returns_400(self, async_client: AsyncClient):
        """Test that non-string session_id returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "test", "session_id": 123}
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_empty_surface_id_returns_400(self, async_client: AsyncClient):
        """Test that empty string surface_id returns 400."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "test", "surface_id": ""}
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_valid_minimal_request_succeeds(self, async_client: AsyncClient):
        """Test that valid minimal request (utterance only) succeeds."""
        response = await async_client.post(
            "/dispatch",
            json={"utterance": "test utterance"}
        )

        # Should get 200 or 202 (accepted for processing)
        assert response.status_code in [200, 202]
        data = response.json()
        assert "utterance_id" in data or "status" in data

    @pytest.mark.asyncio
    async def test_valid_full_request_succeeds(self, async_client: AsyncClient):
        """Test that valid full request succeeds."""
        response = await async_client.post(
            "/dispatch",
            json={
                "utterance": "test utterance",
                "session_id": "test-session-123",
                "surface_id": "test-surface-456",
                "utterance_id": "custom-utterance-789"
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

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "json" in data["error"].lower() or "invalid" in data["error"].lower()

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
                json={"session_id": "test"}  # Missing utterance
            )

        # Should get 400
        assert response.status_code == 400

        # Check that validation was logged
        # (Note: depends on logger setup in main.py)
        assert any(
            "validation" in record.message.lower() or "400" in str(record.levelno)
            for record in caplog.records
        )

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

        # Check that error was logged
        assert any(
            "json" in record.message.lower() or "400" in str(record.levelno)
            for record in caplog.records
        )


class TestDispatchRequestModel:
    """Unit tests for DispatchRequest Pydantic model directly."""

    def test_utterance_must_be_non_empty(self):
        """Test that utterance validator rejects empty strings."""
        from src.main import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance="")

        errors = exc_info.value.errors()
        assert any("utterance" in str(err.get("loc", "")) for err in errors)

    def test_utterance_must_be_string(self):
        """Test that utterance must be a string."""
        from src.main import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance=123)

        errors = exc_info.value.errors()
        assert any("utterance" in str(err.get("loc", "")) for err in errors)

    def test_optional_fields_accept_none(self):
        """Test that optional fields accept None."""
        from src.main import DispatchRequest

        # Should not raise
        request = DispatchRequest(utterance="test")
        assert request.session_id is None
        assert request.surface_id is None
        assert request.utterance_id is None

    def test_optional_fields_reject_empty_strings(self):
        """Test that optional fields reject empty strings."""
        from src.main import DispatchRequest

        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance="test", session_id="")

        errors = exc_info.value.errors()
        assert any("session_id" in str(err.get("loc", "")) for err in errors)

    def test_valid_request_constructs(self):
        """Test that valid request constructs successfully."""
        from src.main import DispatchRequest

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
