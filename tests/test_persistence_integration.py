"""
Persistence layer integration tests (bead adc-d6x7bt).

Comprehensive integration tests that verify the session store works correctly:
- Result creation stores all fields in session.db
- Topic creation and retrieval (with full field validation)
- Utterance linkage to results (intent → utterance → result chain)
- Session isolation (different sessions don't leak data)
- Complete data integrity across the persistence layer

These tests use the isolated database fixtures from conftest.py to ensure
complete test independence and avoid touching production data/session.db.
"""

import json
from datetime import datetime
from uuid import uuid4

import aiosqlite
import pytest

from src.session.store import SessionStore


# =============================================================================
# Result Creation Tests - All Fields
# =============================================================================

@pytest.mark.asyncio
async def test_create_result_stores_all_fields(test_db_store, test_session_id: str) -> None:
    """Test result creation stores all synthesis output, fetch metadata, and timestamps."""
    # Create a topic for the result
    topic_id = await test_db_store.create_topic(
        label="Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create an utterance and intent for the result
    utterance_id = await test_db_store.create_utterance(
        session_id=test_session_id,
        raw_text="test utterance for result"
    )

    intent_id = await test_db_store.create_intent(
        utterance_id=utterance_id,
        session_id=test_session_id,
        project_slug="adc",
        intent_type="status",
        bead_ref="adc-test",
        lookup_kind=None,
        topic_id=topic_id
    )

    # Create result with all fields populated
    result_id = await test_db_store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Test result with all fields",
        data={
            "synthesis_output": "This is the synthesis output",
            "fetch_metadata": {
                "sources": ["kubectl", "git", "logs"],
                "total_sources": 3,
                "fetch_time_ms": 150
            },
            "structured_data": {
                "key": "value",
                "nested": {
                    "field": "nested_value"
                }
            }
        },
        urgency="high",
        result_type="status:adc",
        card_fallback=False,
        previous_result_id=None,
        diff_summary="No previous result",
        diff_data=None
    )

    # Verify result was stored with all fields
    result = await test_db_store.get_result(result_id)
    assert result is not None, "Result should be retrievable"

    # Verify basic fields
    assert result["id"] == result_id
    assert result["intent_id"] == intent_id
    assert result["topic_id"] == topic_id
    assert result["session_id"] == test_session_id
    assert result["summary"] == "Test result with all fields"
    assert result["urgency"] == "high"
    assert result["result_type"] == "status:adc"
    assert result["card_fallback"] == 0  # Stored as integer

    # Verify data field stores synthesis output and fetch metadata
    result_data = json.loads(result["data"])
    assert result_data["synthesis_output"] == "This is the synthesis output"
    assert result_data["fetch_metadata"]["sources"] == ["kubectl", "git", "logs"]
    assert result_data["fetch_metadata"]["total_sources"] == 3
    assert result_data["fetch_metadata"]["fetch_time_ms"] == 150
    assert result_data["structured_data"]["key"] == "value"
    assert result_data["structured_data"]["nested"]["field"] == "nested_value"

    # Verify timestamps are set (created_at is set on creation, surfaced_at is NULL until surfaced)
    assert result["created_at"] is not None
    assert result["surfaced_at"] is None  # Not surfaced yet
    now = int(datetime.now().timestamp())
    assert abs(now - result["created_at"]) < 5  # Created within last 5 seconds

    # Verify optional fields are correctly set to None
    assert result["acked_at"] is None
    assert result["previous_result_id"] is None
    assert result["diff_summary"] == "No previous result"
    assert result["diff_data"] is None


