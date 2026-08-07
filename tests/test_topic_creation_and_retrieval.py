"""
Topic creation and retrieval tests.

Tests for find_or_create_topic() and get_topic() functionality.

Acceptance criteria:
- Test that find_or_create_topic() creates a new topic on first call
- Test that find_or_create_topic() returns existing topic on duplicate
- Test that topic type is stored correctly
- Test that topic retrieval returns all fields

Scope: Tests for find_or_create_topic() and topic retrieval only.
Does not test results or utterances.
"""

import pytest

from src.session.store import SessionStore


# -----------------------------------------------------------------------------
# Topic creation tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_or_create_topic_creates_new_topic_on_first_call(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that find_or_create_topic() creates a new topic on first call."""
    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="Test Topic",
        session_id=in_memory_db_session_id,
        topic_type="adhoc",
        project_slugs=None,
        scope="session",
    )

    # Verify creation flag is True
    assert created is True, "Should have created a new topic"

    # Verify topic_id is not empty
    assert topic_id is not None
    assert len(topic_id) > 0, "Topic ID should not be empty"

    # Verify the topic actually exists in the database
    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None, "Topic should exist in database"
    assert topic["label"] == "Test Topic"
    assert topic["type"] == "adhoc"


@pytest.mark.asyncio
async def test_find_or_create_topic_returns_existing_topic_on_duplicate(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that find_or_create_topic() returns existing topic on duplicate."""
    label = "Duplicate Test Topic"

    # First call should create
    first_topic_id, first_created = await in_memory_db_store.find_or_create_topic(
        label=label,
        session_id=in_memory_db_session_id,
        topic_type="personal",
        project_slugs=None,
        scope="session",
    )

    assert first_created is True, "First call should create topic"

    # Second call with same label and session should return existing
    second_topic_id, second_created = await in_memory_db_store.find_or_create_topic(
        label=label,
        session_id=in_memory_db_session_id,
        topic_type="personal",
        project_slugs=None,
        scope="session",
    )

    assert second_created is False, "Second call should not create new topic"
    assert second_topic_id == first_topic_id, "Should return same topic ID"

    # Verify only one topic exists
    topics = await in_memory_db_store.get_active_topics(in_memory_db_session_id)
    # Filter to only our test topic
    matching_topics = [t for t in topics if t["label"] == label]
    assert len(matching_topics) == 1, "Should have exactly one topic with this label"


@pytest.mark.asyncio
async def test_find_or_create_topic_different_sessions_create_different_topics(in_memory_db_store) -> None:
    """Test that session-scoped topics with same label in different sessions are different."""
    label = "Session Topic"

    # Create first session
    session_id_1 = await in_memory_db_store.create_session()

    # Create topic in first session
    topic_id_1, created_1 = await in_memory_db_store.find_or_create_topic(
        label=label,
        session_id=session_id_1,
        topic_type="personal",
        project_slugs=None,
        scope="session",
    )

    assert created_1 is True

    # Create second session
    session_id_2 = await in_memory_db_store.create_session()

    # Create topic with same label in second session
    topic_id_2, created_2 = await in_memory_db_store.find_or_create_topic(
        label=label,
        session_id=session_id_2,
        topic_type="personal",
        project_slugs=None,
        scope="session",
    )

    assert created_2 is True, "Should create new topic in different session"
    assert topic_id_2 != topic_id_1, "Topics should have different IDs"

    # Verify both topics exist independently
    topic_1 = await in_memory_db_store.get_topic(topic_id_1)
    topic_2 = await in_memory_db_store.get_topic(topic_id_2)

    assert topic_1 is not None
    assert topic_2 is not None
    assert topic_1["label"] == topic_2["label"]
    assert topic_1["session_id"] == session_id_1
    assert topic_2["session_id"] == session_id_2


# -----------------------------------------------------------------------------
# Topic type storage tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topic_type_stored_correctly_project(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that 'project' topic type is stored correctly."""
    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="pbx-web",
        session_id=in_memory_db_session_id,
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="cross-session",
    )

    assert created is True

    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None
    assert topic["type"] == "project", "Topic type should be 'project'"


