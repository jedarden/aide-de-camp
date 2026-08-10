"""
Tests for in-memory database isolation.

Verify that in-memory database fixtures provide complete isolation from
production data and between tests.
"""

import hashlib
from pathlib import Path

import aiosqlite
import pytest

from src.session.store import SessionStore


def _snapshot_database_files(db_path: Path) -> dict[str, tuple | None]:
    """Return read-only snapshots of a SQLite database and its sidecars."""
    snapshot = {}
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if not path.exists():
            snapshot[str(path)] = None
            continue

        stat = path.stat()
        snapshot[str(path)] = (
            stat.st_ino,
            stat.st_mode,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
            hashlib.sha256(path.read_bytes()).digest(),
        )
    return snapshot


@pytest.mark.asyncio
async def test_in_memory_db_store_creates_fresh_database(in_memory_db_store):
    """Test that in_memory_db_store creates a fresh database for each test."""
    # Create a session
    session_id = await in_memory_db_store.create_session()

    # Verify session exists
    session = await in_memory_db_store.get_session(session_id)
    assert session is not None
    assert session["id"] == session_id


@pytest.mark.asyncio
async def test_in_memory_db_store_is_isolated_from_other_tests(in_memory_db_store):
    """Test that in-memory database is isolated between tests."""
    # This test should always start with an empty database
    # even if other tests have run before

    # For a fresh in-memory database, this test runs in isolation
    # The database should be empty at the start
    session_id = await in_memory_db_store.create_session()

    session = await in_memory_db_store.get_session(session_id)
    assert session is not None

    # Verify we have exactly one session (the one we just created)
    sessions = []
    async with aiosqlite.connect(in_memory_db_store.db_path, uri=True) as conn:
        cursor = await conn.execute("SELECT id FROM sessions")
        rows = await cursor.fetchall()
        sessions = [row[0] for row in rows]

    assert len(sessions) == 1, "Should have exactly one session in isolated database"
    assert session_id in sessions, "The session we created should be in the database"


@pytest.mark.asyncio
async def test_in_memory_db_session_id_creates_valid_session(in_memory_db_store, in_memory_db_session_id):
    """Test that in_memory_db_session_id fixture creates a valid session."""
    session = await in_memory_db_store.get_session(in_memory_db_session_id)
    assert session is not None
    assert session["id"] == in_memory_db_session_id


@pytest.mark.asyncio
async def test_in_memory_db_connection_provides_direct_access(in_memory_db_connection):
    """Test that in_memory_db_connection provides direct database access."""
    # Create a session using direct SQL
    import uuid
    from datetime import datetime

    session_id = str(uuid.uuid4())
    now = int(datetime.now().timestamp())

    await in_memory_db_connection.execute(
        "INSERT INTO sessions (id, created_at, last_active) VALUES (?, ?, ?)",
        (session_id, now, now)
    )
    await in_memory_db_connection.commit()

    # Verify session exists using direct SQL
    async with in_memory_db_connection.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == session_id


@pytest.mark.asyncio
async def test_in_memory_database_has_full_schema(in_memory_db_store):
    """Test that in-memory database has the full schema including migrations."""
    # Check that all expected tables exist
    async with aiosqlite.connect(in_memory_db_store.db_path, uri=True) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

        # Verify core tables exist
        expected_tables = [
            'sessions', 'surfaces', 'utterances', 'intents', 'results',
            'topics', 'topic_context_cache', 'intent_topics', 'feedback_signals',
            'dispatch_timings', 'bead_watch', 'pending_bead_approvals', 'card_cache'
        ]

        for table in expected_tables:
            assert table in tables, f"Table {table} not found in schema"


@pytest.mark.asyncio
async def test_in_memory_database_supports_all_operations(in_memory_db_store):
    """Test that in-memory database supports all store operations."""
    # Create a session
    session_id = await in_memory_db_store.create_session()

    # Register a surface
    await in_memory_db_store.register_surface(session_id, "canvas")

    # Create an utterance
    utterance_id = await in_memory_db_store.create_utterance(
        session_id, "test utterance"
    )

    # Create an intent
    intent_id = await in_memory_db_store.create_intent(
        utterance_id, session_id, "test-project", "status"
    )

    # Create a topic
    topic_id = await in_memory_db_store.create_topic(
        "test-topic", "project", ["test-project"], "session", session_id
    )

    # Create a result
    result_id = await in_memory_db_store.create_result(
        intent_id, topic_id, session_id, "test summary", {"key": "value"}
    )

    # Verify all data is accessible
    session = await in_memory_db_store.get_session(session_id)
    assert session is not None

    utterance = await in_memory_db_store.get_utterance(utterance_id)
    assert utterance is not None
    assert utterance["raw_text"] == "test utterance"

    intent = await in_memory_db_store.get_intent(intent_id)
    assert intent is not None
    assert intent["intent_type"] == "status"

    result = await in_memory_db_store.get_result(result_id)
    assert result is not None
    assert result["summary"] == "test summary"


@pytest.mark.asyncio
async def test_in_memory_database_isolation_between_stores(in_memory_db_store, tmp_path):
    """Test that different in-memory stores are isolated from each other."""
    # This test verifies the isolation property of in-memory databases

    # Create data in the fixture-provided store
    session_id = await in_memory_db_store.create_session()

    # Create a separate in-memory store
    # SessionStore opens a fresh connection for each operation, so a plain
    # ':memory:' path would destroy the schema between calls.  A unique
    # temporary file gives the second store independent state while retaining
    # the production connection lifecycle.
    separate_store = SessionStore(str(tmp_path / "separate.db"))
    await separate_store.initialize()

    # The separate store should NOT have the session from the fixture
    session = await separate_store.get_session(session_id)
    assert session is None, "Separate in-memory database should be isolated"

    # Create a session in the separate store
    separate_session_id = await separate_store.create_session()

    # The fixture store should NOT have the session from the separate store
    session = await in_memory_db_store.get_session(separate_session_id)
    assert session is None, "Fixture in-memory database should be isolated"

    await separate_store.close()


@pytest.mark.asyncio
async def test_in_memory_writes_leave_production_unchanged(in_memory_db_store):
    """Test writes to the in-memory store do not change production SQLite files."""
    from src.session.store import DEFAULT_DB_PATH

    production_before = _snapshot_database_files(DEFAULT_DB_PATH)
    marker = "in-memory-database-only-marker"

    session_id = await in_memory_db_store.create_session()
    utterance_id = await in_memory_db_store.create_utterance(session_id, marker)

    async with aiosqlite.connect(in_memory_db_store.db_path, uri=True) as db:
        async with db.execute(
            "SELECT raw_text FROM utterances WHERE id = ?", (utterance_id,)
        ) as cursor:
            row = await cursor.fetchone()
        async with db.execute("PRAGMA database_list") as cursor:
            databases = await cursor.fetchall()

    assert row[0] == marker, "The marker must be stored in the in-memory database"
    assert "mode=memory" in in_memory_db_store.db_path
    assert databases[0][2] == "", "The in-memory database must have no filesystem path"
    assert _snapshot_database_files(DEFAULT_DB_PATH) == production_before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
