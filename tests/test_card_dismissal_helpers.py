"""
Unit tests for card dismissal helper functions (bead adc-3xgfs).

Tests that the helper functions in card_dismissal_helpers.py work correctly.
"""

import pytest

from tests.card_dismissal_helpers import (
    create_test_session,
    create_test_session_with_topic,
    create_stuck_card,
    create_failed_card,
    verify_card_present,
    count_cards_by_type,
    find_card_by_bead_id,
    get_dismissal_selector,
    create_mock_router,
)


class TestSessionCreationHelpers:
    """Test session creation helper functions."""

    @pytest.mark.asyncio
    async def test_create_test_session(self, tmp_path):
        """Test creating a test session."""
        store, session_id = await create_test_session(tmp_path=tmp_path)

        assert store is not None
        assert session_id is not None
        assert len(session_id) > 0

        await store.close()

    @pytest.mark.asyncio
    async def test_create_test_session_with_existing_store(self, tmp_path):
        """Test creating a test session with an existing store."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_existing.db"
        store = SessionStore(db_path)
        await store.initialize()

        new_store, session_id = await create_test_session(store=store)

        assert new_store is store
        assert session_id is not None

        await store.close()

    @pytest.mark.asyncio
    async def test_create_test_session_with_topic(self, tmp_path):
        """Test creating a test session with a topic."""
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path,
            label="Helper Test Topic",
            topic_type="research"
        )

        assert store is not None
        assert session_id is not None
        assert topic_id is not None

        # Verify topic was created
        topics = await store.get_active_topics(session_id)
        assert len(topics) == 1
        assert topics[0]["id"] == topic_id
        assert topics[0]["label"] == "Helper Test Topic"
        assert topics[0]["type"] == "research"

        await store.close()


class TestCardCreationHelpers:
    """Test card creation helper functions."""

    @pytest.mark.asyncio
    async def test_create_stuck_card(self, tmp_path):
        """Test creating a stuck card."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        card_data = await create_stuck_card(
            store=store,
            session_id=session_id,
            topic_id=topic_id,
            bead_id="adc-stuck-helper-test",
            stuck_reason="Helper test stuck",
            refusal_count=5,
            message="Helper test message"
        )

        assert card_data["bead_id"] == "adc-stuck-helper-test"
        assert card_data["stuck_reason"] == "Helper test stuck"
        assert card_data["refusal_count"] == 5
        assert card_data["message"] == "Helper test message"
        assert card_data["session_id"] == session_id
        assert card_data["topic_id"] == topic_id
        assert "intent_id" in card_data

        await store.close()

    @pytest.mark.asyncio
    async def test_create_stuck_card_creates_topic_if_needed(self, tmp_path):
        """Test that create_stuck_card creates a topic if not provided."""
        store, session_id = await create_test_session(tmp_path=tmp_path)

        card_data = await create_stuck_card(
            store=store,
            session_id=session_id,
            bead_id="adc-stuck-auto-topic"
        )

        assert "topic_id" in card_data
        assert card_data["topic_id"] is not None

        # Verify topic was created
        topics = await store.get_active_topics(session_id)
        assert len(topics) >= 1

        await store.close()

    @pytest.mark.asyncio
    async def test_create_failed_card(self, tmp_path):
        """Test creating a failed card."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        card_data = await create_failed_card(
            store=store,
            session_id=session_id,
            topic_id=topic_id,
            bead_id="adc-failed-helper-test",
            failure_reason="Helper test failure",
            error_type="helper_error",
            message="Helper test failure message"
        )

        assert card_data["bead_id"] == "adc-failed-helper-test"
        assert card_data["failure_reason"] == "Helper test failure"
        assert card_data["error_type"] == "helper_error"
        assert card_data["message"] == "Helper test failure message"
        assert card_data["session_id"] == session_id
        assert card_data["topic_id"] == topic_id
        assert "intent_id" in card_data

        await store.close()

    @pytest.mark.asyncio
    async def test_create_failed_card_creates_topic_if_needed(self, tmp_path):
        """Test that create_failed_card creates a topic if not provided."""
        store, session_id = await create_test_session(tmp_path=tmp_path)

        card_data = await create_failed_card(
            store=store,
            session_id=session_id,
            bead_id="adc-failed-auto-topic"
        )

        assert "topic_id" in card_data
        assert card_data["topic_id"] is not None

        # Verify topic was created
        topics = await store.get_active_topics(session_id)
        assert len(topics) >= 1

        await store.close()


class TestCardVerificationHelpers:
    """Test card verification helper functions."""

    @pytest.mark.asyncio
    async def test_verify_card_present_with_stuck_card(self, tmp_path):
        """Test verifying a stuck card is present."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        # Create stuck card
        await create_stuck_card(
            store=store,
            session_id=session_id,
            topic_id=topic_id,
            bead_id="adc-stuck-verify-test"
        )

        # Get cards (in real scenario, these would come from the API)
        # For this test, we'll simulate the card structure
        cards = [
            {
                "card_type": "builtin",
                "builtin_data": {
                    "type": "stuck",
                    "data": {"bead_id": "adc-stuck-verify-test"}
                }
            }
        ]

        assert verify_card_present(cards, "stuck", "adc-stuck-verify-test")
        assert not verify_card_present(cards, "failed", "adc-stuck-verify-test")
        assert not verify_card_present(cards, "stuck", "different-id")

        await store.close()

    @pytest.mark.asyncio
    async def test_verify_card_present_with_failed_card(self, tmp_path):
        """Test verifying a failed card is present."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        # Create failed card
        await create_failed_card(
            store=store,
            session_id=session_id,
            topic_id=topic_id,
            bead_id="adc-failed-verify-test"
        )

        # Simulate card structure
        cards = [
            {
                "card_type": "builtin",
                "builtin_data": {
                    "type": "failed",
                    "data": {"bead_id": "adc-failed-verify-test"}
                }
            }
        ]

        assert verify_card_present(cards, "failed", "adc-failed-verify-test")
        assert not verify_card_present(cards, "stuck", "adc-failed-verify-test")

        await store.close()

    def test_count_cards_by_type(self):
        """Test counting cards by type."""
        cards = [
            {"card_type": "builtin", "builtin_data": {"type": "stuck"}},
            {"card_type": "builtin", "builtin_data": {"type": "stuck"}},
            {"card_type": "builtin", "builtin_data": {"type": "failed"}},
            {"card_type": "topic"},  # Not a builtin card
        ]

        assert count_cards_by_type(cards, "stuck") == 2
        assert count_cards_by_type(cards, "failed") == 1
        assert count_cards_by_type(cards, "error") == 0

    def test_find_card_by_bead_id(self):
        """Test finding a card by bead_id."""
        cards = [
            {
                "card_type": "builtin",
                "builtin_data": {
                    "type": "stuck",
                    "data": {"bead_id": "adc-found-1"}
                }
            },
            {
                "card_type": "builtin",
                "builtin_data": {
                    "type": "failed",
                    "data": {"bead_id": "adc-found-2"}
                }
            },
        ]

        card = find_card_by_bead_id(cards, "adc-found-1")
        assert card is not None
        assert card["builtin_data"]["type"] == "stuck"

        card = find_card_by_bead_id(cards, "adc-found-2")
        assert card is not None
        assert card["builtin_data"]["type"] == "failed"

        card = find_card_by_bead_id(cards, "not-found")
        assert card is None


class TestDismissalTriggerHelpers:
    """Test dismissal trigger helper functions."""

    def test_get_dismissal_selector_for_stuck_card(self):
        """Test getting dismissal selector for stuck cards."""
        # All stuck cards
        selector = get_dismissal_selector(card_type="stuck")
        assert selector == '[data-builtin="stuck"] .dismiss-button'

        # Specific stuck card
        selector = get_dismissal_selector(bead_id="adc-stuck-1", card_type="stuck")
        assert selector == '[data-builtin="stuck"][data-bead-id="adc-stuck-1"] .dismiss-button'

    def test_get_dismissal_selector_for_failed_card(self):
        """Test getting dismissal selector for failed cards."""
        # All failed cards
        selector = get_dismissal_selector(card_type="failed")
        assert selector == '[data-builtin="failed"] .dismiss-button'

        # Specific failed card
        selector = get_dismissal_selector(bead_id="adc-failed-1", card_type="failed")
        assert selector == '[data-builtin="failed"][data-bead-id="adc-failed-1"] .dismiss-button'


class TestMockHelpers:
    """Test mock creation helper functions."""

    def test_create_mock_router(self):
        """Test creating a mock router."""
        import asyncio

        router = create_mock_router()

        assert router is not None
        assert hasattr(router, "route_result")

        # Test that it returns expected decision structure
        # Since route_result is async, we need to run it
        decision = asyncio.run(router.route_result())
        assert decision.target_surfaces == []
        assert decision.fallback_used == True


class TestIntegrationHelpers:
    """Integration tests for helper functions working together."""

    @pytest.mark.asyncio
    async def test_full_stuck_card_workflow(self, tmp_path):
        """Test complete workflow: create session, create card, verify."""
        # Create session with topic
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path,
            label="Integration Test Topic",
            topic_type="project"
        )

        # Create stuck card
        card_data = await create_stuck_card(
            store=store,
            session_id=session_id,
            topic_id=topic_id,
            bead_id="adc-integration-stuck",
            stuck_reason="Integration test",
            refusal_count=2
        )

        # Simulate card list as it would come from API
        cards = [
            {
                "card_type": "builtin",
                "builtin_data": {
                    "type": "stuck",
                    "data": {"bead_id": "adc-integration-stuck"}
                }
            }
        ]

        # Verify card is present
        assert verify_card_present(cards, "stuck", "adc-integration-stuck")

        # Find the card
        card = find_card_by_bead_id(cards, "adc-integration-stuck")
        assert card is not None

        # Count cards
        count = count_cards_by_type(cards, "stuck")
        assert count == 1

        # Get selector for dismissal
        selector = get_dismissal_selector(bead_id="adc-integration-stuck", card_type="stuck")
        assert "adc-integration-stuck" in selector

        await store.close()

    @pytest.mark.asyncio
    async def test_full_failed_card_workflow(self, tmp_path):
        """Test complete workflow with failed card."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        card_data = await create_failed_card(
            store=store,
            session_id=session_id,
            topic_id=topic_id,
            bead_id="adc-integration-failed",
            failure_reason="Integration failure"
        )

        cards = [
            {
                "card_type": "builtin",
                "builtin_data": {
                    "type": "failed",
                    "data": {"bead_id": "adc-integration-failed"}
                }
            }
        ]

        assert verify_card_present(cards, "failed", "adc-integration-failed")
        assert count_cards_by_type(cards, "failed") == 1

        await store.close()

    @pytest.mark.asyncio
    async def test_multiple_cards_workflow(self, tmp_path):
        """Test workflow with multiple cards of different types."""
        store, session_id, topic1 = await create_test_session_with_topic(tmp_path=tmp_path)

        # Create multiple topics for different cards
        _, topic2 = await store.find_or_create_topic(
            label="Second Topic",
            session_id=session_id,
            topic_type="research"
        )

        # Create stuck card
        await create_stuck_card(
            store=store,
            session_id=session_id,
            topic_id=topic1,
            bead_id="adc-multi-stuck-1"
        )

        # Create failed card
        await create_failed_card(
            store=store,
            session_id=session_id,
            topic_id=topic2,
            bead_id="adc-multi-failed-1"
        )

        # Simulate mixed card list
        cards = [
            {
                "card_type": "builtin",
                "builtin_data": {
                    "type": "stuck",
                    "data": {"bead_id": "adc-multi-stuck-1"}
                }
            },
            {
                "card_type": "builtin",
                "builtin_data": {
                    "type": "failed",
                    "data": {"bead_id": "adc-multi-failed-1"}
                }
            },
        ]

        # Verify both cards are present
        assert verify_card_present(cards, "stuck", "adc-multi-stuck-1")
        assert verify_card_present(cards, "failed", "adc-multi-failed-1")

        # Count by type
        assert count_cards_by_type(cards, "stuck") == 1
        assert count_cards_by_type(cards, "failed") == 1

        # Find specific cards
        stuck_card = find_card_by_bead_id(cards, "adc-multi-stuck-1")
        assert stuck_card["builtin_data"]["type"] == "stuck"

        failed_card = find_card_by_bead_id(cards, "adc-multi-failed-1")
        assert failed_card["builtin_data"]["type"] == "failed"

        await store.close()
