"""
Persistence layer integration tests (bead adc-d6x7bt).

Tests core persistence operations for result creation, field storage,
utterance linkage, and session isolation.

These tests verify that the session store correctly persists all result
fields, maintains relationships between results, intents, utterances, and
topics, and ensures proper session isolation.
"""

import json
from datetime import datetime

import aiosqlite
import pytest

from src.session.store import SessionStore


# --- Result creation and field storage tests ---------------------------------

@pytest.mark.asyncio
async def test_result_creation_stores_all_core_fields(test_db_store, test_session_id: str) -> None:
    """Test that result creation stores all core fields in session.db."""
    # Create a topic for the result
    topic_id = await test_db_store.create_topic(
        label="Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create a result with all fields
    result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Test result with all fields",
        data={"test": "data", "nested": {"key": "value"}},
        urgency="high",
        result_type="status:test-project",
        card_fallback=False
    )

    # Verify all fields are persisted correctly
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM results WHERE id = ?""",
            (result_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None, "Result should be persisted"
            assert row["id"] == result_id
            assert row["topic_id"] == topic_id
            assert row["session_id"] == test_session_id
            assert row["summary"] == "Test result with all fields"
            assert row["urgency"] == "high"
            assert row["result_type"] == "status:test-project"
            assert row["card_fallback"] == 0  # False = 0
            assert row["created_at"] is not None
            assert row["surfaced_at"] is not None  # Should be set automatically

            # Verify JSON data is stored correctly
            stored_data = json.loads(row["data"])
            assert stored_data == {"test": "data", "nested": {"key": "value"}}


@pytest.mark.asyncio
async def test_result_creation_with_diff_fields(test_db_store, test_session_id: str) -> None:
    """Test that result creation stores diff-related fields."""
    topic_id = await test_db_store.create_topic(
        label="Diff Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create a previous result for diff
    previous_result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Previous result",
        data={"old": "data"},
        urgency="normal"
    )

    # Create a result with diff fields
    result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Updated result",
        data={"new": "data"},
        previous_result_id=previous_result_id,
        diff_summary="Fields changed: old→new",
        diff_data={"old": "data", "new": "data"}
    )

    # Verify diff fields are persisted
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM results WHERE id = ?""",
            (result_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row["previous_result_id"] == previous_result_id
            assert row["diff_summary"] == "Fields changed: old→new"

            # Verify diff data JSON is stored correctly
            stored_diff_data = json.loads(row["diff_data"])
            assert stored_diff_data == {"old": "data", "new": "data"}


@pytest.mark.asyncio
async def test_result_creation_with_all_urgency_levels(test_db_store, test_session_id: str) -> None:
    """Test that all urgency levels are stored correctly."""
    topic_id = await test_db_store.create_topic(
        label="Urgency Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    urgency_levels = ["critical", "high", "normal", "low"]
    result_ids = []

    for urgency in urgency_levels:
        result_id = await test_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=test_session_id,
            summary=f"Result with {urgency} urgency",
            data={"urgency": urgency},
            urgency=urgency
        )
        result_ids.append(result_id)

    # Verify all urgency levels are persisted correctly
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        for i, (result_id, urgency) in enumerate(zip(result_ids, urgency_levels)):
            async with db.execute(
                """SELECT urgency FROM results WHERE id = ?""",
                (result_id,)
            ) as cur:
                row = await cur.fetchone()
                assert row is not None
                assert row[0] == urgency


@pytest.mark.asyncio
async def test_result_creation_with_card_fallback(test_db_store, test_session_id: str) -> None:
    """Test that card_fallback is stored correctly."""
    topic_id = await test_db_store.create_topic(
        label="Fallback Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create result with card_fallback=True
    result_id_fallback = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Result with fallback card",
        data={"message": "No component matched"},
        urgency="normal",
        card_fallback=True
    )

    # Create result with card_fallback=False
    result_id_no_fallback = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Result with component card",
        data={"message": "Component rendered"},
        urgency="normal",
        card_fallback=False
    )

    # Verify card_fallback values
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """SELECT card_fallback FROM results WHERE id = ?""",
            (result_id_fallback,)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 1  # True = 1

        async with db.execute(
            """SELECT card_fallback FROM results WHERE id = ?""",
            (result_id_no_fallback,)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 0  # False = 0


@pytest.mark.asyncio
async def test_result_creation_stores_timestamps(test_db_store, test_session_id: str) -> None:
    """Test that result creation stores timestamps correctly."""
    topic_id = await test_db_store.create_topic(
        label="Timestamp Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    before_creation = int(datetime.now().timestamp())

    result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Result with timestamps",
        data={"test": "data"}
    )

    after_creation = int(datetime.now().timestamp())

    # Verify timestamps are set correctly
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT created_at, surfaced_at FROM results WHERE id = ?""",
            (result_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert before_creation <= row["created_at"] <= after_creation
            assert row["surfaced_at"] is not None  # surfaced_at should be set automatically
            assert before_creation <= row["surfaced_at"] <= after_creation


# --- Intent-Utterance-Result linkage tests ---------------------------------------

@pytest.mark.asyncio
async def test_utterance_linkage_to_results(test_db_store, test_session_id: str) -> None:
    """Test that utterances are correctly linked to results via intents."""
    # Create utterance
    utterance_id = await test_db_store.create_utterance(
        session_id=test_session_id,
        raw_text="test utterance for linkage"
    )

    # Create intent
    intent_id = await test_db_store.create_intent(
        utterance_id=utterance_id,
        session_id=test_session_id,
        project_slug="test-project",
        intent_type="status",
        topic_id=None
    )

    # Create topic
    topic_id = await test_db_store.create_topic(
        label="Linkage Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Update intent with topic
    await test_db_store.update_intent_topic(intent_id, topic_id)

    # Create result linked to intent
    result_id = await test_db_store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Result linked to utterance",
        data={"utterance_linked": True}
    )

    # Verify the complete linkage chain
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify utterance exists
        async with db.execute(
            """SELECT * FROM utterances WHERE id = ?""",
            (utterance_id,)
        ) as cur:
            utterance = await cur.fetchone()
            assert utterance is not None
            assert utterance["raw_text"] == "test utterance for linkage"

        # Verify intent exists and links to utterance
        async with db.execute(
            """SELECT * FROM intents WHERE id = ?""",
            (intent_id,)
        ) as cur:
            intent = await cur.fetchone()
            assert intent is not None
            assert intent["utterance_id"] == utterance_id
            assert intent["topic_id"] == topic_id

        # Verify result exists and links to intent
        async with db.execute(
            """SELECT * FROM results WHERE id = ?""",
            (result_id,)
        ) as cur:
            result = await cur.fetchone()
            assert result is not None
            assert result["intent_id"] == intent_id
            assert result["topic_id"] == topic_id


@pytest.mark.asyncio
async def test_multiple_results_from_single_utterance(test_db_store, test_session_id: str) -> None:
    """Test that a single utterance can generate multiple results."""
    utterance_id = await test_db_store.create_utterance(
        session_id=test_session_id,
        raw_text="complex utterance with multiple results"
    )

    # Create multiple intents for the same utterance
    intent_ids = []
    for i in range(3):
        intent_id = await test_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=test_session_id,
            project_slug="test-project",
            intent_type="status",
            topic_id=None
        )
        intent_ids.append(intent_id)

    # Create topic
    topic_id = await test_db_store.create_topic(
        label="Multi-result Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create multiple results from different intents
    result_ids = []
    for intent_id in intent_ids:
        result_id = await test_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=test_session_id,
            summary=f"Result {len(result_ids) + 1}",
            data={"result_number": len(result_ids) + 1}
        )
        result_ids.append(result_id)

    # Verify all results are stored correctly
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify all intents link to the same utterance
        for intent_id in intent_ids:
            async with db.execute(
                """SELECT utterance_id FROM intents WHERE id = ?""",
                (intent_id,)
            ) as cur:
                intent = await cur.fetchone()
                assert intent is not None
                assert intent[0] == utterance_id

        # Verify all results are stored
        async with db.execute(
            """SELECT COUNT(*) FROM results WHERE topic_id = ?""",
            (topic_id,)
        ) as cur:
            count = (await cur.fetchone())[0]
            assert count == 3

        # Verify each result has correct data
        for i, result_id in enumerate(result_ids):
            async with db.execute(
                """SELECT data FROM results WHERE id = ?""",
                (result_id,)
            ) as cur:
                result = await cur.fetchone()
                assert result is not None
                data = json.loads(result[0])
                assert data["result_number"] == i + 1


@pytest.mark.asyncio
async def test_result_with_null_intent_id(test_db_store, test_session_id: str) -> None:
    """Test that results can have NULL intent_id (monitoring-originated results)."""
    topic_id = await test_db_store.create_topic(
        label="Monitoring Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create result with intent_id=None (monitoring-originated)
    result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Monitoring result",
        data={"monitoring": True},
        result_type="monitoring:test-project"
    )

    # Verify result is stored with NULL intent_id
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM results WHERE id = ?""",
            (result_id,)
        ) as cur:
            result = await cur.fetchone()
            assert result is not None
            assert result["intent_id"] is None
            assert result["result_type"] == "monitoring:test-project"


