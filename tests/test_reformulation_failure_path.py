"""
Tests for re-formulation failure path in escalate handler.

Tests the complete flow:
1. Validation failure → re-formulation attempt (exactly once)
2. Re-formulation includes specific failure reason
3. Failed re-formulation → clarification card
4. Re-formulation count tracking prevents infinite loops
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.escalate.handler import EscalateHandler, EscalateRequest
from src.bead_validation import get_validator, ValidationResult, ValidationRetryExhaustedError
from src.bead_validation.models import Violation, Severity


@pytest.fixture
def escalate_handler():
    """Create an escalate handler for testing."""
    return EscalateHandler()


@pytest.fixture
def sample_request():
    """Create a sample escalate request."""
    return EscalateRequest(
        intent_id="test-intent-123",
        session_id="test-session-456",
        utterance="Create a Kubernetes pod",
        intent_type="task-profile",
        project_slug="test-project",
    )


@pytest.mark.asyncio
async def test_reformulation_failure_path_tracks_count(escalate_handler, sample_request):
    """Test that re-formulation count is tracked per session."""
    store_mock = AsyncMock()
    store_mock.get_reformulation_count.return_value = 0
    store_mock.increment_reformulation_count.return_value = 1

    escalate_handler.store = store_mock

    # Mock the validator to return invalid result
    with patch('src.escalate.handler.get_validator') as mock_validator_get:
        mock_validator = MagicMock()
        mock_validator.validate_bead_body.return_value = ValidationResult.invalid(
            violations=[
                Violation(
                    rule_id="kubectl-deny-list",
                    severity=Severity.ERROR,
                    message="Bead contains forbidden kubectl command: kubectl delete",
                    line_number=5,
                    context="kubectl delete pod my-pod"
                )
            ],
            reformulation_hint="Replace kubectl commands with GitOps declarative-config edits"
        )
        mock_validator_get.return_value = mock_validator

        # Mock LLM client to fail re-formulation
        with patch.object(escalate_handler, '_get_zai_client') as mock_client:
            mock_client.return_value.call_simple.side_effect = Exception("LLM failed")

            # Execute and expect ValidationRetryExhaustedError
            with pytest.raises(ValidationRetryExhaustedError) as exc_info:
                await escalate_handler._validate_and_prepare_approval(
                    request=sample_request,
                    bead_body="## Task\nkubectl delete pod my-pod",
                    bead_type="task"
                )

            # Verify the error contains violations
            assert exc_info.value.original_violations
            assert len(exc_info.value.original_violations) == 1
            assert "kubectl delete" in exc_info.value.original_violations[0].message


@pytest.mark.asyncio
async def test_reformulation_prevents_infinite_loops(escalate_handler, sample_request):
    """Test that re-formulation is limited to prevent infinite loops."""
    store_mock = AsyncMock()
    # Simulate session that already exceeded max attempts
    store_mock.get_reformulation_count.return_value = 3
    store_mock.increment_reformulation_count.return_value = 4

    escalate_handler.store = store_mock

    # Mock validator to return invalid result
    with patch('src.escalate.handler.get_validator') as mock_validator_get:
        mock_validator = MagicMock()
        mock_validator.validate_bead_body.return_value = ValidationResult.invalid(
            violations=[
                Violation(
                    rule_id="kubectl-deny-list",
                    severity=Severity.ERROR,
                    message="Bead contains forbidden kubectl command"
                )
            ]
        )
        mock_validator_get.return_value = mock_validator

        # Should immediately fail without attempting re-formulation
        with pytest.raises(ValidationRetryExhaustedError) as exc_info:
            await escalate_handler._validate_and_prepare_approval(
                request=sample_request,
                bead_body="kubectl delete pod my-pod",
                bead_type="task"
            )

        # Verify error message mentions attempt limit
        assert "3 attempts per session" in str(exc_info.value)
        # Verify increment was NOT called (already at limit)
        store_mock.increment_reformulation_count.assert_not_called()


@pytest.mark.asyncio
async def test_reformulation_includes_failure_reason(escalate_handler, sample_request):
    """Test that re-formulation prompt includes specific failure reason."""
    store_mock = AsyncMock()
    store_mock.get_reformulation_count.return_value = 0
    store_mock.increment_reformulation_count.return_value = 1
    store_mock.reset_reformulation_count.return_value = None

    escalate_handler.store = store_mock

    # Mock validator to return invalid result initially
    with patch('src.escalate.handler.get_validator') as mock_validator_get:
        mock_validator = MagicMock()

        # First call: invalid
        invalid_result = ValidationResult.invalid(
            violations=[
                Violation(
                    rule_id="missing-scope",
                    severity=Severity.ERROR,
                    message="Bead must specify cluster and namespace",
                    line_number=3,
                    context="Deploy the application"
                )
            ],
            reformulation_hint="Add cluster=ardenone-cluster and namespace=production"
        )

        # Second call: valid after re-formulation
        valid_result = ValidationResult.valid(
            bead_type="task"
        )

        mock_validator.validate_bead_body.side_effect = [invalid_result, valid_result]
        mock_validator_get.return_value = mock_validator

        # Mock LLM client to return reformulated body
        with patch.object(escalate_handler, '_get_zai_client') as mock_client:
            reformulated_body = "## Task\nDeploy the application to cluster=ardenone-cluster namespace=production"
            mock_client.return_value.call_simple.return_value = reformulated_body

            result, returned_body = await escalate_handler._validate_and_prepare_approval(
                request=sample_request,
                bead_body="Deploy the application",
                bead_type="task"
            )

            # Verify re-formulation succeeded
            assert result.is_valid
            assert returned_body == reformulated_body

            # Verify LLM was called with failure reason in prompt
            call_args = mock_client.return_value.call_simple.call_args
            user_message = call_args[1]['user_message']
            assert "must specify cluster and namespace" in user_message
            assert "cluster=ardenone-cluster and namespace=production" in user_message


@pytest.mark.asyncio
async def test_reset_reformulation_count_on_success(escalate_handler, sample_request):
    """Test that re-formulation count is reset on successful bead creation."""
    store_mock = AsyncMock()
    store_mock.get_reformulation_count.return_value = 1
    store_mock.increment_reformulation_count.return_value = 2
    store_mock.reset_reformulation_count.return_value = None
    store_mock.update_intent_status.return_value = None
    store_mock.create_bead_watch.return_value = None

    escalate_handler.store = store_mock

    # Mock all dependencies
    with patch('src.escalate.handler.get_validator') as mock_validator_get:
        mock_validator = MagicMock()
        mock_validator.validate_bead_body.return_value = ValidationResult.valid(
            bead_type="task"
        )
        mock_validator_get.return_value = mock_validator

        with patch('src.escalate.handler.get_reload_manager'):
            with patch.object(escalate_handler, '_get_zai_client') as mock_client:
                mock_client.return_value.call_simple.return_value = "## Valid bead body"

                with patch.object(escalate_handler, '_create_bead_with_type') as mock_create:
                    mock_create.return_value = "abc-123"

                    result = await escalate_handler.escalate_intent(sample_request)

                    # Verify reset was called
                    store_mock.reset_reformulation_count.assert_called_once_with(sample_request.session_id)


@pytest.mark.asyncio
async def test_clarification_card_on_exhausted_retries(escalate_handler, sample_request):
    """Test that clarification card is returned when re-formulation is exhausted."""
    store_mock = AsyncMock()
    store_mock.get_reformulation_count.return_value = 1
    store_mock.increment_reformulation_count.return_value = 2
    store_mock.update_intent_status.return_value = None

    escalate_handler.store = store_mock

    # Mock validator to always fail validation
    with patch('src.escalate.handler.get_validator') as mock_validator_get:
        mock_validator = MagicMock()

        # Both original and reformulated fail validation
        invalid_result = ValidationResult.invalid(
            violations=[
                Violation(
                    rule_id="kubectl-deny-list",
                    severity=Severity.ERROR,
                    message="Bead contains forbidden kubectl command"
                )
            ]
        )

        mock_validator.validate_bead_body.return_value = invalid_result
        mock_validator_get.return_value = mock_validator

        with patch('src.escalate.handler.get_reload_manager'):
            with patch.object(escalate_handler, '_get_zai_client') as mock_client:
                # Re-formulation succeeds but still fails validation
                mock_client.return_value.call_simple.return_value = "kubectl delete pod my-pod"

                result = await escalate_handler.escalate_intent(sample_request)

                # Verify clarification card is returned
                assert result.status == "needs_clarification"
                assert result.pending_card["type"] == "clarification"
                assert result.bead_id == ""  # No bead created

                # Verify violations are in the card
                assert "violations" in result.pending_card
                assert len(result.pending_card["violations"]) == 1


@pytest.mark.asyncio
async def test_clarification_card_broadcasts_sse_event(escalate_handler, sample_request):
    """Test that clarification card triggers SSE broadcast."""
    store_mock = AsyncMock()
    store_mock.get_reformulation_count.return_value = 0
    store_mock.increment_reformulation_count.return_value = 1
    store_mock.update_intent_status.return_value = None

    escalate_handler.store = store_mock

    # Mock broadcaster
    with patch('src.escalate.handler.get_broadcaster') as mock_broadcaster_get:
        mock_broadcaster = AsyncMock()
        mock_broadcaster_get.return_value = mock_broadcaster

        with patch('src.escalate.handler.get_validator') as mock_validator_get:
            mock_validator = MagicMock()

            # Both original and reformulated fail validation
            invalid_result = ValidationResult.invalid(
                violations=[
                    Violation(
                        rule_id="kubectl-deny-list",
                        severity=Severity.ERROR,
                        message="Bead contains forbidden kubectl command"
                    )
                ]
            )

            mock_validator.validate_bead_body.return_value = invalid_result
            mock_validator_get.return_value = mock_validator

            with patch('src.escalate.handler.get_reload_manager'):
                with patch.object(escalate_handler, '_get_zai_client') as mock_client:
                    mock_client.return_value.call_simple.return_value = "kubectl delete pod my-pod"

                    await escalate_handler.escalate_intent(sample_request)

                    # Verify SSE broadcast was called
                    mock_broadcaster.broadcast.assert_called_once()
                    call_args = mock_broadcaster.broadcast.call_args[0][0]

                    # Verify event type is clarification_card
                    assert call_args.event_type == "clarification_card"

                    # Verify data includes clarification_card
                    assert "clarification_card" in call_args.data
                    assert "violations" in call_args.data
