"""
Utterance table verification infrastructure tests (bead adc-3topdl).

This test file provides infrastructure for verifying utterance table state:
1. Utterance record creation and persistence
2. Utterance field validation and constraints
3. Utterance foreign key relationships
4. Utterance table state verification

The infrastructure includes:
- Helper functions for utterance table operations
- Database connection utilities
- Test fixtures for utterance table testing
- Verification functions for utterance integrity

This is infrastructure setup only - no test logic yet.
"""

import asyncio
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiosqlite
import pytest

from src.session.store import SessionStore


# =============================================================================
# Utterance table verification helpers
# =============================================================================


async def get_utterance_count(db_path: str | Path) -> int:
    """Get the total number of utterances in the database."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_utterance_by_id(db_path: str | Path, utterance_id: str) -> Optional[dict]:
    """Retrieve an utterance record by its ID.

    Returns None if not found, otherwise returns a dict with all fields.
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, session_id, raw_text, created_at, router_timing_breakdown "
            "FROM utterances WHERE id = ?",
            (utterance_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            return None


async def get_utterances_by_session(db_path: str | Path, session_id: str) -> list[dict]:
    """Retrieve all utterances for a specific session.

    Returns a list of dicts, each containing all utterance fields.
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, session_id, raw_text, created_at, router_timing_breakdown "
            "FROM utterances WHERE session_id = ? "
            "ORDER BY created_at ASC",
            (session_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]


async def verify_utterance_fields(
    db_path: str | Path,
    utterance_id: str,
    expected_session_id: str,
    expected_raw_text: str
) -> bool:
    """Verify that an utterance record has the expected field values.

    Returns True if all fields match, False otherwise.
    """
    utterance = await get_utterance_by_id(db_path, utterance_id)
    if not utterance:
        return False

    return (
        utterance["session_id"] == expected_session_id and
        utterance["raw_text"] == expected_raw_text and
        utterance["id"] == utterance_id and
        utterance["created_at"] is not None
    )


async def verify_utterance_session_relationship(
    db_path: str | Path,
    utterance_id: str
) -> bool:
    """Verify that an utterance's session_id references a valid session.

    Returns True if the foreign key relationship is valid, False otherwise.
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        # Get utterance's session_id
        async with db.execute(
            "SELECT session_id FROM utterances WHERE id = ?",
            (utterance_id,)
        ) as cur:
            utterance_row = await cur.fetchone()
            if not utterance_row:
                return False
            session_id = utterance_row[0]

        # Verify session exists
        async with db.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,)
        ) as cur:
            session_row = await cur.fetchone()
            return session_row is not None


async def verify_utterance_uniqueness(
    db_path: str | Path,
    utterance_id: str
) -> bool:
    """Verify that an utterance ID is unique (only one record exists).

    Returns True if exactly one record exists with this ID, False otherwise.
    """
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM utterances WHERE id = ?",
            (utterance_id,)
        ) as cur:
            row = await cur.fetchone()
            count = row[0] if row else 0
            return count == 1


async def create_test_utterance(
    store: SessionStore,
    session_id: str,
    raw_text: str,
    utterance_id: Optional[str] = None
) -> str:
    """Create a test utterance with optional custom ID.

    Returns the utterance_id of the created record.
    """
    if utterance_id is None:
        utterance_id = str(uuid4())

    await store.create_utterance(
        session_id=session_id,
        raw_text=raw_text,
        utterance_id=utterance_id
    )
    return utterance_id


async def delete_all_utterances_for_session(
    db_path: str | Path,
    session_id: str
) -> int:
    """Delete all utterances for a specific session.

    Returns the number of utterances deleted.
    """
    async with aiosqlite.connect(db_path) as db:
        # First count
        async with db.execute(
            "SELECT COUNT(*) FROM utterances WHERE session_id = ?",
            (session_id,)
        ) as cur:
            row = await cur.fetchone()
            count = row[0] if row else 0

        # Then delete
        await db.execute(
            "DELETE FROM utterances WHERE session_id = ?",
            (session_id,)
        )
        await db.commit()

        return count


# =============================================================================
# Test fixtures
# =============================================================================


@pytest.fixture
async def utterance_verification_store(test_db_store: SessionStore) -> SessionStore:
    """
    Provide a SessionStore instance for utterance table verification.

    This fixture wraps the standard test_db_store and ensures
    the utterances table is in a clean state for testing.
    """
    # Verify the table exists and is empty
    count = await get_utterance_count(test_db_store.db_path)
    assert count == 0, f"utterances table should be empty, but has {count} records"

    return test_db_store


