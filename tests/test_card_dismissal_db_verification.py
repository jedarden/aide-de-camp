"""
Database verification helpers tests for card dismissal (bead adc-4rxxx).

Acceptance criteria:
- Test that dismissed card is removed from session store
- Test that other cards remain after dismissal
- Test that dismissal state survives session reload
- Add database verification helpers
- All persistence tests pass

This test suite validates the database verification helpers in
card_dismissal_helpers.py work correctly for verifying card
dismissal persistence.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from tests.card_dismissal_helpers import (
    create_test_session,
    create_test_session_with_topic,
    create_stuck_card,
    create_failed_card,
    verify_result_exists_in_db,
    verify_result_count_for_intent,
    verify_result_deleted_from_db,
    get_all_results_for_session,
    verify_database_integrity_after_dismissal,
    verify_dismissal_persistence_across_reopen,
    count_results_by_bead_id,
    verify_cards_remain_after_dismissal,
)
from src.session.store import SessionStore


# =============================================================================
# Result Existence Verification Tests
# =============================================================================

@pytest.mark.asyncio
class TestVerifyResultExistsInDb:
    """Test verify_result_exists_in_db helper."""

    async def test_verifies_existing_result(self, tmp_path):
        """Helper returns True for existing result."""
        store, session_id = await create_test_session(tmp_path=tmp_path)

        try:
            # Create a stuck card with result
            card_data = await create_stuck_card(store, session_id)

            # Create the actual result
            result_id = await store.create_result(
                intent_id=card_data["intent_id"],
                topic_id=card_data["topic_id"],
                session_id=session_id,
                summary="Test stuck card",
                data={
                    "bead_id": card_data["bead_id"],
                    "stuck_reason": card_data["stuck_reason"],
                    "refusal_count": card_data["refusal_count"],
                    "message": card_data["message"],
                },
                urgency="high",
            )

            # Verify result exists
            exists = await verify_result_exists_in_db(store, result_id)
            assert exists is True, "Result should exist in database"

        finally:
            await store.close()

    async def test_returns_false_for_deleted_result(self, tmp_path):
        """Helper returns False for deleted result."""
        store, session_id = await create_test_session(tmp_path=tmp_path)

        try:
            # Create and store result
            card_data = await create_stuck_card(store, session_id)
            result_id = await store.create_result(
                intent_id=card_data["intent_id"],
                topic_id=card_data["topic_id"],
                session_id=session_id,
                summary="Test result",
                data={"bead_id": card_data["bead_id"]},
                urgency="high",
            )

            # Delete the result
            await store.delete_result(result_id, session_id)

            # Verify result no longer exists
            exists = await verify_result_exists_in_db(store, result_id)
            assert exists is False, "Deleted result should not exist"

        finally:
            await store.close()


# =============================================================================
# Result Count Verification Tests
# =============================================================================

@pytest.mark.asyncio
class TestVerifyResultCountForIntent:
    """Test verify_result_count_for_intent helper."""

    async def test_verifies_correct_count(self, tmp_path):
        """Helper correctly counts results for an intent."""
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path
        )

        try:
            # Create intent
            card_data = await create_stuck_card(
                store, session_id, topic_id=topic_id
            )

            # Create multiple results
            await store.create_result(
                intent_id=card_data["intent_id"],
                topic_id=topic_id,
                session_id=session_id,
                summary="Result 1",
                data={"bead_id": card_data["bead_id"]},
                urgency="high",
            )
            await store.create_result(
                intent_id=card_data["intent_id"],
                topic_id=topic_id,
                session_id=session_id,
                summary="Result 2",
                data={"bead_id": card_data["bead_id"]},
                urgency="high",
            )

            # Verify count
            assert await verify_result_count_for_intent(
                store, card_data["intent_id"], 2
            ), "Should count 2 results"

            # Delete one and verify new count
            results = await store.get_results_for_intent(card_data["intent_id"])
            await store.delete_result(results[0]["id"], session_id)

            assert await verify_result_count_for_intent(
                store, card_data["intent_id"], 1
            ), "Should count 1 result after deletion"

        finally:
            await store.close()


# =============================================================================
# Result Deletion Verification Tests
# =============================================================================

@pytest.mark.asyncio
class TestVerifyResultDeletedFromDb:
    """Test verify_result_deleted_from_db helper."""

    async def test_verifies_successful_deletion(self, tmp_path):
        """Helper verifies result was deleted with session isolation."""
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path
        )

        try:
            card_data = await create_stuck_card(
                store, session_id, topic_id=topic_id
            )

            result_id = await store.create_result(
                intent_id=card_data["intent_id"],
                topic_id=topic_id,
                session_id=session_id,
                summary="Test result",
                data={"bead_id": card_data["bead_id"]},
                urgency="high",
            )

            # Delete the result
            await store.delete_result(result_id, session_id)

            # Verify deletion
            verification = await verify_result_deleted_from_db(
                store, result_id, session_id
            )

            assert verification["result_deleted"] is True
            assert verification["session_isolated"] is True
            assert verification["verification_passed"] is True

        finally:
            await store.close()


# =============================================================================
# Database Integrity Verification Tests
# =============================================================================

@pytest.mark.asyncio
class TestVerifyDatabaseIntegrityAfterDismissal:
    """Test verify_database_integrity_after_dismissal helper."""

    async def test_passes_all_checks_after_dismissal(self, tmp_path):
        """Helper verifies database integrity after card dismissal."""
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path
        )

        try:
            # Create multiple cards
            cards = []
            for i in range(3):
                card_data = await create_stuck_card(
                    store,
                    session_id,
                    topic_id=topic_id,
                    bead_id=f"adc-stuck-{i}",
                )
                result_id = await store.create_result(
                    intent_id=card_data["intent_id"],
                    topic_id=topic_id,
                    session_id=session_id,
                    summary=f"Card {i}",
                    data={"bead_id": card_data["bead_id"]},
                    urgency="high",
                )
                cards.append(result_id)

            # Dismiss one card
            await store.delete_result(cards[1], session_id)

            # Verify integrity (expect 2 results remaining)
            integrity = await verify_database_integrity_after_dismissal(
                store, session_id, expected_result_count=2
            )

            assert integrity["all_checks_passed"] is True
            assert integrity["checks"]["no_orphaned_results"] is True
            assert integrity["checks"]["result_count_match"] is True
            assert integrity["checks"]["session_valid"] is True
            assert integrity["checks"]["topics_valid"] is True

        finally:
            await store.close()


# =============================================================================
# Dismissal Persistence Across Reopen Tests
# =============================================================================

@pytest.mark.asyncio
class TestVerifyDismissalPersistenceAcrossReopen:
    """Test verify_dismissal_persistence_across_reopen helper."""

    async def test_verifies_dismissal_persists_across_db_reopen(self, tmp_path):
        """Helper verifies dismissal state survives database reopen."""
        db_path = tmp_path / "test_persistence.db"

        # Create session and card
        store1 = SessionStore(db_path)
        await store1.initialize()

        session_id = await store1.create_session()
        topic_id, _ = await store1.find_or_create_topic(
            label="Persistence Test",
            session_id=session_id,
            topic_type="project",
        )

        card_data = await create_stuck_card(
            store1, session_id, topic_id=topic_id, bead_id="adc-persist-test"
        )

        result_id = await store1.create_result(
            intent_id=card_data["intent_id"],
            topic_id=topic_id,
            session_id=session_id,
            summary="Test card",
            data={"bead_id": card_data["bead_id"]},
            urgency="high",
        )

        # Dismiss the card
        await store1.delete_result(result_id, session_id)
        await store1.close()

        # Verify dismissal persists across reopen
        persistence = await verify_dismissal_persistence_across_reopen(
            db_path, session_id, result_id=result_id, intent_id=card_data["intent_id"]
        )

        assert persistence["session_exists"] is True
        assert persistence["result_deleted"] is True
        assert persistence["intent_result_count"] == 0
        assert persistence["dismissal_persisted"] is True


# =============================================================================
# Count Results by Bead ID Tests
# =============================================================================

@pytest.mark.asyncio
class TestCountResultsByBeadId:
    """Test count_results_by_bead_id helper."""

    async def test_counts_results_for_specific_bead(self, tmp_path):
        """Helper counts results for a specific bead_id."""
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path
        )

        try:
            # Create cards for different beads
            bead_1_id = "adc-stuck-1"
            bead_2_id = "adc-stuck-2"

            card_1 = await create_stuck_card(
                store, session_id, topic_id=topic_id, bead_id=bead_1_id
            )
            card_2 = await create_stuck_card(
                store, session_id, topic_id=topic_id, bead_id=bead_2_id
            )

            # Create 2 results for bead_1, 1 result for bead_2
            await store.create_result(
                intent_id=card_1["intent_id"],
                topic_id=topic_id,
                session_id=session_id,
                summary="Card 1a",
                data={"bead_id": bead_1_id},
                urgency="high",
            )
            await store.create_result(
                intent_id=card_1["intent_id"],
                topic_id=topic_id,
                session_id=session_id,
                summary="Card 1b",
                data={"bead_id": bead_1_id},
                urgency="high",
            )
            await store.create_result(
                intent_id=card_2["intent_id"],
                topic_id=topic_id,
                session_id=session_id,
                summary="Card 2",
                data={"bead_id": bead_2_id},
                urgency="high",
            )

            # Verify counts
            count_1 = await count_results_by_bead_id(store, session_id, bead_1_id)
            count_2 = await count_results_by_bead_id(store, session_id, bead_2_id)

            assert count_1 == 2, f"Expected 2 results for {bead_1_id}, got {count_1}"
            assert count_2 == 1, f"Expected 1 result for {bead_2_id}, got {count_2}"

        finally:
            await store.close()


# =============================================================================
# Verify Cards Remain After Dismissal Tests
# =============================================================================

@pytest.mark.asyncio
class TestVerifyCardsRemainAfterDismissal:
    """Test verify_cards_remain_after_dismissal helper."""

    async def test_verifies_selective_dismissal(self, tmp_path):
        """Helper verifies correct cards were dismissed and others remain."""
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path
        )

        try:
            # Create cards for 3 different beads
            bead_ids = ["adc-stuck-1", "adc-stuck-2", "adc-stuck-3"]
            cards = []

            for bead_id in bead_ids:
                card_data = await create_stuck_card(
                    store, session_id, topic_id=topic_id, bead_id=bead_id
                )
                await store.create_result(
                    intent_id=card_data["intent_id"],
                    topic_id=topic_id,
                    session_id=session_id,
                    summary=f"Card {bead_id}",
                    data={"bead_id": bead_id},
                    urgency="high",
                )
                cards.append(card_data)

            # Dismiss the second card
            result_to_dismiss = await store.get_results_for_intent(cards[1]["intent_id"])
            await store.delete_result(result_to_dismiss[0]["id"], session_id)

            # Verify selective dismissal
            verification = await verify_cards_remain_after_dismissal(
                store,
                session_id,
                dismissed_bead_ids=["adc-stuck-2"],
                remaining_bead_ids=["adc-stuck-1", "adc-stuck-3"],
            )

            assert verification["all_correct"] is True
            assert verification["dismissed_adc-stuck-2"] is True
            assert verification["remaining_adc-stuck-1"] is True
            assert verification["remaining_adc-stuck-3"] is True

        finally:
            await store.close()


# =============================================================================
# End-to-End Database Verification Tests
# =============================================================================

@pytest.mark.asyncio
class TestDatabaseVerificationE2E:
    """End-to-end tests using database verification helpers."""

    async def test_complete_dismissal_flow_with_db_verification(self, tmp_path):
        """Test complete dismissal flow with database verification at each step."""
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path, label="E2E DB Verification"
        )

        try:
            # Step 1: Create stuck card
            card_data = await create_stuck_card(
                store, session_id, topic_id=topic_id, bead_id="adc-e2e-test"
            )
            result_id = await store.create_result(
                intent_id=card_data["intent_id"],
                topic_id=topic_id,
                session_id=session_id,
                summary="E2E test card",
                data={
                    "bead_id": card_data["bead_id"],
                    "stuck_reason": "E2E test",
                    "refusal_count": 1,
                    "message": "Test card",
                },
                urgency="high",
            )

            # Verify result exists
            assert await verify_result_exists_in_db(store, result_id)
            assert await verify_result_count_for_intent(
                store, card_data["intent_id"], 1
            )

            # Step 2: Dismiss the card
            deletion_result = await store.delete_result(result_id, session_id)
            assert deletion_result["result_deleted"] == 1

            # Step 3: Verify deletion
            deletion_verification = await verify_result_deleted_from_db(
                store, result_id, session_id
            )
            assert deletion_verification["verification_passed"] is True

            # Step 4: Verify no orphaned data
            integrity = await verify_database_integrity_after_dismissal(
                store, session_id, expected_result_count=0
            )
            assert integrity["all_checks_passed"] is True

        finally:
            await store.close()

    async def test_multiple_cards_dismissal_with_verification(self, tmp_path):
        """Test dismissing multiple cards with comprehensive verification."""
        store, session_id, topic_id = await create_test_session_with_topic(
            tmp_path=tmp_path, label="Multi-Card DB Verification"
        )

        try:
            # Create 5 cards
            bead_ids = [f"adc-multi-{i}" for i in range(5)]
            card_data_list = []

            for bead_id in bead_ids:
                card_data = await create_stuck_card(
                    store, session_id, topic_id=topic_id, bead_id=bead_id
                )
                await store.create_result(
                    intent_id=card_data["intent_id"],
                    topic_id=topic_id,
                    session_id=session_id,
                    summary=f"Multi card {bead_id}",
                    data={"bead_id": bead_id},
                    urgency="high",
                )
                card_data_list.append(card_data)

            # Verify all 5 exist
            for card_data in card_data_list:
                assert await verify_result_count_for_intent(
                    store, card_data["intent_id"], 1
                )

            # Dismiss cards 1, 3, and 5
            to_dismiss = [0, 2, 4]
            dismissed_ids = []
            for idx in to_dismiss:
                results = await store.get_results_for_intent(
                    card_data_list[idx]["intent_id"]
                )
                await store.delete_result(results[0]["id"], session_id)
                dismissed_ids.append(bead_ids[idx])

            # Verify selective dismissal
            remaining_ids = [bid for i, bid in enumerate(bead_ids) if i not in to_dismiss]
            verification = await verify_cards_remain_after_dismissal(
                store, session_id, dismissed_bead_ids=dismissed_ids, remaining_bead_ids=remaining_ids
            )
            assert verification["all_correct"] is True

            # Verify database integrity
            integrity = await verify_database_integrity_after_dismissal(
                store, session_id, expected_result_count=2
            )
            assert integrity["all_checks_passed"] is True

        finally:
            await store.close()

    async def test_dismissal_persistence_with_db_reopen_verification(self, tmp_path):
        """Test that dismissal persists with full database reopen verification."""
        db_path = tmp_path / "test_reopen_persistence.db"

        # First session: create and dismiss
        store1 = SessionStore(db_path)
        await store1.initialize()

        session_id = await store1.create_session()
        topic_id, _ = await store1.find_or_create_topic(
            label="Reopen Persistence",
            session_id=session_id,
            topic_type="project"
        )

        card_data = await create_stuck_card(
            store1, session_id, topic_id=topic_id, bead_id="adc-reopen-test"
        )

        result_id = await store1.create_result(
            intent_id=card_data["intent_id"],
            topic_id=topic_id,
            session_id=session_id,
            summary="Reopen test card",
            data={"bead_id": card_data["bead_id"]},
            urgency="high",
        )

        # Verify created
        assert await verify_result_exists_in_db(store1, result_id)

        # Dismiss
        await store1.delete_result(result_id, session_id)
        await store1.close()

        # Second session: verify persistence
        persistence = await verify_dismissal_persistence_across_reopen(
            db_path, session_id, result_id=result_id, intent_id=card_data["intent_id"]
        )

        assert persistence["dismissal_persisted"] is True
        assert persistence["result_deleted"] is True
        assert persistence["intent_result_count"] == 0
