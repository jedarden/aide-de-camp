"""
Result metadata and timestamp comprehensive tests (bead adc-v3wqmz).

This test module provides comprehensive coverage for result metadata persistence
and timestamp recording beyond basic storage tests. It verifies:

1. Metadata field persistence and validation
2. Timestamp recording for creation, updates, and acknowledgments
3. Metadata field type and format validation
4. Edge cases for metadata and timestamp operations
5. Update scenarios and timestamp modifications

Tests use fixtures from infrastructure bead (adc-2v8ae7):
- in_memory_db_store: Isolated in-memory database for fast tests
- test_topic_with_session: Pre-built session and topic
- test_result_builder: Helper for creating test results
"""

import json
import pytest
from datetime import datetime, timezone
from uuid import uuid4


class TestResultMetadataPersistence:
    """Test comprehensive metadata persistence for all result fields."""

    @pytest.mark.asyncio
    async def test_result_type_metadata_persistence(self, in_memory_db_store, test_topic_with_session):
        """Test that various result_type values are persisted correctly."""
        session_id, topic_id = test_topic_with_session

        # Test different result_type patterns
        result_types = [
            "status:pbx-web",
            "action:api-check",
            "monitoring:whisper-stt",
            "research:deployment-analysis",
            "compound:multi-source",
            None  # Test optional field
        ]

        for result_type in result_types:
            result_id = await in_memory_db_store.create_result(
                intent_id=None,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Result type: {result_type}",
                data={"result_type": result_type},
                result_type=result_type
            )

            result = await in_memory_db_store.get_result(result_id)
            assert result is not None
            assert result["result_type"] == result_type

    @pytest.mark.asyncio
    async def test_urgency_metadata_validation(self, in_memory_db_store, test_topic_with_session):
        """Test that urgency metadata field is validated and persisted correctly."""
        session_id, topic_id = test_topic_with_session

        # Test all valid urgency levels
        valid_urgencies = ["critical", "high", "normal", "low"]

        for urgency in valid_urgencies:
            result_id = await in_memory_db_store.create_result(
                intent_id=None,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Urgency: {urgency}",
                data={"urgency_test": urgency},
                urgency=urgency
            )

            result = await in_memory_db_store.get_result(result_id)
            assert result is not None
            assert result["urgency"] == urgency

    @pytest.mark.asyncio
    async def test_intent_id_metadata_for_different_sources(self, in_memory_db_store, test_topic_with_session):
        """Test intent_id metadata for different result sources."""
        session_id, topic_id = test_topic_with_session

        # Create utterance and intent for user-initiated result
        utterance_id = await in_memory_db_store.create_utterance(
            session_id=session_id,
            raw_text="Check the API status"
        )

        intent_id = await in_memory_db_store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug="api",
            intent_type="status",
            topic_id=topic_id
        )

        # User-initiated result with intent_id
        user_result_id = await in_memory_db_store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary="API status from user request",
            data={"source": "user_intent"}
        )

        user_result = await in_memory_db_store.get_result(user_result_id)
        assert user_result["intent_id"] == intent_id

        # Monitoring-originated result without intent_id
        monitoring_result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="API status from monitoring",
            data={"source": "monitoring"},
            result_type="monitoring:api-status"
        )

        monitoring_result = await in_memory_db_store.get_result(monitoring_result_id)
        assert monitoring_result["intent_id"] is None
        assert monitoring_result["result_type"] == "monitoring:api-status"

    @pytest.mark.asyncio
    async def test_card_fallback_metadata_persistence(self, in_memory_db_store, test_topic_with_session):
        """Test that card_fallback boolean is converted and persisted correctly."""
        session_id, topic_id = test_topic_with_session

        # Test True case
        result_fallback_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Fallback card result",
            data={"requires_fallback": True},
            card_fallback=True
        )

        result_fallback = await in_memory_db_store.get_result(result_fallback_id)
        assert result_fallback["card_fallback"] == 1

        # Test False case (explicit)
        result_no_fallback_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Normal card result",
            data={"requires_fallback": False},
            card_fallback=False
        )

        result_no_fallback = await in_memory_db_store.get_result(result_no_fallback_id)
        assert result_no_fallback["card_fallback"] == 0

    @pytest.mark.asyncio
    async def test_previous_result_id_metadata_persistence(self, in_memory_db_store, test_topic_with_session):
        """Test that previous_result_id is persisted for result chains."""
        session_id, topic_id = test_topic_with_session

        # Create initial result
        first_result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="First result",
            data={"version": 1}
        )

        # Create second result linking to first
        second_result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Second result (update)",
            data={"version": 2},
            previous_result_id=first_result_id
        )

        second_result = await in_memory_db_store.get_result(second_result_id)
        assert second_result["previous_result_id"] == first_result_id

        # Verify chain can be followed
        first_result = await in_memory_db_store.get_result(first_result_id)
        assert first_result is not None

    @pytest.mark.asyncio
    async def test_diff_metadata_persistence(self, in_memory_db_store, test_topic_with_session):
        """Test that diff metadata fields are persisted correctly."""
        session_id, topic_id = test_topic_with_session
        previous_result_id = str(uuid4())

        diff_summary = "Deployment status changed from degraded to healthy"
        diff_data = {
            "status": {"from": "degraded", "to": "healthy"},
            "replicas": {"from": 1, "to": 2},
            "updated_at": {"from": "2024-01-01T10:00:00Z", "to": "2024-01-01T10:05:00Z"}
        }

        result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Deployment recovered",
            data={"status": "healthy"},
            previous_result_id=previous_result_id,
            diff_summary=diff_summary,
            diff_data=diff_data
        )

        result = await in_memory_db_store.get_result(result_id)
        assert result is not None
        assert result["previous_result_id"] == previous_result_id
        assert result["diff_summary"] == diff_summary

        # Verify diff_data JSON serialization
        stored_diff_data = json.loads(result["diff_data"])
        assert stored_diff_data == diff_data
        assert stored_diff_data["status"]["from"] == "degraded"
        assert stored_diff_data["replicas"]["to"] == 2