@pytest.fixture
def sample_utterance_texts() -> list[str]:
    """
    Provide a list of sample utterance texts for testing.

    Includes various edge cases:
    - Empty string
    - Very short utterance
    - Normal utterance
    - Utterance with special characters
    - Very long utterance
    """
    return [
        "",  # Empty string
        "Hi",  # Very short
        "What's the status of the pbx-web deployment?",  # Normal
        "Test with special chars: émojis 🎉, unicode ™, quotes \"'",  # Special chars
        "a" * 10000,  # Very long (10k characters)
    ]


# =============================================================================
# Test infrastructure class
# =============================================================================


class TestUtteranceTableInfrastructure:
    """
    Infrastructure test class for utterance table verification.

    This class provides the basic structure for utterance table tests.
    Individual test methods will be added to verify specific aspects
    of utterance table behavior.

    Current tests verify:
    - Helper function availability and basic operation
    - Fixture functionality
    - Database connection establishment
    """

    @pytest.mark.asyncio
    async def test_helper_functions_exist(self) -> None:
        """Verify that all helper functions are importable and callable."""
        # Test that helper functions can be called
        assert callable(get_utterance_count)
        assert callable(get_utterance_by_id)
        assert callable(get_utterances_by_session)
        assert callable(verify_utterance_fields)
        assert callable(verify_utterance_session_relationship)
        assert callable(verify_utterance_uniqueness)
        assert callable(create_test_utterance)
        assert callable(delete_all_utterances_for_session)

    @pytest.mark.asyncio
    async def test_fixture_provides_store(self, utterance_verification_store: SessionStore) -> None:
        """Verify that the utterance_verification_store fixture provides a valid SessionStore."""
        assert utterance_verification_store is not None
        assert isinstance(utterance_verification_store, SessionStore)
        assert utterance_verification_store.db_path is not None

    @pytest.mark.asyncio
    async def test_sample_utterance_texts_fixture(self, sample_utterance_texts: list[str]) -> None:
        """Verify that the sample_utterance_texts fixture provides expected test data."""
        assert isinstance(sample_utterance_texts, list)
        assert len(sample_utterance_texts) == 5
        assert sample_utterance_texts[0] == ""  # Empty string
        assert sample_utterance_texts[1] == "Hi"  # Very short
        assert len(sample_utterance_texts[4]) == 10000  # Very long


# =============================================================================
# Utterance table cleanup verification tests (bead adc-290sq4)
# =============================================================================


