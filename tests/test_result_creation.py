"""
Result creation and storage tests (bead adc-3rx0sq).

This test module verifies that create_result() correctly stores synthesis output
and persists all result fields including timestamps, metadata, and optional fields.

Tests use fixtures from the infrastructure bead (adc-d6x7bs):
- in_memory_db_store: Isolated in-memory database for fast tests
- test_topic_with_session: Pre-built session and topic
- test_result_builder: Helper for creating test results

Coverage includes:
- Synthesis output storage (data field)
- Fetch metadata persistence (result_type, intent_id)
- Timestamp recording (created_at, surfaced_at)
- All result fields are retrievable
- Optional fields (previous_result_id, diff fields, card_fallback)
- Urgency levels and validation
"""

import json
import pytest
from datetime import datetime
from uuid import uuid4


class TestResultCreation:
    """Test create_result() function storage and retrieval."""

    @pytest.mark.asyncio
    async def test_create_result_stores_synthesis_output(self, in_memory_db_store, test_topic_with_session):
        """Test that create_result() stores synthesis output in data field correctly."""
        session_id, topic_id = test_topic_with_session

        # Arrange: Create synthesis output with typical structure
        synthesis_data = {
            "summary": "Deployment status verified",
            "pods": [
                {"name": "web-0", "phase": "Running", "ready": True},
                {"name": "web-1", "phase": "Running", "ready": True},
            ],
            "deployment": {
                "name": "web",
                "replicas": 2,
                "available": 2,
                "updated": 2
            },
            "metrics": {
                "cpu_usage": "450m",
                "memory_usage": "128Mi"
            }
        }

        # Act: Create result with synthesis output
        result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="2 pods running",
            data=synthesis_data,
            urgency="normal"
        )

        # Assert: Data is persisted and retrievable as valid JSON
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None
        assert result["id"] == result_id

        # Verify data field contains valid JSON matching synthesis output
        stored_data = json.loads(result["data"])
        assert stored_data == synthesis_data
        assert stored_data["pods"][0]["name"] == "web-0"
        assert stored_data["deployment"]["replicas"] == 2

    @pytest.mark.asyncio
    async def test_fetch_metadata_persistence(self, in_memory_db_store, test_topic_with_session):
        """Test that fetch metadata is persisted correctly."""
        session_id, topic_id = test_topic_with_session
        intent_id = str(uuid4())

        # Arrange: Create result with fetch metadata
        result_type = "status:pbx-web"

        # Act: Create result with metadata
        result_id = await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Service status check",
            data={"status": "healthy"},
            result_type=result_type,
            urgency="low"
        )

        # Assert: Fetch metadata is persisted
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None
        assert result["intent_id"] == intent_id
        assert result["result_type"] == result_type

    @pytest.mark.asyncio
    async def test_timestamps_are_recorded(self, in_memory_db_store, test_topic_with_session):
        """Test that created_at and surfaced_at timestamps are recorded."""
        session_id, topic_id = test_topic_with_session

        # Record time before and after creation to verify timestamp
        before_time = int(datetime.now().timestamp())

        # Act: Create result
        result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Timestamp test",
            data={"test": "data"}
        )

        after_time = int(datetime.now().timestamp())

        # Assert: Timestamps are set correctly
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None
        assert result["created_at"] is not None
        assert result["surfaced_at"] is not None

        # Verify timestamps are within reasonable time range
        assert before_time <= result["created_at"] <= after_time
        assert before_time <= result["surfaced_at"] <= after_time

        # Verify surfaced_at equals created_at initially
        assert result["created_at"] == result["surfaced_at"]

    @pytest.mark.asyncio
    async def test_all_result_fields_are_retrievable(self, in_memory_db_store, test_topic_with_session):
        """Test that all result fields are stored and retrievable."""
        session_id, topic_id = test_topic_with_session
        intent_id = str(uuid4())
        previous_result_id = str(uuid4())

        # Arrange: Create result with all fields populated
        result_data = {
            "service": "api",
            "endpoint": "/health",
            "status": "ok",
            "response_time_ms": 45
        }

        # Act: Create result with all parameters
        result_id = await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="API health check passed",
            data=result_data,
            urgency="high",
            result_type="action:api-check",
            card_fallback=True,
            previous_result_id=previous_result_id,
            diff_summary="Status changed from degraded to ok",
            diff_data={"status": {"from": "degraded", "to": "ok"}}
        )

        # Assert: All fields are retrievable
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None

        # Core fields
        assert result["id"] == result_id
        assert result["intent_id"] == intent_id
        assert result["topic_id"] == topic_id
        assert result["session_id"] == session_id
        assert result["summary"] == "API health check passed"

        # Data field
        stored_data = json.loads(result["data"])
        assert stored_data == result_data

        # Metadata fields
        assert result["urgency"] == "high"
        assert result["result_type"] == "action:api-check"

        # Boolean field converted to integer
        assert result["card_fallback"] == 1

        # Timestamp fields
        assert result["created_at"] is not None
        assert result["surfaced_at"] is not None

        # Optional diff fields
        assert result["previous_result_id"] == previous_result_id
        assert result["diff_summary"] == "Status changed from degraded to ok"

        stored_diff_data = json.loads(result["diff_data"])
        assert stored_diff_data == {"status": {"from": "degraded", "to": "ok"}}

        # acked_at should be None for new results
        assert result["acked_at"] is None

    @pytest.mark.asyncio
    async def test_optional_fields_are_none_by_default(self, in_memory_db_store, test_topic_with_session):
        """Test that optional fields default to None correctly."""
        session_id, topic_id = test_topic_with_session

        # Act: Create result with only required fields
        result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Minimal result",
            data={"minimal": True}
        )

        # Assert: Optional fields are None or appropriate defaults
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None

        # These should be None
        assert result["intent_id"] is None
        assert result["result_type"] is None
        assert result["previous_result_id"] is None
        assert result["diff_summary"] is None
        assert result["diff_data"] is None
        assert result["acked_at"] is None

        # Urgency should default to "normal"
        assert result["urgency"] == "normal"

        # card_fallback should default to 0 (False)
        assert result["card_fallback"] == 0

    @pytest.mark.asyncio
    async def test_urgency_levels(self, in_memory_db_store, test_topic_with_session):
        """Test that all urgency levels are stored correctly."""
        session_id, topic_id = test_topic_with_session
        urgency_levels = ["critical", "high", "normal", "low"]

        for urgency in urgency_levels:
            result_id = await in_memory_db_store.create_result(
                intent_id=None,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Result with {urgency} urgency",
                data={"urgency": urgency},
                urgency=urgency
            )

            result = await in_memory_db_store.get_result(result_id)
            assert result is not None
            assert result["urgency"] == urgency

    @pytest.mark.asyncio
    async def test_card_fallback_flag_persistence(self, in_memory_db_store, test_topic_with_session):
        """Test that card_fallback flag is converted and persisted correctly."""
        session_id, topic_id = test_topic_with_session

        # Test card_fallback=True
        result_id_true = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Result with fallback",
            data={"fallback": True},
            card_fallback=True
        )

        result_true = await in_memory_db_store.get_result(result_id_true)
        assert result_true is not None
        assert result_true["card_fallback"] == 1

        # Test card_fallback=False (default)
        result_id_false = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Result without fallback",
            data={"fallback": False},
            card_fallback=False
        )

        result_false = await in_memory_db_store.get_result(result_id_false)
        assert result_false is not None
        assert result_false["card_fallback"] == 0

    @pytest.mark.asyncio
    async def test_diff_fields_optional_handling(self, in_memory_db_store, test_topic_with_session):
        """Test that diff fields are only stored when provided."""
        session_id, topic_id = test_topic_with_session

        # Create result WITH diff fields
        result_id_with_diff = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Result with diff",
            data={"value": 42},
            previous_result_id=str(uuid4()),
            diff_summary="Value increased",
            diff_data={"value": {"from": 40, "to": 42}}
        )

        result_with_diff = await in_memory_db_store.get_result(result_id_with_diff)
        assert result_with_diff is not None
        assert result_with_diff["previous_result_id"] is not None
        assert result_with_diff["diff_summary"] == "Value increased"
        assert result_with_diff["diff_data"] is not None

        # Create result WITHOUT diff fields
        result_id_without_diff = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Result without diff",
            data={"value": 42}
        )

        result_without_diff = await in_memory_db_store.get_result(result_id_without_diff)
        assert result_without_diff is not None
        assert result_without_diff["previous_result_id"] is None
        assert result_without_diff["diff_summary"] is None
        assert result_without_diff["diff_data"] is None

    @pytest.mark.asyncio
    async def test_intent_id_none_for_monitoring_results(self, in_memory_db_store, test_topic_with_session):
        """Test that intent_id can be None for monitoring-originated results."""
        session_id, topic_id = test_topic_with_session

        # Act: Create monitoring-originated result (intent_id=None)
        result_id = await in_memory_db_store.create_result(
            intent_id=None,  # Monitoring results have no intent
            topic_id=topic_id,
            session_id=session_id,
            summary="Monitoring alert",
            data={"alert_type": "high_memory"},
            result_type="monitoring:whisper-stt"
        )

        # Assert: Result is stored correctly with NULL intent_id
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None
        assert result["intent_id"] is None
        assert result["result_type"] == "monitoring:whisper-stt"

    @pytest.mark.asyncio
    async def test_result_retrieval_by_id(self, in_memory_db_store, test_topic_with_session):
        """Test that results can be retrieved by their ID."""
        session_id, topic_id = test_topic_with_session

        # Create a result
        result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Retrievable result",
            data={"retrievable": True}
        )

        # Retrieve and verify
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None
        assert result["id"] == result_id
        assert result["summary"] == "Retrievable result"

        # Verify non-existent result returns None
        non_existent = await in_memory_db_store.get_result(str(uuid4()))
        assert non_existent is None

    @pytest.mark.asyncio
    async def test_multiple_results_for_same_topic(self, in_memory_db_store, test_topic_with_session):
        """Test that multiple results can be created for the same topic."""
        session_id, topic_id = test_topic_with_session

        # Create multiple results
        result_ids = []
        for i in range(3):
            result_id = await in_memory_db_store.create_result(
                intent_id=None,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Result {i+1}",
                data={"index": i+1}
            )
            result_ids.append(result_id)

        # Verify all results are retrievable
        for i, result_id in enumerate(result_ids):
            result = await in_memory_db_store.get_result(result_id)
            assert result is not None
            assert result["summary"] == f"Result {i+1}"

            stored_data = json.loads(result["data"])
            assert stored_data["index"] == i+1

    @pytest.mark.asyncio
    async def test_complex_data_structure_serialization(self, in_memory_db_store, test_topic_with_session):
        """Test that complex nested data structures are serialized correctly."""
        session_id, topic_id = test_topic_with_session

        # Arrange: Create complex nested data
        complex_data = {
            "level1": {
                "level2": {
                    "level3": {
                        "array": [1, 2, 3],
                        "nested_object": {"key": "value"},
                        "boolean": True,
                        "null_value": None,
                        "number": 42.5,
                        "string": "test"
                    }
                }
            },
            "top_level_array": [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "second"}
            ]
        }

        # Act: Create result with complex data
        result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Complex data test",
            data=complex_data
        )

        # Assert: Complex data is serialized and deserialized correctly
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None

        stored_data = json.loads(result["data"])
        assert stored_data == complex_data
        assert stored_data["level1"]["level2"]["level3"]["array"] == [1, 2, 3]
        assert stored_data["level1"]["level2"]["level3"]["nested_object"]["key"] == "value"
        assert stored_data["level1"]["level2"]["level3"]["boolean"] is True
        assert stored_data["level1"]["level2"]["level3"]["null_value"] is None
        assert stored_data["level1"]["level2"]["level3"]["number"] == 42.5
        assert len(stored_data["top_level_array"]) == 2