class TestTimestampRecording:
    """Test timestamp recording for result creation and updates."""

    @pytest.mark.asyncio
    async def test_creation_timestamps_accuracy(self, in_memory_db_store, test_topic_with_session):
        """Test that creation timestamps are accurate and within expected ranges."""
        session_id, topic_id = test_topic_with_session

        # Capture precise timestamps before and after
        before_timestamp = int(datetime.now(timezone.utc).timestamp())

        result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Timestamp accuracy test",
            data={"test": "timestamp"}
        )

        after_timestamp = int(datetime.now(timezone.utc).timestamp())

        result = await in_memory_db_store.get_result(result_id)
        assert result is not None

        # Verify created_at is within the capture window
        assert before_timestamp <= result["created_at"] <= after_timestamp

        # Verify surfaced_at matches created_at for new results
        assert result["surfaced_at"] == result["created_at"]

        # Verify acked_at is None for new results
        assert result["acked_at"] is None

    @pytest.mark.asyncio
    async def test_timestamp_ordering_for_multiple_results(self, in_memory_db_store, test_topic_with_session):
        """Test that timestamps maintain correct ordering across multiple results."""
        import time
        session_id, topic_id = test_topic_with_session

        # Create results with deliberate time gaps
        result_ids = []
        creation_times = []

        for i in range(3):
            before_time = int(datetime.now(timezone.utc).timestamp())

            result_id = await in_memory_db_store.create_result(
                intent_id=None,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Result {i+1}",
                data={"index": i+1}
            )

            after_time = int(datetime.now(timezone.utc).timestamp())
            creation_times.append((before_time, after_time))
            result_ids.append(result_id)

            # Ensure distinct timestamps (1 second delay)
            if i < 2:  # No delay after last result
                time.sleep(1)

        # Verify timestamp ordering
        for i, result_id in enumerate(result_ids):
            result = await in_memory_db_store.get_result(result_id)
            before, after = creation_times[i]

            assert result["created_at"] >= before
            assert result["created_at"] <= after

            # Verify ordering between results
            if i > 0:
                prev_result = await in_memory_db_store.get_result(result_ids[i-1])
                assert result["created_at"] > prev_result["created_at"]

    @pytest.mark.asyncio
    async def test_result_with_existing_previous_result_metadata(self, in_memory_db_store, test_topic_with_session):
        """Test timestamp behavior when linking to previous results."""
        import time
        session_id, topic_id = test_topic_with_session

        # Create first result
        first_result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Original result",
            data={"version": 1}
        )

        time.sleep(1)  # Ensure timestamp difference

        # Create follow-up result
        followup_result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Follow-up result",
            data={"version": 2},
            previous_result_id=first_result_id
        )

        first_result = await in_memory_db_store.get_result(first_result_id)
        followup_result = await in_memory_db_store.get_result(followup_result_id)

        # Verify follow-up has later timestamp
        assert followup_result["created_at"] > first_result["created_at"]

        # Verify previous_result_id is preserved
        assert followup_result["previous_result_id"] == first_result_id


