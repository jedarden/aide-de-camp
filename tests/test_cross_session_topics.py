"""
Cross-session topic scope and session-scoped diff display tests.

Tests the plan's requirements for topic scope vs. session scope:
- Project topics are cross-session (scope='cross-session', session_id=NULL)
- Canvas displays only current session's results
- previous_result_id is pure lineage but diff strip renders ONLY when previous result is from current session
- A status result never diffs against a brainstorm result (different result_type)

Acceptance criteria:
1. Project topics created as cross-session
2. Fresh session reuses cross-session topics (same topic_id)
3. Step-1 dispatch in fresh session shows NO diff strip (previous_result from seed session ignored)
4. Step-6 follow-up in same session DOES show diff strip against step-1
5. Status result never diffs against brainstorm result (different result_type)
"""

import json
from pathlib import Path

import aiosqlite
import pytest

from src.session.store import SessionStore


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
async def store(tmp_path: Path) -> SessionStore:
    """An isolated SessionStore on a tmp DB."""
    db_path = tmp_path / "session.db"
    s = SessionStore(db_path)
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
async def seed_session(store: SessionStore) -> str:
    """Create a seed session for warming topics."""
    return await store.create_session()


@pytest.fixture
async def fresh_session(store: SessionStore) -> str:
    """Create a fresh session (simulates starting a new session after seeding)."""
    return await store.create_session()


# --- cross-session topic creation tests ---------------------------------------


@pytest.mark.asyncio
async def test_project_topic_created_as_cross_session(store: SessionStore, seed_session: str) -> None:
    """Test that project topics are created with scope='cross-session' and session_id=NULL."""
    topic_id, created = await store.find_or_create_topic(
        label="pbx-web",
        session_id=seed_session,
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="cross-session",
    )

    assert created is True, "Should have created new cross-session topic"

    # Verify topic is cross-session
    topics = await store.get_active_topics(seed_session)
    assert len(topics) == 1
    topic = topics[0]

    assert topic["id"] == topic_id
    assert topic["label"] == "pbx-web"
    assert topic["type"] == "project"
    assert topic["scope"] == "cross-session", "Project topic should be cross-session"
    assert topic["session_id"] is None, "Cross-session topic should have NULL session_id"


@pytest.mark.asyncio
async def test_cross_session_topic_reused_across_sessions(store: SessionStore, seed_session: str, fresh_session: str) -> None:
    """Test that cross-session topics are reused when starting a fresh session."""
    # Create cross-session topic in seed session
    seed_topic_id, created = await store.find_or_create_topic(
        label="pbx-web",
        session_id=seed_session,
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="cross-session",
    )
    assert created is True, "Should have created new topic in seed session"

    # Fresh session should reuse the same cross-session topic
    fresh_topic_id, created = await store.find_or_create_topic(
        label="pbx-web",
        session_id=fresh_session,
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="cross-session",
    )
    assert created is False, "Should have reused existing cross-session topic"
    assert fresh_topic_id == seed_topic_id, "Fresh session should reuse same topic ID"

    # Verify both sessions see the same topic
    seed_topics = await store.get_active_topics(seed_session)
    fresh_topics = await store.get_active_topics(fresh_session)

    assert len(seed_topics) == 1
    assert len(fresh_topics) == 1
    assert seed_topics[0]["id"] == fresh_topics[0]["id"]


@pytest.mark.asyncio
async def test_session_scoped_topic_not_reused_across_sessions(store: SessionStore, seed_session: str, fresh_session: str) -> None:
    """Test that session-scoped topics are NOT reused across sessions."""
    # Create session-scoped topic in seed session (using 'personal' which is valid type)
    seed_topic_id, created = await store.find_or_create_topic(
        label="Ad Hoc Task",
        session_id=seed_session,
        topic_type="personal",  # Use valid type instead of 'adhoc'
        project_slugs=[],
        scope="session",
    )
    assert created is True

    # Fresh session should create a NEW topic
    fresh_topic_id, created = await store.find_or_create_topic(
        label="Ad Hoc Task",
        session_id=fresh_session,
        topic_type="personal",  # Use valid type instead of 'adhoc'
        project_slugs=[],
        scope="session",
    )
    assert created is True, "Should have created new topic in fresh session"
    assert fresh_topic_id != seed_topic_id, "Session-scoped topics should have different IDs"


# --- get_previous_result_for_diff tests ---------------------------------------


@pytest.mark.asyncio
async def test_get_previous_result_for_diff_finds_same_result_type(store: SessionStore, seed_session: str) -> None:
    """Test that get_previous_result_for_diff finds results with same result_type."""
    import time

    # Create cross-session topic
    topic_id, _ = await store.find_or_create_topic(
        label="whisper-stt",
        session_id=seed_session,
        topic_type="project",
        project_slugs=["whisper-stt"],
        scope="cross-session",
    )

    # Create first result of type 'status:whisper-stt'
    first_result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=seed_session,
        summary="First result",
        data={"status": "running"},
        urgency="normal",
        result_type="status:whisper-stt",
    )

    # Ensure different timestamp for second result
    time.sleep(0.01)

    # Create second result of type 'status:whisper-stt'
    second_result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=seed_session,
        summary="Second result",
        data={"status": "stopped"},
        urgency="normal",
        result_type="status:whisper-stt",
    )

    # get_previous_result_for_diff should find the second result (most recent of same type)
    previous = await store.get_previous_result_for_diff(topic_id, "status:whisper-stt")
    assert previous is not None
    assert previous["id"] == second_result_id, f"Expected {second_result_id}, got {previous['id']}"
    assert previous["result_type"] == "status:whisper-stt"


