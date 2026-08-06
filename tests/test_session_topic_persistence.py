"""
Session and Topic Record Persistence Verification (bead adc-1nn4v).

This test verifies that session and topic records are correctly created and
persisted to the SQLite session store after test endpoint calls.

Acceptance Criteria:
- Session record exists with correct session_id
- Topic record created with type, utterance, and result fields
- Records queryable from data/session.db
- Basic data structure integrity verified
"""

import json
from pathlib import Path
from typing import Dict, Any

import aiosqlite
import pytest
import httpx
from uuid import uuid4


@pytest.mark.asyncio
async def test_session_persistence_after_synthetic_dispatch(async_client: httpx.AsyncClient) -> None:
    """Test that session records are persisted after synthetic dispatch endpoint call."""
    # Generate unique session_id for this test
    session_id = str(uuid4())

    # Call the synthetic dispatch endpoint
    response = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "surface_id": str(uuid4()),
            "test_data": {
                "utterance": "test session persistence",
                "topic_label": "Session Persistence Test",
                "topic_type": "research",
            }
        }
    )

    # Verify endpoint response
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert "utterance_id" in data
    assert "intent_id" in data
    assert "topic_id" in data

    # Query the database to verify session record exists
    db_path = Path("/home/coding/aide-de-camp/data/session.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify session record exists
        async with db.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,)
        ) as cursor:
            session_row = await cursor.fetchone()
            assert session_row is not None, "Session record not found in database"
            assert session_row["id"] == session_id
            assert session_row["created_at"] is not None
            assert session_row["last_active"] is not None


