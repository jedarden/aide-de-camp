"""
Session storage verification for test endpoint (bead adc-1n26t).

Verifies that results from the test endpoint are correctly persisted to the
SQLite session store, ensuring data integrity and proper record creation.

Acceptance criteria:
- Test results persist to data/session.db
- Session record created with correct session_id
- Topic record created with type, utterance, and result
- Utterance record linked to topic
- All text fields match the test payload exactly
- Foreign key relationships are correct
"""

import json
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from src.session.store import SessionStore

# Test data
TEST_SESSION_ID = "test-session-verification-123"
TEST_SURFACE_ID = "test-surface-verification-456"
TEST_UTTERANCE = "verify session storage for synthetic test endpoint"
TEST_TOPIC_LABEL = "Session Verification Test Topic"
TEST_PROJECT_SLUG = "test-project"
TEST_SUMMARY = "Synthetic test result for session storage verification"
TEST_DATA = {
    "test_mode": True,
    "synthetic": True,
    "message": "This is a synthetic test result for storage verification",
    "verification_fields": {
        "field1": "value1",
        "field2": "value2",
        "nested": {
            "key": "nested_value"
        }
    }
}


class StorageVerificationAssertions:
    """Assertion helpers for session storage verification."""

    @staticmethod
    async def verify_session_record(db_path: Path, session_id: str) -> Dict[str, Any]:
        """Verify session record exists and return it."""
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, f"Session record not found for session_id: {session_id}"
                session = dict(row)
                assert session["id"] == session_id, "Session ID mismatch"
                assert session["created_at"] is not None, "Session created_at should not be NULL"
                assert session["last_active"] is not None, "Session last_active should not be NULL"
                return session

    @staticmethod
    async def verify_utterance_record(
        db_path: Path,
        session_id: str,
        utterance_text: str
    ) -> Dict[str, Any]:
        """Verify utterance record exists and matches expected text."""
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM utterances WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, f"Utterance record not found for session_id: {session_id}"
                utterance = dict(row)
                assert utterance["session_id"] == session_id, "Utterance session_id mismatch"
                assert utterance["raw_text"] == utterance_text, \
                    f"Utterance text mismatch: expected '{utterance_text}', got '{utterance['raw_text']}'"
                assert utterance["id"] is not None, "Utterance ID should not be NULL"
                assert utterance["created_at"] is not None, "Utterance created_at should not be NULL"
                return utterance

    @staticmethod
    async def verify_topic_record(
        db_path: Path,
        session_id: str,
        topic_label: str,
        topic_type: str
    ) -> Dict[str, Any]:
        """Verify topic record exists with correct fields."""
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM topics
                   WHERE session_id = ? AND label = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (session_id, topic_label)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, \
                    f"Topic record not found for session_id: {session_id}, label: {topic_label}"
                topic = dict(row)
                assert topic["label"] == topic_label, f"Topic label mismatch: expected '{topic_label}', got '{topic['label']}'"
                assert topic["type"] == topic_type, f"Topic type mismatch: expected '{topic_type}', got '{topic['type']}'"
                assert topic["session_id"] == session_id, "Topic session_id mismatch"
                assert topic["scope"] == "session", "Topic scope should be 'session'"
                assert topic["archived_at"] is None, "Topic should not be archived"
                assert topic["id"] is not None, "Topic ID should not be NULL"
                return topic

    @staticmethod
    async def verify_intent_record(
        db_path: Path,
        session_id: str,
        utterance_id: str,
        topic_id: str,
        intent_type: str,
        project_slug: str | None
    ) -> Dict[str, Any]:
        """Verify intent record with correct relationships."""
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM intents
                   WHERE session_id = ? AND utterance_id = ? AND topic_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (session_id, utterance_id, topic_id)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, \
                    f"Intent record not found for session_id: {session_id}, utterance_id: {utterance_id}"
                intent = dict(row)
                assert intent["utterance_id"] == utterance_id, "Intent utterance_id mismatch"
                assert intent["session_id"] == session_id, "Intent session_id mismatch"
                assert intent["topic_id"] == topic_id, "Intent topic_id mismatch"
                assert intent["intent_type"] == intent_type, f"Intent type mismatch: expected '{intent_type}', got '{intent['intent_type']}'"
                if project_slug:
                    assert intent["project_slug"] == project_slug, f"Intent project_slug mismatch: expected '{project_slug}', got '{intent.get('project_slug')}'"
                assert intent["status"] in ("pending", "dispatched", "resolved"), \
                    f"Intent status should be valid, got: {intent['status']}"
                return intent

    @staticmethod
    async def verify_result_record(
        db_path: Path,
        session_id: str,
        topic_id: str,
        summary: str,
        data: Dict[str, Any],
        urgency: str = "normal"
    ) -> Dict[str, Any]:
        """Verify result record with correct data and relationships."""
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM results
                   WHERE session_id = ? AND topic_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (session_id, topic_id)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, \
                    f"Result record not found for session_id: {session_id}, topic_id: {topic_id}"
                result = dict(row)
                assert result["session_id"] == session_id, "Result session_id mismatch"
                assert result["topic_id"] == topic_id, "Result topic_id mismatch"
                assert result["summary"] == summary, \
                    f"Result summary mismatch: expected '{summary}', got '{result['summary']}'"

                # Verify data field matches exactly
                stored_data = json.loads(result["data"])
                assert stored_data == data, \
                    f"Result data mismatch:\nExpected: {json.dumps(data, indent=2)}\nGot: {json.dumps(stored_data, indent=2)}"

                assert result["urgency"] == urgency, f"Result urgency mismatch: expected '{urgency}', got '{result['urgency']}'"
                assert result["created_at"] is not None, "Result created_at should not be NULL"
                assert result["surfaced_at"] is not None, "Result surfaced_at should not be NULL"
                return result

    @staticmethod
    async def verify_foreign_key_relationships(
        db_path: Path,
        session_id: str,
        utterance_id: str,
        topic_id: str,
        intent_id: str,
        result_id: str
    ) -> None:
        """Verify all foreign key relationships are correct."""
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # Verify utterance -> session relationship
            async with db.execute(
                "SELECT session_id FROM utterances WHERE id = ?",
                (utterance_id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, "Utterance not found"
                assert row["session_id"] == session_id, "Utterance should reference session"

            # Verify intent -> utterance and intent -> topic relationships
            async with db.execute(
                "SELECT utterance_id, topic_id FROM intents WHERE id = ?",
                (intent_id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, "Intent not found"
                assert row["utterance_id"] == utterance_id, "Intent should reference utterance"
                assert row["topic_id"] == topic_id, "Intent should reference topic"

            # Verify topic -> session relationship
            async with db.execute(
                "SELECT session_id FROM topics WHERE id = ?",
                (topic_id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, "Topic not found"
                assert row["session_id"] == session_id, "Topic should reference session"

            # Verify result -> topic and result -> session relationships
            async with db.execute(
                "SELECT topic_id, session_id FROM results WHERE id = ?",
                (result_id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, "Result not found"
                assert row["topic_id"] == topic_id, "Result should reference topic"
                assert row["session_id"] == session_id, "Result should reference session"

    @staticmethod
    async def verify_text_field_exact_match(
        db_path: Path,
        session_id: str,
        expected_utterance: str,
        expected_summary: str
    ) -> None:
        """Verify all text fields match the test payload exactly."""
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # Check utterance text
            async with db.execute(
                "SELECT raw_text FROM utterances WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, "Utterance not found"
                assert row["raw_text"] == expected_utterance, \
                    f"Utterance text exact match failed: expected '{expected_utterance}', got '{row['raw_text']}'"

            # Check result summary
            async with db.execute(
                """SELECT summary FROM results
                   WHERE session_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, "Result not found"
                assert row["summary"] == expected_summary, \
                    f"Result summary exact match failed: expected '{expected_summary}', got '{row['summary']}'"

    @staticmethod
    async def count_records_by_session(db_path: Path, session_id: str) -> Dict[str, int]:
        """Count all records for a session."""
        async with aiosqlite.connect(db_path) as db:
            counts = {}

            async with db.execute(
                "SELECT COUNT(*) FROM sessions WHERE id = ?",
                (session_id,)
            ) as cursor:
                counts["sessions"] = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM utterances WHERE session_id = ?",
                (session_id,)
            ) as cursor:
                counts["utterances"] = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM topics WHERE session_id = ?",
                (session_id,)
            ) as cursor:
                counts["topics"] = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM intents WHERE session_id = ?",
                (session_id,)
            ) as cursor:
                counts["intents"] = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM results WHERE session_id = ?",
                (session_id,)
            ) as cursor:
                counts["results"] = (await cursor.fetchone())[0]

            return counts


# --- fixtures ---------------------------------------------------------------


@pytest.fixture

@pytest.fixture
    # Import after setting env var so the store picks it up
    from src.session.store import SessionStore

    # Initialize the test database
    store = SessionStore(test_store_path)
    await test_db_store.initialize()
    yield store
    await test_db_store.close()

    # Cleanup
    del os.environ["ADC_DB_PATH"]


@pytest.fixture
    with patch("src.test.dispatch.get_store", return_value=verification_store):
        with TestClient(app) as client:
            yield client


# --- tests --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthetic_result_session_storage(verification_test_db_store, sync_verification_client, test_store_path: Path) -> None:
    """Verify complete session storage for synthetic result endpoint."""
    assertions = StorageVerificationAssertions()

    # Create synthetic result
    response = sync_verification_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": TEST_SESSION_ID,
            "surface_id": TEST_SURFACE_ID,
            "test_data": {
                "utterance": TEST_UTTERANCE,
                "topic_label": TEST_TOPIC_LABEL,
                "topic_type": "research",
                "project_slug": TEST_PROJECT_SLUG,
                "intent_type": "status",
                "summary": TEST_SUMMARY,
                "data": TEST_DATA,
                "urgency": "normal",
                "result_type": "status"
            }
        }
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    result_data = response.json()

    # Extract IDs from response
    utterance_id = result_data["utterance_id"]
    topic_id = result_data["topic_id"]
    intent_id = result_data["intent_id"]

    # Verify session record created with correct session_id
    session = await assertions.verify_session_record(test_store_path, TEST_SESSION_ID)
    assert session["id"] == TEST_SESSION_ID

    # Verify utterance record linked to session
    utterance = await assertions.verify_utterance_record(
        test_store_path, TEST_SESSION_ID, TEST_UTTERANCE
    )
    assert utterance["id"] == utterance_id

    # Verify topic record created with correct type and linked to session
    topic = await assertions.verify_topic_record(
        test_store_path, TEST_SESSION_ID, TEST_TOPIC_LABEL, "research"
    )
    assert topic["id"] == topic_id

    # Verify intent record with correct relationships
    intent = await assertions.verify_intent_record(
        test_store_path,
        TEST_SESSION_ID,
        utterance_id,
        topic_id,
        "status",
        TEST_PROJECT_SLUG
    )
    assert intent["id"] == intent_id

    # Verify result record with correct data
    result = await assertions.verify_result_record(
        test_store_path,
        TEST_SESSION_ID,
        topic_id,
        TEST_SUMMARY,
        TEST_DATA,
        "normal"
    )

    # Verify all foreign key relationships
    await assertions.verify_foreign_key_relationships(
        test_store_path,
        TEST_SESSION_ID,
        utterance_id,
        topic_id,
        intent_id,
        result["id"]
    )

    # Verify all text fields match the test payload exactly
    await assertions.verify_text_field_exact_match(
        test_store_path,
        TEST_SESSION_ID,
        TEST_UTTERANCE,
        TEST_SUMMARY
    )

    # Verify record counts
    counts = await assertions.count_records_by_session(test_store_path, TEST_SESSION_ID)
    assert counts["sessions"] == 1, "Should have 1 session"
    assert counts["utterances"] == 1, "Should have 1 utterance"
    assert counts["topics"] == 1, "Should have 1 topic"
    assert counts["intents"] == 1, "Should have 1 intent"
    assert counts["results"] == 1, "Should have 1 result"


@pytest.mark.asyncio
async def test_synthetic_result_custom_data_persistence(verification_test_db_store, sync_verification_client, test_store_path: Path) -> None:
    """Verify that custom test data is persisted exactly as provided."""
    assertions = StorageVerificationAssertions()

    custom_data = {
        "custom_field": "custom_value",
        "nested": {
            "array": [1, 2, 3],
            "object": {"key": "value"}
        },
        "number": 42,
        "boolean": True
    }

    response = sync_verification_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": "custom-test-session",
            "test_data": {
                "utterance": "custom test utterance",
                "topic_label": "Custom Topic",
                "summary": "Custom summary",
                "data": custom_data
            }
        }
    )

    assert response.status_code == 200
    result_data = response.json()

    # Verify custom data persisted exactly
    result = await assertions.verify_result_record(
        test_store_path,
        "custom-test-session",
        result_data["topic_id"],
        "Custom summary",
        custom_data
    )

    stored_data = json.loads(result["data"])
    assert stored_data == custom_data, "Custom data should persist exactly"


@pytest.mark.asyncio
async def test_multiple_synthetic_results_same_session(verification_test_db_store, sync_verification_client, test_store_path: Path) -> None:
    """Verify multiple results can be stored in the same session."""
    assertions = StorageVerificationAssertions()

    session_id = "multi-result-session"

    # Create first result
    response1 = sync_verification_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "test_data": {
                "utterance": "first utterance",
                "topic_label": "Topic 1",
                "summary": "First result"
            }
        }
    )
    assert response1.status_code == 200

    # Create second result
    response2 = sync_verification_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_id,
            "test_data": {
                "utterance": "second utterance",
                "topic_label": "Topic 2",
                "summary": "Second result"
            }
        }
    )
    assert response2.status_code == 200

    # Verify counts
    counts = await assertions.count_records_by_session(test_store_path, session_id)
    assert counts["sessions"] == 1, "Should have 1 session"
    assert counts["utterances"] == 2, "Should have 2 utterances"
    assert counts["topics"] == 2, "Should have 2 topics"
    assert counts["intents"] == 2, "Should have 2 intents"
    assert counts["results"] == 2, "Should have 2 results"


@pytest.mark.asyncio
async def test_session_isolation(verification_test_db_store, sync_verification_client, test_store_path: Path) -> None:
    """Verify that different sessions maintain proper isolation."""
    assertions = StorageVerificationAssertions()

    session_a = "isolation-session-a"
    session_b = "isolation-session-b"

    # Create result in session A
    sync_verification_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_a,
            "test_data": {
                "utterance": "session a utterance",
                "topic_label": "Session A Topic",
                "summary": "Session A result"
            }
        }
    )

    # Create result in session B
    sync_verification_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": session_b,
            "test_data": {
                "utterance": "session b utterance",
                "topic_label": "Session B Topic",
                "summary": "Session B result"
            }
        }
    )

    # Verify session A has only its records
    counts_a = await assertions.count_records_by_session(test_store_path, session_a)
    assert counts_a["sessions"] == 1
    assert counts_a["utterances"] == 1
    assert counts_a["topics"] == 1

    # Verify session B has only its records
    counts_b = await assertions.count_records_by_session(test_store_path, session_b)
    assert counts_b["sessions"] == 1
    assert counts_b["utterances"] == 1
    assert counts_b["topics"] == 1

    # Verify total records across both sessions
    async with aiosqlite.connect(test_store_path) as db:
        async with db.execute("SELECT COUNT(*) FROM sessions") as cursor:
            total_sessions = (await cursor.fetchone())[0]
        assert total_sessions == 2, "Should have 2 sessions total"

        async with db.execute("SELECT COUNT(*) FROM utterances") as cursor:
            total_utterances = (await cursor.fetchone())[0]
        assert total_utterances == 2, "Should have 2 utterances total"


@pytest.mark.asyncio
async def test_text_field_exact_matching(verification_test_db_store, sync_verification_client, test_store_path: Path) -> None:
    """Verify that all text fields match the payload exactly, including special characters."""
    assertions = StorageVerificationAssertions()

    special_text = "Test with 'quotes', \"double quotes\", and \n newlines \t tabs"
    special_summary = "Summary with <html> & entities; and 🔥 emoji"

    response = sync_verification_client.post(
        "/api/v1/test/dispatch-synthetic",
        json={
            "session_id": "special-chars-session",
            "test_data": {
                "utterance": special_text,
                "topic_label": "Special Characters Topic",
                "summary": special_summary
            }
        }
    )

    assert response.status_code == 200

    # Verify exact text matching
    await assertions.verify_text_field_exact_match(
        test_store_path,
        "special-chars-session",
        special_text,
        special_summary
    )
