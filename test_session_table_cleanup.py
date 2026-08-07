#!/usr/bin/env .venv/bin/python
"""
Session table cleanup verification tests.

Tests verify:
1. Session table is empty after delete_session
2. No orphaned session records exist after cleanup
3. All related records (topics, results, intents, utterances, surfaces) are removed
"""

import asyncio
import tempfile
from pathlib import Path

import pytest
import aiosqlite

from src.session.store import SessionStore


@pytest.mark.asyncio
async def test_session_table_cleanup_after_delete():
    """Test that session table is empty after delete_session is called."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create a session
        session_id = await store.create_session()
        assert session_id is not None, "Session ID should be returned"

        # Verify session exists
        session = await store.get_session(session_id)
        assert session is not None, "Session should exist before deletion"

        # Create related records (surface, utterance, topic, result)
        surface_id = await store.register_surface(
            session_id=session_id,
            surface_type="canvas"
        )

        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text="test utterance"
        )

        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test-project",
            intent_type="status"
        )

        topic_id, _ = await store.find_or_create_topic(
            label="test-topic",
            session_id=session_id,
            topic_type="project",
            project_slugs=["test-project"],
            scope="session"
        )

        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="test result",
            data={"test": "data"}
        )

        # Verify all records exist before deletion
        async with aiosqlite.connect(store.db_path) as db:
            # Count sessions
            cursor = await db.execute("SELECT COUNT(*) FROM sessions")
            session_count = (await cursor.fetchone())[0]
            assert session_count == 1, "Should have 1 session before deletion"

            # Count surfaces
            cursor = await db.execute("SELECT COUNT(*) FROM surfaces")
            surface_count = (await cursor.fetchone())[0]
            assert surface_count == 1, "Should have 1 surface before deletion"

            # Count utterances
            cursor = await db.execute("SELECT COUNT(*) FROM utterances")
            utterance_count = (await cursor.fetchone())[0]
            assert utterance_count == 1, "Should have 1 utterance before deletion"

            # Count intents
            cursor = await db.execute("SELECT COUNT(*) FROM intents")
            intent_count = (await cursor.fetchone())[0]
            assert intent_count == 1, "Should have 1 intent before deletion"

            # Count topics
            cursor = await db.execute("SELECT COUNT(*) FROM topics")
            topic_count = (await cursor.fetchone())[0]
            assert topic_count == 1, "Should have 1 topic before deletion"

            # Count results
            cursor = await db.execute("SELECT COUNT(*) FROM results")
            result_count = (await cursor.fetchone())[0]
            assert result_count == 1, "Should have 1 result before deletion"

        # Delete the session
        result = await store.delete_session(session_id)
        assert result['session_removed'] == 1, "Session should be marked as removed"
        assert result['topics_removed'] == 1, "Topic should be marked as removed"

        # Verify session table is empty after deletion
        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM sessions")
            session_count_after = (await cursor.fetchone())[0]
            assert session_count_after == 0, f"Session table should be empty after deletion, but has {session_count_after} records"

            # Verify all related tables are also empty
            cursor = await db.execute("SELECT COUNT(*) FROM surfaces")
            surface_count_after = (await cursor.fetchone())[0]
            assert surface_count_after == 0, f"Surfaces table should be empty after deletion, but has {surface_count_after} records"

            cursor = await db.execute("SELECT COUNT(*) FROM utterances")
            utterance_count_after = (await cursor.fetchone())[0]
            assert utterance_count_after == 0, f"Utterances table should be empty after deletion, but has {utterance_count_after} records"

            cursor = await db.execute("SELECT COUNT(*) FROM intents")
            intent_count_after = (await cursor.fetchone())[0]
            assert intent_count_after == 0, f"Intents table should be empty after deletion, but has {intent_count_after} records"

            cursor = await db.execute("SELECT COUNT(*) FROM topics")
            topic_count_after = (await cursor.fetchone())[0]
            assert topic_count_after == 0, f"Topics table should be empty after deletion, but has {topic_count_after} records"

            cursor = await db.execute("SELECT COUNT(*) FROM results")
            result_count_after = (await cursor.fetchone())[0]
            assert result_count_after == 0, f"Results table should be empty after deletion, but has {result_count_after} records"

        await store.close()


@pytest.mark.asyncio
async def test_multiple_session_cleanup():
    """Test cleanup of multiple sessions with verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create multiple sessions
        session_ids = []
        for i in range(3):
            session_id = await store.create_session()
            session_ids.append(session_id)

            # Create some related records for each session
            surface_id = await store.register_surface(
                session_id=session_id,
                surface_type="canvas"
            )
            utterance_id = await store.create_utterance(
                session_id=session_id,
                raw_text=f"test utterance {i}"
            )

        # Verify we have 3 sessions
        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM sessions")
            session_count = (await cursor.fetchone())[0]
            assert session_count == 3, "Should have 3 sessions before deletion"

        # Delete all sessions
        for session_id in session_ids:
            await store.delete_session(session_id)

        # Verify session table is completely empty
        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM sessions")
            session_count_after = (await cursor.fetchone())[0]
            assert session_count_after == 0, f"Session table should be empty after deleting all sessions, but has {session_count_after} records"

            # Verify no orphaned records in any table
            cursor = await db.execute("SELECT COUNT(*) FROM surfaces")
            surface_count_after = (await cursor.fetchone())[0]
            assert surface_count_after == 0, "Surfaces table should have no orphaned records"

            cursor = await db.execute("SELECT COUNT(*) FROM utterances")
            utterance_count_after = (await cursor.fetchone())[0]
            assert utterance_count_after == 0, "Utterances table should have no orphaned records"

            cursor = await db.execute("SELECT COUNT(*) FROM intents")
            intent_count_after = (await cursor.fetchone())[0]
            assert intent_count_after == 0, "Intents table should have no orphaned records"

            cursor = await db.execute("SELECT COUNT(*) FROM results")
            result_count_after = (await cursor.fetchone())[0]
            assert result_count_after == 0, "Results table should have no orphaned records"

            cursor = await db.execute("SELECT COUNT(*) FROM topics")
            topic_count_after = (await cursor.fetchone())[0]
            assert topic_count_after == 0, "Topics table should have no orphaned records"

        await store.close()


