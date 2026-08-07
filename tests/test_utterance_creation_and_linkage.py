"""
Utterance creation and linkage tests (bead adc-xh4ow3).

Tests the create_utterance() function and its linkage to results:
1. create_utterance() stores raw text correctly
2. Utterance links to results correctly (via utterance -> intent -> result chain)
3. Utterance stores optional utterance_id parameter
4. Utterance-result relationships are retrievable

Uses fixtures from the infrastructure bead (adc-d6x7bs).
"""

import pytest
from uuid import uuid4
from src.session.store import SessionStore


class TestUtteranceCreation:
    """Tests for utterance creation functionality."""

    @pytest.mark.asyncio
    async def test_create_utterance_stores_raw_text_correctly(
        self,
        test_db_store: SessionStore
    ) -> None:
        """Test that create_utterance() stores raw text correctly.

        Creates an utterance with specific raw text and verifies:
        1. The raw text is stored exactly as provided
        2. The utterance can be retrieved by ID
        3. All fields are correctly populated
        """
        # Create a session and utterance
        session_id = await test_db_store.create_session()
        test_raw_text = "What's the deployment status of pbx-web?"

        utterance_id = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text=test_raw_text
        )

        # Retrieve the utterance and verify raw text is stored correctly
        utterance = await test_db_store.get_utterance(utterance_id)

        assert utterance is not None, "Utterance should be retrievable by ID"
        assert utterance["id"] == utterance_id, "Utterance ID should match"
        assert utterance["session_id"] == session_id, "Session ID should match"
        assert utterance["raw_text"] == test_raw_text, (
            f"Raw text should be stored exactly as provided. "
            f"Expected: {test_raw_text!r}, Got: {utterance['raw_text']!r}"
        )
        assert utterance["created_at"] is not None, "created_at should be set"

    @pytest.mark.asyncio
    async def test_create_utterance_with_optional_utterance_id(
        self,
        test_db_store: SessionStore
    ) -> None:
        """Test that utterance stores optional utterance_id parameter.

        Verifies that when a custom utterance_id is provided:
        1. The custom ID is used (not a generated UUID)
        2. The utterance is retrievable by that custom ID
        3. The custom ID is properly stored in the database
        """
        # Create a session
        session_id = await test_db_store.create_session()

        # Create utterance with custom utterance_id
        custom_utterance_id = str(uuid4())
        test_raw_text = "Check the recent Argo workflow runs"

        returned_utterance_id = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text=test_raw_text,
            utterance_id=custom_utterance_id
        )

        # Verify the custom ID is returned
        assert returned_utterance_id == custom_utterance_id, (
            f"Custom utterance_id should be returned. "
            f"Expected: {custom_utterance_id}, Got: {returned_utterance_id}"
        )

        # Verify the utterance is retrievable by the custom ID
        utterance = await test_db_store.get_utterance(custom_utterance_id)

        assert utterance is not None, "Utterance should be retrievable by custom ID"
        assert utterance["id"] == custom_utterance_id, "Stored ID should match custom ID"
        assert utterance["raw_text"] == test_raw_text, "Raw text should be stored correctly"

    @pytest.mark.asyncio
    async def test_create_utterance_generates_id_when_not_provided(
        self,
        test_db_store: SessionStore
    ) -> None:
        """Test that create_utterance generates UUID when utterance_id is None.

        Verifies that when utterance_id is not provided:
        1. A UUID is automatically generated
        2. The generated ID is a valid UUID string
        3. The utterance is retrievable by the generated ID
        """
        # Create a session
        session_id = await test_db_store.create_session()

        # Create utterance without providing utterance_id (should auto-generate)
        returned_utterance_id = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text="Show me the deployment logs"
        )

        # Verify a valid UUID was generated
        assert returned_utterance_id is not None, "An ID should be generated"

        # Try to parse it as a UUID to verify format
        try:
            from uuid import UUID
            # This will raise ValueError if not a valid UUID
            uuid_obj = UUID(returned_utterance_id)
            # Verify it's a UUID4 (hex format)
            assert len(returned_utterance_id) == 36, "UUID should be 36 characters"
            assert returned_utterance_id.count('-') == 4, "UUID should have 4 hyphens"
        except (ValueError, AttributeError):
            pytest.fail(f"Generated ID should be a valid UUID, got: {returned_utterance_id!r}")

        # Verify the utterance is retrievable by the generated ID
        utterance = await test_db_store.get_utterance(returned_utterance_id)
        assert utterance is not None, "Utterance should be retrievable by generated ID"
        assert utterance["id"] == returned_utterance_id, "ID should be stored correctly"

    @pytest.mark.asyncio
    async def test_create_utterance_with_empty_string(
        self,
        test_db_store: SessionStore
    ) -> None:
        """Test that create_utterance handles empty string raw_text.

        Verifies edge case handling:
        1. Empty string is accepted (not rejected)
        2. Empty string is stored as-is (not converted to NULL)
        3. Utterance with empty text is retrievable
        """
        # Create a session
        session_id = await test_db_store.create_session()

        # Create utterance with empty string
        utterance_id = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text=""
        )

        # Verify empty string is stored correctly (not as NULL)
        utterance = await test_db_store.get_utterance(utterance_id)

        assert utterance is not None, "Utterance with empty text should be retrievable"
        assert utterance["raw_text"] == "", (
            f"Empty string should be stored as empty string, not NULL. "
            f"Got: {utterance['raw_text']!r}"
        )

    @pytest.mark.asyncio
    async def test_create_utterance_with_special_characters(
        self,
        test_db_store: SessionStore
    ) -> None:
        """Test that create_utterance handles special characters correctly.

        Verifies that special characters are stored exactly as provided:
        1. Unicode characters (emojis, accented characters)
        2. Quotes and escape sequences
        3. Newlines and tabs
        """
        # Create a session
        session_id = await test_db_store.create_session()

        # Create utterance with special characters
        test_text = "Test with émojis 🎉, unicode ™, quotes \"', and newlines\nand\ttabs"
        utterance_id = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text=test_text
        )

        # Verify special characters are preserved
        utterance = await test_db_store.get_utterance(utterance_id)

        assert utterance is not None, "Utterance with special chars should be retrievable"
        assert utterance["raw_text"] == test_text, (
            f"Special characters should be preserved. "
            f"Expected: {test_text!r}, Got: {utterance['raw_text']!r}"
        )


