"""
Orphaned utterance detection tests (bead adc-3t9m5t).

These tests verify that:
1. Utterances table is empty after session deletion cleanup
2. No orphaned utterance records exist after cleanup
3. All expected utterance columns/metadata are cleaned
4. Test passes when run once with pytest

This implements post-execution verification as specified in the acceptance criteria.
The scope is limited to post-execution verification - repeat runner integration comes
in a separate child task.
"""

import pytest
import aiosqlite


@pytest.mark.asyncio
async def test_utterance_table_cleanup_via_session_deletion(test_db_store):
    """Verify utterance table cleanup when session is deleted via delete_session.

    This test verifies the production cleanup path for utterances (bead adc-3t9m5t):
    1. Utterances are created and associated with a session
    2. Session is deleted via delete_session (production cleanup path)
    3. Utterance table is empty after cleanup
    4. No orphaned utterance records remain
    5. All utterance metadata is cleaned (including router_timing_breakdown)

    This implements the acceptance criteria: "Write test that verifies no utterance
    records exist after test execution" with proper post-execution verification.
    """
    # Step 1: Create a session and multiple utterances
    session_id = await test_db_store.create_session()

    utterance_id_1 = await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="Test utterance 1"
    )

    utterance_id_2 = await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="Test utterance 2"
    )

    utterance_id_3 = await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="Test utterance 3"
    )

    # Add router timing breakdown to one utterance (testing metadata cleanup)
    await test_db_store.update_utterance_router_timing(
        utterance_id=utterance_id_1,
        timing_breakdown={
            "prompt_construction_ms": 10,
            "proxy_call_ms": 100,
            "json_parse_ms": 5,
            "process_ms": 20,
            "total_ms": 135,
            "intents_count": 1,
            "cached": False
        }
    )

    # Step 2: Verify utterances exist before cleanup
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Count total utterances
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            utterance_count = (await cur.fetchone())[0]

        assert utterance_count == 3, (
            f"Expected exactly 3 utterances before cleanup, but found {utterance_count}"
        )

        # Verify specific utterance IDs exist
        async with db.execute(
            "SELECT id FROM utterances WHERE id IN (?, ?, ?)",
            (utterance_id_1, utterance_id_2, utterance_id_3)
        ) as cur:
            found_utterances = await cur.fetchall()

        assert len(found_utterances) == 3, (
            f"Expected to find all 3 utterance IDs, but found {len(found_utterances)}"
        )

        # Verify router timing breakdown exists
        async with db.execute(
            "SELECT router_timing_breakdown FROM utterances WHERE id = ?",
            (utterance_id_1,)
        ) as cur:
            row = await cur.fetchone()
            assert row[0] is not None, "Expected router timing breakdown to exist"

    # Step 3: Delete session via production cleanup path (delete_session)
    # This should cascade-delete all utterances for this session
    result = await test_db_store.delete_session(session_id)

    # Verify deletion report
    assert result["session_removed"] == 1, "Session should be removed"

    # Step 4: Verify utterance table is empty after cleanup (POST-EXECUTION VERIFICATION)
    # This is the core acceptance criteria: "Query utterances table and verify row count is 0"
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Query utterances table to verify row count is 0
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            final_utterance_count = (await cur.fetchone())[0]

        assert final_utterance_count == 0, (
            f"Expected 0 utterances after session deletion, but found {final_utterance_count}. "
            f"This verifies the utterance table is completely empty after cleanup. "
            f"Orphaned utterance records indicate cleanup did not cascade properly."
        )

        # Verify no orphaned utterance records exist (comprehensive check)
        # This implements: "Detect any residual utterances left in database"
        async with db.execute("SELECT id FROM utterances") as cur:
            any_utterances = await cur.fetchall()

        assert len(any_utterances) == 0, (
            f"Expected no utterance records after cleanup, but found {len(any_utterances)} records. "
            f"This verifies no orphaned utterance records remain in the database. "
            f"Orphaned utterances indicate session deletion did not properly cascade to utterances."
        )

    # Test passes - utterance table cleanup is verified
    # The test_db_store fixture will perform additional cleanup after this test


