"""
Utterance creation and result linkage tests (bead adc-xh4ow3).

This test module verifies that create_utterance() correctly stores utterances
and links them to results through the intent chain.

Tests use fixtures from the infrastructure bead (adc-d6x7bs):
- in_memory_db_store: Isolated in-memory database for fast tests
- test_utterance_builder: Helper for creating test utterances
- test_intent_builder: Helper for creating test intents
- test_result_builder: Helper for creating test results
- test_topic_with_session: Pre-built session and topic

Coverage includes:
- create_utterance() stores raw text correctly
- create_utterance() stores optional utterance_id
- Utterance links to results correctly (via intent chain)
- Utterance-result relationships are retrievable
- Complete utterance creation workflow
"""

import json
import pytest
from datetime import datetime
from uuid import uuid4


class TestUtteranceCreation:
    """Test create_utterance() function storage and field persistence."""

    @pytest.mark.asyncio
    async def test_create_utterance_stores_raw_text_correctly(self, in_memory_db_store):
        """Test that create_utterance() stores raw text correctly."""
        # Arrange: Create a session
        session_id = await in_memory_db_store.create_session()
        raw_text = "Check the deployment status of pbx-web"

        # Act: Create utterance with raw text
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text=raw_text
        )

        # Assert: Raw text is stored correctly
        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance is not None
        assert utterance["id"] == utterance_id
        assert utterance["session_id"] == session_id
        assert utterance["raw_text"] == raw_text
        assert "created_at" in utterance

    @pytest.mark.asyncio
    async def test_create_utterance_with_special_characters(self, in_memory_db_store):
        """Test that create_utterance() preserves special characters exactly."""
        session_id = await in_memory_db_store.create_session()
        raw_text = "Test with special chars: émojis 🎉, unicode ™, quotes \"', and symbols @#$%^&*()"

        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text=raw_text
        )

        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance["raw_text"] == raw_text

    @pytest.mark.asyncio
    async def test_create_utterance_with_unicode(self, in_memory_db_store):
        """Test that create_utterance() handles Unicode characters correctly."""
        session_id = await in_memory_db_store.create_session()
        raw_text = "Unicode test: café, naïve, résumé, 北京, Москва, ✨💡🎯"

        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text=raw_text
        )

        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance["raw_text"] == raw_text

    @pytest.mark.asyncio
    async def test_create_utterance_stores_optional_utterance_id(self, in_memory_db_store):
        """Test that create_utterance() stores optional utterance_id parameter."""
        session_id = await in_memory_db_store.create_session()
        custom_utterance_id = str(uuid4())
        raw_text = "Utterance with custom ID"

        # Act: Create utterance with custom utterance_id
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text=raw_text,
            utterance_id=custom_utterance_id
        )

        # Assert: Custom utterance_id is used
        assert utterance_id == custom_utterance_id
        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance["id"] == custom_utterance_id

    @pytest.mark.asyncio
    async def test_create_utterance_generates_id_by_default(self, in_memory_db_store):
        """Test that create_utterance() generates UUID when utterance_id is None."""
        session_id = await in_memory_db_store.create_session()

        # Act: Create utterance without utterance_id
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Utterance with auto-generated ID"
        )

        # Assert: A valid UUID is generated
        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance is not None
        # Verify it's a valid UUID format (hex string with hyphens)
        assert len(utterance_id) == 36  # Standard UUID length
        assert utterance_id.count('-') == 4  # UUIDs have 4 hyphens

    @pytest.mark.asyncio
    async def test_create_utterance_records_timestamp(self, in_memory_db_store):
        """Test that create_utterance() records created_at timestamp."""
        import time
        session_id = await in_memory_db_store.create_session()

        before_creation = int(time.time())
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Timestamp test"
        )
        after_creation = int(time.time()) + 1  # Add 1 second buffer

        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance["created_at"] is not None
        assert before_creation <= utterance["created_at"] <= after_creation