class TestResultCreationIntegration:
    """Integration tests for result creation with related entities."""

    @pytest.mark.asyncio
    async def test_result_creation_with_intent_link(self, in_memory_db_store, test_topic_with_session):
        """Test result creation with proper intent linking."""
        session_id, topic_id = test_topic_with_session

        # Create an utterance
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Check deployment status"
        )

        # Create an intent
        intent_id = await in_memory_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="pbx-web",
            intent_type="status",
            topic_id=topic_id
        )

        # Create result linked to intent
        result_id = await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="Deployment healthy",
            data={"status": "healthy"}
        )

        # Verify the link
        result = await in_memory_db_store.get_result(result_id)
        assert result is not None
        assert result["intent_id"] == intent_id
        assert result["topic_id"] == topic_id
        assert result["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_results_retrievable_by_topic(self, in_memory_db_store, test_topic_with_session):
        """Test that results can be retrieved for a specific topic."""
        import asyncio
        import time
        session_id, topic_id = test_topic_with_session

        # Create first result
        await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="First result",
            data={"index": 1}
        )

        # Add delay to ensure distinct timestamps (timestamps are integer seconds)
        time.sleep(1)

        # Create second result with guaranteed later timestamp
        await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Second result",
            data={"index": 2}
        )

        # Retrieve latest result for topic
        latest_result = await in_memory_db_store.get_latest_result_for_topic(topic_id)
        assert latest_result is not None
        assert latest_result["summary"] == "Second result"

        stored_data = json.loads(latest_result["data"])
        assert stored_data["index"] == 2