@pytest.mark.asyncio
async def test_topic_type_stored_correctly_research(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that 'research' topic type is stored correctly."""
    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="Performance Research",
        session_id=in_memory_db_session_id,
        topic_type="research",
        project_slugs=None,
        scope="session",
    )

    assert created is True

    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None
    assert topic["type"] == "research", "Topic type should be 'research'"


@pytest.mark.asyncio
async def test_topic_type_stored_correctly_personal(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that 'personal' topic type is stored correctly."""
    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="Personal Task",
        session_id=in_memory_db_session_id,
        topic_type="personal",
        project_slugs=None,
        scope="session",
    )

    assert created is True

    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None
    assert topic["type"] == "personal", "Topic type should be 'personal'"


@pytest.mark.asyncio
async def test_topic_type_stored_correctly_exception(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that 'exception' topic type is stored correctly."""
    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="System Error",
        session_id=in_memory_db_session_id,
        topic_type="exception",
        project_slugs=None,
        scope="session",
    )

    assert created is True

    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None
    assert topic["type"] == "exception", "Topic type should be 'exception'"


@pytest.mark.asyncio
async def test_topic_type_stored_correctly_compound(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that 'compound' topic type is stored correctly."""
    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="Multi-faceted Issue",
        session_id=in_memory_db_session_id,
        topic_type="compound",
        project_slugs=None,
        scope="session",
    )

    assert created is True

    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None
    assert topic["type"] == "compound", "Topic type should be 'compound'"


@pytest.mark.asyncio
async def test_topic_type_stored_correctly_adhoc(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that 'adhoc' topic type is stored correctly (default)."""
    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="Ad Hoc Task",
        session_id=in_memory_db_session_id,
        topic_type="adhoc",
        project_slugs=None,
        scope="session",
    )

    assert created is True

    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None
    assert topic["type"] == "adhoc", "Topic type should be 'adhoc'"


# -----------------------------------------------------------------------------
# Topic retrieval tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_topic_returns_all_fields(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that topic retrieval returns all expected fields."""
    import json

    # Create a topic with specific parameters
    expected_label = "Complete Topic Test"
    expected_type = "project"
    expected_project_slugs = ["pbx-web", "whisper-stt"]
    expected_scope = "session"

    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label=expected_label,
        session_id=in_memory_db_session_id,
        topic_type=expected_type,
        project_slugs=expected_project_slugs,
        scope=expected_scope,
    )

    assert created is True

    # Retrieve the topic
    topic = await in_memory_db_store.get_topic(topic_id)

    assert topic is not None, "Topic should exist"

    # Verify all expected fields are present
    expected_fields = {
        "id", "label", "type", "project_slugs", "scope",
        "session_id", "created_at", "last_active", "archived_at"
    }

    actual_fields = set(topic.keys())
    assert actual_fields == expected_fields, f"Missing fields: {expected_fields - actual_fields}, Extra fields: {actual_fields - expected_fields}"

    # Verify field values
    assert topic["id"] == topic_id
    assert topic["label"] == expected_label
    assert topic["type"] == expected_type
    assert topic["scope"] == expected_scope
    assert topic["session_id"] == in_memory_db_session_id
    assert topic["created_at"] is not None
    assert topic["last_active"] is not None
    assert topic["archived_at"] is None

    # Verify project_slugs is a list (parsed from JSON)
    assert isinstance(topic["project_slugs"], list)
    assert topic["project_slugs"] == expected_project_slugs


@pytest.mark.asyncio
async def test_get_topic_returns_project_slugs_as_list(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that project_slugs field is returned as a list (parsed from JSON)."""
    expected_slugs = ["project-a", "project-b", "project-c"]

    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="Multi-Project Topic",
        session_id=in_memory_db_session_id,
        topic_type="project",
        project_slugs=expected_slugs,
        scope="session",
    )

    assert created is True

    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None

    # Verify project_slugs is a list
    assert isinstance(topic["project_slugs"], list), "project_slugs should be a list"
    assert topic["project_slugs"] == expected_slugs


@pytest.mark.asyncio
async def test_get_topic_with_empty_project_slugs(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that get_topic handles empty project_slugs correctly."""
    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="No Project Topic",
        session_id=in_memory_db_session_id,
        topic_type="personal",
        project_slugs=None,
        scope="session",
    )

    assert created is True

    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None

    # project_slugs should be an empty list when None was passed
    assert isinstance(topic["project_slugs"], list)
    assert topic["project_slugs"] == []


