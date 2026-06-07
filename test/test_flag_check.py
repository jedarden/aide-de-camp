"""
Unit tests for confidence threshold routing in IntentRouter.

Tests cover TC-FC-001 through TC-FC-010 from notes/adc-1dj-flag-check-test-cases.md

Confidence thresholds:
- >= 0.9: High confidence - dispatch immediately
- 0.7 - 0.9: Medium confidence - dispatch but flag for clarification
- < 0.7: Low confidence - return CLARIFICATION intent type

Fixtures are imported from test/fixtures/flag_check_fixtures.py
"""
from unittest.mock import AsyncMock

import pytest

from src.intent.router import IntentType, IntentClassification

# Import fixtures and test data from shared fixtures module
from test.fixtures.flag_check_fixtures import (
    # LLM response fixtures
    HIGH_CONFIDENCE_095,
    HIGH_CONFIDENCE_100,
    HIGH_CONFIDENCE_090,
    MEDIUM_CONFIDENCE_080,
    MEDIUM_CONFIDENCE_075,
    MEDIUM_CONFIDENCE_070,
    LOW_CONFIDENCE_060,
    LOW_CONFIDENCE_030,
    LOW_CONFIDENCE_000,
    MISSING_CONFIDENCE,
    UNKNOWN_INTENT_TYPE,
    MALFORMED_JSON,
    INCOMPLETE_JSON,
    EMPTY_INTENTS_ARRAY,
    # pytest fixtures (must import dependencies for mock_router_with_mocks)
    mock_zai_client,
    mock_session_store,
    mock_router_with_mocks,
    sample_utterance,
    sample_session_id,
    sample_utterance_id,
)


# =============================================================================
# Test Helper Fixtures
# =============================================================================

@pytest.fixture
def mock_router(mock_router_with_mocks):
    """
    Alias for mock_router_with_mocks for backward compatibility.

    Returns a tuple of (router_instance, mock_client, mock_store) where
    mock_client.call_simple can be dynamically configured per test.
    """
    return mock_router_with_mocks


# =============================================================================
# Happy Path (High Confidence Dispatch) - TC-FC-001 to TC-FC-003
# =============================================================================