@pytest.mark.asyncio
async def test_no_orphaned_records_after_partial_cleanup():
    """Test that no orphaned records exist when some sessions are deleted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = SessionStore(db_path)
        await store.initialize()

        # Create two sessions with related records
        session1_id = await store.create_session()
        session2_id = await store.create_session()

        # Add records to session 1
        await store.register_surface(session_id=session1_id, surface_type="canvas")
        utterance1_id = await store.create_utterance(
            session_id=session1_id,
            raw_text="session 1 utterance"
        )
        intent1_id = await store.create_intent(
            utterance_id=utterance1_id,
            session_id=session1_id,
            project_slug="test-project",
            intent_type="status"
        )

        # Add records to session 2
        await store.register_surface(session_id=session2_id, surface_type="telegram")
        utterance2_id = await store.create_utterance(
            session_id=session2_id,
            raw_text="session 2 utterance"
        )
        intent2_id = await store.create_intent(
            utterance_id=utterance2_id,
            session_id=session2_id,
            project_slug="test-project",
            intent_type="lookup"
        )

        # Verify both sessions exist
        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM sessions")
            session_count = (await cursor.fetchone())[0]
            assert session_count == 2, "Should have 2 sessions"

        # Delete only session 1
        await store.delete_session(session1_id)

        # Verify session 1 is gone but session 2 remains
        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM sessions")
            session_count_after = (await cursor.fetchone())[0]
            assert session_count_after == 1, "Should have 1 session remaining"

            # Verify session 1's records are gone
            cursor = await db.execute(
                "SELECT COUNT(*) FROM utterances WHERE session_id = ?",
                (session1_id,)
            )
            session1_utterances = (await cursor.fetchone())[0]
            assert session1_utterances == 0, "Session 1 utterances should be deleted"

            # Verify session 2's records still exist
            cursor = await db.execute(
                "SELECT COUNT(*) FROM utterances WHERE session_id = ?",
                (session2_id,)
            )
            session2_utterances = (await cursor.fetchone())[0]
            assert session2_utterances == 1, "Session 2 utterances should still exist"

        # Clean up session 2
        await store.delete_session(session2_id)

        # Verify completely empty
        async with aiosqlite.connect(store.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM sessions")
            final_session_count = (await cursor.fetchone())[0]
            assert final_session_count == 0, "All sessions should be deleted"

            cursor = await db.execute("SELECT COUNT(*) FROM utterances")
            final_utterance_count = (await cursor.fetchone())[0]
            assert final_utterance_count == 0, "All utterances should be deleted"

        await store.close()


if __name__ == "__main__":
    import sys
    pytest.main([__file__, "-v"] + sys.argv[1:])
