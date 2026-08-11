"""
Session isolation tests.

Verify that data from one session does not leak into another session.
Tests cover topics, results, utterances, intents, and cross-session queries.

This is the final verification bead (adc-1eltxf) — it assumes the other
operations work correctly and tests that they do not leak.
"""

import pytest

from src.session.store import SessionStore


# =============================================================================
# Topic Isolation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_session_a_topics_isolated_from_session_b(in_memory_db_store):
    """Test that topics created in session A do not appear in session B topic queries."""
    # Create two separate sessions
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    # Create topics in session A
    topic_a1_id = await in_memory_db_store.create_topic(
        label="Session A Topic 1",
        topic_type="project",
        project_slugs=["project-a"],
        scope="session",
        session_id=session_a_id,
    )

    topic_a2_id = await in_memory_db_store.create_topic(
        label="Session A Topic 2",
        topic_type="research",
        project_slugs=["project-b"],
        scope="session",
        session_id=session_a_id,
    )

    # Create topics in session B
    topic_b1_id = await in_memory_db_store.create_topic(
        label="Session B Topic 1",
        topic_type="project",
        project_slugs=["project-c"],
        scope="session",
        session_id=session_b_id,
    )

    # Query topics from session A - should only see session A topics
    session_a_topics = await in_memory_db_store.get_active_topics(session_a_id)
    session_a_topic_ids = {t["id"] for t in session_a_topics}

    assert topic_a1_id in session_a_topic_ids, "Session A should see its own topic A1"
    assert topic_a2_id in session_a_topic_ids, "Session A should see its own topic A2"
    assert topic_b1_id not in session_a_topic_ids, "Session A should NOT see session B's topic"

    # Query topics from session B - should only see session B topics
    session_b_topics = await in_memory_db_store.get_active_topics(session_b_id)
    session_b_topic_ids = {t["id"] for t in session_b_topics}

    assert topic_b1_id in session_b_topic_ids, "Session B should see its own topic"
    assert topic_a1_id not in session_b_topic_ids, "Session B should NOT see session A's topic A1"
    assert topic_a2_id not in session_b_topic_ids, "Session B should NOT see session A's topic A2"

    # Verify counts
    assert len(session_a_topics) == 2, "Session A should have exactly 2 topics"
    assert len(session_b_topics) == 1, "Session B should have exactly 1 topic"


@pytest.mark.asyncio
async def test_cross_session_topic_queries_return_empty(in_memory_db_store):
    """Test that querying topics across unrelated sessions returns empty."""
    # Create two separate sessions
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    # Create multiple topics in session A
    for i in range(5):
        await in_memory_db_store.create_topic(
            label=f"Session A Topic {i}",
            topic_type="project",
            project_slugs=["project-a"],
            scope="session",
            session_id=session_a_id,
        )

    # Session B should have no topics
    session_b_topics = await in_memory_db_store.get_active_topics(session_b_id)
    assert len(session_b_topics) == 0, "Session B should have no topics when only session A has data"


# =============================================================================
# Result Isolation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_session_a_results_isolated_from_session_b(
    in_memory_db_store, test_topic_builder
):
    """Test that results created in session A do not appear in session B result queries."""
    # Create two separate sessions with their own topics
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    topic_a_id = await test_topic_builder(
        label="Session A Topic",
        topic_type="project",
        session_id=session_a_id,
    )

    topic_b_id = await test_topic_builder(
        label="Session B Topic",
        topic_type="project",
        session_id=session_b_id,
    )

    # Create results in session A
    result_a1_id = await in_memory_db_store.create_result(
        intent_id=None,
        topic_id=topic_a_id,
        session_id=session_a_id,
        summary="Session A Result 1",
        data={"key": "value_a1"},
    )

    result_a2_id = await in_memory_db_store.create_result(
        intent_id=None,
        topic_id=topic_a_id,
        session_id=session_a_id,
        summary="Session A Result 2",
        data={"key": "value_a2"},
    )

    # Create results in session B
    result_b1_id = await in_memory_db_store.create_result(
        intent_id=None,
        topic_id=topic_b_id,
        session_id=session_b_id,
        summary="Session B Result 1",
        data={"key": "value_b1"},
    )

    # Query unsurfed results from session A - should only see session A results
    session_a_results = await in_memory_db_store.get_unsurfed_results(session_a_id)
    session_a_result_ids = {r["id"] for r in session_a_results}

    assert result_a1_id in session_a_result_ids, "Session A should see its own result A1"
    assert result_a2_id in session_a_result_ids, "Session A should see its own result A2"
    assert result_b1_id not in session_a_result_ids, "Session A should NOT see session B's result"

    # Query unsurfed results from session B - should only see session B results
    session_b_results = await in_memory_db_store.get_unsurfed_results(session_b_id)
    session_b_result_ids = {r["id"] for r in session_b_results}

    assert result_b1_id in session_b_result_ids, "Session B should see its own result"
    assert result_a1_id not in session_b_result_ids, "Session B should NOT see session A's result A1"
    assert result_a2_id not in session_b_result_ids, "Session B should NOT see session A's result A2"

    # Verify counts
    assert len(session_a_results) == 2, "Session A should have exactly 2 results"
    assert len(session_b_results) == 1, "Session B should have exactly 1 result"


