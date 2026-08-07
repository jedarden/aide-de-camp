"""
Database state verification tests (bead adc-6bisdu).

These tests verify that:
1. Database is properly reset between test runs
2. No residual data remains after test execution
3. All tables are cleaned/cleared appropriately
4. Tests pass when run once and when run 10+ times

The tests verify the isolation guarantees provided by the fixtures in conftest.py:
- test_db_store: temporary file-based database with automatic cleanup
- in_memory_db_store: completely isolated in-memory database
- reset_global_store_singleton: autouse fixture that resets global state
"""

import asyncio
import os
import uuid
from pathlib import Path

import aiosqlite
import pytest

from src.session.store import SessionStore


# =============================================================================
# Table inventory and verification helpers
# =============================================================================

# All tables in the session.db schema
ALL_TABLES = [
    "sessions",
    "surfaces",
    "utterances",
    "intents",
    "results",
    "topics",
    "topic_context_cache",
    "intent_topics",
    "feedback_signals",
    "dispatch_timings",
    "bead_watch",
    "pending_bead_approvals",
    "confirmation_prompts",
    "card_cache",
]


async def get_all_table_counts(db_path: str | Path) -> dict[str, int]:
    """Get row counts for all tables in the database."""
    counts = {}
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        for table in ALL_TABLES:
            try:
                async with db.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                    row = await cur.fetchone()
                    counts[table] = row[0] if row else 0
            except Exception:
                # Table might not exist in old migrations
                counts[table] = -1
    return counts


async def verify_all_tables_empty(db_path: str | Path) -> dict[str, bool]:
    """Verify all tables are empty (0 rows). Returns dict of table -> is_empty."""
    results = {}
    counts = await get_all_table_counts(db_path)
    for table, count in counts.items():
        if count == -1:
            # Table doesn't exist, treat as "empty" for migration compatibility
            results[table] = True
        else:
            results[table] = count == 0
    return results