@pytest.mark.asyncio
async def test_get_previous_result_for_diff_cross_session(store: SessionStore, seed_session: str, fresh_session: str) -> None:
    """Test that get_previous_result_for_diff finds results across sessions."""
    # Create cross-session topic
    topic_id, _ = await store.find_or_create_topic(
        label="whisper-stt",
        session_id=seed_session,
        topic_type="project",
        project_slugs=["whisper-stt"],
        scope="cross-session",
    )

    # Create result in seed session
    seed_result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=seed_session,
        summary="Seed result",
        data={"status": "running"},
        urgency="normal",
        result_type="status:whisper-stt",
    )

    # Fresh session should find the previous result from seed session
    previous = await store.get_previous_result_for_diff(topic_id, "status:whisper-stt")
    assert previous is not None
    assert previous["id"] == seed_result_id
    assert previous["session_id"] == seed_session


@pytest.mark.asyncio
async def test_get_previous_result_for_diff_different_types(store: SessionStore, seed_session: str) -> None:
    """Test that get_previous_result_for_diff only finds results of same result_type."""
    topic_id, _ = await store.find_or_create_topic(
        label="pbx-web",
        session_id=seed_session,
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="cross-session",
    )

    # Create status result
    status_result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=seed_session,
        summary="Status result",
        data={"status": "healthy"},
        urgency="normal",
        result_type="status:pbx-web",
    )

    # Create brainstorm result
    brainstorm_result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=seed_session,
        summary="Brainstorm result",
        data={"ideas": ["idea1", "idea2"]},
        urgency="normal",
        result_type="brainstorm:pbx-web",
    )

    # get_previous_result_for_diff with 'status:pbx-web' should NOT find brainstorm result
    status_previous = await store.get_previous_result_for_diff(topic_id, "status:pbx-web")
    assert status_previous is not None
    assert status_previous["id"] == status_result_id

    # get_previous_result_for_diff with 'brainstorm:pbx-web' should NOT find status result
    brainstorm_previous = await store.get_previous_result_for_diff(topic_id, "brainstorm:pbx-web")
    assert brainstorm_previous is not None
    assert brainstorm_previous["id"] == brainstorm_result_id


# --- session-scoped diff display tests ----------------------------------------


@pytest.mark.asyncio
async def test_step1_fresh_session_no_diff_strip(store: SessionStore, seed_session: str, fresh_session: str) -> None:
    """Test that step-1 dispatch in fresh session shows NO diff strip.

    This is the key acceptance criterion: when a fresh session starts after seeding,
    the first dispatch shows no diff strip because the previous_result from the
    seed session is ignored for diff computation (only previous_result_id is set).
    """
    # Create cross-session topic and seed result
    topic_id, _ = await store.find_or_create_topic(
        label="pbx-web",
        session_id=seed_session,
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="cross-session",
    )

    # Seed result (from seed session)
    await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=seed_session,
        summary="Seed result",
        data={"status": "running"},
        urgency="normal",
        result_type="status:pbx-web",
    )

    # Fresh session creates result with diff computation
    result_id, has_diff = await store.create_result_with_diff(
        intent_id=None,
        topic_id=topic_id,
        session_id=fresh_session,
        summary="Step-1 result",
        data={"status": "running"},
        urgency="normal",
        result_type="status:pbx-web",
    )

    # Verify result was created
    assert result_id is not None

    # Verify NO diff was computed (has_diff should be False)
    assert has_diff is False, "Step-1 in fresh session should have no diff strip"

    # Verify previous_result_id IS set for lineage
    result = await store.get_all_results()
    fresh_result = next((r for r in result if r["id"] == result_id), None)
    assert fresh_result is not None
    assert fresh_result["previous_result_id"] is not None, "previous_result_id should be set for lineage"
    assert fresh_result["diff_summary"] is None, "diff_summary should be None (no diff strip)"


