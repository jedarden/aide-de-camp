"""
Tests for confirmed deletions storage functionality (adc-zkdjq).

Acceptance Criteria:
1. Confirmation is documented with timestamp
2. User response (yes/no) is recorded
3. Confirmed pod name is stored for deletion
4. Document is persistent and accessible by deletion step
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from src.confirmations.confirmed_deletions import (
    document_confirmed_deletion,
    get_latest_confirmed_deletion,
    get_confirmed_deletion_by_confirmation_id,
    list_all_confirmed_deletions,
    get_deletion_count,
)


@pytest.fixture
def temp_log_file(monkeypatch):
    """Create a temporary log file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as f:
        temp_path = Path(f.name)
    monkeypatch.setattr('src.confirmations.confirmed_deletions.CONFIRMED_DELETIONS_LOG', temp_path)
    monkeypatch.setattr('src.confirmations.confirmed_deletions.CONFIRMED_DELETIONS_DIR', temp_path.parent)
    yield temp_path
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


class TestConfirmedDeletionsStorage:
    """Test suite for confirmed deletions storage (adc-zkdjq acceptance criteria)."""

    def test_confirmation_documented_with_timestamp(self, temp_log_file):
        """
        AC1: Confirmation is documented with timestamp
        """
        # Arrange
        pod_name = "test-pod-123"
        confirmation_id = "test-conf-001"

        # Act
        record = document_confirmed_deletion(
            pod_name=pod_name,
            namespace="test-ns",
            cluster="test-cluster",
            user_response="yes",
            confirmation_id=confirmation_id
        )

        # Assert
        assert "timestamp" in record
        assert record["timestamp"] is not None
        # Verify it's an ISO 8601 format timestamp
        datetime.fromisoformat(record["timestamp"].replace('+00:00', '+00:00'))

    def test_user_response_recorded(self, temp_log_file):
        """
        AC2: User response (yes/no) is recorded
        """
        # Arrange & Act - Test with 'yes'
        record_yes = document_confirmed_deletion(
            pod_name="test-pod-yes",
            namespace="test-ns",
            cluster="test-cluster",
            user_response="yes",
            confirmation_id="test-conf-yes"
        )

        # Assert
        assert "user_response" in record_yes
        assert record_yes["user_response"] == "yes"
        assert record_yes["status"] == "confirmed"

        # Test with 'no'
        record_no = document_confirmed_deletion(
            pod_name="test-pod-no",
            namespace="test-ns",
            cluster="test-cluster",
            user_response="no",
            confirmation_id="test-conf-no"
        )

        assert "user_response" in record_no
        assert record_no["user_response"] == "no"
        assert record_no["status"] == "rejected"

    def test_confirmed_pod_name_stored_for_deletion(self, temp_log_file):
        """
        AC3: Confirmed pod name is stored for deletion
        """
        # Arrange
        pod_name = "pbx-web-5ff68464d-mkn8n"
        confirmation_id = "test-conf-pod"

        # Act
        record = document_confirmed_deletion(
            pod_name=pod_name,
            namespace="default",
            cluster="iad-ci",
            user_response="yes",
            confirmation_id=confirmation_id
        )

        # Assert - pod name is stored
        assert record["pod_name"] == pod_name
        assert "namespace" in record
        assert "cluster" in record

        # Assert - pod name can be retrieved for deletion
        retrieved = get_latest_confirmed_deletion()
        assert retrieved is not None
        assert retrieved["pod_name"] == pod_name
        assert retrieved["namespace"] == "default"
        assert retrieved["cluster"] == "iad-ci"

    def test_document_persistent_and_accessible(self, temp_log_file):
        """
        AC4: Document is persistent and accessible by deletion step
        """
        # Arrange
        pod_name = "persistent-pod-123"
        confirmation_id = "test-conf-persist"

        # Act - Write to file
        record = document_confirmed_deletion(
            pod_name=pod_name,
            namespace="test-ns",
            cluster="test-cluster",
            user_response="yes",
            confirmation_id=confirmation_id
        )

        # Assert - File exists and is readable
        assert temp_log_file.exists()

        with open(temp_log_file, 'r') as f:
            content = f.read()
            assert content  # File is not empty

        # Assert - Record is accessible via retrieval function
        retrieved = get_latest_confirmed_deletion()
        assert retrieved is not None
        assert retrieved["pod_name"] == pod_name
        assert retrieved["confirmation_id"] == confirmation_id

    def test_retrieval_by_confirmation_id(self, temp_log_file):
        """Test retrieval by confirmation ID."""
        # Arrange
        confirmation_id = "test-conf-lookup"
        pod_name = "lookup-pod-123"

        # Act
        document_confirmed_deletion(
            pod_name=pod_name,
            namespace="test-ns",
            cluster="test-cluster",
            user_response="yes",
            confirmation_id=confirmation_id
        )

        # Assert
        retrieved = get_confirmed_deletion_by_confirmation_id(confirmation_id)
        assert retrieved is not None
        assert retrieved["pod_name"] == pod_name
        assert retrieved["confirmation_id"] == confirmation_id

    def test_list_all_confirmed_deletions(self, temp_log_file):
        """Test listing all confirmed deletions."""
        # Arrange - Create multiple records
        for i in range(3):
            document_confirmed_deletion(
                pod_name=f"pod-{i}",
                namespace="test-ns",
                cluster="test-cluster",
                user_response="yes",
                confirmation_id=f"conf-{i}"
            )

        # Act
        all_deletions = list_all_confirmed_deletions()

        # Assert
        assert len(all_deletions) == 3
        # Check they're sorted by timestamp (newest first)
        timestamps = [d["timestamp"] for d in all_deletions]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_list_with_limit(self, temp_log_file):
        """Test listing with a limit."""
        # Arrange
        for i in range(5):
            document_confirmed_deletion(
                pod_name=f"pod-{i}",
                namespace="test-ns",
                cluster="test-cluster",
                user_response="yes",
                confirmation_id=f"conf-{i}"
            )

        # Act
        limited = list_all_confirmed_deletions(limit=2)

        # Assert
        assert len(limited) == 2

    def test_get_deletion_count(self, temp_log_file):
        """Test getting deletion statistics."""
        # Arrange
        for i in range(3):
            document_confirmed_deletion(
                pod_name=f"confirmed-{i}",
                namespace="test-ns",
                cluster="test-cluster",
                user_response="yes",
                confirmation_id=f"conf-yes-{i}"
            )

        for i in range(2):
            document_confirmed_deletion(
                pod_name=f"rejected-{i}",
                namespace="test-ns",
                cluster="test-cluster",
                user_response="no",
                confirmation_id=f"conf-no-{i}"
            )

        # Act
        stats = get_deletion_count()

        # Assert
        assert stats["total_confirmed"] == 3
        assert stats["total_rejected"] == 2
        assert stats["total_records"] == 5

    def test_rejected_deletions_not_returned(self, temp_log_file):
        """Test that rejected deletions are not returned as confirmed."""
        # Arrange
        document_confirmed_deletion(
            pod_name="rejected-pod",
            namespace="test-ns",
            cluster="test-cluster",
            user_response="no",
            confirmation_id="conf-rejected"
        )

        document_confirmed_deletion(
            pod_name="confirmed-pod",
            namespace="test-ns",
            cluster="test-cluster",
            user_response="yes",
            confirmation_id="conf-confirmed"
        )

        # Act
        latest = get_latest_confirmed_deletion()
        all_confirmed = list_all_confirmed_deletions()

        # Assert - Only the confirmed one should be returned
        assert latest is not None
        assert latest["pod_name"] == "confirmed-pod"
        assert len(all_confirmed) == 1
        assert all_confirmed[0]["pod_name"] == "confirmed-pod"

    def test_json_format_in_log_file(self, temp_log_file):
        """Test that records are stored as valid JSON in the log file."""
        # Arrange & Act
        document_confirmed_deletion(
            pod_name="json-test-pod",
            namespace="test-ns",
            cluster="test-cluster",
            user_response="yes",
            confirmation_id="conf-json-test"
        )

        # Assert - File contains valid JSON
        with open(temp_log_file, 'r') as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    assert isinstance(record, dict)
                    assert "timestamp" in record
                    assert "pod_name" in record

    def test_missing_required_parameters(self):
        """Test that missing required parameters raise ValueError."""
        with pytest.raises(ValueError, match="pod_name is required"):
            document_confirmed_deletion(
                pod_name="",
                namespace="test-ns",
                cluster="test-cluster",
                user_response="yes",
                confirmation_id="test-conf"
            )

        with pytest.raises(ValueError, match="user_response is required"):
            document_confirmed_deletion(
                pod_name="test-pod",
                namespace="test-ns",
                cluster="test-cluster",
                user_response="",
                confirmation_id="test-conf"
            )

        with pytest.raises(ValueError, match="confirmation_id is required"):
            document_confirmed_deletion(
                pod_name="test-pod",
                namespace="test-ns",
                cluster="test-cluster",
                user_response="yes",
                confirmation_id=""
            )

    def test_multiple_confirmations_sorted_by_timestamp(self, temp_log_file):
        """Test that multiple confirmations are stored and retrieved in timestamp order."""
        # Arrange
        import time

        records = []
        for i in range(3):
            record = document_confirmed_deletion(
                pod_name=f"timestamp-pod-{i}",
                namespace="test-ns",
                cluster="test-cluster",
                user_response="yes",
                confirmation_id=f"conf-ts-{i}"
            )
            records.append(record)
            time.sleep(0.01)  # Ensure different timestamps

        # Act
        all_deletions = list_all_confirmed_deletions()

        # Assert - Should be sorted newest first
        assert len(all_deletions) == 3
        # The last created should be first in the list
        assert all_deletions[0]["pod_name"] == "timestamp-pod-2"
        assert all_deletions[1]["pod_name"] == "timestamp-pod-1"
        assert all_deletions[2]["pod_name"] == "timestamp-pod-0"