@pytest.mark.asyncio
async def test_cross_session_result_queries_return_empty(
    in_memory_db_store, test_topic_builder
):
    """Test that querying results across unrelated sessions returns empty."""
    # Create two separate sessions
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    topic_a_id = await test_topic_builder(
        label="Session A Topic",
        session_id=session_a_id,
    )

    # Create multiple results in session A
    for i in range(5):
        await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_a_id,
            session_id=session_a_id,
            summary=f"Session A Result {i}",
            data={"index": i},
        )

    # Session B should have no results
    session_b_results = await in_memory_db_store.get_unsurfed_results(session_b_id)
    assert len(session_b_results) == 0, "Session B should have no results when only session A has data"


# =============================================================================
# Utterance Isolation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_session_a_utterances_isolated_from_session_b(in_memory_db_store):
    """Test that utterances created in session A cannot be accessed from session B by session filtering."""
    # Create two separate sessions
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    # Create utterances in session A
    utterance_a1_id = await in_memory_db_store.create_utterance(
        session_id=session_a_id,
        raw_text="Session A utterance 1",
    )

    utterance_a2_id = await in_memory_db_store.create_utterance(
        session_id=session_a_id,
        raw_text="Session A utterance 2",
    )

    # Create utterances in session B
    utterance_b1_id = await in_memory_db_store.create_utterance(
        session_id=session_b_id,
        raw_text="Session B utterance 1",
    )

    # Verify utterances are created with correct session associations
    utterance_a1 = await in_memory_db_store.get_utterance(utterance_a1_id)
    assert utterance_a1 is not None, "Session A utterance A1 should exist"
    assert utterance_a1["session_id"] == session_a_id, "Utterance A1 should belong to session A"

    utterance_a2 = await in_memory_db_store.get_utterance(utterance_a2_id)
    assert utterance_a2 is not None, "Session A utterance A2 should exist"
    assert utterance_a2["session_id"] == session_a_id, "Utterance A2 should belong to session A"

    utterance_b1 = await in_memory_db_store.get_utterance(utterance_b1_id)
    assert utterance_b1 is not None, "Session B utterance B1 should exist"
    assert utterance_b1["session_id"] == session_b_id, "Utterance B1 should belong to session B"

    # Verify utterances cannot be accessed from the wrong session via session filtering
    # (Since get_utterance is by ID, the session_id field in the record enforces isolation)
    assert utterance_a1["session_id"] != session_b_id, "Utterance A1 should not belong to session B"
    assert utterance_a2["session_id"] != session_b_id, "Utterance A2 should not belong to session B"
    assert utterance_b1["session_id"] != session_a_id, "Utterance B1 should not belong to session A"


@pytest.mark.asyncio
async def test_cross_session_utterance_access_by_wrong_session(in_memory_db_store):
    """Test that accessing an utterance from a different session shows it belongs to its original session."""
    # Create two separate sessions
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    # Create utterance in session A
    utterance_a_id = await in_memory_db_store.create_utterance(
        session_id=session_a_id,
        raw_text="Session A utterance",
    )

    # Even if session B tries to access this utterance (by ID), it should see it belongs to session A
    utterance = await in_memory_db_store.get_utterance(utterance_a_id)
    assert utterance is not None, "Utterance should exist"
    assert utterance["session_id"] == session_a_id, "Utterance should belong to session A, not B"
    assert utterance["session_id"] != session_b_id, "Utterance should not belong to session B"


