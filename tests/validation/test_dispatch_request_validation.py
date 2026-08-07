"""
Test DispatchRequest model validation.

Comprehensive tests for Pydantic model validation including:
- Valid request creation
- Missing required fields
- Empty string validation
- Validator error messages
"""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.models import DispatchRequest
from src.main import app


class TestValidRequestCreation:
    """Test cases for valid request creation."""

    def test_minimal_valid_request(self):
        """Test creating a request with only required fields."""
        request = DispatchRequest(
            utterance="Check CI status",
            session_id="session-123",
            surface_id="surface-456"
        )

        assert request.utterance == "Check CI status"
        assert request.session_id == "session-123"
        assert request.surface_id == "surface-456"
        assert request.utterance_id is None

    def test_full_valid_request(self):
        """Test creating a request with all fields including optional."""
        request = DispatchRequest(
            utterance="Check CI status",
            session_id="550e8400-e29b-41d4-a716-446655440000",
            surface_id="surface-abc123",
            utterance_id="660e8400-e29b-41d4-a716-446655440000"
        )

        assert request.utterance == "Check CI status"
        assert request.session_id == "550e8400-e29b-41d4-a716-446655440000"
        assert request.surface_id == "surface-abc123"
        assert request.utterance_id == "660e8400-e29b-41d4-a716-446655440000"

    def test_utterance_is_stripped(self):
        """Test that utterance is stripped of leading/trailing whitespace."""
        request = DispatchRequest(
            utterance="  Check CI status  ",
            session_id="session-123",
            surface_id="surface-456"
        )

        assert request.utterance == "Check CI status"

    def test_session_id_is_stripped(self):
        """Test that session_id is stripped of leading/trailing whitespace."""
        request = DispatchRequest(
            utterance="Check CI status",
            session_id="  session-123  ",
            surface_id="surface-456"
        )

        assert request.session_id == "session-123"

    def test_surface_id_is_stripped(self):
        """Test that surface_id is stripped of leading/trailing whitespace."""
        request = DispatchRequest(
            utterance="Check CI status",
            session_id="session-123",
            surface_id="  surface-456  "
        )

        assert request.surface_id == "surface-456"


class TestMissingRequiredFields:
    """Test cases for missing required fields."""

    def test_missing_utterance(self):
        """Test that missing utterance field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0
        assert utterance_errors[0]['type'] == 'missing'

    def test_missing_session_id(self):
        """Test that missing session_id field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        session_errors = [e for e in errors if 'session_id' in str(e.get('loc', ''))]

        assert len(session_errors) > 0
        assert session_errors[0]['type'] == 'missing'

    def test_missing_surface_id(self):
        """Test that missing surface_id field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="session-123"
            )

        errors = exc_info.value.errors()
        surface_errors = [e for e in errors if 'surface_id' in str(e.get('loc', ''))]

        assert len(surface_errors) > 0
        assert surface_errors[0]['type'] == 'missing'

    def test_multiple_missing_fields(self):
        """Test that multiple missing fields are reported together."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(utterance="Check CI status")

        errors = exc_info.value.errors()
        missing_fields = [e for e in errors if e['type'] == 'missing']

        # Should report both session_id and surface_id as missing
        assert len(missing_fields) >= 2


class TestEmptyStringValidation:
    """Test cases for empty string validation."""

    def test_empty_utterance_string(self):
        """Test that empty utterance string raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="",
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0
        error_msg = str(utterance_errors[0].get('msg', ''))
        # Pydantic's built-in min_length validation runs first
        assert ('string' in error_msg.lower() or 'character' in error_msg.lower())

    def test_whitespace_only_utterance(self):
        """Test that whitespace-only utterance raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="   ",
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0
        error_msg = str(utterance_errors[0].get('msg', ''))
        assert 'utterance must be a non-empty string' in error_msg

    def test_empty_session_id_string(self):
        """Test that empty session_id string raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        session_errors = [e for e in errors if 'session_id' in str(e.get('loc', ''))]

        assert len(session_errors) > 0
        error_msg = str(session_errors[0].get('msg', ''))
        assert 'session_id must be a non-empty string' in error_msg

    def test_whitespace_only_session_id(self):
        """Test that whitespace-only session_id raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="   ",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        session_errors = [e for e in errors if 'session_id' in str(e.get('loc', ''))]

        assert len(session_errors) > 0
        error_msg = str(session_errors[0].get('msg', ''))
        assert 'session_id must be a non-empty string' in error_msg

    def test_empty_surface_id_string(self):
        """Test that empty surface_id string raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="session-123",
                surface_id=""
            )

        errors = exc_info.value.errors()
        surface_errors = [e for e in errors if 'surface_id' in str(e.get('loc', ''))]

        assert len(surface_errors) > 0
        error_msg = str(surface_errors[0].get('msg', ''))
        assert 'surface_id must be a non-empty string' in error_msg

    def test_whitespace_only_surface_id(self):
        """Test that whitespace-only surface_id raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="session-123",
                surface_id="   "
            )

        errors = exc_info.value.errors()
        surface_errors = [e for e in errors if 'surface_id' in str(e.get('loc', ''))]

        assert len(surface_errors) > 0
        error_msg = str(surface_errors[0].get('msg', ''))
        assert 'surface_id must be a non-empty string' in error_msg