@pytest.mark.asyncio
async def test_topic_persistence_after_synthetic_dispatch(async_client: httpx.AsyncClient) -> None:
    """Test that topic records are persisted with correct fields after synthetic dispatch."""
    session_id = str(uuid4())
    topic_label = "Topic Persistence Test"
    topic_type = "research"

    # Call the synthetic dispatch endpoint
    response = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "surface_id": str(uuid4()),
            "test_data": {
                "utterance": "test topic persistence",
                "topic_label": topic_label,
                "topic_type": topic_type,
                "project_slug": "test-project",
            }
        }
    )

    # Verify endpoint response
    assert response.status_code == 200
    data = response.json()
    topic_id = data["topic_id"]

    # Query the database to verify topic record
    db_path = Path("/home/coding/aide-de-camp/data/session.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify topic record exists with correct fields
        async with db.execute(
            "SELECT * FROM topics WHERE id = ?",
            (topic_id,)
        ) as cursor:
            topic_row = await cursor.fetchone()
            assert topic_row is not None, "Topic record not found in database"
            assert topic_row["id"] == topic_id
            assert topic_row["label"] == topic_label
            assert topic_row["type"] == topic_type
            assert topic_row["scope"] == "session"
            assert topic_row["session_id"] == session_id
            assert topic_row["created_at"] is not None
            assert topic_row["last_active"] is not None
            assert topic_row["archived_at"] is None

            # Verify project_slugs is valid JSON
            project_slugs = json.loads(topic_row["project_slugs"])
            assert isinstance(project_slugs, list)
            assert "test-project" in project_slugs


@pytest.mark.asyncio
async def test_utterance_persistence_after_synthetic_dispatch(async_client: httpx.AsyncClient) -> None:
    """Test that utterance records are persisted after synthetic dispatch."""
    session_id = str(uuid4())
    test_utterance = "test utterance persistence"

    # Call the synthetic dispatch endpoint
    response = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "surface_id": str(uuid4()),
            "test_data": {
                "utterance": test_utterance,
            }
        }
    )

    # Verify endpoint response
    assert response.status_code == 200
    data = response.json()
    utterance_id = data["utterance_id"]

    # Query the database to verify utterance record
    db_path = Path("/home/coding/aide-de-camp/data/session.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify utterance record exists
        async with db.execute(
            "SELECT * FROM utterances WHERE id = ?",
            (utterance_id,)
        ) as cursor:
            utterance_row = await cursor.fetchone()
            assert utterance_row is not None, "Utterance record not found in database"
            assert utterance_row["id"] == utterance_id
            assert utterance_row["session_id"] == session_id
            assert utterance_row["raw_text"] == test_utterance
            assert utterance_row["created_at"] is not None


@pytest.mark.asyncio
async def test_intent_persistence_after_synthetic_dispatch(async_client: httpx.AsyncClient) -> None:
    """Test that intent records are persisted after synthetic dispatch."""
    session_id = str(uuid4())
    intent_type = "status"
    project_slug = "test-project"

    # Call the synthetic dispatch endpoint
    response = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "surface_id": str(uuid4()),
            "test_data": {
                "intent_type": intent_type,
                "project_slug": project_slug,
            }
        }
    )

    # Verify endpoint response
    assert response.status_code == 200
    data = response.json()
    intent_id = data["intent_id"]

    # Query the database to verify intent record
    db_path = Path("/home/coding/aide-de-camp/data/session.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify intent record exists
        async with db.execute(
            "SELECT * FROM intents WHERE id = ?",
            (intent_id,)
        ) as cursor:
            intent_row = await cursor.fetchone()
            assert intent_row is not None, "Intent record not found in database"
            assert intent_row["id"] == intent_id
            assert intent_row["session_id"] == session_id
            assert intent_row["intent_type"] == intent_type
            assert intent_row["project_slug"] == project_slug
            assert intent_row["status"] in ("pending", "dispatched")
            assert intent_row["created_at"] is not None


@pytest.mark.asyncio
async def test_result_persistence_after_synthetic_dispatch(async_client: httpx.AsyncClient) -> None:
    """Test that result records are persisted after synthetic dispatch."""
    session_id = str(uuid4())
    test_summary = "test result persistence"
    test_data = {"test_key": "test_value"}

    # Call the synthetic dispatch endpoint
    response = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "surface_id": str(uuid4()),
            "test_data": {
                "summary": test_summary,
                "data": test_data,
            }
        }
    )

    # Verify endpoint response
    assert response.status_code == 200
    data = response.json()
    topic_id = data["topic_id"]

    # Query the database to verify result record
    db_path = Path("/home/coding/aide-de-camp/data/session.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify result record exists for the topic
        async with db.execute(
            "SELECT * FROM results WHERE topic_id = ?",
            (topic_id,)
        ) as cursor:
            result_row = await cursor.fetchone()
            assert result_row is not None, "Result record not found in database"
            assert result_row["topic_id"] == topic_id
            assert result_row["session_id"] == session_id
            assert result_row["summary"] == test_summary

            # Verify data field contains valid JSON
            result_data = json.loads(result_row["data"])
            assert result_data["test_key"] == "test_value"

            assert result_row["urgency"] in ("critical", "high", "normal", "low")
            assert result_row["created_at"] is not None
            assert result_row["surfaced_at"] is not None


@pytest.mark.asyncio
async def test_complete_record_hierarchy_persistence(async_client: httpx.AsyncClient) -> None:
    """Test that all records in the hierarchy are persisted and linked correctly."""
    session_id = str(uuid4())

    # Call the synthetic dispatch endpoint
    response = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "surface_id": str(uuid4()),
            "test_data": {
                "utterance": "complete hierarchy test",
                "topic_label": "Complete Hierarchy Test",
                "topic_type": "project",
                "project_slug": "hierarchy-test",
                "intent_type": "status",
                "summary": "Complete hierarchy verification",
                "data": {"verify": "all records"},
            }
        }
    )

    # Verify endpoint response
    assert response.status_code == 200
    data = response.json()

    utterance_id = data["utterance_id"]
    intent_id = data["intent_id"]
    topic_id = data["topic_id"]

    # Query the database to verify all records and their relationships
    db_path = Path("/home/coding/aide-de-camp/data/session.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify session exists
        async with db.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,)
        ) as cursor:
            session = await cursor.fetchone()
            assert session is not None, "Session not found"

        # Verify utterance exists and is linked to session
        async with db.execute(
            "SELECT * FROM utterances WHERE id = ? AND session_id = ?",
            (utterance_id, session_id)
        ) as cursor:
            utterance = await cursor.fetchone()
            assert utterance is not None, "Utterance not found or not linked to session"

        # Verify intent exists and is linked to utterance and session
        async with db.execute(
            "SELECT * FROM intents WHERE id = ? AND utterance_id = ? AND session_id = ?",
            (intent_id, utterance_id, session_id)
        ) as cursor:
            intent = await cursor.fetchone()
            assert intent is not None, "Intent not found or not linked correctly"

        # Verify topic exists and is linked to session
        async with db.execute(
            "SELECT * FROM topics WHERE id = ? AND session_id = ?",
            (topic_id, session_id)
        ) as cursor:
            topic = await cursor.fetchone()
            assert topic is not None, "Topic not found or not linked to session"

        # Verify result exists and is linked to topic and session
        async with db.execute(
            "SELECT * FROM results WHERE topic_id = ? AND session_id = ?",
            (topic_id, session_id)
        ) as cursor:
            result = await cursor.fetchone()
            assert result is not None, "Result not found or not linked correctly"