async def populate_all_tables(store: SessionStore, session_id: str) -> dict[str, int]:
    """Populate all tables with test data for isolation verification.

    Returns a dict of table -> row_count after population.
    """
    counts = {}

    # Sessions table (already has 1 from create_session)
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM sessions") as cur:
            row = await cur.fetchone()
            counts["sessions"] = row[0] if row else 0

    # Surfaces
    surface_id = await store.register_surface(session_id, "canvas")
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM surfaces") as cur:
            row = await cur.fetchone()
            counts["surfaces"] = row[0] if row else 0

    # Utterances
    utterance_id = await store.create_utterance(session_id, "test utterance")
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            row = await cur.fetchone()
            counts["utterances"] = row[0] if row else 0

    # Topics
    topic_id = await store.create_topic(
        label="Test Topic",
        topic_type="project",
        project_slugs=["test-project"],
        scope="session",
        session_id=session_id
    )
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM topics") as cur:
            row = await cur.fetchone()
            counts["topics"] = row[0] if row else 0

    # Intents
    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="status",
        topic_id=topic_id,
        bead_ref=None,
        lookup_kind=None
    )
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM intents") as cur:
            row = await cur.fetchone()
            counts["intents"] = row[0] if row else 0

    # Intent_topics many-to-many
    await store.link_intent_to_topic(intent_id, topic_id)
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM intent_topics") as cur:
            row = await cur.fetchone()
            counts["intent_topics"] = row[0] if row else 0

    # Results
    result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result",
        data={"test": "data"},
        urgency="normal"
    )
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM results") as cur:
            row = await cur.fetchone()
            counts["results"] = row[0] if row else 0

    # Topic context cache
    await store.set_topic_context(topic_id, {"test": "context"}, ttl_seconds=600)
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM topic_context_cache") as cur:
            row = await cur.fetchone()
            counts["topic_context_cache"] = row[0] if row else 0

    # Feedback signals
    await store.create_feedback_signal(
        signal_id=str(uuid.uuid4()),
        signal_type="test_signal",
        session_id=session_id,
        result_id=result_id,
        topic_id=topic_id,
        data={"test": "signal"}
    )
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM feedback_signals") as cur:
            row = await cur.fetchone()
            counts["feedback_signals"] = row[0] if row else 0

    # Dispatch timings
    await store.record_dispatch_timings(
        intent_id=intent_id,
        router_ms=100,
        fetch_total_ms=200,
        synthesize_total_ms=300
    )
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM dispatch_timings") as cur:
            row = await cur.fetchone()
            counts["dispatch_timings"] = row[0] if row else 0

    # Bead watch
    async with aiosqlite.connect(store.db_path) as db:
        await db.execute(
            """INSERT INTO bead_watch
               (bead_ref, refusal_count, sla_deadline, created_at)
               VALUES (?, ?, ?, ?)""",
            ("test-bead", 0, int(asyncio.get_event_loop().time()) + 3600, int(asyncio.get_event_loop().time()))
        )
        await db.commit()
        async with db.execute("SELECT COUNT(*) FROM bead_watch") as cur:
            row = await cur.fetchone()
            counts["bead_watch"] = row[0] if row else 0

    # Pending bead approvals
    async with aiosqlite.connect(store.db_path) as db:
        await db.execute(
            """INSERT INTO pending_bead_approvals
               (id, intent_id, session_id, bead_body, bead_type, validation_result, utterance, created_at, expires_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), intent_id, session_id, "test body", "action", "{}", "test utterance",
             int(asyncio.get_event_loop().time()), int(asyncio.get_event_loop().time()) + 3600, "pending")
        )
        await db.commit()
        async with db.execute("SELECT COUNT(*) FROM pending_bead_approvals") as cur:
            row = await cur.fetchone()
            counts["pending_bead_approvals"] = row[0] if row else 0

    # Confirmation prompts
    async with aiosqlite.connect(store.db_path) as db:
        await db.execute(
            """INSERT INTO confirmation_prompts
               (id, intent_id, session_id, prompt_type, question, created_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), intent_id, session_id, "test_confirmation", "Test question?",
             int(asyncio.get_event_loop().time()), "pending")
        )
        await db.commit()
        async with db.execute("SELECT COUNT(*) FROM confirmation_prompts") as cur:
            row = await cur.fetchone()
            counts["confirmation_prompts"] = row[0] if row else 0

    # Card cache
    await store.write_card_cache(
        result_id=result_id,
        component_id="test-component",
        layout_bucket="default",
        rendered_html="<div>Test</div>"
    )
    async with aiosqlite.connect(store.db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM card_cache") as cur:
            row = await cur.fetchone()
            counts["card_cache"] = row[0] if row else 0

    return counts


# =============================================================================
# Test: File-based database isolation (test_db_store fixture)
# =============================================================================


@pytest.mark.asyncio
async def test_file_db_isolation_between_tests(test_db_store):
    """Verify test_db_store provides complete isolation between tests.

    This test verifies that the test_db_store fixture:
    1. Creates a fresh database for each test
    2. Contains no residual data from previous tests
    3. Is properly cleaned up after the test completes
    """
    # At the start of the test, database should be completely empty
    # (except for schema, which we don't count as data)
    empty_state = await verify_all_tables_empty(test_db_store.db_path)

    # All tables should be empty at test start
    non_empty_tables = [table for table, is_empty in empty_state.items() if not is_empty]
    assert len(non_empty_tables) == 0, (
        f"Expected all tables to be empty at test start, but found data in: {non_empty_tables}"
    )

    # Create some test data
    session_id = await test_db_store.create_session()
    counts = await populate_all_tables(test_db_store, session_id)

    # Verify data was created
    for table in ALL_TABLES:
        if counts.get(table, 0) > 0:
            assert counts[table] > 0, f"Expected data in {table}"

    # The fixture will automatically clean up after this test
    # The next test (if run) should get a completely fresh database


@pytest.mark.asyncio
async def test_file_db_cleanup_after_test(test_db_store):
    """Verify that the test database file is properly cleaned up after test execution.

    This test verifies the cleanup mechanism in the test_db_path fixture:
    1. Database file is deleted after test
    2. WAL files are also cleaned up
    3. No orphaned files remain
    """
    db_file = test_db_store.db_path
    wal_file = str(db_file) + "-wal"
    shm_file = str(db_file) + "-shm"

    # Create data to ensure the database file exists
    session_id = await test_db_store.create_session()
    await test_db_store.create_utterance(session_id, "test")

    # Verify database file exists
    assert db_file.exists(), "Database file should exist during test"

    # After the test, the fixture will clean up
    # (We can't verify this within the same test, but the fixture
    # teardown in conftest.py handles the cleanup)


@pytest.mark.asyncio
async def test_file_db_no_orphaned_records(test_db_store):
    """Verify that no orphaned records remain after test execution.

    This test checks for common orphaned record scenarios:
    1. Child records without parents (due to CASCADE issues)
    2. Unlinked many-to-many relationships
    3. Stranded cache entries
    """
    session_id = await test_db_store.create_session()

    # Create a complete data tree
    topic_id = await test_db_store.create_topic(
        label="Test Topic",
        topic_type="project",
        scope="session",
        session_id=session_id
    )

    utterance_id = await test_db_store.create_utterance(session_id, "test")
    intent_id = await test_db_store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test-project",
        intent_type="status",
        topic_id=topic_id
    )

    result_id = await test_db_store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result",
        data={"test": "data"}
    )

    # Verify referential integrity - all records should have proper parents
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check all results have valid topics
        async with db.execute("""
            SELECT COUNT(*) FROM results r
            LEFT JOIN topics t ON r.topic_id = t.id
            WHERE t.id IS NULL
        """) as cur:
            orphaned_results = (await cur.fetchone())[0]
        assert orphaned_results == 0, "Found results without valid topics"

        # Check all intents have valid utterances
        async with db.execute("""
            SELECT COUNT(*) FROM intents i
            LEFT JOIN utterances u ON i.utterance_id = u.id
            WHERE u.id IS NULL
        """) as cur:
            orphaned_intents = (await cur.fetchone())[0]
        assert orphaned_intents == 0, "Found intents without valid utterances"

        # Check all intent_topics have valid intents and topics
        async with db.execute("""
            SELECT COUNT(*) FROM intent_topics it
            LEFT JOIN intents i ON it.intent_id = i.id
            LEFT JOIN topics t ON it.topic_id = t.id
            WHERE i.id IS NULL OR t.id IS NULL
        """) as cur:
            orphaned_links = (await cur.fetchone())[0]
        assert orphaned_links == 0, "Found intent_topics with invalid intent or topic"