@pytest.mark.asyncio
async def test_create_result_with_diff_data(test_db_store, test_session_id: str) -> None:
    """Test result creation with diff computation data."""
    topic_id = await test_db_store.create_topic(
        label="Diff Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create first result
    first_result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="First result",
        data={"status": "active", "count": 1},
        urgency="normal",
        result_type="status:test"
    )

    # Create second result with diff from first
    second_result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Second result",
        data={"status": "pending", "count": 2},
        urgency="normal",
        result_type="status:test",
        previous_result_id=first_result_id,
        diff_summary="Status changed from active to pending, count increased",
        diff_data={
            "fields_changed": ["status", "count"],
            "status": {"old": "active", "new": "pending"},
            "count": {"old": 1, "new": 2}
        }
    )

    # Verify second result has diff data
    second_result = await test_db_store.get_result(second_result_id)
    assert second_result is not None
    assert second_result["previous_result_id"] == first_result_id
    assert second_result["diff_summary"] == "Status changed from active to pending, count increased"

    diff_data = json.loads(second_result["diff_data"])
    assert diff_data["fields_changed"] == ["status", "count"]
    assert diff_data["status"]["old"] == "active"
    assert diff_data["status"]["new"] == "pending"
    assert diff_data["count"]["old"] == 1
    assert diff_data["count"]["new"] == 2


@pytest.mark.asyncio
async def test_create_result_card_fallback_flag(test_db_store, test_session_id: str) -> None:
    """Test result creation correctly stores card_fallback flag."""
    topic_id = await test_db_store.create_topic(
        label="Fallback Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create result with card_fallback=True
    result_with_fallback = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Result with generic card fallback",
        data={"message": "No component matched"},
        urgency="normal",
        result_type="unknown:type",
        card_fallback=True
    )

    # Create result with card_fallback=False
    result_without_fallback = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Result with specific component",
        data={"message": "Component rendered successfully"},
        urgency="normal",
        result_type="status:test",
        card_fallback=False
    )

    # Verify card_fallback flags are stored correctly
    fallback_result = await test_db_store.get_result(result_with_fallback)
    assert fallback_result is not None
    assert fallback_result["card_fallback"] == 1

    non_fallback_result = await test_db_store.get_result(result_without_fallback)
    assert non_fallback_result is not None
    assert non_fallback_result["card_fallback"] == 0


# =============================================================================
# Topic Creation and Retrieval Tests
# =============================================================================

@pytest.mark.asyncio
async def test_find_or_create_topic_returns_existing_on_duplicate(test_db_store, test_session_id: str) -> None:
    """Test find_or_create_topic returns existing topic on duplicate label."""
    # Create initial topic
    first_id, first_created = await test_db_store.find_or_create_topic(
        label="Duplicate Test Topic",
        session_id=test_session_id,
        topic_type="project",
        project_slugs=["test-project"]
    )

    assert first_created is True, "First call should create new topic"
    assert isinstance(first_id, str), "Topic ID should be string"

    # Call again with same label and session
    second_id, second_created = await test_db_store.find_or_create_topic(
        label="Duplicate Test Topic",
        session_id=test_session_id,
        topic_type="project",
        project_slugs=["test-project"]
    )

    assert second_created is False, "Second call should not create new topic"
    assert second_id == first_id, "Should return same topic ID"

    # Verify only one topic exists in database
    topics = await test_db_store.get_active_topics(test_session_id)
    assert len(topics) == 1, "Should have exactly one topic"


@pytest.mark.asyncio
async def test_topic_retrieval_with_all_fields(test_db_store, test_session_id: str) -> None:
    """Test topic retrieval returns all fields correctly."""
    # Create topic with all parameters
    topic_id = await test_db_store.create_topic(
        label="Full Field Topic",
        topic_type="research",
        project_slugs=["project-a", "project-b"],
        scope="session",
        session_id=test_session_id
    )

    # Retrieve the topic
    topic = await test_db_store.get_topic(topic_id)
    assert topic is not None, "Topic should be retrievable"

    # Verify all fields
    assert topic["id"] == topic_id
    assert topic["label"] == "Full Field Topic"
    assert topic["type"] == "research"
    assert topic["project_slugs"] == ["project-a", "project-b"]
    assert topic["scope"] == "session"
    assert topic["session_id"] == test_session_id
    assert topic["archived_at"] is None

    # Verify timestamps
    assert topic["created_at"] is not None
    assert topic["last_active"] is not None
    now = int(datetime.now().timestamp())
    assert abs(now - topic["created_at"]) < 5
    assert abs(now - topic["last_active"]) < 5