@pytest.mark.asyncio
async def test_database_queryability(async_client: httpx.AsyncClient) -> None:
    """Test that persisted records are queryable from data/session.db."""
    session_id = str(uuid4())
    topic_label = "Queryability Test"

    # Create test data
    await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "surface_id": str(uuid4()),
            "test_data": {
                "topic_label": topic_label,
            }
        }
    )

    db_path = Path("/home/coding/aide-de-camp/data/session.db")

    # Verify database file exists and is queryable
    assert db_path.exists(), "Database file does not exist"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify all expected tables exist and are queryable
        tables_to_check = [
            "sessions",
            "utterances",
            "intents",
            "topics",
            "results",
            "surfaces",
        ]

        for table in tables_to_check:
            # Query should not raise an error
            async with db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                count = await cursor.fetchone()
                assert count is not None, f"Table {table} is not queryable"

        # Verify our session is queryable
        async with db.execute(
            "SELECT COUNT(*) FROM sessions WHERE id = ?",
            (session_id,)
        ) as cursor:
            count = (await cursor.fetchone())[0]
            assert count == 1, "Session should be queryable by session_id"

        # Verify our topic is queryable
        async with db.execute(
            "SELECT COUNT(*) FROM topics WHERE label = ? AND session_id = ?",
            (topic_label, session_id)
        ) as cursor:
            count = (await cursor.fetchone())[0]
            assert count == 1, "Topic should be queryable by label and session_id"