# --- Session isolation tests --------------------------------------------------

@pytest.mark.asyncio
async def test_session_isolation_results(test_db_store) -> None:
    """Test that different sessions don't leak results."""
    # Create two sessions
    session1 = await test_db_store.create_session()
    session2 = await test_db_store.create_session()

    # Create topics in each session
    topic1_id = await test_db_store.create_topic(
        label="Session1 Topic",
        topic_type="project",
        scope="session",
        session_id=session1
    )

    topic2_id = await test_db_store.create_topic(
        label="Session2 Topic",
        topic_type="project",
        scope="session",
        session_id=session2
    )

    # Create results in each session
    result1_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic1_id,
        session_id=session1,
        summary="Session1 result",
        data={"session": 1}
    )

    result2_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic2_id,
        session_id=session2,
        summary="Session2 result",
        data={"session": 2}
    )

    # Verify session isolation - each session should only see its own results
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Session1 should only see its own result
        async with db.execute(
            """SELECT COUNT(*) FROM results WHERE session_id = ?""",
            (session1,)
        ) as cur:
            session1_count = (await cur.fetchone())[0]
            assert session1_count == 1

        # Session2 should only see its own result
        async with db.execute(
            """SELECT COUNT(*) FROM results WHERE session_id = ?""",
            (session2,)
        ) as cur:
            session2_count = (await cur.fetchone())[0]
            assert session2_count == 1

        # Verify the correct result is in each session
        async with db.execute(
            """SELECT data FROM results WHERE id = ?""",
            (result1_id,)
        ) as cur:
            result = await cur.fetchone()
            assert result is not None
            data = json.loads(result[0])
            assert data["session"] == 1

        async with db.execute(
            """SELECT data FROM results WHERE id = ?""",
            (result2_id,)
        ) as cur:
            result = await cur.fetchone()
            assert result is not None
            data = json.loads(result[0])
            assert data["session"] == 2