@pytest.mark.asyncio
async def test_step6_in_session_shows_diff_strip(store: SessionStore, fresh_session: str) -> None:
    """Test that step-6 follow-up in same session DOES show diff strip against step-1.

    This is the key acceptance criterion: when dispatching a follow-up in the same
    session, the diff strip should render against the previous result from that session.
    """
    # Create cross-session topic
    topic_id, _ = await store.find_or_create_topic(
        label="pbx-web",
        session_id=fresh_session,
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="cross-session",
    )

    # Step-1: Create first result in fresh session
    step1_result_id, has_diff = await store.create_result_with_diff(
        intent_id=None,
        topic_id=topic_id,
        session_id=fresh_session,
        summary="Step-1 result",
        data={"status": "running", "replicas": 3},
        urgency="normal",
        result_type="status:pbx-web",
    )

    assert has_diff is False, "First result should have no diff"

    # Step-6: Create second result in same session (simulating follow-up)
    step6_result_id, has_diff = await store.create_result_with_diff(
        intent_id=None,
        topic_id=topic_id,
        session_id=fresh_session,
        summary="Step-6 result",
        data={"status": "running", "replicas": 5},  # Changed value
        urgency="normal",
        result_type="status:pbx-web",
    )

    # Verify diff WAS computed (has_diff should be True)
    assert has_diff is True, "Step-6 in same session should show diff strip"

    # Verify previous_result_id points to step-1
    result = await store.get_all_results()
    step6_result = next((r for r in result if r["id"] == step6_result_id), None)
    assert step6_result is not None
    assert step6_result["previous_result_id"] == step1_result_id
    assert step6_result["diff_summary"] is not None, "diff_summary should be set (diff strip shown)"


@pytest.mark.asyncio
async def test_status_never_diffs_against_brainstorm(store: SessionStore, fresh_session: str) -> None:
    """Test that a status result never diffs against a brainstorm result.

    This is the key acceptance criterion: different result_types should not diff
    against each other, even on the same topic.
    """
    # Create cross-session topic
    topic_id, _ = await store.find_or_create_topic(
        label="pbx-web",
        session_id=fresh_session,
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="cross-session",
    )

    # Create brainstorm result
    brainstorm_result_id, _ = await store.create_result_with_diff(
        intent_id=None,
        topic_id=topic_id,
        session_id=fresh_session,
        summary="Brainstorm result",
        data={"ideas": ["use Django", "use FastAPI"]},
        urgency="normal",
        result_type="brainstorm:pbx-web",
    )

    # Create status result - should NOT diff against brainstorm result
    status_result_id, has_diff = await store.create_result_with_diff(
        intent_id=None,
        topic_id=topic_id,
        session_id=fresh_session,
        summary="Status result",
        data={"status": "healthy"},
        urgency="normal",
        result_type="status:pbx-web",
    )

    # Verify NO diff was computed (different result_types)
    assert has_diff is False, "Status result should not diff against brainstorm result"

    # Verify previous_result_id does NOT point to brainstorm result
    result = await store.get_all_results()
    status_result = next((r for r in result if r["id"] == status_result_id), None)
    assert status_result is not None
    # previous_result_id should be None (no previous status result to diff against)
    assert status_result["previous_result_id"] is None


@pytest.mark.asyncio
async def test_cross_session_canvas_shows_only_current_session_results(store: SessionStore, seed_session: str, fresh_session: str) -> None:
    """Test that canvas (get_latest_results_by_type) shows only current session's results."""
    # Create cross-session topic
    topic_id, _ = await store.find_or_create_topic(
        label="whisper-stt",
        session_id=seed_session,
        topic_type="project",
        project_slugs=["whisper-stt"],
        scope="cross-session",
    )

    # Create result in seed session
    await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=seed_session,
        summary="Seed result",
        data={"status": "running"},
        urgency="normal",
        result_type="status:whisper-stt",
    )

    # Create result in fresh session
    fresh_result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=fresh_session,
        summary="Fresh result",
        data={"status": "stopped"},
        urgency="normal",
        result_type="status:whisper-stt",
    )

    # get_latest_results_by_type for seed session should return only seed result
    seed_results = await store.get_latest_results_by_type(seed_session)
    assert len(seed_results) == 1
    assert seed_results[0]["session_id"] == seed_session
    assert seed_results[0]["id"] != fresh_result_id

    # get_latest_results_by_type for fresh session should return only fresh result
    fresh_results = await store.get_latest_results_by_type(fresh_session)
    assert len(fresh_results) == 1
    assert fresh_results[0]["session_id"] == fresh_session
    assert fresh_results[0]["id"] == fresh_result_id


# --- lineage tracking tests ---------------------------------------------------


@pytest.mark.asyncio
async def test_previous_result_id_set_cross_session(store: SessionStore, seed_session: str, fresh_session: str) -> None:
    """Test that previous_result_id is set even across sessions (pure lineage)."""
    # Create cross-session topic
    topic_id, _ = await store.find_or_create_topic(
        label="pbx-web",
        session_id=seed_session,
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="cross-session",
    )

    # Create result in seed session
    seed_result_id = await store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=seed_session,
        summary="Seed result",
        data={"status": "running"},
        urgency="normal",
        result_type="status:pbx-web",
    )

    # Create result in fresh session
    fresh_result_id, _ = await store.create_result_with_diff(
        intent_id=None,
        topic_id=topic_id,
        session_id=fresh_session,
        summary="Fresh result",
        data={"status": "running"},
        urgency="normal",
        result_type="status:pbx-web",
    )

    # Verify previous_result_id is set for lineage (cross-session)
    result = await store.get_all_results()
    fresh_result = next((r for r in result if r["id"] == fresh_result_id), None)
    assert fresh_result is not None
    assert fresh_result["previous_result_id"] == seed_result_id, "previous_result_id should point to seed result"
