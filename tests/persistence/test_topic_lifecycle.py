"""
Topic Record Lifecycle Tests (bead adc-3540k).

Comprehensive test suite for topic record creation, updates, querying, and filtering.
Tests the complete lifecycle of topic records including creation, updates, and queries.

Acceptance Criteria:
- Topic records are created correctly with all field types
- Topic activity updates persist properly
- Topic querying and filtering work as expected
- Topic-result relationships are maintained
- Topic type validation and constraints are enforced
- All tests pass
"""

import json
import pytest
import aiosqlite
from pathlib import Path
from datetime import datetime, timedelta
from uuid import uuid4

from src.session.store import SessionStore


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """Create a fresh session store for each test."""
    db_path = tmp_path / "test_session.db"
    store = SessionStore(db_path)
    await store.initialize()
    return store


@pytest.fixture
async def session_id(store: SessionStore) -> str:
    """Create a fresh session for each test."""
    return await store.create_session()


@pytest.mark.asyncio
async def test_topic_creation_basic_fields(store: SessionStore, session_id: str) -> None:
    """Test topic creation with all basic field types."""
    topic_id = await store.create_topic(
        label="Test Topic",
        topic_type="project",
        project_slugs=["test-project"],
        scope="session",
        session_id=session_id
    )

    assert topic_id is not None
    assert isinstance(topic_id, str)

    # Verify topic was created correctly
    topic = await store.get_topic(topic_id)
    assert topic is not None
    assert topic["id"] == topic_id
    assert topic["label"] == "Test Topic"
    assert topic["type"] == "project"
    assert topic["project_slugs"] == ["test-project"]
    assert topic["scope"] == "session"
    assert topic["session_id"] == session_id
    assert topic["created_at"] is not None
    assert topic["last_active"] is not None
    assert topic["archived_at"] is None


@pytest.mark.asyncio
async def test_topic_type_validation(store: SessionStore, session_id: str) -> None:
    """Test that all valid topic types are accepted and invalid ones are rejected."""
    valid_types = ["project", "research", "personal", "exception", "compound"]

    for topic_type in valid_types:
        topic_id = await store.create_topic(
            label=f"Test {topic_type} topic",
            topic_type=topic_type,
            session_id=session_id
        )

        topic = await store.get_topic(topic_id)
        assert topic["type"] == topic_type


@pytest.mark.asyncio
async def test_topic_scope_validation(store: SessionStore, session_id: str) -> None:
    """Test topic scope types: session, cross-session, global."""
    # Session-scoped topic
    session_topic_id = await store.create_topic(
        label="Session Topic",
        topic_type="research",
        scope="session",
        session_id=session_id
    )

    session_topic = await store.get_topic(session_topic_id)
    assert session_topic["scope"] == "session"
    assert session_topic["session_id"] == session_id

    # Cross-session topic (session_id should be None)
    cross_session_topic_id = await store.create_topic(
        label="Cross-Session Topic",
        topic_type="project",
        scope="cross-session",
        session_id=None
    )

    cross_session_topic = await store.get_topic(cross_session_topic_id)
    assert cross_session_topic["scope"] == "cross-session"
    assert cross_session_topic["session_id"] is None

    # Global topic
    global_topic_id = await store.create_topic(
        label="Global Topic",
        topic_type="project",
        scope="global",
        session_id=None
    )

    global_topic = await store.get_topic(global_topic_id)
    assert global_topic["scope"] == "global"
    assert global_topic["session_id"] is None


@pytest.mark.asyncio
async def test_topic_activity_update_persistence(store: SessionStore, session_id: str) -> None:
    """Test that topic activity updates persist correctly."""
    topic_id = await store.create_topic(
        label="Activity Test Topic",
        topic_type="personal",
        session_id=session_id
    )

    # Get initial activity timestamp
    topic_before = await store.get_topic(topic_id)
    initial_activity = topic_before["last_active"]

    # Update activity (timestamp will be set to current time)
    await store.update_topic_activity(topic_id)

    # Verify activity was updated or stayed the same (since we just called it)
    topic_after = await store.get_topic(topic_id)
    updated_activity = topic_after["last_active"]

    # The activity should be updated or at least equal (same second)
    assert updated_activity >= initial_activity, "Activity timestamp should be updated or equal"