@pytest.mark.asyncio
async def test_cross_session_topic_with_session_scoped_results(test_db_store) -> None:
    """Test that cross-session topics work correctly with session-scoped results."""
    # Create two sessions
    session1 = await test_db_store.create_session()
    session2 = await test_db_store.create_session()

    # Create a cross-session topic
    topic_id, created = await test_db_store.find_or_create_topic(
        label="Cross-session Topic",
        session_id=session1,
        topic_type="project",
        scope="cross-session"
    )
    assert created is True

    # Create results in both sessions for the same topic
    result1_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session1,
        summary="Session1 result for cross-session topic",
        data={"session": 1}
    )

    result2_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=session2,
        summary="Session2 result for cross-session topic",
        data={"session": 2}
    )

    # Verify both results are stored correctly
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify topic has no session_id (cross-session)
        async with db.execute(
            """SELECT session_id FROM topics WHERE id = ?""",
            (topic_id,)
        ) as cur:
            topic = await cur.fetchone()
            assert topic is not None
            assert topic[0] is None  # Cross-session topic has NULL session_id

        # Verify both results exist and reference the same topic
        async with db.execute(
            """SELECT COUNT(*) FROM results WHERE topic_id = ?""",
            (topic_id,)
        ) as cur:
            count = (await cur.fetchone())[0]
            assert count == 2

        # Verify results are properly scoped by session
        async with db.execute(
            """SELECT id FROM results WHERE session_id = ? AND topic_id = ?""",
            (session1, topic_id)
        ) as cur:
            session1_results = await cur.fetchall()
            assert len(session1_results) == 1
            assert session1_results[0][0] == result1_id

        async with db.execute(
            """SELECT id FROM results WHERE session_id = ? AND topic_id = ?""",
            (session2, topic_id)
        ) as cur:
            session2_results = await cur.fetchall()
            assert len(session2_results) == 1
            assert session2_results[0][0] == result2_id


