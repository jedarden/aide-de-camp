"""
Session store unit tests (bead adc-3ttx0).

Tests core CRUD operations for SQLite session store:
- Topic creation and retrieval
- find_or_create_topic idempotency
- Utterance persistence
- Topic type mapping
- Independent session.store operations

These tests are hermetic and use temporary databases to avoid touching
production data/session.db.
"""

import json
from pathlib import Path

import aiosqlite
import pytest

from src.session.store import SessionStore

# --- fixtures ----------------------------------------------------------------


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """An isolated SessionStore on a tmp DB (same code as production session.db)."""
    db_path = tmp_path / "session.db"
    s = SessionStore(db_path)
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def session_id(store: SessionStore) -> str:
    """Create a test session and return its ID."""
    return await store.create_session()


# --- topic creation tests ---------------------------------------------------


@pytest.mark.asyncio
async def test_create_topic_basic(store: SessionStore, session_id: str) -> None:
    """Test basic topic creation with required fields."""
    topic_id = await store.create_topic(
        label="Test Topic",
        topic_type="project",
        scope="session",
        session_id=session_id
    )

    # Verify topic was persisted
    topics = await store.get_active_topics(session_id)
    assert len(topics) == 1, f"Expected 1 topic, got {len(topics)}"

    topic = topics[0]
    assert topic["id"] == topic_id, "Topic ID mismatch"
    assert topic["label"] == "Test Topic", "Topic label mismatch"
    assert topic["type"] == "project", "Topic type mismatch"
    assert topic["scope"] == "session", "Topic scope mismatch"
    assert topic["result_count"] == 0, "Expected 0 results for new topic"
    assert topic["archived_at"] is None, "New topic should not be archived"


@pytest.mark.asyncio
async def test_create_topic_with_project_slugs(store: SessionStore, session_id: str) -> None:
    """Test topic creation with project slugs."""
    topic_id = await store.create_topic(
        label="Multi-Project Topic",
        topic_type="project",
        project_slugs=["k8s", "monitoring", "logs"],
        scope="session",
        session_id=session_id
    )

    topics = await store.get_active_topics(session_id)
    assert len(topics) == 1

    topic = topics[0]
    assert topic["id"] == topic_id
    # project_slugs is stored as JSON array
    slugs = json.loads(topic["project_slugs"])
    assert slugs == ["k8s", "monitoring", "logs"], "Project slugs not stored correctly"


@pytest.mark.asyncio
async def test_find_or_create_topic_creates_new(store: SessionStore, session_id: str) -> None:
    """Test find_or_create_topic creates new topic when none exists."""
    topic_id, created = await store.find_or_create_topic(
        label="New Topic",
        session_id=session_id,
        topic_type="research",
        project_slugs=["research-project"]
    )

    assert created is True, "Should have created new topic"
    assert isinstance(topic_id, str), "Topic ID should be string"
    assert len(topic_id) > 0, "Topic ID should not be empty"

    # Verify it was persisted
    topics = await store.get_active_topics(session_id)
    assert len(topics) == 1
    assert topics[0]["label"] == "New Topic"
    assert topics[0]["type"] == "research"


@pytest.mark.asyncio
async def test_find_or_create_topic_returns_existing(store: SessionStore, session_id: str) -> None:
    """Test find_or_create_topic returns existing topic on duplicate call."""
    # Create initial topic
    first_id, first_created = await store.find_or_create_topic(
        label="Shared Topic",
        session_id=session_id,
        topic_type="personal"
    )
    assert first_created is True, "First call should create topic"

    # Call again with same label and session
    second_id, second_created = await store.find_or_create_topic(
        label="Shared Topic",
        session_id=session_id,
        topic_type="personal"
    )
    assert second_created is False, "Second call should not create topic"
    assert second_id == first_id, "Should return same topic ID"

    # Verify only one topic exists
    topics = await store.get_active_topics(session_id)
    assert len(topics) == 1, "Should not have created duplicate topic"


@pytest.mark.asyncio
async def test_find_or_create_topic_different_sessions(store: SessionStore) -> None:
    """Test find_or_create_topic is scoped per session."""
    session1 = await store.create_session()
    session2 = await store.create_session()

    # Create topic in session1
    topic1_id, created = await store.find_or_create_topic(
        label="Cross-Session Label",
        session_id=session1,
        topic_type="project"
    )
    assert created is True

    # Same label in session2 should create different topic
    topic2_id, created = await store.find_or_create_topic(
        label="Cross-Session Label",
        session_id=session2,
        topic_type="project"
    )
    assert created is True, "Should create new topic for different session"
    assert topic2_id != topic1_id, "Topics should have different IDs"

    # Verify each session has its own topic
    topics1 = await store.get_active_topics(session1)
    topics2 = await store.get_active_topics(session2)
    assert len(topics1) == 1
    assert len(topics2) == 1
    assert topics1[0]["id"] != topics2[0]["id"]