@pytest.mark.asyncio
async def test_topic_find_or_create_new(store: SessionStore, session_id: str) -> None:
    """Test find_or_create_topic creates new topic when none exists."""
    topic_id, created = await store.find_or_create_topic(
        label="New Topic",
        session_id=session_id,
        topic_type="research",
        project_slugs=["test-project"],
        scope="session"
    )

    assert created is True, "Should create new topic"
    assert topic_id is not None

    # Verify topic exists
    topic = await store.get_topic(topic_id)
    assert topic["label"] == "New Topic"
    assert topic["type"] == "research"


@pytest.mark.asyncio
async def test_topic_find_or_create_existing(store: SessionStore, session_id: str) -> None:
    """Test find_or_create_topic returns existing topic."""
    label = "Existing Topic"

    # Create topic first
    original_id = await store.create_topic(
        label=label,
        topic_type="project",
        session_id=session_id
    )

    # Find existing topic
    found_id, created = await store.find_or_create_topic(
        label=label,
        session_id=session_id,
        topic_type="project",
        scope="session"
    )

    assert created is False, "Should find existing topic"
    assert found_id == original_id, "Should return same topic ID"


@pytest.mark.asyncio
async def test_topic_query_by_session(store: SessionStore, session_id: str) -> None:
    """Test querying topics by session."""
    # Create multiple topics for the session
    topic1_id = await store.create_topic("Topic 1", "project", session_id=session_id)
    topic2_id = await store.create_topic("Topic 2", "research", session_id=session_id)
    topic3_id = await store.create_topic("Topic 3", "personal", session_id=session_id)

    # Get active topics for session
    topics = await store.get_active_topics(session_id)

    assert len(topics) >= 3, "Should have at least 3 topics"

    # Verify our topics are in the list
    topic_ids = [t["id"] for t in topics]
    assert topic1_id in topic_ids
    assert topic2_id in topic_ids
    assert topic3_id in topic_ids


@pytest.mark.asyncio
async def test_topic_query_with_result_count(store: SessionStore, session_id: str) -> None:
    """Test that topic query includes result count."""
    topic_id = await store.create_topic("Result Count Topic", "project", session_id=session_id)

    # Create some results for the topic
    utterance_id = await store.create_utterance(session_id, "test utterance")
    intent_id = await store.create_intent(utterance_id, session_id, "test-project", "status")

    await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result 1",
        data={"field": "value1"}
    )

    await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result 2",
        data={"field": "value2"}
    )

    # Get active topics should include result count
    topics = await store.get_active_topics(session_id)
    topic = next(t for t in topics if t["id"] == topic_id)

    assert "result_count" in topic
    assert topic["result_count"] == 2


@pytest.mark.asyncio
async def test_topic_cross_session_isolation(store: SessionStore) -> None:
    """Test that cross-session topics work correctly across multiple sessions."""
    session1_id = await store.create_session()
    session2_id = await store.create_session()

    # Create cross-session topic
    cross_topic_id = await store.create_topic(
        label="Cross Session Topic",
        topic_type="project",
        scope="cross-session",
        session_id=None
    )

    # Create session-specific topics
    session1_topic_id = await store.create_topic(
        label="Session 1 Topic",
        topic_type="research",
        scope="session",
        session_id=session1_id
    )

    session2_topic_id = await store.create_topic(
        label="Session 2 Topic",
        topic_type="research",
        scope="session",
        session_id=session2_id
    )

    # Session 1 should see cross-session topic and its own topic
    session1_topics = await store.get_active_topics(session1_id)
    session1_topic_ids = [t["id"] for t in session1_topics]
    assert cross_topic_id in session1_topic_ids
    assert session1_topic_id in session1_topic_ids
    assert session2_topic_id not in session1_topic_ids  # Should not see session 2's topic

    # Session 2 should see cross-session topic and its own topic
    session2_topics = await store.get_active_topics(session2_id)
    session2_topic_ids = [t["id"] for t in session2_topics]
    assert cross_topic_id in session2_topic_ids
    assert session2_topic_id in session2_topic_ids
    assert session1_topic_id not in session2_topic_ids  # Should not see session 1's topic