@pytest.mark.asyncio
async def test_results_query_isolation_by_session(test_db_store) -> None:
    """Test that result queries respect session isolation."""
    # Create two sessions
    session1 = await test_db_store.create_session()
    session2 = await test_db_store.create_session()

    # Create topics and results in both sessions
    topic1_id = await test_db_store.create_topic(
        label="Session1 Topic",
        topic_type="project",
        scope="session",
        session_id=session1
    )

    topic2_id = await test_db_store.create_topic(
        label="Session2 Topic",
        topic_type="project",
        scope="session",
        session_id=session2
    )

    # Create multiple results in session1
    for i in range(3):
        await test_db_store.create_result(
            intent_id=None,
            topic_id=topic1_id,
            session_id=session1,
            summary=f"Session1 result {i}",
            data={"session": 1, "index": i}
        )

    # Create multiple results in session2
    for i in range(2):
        await test_db_store.create_result(
            intent_id=None,
            topic_id=topic2_id,
            session_id=session2,
            summary=f"Session2 result {i}",
            data={"session": 2, "index": i}
        )

    # Test get_results_for_intent (should be session-scoped)
    # Create an intent in session1
    utterance1_id = await test_db_store.create_utterance(
        session_id=session1,
        raw_text="session1 utterance"
    )
    intent1_id = await test_db_store.create_intent(
        utterance_id=utterance1_id,
        session_id=session1,
        project_slug="test",
        intent_type="status",
        topic_id=topic1_id
    )

    # Create results for the intent
    await test_db_store.create_result(
        intent_id=intent1_id,
        topic_id=topic1_id,
        session_id=session1,
        summary="Intent result",
        data={"intent": "test"}
    )

    # Verify query isolation
    results_for_intent = await test_db_store.get_results_for_intent(intent1_id)
    assert len(results_for_intent) == 1
    assert results_for_intent[0]["session_id"] == session1

    # Verify unsurfaced results query is session-scoped
    # Mark some results as surfaced
    await test_db_store.mark_results_surfed(session1)

    unsurfaced_results = await test_db_store.get_unsurfed_results(session1)
    assert len(unsurfaced_results) == 0  # All session1 results are surfaced

    unsurfeded_results_s2 = await test_db_store.get_unsurfed_results(session2)
    assert len(unsurfeded_results_s2) == 0  # All session2 results are surfaced


@pytest.mark.asyncio
async def test_delete_result_respects_session_isolation(test_db_store) -> None:
    """Test that delete_result only deletes results from the correct session."""
    # Create two sessions
    session1 = await test_db_store.create_session()
    session2 = await test_db_store.create_session()

    # Create topics in each session
    topic1_id = await test_db_store.create_topic(
        label="Session1 Topic",
        topic_type="project",
        scope="session",
        session_id=session1
    )

    topic2_id = await test_db_store.create_topic(
        label="Session2 Topic",
        topic_type="project",
        scope="session",
        session_id=session2
    )

    # Create results in both sessions
    result1_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic1_id,
        session_id=session1,
        summary="Session1 result",
        data={"session": 1}
    )

    result2_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic2_id,
        session_id=session2,
        summary="Session2 result",
        data={"session": 2}
    )

    # Try to delete session2's result using session1 (should fail)
    delete_response = await test_db_store.delete_result(result2_id, session1)
    assert delete_response["result_deleted"] == 0

    # Verify session2's result still exists
    result2_check = await test_db_store.get_result(result2_id)
    assert result2_check is not None
    assert result2_check["id"] == result2_id

    # Delete session1's result using session1 (should succeed)
    delete_response = await test_db_store.delete_result(result1_id, session1)
    assert delete_response["result_deleted"] == 1

    # Verify session1's result is gone
    result1_check = await test_db_store.get_result(result1_id)
    assert result1_check is None

    # Verify session2's result still exists
    result2_check = await test_db_store.get_result(result2_id)
    assert result2_check is not None


