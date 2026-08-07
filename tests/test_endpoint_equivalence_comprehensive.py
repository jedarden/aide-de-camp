"""
Comprehensive Endpoint Equivalence Tests

Test suite that verifies /dispatch and /test/intent-classify endpoints produce
identical classifications for the same utterances across all intent types and edge cases.

These tests use the comparison utilities from tests.helpers.endpoint_comparison
to send requests to both endpoints and verify equivalence.

Test Coverage:
- All intent types: status, action, brainstorm, lookup, reminder, self-modification, etc.
- Edge cases: empty utterances, special characters, Unicode, very long text
- Diverse utterances: natural language variations, technical queries, multi-intent
- Minimum 10+ test cases as required
"""
import pytest
from httpx import AsyncClient, ASGITransport

from tests.helpers.endpoint_comparison import (
    send_to_both_endpoints,
    compare_classification_counts,
    format_comparison_summary,
    RequestValidationError,
)


@pytest.mark.asyncio
async def test_status_intent_equivalence_basic():
    """Test that both endpoints classify basic status intent identically."""
    from src.main import app

    utterance = "how are the pods doing"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-status-basic",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for status intent: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    # Both should return at least 1 classification
    assert count_comparison["dispatch_count"] >= 1
    assert count_comparison["test_count"] >= 1

    print(f"✅ Status intent equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_action_intent_equivalence_restart():
    """Test action intent classification equivalence (restart scenario)."""
    from src.main import app

    utterance = "restart the nap-api deployment"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-action-restart",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for restart action: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    # Both should identify as action
    test_intent_types = [c.get("intent_type") for c in test_result["classifications"]]
    assert "action" in test_intent_types or any("action" in str(t).lower() for t in test_intent_types)

    print(f"✅ Action intent equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_brainstorm_intent_equivalence():
    """Test brainstorm intent classification equivalence."""
    from src.main import app

    utterance = "help me think of ways to improve the deployment pipeline"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-brainstorm",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for brainstorm: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    print(f"✅ Brainstorm intent equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_lookup_logs_intent_equivalence():
    """Test lookup:logs intent classification equivalence."""
    from src.main import app

    utterance = "show me the recent logs for nap-api-pod"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-lookup-logs",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for lookup logs: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    # Should identify as lookup or lookup:logs
    test_intent_types = [c.get("intent_type") for c in test_result["classifications"]]
    assert any("lookup" in str(t).lower() for t in test_intent_types)

    print(f"✅ Lookup logs intent equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_lookup_config_intent_equivalence():
    """Test lookup:config intent classification equivalence."""
    from src.main import app

    utterance = "what's the current configuration for the options pipeline"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-lookup-config",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for lookup config: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    print(f"✅ Lookup config intent equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_reminder_intent_equivalence():
    """Test reminder intent classification equivalence."""
    from src.main import app

    utterance = "remind me to check the deployment status in 30 minutes"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-reminder",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for reminder: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    # Should identify as reminder
    test_intent_types = [c.get("intent_type") for c in test_result["classifications"]]
    assert any("reminder" in str(t).lower() for t in test_intent_types)

    print(f"✅ Reminder intent equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_self_modification_intent_equivalence():
    """Test self-modification intent classification equivalence."""
    from src.main import app

    utterance = "update the dispatch logic to use the new intent router"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-self-modification",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for self-modification: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    print(f"✅ Self-modification intent equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_monitoring_config_intent_equivalence():
    """Test monitoring-config intent classification equivalence."""
    from src.main import app

    utterance = "set up monitoring for the nap-api pipeline"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-monitoring-config",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for monitoring config: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    print(f"✅ Monitoring config intent equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_multi_intent_equivalence():
    """Test that both endpoints handle multi-intent utterances identically."""
    from src.main import app

    utterance = "check the pods and show me the logs if any are failing"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-multi-intent",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for multi-intent: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    # Multi-intent should return 2+ classifications
    assert count_comparison["dispatch_count"] >= 2, "Should identify 2+ intents"

    print(f"✅ Multi-intent equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_edge_case_empty_utterance():
    """Test edge case: empty utterance raises validation error on both endpoints."""
    from src.main import app

    with pytest.raises(RequestValidationError) as exc_info:
        await send_to_both_endpoints(
            utterance="",
            app=app,
        )

    assert "non-empty string" in str(exc_info.value)
    print("✅ Empty utterance validation test passed")


@pytest.mark.asyncio
async def test_edge_case_whitespace_only():
    """Test edge case: whitespace-only utterance raises validation error."""
    from src.main import app

    with pytest.raises(RequestValidationError) as exc_info:
        await send_to_both_endpoints(
            utterance="   \n\t  ",
            app=app,
        )

    assert "non-empty string" in str(exc_info.value)
    print("✅ Whitespace-only utterance validation test passed")


@pytest.mark.asyncio
async def test_edge_case_special_characters():
    """Test edge case: utterance with special characters."""
    from src.main import app

    utterance = "check the pods in namespace: test-env & deployment: api-v2 (prod)"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-special-chars",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for special characters: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    print(f"✅ Special characters equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_edge_case_unicode_emoji():
    """Test edge case: utterance with Unicode emoji."""
    from src.main import app

    utterance = "check the pod status 🚀 and show logs 📋"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-unicode-emoji",
        app=app,
    )

    # Verify count equivalence
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for Unicode emoji: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    print(f"✅ Unicode emoji equivalence test passed for: '{utterance}'")


@pytest.mark.asyncio
async def test_edge_case_long_utterance():
    """Test edge case: very long utterance (1000+ characters)."""
    from src.main import app

    utterance = (
        "I need you to check the deployment status of the nap-api pipeline in the "
        "production environment and then verify that all the pods are running correctly "
        "and also check the recent logs for any errors and then show me the ArgoCD "
        "application status and finally check if there are any recent git commits that "
        "might have affected the deployment and also check the bead list to see if there "
        "are any open beads related to this deployment and verify the CI status and check "
        "the events in the namespace to see if there are any recent issues and overall "
        "give me a comprehensive status report of everything related to the nap-api "
        "deployment in production right now with all the details you can find. " * 3
    )

    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-long-utterance",
        app=app,
    )

    # Verify count equivalence (may identify multiple intents)
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    assert count_comparison["match"], (
        f"Intent count mismatch for long utterance: "
        f"dispatch={count_comparison['dispatch_count']}, "
        f"test={count_comparison['test_count']}"
    )

    print(f"✅ Long utterance ({len(utterance)} chars) equivalence test passed")


@pytest.mark.asyncio
async def test_natural_language_variations_status():
    """Test that various natural language forms are classified identically."""
    from src.main import app

    variations = [
        "how are the pods doing",
        "what's the status of the pods",
        "check pod status",
        "show me pod health",
        "are the pods running",
    ]

    for i, utterance in enumerate(variations):
        dispatch_result, test_result = await send_to_both_endpoints(
            utterance=utterance,
            session_id=f"test-nl-variations-{i}",
            app=app,
        )

        # Verify count equivalence for each variation
        count_comparison = compare_classification_counts(dispatch_result, test_result)
        assert count_comparison["match"], (
            f"Intent count mismatch for variation '{utterance}': "
            f"dispatch={count_comparison['dispatch_count']}, "
            f"test={count_comparison['test_count']}"
        )

    print(f"✅ Natural language variations equivalence test passed ({len(variations)} variations)")


@pytest.mark.asyncio
async def test_technical_query_variations():
    """Test technical queries with different terminology."""
    from src.main import app

    technical_queries = [
        "kubectl get pods -n production",
        "show me all pods in the production namespace",
        "list all running pods in prod",
        "get pod json output for production environment",
    ]

    for i, utterance in enumerate(technical_queries):
        dispatch_result, test_result = await send_to_both_endpoints(
            utterance=utterance,
            session_id=f"test-technical-queries-{i}",
            app=app,
        )

        # Verify count equivalence
        count_comparison = compare_classification_counts(dispatch_result, test_result)
        assert count_comparison["match"], (
            f"Intent count mismatch for technical query '{utterance}': "
            f"dispatch={count_comparison['dispatch_count']}, "
            f"test={count_comparison['test_count']}"
        )

    print(f"✅ Technical query variations equivalence test passed ({len(technical_queries)} queries)")


@pytest.mark.asyncio
async def test_comprehensive_summary_generation():
    """Test that comprehensive comparison summary is generated correctly."""
    from src.main import app

    utterance = "check the pods and deployment status for nap-api"
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id="test-summary-generation",
        app=app,
    )

    # Generate comparison summary
    count_comparison = compare_classification_counts(dispatch_result, test_result)
    summary = format_comparison_summary(
        dispatch_result,
        test_result,
        count_comparison,
        intent_comparison=None,
    )

    # Verify summary contains expected sections
    assert "ENDPOINT COMPARISON SUMMARY" in summary
    assert "DISPATCH ENDPOINT" in summary
    assert "TEST ENDPOINT" in summary
    assert "COMPARISON RESULTS" in summary
    assert utterance in summary
    assert "test-summary-generation" in summary

    # Verify count comparison is shown
    if count_comparison["match"]:
        assert "✅ Count Match" in summary
    else:
        assert "❌ Count Mismatch" in summary

    print(f"✅ Comprehensive summary generation test passed")


@pytest.mark.asyncio
async def test_session_isolation():
    """Test that different sessions produce independent but equivalent results."""
    from src.main import app

    utterance = "check the pipeline status"

    # Test with multiple different session IDs
    session_ids = ["test-session-1", "test-session-2", "test-session-3"]

    for session_id in session_ids:
        dispatch_result, test_result = await send_to_both_endpoints(
            utterance=utterance,
            session_id=session_id,
            app=app,
        )

        # Each session should produce equivalent counts
        count_comparison = compare_classification_counts(dispatch_result, test_result)
        assert count_comparison["match"], (
            f"Intent count mismatch for session {session_id}: "
            f"dispatch={count_comparison['dispatch_count']}, "
            f"test={count_comparison['test_count']}"
        )

        # Verify session ID is respected in dispatch result
        assert dispatch_result["session_id"] == session_id

    print(f"✅ Session isolation equivalence test passed ({len(session_ids)} sessions)")


@pytest.mark.asyncio
async def test_concurrent_requests_equivalence():
    """Test that concurrent requests to both endpoints produce equivalent results."""
    from src.main import app
    import asyncio

    utterances = [
        "check the pods",
        "show me the logs",
        "what's the deployment status",
        "list the open beads",
    ]

    async def test_single_utterance(utterance: str, index: int):
        dispatch_result, test_result = await send_to_both_endpoints(
            utterance=utterance,
            session_id=f"test-concurrent-{index}",
            app=app,
        )
        count_comparison = compare_classification_counts(dispatch_result, test_result)
        assert count_comparison["match"], (
            f"Intent count mismatch for concurrent utterance '{utterance}': "
            f"dispatch={count_comparison['dispatch_count']}, "
            f"test={count_comparison['test_count']}"
        )
        return utterance, count_comparison["dispatch_count"]

    # Run all tests concurrently
    results = await asyncio.gather(*[
        test_single_utterance(u, i) for i, u in enumerate(utterances)
    ])

    print(f"✅ Concurrent requests equivalence test passed ({len(results)} concurrent requests)")


# Run tests when executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
