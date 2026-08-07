"""
Tests for load_categorized_failures module.

Tests the validation and grouping of categorized failures dataset.
"""

import json
import os
import tempfile
import pytest
from pathlib import Path

# Import the functions we're testing
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from load_categorized_failures import (
    find_field_value,
    validate_record,
    ValidationError,
    load_categorized_failures,
    FIELD_MAPPINGS
)


class TestFindFieldValue:
    """Tests for find_field_value function."""

    def test_find_existing_field(self):
        """Test finding an existing field."""
        record = {'namespace': 'pbx-web', 'pod_name': 'test-pod'}
        result = find_field_value(record, 'service')
        assert result is not None
        # Should return first matching field (namespace comes before pod_name in mappings)
        assert result in ['pbx-web', 'test-pod']

    def test_find_field_with_none_value(self):
        """Test that None values are skipped."""
        record = {'namespace': None, 'pod_name': 'test-pod'}
        result = find_field_value(record, 'service')
        assert result == 'test-pod'

    def test_find_field_with_empty_string(self):
        """Test that empty strings are skipped."""
        record = {'namespace': '', 'pod_name': 'test-pod'}
        result = find_field_value(record, 'service')
        assert result == 'test-pod'

    def test_find_field_with_na_value(self):
        """Test that 'N/A' values are skipped."""
        record = {'namespace': 'N/A', 'pod_name': 'test-pod'}
        result = find_field_value(record, 'service')
        assert result == 'test-pod'

    def test_find_field_not_present(self):
        """Test when field is not present."""
        record = {'unrelated_field': 'value'}
        result = find_field_value(record, 'service')
        assert result is None


class TestValidateRecord:
    """Tests for validate_record function."""

    def test_validate_complete_record(self):
        """Test validating a record with all fields."""
        record = {
            'pattern_category': 'HTTPError',
            'namespace': 'pbx-web',
            'image': 'ronaldraygun/pbx-web:1.0.9',
            'timestamp': '2026-07-28T13:36:40Z'
        }

        result = validate_record(record, 0)

        assert result['pattern_category'] == 'HTTPError'
        assert result['service'] == 'pbx-web'
        assert result['image_tag'] == 'ronaldraygun/pbx-web:1.0.9'
        assert result['timestamp'] == '2026-07-28T13:36:40Z'
        assert '_original' in result

    def test_validate_minimal_record(self):
        """Test validating a record with only pattern_category."""
        record = {
            'pattern_category': 'NetworkIssue'
        }

        result = validate_record(record, 0)

        assert result['pattern_category'] == 'NetworkIssue'
        assert result['service'] is None
        assert result['image_tag'] is None
        assert result['timestamp'] is None
        assert '_original' in result

    def test_validate_record_without_pattern_category(self):
        """Test that records without pattern_category raise ValidationError."""
        record = {
            'namespace': 'pbx-web',
            'image': 'test:1.0'
        }

        with pytest.raises(ValidationError, match='pattern_category'):
            validate_record(record, 0)

    def test_validate_with_alternative_service_fields(self):
        """Test that alternative service field names work."""
        record = {
            'pattern_category': 'HTTPError',
            'pod': 'test-pod-123'
        }

        result = validate_record(record, 0)

        assert result['pattern_category'] == 'HTTPError'
        assert result['service'] == 'test-pod-123'

    def test_validate_with_alternative_timestamp_fields(self):
        """Test that alternative timestamp field names work."""
        record = {
            'pattern_category': 'HTTPError',
            'data_collection_timestamp': '2026-07-28T13:36:40Z'
        }

        result = validate_record(record, 0)

        assert result['pattern_category'] == 'HTTPError'
        assert result['timestamp'] == '2026-07-28T13:36:40Z'


class TestLoadCategorizedFailures:
    """Tests for load_categorized_failures function."""

    def test_load_valid_file(self):
        """Test loading a properly formatted file."""
        test_data = {
            'failures': [
                {'pattern_category': 'HTTPError', 'namespace': 'pbx-web', 'timestamp': '2026-07-28T13:36:40Z'},
                {'pattern_category': 'NetworkIssue', 'pod_name': 'test-pod'},
                {'pattern_category': 'HTTPError', 'namespace': 'whisper-stt', 'timestamp': '2026-07-28T14:00:00Z'}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            result = load_categorized_failures(temp_path)

            assert 'HTTPError' in result
            assert 'NetworkIssue' in result
            assert len(result['HTTPError']) == 2
            assert len(result['NetworkIssue']) == 1

            # Check field coverage in HTTPError records
            assert result['HTTPError'][0]['service'] == 'pbx-web'
            assert result['HTTPError'][0]['timestamp'] == '2026-07-28T13:36:40Z'

        finally:
            os.unlink(temp_path)

    def test_load_file_with_invalid_records(self):
        """Test that invalid records are skipped gracefully."""
        test_data = {
            'failures': [
                {'pattern_category': 'HTTPError', 'namespace': 'pbx-web'},
                {'unrelated_field': 'value'},  # Should be skipped
                {'pattern_category': 'NetworkIssue', 'pod_name': 'test-pod'}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            result = load_categorized_failures(temp_path)

            # Should only have valid records
            assert len(result['HTTPError']) == 1
            assert len(result['NetworkIssue']) == 1

        finally:
            os.unlink(temp_path)

    def test_load_nonexistent_file(self):
        """Test that FileNotFoundError is raised for missing files."""
        with pytest.raises(FileNotFoundError):
            load_categorized_failures('/nonexistent/path.json')

    def test_load_file_without_failures_key(self):
        """Test that ValueError is raised for files without 'failures' key."""
        test_data = {'wrong_key': []}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match='failures'):
                load_categorized_failures(temp_path)

        finally:
            os.unlink(temp_path)

    def test_file_not_found(self):
        """Test FileNotFoundError is raised for missing files."""
        with pytest.raises(FileNotFoundError):
            load_categorized_failures('/tmp/nonexistent_12345.json')


class TestIntegration:
    """Integration tests with the actual categorized failures file."""

    def test_load_actual_categorized_failures(self):
        """Test loading the actual categorized-failures-report.json if it exists."""
        input_file = Path('categorized-failures-report.json')

        if not input_file.exists():
            pytest.skip("categorized-failures-report.json not found")

        result = load_categorized_failures(str(input_file))

        # Check that we got expected categories
        assert 'uncategorized' in result
        assert len(result) >= 1

        # Check that records have expected structure
        uncategorized_records = result['uncategorized']
        if uncategorized_records:
            sample = uncategorized_records[0]
            assert 'pattern_category' in sample
            assert sample['pattern_category'] == 'uncategorized'
            assert '_original' in sample


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
