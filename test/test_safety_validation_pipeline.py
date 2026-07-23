#!/usr/bin/env python3
"""
Comprehensive test suite for safety validation pipeline.

Tests the complete pipeline: validation → (re-formulation) → approval → creation.
Verifies the integration between escalate handler and bead validation.

Acceptance criteria:
- Historical 'kubectl delete pod' unscoped body rejected (validation fails)
- GitOps-phrased scoped mutation passes validation but requires approval
- Informational bead passes without approval
- Re-formulation happens exactly once on validation failure
- Clarification card generated after failed re-formulation
- All tests pass with pytest
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Ensure the project root is in the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from src.bead_validation.validator import BeadValidator, get_validator
from src.bead_validation.models import (
    BeadType,
    ValidationResult,
    Severity,
    Violation,
)
from src.bead_validation.exceptions import ValidationRetryExhaustedError
from src.escalate.handler import (
    EscalateHandler,
    EscalateRequest,
    BeadApprovalRequired,
)
from src.session.store import SessionStore


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def validator():
    """Get a fresh validator instance."""
    return get_validator()


@pytest.fixture
async def session_store(tmp_path):
    """Create a temporary session store for testing."""
    db_path = tmp_path / "test_session.db"
    store = SessionStore(db_path)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def escalate_handler(session_store):
    """Create an escalate handler with test session store."""
    handler = EscalateHandler(store=session_store)
    return handler


@pytest.fixture
def sample_request():
    """Create a sample escalate request."""
    return EscalateRequest(
        intent_id="test-intent-123",
        session_id="test-session-456",
        utterance="Delete the pod named web-app-123 in production namespace",
        intent_type="action",
        project_slug="ardenone-cluster",
        topic_id="test-topic-789",
    )


# =============================================================================
# Test 1: Historical 'kubectl delete pod' rejection
# =============================================================================

def test_historical_kubectl_delete_rejected_integration(validator, sample_request):
    """
    Integration test: Historical 'kubectl delete pod' unscoped body is rejected.

    This test verifies that when the escalate handler generates a bead body
    with the historical unscoped kubectl delete pattern, validation fails.
    """
    # Simulate the historical bead body that would be generated
    historical_body = """# Task: Delete Pod

Delete the pod using kubectl.

## Steps
1. kubectl delete pod <pod_name>

No namespace or cluster specified - this is the bug.
"""

    # Validation should fail
    result = validator.validate_bead_body(historical_body, bead_type="action")

    # Verify rejection
    assert result.is_valid is False, "Historical kubectl delete should be rejected"
    assert result.requires_approval is False, "Invalid beads don't require approval"
    assert len(result.violations) > 0, "Should have violations"

    # Verify specific violations
    violation_rule_ids = [v.rule_id for v in result.violations]
    assert "no_direct_kubectl_mutation" in violation_rule_ids, "Should forbid direct kubectl"

    # Verify reformulation hint is provided
    assert result.reformulation_hint is not None, "Should provide reformulation hint"


# =============================================================================
# Test 2: GitOps-phrased scoped mutation passes with approval
# =============================================================================

def test_gitops_scoped_mutation_passes_with_approval(validator):
    """
    Test: GitOps-phrased scoped mutation passes validation but requires approval.

    A properly scoped mutation that uses GitOps approach should pass validation
    but still require approval for action-type beads.
    """
    gitops_body = """# Task: Restart Pod on Production

## Overview
Restart the pod in the production namespace using GitOps workflow.

## Scope
- Cluster: ardenone-cluster
- Namespace: production
- Deployment: web-app

## Steps
1. Edit the manifest in jedarden/declarative-config/k8s/ardenone-cluster/production/web-app.yaml
2. Add or modify an annotation to trigger rollout
3. Commit the change: git commit -m 'Trigger rollout for web-app'
4. Push to main branch
5. ArgoCD will sync automatically

