"""Tests for confirmation response validation (adc-2os76)."""

import pytest
from src.confirmations import validate_confirmation_response, get_confirmation_for_validation
from src.confirmations.prompts import ConfirmationPromptError


class TestConfirmationValidation:
    """Test suite for validating user confirmation responses."""

    @pytest.mark.asyncio
    async def test_validate_yes_response_lowercase(self, confirmation_with_pod):
        """Test that lowercase 'yes' is validated correctly."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="yes"
        )

        assert result["valid"] is True
        assert result["response_type"] == "yes"
        assert result["normalized_response"] == "yes"
        assert result["error_message"] is None
        assert result["confirmation_id"] == confirmation_with_pod

    @pytest.mark.asyncio
    async def test_validate_yes_response_uppercase(self, confirmation_with_pod):
        """Test that uppercase 'YES' is validated correctly."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="YES"
        )

        assert result["valid"] is True
        assert result["response_type"] == "yes"
        assert result["normalized_response"] == "yes"
        assert result["error_message"] is None

    @pytest.mark.asyncio
    async def test_validate_yes_response_mixed_case(self, confirmation_with_pod):
        """Test that mixed case 'YeS' is validated correctly."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="YeS"
        )

        assert result["valid"] is True
        assert result["response_type"] == "yes"
        assert result["normalized_response"] == "yes"
        assert result["error_message"] is None

    @pytest.mark.asyncio
    async def test_validate_yes_response_with_whitespace(self, confirmation_with_pod):
        """Test that '  yes  ' with whitespace is validated correctly."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="  yes  "
        )

        assert result["valid"] is True
        assert result["response_type"] == "yes"
        assert result["normalized_response"] == "yes"
        assert result["error_message"] is None

    @pytest.mark.asyncio
    async def test_validate_no_response_lowercase(self, confirmation_with_pod):
        """Test that lowercase 'no' is validated correctly."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="no"
        )

        assert result["valid"] is True
        assert result["response_type"] == "no"
        assert result["normalized_response"] == "no"
        assert result["error_message"] is None

    @pytest.mark.asyncio
    async def test_validate_no_response_uppercase(self, confirmation_with_pod):
        """Test that uppercase 'NO' is validated correctly."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="NO"
        )

        assert result["valid"] is True
        assert result["response_type"] == "no"
        assert result["normalized_response"] == "no"
        assert result["error_message"] is None

    @pytest.mark.asyncio
    async def test_validate_exact_pod_name(self, confirmation_with_pod):
        """Test that exact pod name match is validated correctly (case-sensitive)."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="test-pod-abc123"
        )

        assert result["valid"] is True
        assert result["response_type"] == "pod_name"
        assert result["normalized_response"] == "test-pod-abc123"
        assert result["error_message"] is None

    @pytest.mark.asyncio
    async def test_validate_pod_name_case_sensitive(self, confirmation_with_pod):
        """Test that pod name match is case-sensitive."""
        # Should fail with different case
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="Test-Pod-Abc123"
        )

        assert result["valid"] is False
        assert result["response_type"] is None
        assert result["normalized_response"] is None
        assert result["error_message"] is not None
        assert "Invalid response" in result["error_message"]
        assert "Test-Pod-Abc123" in result["error_message"]

    @pytest.mark.asyncio
    async def test_validate_empty_response(self, confirmation_with_pod):
        """Test that empty response is rejected with clear error."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response=""
        )

        assert result["valid"] is False
        assert result["response_type"] is None
        assert result["normalized_response"] is None
        assert result["error_message"] is not None
        assert "Empty response" in result["error_message"]
        assert "Please respond with" in result["error_message"]

    @pytest.mark.asyncio
    async def test_validate_whitespace_only_response(self, confirmation_with_pod):
        """Test that whitespace-only response is rejected."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="   "
        )

        assert result["valid"] is False
        assert result["response_type"] is None
        assert result["normalized_response"] is None
        assert result["error_message"] is not None
        assert "Empty response" in result["error_message"]

    @pytest.mark.asyncio
    async def test_validate_invalid_response_maybe(self, confirmation_with_pod):
        """Test that 'maybe' is rejected with clear error."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="maybe"
        )

        assert result["valid"] is False
        assert result["response_type"] is None
        assert result["normalized_response"] is None
        assert result["error_message"] is not None
        assert "Invalid response: 'maybe'" in result["error_message"]
        assert "Please respond with" in result["error_message"]
        assert "test-pod-abc123" in result["error_message"]

    @pytest.mark.asyncio
    async def test_validate_invalid_response_probably(self, confirmation_with_pod):
        """Test that 'probably' is rejected with clear error."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="probably"
        )

        assert result["valid"] is False
        assert result["response_type"] is None
        assert result["normalized_response"] is None
        assert result["error_message"] is not None
        assert "Invalid response: 'probably'" in result["error_message"]

    @pytest.mark.asyncio
    async def test_validate_invalid_response_wrong_pod_name(self, confirmation_with_pod):
        """Test that wrong pod name is rejected."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="wrong-pod-name"
        )

        assert result["valid"] is False
        assert result["response_type"] is None
        assert result["normalized_response"] is None
        assert result["error_message"] is not None
        assert "Invalid response: 'wrong-pod-name'" in result["error_message"]
        assert "test-pod-abc123" in result["error_message"]

    @pytest.mark.asyncio
    async def test_validate_invalid_response_yesno_combined(self, confirmation_with_pod):
        """Test that 'yesno' is rejected (not a valid format)."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_with_pod,
            response="yesno"
        )

        assert result["valid"] is False
        assert result["response_type"] is None
        assert result["normalized_response"] is None
        assert result["error_message"] is not None
        assert "Invalid response: 'yesno'" in result["error_message"]

    @pytest.mark.asyncio
    async def test_validate_nonexistent_confirmation(self, confirmation_id_nonexistent):
        """Test that validation fails for non-existent confirmation."""
        with pytest.raises(ConfirmationPromptError) as exc_info:
            await validate_confirmation_response(
                confirmation_id=confirmation_id_nonexistent,
                response="yes"
            )

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_without_pod_name(self, confirmation_without_pod):
        """Test validation when confirmation has no pod name context."""
        result = await validate_confirmation_response(
            confirmation_id=confirmation_without_pod,
            response="yes"
        )

        assert result["valid"] is True
        assert result["response_type"] == "yes"
        assert result["normalized_response"] == "yes"
        assert result["error_message"] is None

        # Test invalid response when no pod name is available
        invalid_result = await validate_confirmation_response(
            confirmation_id=confirmation_without_pod,
            response="invalid"
        )

        assert invalid_result["valid"] is False
        assert invalid_result["error_message"] is not None
        # Should not mention pod name in error message
        assert "pod name" not in invalid_result["error_message"].lower()


# Pytest fixtures for setting up test data

@pytest.fixture
async def confirmation_with_pod(session_store):
    """Create a confirmation prompt with pod name context for testing."""
    from src.confirmations import create_pod_deletion_confirmation

    # Create a session for the confirmation
    session_id = await session_store.create_session()

    # Create confirmation with pod name
    confirmation = await create_pod_deletion_confirmation(
        intent_id="test-intent-1",
        session_id=session_id,
        pod_name="test-pod-abc123",
        namespace="default",
        cluster="test-cluster"
    )

    return confirmation["confirmation_id"]


@pytest.fixture
async def confirmation_without_pod(session_store):
    """Create a confirmation prompt without pod name for testing."""
    from src.confirmations.prompts import ConfirmationPromptManager

    manager = ConfirmationPromptManager()

    # Create a session for the confirmation
    session_id = await session_store.create_session()

    # Create confirmation directly without pod context
    confirmation_id = await session_store.create_confirmation_prompt(
        intent_id="test-intent-2",
        session_id=session_id,
        prompt_type="test_confirmation",
        question="Do you want to proceed?",
        context={}
    )

    return confirmation_id


@pytest.fixture
def confirmation_id_nonexistent():
    """Provide a non-existent confirmation ID for testing error handling."""
    return "nonexistent-confirmation-id"


@pytest.fixture
async def session_store():
    """Provide a session store instance for testing."""
    from src.session.store import get_store

    store = get_store()
    yield store

    # Cleanup: delete test sessions if needed
    # (This is optional and depends on your test cleanup strategy)