# =============================================================================
# Intent Isolation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_session_a_intents_isolated_from_session_b(
    in_memory_db_store, test_utterance_builder
):
    """Test that intents created in session A do not appear in session B intent queries."""
    # Create two separate sessions
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    # Create utterances in each session
    utterance_a_id = await test_utterance_builder(
        session_id=session_a_id,
        raw_text="Session A utterance",
    )

    utterance_b_id = await test_utterance_builder(
        session_id=session_b_id,
        raw_text="Session B utterance",
    )

    # Create intents in session A
    intent_a1_id = await in_memory_db_store.create_intent(
        utterance_id=utterance_a_id,
        session_id=session_a_id,
        intent_type="status",
        project_slug="project-a",
    )

    intent_a2_id = await in_memory_db_store.create_intent(
        utterance_id=utterance_a_id,
        session_id=session_a_id,
        intent_type="dispatch",
        project_slug="project-b",
    )

    # Create intents in session B
    intent_b1_id = await in_memory_db_store.create_intent(
        utterance_id=utterance_b_id,
        session_id=session_b_id,
        intent_type="status",
        project_slug="project-c",
    )

    # Query pending intents from session A - should only see session A intents
    session_a_intents = await in_memory_db_store.get_pending_intents(session_a_id)
    session_a_intent_ids = {i["id"] for i in session_a_intents}

    assert intent_a1_id in session_a_intent_ids, "Session A should see its own intent A1"
    assert intent_a2_id in session_a_intent_ids, "Session A should see its own intent A2"
    assert intent_b1_id not in session_a_intent_ids, "Session A should NOT see session B's intent"

    # Query pending intents from session B - should only see session B intents
    session_b_intents = await in_memory_db_store.get_pending_intents(session_b_id)
    session_b_intent_ids = {i["id"] for i in session_b_intents}

    assert intent_b1_id in session_b_intent_ids, "Session B should see its own intent"
    assert intent_a1_id not in session_b_intent_ids, "Session B should NOT see session A's intent A1"
    assert intent_a2_id not in session_b_intent_ids, "Session B should NOT see session A's intent A2"

    # Verify counts
    assert len(session_a_intents) == 2, "Session A should have exactly 2 intents"
    assert len(session_b_intents) == 1, "Session B should have exactly 1 intent"


@pytest.mark.asyncio
async def test_cross_session_intent_queries_return_empty(
    in_memory_db_store, test_utterance_builder
):
    """Test that querying intents across unrelated sessions returns empty."""
    # Create two separate sessions
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    utterance_a_id = await test_utterance_builder(
        session_id=session_a_id,
        raw_text="Session A utterance",
    )

    # Create multiple intents in session A
    for i in range(5):
        await in_memory_db_store.create_intent(
            utterance_id=utterance_a_id,
            session_id=session_a_id,
            intent_type="status",
            project_slug=f"project-{i}",
        )

    # Session B should have no intents
    session_b_intents = await in_memory_db_store.get_pending_intents(session_b_id)
    assert len(session_b_intents) == 0, "Session B should have no intents when only session A has data"


# =============================================================================
# Cross-Session Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_full_cross_session_isolation(
    in_memory_db_store,
    test_topic_builder,
    test_utterance_builder,
    test_intent_builder,
    test_result_builder,
):
    """Comprehensive test that all data types are isolated between sessions."""
    # Create two separate sessions
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    # Create complete data chain in session A
    topic_a_id = await test_topic_builder(
        label="Session A Topic",
        session_id=session_a_id,
    )

    utterance_a_id = await test_utterance_builder(
        session_id=session_a_id,
        raw_text="Session A utterance",
    )

    intent_a_id = await test_intent_builder(
        utterance_id=utterance_a_id,
        session_id=session_a_id,
        intent_type="status",
        project_slug="project-a",
    )

    result_a_id = await test_result_builder(
        topic_id=topic_a_id,
        session_id=session_a_id,
        summary="Session A result",
        data={"source": "session_a"},
    )

    # Create complete data chain in session B
    topic_b_id = await test_topic_builder(
        label="Session B Topic",
        session_id=session_b_id,
    )

    utterance_b_id = await test_utterance_builder(
        session_id=session_b_id,
        raw_text="Session B utterance",
    )

    intent_b_id = await test_intent_builder(
        utterance_id=utterance_b_id,
        session_id=session_b_id,
        intent_type="dispatch",
        project_slug="project-b",
    )

    result_b_id = await test_result_builder(
        topic_id=topic_b_id,
        session_id=session_b_id,
        summary="Session B result",
        data={"source": "session_b"},
    )

    # Session A queries - should only see session A data
    session_a_topics = await in_memory_db_store.get_active_topics(session_a_id)
    session_a_results = await in_memory_db_store.get_unsurfed_results(session_a_id)
    session_a_intents = await in_memory_db_store.get_pending_intents(session_a_id)

    assert len(session_a_topics) == 1, "Session A should have 1 topic"
    assert session_a_topics[0]["id"] == topic_a_id, "Session A should see its topic"
    assert topic_b_id not in {t["id"] for t in session_a_topics}, "Session A should NOT see session B's topic"

    assert len(session_a_results) == 1, "Session A should have 1 result"
    assert session_a_results[0]["id"] == result_a_id, "Session A should see its result"
    assert result_b_id not in {r["id"] for r in session_a_results}, "Session A should NOT see session B's result"

    assert len(session_a_intents) == 1, "Session A should have 1 intent"
    assert session_a_intents[0]["id"] == intent_a_id, "Session A should see its intent"
    assert intent_b_id not in {i["id"] for i in session_a_intents}, "Session A should NOT see session B's intent"

    # Session B queries - should only see session B data
    session_b_topics = await in_memory_db_store.get_active_topics(session_b_id)
    session_b_results = await in_memory_db_store.get_unsurfed_results(session_b_id)
    session_b_intents = await in_memory_db_store.get_pending_intents(session_b_id)

    assert len(session_b_topics) == 1, "Session B should have 1 topic"
    assert session_b_topics[0]["id"] == topic_b_id, "Session B should see its topic"
    assert topic_a_id not in {t["id"] for t in session_b_topics}, "Session B should NOT see session A's topic"

    assert len(session_b_results) == 1, "Session B should have 1 result"
    assert session_b_results[0]["id"] == result_b_id, "Session B should see its result"
    assert result_a_id not in {r["id"] for r in session_b_results}, "Session B should NOT see session A's result"

    assert len(session_b_intents) == 1, "Session B should have 1 intent"
    assert session_b_intents[0]["id"] == intent_b_id, "Session B should see its intent"
    assert intent_a_id not in {i["id"] for i in session_b_intents}, "Session B should NOT see session A's intent"