## Success Criteria
- ArgoCD reports Synced and Healthy
- New pod is Running
"""

    result = validator.validate_bead_body(gitops_body, bead_type="action")

    # Should pass safety validation
    assert result.is_valid is True, "GitOps-phrased mutation should be valid"

    # But requires approval for action beads
    assert result.requires_approval is True, "Action beads require approval"
    assert result.approval_requirement is not None
    assert result.approval_requirement.bead_type == BeadType.ACTION

    # Should have no ERROR-level violations
    error_violations = [v for v in result.violations if v.severity == Severity.ERROR]
    assert len(error_violations) == 0, "Should have no ERROR violations"


# =============================================================================
# Test 3: Informational bead passes without approval
# =============================================================================

def test_informational_bead_passes_without_approval(validator):
    """
    Test: Informational bead passes without approval.

    Purely informational beads (research, lookups) should pass validation
    without requiring approval.
    """
    informational_body = """# Research Task: Investigate Pod Restart Patterns

## Overview
Look up and analyze the last month of pod restart patterns for the web application.

## Scope
- Cluster: ardenone-cluster
- Namespace: production
- Time range: Last 30 days

## Steps
1. Check pod logs from kubectl
2. Look at crash loop back off events
3. Analyze restart patterns
4. Summarize findings

## Success Criteria
- Report includes restart frequency
- Report identifies common failure patterns
- Recommendations provided
"""

    result = validator.validate_bead_body(informational_body, bead_type="task")

    # Should pass validation
    assert result.is_valid is True, "Informational bead should be valid"

    # Should NOT require approval
    assert result.requires_approval is False, "Informational beads should not require approval"

    # Should have no violations
    assert len(result.violations) == 0, "Should have no violations"


# =============================================================================
# Test 4: Re-formulation happens exactly once on validation failure
# =============================================================================

@pytest.mark.asyncio
async def test_reformulation_happens_exactly_once(escalate_handler, session_store, sample_request):
    """
    Test: Re-formulation happens exactly once on validation failure.

    When a bead body fails validation, the system should attempt exactly
    one re-formulation before giving up.
    """
    # Create a session for testing
    session_id = await session_store.create_session()
    sample_request.session_id = session_id

    # Mock the formulate_bead_body to return invalid body first, then valid one
    invalid_body = """# Task: Delete Pod
kubectl delete pod xyz
No scoping here.
"""

    valid_body = """# Task: Delete Pod Using GitOps

## Scope
- Cluster: ardenone-cluster
- Namespace: production
- Pod: xyz

## Steps
1. Edit jedarden/declarative-config/k8s/ardenone-cluster/production/pod.yaml
2. Remove the pod from the manifest
3. Commit and push
4. ArgoCD will sync
"""

    call_count = 0

    async def mock_call_simple(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return invalid_body
        else:
            return valid_body

    # Mock the LLM client's call_simple method
    with patch.object(escalate_handler, '_get_zai_client') as mock_get_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.call_simple = mock_call_simple
        mock_get_client.return_value = mock_client_instance

        # Mock create_bead_with_type to avoid actual bead creation
        with patch.object(escalate_handler, '_create_bead_with_type', return_value="test-bead-123"):
            with patch.object(escalate_handler, '_create_bead_watch'):
                with patch('src.escalate.handler.get_reload_manager') as mock_reload_mgr:
                    # Mock reload manager to return exceptions config
                    mock_reload = MagicMock()
                    mock_reload.get_config.return_value = {"escalation_targets": {"action": {"bead_type": "action"}}}
                    mock_reload_mgr.return_value = mock_reload

                    try:
                        result = await escalate_handler.escalate_intent(sample_request)

                        # If we get here, reformulation should have happened exactly once
                        assert call_count == 2, f"Expected 2 LLM calls (original + 1 reformulation), got {call_count}"

                    except BeadApprovalRequired as e:
                        # This is also acceptable - re-formulation resulted in approval-required bead
                        assert call_count == 2, f"Expected 2 LLM calls (original + 1 reformulation), got {call_count}"


@pytest.mark.asyncio
async def test_reformulation_count_increments_and_resets(session_store, escalate_handler, sample_request):
    """
    Test: Re-formulation count increments and resets properly.

    The session store should track reformulation attempts and reset the counter
    after successful bead creation.
    """
    # Create a session
    session_id = await session_store.create_session()
    sample_request.session_id = session_id

    # Initial count should be 0
    initial_count = await session_store.get_reformulation_count(session_id)
    assert initial_count == 0, "Initial reformulation count should be 0"

    # Increment count
    new_count = await session_store.increment_reformulation_count(session_id)
    assert new_count == 1, "Count should increment to 1"

    # Verify increment
    check_count = await session_store.get_reformulation_count(session_id)
    assert check_count == 1, "Count should be 1 after increment"

    # Reset count
    await session_store.reset_reformulation_count(session_id)

    # Verify reset
    reset_count = await session_store.get_reformulation_count(session_id)
    assert reset_count == 0, "Count should be 0 after reset"


@pytest.mark.asyncio
async def test_reformulation_limit_enforced(session_store, escalate_handler, sample_request):
    """
    Test: Re-formulation limit is enforced (MAX_REFORMULATION_ATTEMPTS = 3).

    After 3 failed re-formulation attempts, the system should give up and
    return a clarification card instead of raising an exception.
    """
    # Create a session and set reformulation count to limit
    session_id = await session_store.create_session()
    sample_request.session_id = session_id

    # Set count to MAX (3)
    for _ in range(3):
        await session_store.increment_reformulation_count(session_id)

    # Verify count is at limit
    count = await session_store.get_reformulation_count(session_id)
    assert count == 3, "Count should be at limit"

    # Mock formulate to return invalid body
    invalid_body = """# Task: Delete Pod