class TestUtteranceTableCleanupVerification:
    """
    Utterance table cleanup verification tests (bead adc-290sq4).

    These tests verify that:
    1. Utterance table is empty after session deletion cleanup
    2. No orphaned utterance records exist after cleanup
    3. All utterance-related data is cleaned (intents, dispatch timings, etc.)
    4. Test passes when run once with pytest

    This complements the existing utterance infrastructure tests by testing the
    production cleanup path (delete_session) instead of manual SQL deletion.
    """

    @pytest.mark.asyncio
    async def test_utterance_table_cleanup_via_session_deletion(self, utterance_verification_store: SessionStore) -> None:
        """Verify utterance table cleanup when session is deleted via delete_session.

        This test verifies the production cleanup path (bead adc-290sq4):
        1. Utterances are created and associated with a session
        2. Session is deleted via delete_session (production cleanup path)
        3. Utterance table is empty after cleanup
        4. No orphaned utterance records remain
        5. All utterance metadata is cleaned (intents, etc.)

        This differs from test_utterance_table_idempotent_cleanup in test_database_state_reset.py
        which uses manual SQL DELETE, whereas this test uses the actual SessionStore cleanup method.
        """
        # Step 1: Create a session and multiple utterances
        session_id = await utterance_verification_store.create_session()

        utterance_id_1 = await create_test_utterance(
            utterance_verification_store,
            session_id,
            "Test utterance 1: What's the deployment status?"
        )

        utterance_id_2 = await create_test_utterance(
            utterance_verification_store,
            session_id,
            "Test utterance 2: Check the logs for errors"
        )

        utterance_id_3 = await create_test_utterance(
            utterance_verification_store,
            session_id,
            "Test utterance 3: Show me the recent commits"
        )

        # Step 2: Verify utterances exist before cleanup
        initial_count = await get_utterance_count(utterance_verification_store.db_path)
        assert initial_count == 3, (
            f"Expected exactly 3 utterances before cleanup, but found {initial_count}"
        )

        # Verify specific utterance IDs exist
        utterance_1 = await get_utterance_by_id(utterance_verification_store.db_path, utterance_id_1)
        utterance_2 = await get_utterance_by_id(utterance_verification_store.db_path, utterance_id_2)
        utterance_3 = await get_utterance_by_id(utterance_verification_store.db_path, utterance_id_3)

        assert utterance_1 is not None, "Utterance 1 should exist"
        assert utterance_2 is not None, "Utterance 2 should exist"
        assert utterance_3 is not None, "Utterance 3 should exist"

        # Step 3: Delete session via production cleanup path (delete_session)
        # This should cascade-delete all utterances for this session
        result = await utterance_verification_store.delete_session(session_id)

        # Verify deletion report
        assert result["session_removed"] == 1, "Session should be removed"

        # Step 4: Verify utterance table is empty after cleanup
        final_count = await get_utterance_count(utterance_verification_store.db_path)

        assert final_count == 0, (
            f"Expected 0 utterances after session deletion, but found {final_count}. "
            f"This verifies the utterance table is completely empty after cleanup."
        )

        # Verify no orphaned utterance records exist (comprehensive check)
        async with aiosqlite.connect(utterance_verification_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id FROM utterances") as cur:
                any_utterances = await cur.fetchall()

        assert len(any_utterances) == 0, (
            f"Expected no utterance records after cleanup, but found {len(any_utterances)} records. "
            f"This verifies no orphaned utterance records remain in the database."
        )

        # Test passes when run once - utterance table cleanup is verified
        # The utterance_verification_store fixture will perform additional cleanup after this test

    @pytest.mark.asyncio
    async def test_utterance_table_empty_state_after_test_operations(self, utterance_verification_store: SessionStore) -> None:
        """Verify utterance table returns to empty state after complex test operations.

        This test verifies that after typical test operations (create, use, delete),
        the utterance table can be returned to a clean state (bead adc-290sq4 acceptance):
        1. Query all utterances from database
        2. Assert count == 0 after test operations and cleanup
        3. Verify no utterance metadata remains
        4. Use existing session store utilities (no raw SQL for cleanup)

        This test uses only SessionStore methods (no direct SQL) to match production usage.
        """
        # Create a session with utterances
        session_id = await utterance_verification_store.create_session()

        # Create multiple utterances with different text content
        await create_test_utterance(
            utterance_verification_store,
            session_id,
            "What's the status of the production cluster?"
        )

        await create_test_utterance(
            utterance_verification_store,
            session_id,
            "Check the recent Argo workflow runs"
        )

        await create_test_utterance(
            utterance_verification_store,
            session_id,
            "Show me the deployment logs for pbx-web"
        )

        # Verify utterances exist using helper functions
        session_utterances = await get_utterances_by_session(
            utterance_verification_store.db_path,
            session_id
        )
        assert len(session_utterances) == 3, "Should have exactly 3 utterances"

        # Clean up via session deletion (production cleanup path)
        await utterance_verification_store.delete_session(session_id)

        # Query all utterances from database (using helper for verification)
        final_count = await get_utterance_count(utterance_verification_store.db_path)

        assert final_count == 0, (
            f"Expected 0 utterances after cleanup, but found {final_count}. "
            f"This verifies the utterance table cleanup via delete_session."
        )

        # Final verification: all utterances are gone
        async with aiosqlite.connect(utterance_verification_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
                total_count = (await cur.fetchone())[0]

        assert total_count == 0, (
            f"Expected 0 utterances (all sessions) after full cleanup, but found {total_count}. "
            f"This verifies complete utterance table cleanup."
        )

    @pytest.mark.asyncio
    async def test_no_orphaned_utterance_metadata_after_cleanup(self, utterance_verification_store: SessionStore) -> None:
        """Verify no orphaned utterance metadata remains after session deletion.

        This test specifically checks that all utterance-related data is cleaned up,
        not just the main utterance records (bead adc-290sq4 scope):
        1. Intent records linked to utterances
        2. Dispatch timings for intents
        3. Router timing breakdown in utterances

        Uses existing session store utilities for cleanup.
        """
        # Create a session with a complete data tree
        session_id = await utterance_verification_store.create_session()

        # Create utterance
        utterance_id = await create_test_utterance(
            utterance_verification_store,
            session_id,
            "Test utterance for metadata cleanup"
        )

        # Create intent linked to utterance
        intent_id = await utterance_verification_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test-project",
            intent_type="status",
            topic_id=None
        )

        # Update utterance with router timing breakdown (testing metadata cleanup)
        timing_breakdown = {
            "prompt_construction_ms": 10,
            "proxy_call_ms": 100,
            "proxy_network_ms": 20,
            "proxy_inference_ms": 80,
            "json_parse_ms": 5,
            "process_ms": 15,
            "total_ms": 150,
            "intents_count": 1,
            "cached": False
        }
        await utterance_verification_store.update_utterance_router_timing(
            utterance_id=utterance_id,
            timing_breakdown=timing_breakdown
        )

        # Verify all data exists before cleanup
        async with aiosqlite.connect(utterance_verification_store.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Check utterance exists
            utterance = await get_utterance_by_id(utterance_verification_store.db_path, utterance_id)
            assert utterance is not None, "Utterance should exist"

            # Check intent exists
            async with db.execute(
                "SELECT COUNT(*) FROM intents WHERE utterance_id = ?",
                (utterance_id,)
            ) as cur:
                intent_count = (await cur.fetchone())[0]
            assert intent_count == 1, "Intent should be linked to utterance"

            # Check router timing breakdown exists
            async with db.execute(
                "SELECT router_timing_breakdown FROM utterances WHERE id = ?",
                (utterance_id,)
            ) as cur:
                timing_row = await cur.fetchone()
                assert timing_row is not None, "Router timing breakdown should exist"

        # Delete session (should cascade-delete all related data)
        await utterance_verification_store.delete_session(session_id)

        # Verify no orphaned utterance metadata remains
        async with aiosqlite.connect(utterance_verification_store.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Check utterance is cleaned
            final_utterance = await get_utterance_by_id(utterance_verification_store.db_path, utterance_id)
            assert final_utterance is None, (
                "Utterance should be deleted after session cleanup"
            )

            # Check intents linked to utterance are cleaned
            async with db.execute(
                "SELECT COUNT(*) FROM intents WHERE utterance_id = ?",
                (utterance_id,)
            ) as cur:
                intent_count = (await cur.fetchone())[0]

            assert intent_count == 0, (
                f"Expected 0 intents for deleted utterance after cleanup, but found {intent_count}. "
                f"This verifies intent-utterance relationships are cleaned."
            )

            # Check no utterance records exist with router timing breakdown
            async with db.execute(
                "SELECT COUNT(*) FROM utterances WHERE router_timing_breakdown IS NOT NULL"
            ) as cur:
                timing_count = (await cur.fetchone())[0]

            assert timing_count == 0, (
                f"Expected 0 utterances with timing breakdown after cleanup, but found {timing_count}. "
                f"This verifies all utterance metadata is cleaned."
            )

        # Test passes - no orphaned utterance metadata remains

    @pytest.mark.asyncio
    async def test_utterance_foreign_key_cleanup(self, utterance_verification_store: SessionStore) -> None:
        """Verify utterance foreign keys are properly cleaned when sessions are deleted.

        This test verifies that utterance foreign key relationships are maintained
        and cleaned up correctly (bead adc-290sq4 scope):
        1. Utterances reference valid sessions (FK integrity)
        2. When session is deleted, utterances are cascade-deleted
        3. No orphaned utterances with invalid session_id remain

        This ensures referential integrity is maintained during cleanup operations.
        """
        # Create two sessions
        session_id_1 = await utterance_verification_store.create_session()
        session_id_2 = await utterance_verification_store.create_session()

        # Create utterances for both sessions
        utterance_1_id = await create_test_utterance(
            utterance_verification_store,
            session_id_1,
            "Session 1 utterance"
        )

        utterance_2_id = await create_test_utterance(
            utterance_verification_store,
            session_id_2,
            "Session 2 utterance"
        )

        # Verify foreign key relationships are valid before cleanup
        assert await verify_utterance_session_relationship(
            utterance_verification_store.db_path,
            utterance_1_id
        ), "Utterance 1 should have valid FK to session"

        assert await verify_utterance_session_relationship(
            utterance_verification_store.db_path,
            utterance_2_id
        ), "Utterance 2 should have valid FK to session"

        # Delete only session 1
        await utterance_verification_store.delete_session(session_id_1)

        # Verify session 1 utterances are cleaned
        utterance_1_after = await get_utterance_by_id(
            utterance_verification_store.db_path,
            utterance_1_id
        )
        assert utterance_1_after is None, (
            "Utterance 1 should be deleted when session 1 is deleted"
        )

        # Verify session 2 utterances still exist (FK integrity maintained)
        utterance_2_after = await get_utterance_by_id(
            utterance_verification_store.db_path,
            utterance_2_id
        )
        assert utterance_2_after is not None, (
            "Utterance 2 should still exist (session 2 not deleted)"
        )

        # Verify session 2 utterance still has valid FK
        assert await verify_utterance_session_relationship(
            utterance_verification_store.db_path,
            utterance_2_id
        ), "Utterance 2 should still have valid FK to session 2"

        # Clean up session 2
        await utterance_verification_store.delete_session(session_id_2)

        # Verify all utterances are now cleaned
        final_count = await get_utterance_count(utterance_verification_store.db_path)
        assert final_count == 0, (
            f"Expected 0 utterances after all sessions deleted, but found {final_count}"
        )

        # Test passes - foreign key cleanup is verified
