"""
Test DispatchRequest model validation.

Comprehensive tests for Pydantic model validation including:
- Valid request creation
- Missing required fields
- Empty string validation
- Validator error messages
"""
import pytest
from pydantic import ValidationError

from src.api.models import DispatchRequest


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
        assert 'utterance must be a non-empty string' in error_msg
        assert len(error_msg) > 0  # Not empty
        assert 'string' in error_msg.lower()  # Mentions type
        assert 'empty' in error_msg.lower()  # Mentions requirement

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

        assert request.utterance == long_utterance

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