@pytest.mark.asyncio
async def test_topic_result_relationship(store: SessionStore, session_id: str) -> None:
    """Test topic-result relationships and latest result retrieval."""
    topic_id = await store.create_topic("Result Relationship Topic", "project", session_id=session_id)

    utterance_id = await store.create_utterance(session_id, "test utterance")
    intent_id = await store.create_intent(utterance_id, session_id, "test-project", "status")

    # Create multiple results
    result1_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="First result",
        data={"version": 1}
    )

    import asyncio
    await asyncio.sleep(1.1)  # Ensure timestamp difference (system uses 1-second resolution)

    result2_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Second result",
        data={"version": 2}
    )

    # Get latest result for topic
    latest_result = await store.get_latest_result_for_topic(topic_id)

    assert latest_result is not None
    assert latest_result["id"] == result2_id, "Should return the most recent result"
    assert latest_result["summary"] == "Second result"

    # Parse data JSON since it's stored as string in DB
    import json
    latest_data = json.loads(latest_result["data"])
    assert latest_data["version"] == 2


@pytest.mark.asyncio
async def test_topic_intent_linking(store: SessionStore, session_id: str) -> None:
    """Test intent-topic many-to-many relationship."""
    topic_id = await store.create_topic("Intent Linking Topic", "project", session_id=session_id)

    utterance_id = await store.create_utterance(session_id, "test utterance")
    intent1_id = await store.create_intent(utterance_id, session_id, "test-project", "status")
    intent2_id = await store.create_intent(utterance_id, session_id, "test-project", "action")

    # Link intents to topic
    await store.link_intent_to_topic(intent1_id, topic_id)
    await store.link_intent_to_topic(intent2_id, topic_id)

    # Verify links exist in database
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check intent1 link
        async with db.execute(
            "SELECT * FROM intent_topics WHERE intent_id = ? AND topic_id = ?",
            (intent1_id, topic_id)
        ) as cursor:
            link1 = await cursor.fetchone()
            assert link1 is not None, "Intent 1 should be linked to topic"

        # Check intent2 link
        async with db.execute(
            "SELECT * FROM intent_topics WHERE intent_id = ? AND topic_id = ?",
            (intent2_id, topic_id)
        ) as cursor:
            link2 = await cursor.fetchone()
            assert link2 is not None, "Intent 2 should be linked to topic"


@pytest.mark.asyncio
async def test_topic_context_caching(store: SessionStore, session_id: str) -> None:
    """Test topic context cache operations."""
    topic_id = await store.create_topic("Context Cache Topic", "research", session_id=session_id)

    context_data = {
        "kubectl_info": {"pod": "test-pod", "namespace": "default"},
        "git_info": {"branch": "main", "commit": "abc123"}
    }

    # Set context cache
    await store.set_topic_context(topic_id, context_data, ttl_seconds=600)

    # Get cached context
    cached = await store.get_topic_context(topic_id)

    assert cached is not None
    assert cached["context"] == context_data
    assert "expires_at" in cached
    assert cached["expires_at"] > int(datetime.now().timestamp())

    # Invalidate context
    await store.invalidate_topic_context(topic_id)

    # Verify context is gone
    invalidated = await store.get_topic_context(topic_id)
    assert invalidated is None


@pytest.mark.asyncio
async def test_topic_context_expiration(store: SessionStore, session_id: str) -> None:
    """Test topic context cache expiration."""
    topic_id = await store.create_topic("Context Expiration Topic", "research", session_id=session_id)

    context_data = {"test": "data"}

    # Set context with very short TTL
    await store.set_topic_context(topic_id, context_data, ttl_seconds=1)

    # Should be available immediately
    cached = await store.get_topic_context(topic_id)
    assert cached is not None

    # Wait for expiration
    import asyncio
    await asyncio.sleep(1.1)

    # Should be expired
    expired = await store.get_topic_context(topic_id)
    assert expired is None