class TestMetadataValidation:
    """Test metadata field validation and constraints."""

    @pytest.mark.asyncio
    async def test_all_metadata_fields_optional(self, in_memory_db_store, test_topic_with_session):
        """Test that all metadata fields are optional and default correctly."""
        session_id, topic_id = test_topic_with_session

        # Create result with minimal required fields
        result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Minimal metadata test",
            data={"minimal": True}
        )

        result = await in_memory_db_store.get_result(result_id)
        assert result is not None

        # Verify optional metadata fields are None or defaults
        assert result["intent_id"] is None
        assert result["result_type"] is None
        assert result["previous_result_id"] is None
        assert result["diff_summary"] is None
        assert result["diff_data"] is None
        assert result["acked_at"] is None

        # Verify defaults for non-None optional fields
        assert result["urgency"] == "normal"  # Default urgency
        assert result["card_fallback"] == 0  # Default boolean

    @pytest.mark.asyncio
    async def test_metadata_combinations(self, in_memory_db_store, test_topic_with_session):
        """Test various combinations of metadata fields."""
        session_id, topic_id = test_topic_with_session
        previous_id = str(uuid4())

        # Test with all metadata fields populated
        result_id = await in_memory_db_store.create_result(
            intent_id=str(uuid4()),
            topic_id=topic_id,
            session_id=session_id,
            summary="Full metadata test",
            data={"full": "metadata"},
            urgency="critical",
            result_type="status:test-service",
            card_fallback=True,
            previous_result_id=previous_id,
            diff_summary="Status changed",
            diff_data={"status": {"from": "down", "to": "up"}}
        )

        result = await in_memory_db_store.get_result(result_id)
        assert result is not None

        # Verify all fields are set
        assert result["urgency"] == "critical"
        assert result["result_type"] == "status:test-service"
        assert result["card_fallback"] == 1
        assert result["previous_result_id"] == previous_id
        assert result["diff_summary"] == "Status changed"
        assert result["diff_data"] is not None

    @pytest.mark.asyncio
    async def test_result_type_with_special_characters(self, in_memory_db_store, test_topic_with_session):
        """Test result_type with special characters and valid patterns."""
        session_id, topic_id = test_topic_with_session

        special_result_types = [
            "status:service-with-dash",
            "action:api_check",
            "monitoring:cpu.memory",
            "research:deep.dive.analysis",
            "compound:multi-source-sync"
        ]

        for result_type in special_result_types:
            result_id = await in_memory_db_store.create_result(
                intent_id=None,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Special result type: {result_type}",
                data={"type": result_type},
                result_type=result_type
            )

            result = await in_memory_db_store.get_result(result_id)
            assert result["result_type"] == result_type