class TestInvalidTypeValidation:
    """Test cases for invalid type validation."""

    def test_non_string_utterance(self):
        """Test that non-string utterance raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance=123,
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0

    def test_non_string_session_id(self):
        """Test that non-string session_id raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id=123,
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        session_errors = [e for e in errors if 'session_id' in str(e.get('loc', ''))]

        assert len(session_errors) > 0

    def test_non_string_surface_id(self):
        """Test that non-string surface_id raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="session-123",
                surface_id=123
            )

        errors = exc_info.value.errors()
        surface_errors = [e for e in errors if 'surface_id' in str(e.get('loc', ''))]

        assert len(surface_errors) > 0


class TestOptionalUtteranceIdValidation:
    """Test cases for optional utterance_id field validation."""

    def test_optional_utterance_id_none(self):
        """Test that utterance_id can be None (default)."""
        request = DispatchRequest(
            utterance="Check CI status",
            session_id="session-123",
            surface_id="surface-456"
        )

        assert request.utterance_id is None

    def test_optional_utterance_id_valid_string(self):
        """Test that utterance_id accepts valid string."""
        request = DispatchRequest(
            utterance="Check CI status",
            session_id="session-123",
            surface_id="surface-456",
            utterance_id="660e8400-e29b-41d4-a716-446655440000"
        )

        assert request.utterance_id == "660e8400-e29b-41d4-a716-446655440000"

    def test_optional_utterance_id_empty_string(self):
        """Test that empty string utterance_id raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="session-123",
                surface_id="surface-456",
                utterance_id=""
            )

        errors = exc_info.value.errors()
        utterance_id_errors = [e for e in errors if 'utterance_id' in str(e.get('loc', ''))]

        assert len(utterance_id_errors) > 0
        error_msg = str(utterance_id_errors[0].get('msg', ''))
        assert 'utterance_id must be a non-empty string if provided' in error_msg

    def test_optional_utterance_id_whitespace_only(self):
        """Test that whitespace-only utterance_id raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="session-123",
                surface_id="surface-456",
                utterance_id="   "
            )

        errors = exc_info.value.errors()
        utterance_id_errors = [e for e in errors if 'utterance_id' in str(e.get('loc', ''))]

        assert len(utterance_id_errors) > 0
        error_msg = str(utterance_id_errors[0].get('msg', ''))
        assert 'utterance_id must be a non-empty string if provided' in error_msg

    def test_optional_utterance_id_non_string(self):
        """Test that non-string utterance_id raises ValidationError with clear message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="session-123",
                surface_id="surface-456",
                utterance_id=123
            )

        errors = exc_info.value.errors()
        utterance_id_errors = [e for e in errors if 'utterance_id' in str(e.get('loc', ''))]

        assert len(utterance_id_errors) > 0
        error_msg = str(utterance_id_errors[0].get('msg', ''))
        assert 'utterance_id must be a string' in error_msg


class TestValidatorErrorMessages:
    """Test cases for validator error message clarity."""

    def test_utterance_error_message_is_clear(self):
        """Test that utterance validator provides clear error message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="",
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0
        error_msg = utterance_errors[0].get('msg', '')

        # Check for clear, actionable error message
        # With min_length=2, Pydantic's built-in validation runs first
        assert len(error_msg) > 0  # Not empty
        assert 'string' in error_msg.lower() or 'characters' in error_msg.lower()  # Mentions type
        # Error message mentions the length constraint
        assert '2' in error_msg or 'least' in error_msg.lower() or 'at least' in error_msg.lower()

    def test_session_id_error_message_is_clear(self):
        """Test that session_id validator provides clear error message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        session_errors = [e for e in errors if 'session_id' in str(e.get('loc', ''))]

        assert len(session_errors) > 0
        error_msg = session_errors[0].get('msg', '')

        # Check for clear, actionable error message
        assert 'session_id must be a non-empty string' in error_msg
        assert len(error_msg) > 0  # Not empty
        assert 'string' in error_msg.lower()  # Mentions type
        assert 'empty' in error_msg.lower()  # Mentions requirement

    def test_surface_id_error_message_is_clear(self):
        """Test that surface_id validator provides clear error message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="session-123",
                surface_id=""
            )

        errors = exc_info.value.errors()
        surface_errors = [e for e in errors if 'surface_id' in str(e.get('loc', ''))]

        assert len(surface_errors) > 0
        error_msg = surface_errors[0].get('msg', '')

        # Check for clear, actionable error message
        assert 'surface_id must be a non-empty string' in error_msg
        assert len(error_msg) > 0  # Not empty
        assert 'string' in error_msg.lower()  # Mentions type
        assert 'empty' in error_msg.lower()  # Mentions requirement

    def test_utterance_id_error_message_is_clear(self):
        """Test that utterance_id validator provides clear error message."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="Check CI status",
                session_id="session-123",
                surface_id="surface-456",
                utterance_id=""
            )

        errors = exc_info.value.errors()
        utterance_id_errors = [e for e in errors if 'utterance_id' in str(e.get('loc', ''))]

        assert len(utterance_id_errors) > 0
        error_msg = utterance_id_errors[0].get('msg', '')

        # Check for clear, actionable error message
        assert 'utterance_id must be a non-empty string if provided' in error_msg
        assert len(error_msg) > 0  # Not empty
        assert 'string' in error_msg.lower()  # Mentions type
        assert 'provided' in error_msg.lower()  # Mentions optional nature


class TestValidationErrorStructure:
    """Test cases for ValidationError structure and content."""

    def test_validation_error_contains_field_location(self):
        """Test that ValidationError includes field location."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="",
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0
        # Check that location is present and indicates the field
        assert 'loc' in utterance_errors[0]
        assert len(utterance_errors[0]['loc']) > 0

    def test_validation_error_contains_error_type(self):
        """Test that ValidationError includes error type."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="",
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0
        # Check that type is present
        assert 'type' in utterance_errors[0]
        assert len(utterance_errors[0]['type']) > 0

    def test_validation_error_can_be_converted_to_dict(self):
        """Test that ValidationError can be converted to dictionary."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="",
                session_id="session-123",
                surface_id="surface-456"
            )

        # Should be able to convert to dict
        error_dict = exc_info.value.errors()
        assert isinstance(error_dict, list)
        assert len(error_dict) > 0

    def test_multiple_errors_reported_together(self):
        """Test that multiple validation errors are reported together."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="",
                session_id="",
                surface_id=""
            )

        errors = exc_info.value.errors()

        # Should have multiple errors (one for each field)
        assert len(errors) >= 3