# =============================================================================
# Utterance Linkage to Results Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_utterance_links_to_results(test_db_store, test_session_id: str) -> None:
    """Test utterance → intent → result linkage chain."""
    # Create utterance
    utterance_text = "Show me the status of pbx-web"
    utterance_id = await test_db_store.create_utterance(
        session_id=test_session_id,
        raw_text=utterance_text
    )

    # Verify utterance was stored
    utterance = await test_db_store.get_utterance(utterance_id)
    assert utterance is not None
    assert utterance["raw_text"] == utterance_text
    assert utterance["session_id"] == test_session_id

    # Create topic
    topic_id = await test_db_store.create_topic(
        label="pbx-web status",
        topic_type="project",
        project_slugs=["pbx-web"],
        scope="session",
        session_id=test_session_id
    )

    # Create intent linked to utterance
    intent_id = await test_db_store.create_intent(
        utterance_id=utterance_id,
        session_id=test_session_id,
        project_slug="pbx-web",
        intent_type="status",
        bead_ref=None,
        lookup_kind=None,
        topic_id=topic_id
    )

    # Verify intent links to utterance
    intent = await test_db_store.get_intent(intent_id)
    assert intent is not None
    assert intent["utterance_id"] == utterance_id
    assert intent["session_id"] == test_session_id
    assert intent["topic_id"] == topic_id

    # Create result linked to intent
    result_id = await test_db_store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="pbx-web is running",
        data={
            "status": "running",
            "uptime": "15 days",
            "last_check": datetime.now().isoformat()
        },
        urgency="normal",
        result_type="status:pbx-web"
    )

    # Verify result links to intent and topic
    result = await test_db_store.get_result(result_id)
    assert result is not None
    assert result["intent_id"] == intent_id
    assert result["topic_id"] == topic_id
    assert result["session_id"] == test_session_id

    # Verify complete chain: utterance → intent → result
    # Retrieve results for the intent
    results_for_intent = await test_db_store.get_results_for_intent(intent_id)
    assert len(results_for_intent) == 1
    assert results_for_intent[0]["id"] == result_id

    # Retrieve latest result for the topic
    latest_result = await test_db_store.get_latest_result_for_topic(topic_id)
    assert latest_result is not None
    assert latest_result["id"] == result_id


@pytest.mark.asyncio
async def test_utterance_router_timing_breakdown(test_db_store, test_session_id: str) -> None:
    """Test utterance stores router timing breakdown."""
    utterance_id = await test_db_store.create_utterance(
        session_id=test_session_id,
        raw_text="test utterance with timing"
    )

    # Update utterance with router timing breakdown
    timing_breakdown = {
        "prompt_construction_ms": 5,
        "proxy_call_ms": 150,
        "proxy_network_ms": 30,
        "proxy_inference_ms": 120,
        "json_parse_ms": 2,
        "process_ms": 8,
        "total_ms": 165,
        "intents_count": 2,
        "cached": False
    }

    await test_db_store.update_utterance_router_timing(
        utterance_id=utterance_id,
        timing_breakdown=timing_breakdown
    )

    # Verify timing breakdown was stored
    utterance = await test_db_store.get_utterance(utterance_id)
    assert utterance is not None

    stored_timing = json.loads(utterance["router_timing_breakdown"])
    assert stored_timing["prompt_construction_ms"] == 5
    assert stored_timing["proxy_call_ms"] == 150
    assert stored_timing["json_parse_ms"] == 2
    assert stored_timing["total_ms"] == 165
    assert stored_timing["intents_count"] == 2
    assert stored_timing["cached"] is False


