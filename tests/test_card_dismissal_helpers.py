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
    verify_result_exists_in_db,
    verify_result_count_for_intent,
    verify_result_deleted_from_db,
    get_all_results_for_session,
    verify_database_integrity_after_dismissal,
    verify_dismissal_persistence_across_reopen,
    count_results_by_bead_id,
    verify_cards_remain_after_dismissal,
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


class TestDatabaseVerificationHelpers:
    """Test database verification helper functions."""

    @pytest.mark.asyncio
    async def test_verify_result_exists_in_db(self, tmp_path):
        """Test verifying a result exists in the database."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        # Create a stuck card result
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test result exists",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-result-exists-test",
            topic_id=topic_id,
        )

        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Test result",
            data={"bead_id": "adc-result-exists-test", "stuck_reason": "Test"},
            urgency="high",
        )

        # Verify result exists
        exists = await verify_result_exists_in_db(store, result_id)
        assert exists is True

        # Delete result
        await store.delete_result(result_id, session_id)

        # Verify result no longer exists
        exists_after = await verify_result_exists_in_db(store, result_id)
        assert exists_after is False

        await store.close()

    @pytest.mark.asyncio
    async def test_verify_result_count_for_intent(self, tmp_path):
        """Test verifying result count for an intent."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test count",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-count-test",
            topic_id=topic_id,
        )

        # Initially 0 results
        assert await verify_result_count_for_intent(store, intent_id, 0) is True

        # Create first result
        await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Result 1",
            data={"bead_id": "adc-count-test"},
            urgency="normal",
        )

        # Now 1 result
        assert await verify_result_count_for_intent(store, intent_id, 1) is True

        # Create second result
        await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Result 2",
            data={"bead_id": "adc-count-test"},
            urgency="normal",
        )

        # Now 2 results
        assert await verify_result_count_for_intent(store, intent_id, 2) is True
        assert await verify_result_count_for_intent(store, intent_id, 1) is False

        await store.close()

    @pytest.mark.asyncio
    async def test_verify_result_deleted_from_db(self, tmp_path):
        """Test verifying a result was properly deleted from database."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test deletion",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-delete-test",
            topic_id=topic_id,
        )

        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Test deletion",
            data={"bead_id": "adc-delete-test"},
            urgency="high",
        )

        # Delete the result
        await store.delete_result(result_id, session_id)

        # Verify deletion
        verification = await verify_result_deleted_from_db(store, result_id, session_id)
        assert verification["result_deleted"] is True
        assert verification["session_isolated"] is True
        assert verification["verification_passed"] is True

        await store.close()

    @pytest.mark.asyncio
    async def test_get_all_results_for_session(self, tmp_path):
        """Test getting all results for a session."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        # Create multiple intents and results
        for i in range(3):
            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text=f"test result {i}",
            )

            intent_id = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref=f"adc-results-{i}",
                topic_id=topic_id,
            )

            await store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Result {i}",
                data={"bead_id": f"adc-results-{i}"},
                urgency="normal",
            )

        # Get all results
        results = await get_all_results_for_session(store, session_id)
        assert len(results) == 3
        assert all(r.get("session_id") == session_id for r in results)

        await store.close()

    @pytest.mark.asyncio
    async def test_verify_database_integrity_after_dismissal(self, tmp_path):
        """Test database integrity verification after dismissal."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test integrity",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-integrity-test",
            topic_id=topic_id,
        )

        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Test integrity",
            data={"bead_id": "adc-integrity-test"},
            urgency="high",
        )

        # Delete the result
        await store.delete_result(result_id, session_id)

        # Verify integrity
        integrity = await verify_database_integrity_after_dismissal(
            store, session_id, expected_result_count=0
        )
        assert integrity["all_checks_passed"] is True
        assert integrity["checks"]["no_orphaned_results"] is True
        assert integrity["checks"]["result_count_match"] is True
        assert integrity["checks"]["session_valid"] is True
        assert integrity["checks"]["topics_valid"] is True

        await store.close()

    @pytest.mark.asyncio
    async def test_verify_dismissal_persistence_across_reopen(self, tmp_path):
        """Test that dismissal persists across database reopen."""
        db_path = tmp_path / "test_session.db"
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test reopen persistence",
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="adc",
            intent_type="task-profile",
            bead_ref="adc-reopen-test",
            topic_id=topic_id,
        )

        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Test reopen persistence",
            data={"bead_id": "adc-reopen-test"},
            urgency="high",
        )

        # Delete the result
        await store.delete_result(result_id, session_id)
        await store.close()

        # Verify persistence across reopen
        persistence = await verify_dismissal_persistence_across_reopen(
            db_path, session_id, result_id=result_id, intent_id=intent_id
        )
        assert persistence["session_exists"] is True
        assert persistence["result_deleted"] is True
        assert persistence["dismissal_persisted"] is True
        assert persistence["intent_result_count"] == 0

    @pytest.mark.asyncio
    async def test_count_results_by_bead_id(self, tmp_path):
        """Test counting results by bead_id."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        # Create results with different bead_ids
        for i in range(3):
            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text=f"test bead {i}",
            )

            intent_id = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref="adc-bead-count-test",
                topic_id=topic_id,
            )

            await store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Bead count test {i}",
                data={"bead_id": "adc-bead-count-test"},
                urgency="normal",
            )

        count = await count_results_by_bead_id(store, session_id, "adc-bead-count-test")
        assert count == 3

        await store.close()

    @pytest.mark.asyncio
    async def test_verify_cards_remain_after_dismissal(self, tmp_path):
        """Test verifying selective dismissal - some cards gone, others remain."""
        store, session_id, topic_id = await create_test_session_with_topic(tmp_path=tmp_path)

        cards_to_dismiss = ["adc-dismiss-1", "adc-dismiss-2"]
        cards_to_remain = ["adc-remain-1", "adc-remain-2"]

        # Create all cards
        for bead_id in cards_to_dismiss + cards_to_remain:
            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text=f"test {bead_id}",
            )

            intent_id = await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref=bead_id,
                topic_id=topic_id,
            )

            result_id = await store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Card {bead_id}",
                data={"bead_id": bead_id},
                urgency="high",
            )

            # Dismiss the cards that should be dismissed
            if bead_id in cards_to_dismiss:
                await store.delete_result(result_id, session_id)

        # Verify selective dismissal
        verification = await verify_cards_remain_after_dismissal(
            store, session_id, cards_to_dismiss, cards_to_remain
        )
        assert verification["all_correct"] is True
        assert verification["dismissed_adc-dismiss-1"] is True
        assert verification["dismissed_adc-dismiss-2"] is True
        assert verification["remaining_adc-remain-1"] is True
        assert verification["remaining_adc-remain-2"] is True

        await store.close()


