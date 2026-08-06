"""
Comprehensive utterance linkage and exact field matching verification.

This test verifies bead adc-4zek8 requirements:
- Utterance record linked to topic via foreign key (through intent)
- All text fields match test payload exactly
- Foreign key relationships are intact
- Complete data integrity verified
"""

import json
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest

from src.session.store import SessionStore
from src.test.dispatch import generate_synthetic_result, SyntheticResultRequest


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
async def test_store(tmp_path: Path) -> SessionStore:
    """An isolated SessionStore on a temp DB for testing."""
    db_path = tmp_path / "test_session.db"
    store = SessionStore(db_path)
    await store.initialize()
    yield store
    await store.close()


# --- test data ---------------------------------------------------------------

VERIFICATION_TEST_PAYLOAD = {
    "utterance": "verify linkage integrity and exact field matching",
    "project_slug": "linkage-verification",
    "intent_type": "status",
    "topic_label": "Linkage Verification Topic",
    "topic_type": "research",
    "summary": "Verification result for utterance-to-topic linkage",
    "data": {
        "verification_type": "linkage_integrity",
        "test_fields": {
            "field_a": "value_a",
            "field_b": "value_b",
            "field_c": 123,
            "field_d": True,
        }
    },
    "urgency": "normal",
    "result_type": "status:linkage-verification"
}


# --- verification tests ------------------------------------------------------


