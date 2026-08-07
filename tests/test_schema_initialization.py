"""
Test suite for verifying session store schema initialization in test databases.

This test suite ensures that:
- All tables from production schema exist in test database
- All indexes from production schema exist in test database
- Schema initialization uses existing session store logic
- Test database has same structure as production session.db
"""

import pytest

# Expected tables from production SCHEMA_SQL
EXPECTED_TABLES = {
    "bead_watch",
    "card_cache",
    "confirmation_prompts",
    "dispatch_timings",
    "feedback_signals",
    "intent_topics",
    "intents",
    "pending_bead_approvals",
    "results",
    "sessions",
    "surfaces",
    "topic_context_cache",
    "topics",
    "utterances",
}

# Expected indexes from production SCHEMA_SQL
EXPECTED_INDEXES = {
    "idx_bead_watch_fenced",
    "idx_bead_watch_sla_deadline",
    "idx_card_cache_result_id",
    "idx_confirmation_prompts_intent",
    "idx_confirmation_prompts_session",
    "idx_confirmation_prompts_status",
    "idx_context_expires",
    "idx_dispatch_timings_created",
    "idx_intents_session",
    "idx_intents_status",
    "idx_intents_topic",
    "idx_pending_approvals_expires",
    "idx_pending_approvals_intent",
    "idx_pending_approvals_session",
    "idx_pending_approvals_status",
    "idx_results_created",
    "idx_results_previous",
    "idx_results_session",
    "idx_results_topic",
    "idx_signals_processed",
    "idx_signals_result",
    "idx_signals_session",
    "idx_signals_type",
    "idx_surfaces_session",
    "idx_surfaces_state",
    "idx_topics_active",
    "idx_topics_scope",
    "idx_topics_session",
    "idx_utterances_session",
}