class TestMetadataUpdateScenarios:
    """Test metadata behavior in update scenarios."""

    @pytest.mark.asyncio
    async def test_result_chain_metadata_tracking(self, in_memory_db_store, test_topic_with_session):
        """Test metadata tracking through a chain of related results."""
        import time
        session_id, topic_id = test_topic_with_session

        # Create chain of results
        result_ids = []

        # First result (no previous)
        result_ids.append(await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Chain: initial",
            data={"step": 1}
        ))

        time.sleep(1)

        # Second result (links to first)
        result_ids.append(await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Chain: second",
            data={"step": 2},
            previous_result_id=result_ids[0],
            diff_summary="Progress update"
        ))

        time.sleep(1)

        # Third result (links to second)
        result_ids.append(await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Chain: third",
            data={"step": 3},
            previous_result_id=result_ids[1],
            diff_summary="Final update"
        ))

        # Verify chain integrity
        for i, result_id in enumerate(result_ids):
            result = await in_memory_db_store.get_result(result_id)
            assert result is not None

            if i > 0:
                # Verify previous_result_id points to correct predecessor
                prev_result = await in_memory_db_store.get_result(result_ids[i-1])
                assert result["previous_result_id"] == result_ids[i-1]

                # Verify timestamp ordering
                assert result["created_at"] > prev_result["created_at"]

    @pytest.mark.asyncio
    async def test_different_urgency_levels_in_result_chain(self, in_memory_db_store, test_topic_with_session):
        """Test that urgency levels can change in a result chain."""
        import time
        session_id, topic_id = test_topic_with_session

        # Create results with different urgency levels
        urgency_progression = ["low", "normal", "high", "critical"]
        result_ids = []

        for i, urgency in enumerate(urgency_progression):
            if i > 0:
                time.sleep(1)

            result_id = await in_memory_db_store.create_result(
                intent_id=None,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Urgency: {urgency}",
                data={"urgency_level": urgency},
                urgency=urgency,
                previous_result_id=result_ids[i-1] if i > 0 else None
            )
            result_ids.append(result_id)

            result = await in_memory_db_store.get_result(result_id)
            assert result["urgency"] == urgency


class TestTimestampEdgeCases:
    """Test timestamp handling in edge cases."""

    @pytest.mark.asyncio
    async def test_rapid_successive_results_timestamps(self, in_memory_db_store, test_topic_with_session):
        """Test timestamp handling for rapidly created results."""
        session_id, topic_id = test_topic_with_session

        # Create multiple results rapidly without delay
        result_ids = []
        for i in range(5):
            result_id = await in_memory_db_store.create_result(
                intent_id=None,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Rapid result {i+1}",
                data={"rapid": True}
            )
            result_ids.append(result_id)

        # Verify all have valid timestamps
        for result_id in result_ids:
            result = await in_memory_db_store.get_result(result_id)
            assert result["created_at"] is not None
            assert result["surfaced_at"] is not None
            assert result["created_at"] == result["surfaced_at"]

    @pytest.mark.asyncio
    async def test_timestamp_consistency_across_retrieval(self, in_memory_db_store, test_topic_with_session):
        """Test that timestamps remain consistent across multiple retrievals."""
        session_id, topic_id = test_topic_with_session

        result_id = await in_memory_db_store.create_result(
            intent_id=None,
            topic_id=topic_id,
            session_id=session_id,
            summary="Timestamp consistency test",
            data={"test": "consistency"}
        )

        # Retrieve same result multiple times
        timestamps = []
        for _ in range(3):
            result = await in_memory_db_store.get_result(result_id)
            timestamps.append({
                "created_at": result["created_at"],
                "surfaced_at": result["surfaced_at"],
                "acked_at": result["acked_at"]
            })

        # Verify all timestamps are identical across retrievals
        for i in range(1, len(timestamps)):
            assert timestamps[i] == timestamps[0]