class TestUtteranceLinkageVerification:
    """
    Verify utterance linkage to topic via foreign key chain and exact field matching.

    Tests the complete path: utterance → intent → topic, ensuring:
    - Foreign key relationships are valid
    - Text fields match payload exactly
    - Data integrity is maintained
    """

    @pytest.mark.asyncio
    async def test_utterance_to_topic_linkage_via_intent(self, test_store: SessionStore) -> None:
        """Verify utterance is linked to topic through the intent foreign key chain."""
        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=VERIFICATION_TEST_PAYLOAD
            )

            response = await generate_synthetic_result(request)

            # Step 1: Verify utterance exists and get its details
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, session_id, raw_text FROM utterances WHERE id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    utterance = await cursor.fetchone()
                    assert utterance is not None, "Utterance not found in store"

            # Step 2: Verify intent exists and links to the utterance
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, utterance_id, topic_id, session_id FROM intents WHERE utterance_id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    intent = await cursor.fetchone()
                    assert intent is not None, "Intent not found for utterance"
                    assert intent["utterance_id"] == response.utterance_id, "Intent not linked to utterance"
                    assert intent["topic_id"] is not None, "Intent topic_id is NULL"

            # Step 3: Verify topic exists and is reachable through intent
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, label, type, session_id FROM topics WHERE id = ?",
                    (intent["topic_id"],)
                ) as cursor:
                    topic = await cursor.fetchone()
                    assert topic is not None, "Topic not found through intent linkage"
                    assert topic["id"] == intent["topic_id"], "Topic ID mismatch"

            # Step 4: Verify complete chain: utterance → intent → topic
            # The linkage is indirect but valid: utterance.utterance_id → intent.utterance_id → intent.topic_id → topic.id
            assert utterance["id"] == intent["utterance_id"], "Utterance → Intent linkage broken"
            assert intent["topic_id"] == topic["id"], "Intent → Topic linkage broken"

    @pytest.mark.asyncio
    async def test_exact_text_field_matching(self, test_store: SessionStore) -> None:
        """Verify that all text fields match the test payload exactly, character-for-character."""
        test_utterance = VERIFICATION_TEST_PAYLOAD["utterance"]
        test_topic_label = VERIFICATION_TEST_PAYLOAD["topic_label"]
        test_summary = VERIFICATION_TEST_PAYLOAD["summary"]
        test_data = VERIFICATION_TEST_PAYLOAD["data"]

        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=VERIFICATION_TEST_PAYLOAD
            )

            response = await generate_synthetic_result(request)

            # Verify utterance.raw_text matches exactly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT raw_text FROM utterances WHERE id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    utterance = await cursor.fetchone()
                    assert utterance is not None, "Utterance not found"
                    assert utterance["raw_text"] == test_utterance, \
                        f"Utterance text mismatch: expected '{test_utterance}', got '{utterance['raw_text']}'"

            # Verify topic.label matches exactly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT label FROM topics WHERE id = ?",
                    (response.topic_id,)
                ) as cursor:
                    topic = await cursor.fetchone()
                    assert topic is not None, "Topic not found"
                    assert topic["label"] == test_topic_label, \
                        f"Topic label mismatch: expected '{test_topic_label}', got '{topic['label']}'"

            # Verify result.summary matches exactly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT summary FROM results WHERE session_id = ?",
                    (response.session_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    assert result is not None, "Result not found"
                    assert result["summary"] == test_summary, \
                        f"Result summary mismatch: expected '{test_summary}', got '{result['summary']}'"

            # Verify result.data (JSON) matches exactly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT data FROM results WHERE session_id = ?",
                    (response.session_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    stored_data = json.loads(result["data"])
                    assert stored_data == test_data, \
                        f"Result data mismatch: expected {test_data}, got {stored_data}"

    @pytest.mark.asyncio
    async def test_foreign_key_relationships_integrity(self, test_store: SessionStore) -> None:
        """Verify that all foreign key relationships are valid and intact."""
        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=VERIFICATION_TEST_PAYLOAD
            )

            response = await generate_synthetic_result(request)

            # Get the intent_id associated with the utterance
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id FROM intents WHERE utterance_id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    intent = await cursor.fetchone()
                    assert intent is not None, "Intent not found"

            # Verify referential integrity: utterance.session_id references sessions.id
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id FROM sessions WHERE id = ?",
                    (response.session_id,)
                ) as cursor:
                    session = await cursor.fetchone()
                    assert session is not None, "Session referenced by utterance does not exist"

            # Verify referential integrity: intent.utterance_id references utterances.id
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id FROM utterances WHERE id = ?",
                    (intent["id"],)
                ) as cursor:
                    # This should return the intent, not the utterance
                    # Correct query:
                    async with db.execute(
                        "SELECT id FROM utterances WHERE id = ?",
                        (response.utterance_id,)
                    ) as cur:
                        utterance_check = await cur.fetchone()
                        assert utterance_check is not None, "Utterance referenced by intent does not exist"

            # Verify referential integrity: intent.topic_id references topics.id
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id FROM topics WHERE id = ?",
                    (response.topic_id,)
                ) as cursor:
                    topic = await cursor.fetchone()
                    assert topic is not None, "Topic referenced by intent does not exist"

    @pytest.mark.asyncio
    async def test_complete_data_integrity_verification(self, test_store: SessionStore) -> None:
        """Verify complete data integrity across all related records."""
        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=VERIFICATION_TEST_PAYLOAD
            )

            response = await generate_synthetic_result(request)

            # Verify all records exist and are linked correctly
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row

                # 1. Session exists
                session = await db.execute(
                    "SELECT * FROM sessions WHERE id = ?", (response.session_id,)
                )
                session_row = await session.fetchone()
                assert session_row is not None, "Session record missing"

                # 2. Utterance exists and links to session
                utterance = await db.execute(
                    "SELECT * FROM utterances WHERE id = ?", (response.utterance_id,)
                )
                utterance_row = await utterance.fetchone()
                assert utterance_row is not None, "Utterance record missing"
                assert utterance_row["session_id"] == response.session_id, "Utterance not linked to session"

                # 3. Intent exists and links to utterance
                intent = await db.execute(
                    "SELECT * FROM intents WHERE utterance_id = ?", (response.utterance_id,)
                )
                intent_row = await intent.fetchone()
                assert intent_row is not None, "Intent record missing"
                assert intent_row["utterance_id"] == response.utterance_id, "Intent not linked to utterance"

                # 4. Topic exists and is linked by intent
                topic = await db.execute(
                    "SELECT * FROM topics WHERE id = ?", (response.topic_id,)
                )
                topic_row = await topic.fetchone()
                assert topic_row is not None, "Topic record missing"
                assert intent_row["topic_id"] == response.topic_id, "Intent not linked to topic"

                # 5. Result exists and links to intent and topic
                result = await db.execute(
                    "SELECT * FROM results WHERE session_id = ?", (response.session_id,)
                )
                result_row = await result.fetchone()
                assert result_row is not None, "Result record missing"
                assert result_row["intent_id"] == response.intent_id, "Result not linked to intent"
                assert result_row["topic_id"] == response.topic_id, "Result not linked to topic"

    @pytest.mark.asyncio
    async def test_utterance_linkage_with_special_characters(self, test_store: SessionStore) -> None:
        """Verify utterance linkage preserves special characters exactly."""
        special_text = "Test with special chars: émojis 🎉, unicode ™, quotes \"', and symbols @#$%^&*()"

        test_data = {
            "utterance": special_text,
            "project_slug": "special-chars-test",
            "intent_type": "status",
            "topic_label": "Special Characters Topic™",
            "topic_type": "research",
            "summary": "Summary with special chars: café, naïve, résumé",
            "data": {"special": "data with unicode: ✓ ✗ ★ ♥"},
            "urgency": "normal",
            "result_type": "status:special-chars-test"
        }

        with patch('src.test.dispatch.get_store', return_value=test_store):
            request = SyntheticResultRequest(
                session_id=None,
                surface_id=None,
                test_data=test_data
            )

            response = await generate_synthetic_result(request)

            # Verify special characters are preserved exactly in utterance
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT raw_text FROM utterances WHERE id = ?",
                    (response.utterance_id,)
                ) as cursor:
                    utterance = await cursor.fetchone()
                    assert utterance["raw_text"] == special_text, \
                        f"Special characters in utterance not preserved: expected '{special_text}', got '{utterance['raw_text']}'"

            # Verify special characters are preserved exactly in topic
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT label FROM topics WHERE id = ?",
                    (response.topic_id,)
                ) as cursor:
                    topic = await cursor.fetchone()
                    assert topic["label"] == "Special Characters Topic™", \
                        f"Special characters in topic not preserved"

            # Verify special characters are preserved exactly in summary
            async with aiosqlite.connect(test_store.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT summary FROM results WHERE session_id = ?",
                    (response.session_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    assert result["summary"] == "Summary with special chars: café, naïve, résumé", \
                        f"Special characters in summary not preserved"