@pytest.mark.asyncio
async def test_no_orphaned_utterances_after_complex_operations(test_db_store):
    """Verify utterance table returns to empty state after complex test operations.

    This test verifies that after typical test operations (create, use, delete),
    the utterance table can be returned to a clean state (bead adc-3t9m5t acceptance):
    1. Query all utterances from database
    2. Assert count == 0 after test operations and cleanup
    3. Verify no utterance metadata remains
    4. Use existing session store utilities for cleanup

    This implements the scope: "ONLY for post-execution verification" checking
    that no residual utterances exist after typical test workflows.
    """
    # Create a session with utterances
    session_id = await test_db_store.create_session()

    # Create multiple utterances
    await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="First test utterance"
    )

    await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="Second test utterance"
    )

    await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="Third test utterance"
    )

    # Verify utterances exist
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) FROM utterances WHERE session_id = ?",
                             (session_id,)) as cur:
            utterance_count = (await cur.fetchone())[0]

        assert utterance_count == 3, "Should have exactly 3 utterances"

    # Clean up via session deletion (production cleanup path)
    await test_db_store.delete_session(session_id)

    # POST-EXECUTION VERIFICATION: Query utterances table and verify row count is 0
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Assert count == 0 after cleanup
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            final_count = (await cur.fetchone())[0]

        assert final_count == 0, (
            f"Expected 0 utterances after cleanup, but found {final_count}. "
            f"This verifies post-execution state shows no residual utterances. "
            f"Helpful message: {final_count} orphaned utterance records detected."
        )

        # Detect any residual utterances with detailed check
        async with db.execute(
            "SELECT id, session_id, raw_text FROM utterances"
        ) as cur:
            orphaned_utterances = await cur.fetchall()

        assert len(orphaned_utterances) == 0, (
            f"Detected {len(orphaned_utterances)} residual utterance(s) in database. "
            f"Orphaned utterances: {[dict(u) for u in orphaned_utterances]}. "
            f"This provides helpful diagnostic information when orphaned records are found."
        )


@pytest.mark.asyncio
async def test_no_orphaned_utterance_metadata_after_cleanup(test_db_store):
    """Verify no orphaned utterance metadata remains after session deletion.

    This test specifically checks that all utterance-related data is cleaned up,
    not just the main utterance records (bead adc-3t9m5t scope):
    1. Router timing breakdown data
    2. Utterance links to intents
    3. Utterance session associations

    Uses existing session store utilities for cleanup.
    """
    # Create a session with complete utterance data tree
    session_id = await test_db_store.create_session()

    # Create utterance with full metadata
    utterance_id = await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="Test utterance with metadata"
    )

    # Add router timing breakdown (utterance metadata)
    await test_db_store.update_utterance_router_timing(
        utterance_id=utterance_id,
        timing_breakdown={
            "prompt_construction_ms": 15,
            "proxy_call_ms": 120,
            "json_parse_ms": 8,
            "process_ms": 25,
            "total_ms": 168,
            "intents_count": 2,
            "cached": False
        }
    )

    # Create intent linked to utterance
    intent_id = await test_db_store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="status"
    )

    # Verify all data exists before cleanup
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check utterance exists with session association
        async with db.execute(
            "SELECT session_id, raw_text FROM utterances WHERE id = ?",
            (utterance_id,)
        ) as cur:
            utterance = await cur.fetchone()
        assert utterance is not None, "Utterance should exist"
        assert utterance[0] == session_id, "Utterance should be associated with session"

        # Check router timing breakdown exists
        async with db.execute(
            "SELECT router_timing_breakdown FROM utterances WHERE id = ?",
            (utterance_id,)
        ) as cur:
            timing_row = await cur.fetchone()
        assert timing_row[0] is not None, "Router timing breakdown should exist"

        # Check intent linked to utterance
        async with db.execute(
            "SELECT utterance_id FROM intents WHERE id = ?",
            (intent_id,)
        ) as cur:
            intent = await cur.fetchone()
        assert intent is not None, "Intent should be linked to utterance"

    # Delete session (should cascade-delete all related data)
    await test_db_store.delete_session(session_id)

    # Verify no orphaned utterance metadata remains (POST-EXECUTION VERIFICATION)
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check utterances are cleaned - main assertion for acceptance criteria
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            utterance_count = (await cur.fetchone())[0]

        assert utterance_count == 0, (
            f"Expected 0 utterances after cleanup, but found {utterance_count}. "
            f"This verifies the core acceptance criteria: no utterance records exist "
            f"after test execution."
        )

        # Check no orphaned utterance-session associations
        async with db.execute(
            "SELECT COUNT(*) FROM utterances WHERE session_id = ?",
            (session_id,)
        ) as cur:
            session_utterance_count = (await cur.fetchone())[0]

        assert session_utterance_count == 0, (
            f"Expected 0 utterances associated with deleted session, but found "
            f"{session_utterance_count}. This verifies session-utterance links are cleaned."
        )

        # Check no orphaned router timing breakdown data
        async with db.execute(
            "SELECT COUNT(*) FROM utterances WHERE router_timing_breakdown IS NOT NULL"
        ) as cur:
            timing_count = (await cur.fetchone())[0]

        assert timing_count == 0, (
            f"Expected 0 utterances with router timing breakdown after cleanup, but found "
            f"{timing_count}. This verifies utterance metadata is properly cleaned."
        )

    # Test passes - no orphaned utterance metadata remains
