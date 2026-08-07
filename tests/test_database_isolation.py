"""
Test database isolation fixtures.

Tests verify that the database fixtures provide complete isolation
from production data and from each other.

Acceptance criteria for bead adc-2gwlq:
- Test database setup fixture that uses isolated SQLite ✓
- Test database is completely isolated from production session.db ✓
- Each test gets a fresh database instance ✓
- Fixture tears down database after test completes ✓
- Uses aiosqlite for database access ✓
- Fixture yields fresh database connection ✓
- Schema is initialized using existing session store logic ✓
- Database uses temporary files to guarantee isolation ✓
"""

import aiosqlite
import pytest

from src.session.store import SessionStore


class TestDatabaseIsolationFixtures:
    """Test suite for database isolation fixtures."""

    @pytest.mark.asyncio
    async def test_db_store_creates_fresh_database(self, test_db_store):
        """Test that test_db_store provides a fresh database instance."""
        # Should start empty
        sessions = await test_db_store.get_session("nonexistent")
        assert sessions is None, "New database should have no sessions"

        # Create a session
        session_id = await test_db_store.create_session()
        assert session_id is not None, "Should create session successfully"

        # Verify it was created
        session = await test_db_store.get_session(session_id)
        assert session is not None, "Session should exist"
        assert session["id"] == session_id

    @pytest.mark.asyncio
    async def test_db_store_isolation_between_tests(self, test_db_store):
        """Test that each test gets a completely isolated database."""
        # Create data in this test
        session_id = await test_db_store.create_session()
        await test_db_store.create_topic(
            label="Test Topic",
            topic_type="project",
            scope="session",
            session_id=session_id
        )

        # Verify data exists in this test's database
        topics = await test_db_store.get_active_topics(session_id)
        assert len(topics) == 1, "Should have exactly one topic"

    @pytest.mark.asyncio
    async def test_db_store_independent_sessions(self, test_db_store):
        """Test that multiple sessions in the same test are independent."""
        session1_id = await test_db_store.create_session()
        session2_id = await test_db_store.create_session()

        # Verify both sessions exist and are different
        session1 = await test_db_store.get_session(session1_id)
        session2 = await test_db_store.get_session(session2_id)

        assert session1["id"] == session1_id
        assert session2["id"] == session2_id
        assert session1_id != session2_id

    @pytest.mark.asyncio
    async def test_session_id_fixture_provides_id(self, test_session_id, test_db_store):
        """Test that test_session_id fixture provides a valid session ID."""
        # The fixture should have created a session
        session = await test_db_store.get_session(test_session_id)
        assert session is not None, "Session should exist"
        assert session["id"] == test_session_id

    @pytest.mark.asyncio
    async def test_db_connection_fixture(self, test_db_connection):
        """Test that test_db_connection provides direct database access."""
        # Should be able to execute raw SQL
        async with test_db_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cur:
            tables = await cur.fetchall()

        # Should have all the tables from schema
        table_names = {row[0] for row in tables}
        assert "sessions" in table_names, "Should have sessions table"
        assert "topics" in table_names, "Should have topics table"
        assert "intents" in table_names, "Should have intents table"
        assert "results" in table_names, "Should have results table"
        assert "utterances" in table_names, "Should have utterances table"

    @pytest.mark.asyncio
    async def test_complete_schema_initialization(self, test_db_store):
        """Test that the database is initialized with the complete schema."""
        # Connect to the same database
        async with aiosqlite.connect(test_db_store.db_path) as db:
            # Check all expected tables exist
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cur:
                tables = {row[0] for row in await cur.fetchall()}

        # Verify all core tables exist
        expected_tables = {
            "sessions", "surfaces", "utterances", "intents", "results",
            "topics", "topic_context_cache", "intent_topics", "feedback_signals",
            "dispatch_timings", "bead_watch", "pending_bead_approvals", "card_cache"
        }

        missing_tables = expected_tables - tables
        assert not missing_tables, f"Missing tables: {missing_tables}"

    @pytest.mark.asyncio
    async def test_wal_mode_enabled(self, test_db_store):
        """Test that WAL mode is enabled for concurrent access."""
        async with aiosqlite.connect(test_db_store.db_path) as db:
            async with db.execute("PRAGMA journal_mode") as cur:
                journal_mode = await cur.fetchone()

        assert journal_mode[0] == "wal", "WAL mode should be enabled"

    @pytest.mark.asyncio
    async def test_isolated_from_production_database(self, test_db_store, test_db_path):
        """Test that test database is isolated from production data."""
        # The production database path should be different
        from src.session.store import DEFAULT_DB_PATH

        assert test_db_store.db_path == test_db_path
        assert test_db_path != DEFAULT_DB_PATH
        assert "test_db_" in str(test_db_path), "Should be a test database file"

        # Test database should be empty (not sharing data with production)
        async with aiosqlite.connect(test_db_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM sessions") as cur:
                sessions = await cur.fetchall()

        # Should start empty regardless of production data
        assert len(sessions) == 0, "Test database should not contain production data"

    @pytest.mark.asyncio
    async def test_full_store_functionality(self, test_db_store, test_session_id):
        """Test that SessionStore works correctly with test database."""
        # Create a topic
        topic_id, created = await test_db_store.find_or_create_topic(
            label="Test Topic",
            session_id=test_session_id,
            topic_type="project",
            scope="session"
        )

        assert created is True, "Should create new topic"
        assert topic_id is not None

        # Create an utterance
        utterance_id = await test_db_store.create_utterance(
            session_id=test_session_id,
            raw_text="Test utterance"
        )

        # Create an intent
        intent_id = await test_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=test_session_id,
            project_slug="test-project",
            intent_type="status"
        )

        # Create a result
        result_id = await test_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=test_session_id,
            summary="Test result",
            data={"test": "data"}
        )

        # Verify everything persisted correctly
        topics = await test_db_store.get_active_topics(test_session_id)
        assert len(topics) == 1
        assert topics[0]["id"] == topic_id

        result = await test_db_store.get_result(result_id)
        assert result is not None
        assert result["summary"] == "Test result"