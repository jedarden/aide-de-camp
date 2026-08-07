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