@pytest.mark.asyncio
class TestHighConfidenceDispatch:
    """Test high confidence (>= 0.9) dispatches immediately without clarification."""

    async def test_tc_fc_001_high_confidence_095_dispatch(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-001: High Confidence (>0.9) Dispatch

        Intent with confidence 0.95 should dispatch immediately.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = HIGH_CONFIDENCE_095.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.STATUS
        assert classification.confidence == 0.95
        assert classification.project_slug == "options-pipeline"
        # High confidence should NOT be clarification
        assert classification.intent_type != IntentType.CLARIFICATION

    async def test_tc_fc_002_max_confidence_100_dispatch(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-002: Maximum Confidence (1.0) Dispatch

        Intent with confidence 1.0 should dispatch immediately.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = HIGH_CONFIDENCE_100.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.ACTION
        assert classification.confidence == 1.0
        assert classification.intent_type != IntentType.CLARIFICATION

    async def test_tc_fc_003_boundary_high_090_dispatch(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-003: Boundary High (0.9) Dispatch

        Intent with confidence exactly 0.9 should dispatch immediately.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = HIGH_CONFIDENCE_090.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.LOOKUP
        assert classification.confidence == 0.9
        assert classification.intent_type != IntentType.CLARIFICATION


# =============================================================================
# Flag for Possible Clarification (Medium Confidence) - TC-FC-004 to TC-FC-006
# =============================================================================

@pytest.mark.asyncio
class TestMediumConfidenceFlag:
    """Test medium confidence (0.7-0.9) dispatches but is flagged for clarification."""

    async def test_tc_fc_004_medium_confidence_080_flag(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-004: Medium Confidence (0.8) Flag

        Intent with confidence 0.8 should dispatch but be flagged for clarification.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = MEDIUM_CONFIDENCE_080.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.STATUS
        assert classification.confidence == 0.8
        # Medium confidence is in the "flag for clarification" range
        assert 0.7 <= classification.confidence < 0.9
        # But still dispatches (not CLARIFICATION type)
        assert classification.intent_type != IntentType.CLARIFICATION

    async def test_tc_fc_005_medium_confidence_075_flag(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-005: Medium Confidence (0.75) Flag

        Intent with confidence 0.75 should dispatch but be flagged.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = MEDIUM_CONFIDENCE_075.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.BRAINSTORM
        assert classification.confidence == 0.75
        assert 0.7 <= classification.confidence < 0.9
        assert classification.intent_type != IntentType.CLARIFICATION

    async def test_tc_fc_006_boundary_medium_070_flag(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-006: Boundary Medium (0.7) Flag

        Intent with confidence exactly 0.7 should dispatch but be flagged.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = MEDIUM_CONFIDENCE_070.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.ACTION
        assert classification.confidence == 0.7
        # At the boundary - should be flagged but still dispatch
        assert 0.7 <= classification.confidence < 0.9


# =============================================================================
# Explicit Clarification Request (Low Confidence) - TC-FC-007 to TC-FC-009
# =============================================================================

@pytest.mark.asyncio
class TestLowConfidenceClarification:
    """Test low confidence (< 0.7) returns CLARIFICATION intent type."""

    async def test_tc_fc_007_low_confidence_060_clarification(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-007: Low Confidence (0.6) Clarification

        Intent with confidence 0.6 should return clarification type.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = LOW_CONFIDENCE_060.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.CLARIFICATION
        assert classification.confidence == 0.6
        # Below threshold should require user clarification
        assert classification.confidence < 0.7

    async def test_tc_fc_008_very_low_confidence_030_clarification(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-008: Very Low Confidence (0.3) Clarification

        Intent with confidence 0.3 should require clarification.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = LOW_CONFIDENCE_030.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.CLARIFICATION
        assert classification.confidence == 0.3
        assert classification.confidence < 0.7

    async def test_tc_fc_009_zero_confidence_clarification(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-009: Zero Confidence Clarification

        Intent with confidence 0.0 should require clarification.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = LOW_CONFIDENCE_000.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.CLARIFICATION
        assert classification.confidence == 0.0
        assert classification.confidence < 0.7


# =============================================================================
# Edge Cases - TC-FC-010
# =============================================================================

@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases for confidence threshold routing."""

    async def test_tc_fc_010_missing_confidence_defaults_to_080(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-010: Missing Confidence Field

        JSON response missing confidence field should use default 0.8.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = MISSING_CONFIDENCE.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        assert classification.intent_type == IntentType.STATUS
        # Default confidence is 0.8 when missing
        assert classification.confidence == 0.8

    async def test_unknown_intent_type_defaults_to_status(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-014: Unknown Intent Type

        Invalid intent_type should default to STATUS.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = UNKNOWN_INTENT_TYPE.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        # Unknown intent types default to STATUS
        assert classification.intent_type == IntentType.STATUS
        assert classification.confidence == 0.9

    async def test_malformed_json_fallback_to_status(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-017: Malformed JSON Response

        Non-JSON response from LLM should trigger fallback.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = MALFORMED_JSON.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        # Fallback: return single status intent
        assert classification.intent_type == IntentType.STATUS
        assert classification.confidence == 0.5
        assert classification.reasoning == "Classification failed, defaulting to status"

    async def test_json_decode_error_fallback_to_status(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-018: JSON Decode Error

        Invalid JSON structure should trigger fallback.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = INCOMPLETE_JSON.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        assert len(classifications) == 1
        classification = classifications[0]
        # Fallback: return single status intent
        assert classification.intent_type == IntentType.STATUS
        assert classification.confidence == 0.5
        assert classification.reasoning == "Classification failed, defaulting to status"

    async def test_empty_intents_array(
        self,
        mock_router,
        sample_utterance,
        sample_session_id,
    ):
        """
        TC-FC-015: Empty Intent Array

        Empty JSON array from LLM should be handled.
        """
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = EMPTY_INTENTS_ARRAY.to_raw_response()

        classifications = await router.classify_utterance(sample_utterance, sample_session_id)

        # Empty array should return empty classifications
        assert len(classifications) == 0
        assert classifications == []


# =============================================================================
# Integration Tests - route_utterance
# =============================================================================

@pytest.mark.asyncio
class TestRouteUtterance:
    """Test route_utterance with confidence thresholds."""

    async def test_route_high_confidence_creates_routed_intent(
        self,
        mock_router,
        sample_utterance,
        sample_utterance_id,
        sample_session_id,
    ):
        """Test that high confidence intents create RoutedIntent correctly."""
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = HIGH_CONFIDENCE_095.to_raw_response()

        routed_intents = await router.route_utterance(
            sample_utterance,
            sample_utterance_id,
            sample_session_id,
        )

        assert len(routed_intents) == 1
        routed = routed_intents[0]
        assert routed.intent_id
        assert routed.session_id == sample_session_id
        assert routed.utterance == "check the pods"
        assert routed.classification.intent_type == IntentType.STATUS
        assert routed.classification.confidence == 0.95

    async def test_route_low_confidence_creates_clarification_intent(
        self,
        mock_router,
        sample_utterance,
        sample_utterance_id,
        sample_session_id,
    ):
        """Test that low confidence intents create CLARIFICATION RoutedIntent."""
        router, mock_client, mock_store = mock_router
        mock_client.call_simple.return_value = LOW_CONFIDENCE_060.to_raw_response()

        routed_intents = await router.route_utterance(
            sample_utterance,
            sample_utterance_id,
            sample_session_id,
        )

        assert len(routed_intents) == 1
        routed = routed_intents[0]
        assert routed.intent_id
        assert routed.classification.intent_type == IntentType.CLARIFICATION
        assert routed.classification.confidence == 0.6
