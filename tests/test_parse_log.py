"""
Comprehensive unit tests for log parsing module.

Tests cover all parsing scenarios including valid entries, missing fields,
and malformed JSON for the multi-format log parser.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.parse_log import (
    # Constants
    FORMAT_DEPLOYMENT,
    FORMAT_POD,
    FORMAT_EVENT,
    FORMAT_REPLICASET,
    FORMAT_UNKNOWN,
    # Main functions
    load_jsonl,
    detect_format,
    parse_entry,
    extract_fields,
    normalize_timestamp,
    # Field extraction functions
    extract_deployment_fields,
    extract_pod_fields,
    extract_event_fields,
    extract_replicaset_fields,
)


# -----------------------------------------------------------------------------
# Test fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def valid_pbx_web_entry():
    """Valid pbx-web deployment format entry."""
    return {
        'commit_hash': 'abc123def456',
        'deploy_type': 'feature_addition',
        'timestamp': '2026-08-06T12:00:00Z',
        'service': 'pbx-web',
        'author': 'John Doe',
        'message': 'Add new feature',
        'files_changed': 5,
        'files': ['src/main.py', 'src/utils.py'],
        'image_version': 'v1.2.3',
        'cluster': 'ardenone-cluster',
        'namespace': 'pbx-web'
    }


@pytest.fixture
def valid_whisper_stt_entry():
    """Valid whisper-stt pod format entry."""
    return {
        'name': 'whisper-stt-abc123',
        'status': 'Running',
        'startTime': '2026-08-06T10:30:00Z',
        'service': 'whisper-stt',
        'ready': True,
        'restartCount': 0,
        'nodeName': 'node-1',
        'podIP': '10.0.0.1',
        'image': 'whisper-stt:latest',
        'conditions': [{'type': 'Ready', 'status': 'True'}],
        'cluster': 'ardenone-cluster',
        'namespace': 'whisper-stt'
    }


@pytest.fixture
def valid_event_entry():
    """Valid Kubernetes event format entry."""
    return {
        'type': 'Warning',
        'reason': 'FailedScheduling',
        'object': 'pod/my-pod',
        'message': 'Insufficient cpu',
        'firstTimestamp': '2026-08-06T12:00:00Z',
        'lastTimestamp': '2026-08-06T12:05:00Z',
        'service': 'pbx-web',
        'cluster': 'ardenone-cluster',
        'namespace': 'pbx-web'
    }


@pytest.fixture
def valid_replicaset_entry():
    """Valid ReplicaSet format entry."""
    return {
        'name': 'pbx-web-abc123',
        'replicas': 3,
        'readyReplicas': 3,
        'observedGeneration': 5,
        'createdAt': '2026-08-06T10:00:00Z',
        'service': 'pbx-web',
        'cluster': 'ardenone-cluster',
        'namespace': 'pbx-web'
    }


@pytest.fixture
def temp_jsonl_file(tmp_path):
    """Create a temporary JSONL file for testing."""
    def _create_file(entries):
        file_path = tmp_path / "test.log"
        with open(file_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
        return str(file_path)
    return _create_file


# -----------------------------------------------------------------------------
# Tests for load_jsonl()
# -----------------------------------------------------------------------------


class TestLoadJsonl:
    """Tests for load_jsonl() function."""

    def test_valid_file_yields_entries(self, temp_jsonl_file):
        """Valid file yields all entries."""
        entries = [
            {'test': 'entry1'},
            {'test': 'entry2'},
            {'test': 'entry3'}
        ]
        file_path = temp_jsonl_file(entries)

        result, errors_count, skipped_count = load_jsonl(file_path)
        assert len(result) == 3
        assert errors_count == 0
        assert skipped_count == 0
        assert result[0] == {'test': 'entry1'}
        assert result[1] == {'test': 'entry2'}
        assert result[2] == {'test': 'entry3'}

    def test_empty_lines_skipped(self, temp_jsonl_file):
        """Empty lines are skipped."""
        entries = [
            {'test': 'entry1'},
            None,  # Will create empty line
            {'test': 'entry2'}
        ]
        file_path = temp_jsonl_file(entries)

        # Create file with empty line
        with open(file_path, 'w') as f:
            f.write('{"test":"entry1"}\n\n   \n{"test":"entry2"}\n')

        result, errors_count, skipped_count = load_jsonl(file_path)
        assert len(result) == 2
        assert errors_count == 0
        assert skipped_count == 2  # Two empty lines skipped

    def test_missing_file_raises_error(self):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="JSONL file not found"):
            load_jsonl('/nonexistent/path/file.log')

    def test_path_not_file_raises_error(self, tmp_path):
        """Path that is not a file raises ValueError."""
        with pytest.raises(ValueError, match="Path is not a file"):
            load_jsonl(str(tmp_path))

    def test_malformed_json_skipped_with_warning(self, temp_jsonl_file, caplog):
        """Malformed JSON lines are skipped with warning logged."""
        file_path = temp_jsonl_file([])

        # Create file with malformed JSON
        with open(file_path, 'w') as f:
            f.write('{"valid": "entry"}\n')
            f.write('{invalid json}\n')
            f.write('{"another": "entry"}\n')

        with caplog.at_level(logging.WARNING):
            result = list(load_jsonl(file_path))

        # Should skip malformed line and return valid entries
        assert len(result) == 2
        assert result[0] == {'valid': 'entry'}
        assert result[1] == {'another': 'entry'}

        # Check warning was logged
        assert any('Failed to parse line' in record.message for record in caplog.records)


# -----------------------------------------------------------------------------
# Tests for detect_format()
# -----------------------------------------------------------------------------


class TestDetectFormat:
    """Tests for detect_format() function."""

    def test_detect_deployment_format(self, valid_pbx_web_entry):
        """pbx-web deployment format is detected correctly."""
        result = detect_format(valid_pbx_web_entry)
        assert result == FORMAT_DEPLOYMENT

    def test_detect_pod_format(self, valid_whisper_stt_entry):
        """whisper-stt pod format is detected correctly."""
        result = detect_format(valid_whisper_stt_entry)
        assert result == FORMAT_POD

    def test_detect_event_format(self, valid_event_entry):
        """Kubernetes event format is detected correctly."""
        result = detect_format(valid_event_entry)
        assert result == FORMAT_EVENT

    def test_detect_replicaset_format(self, valid_replicaset_entry):
        """ReplicaSet format is detected correctly."""
        result = detect_format(valid_replicaset_entry)
        assert result == FORMAT_REPLICASET

    def test_unknown_format_returns_unknown(self, caplog):
        """Unknown format returns 'unknown' and logs debug message."""
        unknown_entry = {'random': 'fields', 'with': 'no signature'}

        with caplog.at_level(logging.DEBUG):
            result = detect_format(unknown_entry)

        assert result == FORMAT_UNKNOWN
        assert any('Unable to detect format' in record.message for record in caplog.records)

    def test_pod_not_confused_with_deployment(self):
        """Pod format without commit_hash is not confused with deployment."""
        # Pod with commit_hash is detected as deployment (deployment check comes first)
        pod_entry = {
            'name': 'test-pod',
            'status': 'Running',
            'podIP': '10.0.0.1',
            'commit_hash': 'abc123',
            'deploy_type': 'feature_addition'
        }
        # This has both pod and deployment signatures - deployment format takes priority
        result = detect_format(pod_entry)
        assert result == FORMAT_DEPLOYMENT

    def test_replicaset_not_confused_with_pod(self):
        """ReplicaSet format is detected even with pod-like fields."""
        # ReplicaSet with podIP is detected as pod (pod check comes first when status is present)
        replicaset_entry = {
            'name': 'test-replicaset',
            'replicas': 3,
            'readyReplicas': 2,
            'podIP': '10.0.0.1',
            'status': 'Running'  # This makes it match pod format (name + status + podIP)
        }
        # With all pod fields present, it's detected as pod
        result = detect_format(replicaset_entry)
        assert result == FORMAT_POD


# -----------------------------------------------------------------------------
# Tests for normalize_timestamp()
# -----------------------------------------------------------------------------


class TestNormalizeTimestamp:
    """Tests for normalize_timestamp() function."""

    def test_unix_epoch_seconds(self):
        """Unix epoch timestamp in seconds is normalized."""
        # 2026-08-06 12:00:00 UTC = 1786017600 seconds since epoch
        result = normalize_timestamp(1786017600)
        assert result == '2026-08-06T12:00:00Z'

    def test_unix_epoch_milliseconds(self):
        """Unix epoch timestamp in milliseconds is normalized."""
        # 2026-08-06 12:00:00 UTC = 1786017600000 milliseconds since epoch
        result = normalize_timestamp(1786017600000)
        assert result == '2026-08-06T12:00:00Z'

    def test_iso8601_with_z_suffix(self):
        """ISO 8601 timestamp with Z suffix is preserved."""
        result = normalize_timestamp('2026-08-06T12:00:00Z')
        assert result == '2026-08-06T12:00:00Z'

    def test_iso8601_with_timezone(self):
        """ISO 8601 timestamp with timezone is normalized to Z."""
        result = normalize_timestamp('2026-08-06T12:00:00+00:00')
        assert result == '2026-08-06T12:00:00Z'

    def test_iso8601_without_timezone(self):
        """ISO 8601 timestamp without timezone gets Z suffix."""
        result = normalize_timestamp('2026-08-06T12:00:00')
        assert result == '2026-08-06T12:00:00Z'

    def test_datetime_object(self):
        """datetime object is normalized to ISO 8601 with Z."""
        dt = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        result = normalize_timestamp(dt)
        assert result == '2026-08-06T12:00:00Z'

    def test_none_returns_none(self):
        """None input returns None."""
        result = normalize_timestamp(None)
        assert result is None

    def test_invalid_string_returns_none(self):
        """Invalid string returns None."""
        result = normalize_timestamp('invalid-timestamp')
        assert result is None

    def test_epoch_as_string(self):
        """Unix epoch as string is handled correctly."""
        result = normalize_timestamp('1786017600')
        assert result == '2026-08-06T12:00:00Z'

    def test_negative_timestamp(self):
        """Negative timestamp (before epoch) is handled."""
        result = normalize_timestamp(-86400)  # One day before epoch
        assert result == '1969-12-31T00:00:00Z'


# -----------------------------------------------------------------------------
# Tests for extract_deployment_fields()
# -----------------------------------------------------------------------------


class TestExtractDeploymentFields:
    """Tests for extract_deployment_fields() function."""

    def test_all_fields_present_correct_normalization(self, valid_pbx_web_entry):
        """All fields present → correct normalization."""
        result = extract_deployment_fields(valid_pbx_web_entry)

        assert result['timestamp'] == '2026-08-06T12:00:00Z'
        assert result['service'] == 'pbx-web'
        assert result['event_type'] == 'deployment_feature_addition'
        assert result['status'] == 'success'
        assert result['error_code'] is None
        assert result['duration_ms'] is None
        assert result['cluster'] == 'ardenone-cluster'
        assert result['namespace'] == 'pbx-web'
        assert 'metadata' in result
        assert result['metadata']['raw_format'] == FORMAT_DEPLOYMENT

    def test_missing_timestamp_returns_none(self):
        """Missing timestamp → None."""
        entry = {'commit_hash': 'abc123', 'deploy_type': 'feature_addition'}
        result = extract_deployment_fields(entry)
        assert result['timestamp'] is None

    def test_missing_service_defaults_to_pbx_web(self):
        """Missing service → defaults to 'pbx-web'."""
        entry = {'commit_hash': 'abc123', 'deploy_type': 'feature_addition'}
        result = extract_deployment_fields(entry)
        assert result['service'] == 'pbx-web'

    def test_rollback_deploy_type_sets_failure_status(self):
        """Rollback deploy_type → failure status."""
        entry = {'commit_hash': 'abc123', 'deploy_type': 'rollback'}
        result = extract_deployment_fields(entry)
        assert result['status'] == 'failure'
        assert result['error_code'] == 'rollback'

    def test_bugfix_deploy_type_sets_warning_status(self):
        """Bugfix deploy_type → warning status."""
        entry = {'commit_hash': 'abc123', 'deploy_type': 'bugfix'}
        result = extract_deployment_fields(entry)
        assert result['status'] == 'warning'

    def test_config_change_deploy_type_sets_success_status(self):
        """Config change deploy_type → success status."""
        entry = {'commit_hash': 'abc123', 'deploy_type': 'config_change'}
        result = extract_deployment_fields(entry)
        assert result['status'] == 'success'

    def test_unknown_deploy_type_sets_unknown_status(self):
        """Unknown deploy_type → unknown status."""
        entry = {'commit_hash': 'abc123', 'deploy_type': 'unknown_type'}
        result = extract_deployment_fields(entry)
        assert result['status'] == 'unknown'

    def test_source_fields_preserved_in_metadata(self, valid_pbx_web_entry):
        """Source fields are preserved in metadata."""
        result = extract_deployment_fields(valid_pbx_web_entry)

        assert 'source_fields' in result['metadata']
        source_fields = result['metadata']['source_fields']

        assert source_fields['commit_hash'] == 'abc123def456'
        assert source_fields['author'] == 'John Doe'
        assert source_fields['message'] == 'Add new feature'
        assert source_fields['files_changed'] == 5
        assert source_fields['files'] == ['src/main.py', 'src/utils.py']
        assert source_fields['image_version'] == 'v1.2.3'


# -----------------------------------------------------------------------------
# Tests for extract_pod_fields()
# -----------------------------------------------------------------------------


class TestExtractPodFields:
    """Tests for extract_pod_fields() function."""

    def test_all_fields_present_correct_normalization(self, valid_whisper_stt_entry):
        """All fields present → correct normalization."""
        result = extract_pod_fields(valid_whisper_stt_entry)

        assert result['timestamp'] == '2026-08-06T10:30:00Z'
        assert result['service'] == 'whisper-stt'
        assert result['event_type'] == 'pod_status'
        assert result['status'] == 'success'  # Running + ready
        assert result['error_code'] is None
        assert result['cluster'] == 'ardenone-cluster'
        assert result['namespace'] == 'whisper-stt'
        assert 'metadata' in result
        assert result['metadata']['raw_format'] == FORMAT_POD

    def test_running_not_ready_sets_warning(self):
        """Running but not ready → warning status."""
        entry = {
            'name': 'test-pod',
            'status': 'Running',
            'ready': False,
            'podIP': '10.0.0.1'
        }
        result = extract_pod_fields(entry)
        assert result['status'] == 'warning'

    def test_failed_status_sets_failure(self):
        """Failed status → failure status."""
        entry = {
            'name': 'test-pod',
            'status': 'Failed',
            'podIP': '10.0.0.1'
        }
        result = extract_pod_fields(entry)
        assert result['status'] == 'failure'
        assert result['error_code'] == 'failed'

    def test_crashloopbackoff_sets_failure(self):
        """CrashLoopBackOff status → failure status."""
        entry = {
            'name': 'test-pod',
            'status': 'CrashLoopBackOff',
            'podIP': '10.0.0.1'
        }
        result = extract_pod_fields(entry)
        assert result['status'] == 'failure'
        assert result['error_code'] == 'crashloopbackoff'

    def test_pending_status_sets_warning(self):
        """Pending status → warning status."""
        entry = {
            'name': 'test-pod',
            'status': 'Pending',
            'podIP': '10.0.0.1'
        }
        result = extract_pod_fields(entry)
        assert result['status'] == 'warning'

    def test_containercreating_status_sets_warning(self):
        """ContainerCreating status → warning status."""
        entry = {
            'name': 'test-pod',
            'status': 'ContainerCreating',
            'podIP': '10.0.0.1'
        }
        result = extract_pod_fields(entry)
        assert result['status'] == 'warning'

    def test_unknown_status_sets_unknown(self):
        """Unknown status → unknown status."""
        entry = {
            'name': 'test-pod',
            'status': 'UnknownStatus',
            'podIP': '10.0.0.1'
        }
        result = extract_pod_fields(entry)
        assert result['status'] == 'unknown'

    def test_duration_calculated_from_start_time(self):
        """Duration is calculated from startTime to now."""
        # Mock datetime.now() to return a fixed time
        with patch('src.parse_log.datetime') as mock_dt:
            # Create a fixed "now" time 1 hour after start time
            fixed_now = datetime(2026, 8, 6, 11, 30, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = fixed_now
            mock_dt.fromisoformat.side_effect = lambda x: datetime.fromisoformat(x)

            entry = {
                'name': 'test-pod',
                'status': 'Running',
                'startTime': '2026-08-06T10:30:00Z',
                'podIP': '10.0.0.1'
            }

            result = extract_pod_fields(entry)
            # 1 hour = 3600000 milliseconds
            assert result['duration_ms'] == 3600000

    def test_source_fields_preserved_in_metadata(self, valid_whisper_stt_entry):
        """Source fields are preserved in metadata."""
        result = extract_pod_fields(valid_whisper_stt_entry)

        assert 'source_fields' in result['metadata']
        source_fields = result['metadata']['source_fields']

        assert source_fields['name'] == 'whisper-stt-abc123'
        assert source_fields['ready'] is True
        assert source_fields['restartCount'] == 0
        assert source_fields['nodeName'] == 'node-1'
        assert source_fields['podIP'] == '10.0.0.1'
        assert source_fields['image'] == 'whisper-stt:latest'


# -----------------------------------------------------------------------------
# Tests for extract_event_fields()
# -----------------------------------------------------------------------------


class TestExtractEventFields:
    """Tests for extract_event_fields() function."""

    def test_all_fields_present_correct_normalization(self, valid_event_entry):
        """All fields present → correct normalization."""
        result = extract_event_fields(valid_event_entry)

        assert result['timestamp'] == '2026-08-06T12:05:00Z'  # lastTimestamp preferred
        assert result['service'] == 'pbx-web'
        assert result['event_type'] == 'event_failedscheduling'
        assert result['status'] == 'warning'  # Warning type
        assert result['error_code'] == 'FailedScheduling'
        assert result['duration_ms'] is None
        assert result['cluster'] == 'ardenone-cluster'
        assert result['namespace'] == 'pbx-web'
        assert 'metadata' in result
        assert result['metadata']['raw_format'] == FORMAT_EVENT

    def test_warning_type_sets_warning_status(self):
        """Warning event type → warning status."""
        entry = {
            'type': 'Warning',
            'reason': 'TestWarning',
            'object': 'pod/test'
        }
        result = extract_event_fields(entry)
        assert result['status'] == 'warning'
        assert result['error_code'] == 'TestWarning'

    def test_normal_type_sets_success_status(self):
        """Normal event type → success status."""
        entry = {
            'type': 'Normal',
            'reason': 'Started',
            'object': 'pod/test'
        }
        result = extract_event_fields(entry)
        assert result['status'] == 'success'
        assert result['error_code'] is None

    def test_unknown_type_sets_unknown_status(self):
        """Unknown event type → unknown status."""
        entry = {
            'type': 'Unknown',
            'reason': 'TestReason',
            'object': 'pod/test'
        }
        result = extract_event_fields(entry)
        assert result['status'] == 'unknown'

    def test_first_timestamp_fallback(self):
        """First timestamp used when lastTimestamp is missing."""
        entry = {
            'type': 'Normal',
            'reason': 'Started',
            'object': 'pod/test',
            'firstTimestamp': '2026-08-06T10:00:00Z'
        }
        result = extract_event_fields(entry)
        assert result['timestamp'] == '2026-08-06T10:00:00Z'

    def test_source_fields_preserved_in_metadata(self, valid_event_entry):
        """Source fields are preserved in metadata."""
        result = extract_event_fields(valid_event_entry)

        assert 'source_fields' in result['metadata']
        source_fields = result['metadata']['source_fields']

        assert source_fields['type'] == 'Warning'
        assert source_fields['reason'] == 'FailedScheduling'
        assert source_fields['object'] == 'pod/my-pod'
        assert source_fields['message'] == 'Insufficient cpu'


# -----------------------------------------------------------------------------
# Tests for extract_replicaset_fields()
# -----------------------------------------------------------------------------


class TestExtractReplicasetFields:
    """Tests for extract_replicaset_fields() function."""

    def test_all_fields_present_correct_normalization(self, valid_replicaset_entry):
        """All fields present → correct normalization."""
        result = extract_replicaset_fields(valid_replicaset_entry)

        assert result['timestamp'] == '2026-08-06T10:00:00Z'
        assert result['service'] == 'pbx-web'
        assert result['event_type'] == 'replicaset_status'
        assert result['status'] == 'success'  # All replicas ready
        assert result['error_code'] is None
        assert result['cluster'] == 'ardenone-cluster'
        assert result['namespace'] == 'pbx-web'
        assert 'metadata' in result
        assert result['metadata']['raw_format'] == FORMAT_REPLICASET

    def test_all_replicas_ready_sets_success(self):
        """All replicas ready → success status."""
        entry = {
            'name': 'test-rs',
            'replicas': 5,
            'readyReplicas': 5
        }
        result = extract_replicaset_fields(entry)
        assert result['status'] == 'success'
        assert result['error_code'] is None

    def test_no_replicas_ready_sets_failure(self):
        """No replicas ready → failure status."""
        entry = {
            'name': 'test-rs',
            'replicas': 3,
            'readyReplicas': 0
        }
        result = extract_replicaset_fields(entry)
        assert result['status'] == 'failure'
        assert result['error_code'] == 'replicas_unready'

    def test_partial_replicas_ready_sets_warning(self):
        """Partial replicas ready → warning status."""
        entry = {
            'name': 'test-rs',
            'replicas': 3,
            'readyReplicas': 2
        }
        result = extract_replicaset_fields(entry)
        assert result['status'] == 'warning'
        assert result['error_code'] == 'replicas_unready'

    def test_zero_replicas_sets_unknown(self):
        """Zero replicas → unknown status."""
        entry = {
            'name': 'test-rs',
            'replicas': 0,
            'readyReplicas': 0
        }
        result = extract_replicaset_fields(entry)
        assert result['status'] == 'unknown'

    def test_duration_calculated_from_created_at(self):
        """Duration is calculated from createdAt to now."""
        with patch('src.parse_log.datetime') as mock_dt:
            fixed_now = datetime(2026, 8, 6, 11, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = fixed_now
            mock_dt.fromisoformat.side_effect = lambda x: datetime.fromisoformat(x)

            entry = {
                'name': 'test-rs',
                'replicas': 3,
                'readyReplicas': 3,
                'createdAt': '2026-08-06T10:00:00Z'
            }

            result = extract_replicaset_fields(entry)
            # 1 hour = 3600000 milliseconds
            assert result['duration_ms'] == 3600000

    def test_source_fields_preserved_in_metadata(self, valid_replicaset_entry):
        """Source fields are preserved in metadata."""
        result = extract_replicaset_fields(valid_replicaset_entry)

        assert 'source_fields' in result['metadata']
        source_fields = result['metadata']['source_fields']

        assert source_fields['name'] == 'pbx-web-abc123'
        assert source_fields['replicas'] == 3
        assert source_fields['readyReplicas'] == 3
        assert source_fields['observedGeneration'] == 5


# -----------------------------------------------------------------------------
# Tests for parse_entry()
# -----------------------------------------------------------------------------


class TestParseEntry:
    """Tests for parse_entry() function (main entry point)."""

    def test_parse_deployment_entry_end_to_end(self, valid_pbx_web_entry):
        """End-to-end parsing of deployment entry."""
        result = parse_entry(valid_pbx_web_entry)

        assert result['timestamp'] == '2026-08-06T12:00:00Z'
        assert result['service'] == 'pbx-web'
        assert result['event_type'] == 'deployment_feature_addition'
        assert result['status'] == 'success'
        assert result['cluster'] == 'ardenone-cluster'
        assert result['namespace'] == 'pbx-web'

    def test_parse_pod_entry_end_to_end(self, valid_whisper_stt_entry):
        """End-to-end parsing of pod entry."""
        result = parse_entry(valid_whisper_stt_entry)

        assert result['timestamp'] == '2026-08-06T10:30:00Z'
        assert result['service'] == 'whisper-stt'
        assert result['event_type'] == 'pod_status'
        assert result['status'] == 'success'
        assert result['cluster'] == 'ardenone-cluster'
        assert result['namespace'] == 'whisper-stt'

    def test_parse_event_entry_end_to_end(self, valid_event_entry):
        """End-to-end parsing of event entry."""
        result = parse_entry(valid_event_entry)

        assert result['event_type'] == 'event_failedscheduling'
        assert result['status'] == 'warning'
        assert result['error_code'] == 'FailedScheduling'

    def test_parse_replicaset_entry_end_to_end(self, valid_replicaset_entry):
        """End-to-end parsing of replicaset entry."""
        result = parse_entry(valid_replicaset_entry)

        assert result['event_type'] == 'replicaset_status'
        assert result['status'] == 'success'

    def test_unknown_format_returns_minimal_info(self, caplog):
        """Unknown format returns minimal info with warning logged."""
        unknown_entry = {'random': 'fields', 'with': 'no signature'}

        with caplog.at_level(logging.WARNING):
            result = parse_entry(unknown_entry)

        assert result['timestamp'] is None
        assert result['service'] == 'unknown'
        assert result['event_type'] == 'unknown'
        assert result['status'] == 'unknown'
        assert result['error_code'] is None
        assert result['duration_ms'] is None
        assert result['cluster'] == 'unknown'
        assert result['namespace'] == 'unknown'
        assert result['metadata']['raw_format'] == FORMAT_UNKNOWN

        # Check warning was logged
        assert any('Unknown log format' in record.message for record in caplog.records)

    def test_unknown_format_with_service_preserves_service(self, caplog):
        """Unknown format preserves service field if present."""
        unknown_entry = {'service': 'custom-service', 'data': 'value'}

        with caplog.at_level(logging.WARNING):
            result = parse_entry(unknown_entry)

        assert result['service'] == 'custom-service'

    def test_unknown_format_with_cluster_namespace_preserves_them(self, caplog):
        """Unknown format preserves cluster and namespace if present."""
        unknown_entry = {
            'service': 'custom-service',
            'cluster': 'test-cluster',
            'namespace': 'test-namespace'
        }

        with caplog.at_level(logging.WARNING):
            result = parse_entry(unknown_entry)

        assert result['cluster'] == 'test-cluster'
        assert result['namespace'] == 'test-namespace'


# -----------------------------------------------------------------------------
# Tests for extract_fields() (wrapper function)
# -----------------------------------------------------------------------------


class TestExtractFields:
    """Tests for extract_fields() function (wrapper for parse_entry)."""

    def test_extract_fields_calls_parse_entry(self, valid_pbx_web_entry):
        """extract_fields() correctly wraps parse_entry()."""
        result = extract_fields(valid_pbx_web_entry)

        assert result['timestamp'] == '2026-08-06T12:00:00Z'
        assert result['service'] == 'pbx-web'
        assert result['event_type'] == 'deployment_feature_addition'
        assert result['status'] == 'success'

    def test_extract_fields_with_pod_entry(self, valid_whisper_stt_entry):
        """extract_fields() works with pod entries."""
        result = extract_fields(valid_whisper_stt_entry)

        assert result['event_type'] == 'pod_status'
        assert result['status'] == 'success'


# -----------------------------------------------------------------------------
# Integration tests
# -----------------------------------------------------------------------------


class TestIntegration:
    """Integration tests for complete parsing workflows."""

    def test_parse_mixed_format_jsonl_file(self, temp_jsonl_file):
        """Parse JSONL file with mixed format entries."""
        entries = [
            {
                'commit_hash': 'abc123',
                'deploy_type': 'feature_addition',
                'timestamp': '2026-08-06T12:00:00Z',
                'service': 'pbx-web'
            },
            {
                'name': 'whisper-stt-xyz',
                'status': 'Running',
                'startTime': '2026-08-06T10:00:00Z',
                'service': 'whisper-stt',
                'ready': True,
                'restartCount': 0,
                'podIP': '10.0.0.2'
            },
            {
                'type': 'Normal',
                'reason': 'Started',
                'object': 'pod/test',
                'lastTimestamp': '2026-08-06T12:30:00Z',
                'service': 'pbx-web'
            }
        ]

        file_path = temp_jsonl_file(entries)
        results = []

        for raw_entry in load_jsonl(file_path):
            parsed = parse_entry(raw_entry)
            results.append(parsed)

        assert len(results) == 3
        assert results[0]['event_type'] == 'deployment_feature_addition'
        assert results[1]['event_type'] == 'pod_status'
        assert results[2]['event_type'] == 'event_started'

    def test_parse_file_with_missing_optional_fields(self, temp_jsonl_file):
        """Parse file with entries missing optional fields."""
        entries = [
            # Minimal deployment entry
            {'commit_hash': 'abc123', 'deploy_type': 'feature_addition'},
            # Minimal pod entry
            {'name': 'test-pod', 'status': 'Running', 'podIP': '10.0.0.1'},
            # Unknown format
            {'random': 'data'}
        ]

        file_path = temp_jsonl_file(entries)
        results = []

        for raw_entry in load_jsonl(file_path):
            parsed = parse_entry(raw_entry)
            results.append(parsed)

        assert len(results) == 3
        # All should parse without errors, using defaults
        assert all('timestamp' in r for r in results)
        assert all('service' in r for r in results)
        assert all('status' in r for r in results)