@pytest.mark.asyncio
async def test_get_topic_nonexistent_returns_none(in_memory_db_store) -> None:
    """Test that get_topic returns None for nonexistent topic ID."""
    # Use a UUID that likely doesn't exist
    fake_topic_id = "00000000-0000-0000-0000-000000000000"

    topic = await in_memory_db_store.get_topic(fake_topic_id)
    assert topic is None, "Should return None for nonexistent topic"


@pytest.mark.asyncio
async def test_get_topic_timestamps_are_integers(in_memory_db_store, in_memory_db_session_id) -> None:
    """Test that created_at and last_active timestamps are integers."""
    topic_id, created = await in_memory_db_store.find_or_create_topic(
        label="Timestamp Test",
        session_id=in_memory_db_session_id,
        topic_type="adhoc",
        project_slugs=None,
        scope="session",
    )

    assert created is True

    topic = await in_memory_db_store.get_topic(topic_id)
    assert topic is not None

    # Verify timestamps are integers
    assert isinstance(topic["created_at"], int)
    assert isinstance(topic["last_active"], int)

    # Verify timestamps are reasonable (not in the distant past or future)
    import time
    now = int(time.time())
    assert topic["created_at"] <= now, "created_at should not be in the future"
    assert topic["created_at"] > now - 3600, "created_at should be within last hour"
    assert topic["last_active"] <= now, "last_active should not be in the future"
    assert topic["last_active"] > now - 3600, "last_active should be within last hour"


# -----------------------------------------------------------------------------
# Cross-session topic tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_session_topic_reused_across_sessions(in_memory_db_store) -> None:
    """Test that cross-session topics are reused across different sessions."""
    label = "Cross-Session Topic"

    # Create first session and topic
    session_id_1 = await in_memory_db_store.create_session()
    topic_id_1, created_1 = await in_memory_db_store.find_or_create_topic(
        label=label,
        session_id=session_id_1,
        topic_type="project",
        project_slugs=["test-project"],
        scope="cross-session",
    )

    assert created_1 is True, "Should create new cross-session topic"

    # Create second session
    session_id_2 = await in_memory_db_store.create_session()

    # Should reuse the same cross-session topic
    topic_id_2, created_2 = await in_memory_db_store.find_or_create_topic(
        label=label,
        session_id=session_id_2,
        topic_type="project",
        project_slugs=["test-project"],
        scope="cross-session",
    )

    assert created_2 is False, "Should reuse existing cross-session topic"
    assert topic_id_2 == topic_id_1, "Should return same topic ID"

    # Verify the topic has cross-session scope
    topic = await in_memory_db_store.get_topic(topic_id_1)
    assert topic is not None
    assert topic["scope"] == "cross-session"
    assert topic["session_id"] is None, "Cross-session topic should have NULL session_id"


@pytest.mark.asyncio
async def test_cross_session_topic_session_scoped_not_reused(in_memory_db_store) -> None:
    """Test that session-scoped topics are NOT reused across sessions."""
    label = "Session-Scoped Topic"

    # Create first session and topic
    session_id_1 = await in_memory_db_store.create_session()
    topic_id_1, created_1 = await in_memory_db_store.find_or_create_topic(
        label=label,
        session_id=session_id_1,
        topic_type="personal",
        project_slugs=None,
        scope="session",
    )

    assert created_1 is True

    # Create second session
    session_id_2 = await in_memory_db_store.create_session()

    # Should create a NEW topic (session-scoped)
    topic_id_2, created_2 = await in_memory_db_store.find_or_create_topic(
        label=label,
        session_id=session_id_2,
        topic_type="personal",
        project_slugs=None,
        scope="session",
    )

    assert created_2 is True, "Should create new topic for session-scoped"
    assert topic_id_2 != topic_id_1, "Session-scoped topics should have different IDs"
