#!/usr/bin/env python3
"""
Unit tests for the validation integration function.

Tests cover:
- Integration function chaining all validation steps
- Error aggregation from multiple validation failures
- Early termination on JSON parse failure
- Valid data passing all checks
- File-based and data-based validation paths
- Return signature (bool, List[str])
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
import os

from src.validation.integration import validate_all


class TestValidateAllIntegration:
    """Test the validate_all integration function."""

    def test_returns_correct_signature(self):
        """Test that validate_all returns (bool, List[str]) tuple."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            temp_path = f.name

        try:
            result = validate_all(file_path=temp_path)
            assert isinstance(result, tuple)
            assert len(result) == 2
            is_valid, errors = result
            assert isinstance(is_valid, bool)
            assert isinstance(errors, list)
            assert all(isinstance(e, str) for e in errors)
        finally:
            os.unlink(temp_path)

    def test_valid_data_passes_all_validations(self):
        """Test that valid data passes all validation steps."""
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
            "successful_deployments": 28,
            "failed_deployments": 2,
            "success_rate": 93.33,
            "failure_rate": 6.67,
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

        is_valid, errors = validate_all(data=data)
        assert is_valid is True
        assert errors == []

    def test_valid_file_passes_all_validations(self):
        """Test that valid file passes all validation steps."""
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
            "successful_deployments": 30,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
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
            is_valid, errors = validate_all(file_path=temp_path)
            assert is_valid is True
            assert errors == []
        finally:
            os.unlink(temp_path)

    def test_early_termination_on_invalid_json_file(self):
        """Test early termination when JSON file is malformed."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json content")
            temp_path = f.name

        try:
            is_valid, errors = validate_all(file_path=temp_path)
            assert is_valid is False
            assert len(errors) == 1
            assert "Invalid JSON in file" in errors[0]
            # Should not have other validation errors - early termination
            assert not any("Required fields" in str(e) for e in errors)
            assert not any("Data types" in str(e) for e in errors)
            assert not any("Completeness" in str(e) for e in errors)
        finally:
            os.unlink(temp_path)

    def test_early_termination_on_invalid_json_data(self):
        """Test early termination when provided data has invalid structure."""
        # Pass data with non-JSON-serializable content (datetime object)
        from datetime import datetime as dt
        data_with_datetime = {"timestamp": dt.now()}

        is_valid, errors = validate_all(data=data_with_datetime)
        assert is_valid is False
        # Should have JSON validation error and stop there
        assert len(errors) >= 1
        assert any("JSON validation" in str(e) for e in errors)

    def test_nonexistent_file_returns_error(self):
        """Test that nonexistent file returns appropriate error."""
        is_valid, errors = validate_all(file_path="/nonexistent/path/file.json")
        assert is_valid is False
        assert len(errors) == 1
        assert "File not found" in errors[0]

    def test_required_fields_validation_fails(self):
        """Test that missing required fields are caught."""
        data = {
            "service": "test-service"
            # Missing most required fields
        }

        is_valid, errors = validate_all(data=data)
        assert is_valid is False
        assert len(errors) >= 1
        assert any("Required fields" in str(e) for e in errors)

    def test_data_type_validation_fails(self):
        """Test that incorrect data types are caught."""
        data = {
            "service": 123,  # Should be string
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

        is_valid, errors = validate_all(data=data)
        assert is_valid is False
        assert len(errors) >= 1
        assert any("Data types" in str(e) for e in errors)

    def test_completeness_validation_fails(self):
        """Test that incomplete 30-day data is caught."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Only 3 days instead of 30
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

        is_valid, errors = validate_all(data=data)
        assert is_valid is False
        assert len(errors) >= 1
        assert any("Completeness" in str(e) for e in errors)

    def test_multiple_errors_aggregated(self):
        """Test that multiple validation errors are collected together."""
        # Data with multiple issues:
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

        is_valid, errors = validate_all(data=data)
        assert is_valid is False
        assert len(errors) >= 2

        # Should have both type errors and completeness error
        error_types = [str(e) for e in errors]
        has_type_error = any("Data types" in e for e in error_types)
        has_completeness_error = any("Completeness" in e for e in error_types)

        assert has_type_error, "Should have data type errors"
        assert has_completeness_error, "Should have completeness error"

    def test_neither_file_nor_data_provided_fails(self):
        """Test that calling without file_path or data fails."""
        is_valid, errors = validate_all()
        assert is_valid is False
        assert len(errors) == 1
        assert "Either file_path or data must be provided" in errors[0]

    def test_file_path_takes_precedence(self):
        """Test that file_path is used when both are provided."""
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

        file_data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 30,
            "successful_deployments": 30,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
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

        # Invalid data argument (should be ignored)
        invalid_data = {"service": 123}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(file_data, f)
            temp_path = f.name

        try:
            # Both provided - file_path should take precedence
            is_valid, errors = validate_all(file_path=temp_path, data=invalid_data)
            assert is_valid is True
            assert errors == []
        finally:
            os.unlink(temp_path)

    def test_custom_schema_override(self):
        """Test that custom schema can be provided."""
        from src.validation.deployment_data import DEPLOYMENT_DATA_SCHEMA

        # Use the default schema
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

        # Test with default schema
        is_valid, errors = validate_all(data=data, schema=DEPLOYMENT_DATA_SCHEMA)
        # Should fail completeness but pass schema validation
        assert is_valid is False
        assert any("Completeness" in str(e) for e in errors)

    def test_custom_date_range_for_completeness(self):
        """Test that custom date range can be provided for completeness check."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)  # Full 30-day range

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

        # Provide custom date range (should match what's in metadata)
        is_valid, errors = validate_all(
            data=data,
            start_date=start,
            end_date=end
        )
        # Should pass with custom date range
        assert is_valid is True
        assert errors == []

    def test_error_messages_are_descriptive(self):
        """Test that error messages are descriptive and actionable."""
        # Missing required fields
        data = {"service": "test"}

        is_valid, errors = validate_all(data=data)
        assert is_valid is False
        assert len(errors) > 0

        # Check that errors mention what's wrong
        for error in errors:
            assert isinstance(error, str)
            assert len(error) > 0
            # Errors should indicate the category
            assert any(cat in error for cat in [
                "Required fields",
                "Data types",
                "Completeness",
                "JSON validation"
            ])

    def test_all_four_validation_steps_executed(self):
        """Test that all four validation steps are executed in order."""
        start = datetime(2026, 7, 1)
        end = datetime(2026, 7, 30)

        # Create data that will pass JSON, required fields, and data types
        # but fail completeness (only 1 day)
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
            "last_deployment": "2026-07-01T23:59:59Z",
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

        is_valid, errors = validate_all(data=data)
        assert is_valid is False

        # Should have exactly 1 error (completeness)
        # This proves that JSON, required fields, and data types all passed
        assert len(errors) == 1
        assert "Completeness" in errors[0]

        # No JSON, required fields, or data types errors
        assert not any("JSON validation" in str(e) for e in errors)
        assert not any("Required fields" in str(e) for e in errors)
        assert not any("Data types" in str(e) for e in errors)