class TestUtteranceResultLinkage:
    """Tests for utterance linkage to results via intents."""

    @pytest.mark.asyncio
    async def test_utterance_links_to_results_correctly(
        self,
        test_db_store: SessionStore
    ) -> None:
        """Test that utterance links to results correctly via intent chain.

        Verifies the complete linkage chain:
        1. Utterance is created
        2. Intent is created and linked to utterance
        3. Result is created and linked to intent
        4. Result can be retrieved and traced back to utterance
        """
        # Create a session and utterance
        session_id = await test_db_store.create_session()
        utterance_id = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text="What's the status of pbx-web?"
        )

        # Create an intent linked to the utterance
        intent_id = await test_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="pbx-web",
            intent_type="status"
        )

        # Create a topic for the result
        topic_id = await test_db_store.create_topic(
            label="pbx-web status",
            topic_type="project",
            project_slugs=["pbx-web"],
            scope="session",
            session_id=session_id
        )

        # Create a result linked to the intent
        result_id = await test_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="pbx-web deployment is healthy",
            data={"status": "healthy", "replicas": 3}
        )

        # Verify the linkage chain is complete

        # 1. Verify result exists and is linked to intent
        result = await test_db_store.get_result(result_id)
        assert result is not None, "Result should be retrievable"
        assert result["intent_id"] == intent_id, "Result should be linked to intent"
        assert result["topic_id"] == topic_id, "Result should be linked to topic"

        # 2. Verify intent exists and is linked to utterance
        intent = await test_db_store.get_intent(intent_id)
        assert intent is not None, "Intent should be retrievable"
        assert intent["utterance_id"] == utterance_id, "Intent should be linked to utterance"

        # 3. Verify utterance exists
        utterance = await test_db_store.get_utterance(utterance_id)
        assert utterance is not None, "Utterance should be retrievable"

        # The complete chain: utterance -> intent -> result is verified
        assert (
            utterance["id"] == intent["utterance_id"] and
            intent["id"] == result["intent_id"]
        ), "Complete linkage chain should be intact"

    @pytest.mark.asyncio
    async def test_utterance_result_relationships_are_retrievable(
        self,
        test_db_store: SessionStore
    ) -> None:
        """Test that utterance-result relationships are retrievable.

        Verifies that given an utterance_id, you can retrieve all related results:
        1. Create utterance -> intent -> result chain
        2. Use get_results_for_intent() to retrieve results
        3. Verify results can be traced back to original utterance
        """
        # Create a session and utterance
        session_id = await test_db_store.create_session()
        utterance_id = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text="Check the whisper-stt deployment status"
        )

        # Create an intent linked to the utterance
        intent_id = await test_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="whisper-stt",
            intent_type="status"
        )

        # Create a topic
        topic_id = await test_db_store.create_topic(
            label="whisper-stt status",
            topic_type="project",
            project_slugs=["whisper-stt"],
            scope="session",
            session_id=session_id
        )

        # Create multiple results for the same intent
        result_id_1 = await test_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="whisper-stt is running",
            data={"status": "running", "pods": 2}
        )

        result_id_2 = await test_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="whisper-stt metrics are normal",
            data={"cpu_usage": "45%", "memory_usage": "60%"}
        )

        # Retrieve results for the intent
        results = await test_db_store.get_results_for_intent(intent_id)

        # Verify all results are retrievable
        assert len(results) == 2, f"Should retrieve 2 results, got {len(results)}"

        result_ids = {r["id"] for r in results}
        assert result_id_1 in result_ids, "First result should be retrievable"
        assert result_id_2 in result_ids, "Second result should be retrievable"

        # Verify all results can be traced back to the utterance
        for result in results:
            assert result["intent_id"] == intent_id, "All results should link to the same intent"

        # Verify the intent can be traced back to the utterance
        intent = await test_db_store.get_intent(intent_id)
        assert intent["utterance_id"] == utterance_id, "Intent should trace back to utterance"

    @pytest.mark.asyncio
    async def test_multiple_utterances_link_to_different_results(
        self,
        test_db_store: SessionStore
    ) -> None:
        """Test that multiple utterances can link to different results.

        Verifies that separate utterance chains don't interfere:
        1. Create two separate utterance -> intent -> result chains
        2. Verify each result links only to its own intent/utterance
        3. Verify no cross-contamination between chains
        """
        # Create a session
        session_id = await test_db_store.create_session()

        # Create first utterance chain
        utterance_id_1 = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text="Status of pbx-web?"
        )
        intent_id_1 = await test_db_store.create_intent(
            utterance_id=utterance_id_1,
            session_id=session_id,
            project_slug="pbx-web",
            intent_type="status"
        )
        topic_id_1 = await test_db_store.create_topic(
            label="pbx-web",
            topic_type="project",
            project_slugs=["pbx-web"],
            scope="session",
            session_id=session_id
        )
        result_id_1 = await test_db_store.create_result(
            intent_id=intent_id_1,
            topic_id=topic_id_1,
            session_id=session_id,
            summary="pbx-web healthy",
            data={"status": "ok"}
        )

        # Create second utterance chain
        utterance_id_2 = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text="Status of whisper-stt?"
        )
        intent_id_2 = await test_db_store.create_intent(
            utterance_id=utterance_id_2,
            session_id=session_id,
            project_slug="whisper-stt",
            intent_type="status"
        )
        topic_id_2 = await test_db_store.create_topic(
            label="whisper-stt",
            topic_type="project",
            project_slugs=["whisper-stt"],
            scope="session",
            session_id=session_id
        )
        result_id_2 = await test_db_store.create_result(
            intent_id=intent_id_2,
            topic_id=topic_id_2,
            session_id=session_id,
            summary="whisper-stt healthy",
            data={"status": "ok"}
        )

        # Verify no cross-contamination: result_1 should only link to intent_1
        result_1 = await test_db_store.get_result(result_id_1)
        assert result_1["intent_id"] == intent_id_1, "Result 1 should link to intent 1 only"
        assert result_1["intent_id"] != intent_id_2, "Result 1 should not link to intent 2"

        # Verify no cross-contamination: result_2 should only link to intent_2
        result_2 = await test_db_store.get_result(result_id_2)
        assert result_2["intent_id"] == intent_id_2, "Result 2 should link to intent 2 only"
        assert result_2["intent_id"] != intent_id_1, "Result 2 should not link to intent 1"

        # Verify each intent links to its own utterance
        intent_1 = await test_db_store.get_intent(intent_id_1)
        intent_2 = await test_db_store.get_intent(intent_id_2)
        assert intent_1["utterance_id"] == utterance_id_1, "Intent 1 should link to utterance 1"
        assert intent_2["utterance_id"] == utterance_id_2, "Intent 2 should link to utterance 2"
        assert intent_1["utterance_id"] != utterance_id_2, "Intent 1 should not link to utterance 2"
        assert intent_2["utterance_id"] != utterance_id_1, "Intent 2 should not link to utterance 1"

    @pytest.mark.asyncio
    async def test_utterance_with_no_linked_results(
        self,
        test_db_store: SessionStore
    ) -> None:
        """Test that utterances with no linked results are handled correctly.

        Verifies edge case where utterance exists but has no intent/result:
        1. Utterance can exist without intents
        2. get_results_for_intent() returns empty list for non-existent intent
        3. No errors occur when querying non-existent relationships
        """
        # Create an utterance with no intents
        session_id = await test_db_store.create_session()
        utterance_id = await test_db_store.create_utterance(
            session_id=session_id,
            raw_text="This utterance has no intents or results"
        )

        # Verify utterance exists
        utterance = await test_db_store.get_utterance(utterance_id)
        assert utterance is not None, "Utterance should exist"

        # Try to get results for a non-existent intent (should return empty list)
        # Note: We're using a random UUID that doesn't correspond to any intent
        fake_intent_id = str(uuid4())
        results = await test_db_store.get_results_for_intent(fake_intent_id)
        assert results == [], "get_results_for_intent() should return empty list for non-existent intent"

        # Verify the utterance itself is still intact
        utterance_check = await test_db_store.get_utterance(utterance_id)
        assert utterance_check is not None, "Utterance should still exist after querying non-existent intent"
        assert utterance_check["raw_text"] == "This utterance has no intents or results"