@pytest.mark.asyncio
async def test_data_structure_integrity(async_client: httpx.AsyncClient) -> None:
    """Test that persisted data maintains correct structure and types."""
    session_id = str(uuid4())

    response = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "surface_id": str(uuid4()),
            "test_data": {
                "topic_type": "exception",
                "project_slug": "integrity-test",
                "urgency": "high",
            }
        }
    )

    assert response.status_code == 200
    data = response.json()

    db_path = Path("/home/coding/aide-de-camp/data/session.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify topic type constraint
        async with db.execute(
            "SELECT type FROM topics WHERE id = ?",
            (data["topic_id"],)
        ) as cursor:
            topic = await cursor.fetchone()
            assert topic["type"] in ("project", "research", "personal", "exception", "compound")

        # Verify intent type is present
        async with db.execute(
            "SELECT intent_type FROM intents WHERE id = ?",
            (data["intent_id"],)
        ) as cursor:
            intent = await cursor.fetchone()
            assert intent["intent_type"] is not None
            assert len(intent["intent_type"]) > 0

        # Verify urgency constraint
        async with db.execute(
            "SELECT urgency FROM results WHERE topic_id = ?",
            (data["topic_id"],)
        ) as cursor:
            result = await cursor.fetchone()
            assert result["urgency"] in ("critical", "high", "normal", "low")

        # Verify timestamp fields are integers
        async with db.execute(
            "SELECT created_at, last_active FROM topics WHERE id = ?",
            (data["topic_id"],)
        ) as cursor:
            topic = await cursor.fetchone()
            assert isinstance(topic["created_at"], int)
            assert isinstance(topic["last_active"], int)
            assert topic["created_at"] > 0
            assert topic["last_active"] > 0

        # Verify JSON fields are valid
        async with db.execute(
            "SELECT project_slugs FROM topics WHERE id = ?",
            (data["topic_id"],)
        ) as cursor:
            topic = await cursor.fetchone()
            # Should be valid JSON array
            slugs = json.loads(topic["project_slugs"])
            assert isinstance(slugs, list)


@pytest.mark.asyncio
async def test_multiple_sessions_isolation(async_client: httpx.AsyncClient) -> None:
    """Test that records from different sessions are properly isolated."""
    session_id_1 = str(uuid4())
    session_id_2 = str(uuid4())

    # Create data for session 1
    response1 = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id_1,
            "surface_id": str(uuid4()),
            "test_data": {
                "topic_label": "Session 1 Topic",
            }
        }
    )

    # Create data for session 2
    response2 = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id_2,
            "surface_id": str(uuid4()),
            "test_data": {
                "topic_label": "Session 2 Topic",
            }
        }
    )

    assert response1.status_code == 200
    assert response2.status_code == 200

    data1 = response1.json()
    data2 = response2.json()

    db_path = Path("/home/coding/aide-de-camp/data/session.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify session isolation
        async with db.execute(
            "SELECT COUNT(*) FROM topics WHERE session_id = ?",
            (session_id_1,)
        ) as cursor:
            count1 = (await cursor.fetchone())[0]

        async with db.execute(
            "SELECT COUNT(*) FROM topics WHERE session_id = ?",
            (session_id_2,)
        ) as cursor:
            count2 = (await cursor.fetchone())[0]

        # Each session should have exactly 1 topic
        assert count1 == 1, "Session 1 should have exactly 1 topic"
        assert count2 == 1, "Session 2 should have exactly 1 topic"

        # Verify topics belong to correct sessions
        async with db.execute(
            "SELECT session_id FROM topics WHERE id = ?",
            (data1["topic_id"],)
        ) as cursor:
            topic1 = await cursor.fetchone()
            assert topic1["session_id"] == session_id_1

        async with db.execute(
            "SELECT session_id FROM topics WHERE id = ?",
            (data2["topic_id"],)
        ) as cursor:
            topic2 = await cursor.fetchone()
            assert topic2["session_id"] == session_id_2


@pytest.mark.asyncio
async def test_cascade_relationship_integrity(async_client: httpx.AsyncClient) -> None:
    """Test that cascading relationships between records are maintained."""
    session_id = str(uuid4())

    response = await async_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "surface_id": str(uuid4()),
        }
    )

    assert response.status_code == 200
    data = response.json()

    db_path = Path("/home/coding/aide-de-camp/data/session.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Trace the full cascade: session -> utterance -> intent -> topic -> result

        # Start from session
        async with db.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,)
        ) as cursor:
            session = await cursor.fetchone()
            assert session is not None

        # Session -> Utterance
        async with db.execute(
            "SELECT id, session_id FROM utterances WHERE id = ?",
            (data["utterance_id"],)
        ) as cursor:
            utterance = await cursor.fetchone()
            assert utterance is not None
            assert utterance["session_id"] == session_id

        # Utterance -> Intent
        async with db.execute(
            "SELECT id, utterance_id, session_id FROM intents WHERE id = ?",
            (data["intent_id"],)
        ) as cursor:
            intent = await cursor.fetchone()
            assert intent is not None
            assert intent["utterance_id"] == data["utterance_id"]
            assert intent["session_id"] == session_id

        # Intent -> Topic (via topic_id in intents table or directly)
        async with db.execute(
            "SELECT id, session_id FROM topics WHERE id = ?",
            (data["topic_id"],)
        ) as cursor:
            topic = await cursor.fetchone()
            assert topic is not None
            assert topic["session_id"] == session_id

        # Topic -> Result
        async with db.execute(
            "SELECT id, topic_id, session_id FROM results WHERE topic_id = ?",
            (data["topic_id"],)
        ) as cursor:
            result = await cursor.fetchone()
            assert result is not None
            assert result["topic_id"] == data["topic_id"]
            assert result["session_id"] == session_id