@pytest.mark.asyncio
async def test_multiple_sessions_strict_isolation(in_memory_db_store, test_topic_builder):
    """Test that multiple sessions maintain strict isolation from each other."""
    # Create three separate sessions
    session_ids = [await in_memory_db_store.create_session() for _ in range(3)]
    topic_ids = []

    # Create one topic per session
    for i, session_id in enumerate(session_ids):
        topic_id = await test_topic_builder(
            label=f"Session {i} Topic",
            session_id=session_id,
        )
        topic_ids.append(topic_id)

    # Each session should only see its own topic
    for i, session_id in enumerate(session_ids):
        topics = await in_memory_db_store.get_active_topics(session_id)
        assert len(topics) == 1, f"Session {i} should have exactly 1 topic"
        assert topics[0]["id"] == topic_ids[i], f"Session {i} should see its own topic"

        # Verify it doesn't see topics from other sessions
        for j, other_topic_id in enumerate(topic_ids):
            if i != j:
                assert other_topic_id not in {t["id"] for t in topics}, \
                    f"Session {i} should NOT see session {j}'s topic"


@pytest.mark.asyncio
async def test_session_deletion_does_not_affect_other_sessions(
    in_memory_db_store,
    test_topic_builder,
    test_utterance_builder,
    test_result_builder,
):
    """Test that deleting one session does not affect data in other sessions."""
    # Create two separate sessions
    session_a_id = await in_memory_db_store.create_session()
    session_b_id = await in_memory_db_store.create_session()

    # Create data in both sessions
    topic_a_id = await test_topic_builder(
        label="Session A Topic",
        session_id=session_a_id,
    )

    topic_b_id = await test_topic_builder(
        label="Session B Topic",
        session_id=session_b_id,
    )

    utterance_a_id = await test_utterance_builder(
        session_id=session_a_id,
        raw_text="Session A utterance",
    )

    utterance_b_id = await test_utterance_builder(
        session_id=session_b_id,
        raw_text="Session B utterance",
    )

    result_a_id = await test_result_builder(
        topic_id=topic_a_id,
        session_id=session_a_id,
        summary="Session A result",
        data={},
    )

    result_b_id = await test_result_builder(
        topic_id=topic_b_id,
        session_id=session_b_id,
        summary="Session B result",
        data={},
    )

    # Delete session A
    deleted = await in_memory_db_store.delete_session(session_a_id)
    assert deleted is not None, "Session A should be deleted"
    assert deleted["session_removed"] == 1, "Session A should be marked as removed"

    # Session B data should still be accessible
    session_b_topics = await in_memory_db_store.get_active_topics(session_b_id)
    session_b_results = await in_memory_db_store.get_unsurfed_results(session_b_id)

    assert len(session_b_topics) == 1, "Session B should still have 1 topic after session A deletion"
    assert session_b_topics[0]["id"] == topic_b_id, "Session B topic should still be accessible"

    assert len(session_b_results) == 1, "Session B should still have 1 result after session A deletion"
    assert session_b_results[0]["id"] == result_b_id, "Session B result should still be accessible"

    # Session A data should be gone
    session_a_topics = await in_memory_db_store.get_active_topics(session_a_id)
    session_a_results = await in_memory_db_store.get_unsurfed_results(session_a_id)

    assert len(session_a_topics) == 0, "Session A should have no topics after deletion"
    assert len(session_a_results) == 0, "Session A should have no results after deletion"
