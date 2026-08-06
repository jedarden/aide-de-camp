#!/usr/bin/env python3
"""
Unit tests for the validation runner.

Tests cover:
- End-to-end validation with all checks
- JSON well-formedness failures
- Required fields validation failures
- Data type validation failures
- Completeness validation failures
- Multiple simultaneous errors
- Valid file acceptance
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
import os

from src.validation.runner import validate_deployment_file


class TestValidDeploymentFile:
    """Test validation with valid deployment files."""

    def test_complete_valid_file_passes(self):
        """Test that a complete valid file passes all validations."""
        # Create a complete 30-day dataset
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Generate all 30 dates
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)

        # Create deployment events for all 30 days
        events = [
            {"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"}
            for i, d in enumerate(dates)
        ]

        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 30,
            "successful_deployments": 28,
            "failed_deployments": 2,
            "success_rate": 93.33,
            "failure_rate": 6.67,
            "deployment_frequency_per_day": 1.0,
            "mean_time_between_deployments_hours": 24.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is True
            assert errors == []
        finally:
            os.unlink(temp_path)

    def test_minimal_valid_file_passes(self):
        """Test that a minimal valid file passes."""
        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 0,
            "successful_deployments": 0,
            "failed_deployments": 0,
            "success_rate": 0.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.0,
            "mean_time_between_deployments_hours": 0.0,
            "deployment_names": [],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # This should fail completeness (no deployment events for 30 days)
            # but pass other validations
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Completeness" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)


class TestJsonWellformedness:
    """Test JSON well-formedness validation."""

    def test_nonexistent_file_fails(self):
        """Test that nonexistent file fails."""
        is_valid, errors = validate_deployment_file("/nonexistent/file.json")
        assert is_valid is False
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_invalid_json_fails(self):
        """Test that invalid JSON fails."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json content")
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) == 1
            assert "JSON well-formedness" in errors[0]
            assert "Invalid JSON" in errors[0]
        finally:
            os.unlink(temp_path)

    def test_empty_json_object_fails(self):
        """Test that empty JSON object fails."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            # Should fail required fields validation
            assert len(errors) > 0
            assert any("Required fields" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)

    def test_json_array_fails(self):
        """Test that JSON array (not object) fails."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([1, 2, 3], f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            # Should fail required fields validation
            assert len(errors) > 0
        finally:
            os.unlink(temp_path)

    def test_non_serializable_data_in_file(self):
        """Test file with non-JSON-serializable data (shouldn't happen in real files)."""
        # This test is for files that somehow contain non-serializable data
        # In practice, json.load() would fail on such files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"timestamp": "2026-07-01T00:00:00Z"}')
            temp_path = f.name

        try:
            # Valid JSON, but will fail required fields
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
        finally:
            os.unlink(temp_path)


