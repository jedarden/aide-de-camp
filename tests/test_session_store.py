"""
Session store unit tests (bead adc-3ttx0, bead adc-cmzj5).

Tests core CRUD operations for SQLite session store:
- Topic creation and retrieval
- find_or_create_topic idempotency
- Utterance persistence
- Topic type mapping
- Independent session.store operations
- Card dismissal (delete_result) operations

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


# --- card dismissal tests (bead adc-cmzj5) --------------------------------------


@pytest.mark.asyncio
async def test_delete_result_basic(store: SessionStore, session_id: str) -> None:
    """Test basic result deletion by ID."""
    # Create a topic and result
    topic_id = await store.create_topic(
        label="Dismiss Test Topic",
        topic_type="project",
        scope="session",
        session_id=session_id
    )

    result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result to dismiss",
        data={"message": "This will be deleted"},
        urgency="normal"
    )

    # Verify result exists
    result_before = await store.get_latest_result_for_topic(topic_id)
    assert result_before is not None
    assert result_before["id"] == result_id

    # Delete the result
    delete_response = await store.delete_result(result_id, session_id)
    assert delete_response["result_deleted"] == 1

    # Verify result is gone
    result_after = await store.get_latest_result_for_topic(topic_id)
    assert result_after is None


@pytest.mark.asyncio
async def test_delete_stuck_card_from_results(store: SessionStore, session_id: str) -> None:
    """Test stuck card removal from results (bead adc-cmzj5)."""
    # Create topic, utterance, and intent for stuck card
    topic_id = await store.create_topic(
        label="Stuck Card Test",
        topic_type="exception",
        scope="session",
        session_id=session_id
    )

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="test stuck task"
    )

    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref="adc-stuck-test",
        lookup_kind=None,
        topic_id=topic_id
    )

    # Update intent to stuck status
    await store.update_intent_type_and_status(
        intent_id=intent_id,
        intent_type="stuck",
        status="stuck"
    )

    # Create stuck card result
    stuck_result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Task stuck — needs your input",
        data={
            "bead_id": "adc-stuck-test",
            "stuck_reason": "Missing required information",
            "refusal_count": 3,
            "message": "This task has been blocked after 3 refusals.",
            "action_hint": "Review the bead and provide missing information."
        },
        urgency="high"
    )

    # Verify stuck card exists
    stuck_result_before = await store.get_latest_result_for_topic(topic_id)
    assert stuck_result_before is not None
    assert stuck_result_before["id"] == stuck_result_id
    assert stuck_result_before["summary"] == "Task stuck — needs your input"
    result_data = json.loads(stuck_result_before["data"])
    assert result_data["bead_id"] == "adc-stuck-test"
    assert result_data["refusal_count"] == 3

    # Delete stuck card
    delete_response = await store.delete_result(stuck_result_id, session_id)
    assert delete_response["result_deleted"] == 1

    # Verify stuck card is removed
    stuck_result_after = await store.get_latest_result_for_topic(topic_id)
    assert stuck_result_after is None

    # Verify intent still exists (deleting result doesn't delete intent)
    intent = await store.get_intent(intent_id)
    assert intent is not None
    assert intent["status"] == "stuck"


@pytest.mark.asyncio
async def test_delete_failed_card_from_results(store: SessionStore, session_id: str) -> None:
    """Test failed card removal from results (bead adc-cmzj5)."""
    # Create topic, utterance, and intent for failed card
    topic_id = await store.create_topic(
        label="Failed Card Test",
        topic_type="exception",
        scope="session",
        session_id=session_id
    )

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="test failed task"
    )

    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="adc",
        intent_type="action",
        bead_ref="adc-failed-test",
        lookup_kind=None,
        topic_id=topic_id
    )

    # Update intent to failed status
    await store.update_intent_status(intent_id=intent_id, status="failed")

    # Create failed card result
    failed_result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Task Failed: Worker Crash",
        data={
            "bead_ref": "adc-failed-test",
            "failure_reason": "Worker process crashed",
            "error_type": "worker_crash",
            "message": "Task failed due to worker crash.",
            "action_hint": "Check system logs and retry."
        },
        urgency="high"
    )

    # Verify failed card exists
    failed_result_before = await store.get_latest_result_for_topic(topic_id)
    assert failed_result_before is not None
    assert failed_result_before["id"] == failed_result_id
    assert failed_result_before["summary"] == "Task Failed: Worker Crash"
    result_data = json.loads(failed_result_before["data"])
    assert result_data["bead_ref"] == "adc-failed-test"
    assert result_data["error_type"] == "worker_crash"

    # Delete failed card
    delete_response = await store.delete_result(failed_result_id, session_id)
    assert delete_response["result_deleted"] == 1

    # Verify failed card is removed
    failed_result_after = await store.get_latest_result_for_topic(topic_id)
    assert failed_result_after is None

    # Verify intent still exists
    intent = await store.get_intent(intent_id)
    assert intent is not None
    assert intent["status"] == "failed"


@pytest.mark.asyncio
async def test_delete_result_data_integrity_before_after(store: SessionStore, session_id: str) -> None:
    """Test result data integrity before and after dismissal (bead adc-cmzj5)."""
    # Create multiple results for a topic
    topic_id = await store.create_topic(
        label="Integrity Test Topic",
        topic_type="project",
        scope="session",
        session_id=session_id
    )

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="integrity test"
    )

    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test",
        intent_type="status",
        lookup_kind=None,
        topic_id=topic_id
    )

    # Create first result
    result1_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="First result",
        data={"count": 1, "status": "active"},
        urgency="normal"
    )

    # Create second result
    result2_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Second result",
        data={"count": 2, "status": "pending"},
        urgency="normal"
    )

    # Verify both results exist via intent query
    results_for_intent = await store.get_results_for_intent(intent_id)
    assert len(results_for_intent) == 2

    # Get the latest result (whichever one it is)
    latest_result = await store.get_latest_result_for_topic(topic_id)
    assert latest_result is not None
    latest_result_id_before = latest_result["id"]

    # Determine which result to delete (the one that's currently latest)
    result_to_delete = latest_result_id_before
    remaining_result_id = result1_id if result_to_delete == result2_id else result2_id
    remaining_summary = "First result" if result_to_delete == result2_id else "Second result"
    remaining_count = 1 if result_to_delete == result2_id else 2
    remaining_status = "active" if result_to_delete == result2_id else "pending"

    # Delete the latest result
    delete_response = await store.delete_result(result_to_delete, session_id)
    assert delete_response["result_deleted"] == 1

    # Verify data integrity: only one result remains
    results_after = await store.get_results_for_intent(intent_id)
    assert len(results_after) == 1
    assert results_after[0]["id"] == remaining_result_id
    assert results_after[0]["summary"] == remaining_summary

    # Verify latest result is now the remaining one
    latest_after = await store.get_latest_result_for_topic(topic_id)
    assert latest_after is not None
    assert latest_after["id"] == remaining_result_id
    assert latest_after["summary"] == remaining_summary

    # Verify remaining result data is intact
    remaining_data = json.loads(latest_after["data"])
    assert remaining_data["count"] == remaining_count
    assert remaining_data["status"] == remaining_status


@pytest.mark.asyncio
async def test_delete_result_session_scoping(store: SessionStore) -> None:
    """Test delete_result is scoped to session (security check, bead adc-cmzj5)."""
    # Create two sessions
    session1 = await store.create_session()
    session2 = await store.create_session()

    # Create topics in both sessions
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

    # Create results in both sessions
    result1_id = await store.create_result(
        intent_id=None,
        topic_id=topic1_id,
        session_id=session1,
        summary="Session1 result",
        data={"session": "1"},
        urgency="normal"
    )

    result2_id = await store.create_result(
        intent_id=None,
        topic_id=topic2_id,
        session_id=session2,
        summary="Session2 result",
        data={"session": "2"},
        urgency="normal"
    )

    # Verify both results exist
    result1 = await store.get_latest_result_for_topic(topic1_id)
    result2 = await store.get_latest_result_for_topic(topic2_id)
    assert result1 is not None
    assert result2 is not None

    # Try to delete session2's result using session1 credentials (should fail)
    delete_response = await store.delete_result(result2_id, session1)
    assert delete_response["result_deleted"] == 0  # Not deleted, wrong session

    # Verify session2's result still exists
    result2_after = await store.get_latest_result_for_topic(topic2_id)
    assert result2_after is not None
    assert result2_after["id"] == result2_id

    # Delete session1's result using session1 credentials (should succeed)
    delete_response = await store.delete_result(result1_id, session1)
    assert delete_response["result_deleted"] == 1

    # Verify session1's result is gone
    result1_after = await store.get_latest_result_for_topic(topic1_id)
    assert result1_after is None


@pytest.mark.asyncio
async def test_delete_result_returns_zero_for_nonexistent(store: SessionStore, session_id: str) -> None:
    """Test delete_result returns 0 for nonexistent result (bead adc-cmzj5)."""
    # Try to delete a result that doesn't exist
    fake_result_id = "nonexistent-result-id"
    delete_response = await store.delete_result(fake_result_id, session_id)
    assert delete_response["result_deleted"] == 0


@pytest.mark.asyncio
async def test_delete_multiple_results_from_topic(store: SessionStore, session_id: str) -> None:
    """Test deleting multiple results from a topic (bead adc-cmzj5)."""
    topic_id = await store.create_topic(
        label="Multi-dismiss Topic",
        topic_type="project",
        scope="session",
        session_id=session_id
    )

    utterance_id = await store.create_utterance(
        session_id=session_id,
        raw_text="multiple results test"
    )

    intent_id = await store.create_intent(
        utterance_id=utterance_id,
        session_id=session_id,
        project_slug="test",
        intent_type="status",
        lookup_kind=None,
        topic_id=topic_id
    )

    # Create multiple results
    result_ids = []
    for i in range(3):
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=f"Result {i}",
            data={"index": i},
            urgency="normal"
        )
        result_ids.append(result_id)

    # Verify all 3 results exist
    results = await store.get_results_for_intent(intent_id)
    assert len(results) == 3

    # Delete results one by one
    for result_id in result_ids:
        delete_response = await store.delete_result(result_id, session_id)
        assert delete_response["result_deleted"] == 1

    # Verify all results are gone
    results_final = await store.get_results_for_intent(intent_id)
    assert len(results_final) == 0

    # Verify topic still exists
    topics = await store.get_active_topics(session_id)
    topic = next((t for t in topics if t["id"] == topic_id), None)
    assert topic is not None


@pytest.mark.asyncio
async def test_get_all_results_includes_dismissable_cards(store: SessionStore, session_id: str) -> None:
    """Test get_all_results includes stuck and failed cards (bead adc-cmzj5)."""
    # Create stuck card
    stuck_topic = await store.create_topic(
        label="Stuck Topic",
        topic_type="exception",
        scope="session",
        session_id=session_id
    )

    stuck_utterance = await store.create_utterance(
        session_id=session_id,
        raw_text="stuck test"
    )

    stuck_intent = await store.create_intent(
        utterance_id=stuck_utterance,
        session_id=session_id,
        project_slug="adc",
        intent_type="task-profile",
        bead_ref="adc-stuck-all",
        lookup_kind=None,
        topic_id=stuck_topic
    )

    await store.update_intent_type_and_status(
        intent_id=stuck_intent,
        intent_type="stuck",
        status="stuck"
    )

    stuck_result_id = await store.create_result(
        intent_id=stuck_intent,
        topic_id=stuck_topic,
        session_id=session_id,
        summary="Stuck card",
        data={"bead_id": "adc-stuck-all", "stuck_reason": "Test"},
        urgency="high"
    )

    # Create failed card
    failed_topic = await store.create_topic(
        label="Failed Topic",
        topic_type="exception",
        scope="session",
        session_id=session_id
    )

    failed_utterance = await store.create_utterance(
        session_id=session_id,
        raw_text="failed test"
    )

    failed_intent = await store.create_intent(
        utterance_id=failed_utterance,
        session_id=session_id,
        project_slug="adc",
        intent_type="action",
        bead_ref="adc-failed-all",
        lookup_kind=None,
        topic_id=failed_topic
    )

    await store.update_intent_status(intent_id=failed_intent, status="failed")

    failed_result_id = await store.create_result(
        intent_id=failed_intent,
        topic_id=failed_topic,
        session_id=session_id,
        summary="Failed card",
        data={"bead_ref": "adc-failed-all", "error_type": "test"},
        urgency="high"
    )

    # Verify get_all_results includes both cards
    all_results = await store.get_all_results()
    result_ids = [r["id"] for r in all_results]
    assert stuck_result_id in result_ids
    assert failed_result_id in result_ids

    # Delete stuck card
    await store.delete_result(stuck_result_id, session_id)

    # Verify stuck card is removed from all_results
    all_results_after = await store.get_all_results()
    result_ids_after = [r["id"] for r in all_results_after]
    assert stuck_result_id not in result_ids_after
    assert failed_result_id in result_ids_after

    # Delete failed card
    await store.delete_result(failed_result_id, session_id)

    # Verify failed card is also removed
    all_results_final = await store.get_all_results()
    result_ids_final = [r["id"] for r in all_results_final]
    assert failed_result_id not in result_ids_final