class TestUtteranceResultLinkage:
    """Test utterance to result linkage through intent chain."""

    @pytest.mark.asyncio
    async def test_utterance_links_to_result_via_intent(self, in_memory_db_store, test_topic_with_session):
        """Test that utterance links to result correctly through intent chain."""
        session_id, topic_id = test_topic_with_session

        # Step 1: Create utterance
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Check pbx-web deployment status"
        )

        # Step 2: Create intent linking utterance to topic
        intent_id = await in_memory_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="pbx-web",
            intent_type="status",
            topic_id=topic_id
        )

        # Step 3: Create result linking to intent
        result_id = await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="2 pods running",
            data={"status": "healthy", "pods": 2}
        )

        # Assert: Complete chain exists
        # 1. Utterance exists
        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance is not None
        assert utterance["id"] == utterance_id

        # 2. Intent exists and links utterance
        intent = await in_memory_db_store.get_intent(intent_id)
        assert intent is not None
        assert intent["utterance_id"] == utterance_id
        assert intent["topic_id"] == topic_id

        # 3. Result exists and links to intent
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None
        assert result["intent_id"] == intent_id
        assert result["topic_id"] == topic_id

    @pytest.mark.asyncio
    async def test_utterance_result_relationship_is_retrievable(self, in_memory_db_store, test_topic_with_session):
        """Test that utterance-result relationships are retrievable."""
        session_id, topic_id = test_topic_with_session

        # Create the chain
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="What's the status?"
        )
        intent_id = await in_memory_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="pbx-web",
            intent_type="status",
            topic_id=topic_id
        )
        result_id = await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Status OK",
            data={"healthy": True}
        )

        # Retrieve result and verify linkage
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None

        # Trace back from result to utterance
        intent = await in_memory_db_store.get_intent(result["intent_id"])
        assert intent["utterance_id"] == utterance_id

        utterance = await in_memory_db_store.get_utterance(intent["utterance_id"])
        assert utterance is not None
        assert utterance["raw_text"] == "What's the status?"

    @pytest.mark.asyncio
    async def test_multiple_results_from_single_utterance(self, in_memory_db_store, test_topic_with_session):
        """Test that a single utterance can link to multiple results via multiple intents."""
        session_id, topic_id = test_topic_with_session

        # Create one utterance
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Check status of all services"
        )

        # Create multiple intents from the same utterance
        intent_ids = []
        for project_slug in ["pbx-web", "whisper-stt", "armor"]:
            intent_id = await in_memory_db_store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug=project_slug,
                intent_type="status",
                topic_id=topic_id
            )
            intent_ids.append(intent_id)

        # Create results for each intent
        result_ids = []
        for intent_id in intent_ids:
            result_id = await in_memory_db_store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Status for {intent_id[:8]}",
                data={"status": "running"}
            )
            result_ids.append(result_id)

        # Assert: All results trace back to the same utterance
        for result_id in result_ids:
            result = await in_memory_db_store.get_result(result_id)
            intent = await in_memory_db_store.get_intent(result["intent_id"])
            assert intent["utterance_id"] == utterance_id

        # Verify all intents link to the same utterance
        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance is not None
        assert utterance["raw_text"] == "Check status of all services"

    @pytest.mark.asyncio
    async def test_utterance_with_no_results(self, in_memory_db_store):
        """Test that utterances without linked results are stored correctly."""
        session_id = await in_memory_db_store.create_session()

        # Create utterance without any intent/result
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Orphaned utterance with no results"
        )

        # Verify utterance exists
        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance is not None
        assert utterance["raw_text"] == "Orphaned utterance with no results"

    @pytest.mark.asyncio
    async def test_utterance_retrieval_by_id(self, in_memory_db_store):
        """Test that utterances can be retrieved by their ID."""
        session_id = await in_memory_db_store.create_session()

        # Create multiple utterances
        utterance_1 = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="First utterance"
        )
        utterance_2 = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Second utterance"
        )

        # Verify each can be retrieved independently
        retrieved_1 = await in_memory_db_store.get_utterance(utterance_1)
        retrieved_2 = await in_memory_db_store.get_utterance(utterance_2)

        assert retrieved_1 is not None
        assert retrieved_2 is not None
        assert retrieved_1["id"] == utterance_1
        assert retrieved_2["id"] == utterance_2
        assert retrieved_1["raw_text"] == "First utterance"
        assert retrieved_2["raw_text"] == "Second utterance"

    @pytest.mark.asyncio
    async def test_utterance_nonexistent_retrieval(self, in_memory_db_store):
        """Test that retrieving a non-existent utterance returns None."""
        fake_id = str(uuid4())
        result = await in_memory_db_store.get_utterance(fake_id)
        assert result is None


