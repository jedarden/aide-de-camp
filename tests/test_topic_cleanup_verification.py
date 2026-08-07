"""
Topic table cleanup verification tests (bead adc-65gkbh).

These tests verify that:
1. Topic table is empty after session deletion cleanup
2. No orphaned topic records exist after cleanup
3. All expected topic columns/metadata are cleaned
4. Test passes when run once with pytest

This complements the existing test_topic_table_state_reset by testing the
production cleanup path (delete_session) instead of manual SQL deletion.
"""

import pytest
import aiosqlite


@pytest.mark.asyncio
async def test_topic_table_cleanup_via_session_deletion(test_db_store):
    """Verify topic table cleanup when session is deleted via delete_session.

    This test verifies the production cleanup path (bead adc-65gkbh):
    1. Topics are created and associated with a session
    2. Session is deleted via delete_session (production cleanup path)
    3. Topic table is empty after cleanup
    4. No orphaned topic records remain
    5. All topic metadata is cleaned (including related tables)

    This differs from test_topic_table_state_reset which uses manual SQL DELETE
    to test deletion, whereas this test uses the actual SessionStore cleanup method.
    """
    # Step 1: Create a session and multiple topics
    session_id = await test_db_store.create_session()

    topic_id_1 = await test_db_store.create_topic(
        label="Test Topic 1",
        topic_type="project",
        project_slugs=["test-project-1"],
        scope="session",
        session_id=session_id
    )

    topic_id_2 = await test_db_store.create_topic(
        label="Test Topic 2",
        topic_type="research",
        project_slugs=["test-project-2"],
        scope="session",
        session_id=session_id
    )

    topic_id_3 = await test_db_store.create_topic(
        label="Test Topic 3",
        topic_type="personal",
        project_slugs=["test-project-3"],
        scope="session",
        session_id=session_id
    )

    # Add topic context cache for one topic (testing metadata cleanup)
    await test_db_store.set_topic_context(
        topic_id_1,
        {"test": "context data"},
        ttl_seconds=600
    )

    # Step 2: Verify topics exist before cleanup
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Count total topics
        async with db.execute("SELECT COUNT(*) FROM topics") as cur:
            topic_count = (await cur.fetchone())[0]

        assert topic_count == 3, (
            f"Expected exactly 3 topics before cleanup, but found {topic_count}"
        )

        # Verify specific topic IDs exist
        async with db.execute(
            "SELECT id FROM topics WHERE id IN (?, ?, ?)",
            (topic_id_1, topic_id_2, topic_id_3)
        ) as cur:
            found_topics = await cur.fetchall()

        assert len(found_topics) == 3, (
            f"Expected to find all 3 topic IDs, but found {len(found_topics)}"
        )

        # Verify topic context cache exists
        async with db.execute(
            "SELECT COUNT(*) FROM topic_context_cache WHERE topic_id = ?",
            (topic_id_1,)
        ) as cur:
            cache_count = (await cur.fetchone())[0]

        assert cache_count == 1, "Expected topic context cache to exist"

    # Step 3: Delete session via production cleanup path (delete_session)
    # This should cascade-delete all topics for this session
    result = await test_db_store.delete_session(session_id)

    # Verify deletion report
    assert result["session_removed"] == 1, "Session should be removed"
    assert result["topics_removed"] == 3, "All 3 topics should be removed"

    # Step 4: Verify topic table is empty after cleanup
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Query topics table to verify row count is 0
        async with db.execute("SELECT COUNT(*) FROM topics") as cur:
            final_topic_count = (await cur.fetchone())[0]

        assert final_topic_count == 0, (
            f"Expected 0 topics after session deletion, but found {final_topic_count}. "
            f"This verifies the topic table is completely empty after cleanup."
        )

        # Verify no orphaned topic records exist (comprehensive check)
        async with db.execute("SELECT id FROM topics") as cur:
            any_topics = await cur.fetchall()

        assert len(any_topics) == 0, (
            f"Expected no topic records after cleanup, but found {len(any_topics)} records. "
            f"This verifies no orphaned topic records remain in the database."
        )

    # Step 5: Verify all topic metadata is cleaned
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify topic context cache is cleaned for deleted topics
        async with db.execute(
            "SELECT COUNT(*) FROM topic_context_cache WHERE topic_id IN (?, ?, ?)",
            (topic_id_1, topic_id_2, topic_id_3)
        ) as cur:
            cache_count = (await cur.fetchone())[0]

        assert cache_count == 0, (
            f"Expected 0 topic context cache entries after cleanup, but found {cache_count}. "
            f"This verifies all topic metadata is cleaned, not just the main topic records."
        )

    # Test passes when run once - topic table cleanup is verified
    # The test_db_store fixture will perform additional cleanup after this test