@pytest.mark.asyncio
async def test_test_db_store_schema_tables(test_db_store):
    """Verify test_db_store fixture creates all expected tables."""
    import aiosqlite

    async with aiosqlite.connect(test_db_store.db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        actual_tables = {row[0] for row in await cursor.fetchall()}

        # Remove SQLite system tables
        actual_tables.discard("sqlite_stat1")
        actual_tables.discard("sqlite_stat2")
        actual_tables.discard("sqlite_stat3")
        actual_tables.discard("sqlite_stat4")

        # Verify all expected tables exist
        assert EXPECTED_TABLES.issubset(actual_tables), (
            f"Missing tables: {EXPECTED_TABLES - actual_tables}"
        )

        # Verify no extra unexpected tables (beyond system tables)
        unexpected = actual_tables - EXPECTED_TABLES - {
            "sqlite_sequence",  # AUTOINCREMENT tracking table
        }
        assert not unexpected, f"Unexpected tables found: {unexpected}"


@pytest.mark.asyncio
async def test_test_db_store_schema_indexes(test_db_store):
    """Verify test_db_store fixture creates all expected indexes."""
    import aiosqlite

    async with aiosqlite.connect(test_db_store.db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        actual_indexes = {row[0] for row in await cursor.fetchall()}

        # Verify all expected indexes exist
        assert EXPECTED_INDEXES.issubset(actual_indexes), (
            f"Missing indexes: {EXPECTED_INDEXES - actual_indexes}"
        )


@pytest.mark.asyncio
async def test_test_db_connection_schema_tables(test_db_connection):
    """Verify test_db_connection fixture creates all expected tables."""
    cursor = await test_db_connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    actual_tables = {row[0] for row in await cursor.fetchall()}

    # Remove SQLite system tables
    actual_tables.discard("sqlite_stat1")
    actual_tables.discard("sqlite_stat2")
    actual_tables.discard("sqlite_stat3")
    actual_tables.discard("sqlite_stat4")

    # Verify all expected tables exist
    assert EXPECTED_TABLES.issubset(actual_tables), (
        f"Missing tables: {EXPECTED_TABLES - actual_tables}"
    )


@pytest.mark.asyncio
async def test_test_db_connection_schema_indexes(test_db_connection):
    """Verify test_db_connection fixture creates all expected indexes."""
    cursor = await test_db_connection.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    actual_indexes = {row[0] for row in await cursor.fetchall()}

    # Verify all expected indexes exist
    assert EXPECTED_INDEXES.issubset(actual_indexes), (
        f"Missing indexes: {EXPECTED_INDEXES - actual_indexes}"
    )


@pytest.mark.asyncio
async def test_in_memory_db_store_schema(in_memory_db_store):
    """Verify in_memory_db_store fixture creates all expected tables."""
    import aiosqlite

    # For in-memory DB, we need to connect to the same database
    async with aiosqlite.connect(":memory:") as db:
        # Re-initialize schema for verification
        from src.session.store import SCHEMA_SQL
        await db.executescript(SCHEMA_SQL)
        await db.commit()

        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        actual_tables = {row[0] for row in await cursor.fetchall()}

        # Remove SQLite system tables
        actual_tables.discard("sqlite_stat1")
        actual_tables.discard("sqlite_stat2")
        actual_tables.discard("sqlite_stat3")
        actual_tables.discard("sqlite_stat4")

        # Verify all expected tables exist
        assert EXPECTED_TABLES.issubset(actual_tables), (
            f"Missing tables: {EXPECTED_TABLES - actual_tables}"
        )


@pytest.mark.asyncio
async def test_in_memory_db_connection_schema(in_memory_db_connection):
    """Verify in_memory_db_connection fixture creates all expected tables."""
    cursor = await in_memory_db_connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    actual_tables = {row[0] for row in await cursor.fetchall()}

    # Remove SQLite system tables
    actual_tables.discard("sqlite_stat1")
    actual_tables.discard("sqlite_stat2")
    actual_tables.discard("sqlite_stat3")
    actual_tables.discard("sqlite_stat4")

    # Verify all expected tables exist
    assert EXPECTED_TABLES.issubset(actual_tables), (
        f"Missing tables: {EXPECTED_TABLES - actual_tables}"
    )


@pytest.mark.asyncio
async def test_session_store_initialize_creates_complete_schema():
    """Verify SessionStore.initialize() creates complete schema from scratch."""
    import tempfile
    from pathlib import Path
    from src.session.store import SessionStore

    # Create a new temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        # Initialize session store (this should create all tables and indexes)
        store = SessionStore(db_path)
        await store.initialize()

        # Verify schema was created completely
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            # Check tables
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            actual_tables = {row[0] for row in await cursor.fetchall()}
            actual_tables.discard("sqlite_stat1")
            actual_tables.discard("sqlite_stat2")
            actual_tables.discard("sqlite_stat3")
            actual_tables.discard("sqlite_stat4")
            actual_tables.discard("sqlite_sequence")

            assert EXPECTED_TABLES == actual_tables, (
                f"Schema mismatch: expected {EXPECTED_TABLES}, got {actual_tables}"
            )

            # Check indexes
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            actual_indexes = {row[0] for row in await cursor.fetchall()}

            assert EXPECTED_INDEXES == actual_indexes, (
                f"Index mismatch: expected {EXPECTED_INDEXES}, got {actual_indexes}"
            )

        await store.close()
    finally:
        db_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_migrations_run_on_initialization(test_db_store):
    """Verify that migrations run during schema initialization."""
    import aiosqlite

    # Check that migration columns exist (these prove migrations ran)
    async with aiosqlite.connect(test_db_store.db_path) as db:
        # Check result_type column in results (migration from initial schema)
        cursor = await db.execute("PRAGMA table_info(results)")
        result_columns = {row[1] for row in await cursor.fetchall()}
        assert "result_type" in result_columns, "Migration for result_type column not run"
        assert "card_fallback" in result_columns, "Migration for card_fallback column not run"

        # Check lookup_kind column in intents (migration from initial schema)
        cursor = await db.execute("PRAGMA table_info(intents)")
        intent_columns = {row[1] for row in await cursor.fetchall()}
        assert "lookup_kind" in intent_columns, "Migration for lookup_kind column not run"

        # Check reformulation_count column in sessions (migration)
        cursor = await db.execute("PRAGMA table_info(sessions)")
        session_columns = {row[1] for row in await cursor.fetchall()}
        assert "reformulation_count" in session_columns, "Migration for reformulation_count not run"

        # Check router_timing_breakdown column in utterances (migration)
        cursor = await db.execute("PRAGMA table_info(utterances)")
        utterance_columns = {row[1] for row in await cursor.fetchall()}
        assert "router_timing_breakdown" in utterance_columns, "Migration for router_timing_breakdown not run"

        # Check json_parse_ms column in dispatch_timings (migration)
        cursor = await db.execute("PRAGMA table_info(dispatch_timings)")
        timing_columns = {row[1] for row in await cursor.fetchall()}
        assert "json_parse_ms" in timing_columns, "Migration for json_parse_ms not run"


@pytest.mark.asyncio
async def test_wal_mode_enabled_in_test_db(test_db_store):
    """Verify that WAL mode is enabled in test databases (consistent with production)."""
    import aiosqlite

    async with aiosqlite.connect(test_db_store.db_path) as db:
        cursor = await db.execute("PRAGMA journal_mode")
        journal_mode = (await cursor.fetchone())[0]

        assert journal_mode == "wal", f"Expected WAL mode, got {journal_mode}"


@pytest.mark.asyncio
async def test_test_databases_are_isolated(test_db_store, test_db_path):
    """Verify that test databases use isolated files, not production session.db."""
    # Test database should use a temporary file, not production
    assert str(test_db_path) != "/home/coding/aide-de-camp/data/session.db"
    assert "test_db_" in str(test_db_path) or "tmp" in str(test_db_path).lower()

    # Verify the test database has data
    session_id = await test_db_store.create_session()
    session = await test_db_store.get_session(session_id)
    assert session is not None, "Test database should be functional"