class TestUtteranceResultDataIntegrity:
    """Test data integrity across utterance-result relationships."""

    @pytest.mark.asyncio
    async def test_utterance_text_preserved_through_result_chain(self, in_memory_db_store, test_topic_with_session):
        """Test that utterance raw text is preserved throughout the result chain."""
        session_id, topic_id = test_topic_with_session
        original_text = "Verify deployment status: pbx-web has 2/2 pods ready"

        # Create full chain
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text=original_text
        )
        intent_id = await in_memory_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="pbx-web",
            intent_type="status",
            topic_id=topic_id
        )
        result_id = await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Deployment verified",
            data={"pods": 2, "ready": 2}
        )

        # Trace back and verify text is preserved
        result = await in_memory_db_store.get_result(result_id)
        intent = await in_memory_db_store.get_intent(result["intent_id"])
        utterance = await in_memory_db_store.get_utterance(intent["utterance_id"])

        assert utterance["raw_text"] == original_text

    @pytest.mark.asyncio
    async def test_utterance_with_result_containing_original_text(self, in_memory_db_store, test_topic_with_session):
        """Test that results can include the original utterance text in data."""
        session_id, topic_id = test_topic_with_session
        original_text = "Check whisper-stt latency metrics"

        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text=original_text
        )
        intent_id = await in_memory_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="whisper-stt",
            intent_type="status",
            topic_id=topic_id
        )

        # Result includes original utterance text in its data
        result_id = await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Latency metrics retrieved",
            data={
                "utterance": original_text,
                "p50_ms": 45,
                "p95_ms": 120
            }
        )

        # Verify result data contains the utterance
        result = await in_memory_db_store.get_result(result_id)
        result_data = json.loads(result["data"])
        assert result_data["utterance"] == original_text

        # Verify utterance record also matches
        utterance = await in_memory_db_store.get_utterance(utterance_id)
        assert utterance["raw_text"] == original_text


class TestUtteranceCreationWorkflow:
    """Test complete utterance creation workflows."""

    @pytest.mark.asyncio
    async def test_complete_utterance_to_result_workflow(self, in_memory_db_store, test_topic_with_session):
        """Test the complete workflow from utterance creation to result storage."""
        session_id, topic_id = test_topic_with_session

        # Step 1: User creates an utterance
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Check the status of pbx-web deployment"
        )

        # Step 2: System creates an intent from the utterance
        intent_id = await in_memory_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="pbx-web",
            intent_type="status",
            topic_id=topic_id
        )

        # Step 3: Fetch/synthesize creates a result
        result_id = await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Deployment status: 2/2 pods running",
            data={
                "deployment": "pbx-web",
                "pods": 2,
                "ready": 2,
                "updated": 2,
                "available": 2
            }
        )

        # Verify complete workflow
        utterance = await in_memory_db_store.get_utterance(utterance_id)
        intent = await in_memory_db_store.get_intent(intent_id)
        result = await in_memory_db_store.get_result(result_id)

        assert utterance is not None
        assert intent is not None
        assert result is not None

        # Verify linkage chain
        assert intent["utterance_id"] == utterance_id
        assert result["intent_id"] == intent_id
        assert result["topic_id"] == topic_id

        # Verify data integrity
        assert utterance["raw_text"] == "Check the status of pbx-web deployment"
        assert result["summary"] == "Deployment status: 2/2 pods running"

    @pytest.mark.asyncio
    async def test_utterance_creation_with_custom_id_workflow(self, in_memory_db_store, test_topic_with_session):
        """Test utterance creation workflow with custom utterance_id."""
        session_id, topic_id = test_topic_with_session
        custom_id = str(uuid4())

        # Create utterance with custom ID
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Utterance with custom ID",
            utterance_id=custom_id
        )

        # Verify custom ID is used throughout chain
        intent_id = await in_memory_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="test",
            intent_type="status",
            topic_id=topic_id
        )

        intent = await in_memory_db_store.get_intent(intent_id)
        assert intent["utterance_id"] == custom_id

        utterance = await in_memory_db_store.get_utterance(custom_id)
        assert utterance is not None
        assert utterance["id"] == custom_id

    @pytest.mark.asyncio
    async def test_multiple_utterances_same_session(self, in_memory_db_store, test_topic_with_session):
        """Test creating multiple utterances in the same session."""
        session_id, topic_id = test_topic_with_session

        # Create multiple utterances
        utterance_1 = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="First question"
        )
        utterance_2 = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Second question"
        )
        utterance_3 = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Third question"
        )

        # Verify all exist and are distinct
        retrieved_1 = await in_memory_db_store.get_utterance(utterance_1)
        retrieved_2 = await in_memory_db_store.get_utterance(utterance_2)
        retrieved_3 = await in_memory_db_store.get_utterance(utterance_3)

        assert retrieved_1 is not None
        assert retrieved_2 is not None
        assert retrieved_3 is not None

        assert retrieved_1["id"] != retrieved_2["id"]
        assert retrieved_2["id"] != retrieved_3["id"]
        assert retrieved_3["id"] != retrieved_1["id"]

        # All belong to same session
        assert retrieved_1["session_id"] == session_id
        assert retrieved_2["session_id"] == session_id
        assert retrieved_3["session_id"] == session_id