class TestEdgeCases:
    """Test cases for edge cases and boundary conditions."""

    def test_very_long_utterance(self):
        """Test that very long utterances are accepted."""
        long_utterance = "Check CI status " * 1000
        request = DispatchRequest(
            utterance=long_utterance,
            session_id="session-123",
            surface_id="surface-456"
        )

        # Validator strips trailing spaces, so expect stripped version
        expected = long_utterance.rstrip()
        assert request.utterance == expected
        assert len(request.utterance) > 10000  # Very long utterance preserved

    def test_unicode_in_utterance(self):
        """Test that Unicode characters in utterance are handled correctly."""
        request = DispatchRequest(
            utterance="Check CI status 🚀 ✓",
            session_id="session-123",
            surface_id="surface-456"
        )

        assert "🚀" in request.utterance
        assert "✓" in request.utterance

    def test_newlines_in_utterance(self):
        """Test that newlines in utterance are preserved."""
        utterance_with_newline = "Check CI status\nfor aide-de-camp"
        request = DispatchRequest(
            utterance=utterance_with_newline,
            session_id="session-123",
            surface_id="surface-456"
        )

        assert "\n" in request.utterance

    def test_tabs_in_utterance(self):
        """Test that tabs in utterance are preserved."""
        utterance_with_tabs = "Check CI status\tfor aide-de-camp"
        request = DispatchRequest(
            utterance=utterance_with_tabs,
            session_id="session-123",
            surface_id="surface-456"
        )

        assert "\t" in request.utterance


class TestMinLengthValidation:
    """Test cases for minimum length constraint validation."""

    def test_single_character_utterance(self):
        """Test that single-character utterance raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="A",
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0
        # Check that error mentions minimum length
        error_msg = str(utterance_errors[0].get('msg', ''))
        assert 'at least 2 characters' in error_msg.lower() or 'min_length' in str(utterance_errors[0]).lower()

    def test_utterance_exactly_min_length(self):
        """Test that utterance exactly at minimum length is accepted."""
        request = DispatchRequest(
            utterance="AB",
            session_id="session-123",
            surface_id="surface-456"
        )

        assert request.utterance == "AB"

    def test_utterance_above_min_length(self):
        """Test that utterance above minimum length is accepted."""
        request = DispatchRequest(
            utterance="Check CI status",
            session_id="session-123",
            surface_id="surface-456"
        )

        assert request.utterance == "Check CI status"

    def test_min_length_error_structure(self):
        """Test that min_length validation error has proper structure."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="A",
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0
        error = utterance_errors[0]

        # Verify error structure has required fields
        assert 'loc' in error
        assert 'msg' in error
        assert 'type' in error

        # Verify location points to utterance
        assert 'utterance' in str(error['loc'])

    def test_min_length_error_message_includes_limit(self):
        """Test that error message includes the minimum length requirement."""
        with pytest.raises(ValidationError) as exc_info:
            DispatchRequest(
                utterance="A",
                session_id="session-123",
                surface_id="surface-456"
            )

        errors = exc_info.value.errors()
        utterance_errors = [e for e in errors if 'utterance' in str(e.get('loc', ''))]

        assert len(utterance_errors) > 0
        error_msg = utterance_errors[0].get('msg', '')

        # Error message should mention the constraint
        assert len(error_msg) > 0
        # Pydantic typically includes "at least" and the number in min_length errors
        assert '2' in error_msg or 'two' in error_msg.lower() or 'min_length' in str(utterance_errors[0]).lower()