@pytest.mark.asyncio
async def test_find_or_create_topic_archived_excluded(store: SessionStore, session_id: str) -> None:
    """Test find_or_create_topic excludes archived topics."""
    # Create initial topic
    topic_id, created = await store.find_or_create_topic(
        label="Archive Me",
        session_id=session_id,
        topic_type="project"
    )
    assert created is True

    # Manually archive the topic
    now = int(datetime.now().timestamp())
    async with aiosqlite.connect(store.db_path) as db:
        await db.execute(
            "UPDATE topics SET archived_at = ? WHERE id = ?",
            (now, topic_id)
        )
        await db.commit()

    # Should create new topic despite same label (old one is archived)
    new_id, created = await store.find_or_create_topic(
        label="Archive Me",
        session_id=session_id,
        topic_type="project"
    )
    assert created is True, "Should create new topic when old is archived"
    assert new_id != topic_id, "New topic should have different ID"


# --- topic type mapping tests -----------------------------------------------


@pytest.mark.asyncio
async def test_topic_type_project(store: SessionStore, session_id: str) -> None:
    """Test topic type 'project' is stored correctly."""
    topic_id = await store.create_topic(
        label="Project Topic",
        topic_type="project",
        scope="session",
        session_id=session_id
    )

    topics = await store.get_active_topics(session_id)
    assert topics[0]["type"] == "project"


@pytest.mark.asyncio
async def test_topic_type_research(store: SessionStore, session_id: str) -> None:
    """Test topic type 'research' is stored correctly."""
    topic_id = await store.create_topic(
        label="Research Topic",
        topic_type="research",
        scope="session",
        session_id=session_id
    )

    topics = await store.get_active_topics(session_id)
    assert topics[0]["type"] == "research"


@pytest.mark.asyncio
async def test_topic_type_personal(store: SessionStore, session_id: str) -> None:
    """Test topic type 'personal' is stored correctly."""
    topic_id = await store.create_topic(
        label="Personal Topic",
        topic_type="personal",
        scope="session",
        session_id=session_id
    )

    topics = await store.get_active_topics(session_id)
    assert topics[0]["type"] == "personal"


@pytest.mark.asyncio
async def test_topic_type_exception(store: SessionStore, session_id: str) -> None:
    """Test topic type 'exception' is stored correctly."""
    topic_id = await store.create_topic(
        label="Exception Topic",
        topic_type="exception",
        scope="session",
        session_id=session_id
    )

    topics = await store.get_active_topics(session_id)
    assert topics[0]["type"] == "exception"


@pytest.mark.asyncio
async def test_topic_type_compound(store: SessionStore, session_id: str) -> None:
    """Test topic type 'compound' is stored correctly."""
    topic_id = await store.create_topic(
        label="Compound Topic",
        topic_type="compound",
        scope="session",
        session_id=session_id
    )

    topics = await store.get_active_topics(session_id)
    assert topics[0]["type"] == "compound"


@pytest.mark.asyncio
async def test_all_topic_types_valid(store: SessionStore, session_id: str) -> None:
    """Test all valid topic types can be created."""
    valid_types = ("project", "research", "personal", "exception", "compound")

    for topic_type in valid_types:
        await store.create_topic(
            label=f"{topic_type.capitalize()} Topic",
            topic_type=topic_type,
            scope="session",
            session_id=session_id
        )

    topics = await store.get_active_topics(session_id)
    assert len(topics) == len(valid_types)

    # Verify each type was stored correctly
    stored_types = {t["type"] for t in topics}
    assert stored_types == set(valid_types)


# --- utterance persistence tests --------------------------------------------