kubectl delete pod xyz
"""

    async def mock_call_simple(**kwargs):
        return invalid_body

    # Mock the LLM client's call_simple method
    with patch.object(escalate_handler, '_get_zai_client') as mock_get_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.call_simple = mock_call_simple
        mock_get_client.return_value = mock_client_instance

        with patch('src.escalate.handler.get_reload_manager') as mock_reload_mgr:
            # Mock reload manager to return exceptions config
            mock_reload = MagicMock()
            mock_reload.get_config.return_value = {"escalation_targets": {"action": {"bead_type": "action"}}}
            mock_reload_mgr.return_value = mock_reload

            # Mock broadcaster to avoid actual SSE broadcasting
            with patch('src.escalate.handler.get_broadcaster') as mock_broadcaster:
                mock_bc = MagicMock()
                mock_bc.broadcast = AsyncMock()
                mock_broadcaster.return_value = mock_bc

                # Should return a result with clarification card (not raise exception)
                result = await escalate_handler.escalate_intent(sample_request)

                # Verify the result status indicates clarification is needed
                assert result.status == "needs_clarification"
                assert result.pending_card is not None
                assert result.pending_card.get("type") == "clarification"
                assert len(result.pending_card.get("violations", [])) > 0


# =============================================================================
# Test 5: Clarification card generated after failed re-formulation
# =============================================================================

def test_clarification_card_generation(escalate_handler):
    """
    Test: Clarification card is generated after failed re-formulation.

    When re-formulation fails, the handler should build a clarification card
    with violations and original utterance.
    """
    request = EscalateRequest(
        intent_id="test-intent-123",
        session_id="test-session-456",
        utterance="Delete the pod",
        intent_type="action",
        project_slug="ardenone-cluster",
    )

    # Create sample violations as Violation objects (not dicts)
    violations = [
        Violation(
            rule_id="no_direct_kubectl_mutation",
            severity=Severity.ERROR,
            message="Direct kubectl 'delete' command detected",
            line_number=3,
            context="kubectl delete pod xyz",
        ),
        Violation(
            rule_id="scoping_required",
            severity=Severity.ERROR,
            message="Command lacks proper scoping",
        ),
    ]

    # Build clarification card
    card = escalate_handler.build_clarification_card(
        request=request,
        original_bead_body="kubectl delete pod xyz",
        violations=violations,
    )

    # Verify card structure
    assert card["type"] == "clarification"
    assert card["status"] == "needs_clarification"
    assert card["intent_id"] == request.intent_id
    assert card["original_utterance"] == request.utterance
    assert len(card["violations"]) == 2

    # Verify violation messages are formatted with "- " prefix
    violation_messages = card["violations"]
    assert any(violation_messages[i] == "- " + violations[i].message for i in range(len(violations)))

    # Check specific messages
    assert any("delete" in msg.lower() for msg in violation_messages)
    assert any("scoping" in msg.lower() for msg in violation_messages)


# =============================================================================
# Test 6: Complete pipeline integration
# =============================================================================

@pytest.mark.asyncio
async def test_complete_validation_to_approval_pipeline(escalate_handler, sample_request):
    """
    Test: Complete pipeline from validation to approval.

    This test simulates the full flow:
    1. Formulate initial bead body (passes validation but requires approval)
    2. Validation passes but requires approval
    3. BeadApprovalRequired exception is caught and converted to result
    4. Approval card built and stored
    """
    # Mock formulate to return GitOps-phrased body (requires approval)
    gitops_body = """# Task: Update Deployment

