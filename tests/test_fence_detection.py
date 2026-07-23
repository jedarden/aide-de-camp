"""Tests for fence detection in intent router."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.intent.router import IntentRouter, RoutedIntent, IntentClassification, IntentType


@pytest.mark.asyncio
async def test_check_fence_for_bead_with_refusal():
    """Test detecting a fenced bead with last_refusal_reason."""
    router = IntentRouter()

    # Mock the store to return a fenced bead
    mock_store = AsyncMock()
    mock_store.get_bead_watch.return_value = {
        "bead_ref": "adc-test1",
        "last_refusal_reason": "Missing context: need user input",
        "refusal_count": 3,
        "fenced_at": 1234567890,
    }

    router.store = mock_store

    # Check fence status
    fence_context = await router._check_fence_for_bead("adc-test1")

    # Verify fence detected
    assert fence_context is not None
    assert fence_context["bead_id"] == "adc-test1"
    assert fence_context["refusal_reason"] == "Missing context: need user input"
    assert fence_context["refusal_count"] == 3
    assert fence_context["fenced_at"] == 1234567890

    mock_store.get_bead_watch.assert_called_once_with("adc-test1")


@pytest.mark.asyncio
async def test_check_fence_for_bead_not_fenced():
    """Test detecting a non-fenced bead."""
    router = IntentRouter()

    # Mock the store to return a bead without refusal_reason
    mock_store = AsyncMock()
    mock_store.get_bead_watch.return_value = {
        "bead_ref": "adc-test2",
        "refusal_count": 0,
        "fenced_at": None,
        "last_refusal_reason": None,
    }

    router.store = mock_store

    # Check fence status
    fence_context = await router._check_fence_for_bead("adc-test2")

    # Verify no fence detected
    assert fence_context is None


@pytest.mark.asyncio
async def test_check_fence_for_bead_not_found():
    """Test detecting fence when bead not found in watch list."""
    router = IntentRouter()

    # Mock the store to return None (bead not watched)
    mock_store = AsyncMock()
    mock_store.get_bead_watch.return_value = None

    router.store = mock_store

    # Check fence status
    fence_context = await router._check_fence_for_bead("adc-nonexistent")

    # Verify no fence detected
    assert fence_context is None


@pytest.mark.asyncio
async def test_escalate_with_fenced_bead_in_session():
    """Test escalation when session has fenced beads."""
    router = IntentRouter()

    # Create a routed intent
    routed_intent = RoutedIntent(
        intent_id="intent-1",
        classification=IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="test-project",
        ),
        session_id="session-1",
        utterance="Do something",
    )

    # Mock store to return fenced beads for the session
    mock_store = AsyncMock()
    mock_store.get_fenced_beads_for_session.return_value = [
        {
            "bead_ref": "adc-fenced1",
            "intent_id": "old-intent-1",
            "topic_id": "topic-1",
            "project_slug": "test-project",
            "last_refusal_reason": "Blocked: needs clarification",
            "refusal_count": 3,
            "fenced_at": 1234567890,
        }
    ]

    router.store = mock_store

    # Mock _create_stuck_card_from_fence to return expected result
    expected_result = {
        "intent_id": "intent-1",
        "status": "stuck",
        "bead_id": "adc-fenced1",
        "stuck_reason": "Blocked: needs clarification",
    }

    with patch.object(router, "_create_stuck_card_from_fence", new=AsyncMock(return_value=expected_result)):
        result = await router._escalate_to_bead(routed_intent, MagicMock())

    # Verify stuck card created instead of escalation
    assert result["status"] == "stuck"
    assert result["bead_id"] == "adc-fenced1"
    assert result["stuck_reason"] == "Blocked: needs clarification"

    # Verify fenced beads were checked
    mock_store.get_fenced_beads_for_session.assert_called_once_with("session-1")


@pytest.mark.asyncio
async def test_create_stuck_card_from_fence():
    """Test creating stuck card from fence context."""
    router = IntentRouter()

    routed_intent = RoutedIntent(
        intent_id="intent-1",
        classification=IntentClassification(
            intent_type=IntentType.TASK_PROFILE,
            project_slug="test-project",
        ),
        session_id="session-1",
        utterance="Test task",
    )

    fence_context = {
        "bead_id": "adc-fenced1",
        "refusal_reason": "Missing input",
        "refusal_count": 2,
        "fenced_at": 1234567890,
    }

    # Mock store methods
    mock_store = AsyncMock()
    mock_store.find_or_create_topic.return_value = ("topic-1", False)
    mock_store.link_intent_to_topic = AsyncMock()
    mock_store.create_result.return_value = "result-1"

    router.store = mock_store

    # Mock broadcaster
    mock_broadcaster = AsyncMock()

    with patch("src.intent.router.get_broadcaster", return_value=mock_broadcaster):
        result = await router._create_stuck_card_from_fence(routed_intent, fence_context)

    # Verify result
    assert result["intent_id"] == "intent-1"
    assert result["status"] == "stuck"
    assert result["bead_id"] == "adc-fenced1"
    assert result["stuck_reason"] == "Missing input"
    assert result["refusal_count"] == 2

    # Verify store calls
    mock_store.find_or_create_topic.assert_called_once()
    mock_store.link_intent_to_topic.assert_called_once_with("intent-1", "topic-1")
    mock_store.create_result.assert_called_once()

    # Verify result data includes fence context
    call_args = mock_store.create_result.call_args
    assert call_args[1]["urgency"] == "high"
    assert "bead_id" in call_args[1]["data"]
    assert call_args[1]["data"]["bead_id"] == "adc-fenced1"