@pytest.mark.asyncio
async def test_create_utterance_basic(store: SessionStore, session_id: str) -> None:
    """Test basic utterance creation."""
    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="hello world"
    )

    assert isinstance(utterance_id, str), "Utterance ID should be string"
    assert len(utterance_id) > 0, "Utterance ID should not be empty"

    # Verify it was persisted
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM utterances WHERE id = ?",
            (utterance_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None, "Utterance should be persisted"
            assert row["session_id"] == session_id
            assert row["raw_text"] == "hello world"


@pytest.mark.asyncio
async def test_create_utterance_with_custom_id(store: SessionStore, session_id: str) -> None:
    """Test utterance creation with custom ID."""
    custom_id = "custom-utterance-id"
    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="test utterance",
        utterance_id=custom_id
    )

    assert utterance_id == custom_id, "Should use custom ID"

    # Verify it was persisted with custom ID
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM utterances WHERE id = ?",
            (custom_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None


@pytest.mark.asyncio
async def test_create_utterance_for_topic(store: SessionStore, session_id: str) -> None:
    """Test utterance is persisted to the correct session/topic context."""
    # Create multiple sessions
    session1 = session_id
    session2 = await store.create_session()

    # Create utterance in session1
    utterance1_id = await store.create_utterance(
        session_id=session1,
        raw_text="session1 message"
    )

    # Create utterance in session2
    utterance2_id = await store.create_utterance(
        session_id=session2,
        raw_text="session2 message"
    )

    # Verify utterances are in correct sessions
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check session1 utterance
        async with db.execute(
            "SELECT * FROM utterances WHERE id = ?",
            (utterance1_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row["session_id"] == session1
            assert row["raw_text"] == "session1 message"

        # Check session2 utterance
        async with db.execute(
            "SELECT * FROM utterances WHERE id = ?",
            (utterance2_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row["session_id"] == session2
            assert row["raw_text"] == "session2 message"


@pytest.mark.asyncio
async def test_create_multiple_utterances(store: SessionStore, session_id: str) -> None:
    """Test creating multiple utterances in a session."""
    utterances = []
    for i in range(5):
        utterance_id = await store.create_utterance(
            session_id=session_id,
            raw_text=f"message {i}"
        )
        utterances.append(utterance_id)

    # Verify all were persisted
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM utterances WHERE session_id = ?",
            (session_id,)
        ) as cur:
            rows = await cur.fetchall()
            assert len(rows) == 5, "Should have 5 utterances"


# --- independent session operations tests -------------------------------------


@pytest.mark.asyncio
async def test_independent_session_isolation(store: SessionStore) -> None:
    """Test that session.store operations work independently across sessions."""
    # Create two independent sessions
    session1 = await store.create_session()
    session2 = await store.create_session()

    # Create topics in each session
    topic1_id = await store.create_topic(
        label="Session1 Topic",
        topic_type="project",
        scope="session",
        session_id=session1
    )

    topic2_id = await store.create_topic(
        label="Session2 Topic",
        topic_type="research",
        scope="session",
        session_id=session2
    )

    # Create utterances in each session
    utterance1_id = await store.create_utterance(
        session_id=session1,
        raw_text="session1 utterance"
    )

    utterance2_id = await store.create_utterance(
        session_id=session2,
        raw_text="session2 utterance"
    )

    # Verify session isolation
    # Session1 should only see its own data
    topics1 = await store.get_active_topics(session1)
    assert len(topics1) == 1, "Session1 should have 1 topic"
    assert topics1[0]["id"] == topic1_id

    # Session2 should only see its own data
    topics2 = await store.get_active_topics(session2)
    assert len(topics2) == 1, "Session2 should have 1 topic"
    assert topics2[0]["id"] == topic2_id

    # Verify utterances are isolated
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Session1 utterance
        async with db.execute(
            "SELECT session_id FROM utterances WHERE id = ?",
            (utterance1_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row["session_id"] == session1

        # Session2 utterance
        async with db.execute(
            "SELECT session_id FROM utterances WHERE id = ?",
            (utterance2_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row["session_id"] == session2


@pytest.mark.asyncio
async def test_delete_session_does_not_affect_other_sessions(store: SessionStore) -> None:
    """Test deleting one session doesn't affect other sessions."""
    session1 = await store.create_session()
    session2 = await store.create_session()

    # Create data in both sessions
    topic1_id = await store.create_topic(
        label="Session1 Topic",
        topic_type="project",
        scope="session",
        session_id=session1
    )

    topic2_id = await store.create_topic(
        label="Session2 Topic",
        topic_type="project",
        scope="session",
        session_id=session2
    )

    # Delete session1
    result = await store.delete_session(session1)
    assert result["session_removed"] == 1
    assert result["topics_removed"] == 1

    # Session2 should still have its topic
    topics2 = await store.get_active_topics(session2)
    assert len(topics2) == 1, "Session2 should still have its topic"
    assert topics2[0]["id"] == topic2_id


# --- datetime import fix -----------------------------------------------------

from datetime import datetime  # noqa: E402 (needed for archived test)