## Scope
- Cluster: ardenone-cluster
- Namespace: production

## Steps
1. Edit jedarden/declarative-config/k8s/ardenone-cluster/production/deployment.yaml
2. Commit and push
"""

    async def mock_call_simple(**kwargs):
        return gitops_body

    # Mock the LLM client's call_simple method
    with patch.object(escalate_handler, '_get_zai_client') as mock_get_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.call_simple = mock_call_simple
        mock_get_client.return_value = mock_client_instance

        with patch('src.escalate.handler.get_reload_manager') as mock_reload_mgr:
            # Mock reload manager to return exceptions config
            mock_reload = MagicMock()
            mock_reload.get_config.return_value = {"escalation_targets": {"action": {"bead_type": "action"}}}
            mock_reload_mgr.return_value = mock_reload

            # Mock broadcaster to avoid actual SSE broadcasting
            with patch('src.escalate.handler.get_broadcaster') as mock_broadcaster:
                mock_bc = MagicMock()
                mock_bc.broadcast = AsyncMock()
                mock_broadcaster.return_value = mock_bc

                # Get the store and mock its methods
                store = await escalate_handler._get_store()
                with patch.object(store, 'create_pending_approval', return_value="approval-123"):
                    with patch.object(store, 'update_intent_status'):
                        # Should return result with awaiting_approval status (exception is caught internally)
                        result = await escalate_handler.escalate_intent(sample_request)

                        # Verify the result status
                        assert result.status == "awaiting_approval"
                        assert result.bead_id == ""  # No bead created yet

                        # Verify the approval card
                        approval_card = result.pending_card
                        assert approval_card["type"] == "approval"
                        assert approval_card["intent_id"] == sample_request.intent_id
                        assert approval_card["bead_body"] == gitops_body
                        assert approval_card["bead_type"] == "action"

                        # Verify validation result in card
                        validation_result = approval_card["validation_result"]
                        assert validation_result["is_valid"] is True
                        assert validation_result["requires_approval"] is True


@pytest.mark.asyncio
async def test_complete_validation_failure_to_clarification_pipeline(escalate_handler, session_store):
    """
    Test: Complete pipeline from validation failure to clarification card.

    This test simulates the flow when validation fails after re-formulation:
    1. Formulate initial bead body (fails validation)
    2. Attempt re-formulation (still fails validation)
    3. ValidationRetryExhaustedError raised
    4. Clarification card generated
    """
    # Create a session
    session_id = await session_store.create_session()

    request = EscalateRequest(
        intent_id="test-intent-123",
        session_id=session_id,
        utterance="Delete pod",
        intent_type="action",
        project_slug="ardenone-cluster",
    )

    # Mock formulate to always return invalid body
    invalid_body = "kubectl delete pod xyz"

    async def mock_call_simple(**kwargs):
        return invalid_body

    # Mock the LLM client's call_simple method
    with patch.object(escalate_handler, '_get_zai_client') as mock_get_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.call_simple = mock_call_simple
        mock_get_client.return_value = mock_client_instance

        with patch('src.escalate.handler.get_reload_manager') as mock_reload_mgr:
            # Mock reload manager to return exceptions config
            mock_reload = MagicMock()
            mock_reload.get_config.return_value = {"escalation_targets": {"action": {"bead_type": "action"}}}
            mock_reload_mgr.return_value = mock_reload

            # Set reformulation count to limit to trigger exhaustion
            await session_store.increment_reformulation_count(session_id)
            await session_store.increment_reformulation_count(session_id)
            await session_store.increment_reformulation_count(session_id)

            # Mock broadcaster to avoid actual SSE broadcasting
            with patch('src.escalate.handler.get_broadcaster') as mock_broadcaster:
                mock_bc = MagicMock()
                mock_bc.broadcast = AsyncMock()
                mock_broadcaster.return_value = mock_bc

                # Should raise ValidationRetryExhaustedError (but escalate_intent catches it and returns result)
                result = await escalate_handler.escalate_intent(request)

                # Verify the result is a clarification card (status is needs_clarification)
                assert result.status == "needs_clarification"
                assert result.pending_card["type"] == "clarification"
                assert len(result.pending_card["violations"]) > 0, "Should have violations"


# =============================================================================
# Test 7: Edge cases and error scenarios
# =============================================================================

def test_unknown_bead_type_defaults_to_task(validator):
    """
    Test: Unknown bead type defaults to TASK.

    When an unknown bead_type is passed, the validator should default to TASK.
    """
    body = "Look up pod status"
    result = validator.validate_bead_body(body, bead_type="unknown_type")

    # Should not raise exception
    assert result is not None

    # informational pattern should still be detected
    if "look up" in body.lower():
        assert result.requires_approval is False


def test_empty_bead_body_handling(validator):
    """
    Test: Empty bead body is handled gracefully.
    """
    result = validator.validate_bead_body("", bead_type="task")

    # Empty body should still return a result
    assert result is not None

    # Likely valid (no violations to detect)
    assert result.is_valid is True


def test_very_long_bead_body_handling(validator):
    """
    Test: Very long bead body is handled without performance issues.
    """
    # Create a long bead body
    long_body = "# Task: Large Task\n\n" + "## Details\n\n" + "x" * 100000 + "\n\n## Steps\n\n1. Step one\n2. Step two"

    result = validator.validate_bead_body(long_body, bead_type="task")

    # Should handle long body without issue
    assert result is not None


# =============================================================================
# Test 8: Pattern matching accuracy
# =============================================================================

def test_kubectl_verb_detection_accuracy(validator):
    """
    Test: Kubectl verb detection is accurate (no false positives/negatives).

    Verify that forbidden kubectl verbs are detected correctly.
    """
    # Test each forbidden verb
    for verb in ["delete", "apply", "create", "scale", "patch"]:
        body = f"# Task\n\nkubectl {verb} deployment myapp"
        result = validator.validate_bead_body(body, bead_type="action")

        assert result.is_valid is False, f"Should detect kubectl {verb}"
        assert any(v.rule_id == "no_direct_kubectl_mutation" for v in result.violations)


def test_gitops_pattern_detection_accuracy(validator):
    """
    Test: GitOps pattern detection is accurate.

    Verify that GitOps-approved patterns are recognized correctly.
    """
    gitops_patterns = [
        "Edit jedarden/declarative-config/k8s/",
        "git commit k8s/ manifest changes",
        "argocd app get myapp",
        "git push to declarative branch",
        "pull request in declarative-config",
        "edit k8s/ production deployment",
    ]

    for pattern in gitops_patterns:
        body = f"# Task\n\n{pattern}\n\nkubectl delete pod xyz"
        result = validator.validate_bead_body(body, bead_type="action")

        # Should still have kubectl violation but not GitOps violation
        kubectl_violations = [v for v in result.violations if v.rule_id == "no_direct_kubectl_mutation"]
        gitops_violations = [v for v in result.violations if v.rule_id == "gitops_required_for_mutations"]

        # Should detect kubectl violation
        assert len(kubectl_violations) > 0, f"Should detect kubectl violation for pattern: {pattern}"

        # Should NOT have GitOps violation (pattern is present)
        assert len(gitops_violations) == 0, f"Should not have GitOps violation for pattern: {pattern}"


def test_scoping_pattern_detection_accuracy(validator):
    """
    Test: Scoping pattern detection is accurate.

    Verify that scoping patterns are recognized correctly.
    """
    scoped_patterns = [
        ("cluster: ardenone-cluster", "cluster"),
        ("namespace: production", "namespace"),
        ("pod: myapp-123", "pod"),
        ("deployment: web-app", "deployment"),
    ]

    for pattern, scope_type in scoped_patterns:
        body = f"# Task\n\nkubectl delete pod xyz\n\nScope: {pattern}"
        result = validator.validate_bead_body(body, bead_type="action")

        # Should have kubectl violation but not scoping violation
        kubectl_violations = [v for v in result.violations if v.rule_id == "no_direct_kubectl_mutation"]
        scoping_violations = [v for v in result.violations if v.rule_id == "scoping_required"]

        # Should detect kubectl violation
        assert len(kubectl_violations) > 0, f"Should detect kubectl violation"

        # Should NOT have scoping violation (pattern is present)
        assert len(scoping_violations) == 0, f"Should not have scoping violation for pattern: {pattern}"


# =============================================================================
# Test runner
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])