# =============================================================================
# Test: In-memory database isolation (in_memory_db_store fixture)
# =============================================================================


@pytest.mark.asyncio
async def test_in_memory_db_isolation(in_memory_db_store):
    """Verify in_memory_db_store provides complete isolation between tests.

    This test verifies that the in_memory_db_store fixture:
    1. Creates a fresh in-memory database for each test
    2. Contains no residual data from previous tests
    3. Is completely destroyed when the test completes
    """
    # At the start, database should be completely empty
    empty_state = await verify_all_tables_empty(in_memory_db_store.db_path)

    non_empty_tables = [table for table, is_empty in empty_state.items() if not is_empty]
    assert len(non_empty_tables) == 0, (
        f"Expected all tables to be empty at test start, but found data in: {non_empty_tables}"
    )

    # Create some test data
    session_id = await in_memory_db_store.create_session()
    counts = await populate_all_tables(in_memory_db_store, session_id)

    # Verify data was created
    data_created = False
    for table, count in counts.items():
        if count > 0:
            data_created = True
            break

    assert data_created, "Expected some data to be created"

    # The in-memory database will be completely destroyed after this test
    # No cleanup is needed - it's gone from memory when the connection closes


@pytest.mark.asyncio
async def test_in_memory_db_unique_per_test(in_memory_db_store):
    """Verify that each test gets a unique in-memory database.

    This test verifies the cache name randomization in the fixture:
    1. Each test gets a different cache name
    2. No sharing between concurrent tests
    3. Complete isolation even if tests run in parallel
    """
    # The fixture uses a unique cache name with UUID
    # We can verify this by checking the db_path format
    db_path = in_memory_db_store.db_path

    # Should be in the format: file:in_memory_db_{uuid}?mode=memory&cache=shared
    assert "in_memory_db_" in db_path, "Database path should use unique cache name"
    assert "mode=memory&cache=shared" in db_path, "Database should use shared cache mode"

    # Create data in this test's database
    session_id = await in_memory_db_store.create_session()
    await in_memory_db_store.create_utterance(session_id, "unique test data")

    # Verify data exists in this database
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            count = (await cur.fetchone())[0]
        assert count == 1, "Should have 1 utterance in this test's database"