# =============================================================================
# Session Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_session_isolation_topics_do_not_leak(test_db_store) -> None:
    """Test that session A's topics don't appear in session B."""
    # Create two sessions
    session_a = await test_db_store.create_session()
    session_b = await test_db_store.create_session()

    # Create topics in session A
    topic_a1_id = await test_db_store.create_topic(
        label="Session A Topic 1",
        topic_type="project",
        scope="session",
        session_id=session_a
    )

    topic_a2_id = await test_db_store.create_topic(
        label="Session A Topic 2",
        topic_type="research",
        scope="session",
        session_id=session_a
    )

    # Create topics in session B
    topic_b1_id = await test_db_store.create_topic(
        label="Session B Topic 1",
        topic_type="personal",
        scope="session",
        session_id=session_b
    )

    # Verify session A only sees its own topics
    topics_a = await test_db_store.get_active_topics(session_a)
    assert len(topics_a) == 2, "Session A should have exactly 2 topics"
    topic_ids_a = {t["id"] for t in topics_a}
    assert topic_a1_id in topic_ids_a
    assert topic_a2_id in topic_ids_a
    assert topic_b1_id not in topic_ids_a, "Session A should not see Session B's topics"

    # Verify session B only sees its own topics
    topics_b = await test_db_store.get_active_topics(session_b)
    assert len(topics_b) == 1, "Session B should have exactly 1 topic"
    topic_ids_b = {t["id"] for t in topics_b}
    assert topic_b1_id in topic_ids_b
    assert topic_a1_id not in topic_ids_b, "Session B should not see Session A's topics"
    assert topic_a2_id not in topic_ids_b


@pytest.mark.asyncio
async def test_session_isolation_utterances_do_not_leak(test_db_store) -> None:
    """Test that session A's utterances don't appear in session B."""
    session_a = await test_db_store.create_session()
    session_b = await test_db_store.create_session()

    # Create utterances in session A
    utterance_a1_id = await test_db_store.create_utterance(
        session_id=session_a,
        raw_text="Session A message 1"
    )

    utterance_a2_id = await test_db_store.create_utterance(
        session_id=session_a,
        raw_text="Session A message 2"
    )

    # Create utterances in session B
    utterance_b1_id = await test_db_store.create_utterance(
        session_id=session_b,
        raw_text="Session B message 1"
    )

    # Verify session A's utterances are isolated
    utterance_a1 = await test_db_store.get_utterance(utterance_a1_id)
    assert utterance_a1["session_id"] == session_a

    utterance_a2 = await test_db_store.get_utterance(utterance_a2_id)
    assert utterance_a2["session_id"] == session_a

    utterance_b1 = await test_db_store.get_utterance(utterance_b1_id)
    assert utterance_b1["session_id"] == session_b

    # Verify utterances are stored separately per session
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Count session A utterances
        async with db.execute(
            "SELECT COUNT(*) FROM utterances WHERE session_id = ?",
            (session_a,)
        ) as cur:
            count_a = (await cur.fetchone())[0]
        assert count_a == 2, "Session A should have 2 utterances"

        # Count session B utterances
        async with db.execute(
            "SELECT COUNT(*) FROM utterances WHERE session_id = ?",
            (session_b,)
        ) as cur:
            count_b = (await cur.fetchone())[0]
        assert count_b == 1, "Session B should have 1 utterance"


@pytest.mark.asyncio
async def test_session_isolation_results_do_not_leak(test_db_store) -> None:
    """Test that session A's results don't appear in session B."""
    session_a = await test_db_store.create_session()
    session_b = await test_db_store.create_session()

    # Create topics in both sessions
    topic_a_id = await test_db_store.create_topic(
        label="Session A Topic",
        topic_type="project",
        scope="session",
        session_id=session_a
    )

    topic_b_id = await test_db_store.create_topic(
        label="Session B Topic",
        topic_type="project",
        scope="session",
        session_id=session_b
    )

    # Create results in session A
    result_a1_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_a_id,
        session_id=session_a,
        summary="Session A result 1",
        data={"session": "A", "index": 1},
        urgency="normal"
    )

    result_a2_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_a_id,
        session_id=session_a,
        summary="Session A result 2",
        data={"session": "A", "index": 2},
        urgency="normal"
    )

    # Create results in session B
    result_b1_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_b_id,
        session_id=session_b,
        summary="Session B result 1",
        data={"session": "B", "index": 1},
        urgency="normal"
    )

    # Verify session A's results are isolated
    result_a1 = await test_db_store.get_result(result_a1_id)
    assert result_a1["session_id"] == session_a

    result_a2 = await test_db_store.get_result(result_a2_id)
    assert result_a2["session_id"] == session_a

    result_b1 = await test_db_store.get_result(result_b1_id)
    assert result_b1["session_id"] == session_b

    # Verify get_latest_results_by_type is session-scoped
    latest_a = await test_db_store.get_latest_results_by_type(session_a)
    assert len(latest_a) == 1, "Session A should have 1 latest result"
    assert latest_a[0]["id"] in [result_a1_id, result_a2_id]

    latest_b = await test_db_store.get_latest_results_by_type(session_b)
    assert len(latest_b) == 1, "Session B should have 1 latest result"
    assert latest_b[0]["id"] == result_b1_id

    # Verify sessions don't see each other's results
    latest_a_ids = {r["id"] for r in latest_a}
    latest_b_ids = {r["id"] for r in latest_b}
    assert latest_a_ids.isdisjoint(latest_b_ids), "Sessions should not share results"