class TestDispatchEndpointValidation:
    """Integration tests for /dispatch endpoint request validation."""

    def test_missing_utterance_field_returns_400(self, test_client):
        """Test that missing utterance field returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_missing_utterance_error_structure(self, test_client):
        """Test that missing utterance error includes proper field validation structure."""
        response = test_client.post(
            "/dispatch",
            json={
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "detail" in error_data
        assert "error" in error_data
        assert "errors" in error_data

        # Verify error detail contains field validation information
        assert error_data["error"] == "Validation failed"
        errors = error_data["errors"]
        assert isinstance(errors, list)

        # Find utterance-related error
        utterance_errors = [e for e in errors if "utterance" in e.get("field", "")]
        assert len(utterance_errors) > 0

        # Verify error structure
        utterance_error = utterance_errors[0]
        assert "field" in utterance_error
        assert "message" in utterance_error
        assert "type" in utterance_error
        assert "utterance" in utterance_error["field"]
        assert utterance_error["type"] == "missing"

    def test_missing_session_id_field_returns_400(self, test_client):
        """Test that missing session_id field returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_missing_surface_id_field_returns_400(self, test_client):
        """Test that missing surface_id field returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-123"
            }
        )

        assert response.status_code == 400

    def test_empty_utterance_string_returns_400(self, test_client):
        """Test that empty utterance string returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "",
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_empty_utterance_error_message(self, test_client):
        """Test that empty utterance returns clear error message."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "",
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "errors" in error_data

        # Find utterance error
        errors = error_data["errors"]
        utterance_errors = [e for e in errors if "utterance" in e.get("field", "")]
        assert len(utterance_errors) > 0

        # Verify error message is clear
        utterance_error = utterance_errors[0]
        error_msg = utterance_error.get("message", "")
        assert len(error_msg) > 0
        # With min_length=2, error mentions characters/length
        assert "utterance" in error_msg.lower() or "characters" in error_msg.lower() or "length" in error_msg.lower()

    def test_whitespace_only_utterance_returns_400(self, test_client):
        """Test that whitespace-only utterance returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "   ",
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_multiple_missing_fields_returns_400(self, test_client):
        """Test that multiple missing fields are reported together."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status"
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "errors" in error_data

        errors = error_data["errors"]
        missing_errors = [e for e in errors if e.get("type") == "missing"]

        # Should report both session_id and surface_id as missing
        assert len(missing_errors) >= 2

        # Verify the missing fields are session_id and surface_id
        missing_fields = [e.get("field", "") for e in missing_errors]
        assert any("session_id" in field for field in missing_fields)
        assert any("surface_id" in field for field in missing_fields)

    def test_min_length_violation_returns_400(self, test_client):
        """Test that utterance below minimum length returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "A",
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_min_length_error_structure(self, test_client):
        """Test that min_length violation error includes proper structure."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "A",
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "detail" in error_data
        assert "error" in error_data
        assert "errors" in error_data

        # Verify error detail contains field validation information
        assert error_data["error"] == "Validation failed"
        errors = error_data["errors"]
        assert isinstance(errors, list)

        # Find utterance-related error
        utterance_errors = [e for e in errors if "utterance" in e.get("field", "")]
        assert len(utterance_errors) > 0

        # Verify error structure
        utterance_error = utterance_errors[0]
        assert "field" in utterance_error
        assert "message" in utterance_error
        assert "type" in utterance_error
        assert "utterance" in utterance_error["field"]

    def test_min_length_error_message_includes_details(self, test_client):
        """Test that min_length violation error message includes constraint details."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "A",
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "errors" in error_data

        # Find utterance error
        errors = error_data["errors"]
        utterance_errors = [e for e in errors if "utterance" in e.get("field", "")]
        assert len(utterance_errors) > 0

        # Verify error message includes min-length information
        utterance_error = utterance_errors[0]
        error_msg = utterance_error.get("message", "")
        assert len(error_msg) > 0
        # Error message should mention length constraint - Pydantic includes "at least X characters"
        assert "characters" in error_msg.lower() or "length" in error_msg.lower()
        # Should mention the minimum requirement (2 characters)
        assert "2" in error_msg or "two" in error_msg.lower()

    def test_empty_string_min_length_violation_returns_400(self, test_client):
        """Test that empty string (below min_length) returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "",
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "errors" in error_data

        # Verify the error structure includes field information
        errors = error_data["errors"]
        utterance_errors = [e for e in errors if "utterance" in e.get("field", "")]
        assert len(utterance_errors) > 0

        # Verify error includes message
        utterance_error = utterance_errors[0]
        error_msg = utterance_error.get("message", "")
        assert len(error_msg) > 0


class TestInvalidFieldTypeValidation:
    """Test cases for invalid field type validation at HTTP endpoint level."""

    def test_non_string_utterance_returns_400(self, test_client):
        """Test that non-string utterance returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": 123,
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        # App's custom validation handler returns 400
        assert response.status_code == 400

    def test_non_string_utterance_error_structure(self, test_client):
        """Test that non-string utterance error includes proper validation structure."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": 123,
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        # App's custom validation response structure
        assert "detail" in error_data
        assert "error" in error_data
        assert "errors" in error_data
        assert error_data["error"] == "Validation failed"
        assert error_data["status"] == 400

        # Verify errors array structure
        errors = error_data["errors"]
        assert isinstance(errors, list)

        # Find utterance-related error
        utterance_errors = [e for e in errors if "utterance" in e.get("field", "")]
        assert len(utterance_errors) > 0

        # Verify error structure
        utterance_error = utterance_errors[0]
        assert "field" in utterance_error
        assert "message" in utterance_error
        assert "type" in utterance_error
        # Error type should indicate type validation failure
        assert utterance_error["type"] in ("string_type", "int_parsing")
        # Error message should mention string requirement
        assert "string" in utterance_error["message"].lower()

    def test_non_string_session_id_returns_400(self, test_client):
        """Test that non-string session_id returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": 123,
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_non_string_session_id_error_structure(self, test_client):
        """Test that non-string session_id error includes proper validation structure."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": 123,
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "detail" in error_data
        assert "error" in error_data
        assert "errors" in error_data
        assert error_data["error"] == "Validation failed"

        # Verify errors array structure
        errors = error_data["errors"]
        assert isinstance(errors, list)

        # Find session_id-related error
        session_errors = [e for e in errors if "session_id" in e.get("field", "")]
        assert len(session_errors) > 0

        # Verify error structure
        session_error = session_errors[0]
        assert "field" in session_error
        assert "message" in session_error
        assert "type" in session_error
        # Error type should indicate type validation failure
        assert session_error["type"] in ("string_type", "int_parsing")
        # Error message should mention string requirement
        assert "string" in session_error["message"].lower()

    def test_non_string_surface_id_returns_400(self, test_client):
        """Test that non-string surface_id returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-123",
                "surface_id": 123
            }
        )

        assert response.status_code == 400

    def test_non_string_surface_id_error_structure(self, test_client):
        """Test that non-string surface_id error includes proper validation structure."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-123",
                "surface_id": 123
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "detail" in error_data
        assert "error" in error_data
        assert "errors" in error_data
        assert error_data["error"] == "Validation failed"

        # Verify errors array structure
        errors = error_data["errors"]
        assert isinstance(errors, list)

        # Find surface_id-related error
        surface_errors = [e for e in errors if "surface_id" in e.get("field", "")]
        assert len(surface_errors) > 0

        # Verify error structure
        surface_error = surface_errors[0]
        assert "field" in surface_error
        assert "message" in surface_error
        assert "type" in surface_error
        # Error type should indicate type validation failure
        assert surface_error["type"] in ("string_type", "int_parsing")
        # Error message should mention string requirement
        assert "string" in surface_error["message"].lower()

    def test_non_string_optional_utterance_id_returns_400(self, test_client):
        """Test that non-string utterance_id returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-123",
                "surface_id": "surface-456",
                "utterance_id": 123
            }
        )

        assert response.status_code == 400

    def test_non_string_optional_utterance_id_error_structure(self, test_client):
        """Test that non-string utterance_id error includes proper validation structure."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-123",
                "surface_id": "surface-456",
                "utterance_id": 123
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "detail" in error_data
        assert "error" in error_data
        assert "errors" in error_data
        assert error_data["error"] == "Validation failed"

        # Verify errors array structure
        errors = error_data["errors"]
        assert isinstance(errors, list)

        # Find utterance_id-related error
        utterance_id_errors = [e for e in errors if "utterance_id" in e.get("field", "")]
        assert len(utterance_id_errors) > 0

        # Verify error structure
        utterance_id_error = utterance_id_errors[0]
        assert "field" in utterance_id_error
        assert "message" in utterance_id_error
        assert "type" in utterance_id_error
        # Error type should indicate type validation failure
        # utterance_id has custom validator, so it shows as value_error
        assert utterance_id_error["type"] in ("string_type", "int_parsing", "value_error")
        # Error message should mention string requirement
        assert "string" in utterance_id_error["message"].lower()

    def test_float_type_utterance_returns_400(self, test_client):
        """Test that float type for utterance returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": 123.45,
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_boolean_type_utterance_returns_400(self, test_client):
        """Test that boolean type for utterance returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": True,
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_list_type_utterance_returns_400(self, test_client):
        """Test that list type for utterance returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": ["array", "value"],
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_dict_type_utterance_returns_400(self, test_client):
        """Test that dict type for utterance returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": {"key": "value"},
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_null_type_session_id_returns_400(self, test_client):
        """Test that null type for session_id returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": None,
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_multiple_invalid_field_types_returns_400(self, test_client):
        """Test that multiple invalid field types are reported together."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": 123,
                "session_id": 456,
                "surface_id": 789
            }
        )

        assert response.status_code == 400

        error_data = response.json()
        assert "detail" in error_data
        assert "error" in error_data
        assert "errors" in error_data
        assert error_data["error"] == "Validation failed"

        # Verify errors array structure
        errors = error_data["errors"]
        assert isinstance(errors, list)

        # Should have multiple errors (one for each field)
        assert len(errors) >= 3

        # Verify that utterance, session_id, and surface_id all have errors
        fields_with_errors = set()
        for error in errors:
            field = error.get("field", "")
            if "utterance" in field:
                fields_with_errors.add("utterance")
            if "session_id" in field:
                fields_with_errors.add("session_id")
            if "surface_id" in field:
                fields_with_errors.add("surface_id")

        # All three required fields should have type validation errors
        assert "utterance" in fields_with_errors
        assert "session_id" in fields_with_errors
        assert "surface_id" in fields_with_errors

    def test_float_type_session_id_returns_400(self, test_client):
        """Test that float type for session_id returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": 123.45,
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400

    def test_boolean_type_surface_id_returns_400(self, test_client):
        """Test that boolean type for surface_id returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-123",
                "surface_id": False
            }
        )

        assert response.status_code == 400

    def test_list_type_optional_utterance_id_returns_400(self, test_client):
        """Test that list type for optional utterance_id returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-123",
                "surface_id": "surface-456",
                "utterance_id": ["list", "value"]
            }
        )

        assert response.status_code == 400

    def test_dict_type_session_id_returns_400(self, test_client):
        """Test that dict type for session_id returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": {"key": "value"},
                "surface_id": "surface-456"
            }
        )

        assert response.status_code == 400


class TestMalformedJSONBody:
    """Test cases for malformed JSON request body validation."""

    def test_malformed_json_missing_closing_brace(self, test_client):
        """Test that JSON with missing closing brace returns HTTP 400 status code."""
        malformed_json = '{"utterance": "Check CI status", "session_id": "session-123", "surface_id": "surface-456"'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        # App returns 400 with validation error for malformed JSON
        assert response.status_code == 400

        # Verify error response structure indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") == "Validation failed"
        assert "detail" in error_data
        assert error_data.get("status") == 400
        assert "errors" in error_data

        # Verify the error specifically mentions JSON decode
        errors = error_data.get("errors", [])
        assert len(errors) > 0
        json_error = errors[0]
        assert "JSON decode error" in json_error.get("message", "")
        assert json_error.get("type") == "json_invalid"

    def test_malformed_json_missing_opening_brace(self, test_client):
        """Test that JSON with missing opening brace returns HTTP 400 status code."""
        malformed_json = '"utterance": "Check CI status", "session_id": "session-123", "surface_id": "surface-456"}'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

        # If errors array is present, verify structure
        if "errors" in error_data:
            errors = error_data.get("errors", [])
            assert len(errors) > 0
            json_error = errors[0]
            assert "JSON decode error" in json_error.get("message", "") or "json" in json_error.get("message", "").lower()
            assert json_error.get("type") == "json_invalid"

    def test_malformed_json_unquoted_keys(self, test_client):
        """Test that JSON with unquoted keys returns HTTP 400 status code."""
        malformed_json = '{utterance: "Check CI status", session_id: "session-123", surface_id: "surface-456"}'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") == "Validation failed"
        assert "detail" in error_data
        assert "errors" in error_data

        # Verify the error specifically mentions JSON decode
        errors = error_data.get("errors", [])
        assert len(errors) > 0
        json_error = errors[0]
        assert "JSON decode error" in json_error.get("message", "")
        assert json_error.get("type") == "json_invalid"

    def test_malformed_json_trailing_comma(self, test_client):
        """Test that JSON with trailing comma returns HTTP 400 status code."""
        malformed_json = '{"utterance": "Check CI status", "session_id": "session-123", "surface_id": "surface-456",}'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response structure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

    def test_malformed_json_missing_quotes(self, test_client):
        """Test that JSON with missing quotes returns HTTP 400 status code."""
        malformed_json = '{"utterance": Check CI status, "session_id": "session-123", "surface_id": "surface-456"}'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") == "Validation failed"
        assert "detail" in error_data
        assert "errors" in error_data

        # Verify the error specifically mentions JSON decode
        errors = error_data.get("errors", [])
        assert len(errors) > 0
        json_error = errors[0]
        assert "JSON decode error" in json_error.get("message", "")
        assert json_error.get("type") == "json_invalid"

    def test_malformed_json_invalid_escape_sequence(self, test_client):
        """Test that JSON with invalid escape sequence returns HTTP 400 status code."""
        malformed_json = '{"utterance": "Check CI status\\x", "session_id": "session-123", "surface_id": "surface-456"}'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") == "Validation failed"
        assert "detail" in error_data
        assert "errors" in error_data

        # Verify the error specifically mentions JSON decode
        errors = error_data.get("errors", [])
        assert len(errors) > 0
        json_error = errors[0]
        assert "JSON decode error" in json_error.get("message", "")
        assert json_error.get("type") == "json_invalid"

    def test_malformed_json_error_message_indicates_parse_failure(self, test_client):
        """Test that malformed JSON error message indicates JSON parsing failure."""
        malformed_json = '{"utterance": "Check CI status", "session_id": "session-123"'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        error_data = response.json()

        # Verify error response structure
        assert error_data.get("error") == "Validation failed"
        assert "detail" in error_data
        assert "errors" in error_data

        # Verify the error specifically mentions JSON decode
        errors = error_data.get("errors", [])
        assert len(errors) > 0
        json_error = errors[0]
        error_msg = json_error.get("message", "")
        assert "JSON decode error" in error_msg or "json" in error_msg.lower()
        assert json_error.get("type") == "json_invalid"

    def test_malformed_json_with_missing_colon(self, test_client):
        """Test that JSON with missing colon returns HTTP 400 status code."""
        malformed_json = '{"utterance" "Check CI status", "session_id": "session-123", "surface_id": "surface-456"}'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response structure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

    def test_malformed_json_empty_body(self, test_client):
        """Test that empty request body returns HTTP 400 status code."""
        response = test_client.post(
            "/dispatch",
            content="",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response structure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

    def test_malformed_json_completely_invalid(self, test_client):
        """Test that completely invalid JSON returns HTTP 400 status code."""
        malformed_json = "not valid json at all"

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") == "Validation failed"
        assert "detail" in error_data
        assert "errors" in error_data

        # Verify the error specifically mentions JSON decode
        errors = error_data.get("errors", [])
        assert len(errors) > 0
        json_error = errors[0]
        assert "JSON decode error" in json_error.get("message", "")
        assert json_error.get("type") == "json_invalid"
        error_detail = error_data.get("detail", "")
        assert len(error_detail) > 0

    def test_malformed_json_includes_position_info(self, test_client):
        """Test that malformed JSON error includes position information in field path."""
        malformed_json = '{"utterance": "Check CI status", "session_id": "session-123"'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        error_data = response.json()
        # App's validation handler includes position info in the field path
        assert "errors" in error_data
        errors = error_data.get("errors", [])
        assert len(errors) > 0

        # Position information is included in the field path (e.g., "body -> 89")
        field_path = errors[0].get("field", "")
        assert "->" in field_path  # Indicates position information
        # Field path should contain numeric position
        assert any(c.isdigit() for c in field_path)

    def test_malformed_json_error_structure(self, test_client):
        """Test that malformed JSON error has consistent structure."""
        malformed_json = '{"utterance": "Check CI status", "session_id": "session-123"'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        error_data = response.json()
        # Verify all expected fields are present
        assert "error" in error_data
        assert "detail" in error_data
        assert "status" in error_data
        assert "errors" in error_data

        # Verify field values
        assert error_data["error"] == "Validation failed"
        assert error_data["status"] == 400
        assert len(error_data["detail"]) > 0
        assert isinstance(error_data["errors"], list)
        assert len(error_data["errors"]) > 0

        # Verify error structure
        json_error = error_data["errors"][0]
        assert "field" in json_error
        assert "message" in json_error
        assert "type" in json_error
        assert json_error["type"] == "json_invalid"

    def test_malformed_json_simple_missing_closing_brace(self, test_client):
        """Test that simple JSON with missing closing brace returns HTTP 400 status code.

        This tests the specific pattern: {"utterance": "test" (missing closing })
        Focuses on one specific JSON syntax error pattern with minimal fields.
        """
        malformed_json = '{"utterance": "test"'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        # Verify error status is returned
        assert response.status_code == 400

        # Verify error message indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") == "Validation failed"
        assert "detail" in error_data
        assert "errors" in error_data

        # Verify the error specifically mentions JSON decode
        errors = error_data.get("errors", [])
        assert len(errors) > 0
        json_error = errors[0]
        error_msg = json_error.get("message", "")
        assert "JSON decode error" in error_msg or "json" in error_msg.lower()
        assert json_error.get("type") == "json_invalid"

        # Verify error status is included
        assert error_data.get("status") == 400

    def test_malformed_json_unquoted_strings_simple(self, test_client):
        """Test that JSON with unquoted strings (keys and values) returns HTTP 400 status code.

        This tests the specific pattern: {utterance: "test"} (keys should be quoted).
        Focuses on one specific JSON syntax error pattern where keys are not quoted.
        """
        malformed_json = '{utterance: "test"}'

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        # Verify error status is returned
        assert response.status_code == 400

        # Verify error message indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") == "Validation failed"
        assert "detail" in error_data
        assert "errors" in error_data

        # Verify the error specifically mentions JSON decode
        errors = error_data.get("errors", [])
        assert len(errors) > 0
        json_error = errors[0]
        error_msg = json_error.get("message", "")
        assert "JSON decode error" in error_msg or "json" in error_msg.lower()
        assert json_error.get("type") == "json_invalid"

        # Verify error status is included
        assert error_data.get("status") == 400

    def test_malformed_json_random_text_special_chars(self, test_client):
        """Test that random text with special characters returns HTTP 400 status code."""
        malformed_json = "!@#$%^&*()_+{}[]|\\:;\"'<>?,./"

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

    def test_malformed_json_random_text_single_char(self, test_client):
        """Test that single character returns HTTP 400 status code."""
        malformed_json = "x"

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

    def test_malformed_json_random_text_newlines(self, test_client):
        """Test that random text with newlines returns HTTP 400 status code."""
        malformed_json = "random\ntext\nwith\nnewlines"

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

    def test_malformed_json_random_text_unicode_garbage(self, test_client):
        """Test that random Unicode garbage returns HTTP 400 status code."""
        malformed_json = "עברית العربية 日本语 ລາວ"

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

    def test_malformed_json_random_binary_like(self, test_client):
        """Test that binary-like random text returns HTTP 400 status code."""
        malformed_json = "\x00\x01\x02\x03\x04\x05"

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

    def test_malformed_json_random_text_mixed_content(self, test_client):
        """Test that mixed random text content returns HTTP 400 status code."""
        malformed_json = "hello { world } [ test ] ( 123 ) !@#"

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

    def test_malformed_json_completely_invalid_alphanumeric(self, test_client):
        """Test that completely invalid alphanumeric text returns HTTP 400 status code."""
        malformed_json = "abc123def456ghi789"

        response = test_client.post(
            "/dispatch",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

        # Verify error response indicates JSON parsing failure
        error_data = response.json()
        assert error_data.get("error") in ("Validation failed", "Invalid JSON")
        assert "detail" in error_data

        # If errors array is present, verify it mentions JSON decode
        if "errors" in error_data:
            errors = error_data.get("errors", [])
            assert len(errors) > 0
            json_error = errors[0]
            error_msg = json_error.get("message", "")
            # Should mention JSON decode or parsing error
            assert len(error_msg) > 0
            assert json_error.get("type") == "json_invalid"

    def test_malformed_json_error_message_clarity_consistent(self, test_client):
        """Test that all malformed JSON errors have consistent assertion patterns."""
        test_cases = [
            "not valid json at all",
            "random text here",
            "!@#$% garbage",
            "x",
            "abc123def456",
        ]

        for malformed_json in test_cases:
            response = test_client.post(
                "/dispatch",
                content=malformed_json,
                headers={"Content-Type": "application/json"}
            )

            # Consistent assertion pattern 1: status code
            assert response.status_code == 400, f"Failed for input: {malformed_json}"

            # Consistent assertion pattern 2: error response structure
            error_data = response.json()
            assert "error" in error_data, f"Missing 'error' field for input: {malformed_json}"
            assert "detail" in error_data, f"Missing 'detail' field for input: {malformed_json}"
            assert "status" in error_data, f"Missing 'status' field for input: {malformed_json}"

            # Consistent assertion pattern 3: error type validation
            assert error_data["status"] == 400, f"Wrong status code for input: {malformed_json}"
            assert error_data["error"] in ("Validation failed", "Invalid JSON"), f"Wrong error type for input: {malformed_json}"

            # Consistent assertion pattern 4: error message indicates JSON parsing failure
            error_detail = error_data.get("detail", "")
            assert len(error_detail) > 0, f"Empty error detail for input: {malformed_json}"

            # If errors array is present, verify JSON decode indication
            if "errors" in error_data:
                errors = error_data.get("errors", [])
                assert len(errors) > 0, f"Empty errors array for input: {malformed_json}"
                json_error = errors[0]
                error_msg = json_error.get("message", "")
                assert len(error_msg) > 0, f"Empty error message for input: {malformed_json}"
                assert json_error.get("type") == "json_invalid", f"Wrong error type for input: {malformed_json}"


class TestDispatchHappyPath:
    """Happy path tests: verify valid requests pass validation and reach the handler."""

    def test_minimal_valid_payload_passes_validation(self, test_client):
        """Test that minimal valid payload passes validation and returns non-422 status."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-123",
                "surface_id": "surface-456"
            }
        )

        # Happy path: request passes validation and reaches handler
        # Status code should NOT be a validation error (400/422)
        # Expected: 202 (accepted for processing), 500 (handler error), or other non-validation status
        assert response.status_code not in (400, 422), (
            f"Valid request was rejected with validation error: {response.status_code}"
        )

    def test_minimal_valid_payload_reaches_handler(self, test_client):
        """Test that minimal valid payload reaches the handler (validation passes)."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check deployment status",
                "session_id": "session-456",
                "surface_id": "surface-789"
            }
        )

        # If validation fails, status would be 400/422
        # Any other status (including 500 handler errors) means validation passed
        assert response.status_code not in (400, 422), (
            "Request should pass validation and reach handler"
        )

        # Verify response structure is valid JSON (not a validation error response)
        response_data = response.json()
        assert isinstance(response_data, dict), "Response should be a JSON object"

    def test_full_valid_payload_with_all_optional_fields(self, test_client):
        """Test that valid payload with all optional fields passes validation."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status for aide-de-camp",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "surface_id": "surface-abc123",
                "utterance_id": "660e8400-e29b-41d4-a716-446655440000"
            }
        )

        # Should pass validation (not return 400/422)
        assert response.status_code not in (400, 422), (
            f"Valid request with all optional fields was rejected: {response.status_code}"
        )

    def test_valid_utterance_with_unicode(self, test_client):
        """Test that valid utterance with Unicode characters passes validation."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check status 🚀 ✓",
                "session_id": "session-unicode",
                "surface_id": "surface-unicode"
            }
        )

        # Should pass validation
        assert response.status_code not in (400, 422), (
            "Valid Unicode request should pass validation"
        )

    def test_valid_utterance_exactly_min_length(self, test_client):
        """Test that utterance exactly at minimum length (2 chars) passes validation."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "AB",  # Exactly min_length
                "session_id": "session-min",
                "surface_id": "surface-min"
            }
        )

        # Should pass validation
        assert response.status_code not in (400, 422), (
            "Utterance at min_length should pass validation"
        )

    def test_valid_utterance_with_newlines(self, test_client):
        """Test that utterance with newlines passes validation."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI\nstatus\nnow",
                "session_id": "session-newlines",
                "surface_id": "surface-newlines"
            }
        )

        # Should pass validation (newlines are preserved)
        assert response.status_code not in (400, 422), (
            "Utterance with newlines should pass validation"
        )

    def test_valid_utterance_is_stripped_at_endpoint(self, test_client):
        """Test that utterance is stripped of leading/trailing whitespace at endpoint."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "  Check CI status  ",  # Has whitespace
                "session_id": "session-whitespace",
                "surface_id": "surface-whitespace"
            }
        )

        # Should pass validation (whitespace is stripped by validator)
        assert response.status_code not in (400, 422), (
            "Utterance with whitespace should pass validation after stripping"
        )

    def test_valid_session_id_is_stripped_at_endpoint(self, test_client):
        """Test that session_id is stripped of leading/trailing whitespace at endpoint."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check status",
                "session_id": "  session-whitespace  ",  # Has whitespace
                "surface_id": "surface-test"
            }
        )

        # Should pass validation (whitespace is stripped by validator)
        assert response.status_code not in (400, 422), (
            "Session ID with whitespace should pass validation after stripping"
        )

    def test_valid_surface_id_is_stripped_at_endpoint(self, test_client):
        """Test that surface_id is stripped of leading/trailing whitespace at endpoint."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check status",
                "session_id": "session-test",
                "surface_id": "  surface-whitespace  "  # Has whitespace
            }
        )

        # Should pass validation (whitespace is stripped by validator)
        assert response.status_code not in (400, 422), (
            "Surface ID with whitespace should pass validation after stripping"
        )

    def test_optional_utterance_id_omitted(self, test_client):
        """Test that omitting optional utterance_id still passes validation."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-no-opt",
                "surface_id": "surface-no-opt"
                # utterance_id omitted (optional field)
            }
        )

        # Should pass validation (utterance_id is optional)
        assert response.status_code not in (400, 422), (
            "Request without optional utterance_id should pass validation"
        )

    def test_multiple_valid_requests_all_pass(self, test_client):
        """Test that multiple valid requests all pass validation (batch verification)."""
        valid_requests = [
            # Minimal payload
            {
                "utterance": "Check status",
                "session_id": "session-1",
                "surface_id": "surface-1"
            },
            # With optional utterance_id
            {
                "utterance": "Check deployment",
                "session_id": "session-2",
                "surface_id": "surface-2",
                "utterance_id": "utterance-123"
            },
            # With Unicode
            {
                "utterance": "Status check 🎯",
                "session_id": "session-3",
                "surface_id": "surface-3"
            },
            # Longer utterance
            {
                "utterance": "Please check the continuous integration status for the aide-de-camp project",
                "session_id": "session-4",
                "surface_id": "surface-4"
            },
        ]

        for i, payload in enumerate(valid_requests):
            response = test_client.post("/dispatch", json=payload)

            # All valid requests should pass validation
            assert response.status_code not in (400, 422), (
                f"Valid request {i+1} failed validation: {response.status_code}"
            )

    def test_validation_does_not_return_422_for_valid_request(self, test_client):
        """Test that valid request does not return HTTP 422 Unprocessable Entity."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-422",
                "surface_id": "surface-422"
            }
        )

        # 422 is FastAPI's default validation error status
        # Valid requests should never return 422
        assert response.status_code != 422, (
            "Valid request should not return 422 Unprocessable Entity"
        )

    def test_validation_does_not_return_400_for_valid_request(self, test_client):
        """Test that valid request does not return HTTP 400 Bad Request."""
        response = test_client.post(
            "/dispatch",
            json={
                "utterance": "Check CI status",
                "session_id": "session-400",
                "surface_id": "surface-400"
            }
        )

        # 400 is the app's custom validation error status
        # Valid requests should never return 400
        assert response.status_code != 400, (
            "Valid request should not return 400 Bad Request"
        )