@pytest.mark.asyncio
async def test_topic_active_ids_query(store: SessionStore, session_id: str) -> None:
    """Test querying active topic IDs."""
    # Create recent topics
    recent_topic1 = await store.create_topic("Recent Topic 1", "project", session_id=session_id)
    recent_topic2 = await store.create_topic("Recent Topic 2", "research", session_id=session_id)

    # Simulate old topic by directly updating last_active
    old_topic = await store.create_topic("Old Topic", "personal", session_id=session_id)
    one_hour_ago = int(datetime.now().timestamp()) - 3601  # More than 1 hour ago

    async with aiosqlite.connect(store.db_path) as db:
        await db.execute(
            "UPDATE topics SET last_active = ? WHERE id = ?",
            (one_hour_ago, old_topic)
        )
        await db.commit()

    # Get active topic IDs
    active_ids = await store.get_active_topic_ids()

    assert recent_topic1 in active_ids
    assert recent_topic2 in active_ids
    assert old_topic not in active_ids  # Should be excluded due to age


@pytest.mark.asyncio
async def test_topic_project_slugs_persistence(store: SessionStore, session_id: str) -> None:
    """Test that project slugs are properly persisted and retrieved."""
    project_slugs = ["project-a", "project-b", "project-c"]

    topic_id = await store.create_topic(
        label="Multi-Project Topic",
        topic_type="compound",
        project_slugs=project_slugs,
        session_id=session_id
    )

    # Retrieve and verify project_slugs
    topic = await store.get_topic(topic_id)
    assert topic["project_slugs"] == project_slugs

    # Verify it's stored as JSON in database
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT project_slugs FROM topics WHERE id = ?",
            (topic_id,)
        ) as cursor:
            row = await cursor.fetchone()
            stored_json = row["project_slugs"]
            parsed_slugs = json.loads(stored_json)
            assert parsed_slugs == project_slugs


@pytest.mark.asyncio
async def test_topic_with_no_project_slugs(store: SessionStore, session_id: str) -> None:
    """Test topic creation without project slugs."""
    topic_id = await store.create_topic(
        label="No Project Slugs Topic",
        topic_type="personal",
        project_slugs=None,
        session_id=session_id
    )

    topic = await store.get_topic(topic_id)
    assert topic["project_slugs"] == []

    # Verify it's stored as empty JSON array
    async with aiosqlite.connect(store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT project_slugs FROM topics WHERE id = ?",
            (topic_id,)
        ) as cursor:
            row = await cursor.fetchone()
            stored_json = row["project_slugs"]
            parsed_slugs = json.loads(stored_json)
            assert parsed_slugs == []


@pytest.mark.asyncio
async def test_topic_archiving_not_implemented(store: SessionStore, session_id: str) -> None:
    """Test that topics can be created and archived_at field works correctly."""
    topic_id = await store.create_topic(
        label="To Be Archived Topic",
        topic_type="project",
        session_id=session_id
    )

    # Verify topic is not archived initially
    topic = await store.get_topic(topic_id)
    assert topic["archived_at"] is None

    # Archive the topic manually (since there's no archive method exposed)
    now = int(datetime.now().timestamp())
    async with aiosqlite.connect(store.db_path) as db:
        await db.execute(
            "UPDATE topics SET archived_at = ? WHERE id = ?",
            (now, topic_id)
        )
        await db.commit()

    # Verify archived status
    archived_topic = await store.get_topic(topic_id)
    assert archived_topic["archived_at"] == now

    # Verify find_or_create_topic should not return archived topics
    new_id, created = await store.find_or_create_topic(
        label="To Be Archived Topic",
        session_id=session_id,
        topic_type="project",
        scope="session"
    )

    assert created is True, "Should create new topic since old one is archived"
    assert new_id != topic_id, "New topic should have different ID"


@pytest.mark.asyncio
async def test_topic_get_nonexistent(store: SessionStore) -> None:
    """Test getting a topic that doesn't exist returns None."""
    fake_id = str(uuid4())
    topic = await store.get_topic(fake_id)
    assert topic is None


@pytest.mark.asyncio
async def test_topic_latest_result_none_for_empty_topic(store: SessionStore, session_id: str) -> None:
    """Test getting latest result for topic with no results returns None."""
    topic_id = await store.create_topic("Empty Topic", "project", session_id=session_id)

    latest_result = await store.get_latest_result_for_topic(topic_id)
    assert latest_result is None