# --- Complex integration scenarios -------------------------------------------

@pytest.mark.asyncio
async def test_complete_result_lifecycle(test_db_store, test_session_id: str) -> None:
    """Test complete result lifecycle from utterance to deletion."""
    # 1. Create utterance
    utterance_id = await test_db_store.create_utterance(
        session_id=test_session_id,
        raw_text="test complete lifecycle"
    )

    # 2. Create intent
    intent_id = await test_db_store.create_intent(
        utterance_id=utterance_id,
        session_id=test_session_id,
        project_slug="test-project",
        intent_type="status",
        topic_id=None
    )

    # 3. Create topic
    topic_id = await test_db_store.create_topic(
        label="Lifecycle Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # 4. Link intent to topic
    await test_db_store.update_intent_topic(intent_id, topic_id)

    # 5. Create result
    result_id = await test_db_store.create_result(
        intent_id=intent_id,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Complete lifecycle result",
        data={"lifecycle": "complete"}
    )

    # 6. Verify result exists
    result_check = await test_db_store.get_result(result_id)
    assert result_check is not None
    assert result_check["summary"] == "Complete lifecycle result"

    # 7. Update intent status
    await test_db_store.update_intent_status(intent_id, "resolved")

    # 8. Verify intent status updated
    intent_check = await test_db_store.get_intent(intent_id)
    assert intent_check is not None
    assert intent_check["status"] == "resolved"

    # 9. Delete result
    delete_response = await test_db_store.delete_result(result_id, test_session_id)
    assert delete_response["result_deleted"] == 1

    # 10. Verify result is gone but intent and utterance still exist
    result_check = await test_db_store.get_result(result_id)
    assert result_check is None

    intent_check = await test_db_store.get_intent(intent_id)
    assert intent_check is not None

    utterance_check = await test_db_store.get_utterance(utterance_id)
    assert utterance_check is not None


@pytest.mark.asyncio
async def test_result_with_complex_data_structure(test_db_store, test_session_id: str) -> None:
    """Test that results with complex nested data structures are stored correctly."""
    topic_id = await test_db_store.create_topic(
        label="Complex Data Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create result with complex nested data
    complex_data = {
        "level1": {
            "level2": {
                "level3": {
                    "value": "deep",
                    "array": [1, 2, 3, 4, 5],
                    "objects": [{"a": 1}, {"b": 2}, {"c": 3}]
                },
                "metadata": {
                    "timestamp": 1234567890,
                    "nested": {"key": "value"}
                }
            },
            "top_array": ["item1", "item2", "item3"]
        },
        "strings": ["test", "data", "structure"],
        "numbers": [1, 2, 3, 4, 5],
        "mixed": [
            {"type": "object", "value": 1},
            {"type": "array", "value": [1, 2, 3]},
            "string_value",
            123,
            True,
            False,
            None
        ]
    }

    result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Complex data result",
        data=complex_data
    )

    # Verify complex data is stored and retrieved correctly
    result_check = await test_db_store.get_result(result_id)
    assert result_check is not None

    stored_data = json.loads(result_check["data"])
    assert stored_data == complex_data

    # Verify deep structure is preserved
    assert stored_data["level1"]["level2"]["level3"]["value"] == "deep"
    assert stored_data["level1"]["level2"]["level3"]["array"] == [1, 2, 3, 4, 5]
    assert stored_data["mixed"][6] is None


@pytest.mark.asyncio
async def test_result_creation_with_retry(test_db_store, test_session_id: str) -> None:
    """Test that result creation with retry logic works correctly."""
    topic_id = await test_db_store.create_topic(
        label="Retry Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create multiple results rapidly to test retry logic
    result_ids = []
    for i in range(5):
        result_id = await test_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=test_session_id,
            summary=f"Retry test result {i}",
            data={"retry": i}
        )
        result_ids.append(result_id)

    # Verify all results are stored correctly despite rapid creation
    for i, result_id in enumerate(result_ids):
        result_check = await test_db_store.get_result(result_id)
        assert result_check is not None
        data = json.loads(result_check["data"])
        assert data["retry"] == i


@pytest.mark.asyncio
async def test_result_queries_and_filtering(test_db_store, test_session_id: str) -> None:
    """Test various result query methods and filtering."""
    # Create multiple topics
    topic1_id = await test_db_store.create_topic(
        label="Query Test Topic 1",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    topic2_id = await test_db_store.create_topic(
        label="Query Test Topic 2",
        topic_type="research",
        scope="session",
        session_id=test_session_id
    )

    # Create utterance and intent for result linking
    utterance_id = await test_db_store.create_utterance(
        session_id=test_session_id,
        raw_text="query test utterance"
    )

    intent_id = await test_db_store.create_intent(
        utterance_id=utterance_id,
        session_id=test_session_id,
        project_slug="test",
        intent_type="status",
        topic_id=topic1_id
    )

    # Create results with different properties
    result1_id = await test_db_store.create_result(
        intent_id=intent_id,
        topic_id=topic1_id,
        session_id=test_session_id,
        summary="Result 1",
        data={"index": 1},
        urgency="high"
    )

    result2_id = await test_db_store.create_result(
        intent_id=intent_id,
        topic_id=topic1_id,
        session_id=test_session_id,
        summary="Result 2",
        data={"index": 2},
        urgency="normal"
    )

    result3_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic2_id,
        session_id=test_session_id,
        summary="Result 3",
        data={"index": 3},
        urgency="critical"
    )

    # Test get_results_for_intent
    intent_results = await test_db_store.get_results_for_intent(intent_id)
    assert len(intent_results) == 2
    intent_result_ids = {r["id"] for r in intent_results}
    assert result1_id in intent_result_ids
    assert result2_id in intent_result_ids

    # Test get_latest_result_for_topic
    latest_topic1 = await test_db_store.get_latest_result_for_topic(topic1_id)
    assert latest_topic1 is not None
    assert latest_topic1["id"] in [result1_id, result2_id]

    latest_topic2 = await test_db_store.get_latest_result_for_topic(topic2_id)
    assert latest_topic2 is not None
    assert latest_topic2["id"] == result3_id

    # Test get_all_results
    all_results = await test_db_store.get_all_results()
    assert len(all_results) >= 3
    all_result_ids = {r["id"] for r in all_results}
    assert result1_id in all_result_ids
    assert result2_id in all_result_ids
    assert result3_id in all_result_ids


@pytest.mark.asyncio
async def test_result_update_operations(test_db_store, test_session_id: str) -> None:
    """Test result update operations."""
    topic_id = await test_db_store.create_topic(
        label="Update Test Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create result
    result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Original summary",
        data={"original": True},
        card_fallback=False
    )

    # Update card_fallback
    await test_db_store.update_result_card_fallback(result_id, True)

    # Verify update
    result_check = await test_db_store.get_result(result_id)
    assert result_check is not None
    assert result_check["card_fallback"] == 1  # True = 1

    # Update back to False
    await test_db_store.update_result_card_fallback(result_id, False)

    # Verify update
    result_check = await test_db_store.get_result(result_id)
    assert result_check is not None
    assert result_check["card_fallback"] == 0  # False = 0


@pytest.mark.asyncio
async def test_result_timestamp_ordering(test_db_store, test_session_id: str) -> None:
    """Test that result timestamps maintain correct ordering."""
    topic_id = await test_db_store.create_topic(
        label="Timestamp Ordering Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create multiple results with delays
    import asyncio

    result_ids = []
    timestamps = []

    for i in range(3):
        result_id = await test_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=test_session_id,
            summary=f"Result {i}",
            data={"index": i}
        )
        result_ids.append(result_id)

        # Capture timestamp immediately after creation
        timestamps.append(int(datetime.now().timestamp()))

        # Small delay to ensure different timestamps
        await asyncio.sleep(0.01)

    # Verify timestamps are in correct order
    async with aiosqlite.connect(test_db_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT id, created_at FROM results WHERE id IN ({})
               ORDER BY created_at ASC""".format(
                ",".join(f"'{rid}'" for rid in result_ids)
            )
        ) as cur:
            results = await cur.fetchall()
            assert len(results) == 3

            # Verify ordering matches creation order
            for i, result in enumerate(results):
                assert result["id"] == result_ids[i]


# --- Data integrity and edge cases -------------------------------------------

@pytest.mark.asyncio
async def test_result_with_special_characters(test_db_store, test_session_id: str) -> None:
    """Test that results with special characters are stored correctly."""
    topic_id = await test_db_store.create_topic(
        label="Special Chars Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create result with special characters
    special_summary = "Test with 'quotes', \"double quotes\", `backticks`, and \n newlines"
    special_data = {
        "unicode": "Test with unicode: 🎉 🔥 💡",
        "html": "<script>alert('test')</script>",
        "sql": "SELECT * FROM users WHERE name = 'admin' --",
        "json": '{"nested": {"data": "value"}}',
        "newlines": "Line 1\nLine 2\nLine 3",
        "tabs": "Col1\tCol2\tCol3",
        "mixed": "Mix of 'single' and \"double\" quotes"
    }

    result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary=special_summary,
        data=special_data
    )

    # Verify special characters are preserved
    result_check = await test_db_store.get_result(result_id)
    assert result_check is not None
    assert result_check["summary"] == special_summary

    stored_data = json.loads(result_check["data"])
    assert stored_data["unicode"] == special_data["unicode"]
    assert stored_data["html"] == special_data["html"]
    assert stored_data["sql"] == special_data["sql"]
    assert stored_data["json"] == special_data["json"]
    assert stored_data["newlines"] == special_data["newlines"]
    assert stored_data["tabs"] == special_data["tabs"]
    assert stored_data["mixed"] == special_data["mixed"]


@pytest.mark.asyncio
async def test_result_with_large_data(test_db_store, test_session_id: str) -> None:
    """Test that results with large data payloads are stored correctly."""
    topic_id = await test_db_store.create_topic(
        label="Large Data Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create result with large data
    large_data = {
        "large_array": list(range(1000)),
        "large_string": "x" * 10000,
        "nested_large": {
            "array": [{"value": i, "data": "y" * 100} for i in range(100)]
        }
    }

    result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Large data result",
        data=large_data
    )

    # Verify large data is stored correctly
    result_check = await test_db_store.get_result(result_id)
    assert result_check is not None

    stored_data = json.loads(result_check["data"])
    assert len(stored_data["large_array"]) == 1000
    assert len(stored_data["large_string"]) == 10000
    assert len(stored_data["nested_large"]["array"]) == 100


@pytest.mark.asyncio
async def test_result_with_empty_and_null_values(test_db_store, test_session_id: str) -> None:
    """Test that results with empty and null values are stored correctly."""
    topic_id = await test_db_store.create_topic(
        label="Empty Values Topic",
        topic_type="project",
        scope="session",
        session_id=test_session_id
    )

    # Create result with various empty/null values
    empty_data = {
        "empty_string": "",
        "empty_array": [],
        "empty_object": {},
        "null_value": None,
        "zero": 0,
        "false": False
    }

    result_id = await test_db_store.create_result(
        intent_id=None,
        topic_id=topic_id,
        session_id=test_session_id,
        summary="Empty values result",
        data=empty_data
    )

    # Verify empty/null values are preserved
    result_check = await test_db_store.get_result(result_id)
    assert result_check is not None

    stored_data = json.loads(result_check["data"])
    assert stored_data["empty_string"] == ""
    assert stored_data["empty_array"] == []
    assert stored_data["empty_object"] == {}
    assert stored_data["null_value"] is None
    assert stored_data["zero"] == 0
    assert stored_data["false"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