@pytest.mark.asyncio
async def test_session_isolation_intents_do_not_leak(test_db_store) -> None:
    """Test that session A's intents don't appear in session B."""
    session_a = await test_db_store.create_session()
    session_b = await test_db_store.create_session()

    # Create utterances and topics in both sessions
    utterance_a = await test_db_store.create_utterance(
        session_id=session_a,
        raw_text="Session A utterance"
    )

    utterance_b = await test_db_store.create_utterance(
        session_id=session_b,
        raw_text="Session B utterance"
    )

    topic_a = await test_db_store.create_topic(
        label="Session A Topic",
        topic_type="project",
        scope="session",
        session_id=session_a
    )

    topic_b = await test_db_store.create_topic(
        label="Session B Topic",
        topic_type="project",
        scope="session",
        session_id=session_b
    )

    # Create intents in session A
    intent_a1_id = await test_db_store.create_intent(
        utterance_id=utterance_a,
        session_id=session_a,
        project_slug="test",
        intent_type="status",
        bead_ref=None,
        lookup_kind=None,
        topic_id=topic_a
    )

    intent_a2_id = await test_db_store.create_intent(
        utterance_id=utterance_a,
        session_id=session_a,
        project_slug="test",
        intent_type="lookup",
        bead_ref=None,
        lookup_kind="logs",
        topic_id=topic_a
    )

    # Create intents in session B
    intent_b1_id = await test_db_store.create_intent(
        utterance_id=utterance_b,
        session_id=session_b,
        project_slug="test",
        intent_type="action",
        bead_ref=None,
        lookup_kind=None,
        topic_id=topic_b
    )

    # Verify session A's intents are isolated
    pending_a = await test_db_store.get_pending_intents(session_a)
    assert len(pending_a) == 2, "Session A should have 2 pending intents"
    pending_a_ids = {i["id"] for i in pending_a}
    assert intent_a1_id in pending_a_ids
    assert intent_a2_id in pending_a_ids

    # Verify session B's intents are isolated
    pending_b = await test_db_store.get_pending_intents(session_b)
    assert len(pending_b) == 1, "Session B should have 1 pending intent"
    pending_b_ids = {i["id"] for i in pending_b}
    assert intent_b1_id in pending_b_ids

    # Verify sessions don't see each other's intents
    assert pending_a_ids.isdisjoint(pending_b_ids), "Sessions should not share intents"