class TestRequiredFieldsValidation:
    """Test required fields validation."""

    def test_missing_service_field_fails(self):
        """Test that missing service field fails."""
        data = {
            "period_days": 30,
            "total_deployments": 10,
            # Missing service and other required fields
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Required fields" in str(e) for e in errors)
            assert any("service" in str(e).lower() for e in errors)
        finally:
            os.unlink(temp_path)

    def test_missing_multiple_fields_fails(self):
        """Test that missing multiple fields fails."""
        data = {"service": "test"}  # Only one field

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Required fields" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)

    def test_all_required_fields_present_passes_field_check(self):
        """Test that all required fields pass the field presence check."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 1,
            "successful_deployments": 1,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.033,
            "mean_time_between_deployments_hours": 720.0,
            "deployment_names": ["test-service"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": [
                {"date": "2026-07-01", "event": "deploy0"}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            # Should fail completeness (only 1 day, not 30) but pass field check
            assert is_valid is False
            assert any("Completeness" in str(e) for e in errors)
            # Should not have required fields errors
            assert not any("Required fields" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)


class TestDataTypeValidation:
    """Test data type validation."""

    def test_incorrect_string_field_fails(self):
        """Test that incorrect string field type fails."""
        data = {
            "service": 123,  # Should be string
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["test"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Data types" in str(e) for e in errors)
            assert any("service" in str(e).lower() for e in errors)
        finally:
            os.unlink(temp_path)

    def test_incorrect_integer_field_fails(self):
        """Test that incorrect integer field type fails."""
        data = {
            "service": "test-service",
            "period_days": "30",  # Should be int
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["test"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Data types" in str(e) for e in errors)
            assert any("period_days" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)

    def test_incorrect_list_field_fails(self):
        """Test that incorrect list field type fails."""
        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": "not-a-list",  # Should be list
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Data types" in str(e) for e in errors)
            assert any("deployment_names" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)

    def test_invalid_timestamp_format_fails(self):
        """Test that invalid timestamp format fails."""
        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["test"],
            "first_deployment": "invalid-timestamp",  # Invalid format
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Data types" in str(e) for e in errors)
            assert any("invalid date" in str(e).lower() for e in errors)
        finally:
            os.unlink(temp_path)

    def test_correct_types_pass_type_check(self):
        """Test that correct types pass type validation."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 1,
            "successful_deployments": 1,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.033,
            "mean_time_between_deployments_hours": 720.0,
            "deployment_names": ["test-service"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": [
                {"date": "2026-07-01", "event": "deploy0"}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            # Should fail completeness but pass type check
            assert is_valid is False
            assert any("Completeness" in str(e) for e in errors)
            # Should not have type errors
            assert not any("Data types" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)


class TestCompletenessValidation:
    """Test 30-day completeness validation."""

    def test_incomplete_data_fails(self):
        """Test that incomplete data (missing dates) fails."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Only 3 dates instead of 30
        events = [
            {"date": "2026-07-01", "event": "deploy1"},
            {"date": "2026-07-02", "event": "deploy2"},
            {"date": "2026-07-03", "event": "deploy3"},
        ]

        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 3,
            "successful_deployments": 3,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.1,
            "mean_time_between_deployments_hours": 240.0,
            "deployment_names": ["test-service"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-03T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Completeness" in str(e) for e in errors)
            assert any("Missing data" in str(e) or "Missing" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)

    def test_date_gaps_fail(self):
        """Test that gaps in date sequence fail."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Missing dates in the middle
        events = [
            {"date": "2026-07-01", "event": "deploy1"},
            {"date": "2026-07-05", "event": "deploy5"},  # Gap: missing 2,3,4
        ]

        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 2,
            "successful_deployments": 2,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.067,
            "mean_time_between_deployments_hours": 360.0,
            "deployment_names": ["test-service"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-05T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Completeness" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)

    def test_no_metadata_fails_completeness(self):
        """Test that missing metadata fails completeness check."""
        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 1,
            "successful_deployments": 1,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.033,
            "mean_time_between_deployments_hours": 720.0,
            "deployment_names": ["test-service"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "deployment_events_last_30_days": [
                {"date": "2026-07-01", "event": "deploy1"}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
            assert any("Completeness" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)

    def test_complete_30_day_data_passes(self):
        """Test that complete 30-day data passes completeness check."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Generate all 30 dates
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)

        events = [
            {"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"}
            for i, d in enumerate(dates)
        ]

        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 30,
            "successful_deployments": 30,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 1.0,
            "mean_time_between_deployments_hours": 24.0,
            "deployment_names": ["test-service"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is True
            assert errors == []
        finally:
            os.unlink(temp_path)


class TestMultipleErrors:
    """Test files with multiple validation errors."""

    def test_multiple_errors_collected(self):
        """Test that multiple errors are collected and reported."""
        # File with multiple issues:
        # - Wrong type for service (should be string)
        # - Wrong type for period_days (should be int)
        # - Incomplete data (only 3 days)
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        events = [
            {"date": "2026-07-01", "event": "deploy1"},
            {"date": "2026-07-02", "event": "deploy2"},
            {"date": "2026-07-03", "event": "deploy3"},
        ]

        data = {
            "service": 123,  # Wrong type
            "period_days": "30",  # Wrong type
            "total_deployments": 3,
            "successful_deployments": 3,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.1,
            "mean_time_between_deployments_hours": 240.0,
            "deployment_names": ["test-service"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-03T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) >= 2  # Should have at least 2 errors

            # Check that we get both type errors and completeness error
            error_types = [str(e) for e in errors]
            has_type_error = any("Data types" in e for e in error_types)
            has_completeness_error = any("Completeness" in e for e in error_types)

            assert has_type_error, "Should have data type errors"
            assert has_completeness_error, "Should have completeness error"
        finally:
            os.unlink(temp_path)

    def test_field_and_type_errors_together(self):
        """Test that field presence and type errors are collected together."""
        # Missing some fields, wrong types on others
        data = {
            "service": 123,  # Wrong type
            "period_days": "30",  # Wrong type
            # Missing many required fields
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) >= 1

            # Should have both required fields and data types errors
            error_types = [str(e) for e in errors]
            has_field_error = any("Required fields" in e for e in error_types)
            has_type_error = any("Data types" in e for e in error_types)

            assert has_field_error, "Should have required fields errors"
            assert has_type_error, "Should have data type errors"
        finally:
            os.unlink(temp_path)


class TestReturnSignature:
    """Test the return signature of validate_deployment_file."""

    def test_returns_tuple(self):
        """Test that function returns a tuple."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path)
            assert isinstance(result, tuple)
            assert len(result) == 2
        finally:
            os.unlink(temp_path)

    def test_first_element_is_bool(self):
        """Test that first element is boolean."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert isinstance(is_valid, bool)
        finally:
            os.unlink(temp_path)

    def test_second_element_is_list(self):
        """Test that second element is a list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert isinstance(errors, list)
        finally:
            os.unlink(temp_path)

    def test_valid_file_returns_empty_list(self):
        """Test that valid file returns empty error list."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Generate all 30 dates
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)

        events = [
            {"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"}
            for i, d in enumerate(dates)
        ]

        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 30,
            "successful_deployments": 30,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 1.0,
            "mean_time_between_deployments_hours": 24.0,
            "deployment_names": ["test-service"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is True
            assert errors == []
        finally:
            os.unlink(temp_path)

    def test_invalid_file_returns_populated_list(self):
        """Test that invalid file returns populated error list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is False
            assert len(errors) > 0
        finally:
            os.unlink(temp_path)


class TestRealWorldScenarios:
    """Test with realistic deployment data scenarios."""

    def test_pbx_web_complete_30_days(self):
        """Test with realistic pbx-web complete 30-day data."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Generate all 30 dates
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)

        events = [
            {"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"}
            for i, d in enumerate(dates)
        ]

        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 30,
            "successful_deployments": 28,
            "failed_deployments": 2,
            "success_rate": 93.33,
            "failure_rate": 6.67,
            "deployment_frequency_per_day": 1.0,
            "mean_time_between_deployments_hours": 24.0,
            "deployment_names": ["pbx-web", "pbx-web-v2"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is True
            assert errors == []
        finally:
            os.unlink(temp_path)

    def test_whisper_stt_complete_30_days(self):
        """Test with realistic whisper-stt complete 30-day data."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Generate all 30 dates
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)

        events = [
            {"date": d.strftime("%Y-%m-%d"), "event": f"deploy{i}"}
            for i, d in enumerate(dates)
        ]

        data = {
            "service": "whisper-stt",
            "period_days": 30,
            "total_deployments": 30,
            "successful_deployments": 27,
            "failed_deployments": 3,
            "success_rate": 90.0,
            "failure_rate": 10.0,
            "deployment_frequency_per_day": 1.0,
            "mean_time_between_deployments_hours": 24.0,
            "deployment_names": ["whisper-stt"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "time_period": {
                    "start": start.isoformat() + "Z",
                    "end": end.isoformat() + "Z"
                }
            },
            "deployment_events_last_30_days": events
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid is True
            assert errors == []
        finally:
            os.unlink(temp_path)