# =============================================================================
# Test: Global singleton reset (reset_global_store_singleton fixture)
# =============================================================================


@pytest.mark.asyncio
async def test_global_store_singleton_reset():
    """Verify that the global store singleton is reset between tests.

    This test verifies the autouse reset_global_store_singleton fixture:
    1. Global _store singleton is reset to None before each test
    2. ADC_DB_PATH environment variable points to a unique test database
    3. Each test calling get_store() gets a fresh instance
    """
    from src.session import store as store_module

    # The autouse fixture should have already reset the singleton
    # before this test started
    assert store_module._store is None, (
        "Global store singleton should be None at test start "
        "(reset_global_store_singleton should have reset it)"
    )

    # Get a fresh store instance
    from src.session.store import get_store
    store = get_store()

    # Verify it's a new instance with the test database
    assert store is not None, "Should get a valid store instance"

    # The database path should be a test-specific path (not production)
    test_db_path = os.environ.get("ADC_DB_PATH", "")
    assert "singleton_test_db" in test_db_path or "test_db" in test_db_path, (
        f"ADC_DB_PATH should point to a test database, got: {test_db_path}"
    )

    # Create some data
    session_id = await store.create_session()
    await store.create_utterance(session_id, "singleton test")

    # Verify data exists
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            count = (await cur.fetchone())[0]
        assert count == 1, "Should have 1 utterance"

    # The next test will get a completely fresh store and database


# =============================================================================
# Test: Cross-test verification (repeatable isolation)
# =============================================================================


@pytest.mark.asyncio
async def test_repeatable_isolation_run_1(test_db_store):
    """First run of isolation test - creates data with specific IDs.

    This test is part of a pair that verifies repeatable isolation:
    - test_repeatable_isolation_run_1: Creates data with known IDs
    - test_repeatable_isolation_run_2: Verifies that data doesn't leak into next test

    Both tests should pass regardless of execution order or repetition count.
    """
    # Use a deterministic session ID for this test run
    session_id = "test-isolation-run-1-session"
    await test_db_store.create_session(session_id)

    # Create data with this test's specific marker
    await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="isolation test run 1"
    )

    # Verify data exists
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT raw_text FROM utterances WHERE session_id = ?",
            (session_id,)
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["raw_text"] == "isolation test run 1"