class TestDatabaseVerificationIntegration:
    """Integration tests for database verification helpers working together."""

    @pytest.mark.asyncio
    async def test_complete_persistence_verification_workflow(self, tmp_path):
        """Test complete workflow: create, dismiss, verify persistence, reopen, verify again."""
        from src.session.store import SessionStore

        db_path = tmp_path / "test_persistence_workflow.db"

        # First session: create and dismiss
        store1 = SessionStore(db_path)
        await store1.initialize()

        session_id = await store1.create_session()
        topic_id, _ = await store1.find_or_create_topic(
            label="Persistence Workflow Test",
            session_id=session_id,
            topic_type="project"
        )

        # Create multiple cards
        card_ids = []
        for i in range(1, 4):
            utterance_id = await store1.create_utterance(
                session_id=session_id,
                raw_text=f"card {i}",
            )

            intent_id = await store1.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug="adc",
                intent_type="task-profile",
                bead_ref=f"adc-workflow-{i}",
                topic_id=topic_id,
            )

            result_id = await store1.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Card {i}",
                data={"bead_id": f"adc-workflow-{i}"},
                urgency="high",
            )
            card_ids.append((f"adc-workflow-{i}", result_id, intent_id))

        # Verify all cards exist
        all_results = await get_all_results_for_session(store1, session_id)
        assert len(all_results) == 3

        # Dismiss card 2
        await store1.delete_result(card_ids[1][1], session_id)

        # Verify card 2 is gone, others remain
        verification = await verify_cards_remain_after_dismissal(
            store1, session_id,
            dismissed_bead_ids=[card_ids[1][0]],
            remaining_bead_ids=[card_ids[0][0], card_ids[2][0]]
        )
        assert verification["all_correct"]

        # Verify database integrity
        integrity = await verify_database_integrity_after_dismissal(store1, session_id)
        assert integrity["all_checks_passed"]

        await store1.close()

        # Second session: verify persistence
        persistence = await verify_dismissal_persistence_across_reopen(
            db_path, session_id,
            result_id=card_ids[1][1],
            intent_id=card_ids[1][2]
        )
        assert persistence["dismissal_persisted"], f"Persistence check failed: {persistence}"

        await store1.close()
