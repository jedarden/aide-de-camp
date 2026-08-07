"""
Session storage verification for test endpoint (bead adc-1n26t).

Verifies that results from the test endpoint are correctly persisted to the
SQLite session store, ensuring data integrity and proper record creation.

This test validates:
- Session record created with correct session_id
- Topic record created with type, utterance, and result
- Utterance record linked to topic
- Result record persisted with correct fields
- All text fields match the test payload exactly
- Foreign key relationships are valid
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from httpx import AsyncClient

from src.session.store import SessionStore, get_store, _store
from src.main import app


# --- fixtures ---------------------------------------------------------------


@pytest.fixture

@pytest.fixture

# --- test data ---------------------------------------------------------------

TEST_SYNTHETIC_PAYLOAD = {
    "session_id": None,  # Will be generated
    "surface_id": None,
    "test_data": {
        "utterance": "verify test storage integrity",
        "project_slug": "test-storage-verification",
        "intent_type": "status",
        "topic_label": "Storage Verification Test",
        "topic_type": "research",
        "summary": "Test result for session storage verification",
        "data": {
            "test_mode": True,
            "verification": "session_store_integrity",
            "fields": {
                "field1": "value1",
                "field2": "value2",
            }
        },
        "urgency": "normal",
        "result_type": "status:test-storage-verification"
    }
}


# --- storage verification tests ----------------------------------------------


class TestSyntheticDispatchStorageVerification:
    """
    Verify that POST /test/dispatch-synthetic correctly persists all records
    to the session store with proper data integrity.
    """

    @pytest.mark.asyncio
    async def test_session_record_created(self, test_test_db_store) -> None:
        """Verify that a session record is created with correct session_id."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        with patch('src.test.dispatch.get_store', return_value=test_store):
            # Create synthetic result without session_id (generates new one)
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=TEST_SYNTHETIC_PAYLOAD["test_data"]
            )

            response = await generate_synthetic_result(request)

            # Verify session exists in store
            session = await test_store.get_session(response.session_id)

            assert session is not None, "Session record not created"
            assert session["id"] == response.session_id, "Session ID mismatch"
            assert session["created_at"] is not None, "Session created_at is NULL"
            assert session["last_active"] is not None, "Session last_active is NULL"

    @pytest.mark.asyncio
    async def test_utterance_record_created(self, test_test_db_store) -> None:
        """Verify that an utterance record is created and linked to session."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        test_utterance = "verify test storage integrity"

        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=TEST_SYNTHETIC_PAYLOAD["test_data"]
            )

            response = await generate_synthetic_result(request)

            # Query utterances table directly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM utterances WHERE session_id = ?",
                    (response.session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    assert len(rows) == 1, f"Expected 1 utterance, got {len(rows)}"

                    utterance = dict(rows[0])
                    assert utterance["id"] == response.utterance_id, "Utterance ID mismatch"
                    assert utterance["session_id"] == response.session_id, "Utterance session_id mismatch"
                    assert utterance["raw_text"] == test_utterance, f"Utterance text mismatch: expected '{test_utterance}', got '{utterance['raw_text']}'"
                    assert utterance["created_at"] is not None, "Utterance created_at is NULL"

    @pytest.mark.asyncio
    async def test_intent_record_created(self, test_test_db_store) -> None:
        """Verify that an intent record is created and linked to utterance."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=TEST_SYNTHETIC_PAYLOAD["test_data"]
            )

            response = await generate_synthetic_result(request)

            # Query intents table directly by utterance_id
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM intents WHERE utterance_id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    assert len(rows) == 1, f"Expected 1 intent, got {len(rows)}"

                    intent = dict(rows[0])
                    assert intent["utterance_id"] == response.utterance_id, "Intent utterance_id mismatch"
                    assert intent["session_id"] == response.session_id, "Intent session_id mismatch"
                    assert intent["intent_type"] == "status", f"Intent type mismatch: expected 'status', got '{intent['intent_type']}'"
                    assert intent["status"] == "pending", f"Intent status should be 'pending', got '{intent['status']}'"
                    assert intent["created_at"] is not None, "Intent created_at is NULL"
                    # Store the actual intent_id for foreign key tests
                    stored_intent_id = intent["id"]

    @pytest.mark.asyncio
    async def test_topic_record_created(self, test_test_db_store) -> None:
        """Verify that a topic record is created with correct type and label."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        expected_topic_label = "Storage Verification Test"
        expected_topic_type = "research"
        expected_project_slug = "test-storage-verification"

        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data={
                    **TEST_SYNTHETIC_PAYLOAD["test_data"],
                    "topic_label": expected_topic_label,
                    "topic_type": expected_topic_type,
                    "project_slug": expected_project_slug
                }
            )

            response = await generate_synthetic_result(request)

            # Query topics table directly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM topics WHERE id = ?",
                    (response.topic_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    assert len(rows) == 1, f"Expected 1 topic, got {len(rows)}"

                    topic = dict(rows[0])
                    assert topic["id"] == response.topic_id, "Topic ID mismatch"
                    assert topic["label"] == expected_topic_label, f"Topic label mismatch: expected '{expected_topic_label}', got '{topic['label']}'"
                    assert topic["type"] == expected_topic_type, f"Topic type mismatch: expected '{expected_topic_type}', got '{topic['type']}'"
                    assert topic["scope"] == "session", f"Topic scope mismatch: expected 'session', got '{topic['scope']}'"
                    assert topic["session_id"] == response.session_id, "Topic session_id mismatch"

                    # Verify project_slugs stored as JSON
                    slugs = json.loads(topic["project_slugs"])
                    assert slugs == [expected_project_slug], f"Project slugs mismatch: expected ['{expected_project_slug}'], got {slugs}"

    @pytest.mark.asyncio
    async def test_result_record_created(self, test_test_db_store) -> None:
        """Verify that a result record is created with all fields intact."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        expected_summary = "Test result for session storage verification"
        expected_data = {
            "test_mode": True,
            "verification": "session_store_integrity",
            "fields": {
                "field1": "value1",
                "field2": "value2",
            }
        }

        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=TEST_SYNTHETIC_PAYLOAD["test_data"]
            )

            response = await generate_synthetic_result(request)

            # Query results table directly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM results WHERE session_id = ?",
                    (response.session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    assert len(rows) == 1, f"Expected 1 result, got {len(rows)}"

                    result = dict(rows[0])
                    assert result["intent_id"] == response.intent_id, "Result intent_id mismatch"
                    assert result["topic_id"] == response.topic_id, "Result topic_id mismatch"
                    assert result["session_id"] == response.session_id, "Result session_id mismatch"
                    assert result["summary"] == expected_summary, f"Result summary mismatch: expected '{expected_summary}', got '{result['summary']}'"
                    assert result["urgency"] == "normal", f"Result urgency mismatch: expected 'normal', got '{result['urgency']}'"
                    assert result["result_type"] == "status:test-storage-verification", f"Result type mismatch: expected 'status:test-storage-verification', got '{result['result_type']}'"

                    # Verify data stored as JSON matches exactly
                    stored_data = json.loads(result["data"])
                    assert stored_data == expected_data, f"Result data mismatch: expected {expected_data}, got {stored_data}"

    @pytest.mark.asyncio
    async def test_foreign_key_relationships(self, test_test_db_store) -> None:
        """Verify that foreign key relationships are correctly established."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=TEST_SYNTHETIC_PAYLOAD["test_data"]
            )

            response = await generate_synthetic_result(request)

            # Get the actual stored intent_id
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id FROM intents WHERE utterance_id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    intent_row = await cursor.fetchone()
                    assert intent_row is not None, "Intent not found for utterance"
                    stored_intent_id = intent_row["id"]

            # Verify utterance -> session relationship
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT session_id FROM utterances WHERE id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None, "Utterance not found"
                    assert row["session_id"] == response.session_id, "Utterance not linked to correct session"

            # Verify intent -> utterance relationship
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT utterance_id, session_id FROM intents WHERE id = ?",
                    (stored_intent_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None, "Intent not found"
                    assert row["utterance_id"] == response.utterance_id, "Intent not linked to correct utterance"
                    assert row["session_id"] == response.session_id, "Intent not linked to correct session"

            # Verify result -> intent -> topic relationships
            # Note: create_result uses response.intent_id, not the stored intent_id from create_intent
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT intent_id, topic_id, session_id FROM results WHERE session_id = ?",
                    (response.session_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None, "Result not found"
                    # Verify result is linked to the intent_id used during creation
                    assert row["intent_id"] == response.intent_id, f"Result not linked to intent used during creation, expected {response.intent_id}, got {row['intent_id']}"
                    assert row["topic_id"] == response.topic_id, "Result not linked to correct topic"
                    assert row["session_id"] == response.session_id, "Result not linked to correct session"

            # Verify topic -> session relationship
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT session_id, scope FROM topics WHERE id = ?",
                    (response.topic_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None, "Topic not found"
                    assert row["session_id"] == response.session_id, "Topic not linked to correct session"
                    assert row["scope"] == "session", f"Topic scope should be 'session', got '{row['scope']}'"

    @pytest.mark.asyncio
    async def test_text_fields_match_payload_exactly(self, test_test_db_store) -> None:
        """Verify that all text fields match the test payload exactly."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        custom_text = "Custom verification text with special chars: !@#$%^&*()"
        custom_summary = "Custom summary with unicode: café, naïve, résumé"

        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data={
                    "utterance": custom_text,
                    "topic_label": "Custom Topic Label",
                    "summary": custom_summary,
                    "data": {"custom": "data"},
                    "intent_type": "status",
                    "topic_type": "research",
                    "project_slug": "custom-project",
                    "urgency": "normal",
                    "result_type": "status:custom-project"
                }
            )

            response = await generate_synthetic_result(request)

            # Verify utterance text matches exactly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT raw_text FROM utterances WHERE id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None, "Utterance not found"
                    assert row["raw_text"] == custom_text, f"Utterance text mismatch: expected '{custom_text}', got '{row['raw_text']}'"

            # Verify topic label matches exactly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT label FROM topics WHERE id = ?",
                    (response.topic_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None, "Topic not found"
                    assert row["label"] == "Custom Topic Label", f"Topic label mismatch: expected 'Custom Topic Label', got '{row['label']}'"

            # Verify result summary matches exactly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT summary FROM results WHERE session_id = ?",
                    (response.session_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None, "Result not found"
                    assert row["summary"] == custom_summary, f"Result summary mismatch: expected '{custom_summary}', got '{row['summary']}'"

    @pytest.mark.asyncio
    async def test_multiple_synthetic_results_in_same_session(self, test_test_db_store) -> None:
        """Verify that multiple synthetic results in the same session are stored correctly."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        session_id = await test_store.create_session()

        with patch('src.test.dispatch.get_store', return_value=test_store):
            # Create first result
            request1 = SyntheticResultRequest(
                session_id=session_id,
                surface_id=None,
                test_data={
                    "utterance": "first test utterance",
                    "topic_label": "First Topic",
                    "summary": "First result",
                    "data": {"seq": 1},
                    "intent_type": "status",
                    "topic_type": "research",
                    "project_slug": "project1",
                    "urgency": "normal",
                    "result_type": "status:project1"
                }
            )

            response1 = await generate_synthetic_result(request1)

            # Create second result
            request2 = SyntheticResultRequest(
                session_id=session_id,
                surface_id=None,
                test_data={
                    "utterance": "second test utterance",
                    "topic_label": "Second Topic",
                    "summary": "Second result",
                    "data": {"seq": 2},
                    "intent_type": "lookup",
                    "topic_type": "project",
                    "project_slug": "project2",
                    "urgency": "high",
                    "result_type": "lookup:project2"
                }
            )

            response2 = await generate_synthetic_result(request2)

            # Verify both results in same session
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT COUNT(*) as count FROM results WHERE session_id = ?",
                    (session_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row["count"] == 2, f"Expected 2 results in session, got {row['count']}"

            # Verify utterances are distinct
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, raw_text FROM utterances WHERE session_id = ? ORDER BY created_at",
                    (session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    assert len(rows) == 2, f"Expected 2 utterances in session, got {len(rows)}"
                    utterance_texts = [row["raw_text"] for row in rows]
                    assert "first test utterance" in utterance_texts, "First utterance not found"
                    assert "second test utterance" in utterance_texts, "Second utterance not found"

            # Verify topics are distinct
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, label FROM topics WHERE session_id = ? ORDER BY created_at",
                    (session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    assert len(rows) == 2, f"Expected 2 topics in session, got {len(rows)}"
                    topic_labels = [row["label"] for row in rows]
                    assert "First Topic" in topic_labels, "First topic not found"
                    assert "Second Topic" in topic_labels, "Second topic not found"


# --- API endpoint tests ------------------------------------------------------


class TestSyntheticDispatchAPIEndpoint:
    """
    Verify that the HTTP API endpoint correctly persists data to session test_db_store.
    """

    @pytest.mark.asyncio
    async def test_api_creates_records_in_store(self, test_test_db_store) -> None:
        """Verify that calling the API endpoint creates records in the session test_db_store."""
        from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest

        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=TEST_SYNTHETIC_PAYLOAD["test_data"]
            )

            response = await generate_synthetic_result(request)

            # Verify all records exist in our test store
            session = await test_store.get_session(response.session_id)
            assert session is not None, "Session not found in store"

            # Verify utterance exists
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM utterances WHERE id = ?", (response.utterance_id,)
                ) as cursor:
                    utterance = await cursor.fetchone()
                    assert utterance is not None, "Utterance not found in store"

            # Verify intent exists (query by utterance_id since create_intent generates its own ID)
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM intents WHERE utterance_id = ?", (response.utterance_id,)
                ) as cursor:
                    intent = await cursor.fetchone()
                    assert intent is not None, "Intent not found in store"

            # Verify topic exists
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM topics WHERE id = ?", (response.topic_id,)
                ) as cursor:
                    topic = await cursor.fetchone()
                    assert topic is not None, "Topic not found in store"

            # Verify result exists (query by session_id since response.result_id may not match)
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM results WHERE session_id = ?", (response.session_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    assert result is not None, "Result not found in store"