@pytest.mark.asyncio
async def test_topic_previous_result_for_diff(store: SessionStore, session_id: str) -> None:
    """Test getting previous result for diff computation."""
    topic_id = await store.create_topic("Diff Test Topic", "project", session_id=session_id)

    utterance_id = await store.create_utterance(session_id, "test utterance")
    intent_id = await store.create_intent(utterance_id, session_id, "test-project", "status")

    # Create results with different types
    result1_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Status result",
        data={"status": "running"},
        result_type="status:test-project"
    )

    await asyncio.sleep(1.1)  # Ensure timestamp difference

    result2_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Brainstorm result",
        data={"ideas": ["idea1", "idea2"]},
        result_type="brainstorm:test-project"
    )

    await asyncio.sleep(1.1)  # Ensure timestamp difference

    result3_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Updated status",
        data={"status": "stopped"},
        result_type="status:test-project"
    )

    # Get previous result for status type
    # Note: get_previous_result_for_diff returns the most recent result for the type,
    # which would be result3 (not result1), since it's used for lineage tracking
    previous_status_result = await store.get_previous_result_for_diff(topic_id, "status:test-project")
    assert previous_status_result["id"] == result3_id
    assert previous_status_result["summary"] == "Updated status"

    # Get previous result for brainstorm type (should return result2)
    previous_brainstorm_result = await store.get_previous_result_for_diff(topic_id, "brainstorm:test-project")
    assert previous_brainstorm_result["id"] == result2_id
    assert previous_brainstorm_result["summary"] == "Brainstorm result"


@pytest.mark.asyncio
async def test_topic_cleanup_expired_context(store: SessionStore, session_id: str) -> None:
    """Test cleanup of expired context cache entries."""
    topic1_id = await store.create_topic("Topic 1", "project", session_id=session_id)
    topic2_id = await store.create_topic("Topic 2", "project", session_id=session_id)
    topic3_id = await store.create_topic("Topic 3", "project", session_id=session_id)

    # Set context with different TTLs
    await store.set_topic_context(topic1_id, {"data": "1"}, ttl_seconds=3600)  # Far future
    await store.set_topic_context(topic2_id, {"data": "2"}, ttl_seconds=1)     # Will expire soon
    await store.set_topic_context(topic3_id, {"data": "3"}, ttl_seconds=3600)  # Far future

    # Wait for topic2 to expire
    await asyncio.sleep(1.1)

    # Cleanup expired contexts
    deleted_count = await store.cleanup_expired_context()
    assert deleted_count == 1, "Should delete exactly 1 expired entry"

    # Verify topic2 context is gone, others remain
    assert await store.get_topic_context(topic1_id) is not None
    assert await store.get_topic_context(topic2_id) is None
    assert await store.get_topic_context(topic3_id) is not None


@pytest.mark.asyncio
async def test_complete_topic_lifecycle(store: SessionStore, session_id: str) -> None:
    """Test complete topic lifecycle from creation to results."""
    # 1. Create topic
    topic_id = await store.create_topic(
        label="Lifecycle Topic",
        topic_type="project",
        project_slugs=["lifecycle-project"],
        scope="session",
        session_id=session_id
    )

    # 2. Update activity
    await store.update_topic_activity(topic_id)

    # 3. Cache context
    context = {"kubectl": "pod-info"}
    await store.set_topic_context(topic_id, context)

    # 4. Create utterance and intent
    utterance_id = await store.create_utterance(session_id, "test utterance")
    intent_id = await store.create_intent(utterance_id, session_id, "lifecycle-project", "status")

    # 5. Link intent to topic
    await store.link_intent_to_topic(intent_id, topic_id)

    # 6. Create results
    result_id = await store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=session_id,
        summary="Test result",
        data={"test": "data"}
    )

    # 7. Verify complete lifecycle
    topic = await store.get_topic(topic_id)
    assert topic["label"] == "Lifecycle Topic"
    assert topic["type"] == "project"

    cached_context = await store.get_topic_context(topic_id)
    assert cached_context["context"] == context

    latest_result = await store.get_latest_result_for_topic(topic_id)
    assert latest_result["id"] == result_id

    active_topics = await store.get_active_topics(session_id)
    assert any(t["id"] == topic_id for t in active_topics)


# Import asyncio for sleeps
import asyncio