@pytest.mark.asyncio
async def test_session_deletion_isolation(test_db_store) -> None:
    """Test that deleting one session doesn't affect other sessions."""
    session_a = await test_db_store.create_session()
    session_b = await test_db_store.create_session()

    # Create comprehensive data in both sessions
    topic_a = await test_db_store.create_topic(
        label="Session A Topic",
        topic_type="project",
        scope="session",
        session_id=session_a
    )

    topic_b = await test_db_store.create_topic(
        label="Session B Topic",
        topic_type="project",
        scope="session",
        session_id=session_b
    )

    utterance_a = await test_db_store.create_utterance(
        session_id=session_a,
        raw_text="Session A utterance"
    )

    utterance_b = await test_db_store.create_utterance(
        session_id=session_b,
        raw_text="Session B utterance"
    )

    intent_a = await test_db_store.create_intent(
        utterance_id=utterance_a,
        session_id=session_a,
        project_slug="test",
        intent_type="status",
        bead_ref=None,
        lookup_kind=None,
        topic_id=topic_a
    )

    intent_b = await test_db_store.create_intent(
        utterance_id=utterance_b,
        session_id=session_b,
        project_slug="test",
        intent_type="status",
        bead_ref=None,
        lookup_kind=None,
        topic_id=topic_b
    )

    result_a = await test_db_store.create_result(
        intent_id=intent_a,
        topic_id=topic_a,
        session_id=session_a,
        summary="Session A result",
        data={"session": "A"},
        urgency="normal"
    )

    result_b = await test_db_store.create_result(
        intent_id=intent_b,
        topic_id=topic_b,
        session_id=session_b,
        summary="Session B result",
        data={"session": "B"},
        urgency="normal"
    )

    # Delete session A
    deletion_result = await test_db_store.delete_session(session_a)
    assert deletion_result["session_removed"] == 1
    assert deletion_result["topics_removed"] == 1

    # Verify session A is gone
    session_a_check = await test_db_store.get_session(session_a)
    assert session_a_check is None, "Session A should be deleted"

    # Verify session B is completely intact
    session_b_check = await test_db_store.get_session(session_b)
    assert session_b_check is not None, "Session B should still exist"

    topics_b = await test_db_store.get_active_topics(session_b)
    assert len(topics_b) == 1, "Session B should still have its topic"

    utterance_b_check = await test_db_store.get_utterance(utterance_b)
    assert utterance_b_check is not None, "Session B's utterance should still exist"

    intent_b_check = await test_db_store.get_intent(intent_b)
    assert intent_b_check is not None, "Session B's intent should still exist"

    result_b_check = await test_db_store.get_result(result_b)
    assert result_b_check is not None, "Session B's result should still exist"


# =============================================================================
# Cross-Session Topic Tests
# =============================================================================

@pytest.mark.asyncio
async def test_cross_session_topic_sharing(test_db_store) -> None:
    """Test that cross-session topics can be shared across sessions."""
    session_a = await test_db_store.create_session()
    session_b = await test_db_store.create_session()

    # Create a cross-session topic from session A
    cross_topic_id, created = await test_db_store.find_or_create_topic(
        label="Shared Cross-Session Topic",
        session_id=session_a,
        topic_type="project",
        project_slugs=["shared-project"],
        scope="cross-session"
    )

    assert created is True, "Should create new cross-session topic"

    # Verify session A sees the topic
    topics_a = await test_db_store.get_active_topics(session_a)
    assert len(topics_a) == 1
    assert topics_a[0]["id"] == cross_topic_id

    # Session B should also see the same topic (by virtue of cross-session scope)
    topics_b = await test_db_store.get_active_topics(session_b)
    assert len(topics_b) == 1
    assert topics_b[0]["id"] == cross_topic_id, "Session B should see cross-session topic"

    # Both sessions should get the same topic ID (no duplicate created)
    cross_topic_id_b, created_b = await test_db_store.find_or_create_topic(
        label="Shared Cross-Session Topic",
        session_id=session_b,
        topic_type="project",
        project_slugs=["shared-project"],
        scope="cross-session"
    )

    assert created_b is False, "Should not create duplicate cross-session topic"
    assert cross_topic_id_b == cross_topic_id, "Should return same topic ID"