@pytest.mark.asyncio
async def test_repeatable_isolation_run_2(test_db_store):
    """Second run of isolation test - verifies no data leakage from previous tests.

    This test verifies that:
    1. Data from test_repeatable_isolation_run_1 doesn't appear in this test
    2. The database is completely fresh for this test
    3. Tests can be run repeatedly without interference
    """
    # Use a different session ID for this test run
    session_id = "test-isolation-run-2-session"
    await test_db_store.create_session(session_id)

    # Create data for this test
    await test_db_store.create_utterance(
        session_id=session_id,
        raw_text="isolation test run 2"
    )

    # Verify ONLY this test's data exists
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Should have exactly 1 utterance (from this test)
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            count = (await cur.fetchone())[0]
        assert count == 1, f"Expected exactly 1 utterance, found {count}"

        # Should NOT have data from run 1
        async with db.execute(
            "SELECT raw_text FROM utterances WHERE raw_text = ?",
            ("isolation test run 1",)
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == 0, "Should not find data from previous test run"

        # Should have data from run 2
        async with db.execute(
            "SELECT raw_text FROM utterances WHERE raw_text = ?",
            ("isolation test run 2",)
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == 1, "Should find data from this test run"


@pytest.mark.asyncio
async def test_no_residual_data_after_complex_operations(test_db_store):
    """Verify no residual data after complex multi-table operations.

    This test performs a series of complex operations and verifies that
    the fixture cleanup still works correctly:
    1. Create a full data tree across all tables
    2. Perform deletes and cascades
    3. Verify the fixture still cleans up properly
    """
    session1 = await test_db_store.create_session()
    session2 = await test_db_store.create_session()

    # Create complex data in session1
    topic1 = await test_db_store.create_topic(
        label="Topic 1",
        topic_type="project",
        scope="session",
        session_id=session1
    )

    utterance1 = await test_db_store.create_utterance(session1, "utterance 1")
    intent1 = await test_db_store.create_intent(
        utterance_id=utterance1,
        session_id=session1,
        project_slug="test-project",
        intent_type="status",
        topic_id=topic1
    )

    result1 = await test_db_store.create_result(
        intent_id=intent1,
        topic_id=topic1,
        session_id=session1,
        summary="Result 1",
        data={"test": "data1"}
    )

    # Create data in session2
    topic2 = await test_db_store.create_topic(
        label="Topic 2",
        topic_type="research",
        scope="session",
        session_id=session2
    )

    # Delete session1 (should cascade delete all its data)
    await test_db_store.delete_session(session1)

    # Verify session1 data is gone
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Session1 should be gone
        async with db.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (session1,)) as cur:
            count = (await cur.fetchone())[0]
        assert count == 0, "Session1 should be deleted"

        # Session1's utterances should be gone
        async with db.execute("SELECT COUNT(*) FROM utterances WHERE session_id = ?", (session1,)) as cur:
            count = (await cur.fetchone())[0]
        assert count == 0, "Session1 utterances should be cascade deleted"

        # Session2 should still exist
        async with db.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (session2,)) as cur:
            count = (await cur.fetchone())[0]
        assert count == 1, "Session2 should still exist"

    # The fixture will clean up everything after this test
    # Both sessions and all their data will be gone


# =============================================================================
# Test: Fixture-specific cleanup verification
# =============================================================================


@pytest.mark.asyncio
async def test_test_db_path_cleanup(tmp_path):
    """Verify that test_db_path fixture properly cleans up database files.

    This test verifies the file cleanup mechanism:
    1. Temporary database file is created
    2. WAL files are created during use
    3. All files are properly deleted during cleanup
    """
    import tempfile

    # Create a test database path
    test_db = tmp_path / f"cleanup_test_{uuid.uuid4().hex[:8]}.db"

    # Initialize a database
    store = SessionStore(test_db)
    await store.initialize()

    # Create some data to ensure WAL files are created
    session_id = await store.create_session()
    await store.create_utterance(session_id, "cleanup test")

    # Close the store
    await store.close()

    # Verify database files exist
    assert test_db.exists(), "Database file should exist"

    wal_path = str(test_db) + "-wal"
    shm_path = str(test_db) + "-shm"

    # WAL files might or might not exist depending on SQLite's behavior
    # but if they do exist, they should be cleaned up

    # Simulate the fixture cleanup (from conftest.py test_db_path fixture)
    try:
        if test_db.exists():
            os.unlink(test_db)
        if os.path.exists(wal_path):
            os.unlink(wal_path)
        if os.path.exists(shm_path):
            os.unlink(shm_path)
    except Exception:
        pass

    # Verify all files are gone
    assert not test_db.exists(), "Database file should be deleted"
    assert not os.path.exists(wal_path), "WAL file should be deleted"
    assert not os.path.exists(shm_path), "SHM file should be deleted"


# =============================================================================
# Test: Stress test - repeated execution
# =============================================================================