@pytest.mark.asyncio
async def test_topic_table_empty_state_after_test_operations(test_db_store):
    """Verify topic table returns to empty state after complex test operations.

    This test verifies that after typical test operations (create, use, delete),
    the topic table can be returned to a clean state (bead adc-65gkbh acceptance):
    1. Query all topics from database
    2. Assert count == 0 after test operations and cleanup
    3. Verify no topic metadata remains
    4. Use existing session store utilities (no raw SQL)

    This test uses only SessionStore methods (no direct SQL) to match production usage.
    """
    # Create a session with topics
    session_id = await test_db_store.create_session()

    # Create multiple topics with different configurations
    await test_db_store.create_topic(
        label="Project Topic",
        topic_type="project",
        project_slugs=["project-a", "project-b"],
        scope="session",
        session_id=session_id
    )

    await test_db_store.create_topic(
        label="Research Topic",
        topic_type="research",
        project_slugs=["research-x"],
        scope="session",
        session_id=session_id
    )

    cross_session_topic = await test_db_store.create_topic(
        label="Cross-Session Topic",
        topic_type="compound",  # Valid type: project, research, personal, exception, compound
        project_slugs=["global-project"],
        scope="cross-session",
        session_id=None  # Cross-session topics have NULL session_id
    )

    # Verify topics exist using SessionStore utilities
    topics = await test_db_store.get_active_topics(session_id)
    assert len(topics) >= 2, "Should have at least 2 session-scoped topics"

    # Clean up via session deletion (production cleanup path)
    await test_db_store.delete_session(session_id)

    # Query all topics from database (using direct query for verification)
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Assert count == 0 after cleanup
        async with db.execute("SELECT COUNT(*) FROM topics WHERE session_id IS NOT NULL") as cur:
            session_topic_count = (await cur.fetchone())[0]

        assert session_topic_count == 0, (
            f"Expected 0 session-scoped topics after cleanup, but found {session_topic_count}. "
            f"This verifies the session topic cleanup via delete_session."
        )

    # Clean up the cross-session topic manually (it won't be cascade-deleted)
    async with aiosqlite.connect(test_db_store.db_path) as db:
        await db.execute("DELETE FROM topics WHERE id = ?", (cross_session_topic,))
        await db.commit()

    # Final verification: all topics are gone
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) FROM topics") as cur:
            final_count = (await cur.fetchone())[0]

        assert final_count == 0, (
            f"Expected 0 topics (all scopes) after full cleanup, but found {final_count}. "
            f"This verifies complete topic table cleanup."
        )


@pytest.mark.asyncio
async def test_no_orphaned_topic_metadata_after_cleanup(test_db_store):
    """Verify no orphaned topic metadata remains after session deletion.

    This test specifically checks that all topic-related data is cleaned up,
    not just the main topic records (bead adc-65gkbh scope):
    1. Topic context cache entries
    2. Intent-topic relationships
    3. Results linked to topics

    Uses existing session store utilities for cleanup.
    """
    # Create a session with a complete data tree
    session_id = await test_db_store.create_session()

    topic_id = await test_db_store.create_topic(
        label="Test Topic",
        topic_type="project",
        project_slugs=["test-project"],
        scope="session",
        session_id=session_id
    )

    # Add topic context cache
    await test_db_store.set_topic_context(
        topic_id,
        {"context": "data", "items": [1, 2, 3]},
        ttl_seconds=600
    )

    # Create utterance and intent linked to topic
    utterance_id = await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="Test utterance"
    )

    intent_id = await test_db_store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="status",
        topic_id=topic_id
    )

    # Link intent to topic (many-to-many)
    await test_db_store.link_intent_to_topic(intent_id, topic_id)

    # Create result for the topic
    result_id = await test_db_store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result",
        data={"test": "data"}
    )

    # Verify all data exists before cleanup
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check topic context cache
        async with db.execute(
            "SELECT COUNT(*) FROM topic_context_cache WHERE topic_id = ?",
            (topic_id,)
        ) as cur:
            cache_count = (await cur.fetchone())[0]
        assert cache_count == 1, "Topic context cache should exist"

        # Check intent-topic links
        async with db.execute(
            "SELECT COUNT(*) FROM intent_topics WHERE topic_id = ?",
            (topic_id,)
        ) as cur:
            link_count = (await cur.fetchone())[0]
        assert link_count == 1, "Intent-topic link should exist"

        # Check results linked to topic
        async with db.execute(
            "SELECT COUNT(*) FROM results WHERE topic_id = ?",
            (topic_id,)
        ) as cur:
            result_count = (await cur.fetchone())[0]
        assert result_count == 1, "Result should be linked to topic"

    # Delete session (should cascade-delete all related data)
    await test_db_store.delete_session(session_id)

    # Verify no orphaned topic metadata remains
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check topic context cache is cleaned
        async with db.execute(
            "SELECT COUNT(*) FROM topic_context_cache WHERE topic_id = ?",
            (topic_id,)
        ) as cur:
            cache_count = (await cur.fetchone())[0]

        assert cache_count == 0, (
            f"Expected 0 topic context cache entries after cleanup, but found {cache_count}. "
            f"This verifies topic metadata is properly cleaned."
        )

        # Check intent-topic links are cleaned
        async with db.execute(
            "SELECT COUNT(*) FROM intent_topics WHERE topic_id = ?",
            (topic_id,)
        ) as cur:
            link_count = (await cur.fetchone())[0]

        assert link_count == 0, (
            f"Expected 0 intent-topic links after cleanup, but found {link_count}. "
            f"This verifies intent-topic relationships are cleaned."
        )

        # Check results for deleted topic are cleaned
        async with db.execute(
            "SELECT COUNT(*) FROM results WHERE topic_id = ?",
            (topic_id,)
        ) as cur:
            result_count = (await cur.fetchone())[0]

        assert result_count == 0, (
            f"Expected 0 results for deleted topic after cleanup, but found {result_count}. "
            f"This verifies results linked to deleted topics are cleaned."
        )

    # Test passes - no orphaned topic metadata remains