@pytest.mark.asyncio
async def test_cross_session_vs_session_scoped_isolation(test_db_store) -> None:
    """Test that session-scoped topics are isolated even with cross-session topics present."""
    session_a = await test_db_store.create_session()
    session_b = await test_db_store.create_session()

    # Create a cross-session topic
    cross_topic_id = await test_db_store.create_topic(
        label="Cross-Session Topic",
        topic_type="project",
        project_slugs=["cross-project"],
        scope="cross-session",
        session_id=None  # Cross-session topics have no session_id
    )

    # Create session-scoped topics in both sessions
    session_a_topic_id = await test_db_store.create_topic(
        label="Session A Private Topic",
        topic_type="personal",
        scope="session",
        session_id=session_a
    )

    session_b_topic_id = await test_db_store.create_topic(
        label="Session B Private Topic",
        topic_type="personal",
        scope="session",
        session_id=session_b
    )

    # Verify both sessions see the cross-session topic
    topics_a = await test_db_store.get_active_topics(session_a)
    assert len(topics_a) == 2, "Session A should see cross-session + its own topic"
    topic_ids_a = {t["id"] for t in topics_a}
    assert cross_topic_id in topic_ids_a
    assert session_a_topic_id in topic_ids_a
    assert session_b_topic_id not in topic_ids_a, "Session A should not see Session B's private topic"

    topics_b = await test_db_store.get_active_topics(session_b)
    assert len(topics_b) == 2, "Session B should see cross-session + its own topic"
    topic_ids_b = {t["id"] for t in topics_b}
    assert cross_topic_id in topic_ids_b
    assert session_b_topic_id in topic_ids_b
    assert session_a_topic_id not in topic_ids_b, "Session B should not see Session A's private topic"


# =============================================================================
# Result Type and Component Selection Tests
# =============================================================================

@pytest.mark.asyncio
async def test_result_type_for_component_selection(test_db_store, test_session_id: str) -> None:
    """Test that result_type is stored correctly for component selection."""
    topic_id = await test_db_store.create_topic(
        label="Component Selection Test",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create results with different result_types
    status_result = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Status result",
        data={"status": "running"},
        urgency="normal",
        result_type="status:pbx-web"
    )

    lookup_result = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Lookup result",
        data={"logs": "output"},
        urgency="normal",
        result_type="lookup:logs:whisper-stt"
    )

    monitoring_result = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Monitoring result",
        data={"metrics": {"cpu": 50}},
        urgency="normal",
        result_type="monitoring:pbx-web"
    )

    # Verify result_type is stored correctly
    status = await test_db_store.get_result(status_result)
    assert status["result_type"] == "status:pbx-web"

    lookup = await test_db_store.get_result(lookup_result)
    assert lookup["result_type"] == "lookup:logs:whisper-stt"

    monitoring = await test_db_store.get_result(monitoring_result)
    assert monitoring["result_type"] == "monitoring:pbx-web"

    # Verify get_latest_results_by_type returns one result per type
    latest_results = await test_db_store.get_latest_results_by_type(test_session_id)
    assert len(latest_results) == 3, "Should have one result per result_type"

    result_types = {r["result_type"] for r in latest_results}
    assert result_types == {"status:pbx-web", "lookup:logs:whisper-stt", "monitoring:pbx-web"}


# =============================================================================
# Urgency Level Tests
# =============================================================================

@pytest.mark.asyncio
async def test_result_urgency_levels(test_db_store, test_session_id: str) -> None:
    """Test that all urgency levels are stored correctly."""
    topic_id = await test_db_store.create_topic(
        label="Urgency Test",
        topic_type="exception",
        scope="session",
        session_id=test_session_id
    )

    # Create results with different urgency levels
    critical_result = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Critical issue",
        data={"issue": "system down"},
        urgency="critical"
    )

    high_result = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="High priority issue",
        data={"issue": "degraded performance"},
        urgency="high"
    )

    normal_result = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Normal update",
        data={"status": "running"},
        urgency="normal"
    )

    low_result = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Low priority info",
        data={"info": "minor event"},
        urgency="low"
    )

    # Verify all urgency levels are stored correctly
    critical = await test_db_store.get_result(critical_result)
    assert critical["urgency"] == "critical"

    high = await test_db_store.get_result(high_result)
    assert high["urgency"] == "high"

    normal = await test_db_store.get_result(normal_result)
    assert normal["urgency"] == "normal"

    low = await test_db_store.get_result(low_result)
    assert low["urgency"] == "low"