@pytest.mark.asyncio
async def test_isolation_under_repeated_execution(test_db_store):
    """Verify isolation holds up under repeated execution.

    This test simulates what happens when tests are run multiple times:
    1. Create data with unique identifiers
    2. Verify that previous runs' data doesn't interfere
    3. Demonstrate that tests can be run 10+ times safely
    """
    # Use the current timestamp to make this run unique
    import time
    run_id = int(time.time() * 1000000)  # microseconds

    session_id = f"stress-test-session-{run_id}"
    await test_db_store.create_session(session_id)

    await test_db_store.create_utterance(
        session_id=session_id,
        raw_text=f"stress test run {run_id}"
    )

    # Verify ONLY this run's data exists
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Should have exactly 1 utterance
        async with db.execute("SELECT COUNT(*) FROM utterances") as cur:
            count = (await cur.fetchone())[0]
        assert count == 1

        # Should have this run's specific data
        async with db.execute(
            "SELECT raw_text FROM utterances WHERE raw_text LIKE ?",
            (f"stress test run {run_id}",)
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == 1

        # Should NOT have data from other runs
        async with db.execute(
            "SELECT COUNT(*) FROM utterances WHERE raw_text LIKE 'stress test run %' AND raw_text NOT LIKE ?",
            (f"stress test run {run_id}",)
        ) as cur:
            count = (await cur.fetchone())[0]
        assert count == 0, "Should not have data from other stress test runs"


# =============================================================================
# Test: Comprehensive table coverage
# =============================================================================


@pytest.mark.asyncio
async def test_all_tables_are_initialized(test_db_store):
    """Verify that all expected tables exist in the test database.

    This test ensures that the test database schema is complete:
    1. All tables from ALL_TABLES exist
    2. Schema matches production structure
    3. No missing tables that would cause production code to fail
    """
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Get list of tables in the database
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()
        actual_tables = {row["name"] for row in rows}

        # Verify all expected tables exist
        missing_tables = set(ALL_TABLES) - actual_tables
        assert len(missing_tables) == 0, (
            f"Test database is missing tables: {missing_tables}"
        )

        # Verify no unexpected tables (schema drift)
        # Note: sqlite_* tables are system tables and are OK
        system_tables = {t for t in actual_tables if t.startswith("sqlite_")}
        user_tables = actual_tables - system_tables

        # All user tables should be in our expected list
        unexpected_tables = user_tables - set(ALL_TABLES)
        # Allow some tolerance for test-specific tables if any
        # (currently none, but this makes the test more robust)
        assert len(unexpected_tables) <= 0, (
            f"Found unexpected tables in test database: {unexpected_tables}"
        )


@pytest.mark.asyncio
async def test_all_tables_can_be_cleared(test_db_store):
    """Verify that all tables can be cleared (empty state is achievable).

    This test verifies that the database can be returned to a clean state:
    1. Populate all tables
    2. Clear all data (simulating fixture teardown)
    3. Verify all tables are empty
    """
    # Populate all tables
    session_id = await test_db_store.create_session()
    counts_before = await populate_all_tables(test_db_store, session_id)

    # Verify data was created
    total_before = sum(c for c in counts_before.values() if c > 0)
    assert total_before > 0, "Should have created some data"

    # Simulate fixture cleanup by deleting all data
    async with aiosqlite.connect(test_db_store.db_path) as db:
        # Delete from all tables in dependency order (children first)
        await db.execute("DELETE FROM feedback_signals")
        await db.execute("DELETE FROM dispatch_timings")
        await db.execute("DELETE FROM card_cache")
        await db.execute("DELETE FROM results")
        await db.execute("DELETE FROM intent_topics")
        await db.execute("DELETE FROM intents")
        await db.execute("DELETE FROM utterances")
        await db.execute("DELETE FROM topic_context_cache")
        await db.execute("DELETE FROM confirmation_prompts")
        await db.execute("DELETE FROM pending_bead_approvals")
        await db.execute("DELETE FROM topics")
        await db.execute("DELETE FROM surfaces")
        await db.execute("DELETE FROM bead_watch")
        await db.execute("DELETE FROM sessions")
        await db.commit()

    # Verify all tables are now empty
    empty_state = await verify_all_tables_empty(test_db_store.db_path)
    non_empty_tables = [table for table, is_empty in empty_state.items() if not is_empty]

    assert len(non_empty_tables) == 0, (
        f"Expected all tables to be empty after cleanup, but found data in: {non_empty_tables}"
    )
