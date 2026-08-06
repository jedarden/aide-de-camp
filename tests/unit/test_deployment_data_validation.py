#!/usr/bin/env python3
"""
Unit tests for deployment data validation functions.

Tests cover field presence, data type validation, and edge cases
for deployment data structures.
"""

import pytest
from src.validation.deployment_data import (
    validate_deployment_data,
    validate_deployment_data_simple,
    validate_deployment_record,
    validate_timestamp,
    validate_required_fields,
    validate_data_types,
    DEPLOYMENT_DATA_SCHEMA
)


class TestTimestampValidation:
    """Test ISO 8601 timestamp validation."""

    def test_valid_timestamp_with_z(self):
        """Test valid timestamp with Z suffix."""
        assert validate_timestamp("2026-08-06T12:00:00Z") is True

    def test_valid_timestamp_with_offset(self):
        """Test valid timestamp with timezone offset."""
        assert validate_timestamp("2026-08-06T12:00:00+00:00") is True

    def test_valid_timestamp_without_offset(self):
        """Test valid timestamp without timezone."""
        assert validate_timestamp("2026-08-06T12:00:00") is True

    def test_invalid_timestamp_format(self):
        """Test invalid timestamp format."""
        assert validate_timestamp("not-a-timestamp") is False
        assert validate_timestamp("2026-13-01") is False  # Invalid month
        assert validate_timestamp("") is False

    def test_empty_string_timestamp(self):
        """Test empty string timestamp."""
        assert validate_timestamp("") is False

    def test_none_timestamp(self):
        """Test None timestamp."""
        assert validate_timestamp(None) is False


class TestSchemaCompleteness:
    """Verify schema completeness and structure."""

    def test_all_required_fields_documented(self):
        """Ensure DEPLOYMENT_DATA_SCHEMA contains all expected fields."""
        required_fields = [
            "service", "period_days", "total_deployments",
            "successful_deployments", "failed_deployments",
            "success_rate", "failure_rate",
            "deployment_frequency_per_day",
            "mean_time_between_deployments_hours",
            "deployment_names", "first_deployment", "last_deployment"
        ]
        for field in required_fields:
            assert field in DEPLOYMENT_DATA_SCHEMA, f"Missing field in schema: {field}"


class TestFieldPresenceValidation:
    """Test validation of required field presence."""

    def test_all_required_fields_present_passes(self):
        """Test that valid data with all required fields passes."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z"
        }
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True
        assert error is None

    def test_missing_service_field_fails(self):
        """Test that missing 'service' field fails validation."""
        data = {
            "period_days": 30,
            "total_deployments": 10,
            # Missing 'service' and other required fields
        }
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "Missing required fields" in error
        assert "service" in error

    def test_missing_multiple_fields_fails(self):
        """Test that missing multiple required fields fails validation."""
        data = {"service": "test"}  # Only one field present
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "Missing required fields" in error
        # Should list multiple missing fields
        missing_count = error.count(",") + 1
        assert missing_count >= 10  # At least 10 fields missing

    def test_missing_total_deployments_fails(self):
        """Test that missing 'total_deployments' field fails."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            # Missing total_deployments
            "successful_deployments": 8,
            "failed_deployments": 2
        }
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "total_deployments" in error

    def test_non_dict_input_fails(self):
        """Test that non-dictionary input fails."""
        is_valid, error = validate_deployment_record("not a dict")
        assert is_valid is False
        assert "must be a dictionary" in error

    def test_list_input_fails(self):
        """Test that list input fails."""
        is_valid, error = validate_deployment_record([])
        assert is_valid is False
        assert "must be a dictionary" in error


class TestDataTypeValidation:
    """Test validation of data types for deployment fields."""

    def get_valid_data(self):
        """Helper function to get valid deployment data."""
        return {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z"
        }

    def test_service_field_string_passes(self):
        """Test that service field as string passes."""
        data = self.get_valid_data()
        assert isinstance(data["service"], str)
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_service_field_not_string_fails(self):
        """Test that service field as non-string fails."""
        data = self.get_valid_data()
        data["service"] = 123  # Should be string
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "service must be str" in error

    def test_integer_fields_int_passes(self):
        """Test that integer fields as int pass."""
        data = self.get_valid_data()
        for field in ["period_days", "total_deployments", "successful_deployments", "failed_deployments"]:
            assert isinstance(data[field], int), f"{field} should be int"
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_integer_fields_string_fails(self):
        """Test that integer fields as string fail."""
        data = self.get_valid_data()
        data["total_deployments"] = "10"  # Should be int
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "total_deployments must be int" in error

    def test_float_fields_float_passes(self):
        """Test that float fields as float pass."""
        data = self.get_valid_data()
        for field in ["success_rate", "failure_rate", "deployment_frequency_per_day"]:
            assert isinstance(data[field], (int, float)), f"{field} should be numeric"
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_float_fields_string_fails(self):
        """Test that float fields as string fail."""
        data = self.get_valid_data()
        data["success_rate"] = "80.0"  # Should be numeric
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "success_rate must be numeric" in error

    def test_float_fields_accept_int(self):
        """Test that float fields accept int values."""
        data = self.get_valid_data()
        data["success_rate"] = 80  # int is acceptable for float field
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_deployment_names_list_passes(self):
        """Test that deployment_names as list passes."""
        data = self.get_valid_data()
        assert isinstance(data["deployment_names"], list)
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_deployment_names_not_list_fails(self):
        """Test that deployment_names as non-list fails."""
        data = self.get_valid_data()
        data["deployment_names"] = "pbx-web"  # Should be list
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "deployment_names must be a list" in error

    def test_deployment_names_dict_fails(self):
        """Test that deployment_names as dict fails."""
        data = self.get_valid_data()
        data["deployment_names"] = {"name": "pbx-web"}  # Should be list
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "deployment_names must be a list" in error

    def test_timestamp_fields_string_passes(self):
        """Test that timestamp fields as valid string pass."""
        data = self.get_valid_data()
        for field in ["first_deployment", "last_deployment"]:
            assert isinstance(data[field], str)
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_timestamp_fields_invalid_format_fails(self):
        """Test that invalid timestamp format fails."""
        data = self.get_valid_data()
        data["first_deployment"] = "invalid-timestamp"
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "first_deployment contains invalid timestamp" in error


class TestBusinessConstraints:
    """Test validation of business logic constraints."""

    def get_valid_data(self):
        """Helper function to get valid deployment data."""
        return {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z"
        }

    def test_successful_plus_failed_equals_total_passes(self):
        """Test that successful + failed = total passes."""
        data = self.get_valid_data()
        assert data["successful_deployments"] + data["failed_deployments"] == data["total_deployments"]
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_successful_plus_failed_not_equals_total_fails(self):
        """Test that successful + failed != total fails."""
        data = self.get_valid_data()
        data["successful_deployments"] = 5  # 5 + 2 != 10
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "must equal total_deployments" in error

    def test_success_rate_plus_failure_rate_equals_100_passes(self):
        """Test that success_rate + failure_rate = 100 passes."""
        data = self.get_valid_data()
        assert abs(data["success_rate"] + data["failure_rate"] - 100.0) < 0.1
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_success_rate_plus_failure_rate_not_100_fails(self):
        """Test that success_rate + failure_rate != 100 fails."""
        data = self.get_valid_data()
        data["success_rate"] = 75.0  # 75 + 20 != 100
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "should equal 100.0" in error

    def test_small_floating_point_error_allowed(self):
        """Test that small floating point errors are allowed."""
        data = self.get_valid_data()
        data["success_rate"] = 80.0001
        data["failure_rate"] = 19.9999
        # Sum is 100.0 within tolerance
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_negative_period_days_fails(self):
        """Test that negative period_days fails."""
        data = self.get_valid_data()
        data["period_days"] = -1
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "period_days must be non-negative" in error

    def test_negative_total_deployments_fails(self):
        """Test that negative total_deployments fails."""
        data = self.get_valid_data()
        data["total_deployments"] = -1
        data["successful_deployments"] = 0  # Need to adjust to avoid sum error
        data["failed_deployments"] = 0  # Need to adjust to avoid sum error
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "total_deployments must be non-negative" in error

    def test_negative_deployment_frequency_fails(self):
        """Test that negative deployment_frequency_per_day fails."""
        data = self.get_valid_data()
        data["deployment_frequency_per_day"] = -1.0
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        assert "deployment_frequency_per_day must be non-negative" in error


class TestMainValidationFunction:
    """Test the main validate_deployment_data function."""

    def get_valid_record(self):
        """Helper function to get valid deployment record."""
        return {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z"
        }

    def test_single_valid_record_passes(self):
        """Test validation of single valid deployment record."""
        data = self.get_valid_record()
        is_valid, error = validate_deployment_data(data)
        assert is_valid is True
        assert error is None

    def test_single_invalid_record_fails(self):
        """Test validation of single invalid deployment record."""
        data = {"service": "test"}  # Missing required fields
        is_valid, error = validate_deployment_data(data)
        assert is_valid is False
        assert error is not None

    def test_services_collection_valid_passes(self):
        """Test validation of valid services collection."""
        data = {
            "services": {
                "pbx-web": self.get_valid_record(),
                "whisper-stt": self.get_valid_record()
            }
        }
        is_valid, error = validate_deployment_data(data)
        assert is_valid is True
        assert error is None

    def test_services_collection_invalid_fails(self):
        """Test validation of invalid services collection."""
        data = {
            "services": {
                "pbx-web": {"service": "test"}  # Invalid record
            }
        }
        is_valid, error = validate_deployment_data(data)
        assert is_valid is False
        assert error is not None
        assert "pbx-web" in error

    def test_services_collection_not_dict_fails(self):
        """Test that services collection as non-dict fails."""
        data = {
            "services": ["not", "a", "dict"]
        }
        is_valid, error = validate_deployment_data(data)
        assert is_valid is False
        assert "must be a dictionary" in error

    def test_non_dict_input_fails(self):
        """Test that non-dict input fails."""
        is_valid, error = validate_deployment_data("not a dict")
        assert is_valid is False
        assert "must be a dictionary" in error


class TestSimpleValidationFunction:
    """Test the validate_deployment_data_simple function."""

    def test_valid_data_returns_true(self):
        """Test that valid data returns True."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z"
        }
        result = validate_deployment_data_simple(data)
        assert result is True

    def test_invalid_data_returns_false(self):
        """Test that invalid data returns False."""
        data = {"service": "test"}  # Missing required fields
        result = validate_deployment_data_simple(data)
        assert result is False

    def test_missing_service_field_returns_false(self):
        """Test that missing service field returns False."""
        data = {
            "period_days": 30,
            "total_deployments": 10
        }
        result = validate_deployment_data_simple(data)
        assert result is False

    def test_wrong_types_returns_false(self):
        """Test that wrong data types return False."""
        data = {
            "service": "pbx-web",
            "period_days": "30",  # Should be int
            "total_deployments": "10",  # Should be int
        }
        result = validate_deployment_data_simple(data)
        assert result is False

    def test_non_dict_input_returns_false(self):
        """Test that non-dict input returns False."""
        result = validate_deployment_data_simple("not a dict")
        assert result is False

    def test_services_collection_valid_returns_true(self):
        """Test that valid services collection returns True."""
        data = {
            "services": {
                "pbx-web": {
                    "service": "pbx-web",
                    "period_days": 30,
                    "total_deployments": 10,
                    "successful_deployments": 8,
                    "failed_deployments": 2,
                    "success_rate": 80.0,
                    "failure_rate": 20.0,
                    "deployment_frequency_per_day": 0.33,
                    "mean_time_between_deployments_hours": 72.0,
                    "deployment_names": ["pbx-web"],
                    "first_deployment": "2026-07-01T00:00:00Z",
                    "last_deployment": "2026-07-30T23:59:59Z"
                }
            }
        }
        result = validate_deployment_data_simple(data)
        assert result is True


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_deployments_valid(self):
        """Test that zero deployments is valid."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 0,
            "successful_deployments": 0,
            "failed_deployments": 0,
            "success_rate": 0.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.0,
            "mean_time_between_deployments_hours": 0.0,
            "deployment_names": [],
            "first_deployment": "",
            "last_deployment": ""
        }
        # Empty timestamps are invalid, so this should fail
        is_valid, error = validate_deployment_record(data)
        assert is_valid is False
        # Empty timestamps should be caught as timestamp validation errors
        assert "invalid timestamp" in error

    def test_very_large_values_valid(self):
        """Test that very large numeric values are valid."""
        data = {
            "service": "pbx-web",
            "period_days": 365,
            "total_deployments": 1000000,
            "successful_deployments": 999999,
            "failed_deployments": 1,
            "success_rate": 99.9999,
            "failure_rate": 0.0001,
            "deployment_frequency_per_day": 1000.0,
            "mean_time_between_deployments_hours": 0.024,
            "deployment_names": ["pbx-web"] * 1000,
            "first_deployment": "2025-01-01T00:00:00Z",
            "last_deployment": "2026-12-31T23:59:59Z"
        }
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_leap_year_timestamp_valid(self):
        """Test that leap year timestamp is valid."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 1,
            "successful_deployments": 1,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.033,
            "mean_time_between_deployments_hours": 720.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2024-02-29T12:00:00Z",  # Leap year
            "last_deployment": "2024-03-30T12:00:00Z"
        }
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_empty_deployment_names_list_valid(self):
        """Test that empty deployment_names list is valid."""
        data = {
            "service": "pbx-web",
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
            "last_deployment": "2026-07-30T23:59:59Z"
        }
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True  # Empty list is still a list

    def test_extra_fields_ignored(self):
        """Test that extra fields not in schema are ignored."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "extra_field": "should be ignored",
            "another_extra": 12345
        }
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True  # Extra fields don't affect validation


class TestRealWorldData:
    """Test with realistic deployment data structures."""

    def test_whisper_stt_realistic_data(self):
        """Test validation with realistic whisper-stt data."""
        data = {
            "service": "whisper-stt",
            "period_days": 30,
            "total_deployments": 4,
            "successful_deployments": 1,
            "failed_deployments": 3,
            "success_rate": 25.0,
            "failure_rate": 75.0,
            "deployment_frequency_per_day": 0.133,
            "mean_time_between_deployments_hours": 168.0,
            "deployment_names": ["whisper-stt"],
            "first_deployment": "2026-07-08T03:26:44Z",
            "last_deployment": "2026-07-12T16:54:57Z"
        }
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_pbx_web_realistic_data(self):
        """Test validation with realistic pbx-web data."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 12,
            "successful_deployments": 11,
            "failed_deployments": 1,
            "success_rate": 91.67,
            "failure_rate": 8.33,
            "deployment_frequency_per_day": 0.4,
            "mean_time_between_deployments_hours": 60.0,
            "deployment_names": ["pbx-web", "pbx-web-v2"],
            "first_deployment": "2026-07-01T10:15:00Z",
            "last_deployment": "2026-07-30T18:45:00Z"
        }
        is_valid, error = validate_deployment_record(data)
        assert is_valid is True

    def test_multi_service_collection(self):
        """Test validation with multiple services in collection."""
        data = {
            "services": {
                "pbx-web": {
                    "service": "pbx-web",
                    "period_days": 30,
                    "total_deployments": 12,
                    "successful_deployments": 11,
                    "failed_deployments": 1,
                    "success_rate": 91.67,
                    "failure_rate": 8.33,
                    "deployment_frequency_per_day": 0.4,
                    "mean_time_between_deployments_hours": 60.0,
                    "deployment_names": ["pbx-web"],
                    "first_deployment": "2026-07-01T10:15:00Z",
                    "last_deployment": "2026-07-30T18:45:00Z"
                },
                "whisper-stt": {
                    "service": "whisper-stt",
                    "period_days": 30,
                    "total_deployments": 4,
                    "successful_deployments": 1,
                    "failed_deployments": 3,
                    "success_rate": 25.0,
                    "failure_rate": 75.0,
                    "deployment_frequency_per_day": 0.133,
                    "mean_time_between_deployments_hours": 168.0,
                    "deployment_names": ["whisper-stt"],
                    "first_deployment": "2026-07-08T03:26:44Z",
                    "last_deployment": "2026-07-12T16:54:57Z"
                }
            }
        }
        is_valid, error = validate_deployment_data(data)
        assert is_valid is True
        assert error is None


class TestValidateRequiredFields:
    """Test the validate_required_fields function specifically."""

    def test_all_required_fields_present_returns_true_empty_string(self):
        """Test that data with all required fields returns (True, '')."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z"
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is True
        assert error == ""

    def test_missing_single_field_returns_false_with_error(self):
        """Test that missing a single required field returns (False, error_message)."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z"
            # Missing: last_deployment
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is False
        assert "Missing required field" in error
        assert "last_deployment" in error
        assert error != ""

    def test_missing_multiple_fields_returns_false_with_clear_error(self):
        """Test that missing multiple fields returns clear error listing all missing."""
        data = {
            "service": "pbx-web"
            # Missing: all other required fields
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is False
        assert "Missing required fields" in error
        assert error != ""
        # Should list multiple missing fields
        missing_count = error.count(",") + 1
        assert missing_count >= 10  # At least 10 fields missing

    def test_missing_service_field_specific_error(self):
        """Test that missing 'service' field gives specific error."""
        data = {
            "period_days": 30,
            "total_deployments": 10
            # Missing: service and other fields
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is False
        assert "service" in error.lower()

    def test_non_dict_input_returns_type_error(self):
        """Test that non-dictionary input returns type error."""
        is_valid, error = validate_required_fields("not a dict")
        assert is_valid is False
        assert "must be a dictionary" in error
        assert error != ""

    def test_list_input_returns_type_error(self):
        """Test that list input returns type error."""
        is_valid, error = validate_required_fields([])
        assert is_valid is False
        assert "must be a dictionary" in error

    def test_none_input_returns_type_error(self):
        """Test that None input returns type error."""
        is_valid, error = validate_required_fields(None)
        assert is_valid is False
        assert "must be a dictionary" in error

    def test_services_collection_valid_returns_true_empty_string(self):
        """Test that valid services collection returns (True, '')."""
        data = {
            "services": {
                "pbx-web": {
                    "service": "pbx-web",
                    "period_days": 30,
                    "total_deployments": 10,
                    "successful_deployments": 8,
                    "failed_deployments": 2,
                    "success_rate": 80.0,
                    "failure_rate": 20.0,
                    "deployment_frequency_per_day": 0.33,
                    "mean_time_between_deployments_hours": 72.0,
                    "deployment_names": ["pbx-web"],
                    "first_deployment": "2026-07-01T00:00:00Z",
                    "last_deployment": "2026-07-30T23:59:59Z"
                },
                "whisper-stt": {
                    "service": "whisper-stt",
                    "period_days": 30,
                    "total_deployments": 4,
                    "successful_deployments": 1,
                    "failed_deployments": 3,
                    "success_rate": 25.0,
                    "failure_rate": 75.0,
                    "deployment_frequency_per_day": 0.133,
                    "mean_time_between_deployments_hours": 168.0,
                    "deployment_names": ["whisper-stt"],
                    "first_deployment": "2026-07-08T03:26:44Z",
                    "last_deployment": "2026-07-12T16:54:57Z"
                }
            }
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is True
        assert error == ""

    def test_services_collection_missing_field_returns_error_with_service_name(self):
        """Test that services collection with missing field returns error with service context."""
        data = {
            "services": {
                "pbx-web": {
                    "service": "pbx-web"
                    # Missing all other required fields
                }
            }
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is False
        assert "pbx-web" in error  # Service name should be in error
        assert "Missing required fields" in error

    def test_services_collection_not_dict_returns_error(self):
        """Test that services collection as non-dict returns error."""
        data = {
            "services": ["not", "a", "dict"]
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is False
        assert "must be a dictionary" in error

    def test_empty_dict_returns_false_with_missing_fields_error(self):
        """Test that empty dictionary returns False with missing fields error."""
        is_valid, error = validate_required_fields({})
        assert is_valid is False
        assert "Missing required fields" in error
        assert error != ""

    def test_extra_fields_do_not_affect_validation(self):
        """Test that extra fields not in schema are ignored."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "extra_field": "should be ignored",
            "another_extra": 12345,
            "yet_another": ["extra", "data"]
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is True
        assert error == ""

    def test_incorrect_data_types_still_pass_field_presence_check(self):
        """Test that incorrect data types pass field presence check (only checks presence)."""
        data = {
            "service": "pbx-web",
            "period_days": "30",  # Should be int, but field presence check passes
            "total_deployments": "10",  # Should be int
            "successful_deployments": "8",  # Should be int
            "failed_deployments": "2",  # Should be int
            "success_rate": "80.0",  # Should be float
            "failure_rate": "20.0",  # Should be float
            "deployment_frequency_per_day": "0.33",  # Should be float
            "mean_time_between_deployments_hours": "72.0",  # Should be float
            "deployment_names": "not-a-list",  # Should be list, but field exists
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z"
        }
        # Field presence check should pass (all fields exist)
        is_valid, error = validate_required_fields(data)
        assert is_valid is True
        assert error == ""

    def test_specific_field_error_messages_are_clear(self):
        """Test that specific missing field error messages are clear and actionable."""
        # Test missing service field specifically
        data = {
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z"
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is False
        assert "service" in error.lower()
        assert "missing" in error.lower()

    def test_realistic_pbx_web_data_passes(self):
        """Test with realistic pbx-web deployment data."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 12,
            "successful_deployments": 11,
            "failed_deployments": 1,
            "success_rate": 91.67,
            "failure_rate": 8.33,
            "deployment_frequency_per_day": 0.4,
            "mean_time_between_deployments_hours": 60.0,
            "deployment_names": ["pbx-web", "pbx-web-v2"],
            "first_deployment": "2026-07-01T10:15:00Z",
            "last_deployment": "2026-07-30T18:45:00Z"
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is True
        assert error == ""

    def test_realistic_whisper_stt_data_passes(self):
        """Test with realistic whisper-stt deployment data."""
        data = {
            "service": "whisper-stt",
            "period_days": 30,
            "total_deployments": 4,
            "successful_deployments": 1,
            "failed_deployments": 3,
            "success_rate": 25.0,
            "failure_rate": 75.0,
            "deployment_frequency_per_day": 0.133,
            "mean_time_between_deployments_hours": 168.0,
            "deployment_names": ["whisper-stt"],
            "first_deployment": "2026-07-08T03:26:44Z",
            "last_deployment": "2026-07-12T16:54:57Z"
        }
        is_valid, error = validate_required_fields(data)
        assert is_valid is True
        assert error == ""


class TestValidateDataTypes:
    """Test the validate_data_types function for type checking against schema."""

    def test_string_field_valid_type_passes(self):
        """Test that valid string type passes validation."""
        data = {"service": "pbx-web"}
        schema = {"service": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_string_field_invalid_type_fails(self):
        """Test that invalid string type fails validation."""
        data = {"service": 123}  # Should be string
        schema = {"service": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "service must be str" in error
        assert "int" in error

    def test_string_field_list_type_fails(self):
        """Test that string field as list fails validation."""
        data = {"service": ["pbx-web"]}  # Should be string
        schema = {"service": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "service must be str" in error
        assert "list" in error

    def test_integer_field_valid_int_passes(self):
        """Test that valid integer type passes validation."""
        data = {"total_deployments": 10}
        schema = {"total_deployments": int}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_integer_field_string_fails(self):
        """Test that integer field as string fails validation."""
        data = {"total_deployments": "10"}  # Should be int
        schema = {"total_deployments": int}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "total_deployments must be int" in error
        assert "str" in error

    def test_integer_field_float_fails(self):
        """Test that integer field as float fails validation."""
        data = {"total_deployments": 10.5}  # Should be int
        schema = {"total_deployments": int}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "total_deployments must be int" in error
        assert "float" in error

    def test_float_field_valid_float_passes(self):
        """Test that valid float type passes validation."""
        data = {"success_rate": 80.0}
        schema = {"success_rate": float}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_float_field_int_accepted_passes(self):
        """Test that float field accepts int values."""
        data = {"success_rate": 80}  # int is acceptable for float field
        schema = {"success_rate": float}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_float_field_string_fails(self):
        """Test that float field as string fails validation."""
        data = {"success_rate": "80.0"}  # Should be numeric
        schema = {"success_rate": float}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "success_rate must be numeric" in error
        assert "str" in error

    def test_list_field_valid_list_passes(self):
        """Test that valid list type passes validation."""
        data = {"deployment_names": ["pbx-web"]}
        schema = {"deployment_names": list}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_list_field_string_fails(self):
        """Test that list field as string fails validation."""
        data = {"deployment_names": "pbx-web"}  # Should be list
        schema = {"deployment_names": list}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "deployment_names must be a list" in error
        assert "str" in error

    def test_list_field_dict_fails(self):
        """Test that list field as dict fails validation."""
        data = {"deployment_names": {"name": "pbx-web"}}  # Should be list
        schema = {"deployment_names": list}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "deployment_names must be a list" in error
        assert "dict" in error

    def test_list_field_int_fails(self):
        """Test that list field as int fails validation."""
        data = {"deployment_names": 123}  # Should be list
        schema = {"deployment_names": list}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "deployment_names must be a list" in error
        assert "int" in error

    def test_date_field_valid_timestamp_passes(self):
        """Test that valid date/timestamp string passes validation."""
        data = {"first_deployment": "2026-07-01T00:00:00Z"}
        schema = {"first_deployment": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_date_field_invalid_format_fails(self):
        """Test that invalid date format fails validation."""
        data = {"first_deployment": "invalid-date"}
        schema = {"first_deployment": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "invalid date string" in error
        assert "first_deployment" in error

    def test_date_field_empty_string_passes(self):
        """Test that empty date string is accepted (valid string, just empty)."""
        data = {"first_deployment": ""}
        schema = {"first_deployment": str}
        is_valid, error = validate_data_types(data, schema)
        # Empty string is valid as a string type
        assert is_valid is True
        assert error == ""

    def test_date_field_with_offset_passes(self):
        """Test that date with timezone offset passes validation."""
        data = {"created_at": "2026-08-06T12:00:00+00:00"}
        schema = {"created_at": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_date_field_without_offset_passes(self):
        """Test that date without timezone passes validation."""
        data = {"updated_at": "2026-08-06T12:00:00"}
        schema = {"updated_at": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_multiple_field_types_all_valid_passes(self):
        """Test that multiple fields with correct types pass validation."""
        data = {
            "service": "pbx-web",
            "total_deployments": 10,
            "success_rate": 80.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z"
        }
        schema = {
            "service": str,
            "total_deployments": int,
            "success_rate": float,
            "deployment_names": list,
            "first_deployment": str
        }
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_multiple_field_types_one_invalid_fails(self):
        """Test that multiple field validation fails when one is invalid."""
        data = {
            "service": "pbx-web",
            "total_deployments": "10",  # Should be int
            "success_rate": 80.0,
            "deployment_names": ["pbx-web"]
        }
        schema = {
            "service": str,
            "total_deployments": int,
            "success_rate": float,
            "deployment_names": list
        }
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "total_deployments must be int" in error

    def test_multiple_field_types_multiple_invalid_fails(self):
        """Test that multiple field validation fails when multiple are invalid."""
        data = {
            "service": 123,  # Should be string
            "total_deployments": "10",  # Should be int
            "success_rate": 80.0,
            "deployment_names": "not-a-list"  # Should be list
        }
        schema = {
            "service": str,
            "total_deployments": int,
            "success_rate": float,
            "deployment_names": list
        }
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        # Should contain multiple error messages
        assert "service must be str" in error
        assert "total_deployments must be int" in error
        assert "deployment_names must be a list" in error

    def test_field_not_in_data_skipped(self):
        """Test that fields in schema but not in data are skipped."""
        data = {"service": "pbx-web"}
        schema = {"service": str, "total_deployments": int, "success_rate": float}
        is_valid, error = validate_data_types(data, schema)
        # Should pass because only 'service' is validated (others are not in data)
        assert is_valid is True
        assert error == ""

    def test_field_not_in_schema_ignored(self):
        """Test that fields in data but not in schema are ignored."""
        data = {
            "service": "pbx-web",
            "extra_field": "ignored",
            "another_extra": 12345
        }
        schema = {"service": str}
        is_valid, error = validate_data_types(data, schema)
        # Should pass because extra fields not in schema are ignored
        assert is_valid is True
        assert error == ""

    def test_non_dict_data_fails(self):
        """Test that non-dictionary data fails validation."""
        data = "not a dict"
        schema = {"service": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "Data must be a dictionary" in error

    def test_non_dict_schema_fails(self):
        """Test that non-dictionary schema fails validation."""
        data = {"service": "pbx-web"}
        schema = "not a dict"
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "Schema must be a dictionary" in error

    def test_none_data_fails(self):
        """Test that None data fails validation."""
        data = None
        schema = {"service": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "Data must be a dictionary" in error

    def test_empty_schema_passes(self):
        """Test that empty schema always passes."""
        data = {"service": "pbx-web", "total_deployments": 10}
        schema = {}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_empty_data_passes(self):
        """Test that empty data passes if schema fields are not present."""
        data = {}
        schema = {"service": str, "total_deployments": int}
        is_valid, error = validate_data_types(data, schema)
        # Should pass because fields are not in data (skipped)
        assert is_valid is True
        assert error == ""

    def test_full_deployment_schema_with_valid_data_passes(self):
        """Test full DEPLOYMENT_DATA_SCHEMA with valid deployment data."""
        data = {
            "service": "pbx-web",
            "period_days": 30,
            "total_deployments": 10,
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": 80.0,
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": ["pbx-web"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z"
        }
        is_valid, error = validate_data_types(data, DEPLOYMENT_DATA_SCHEMA)
        assert is_valid is True
        assert error == ""

    def test_full_deployment_schema_with_invalid_types_fails(self):
        """Test full DEPLOYMENT_DATA_SCHEMA with invalid types fails."""
        data = {
            "service": 123,  # Should be string
            "period_days": "30",  # Should be int
            "total_deployments": 10.5,  # Should be int
            "successful_deployments": 8,
            "failed_deployments": 2,
            "success_rate": "80.0",  # Should be float
            "failure_rate": 20.0,
            "deployment_frequency_per_day": 0.33,
            "mean_time_between_deployments_hours": 72.0,
            "deployment_names": "not-a-list",  # Should be list
            "first_deployment": "invalid-date",  # Should be valid timestamp
            "last_deployment": "2026-07-30T23:59:59Z"
        }
        is_valid, error = validate_data_types(data, DEPLOYMENT_DATA_SCHEMA)
        assert is_valid is False
        # Should contain multiple type errors
        assert "service must be str" in error
        assert "period_days must be int" in error
        assert "total_deployments must be int" in error
        assert "success_rate must be numeric" in error
        assert "deployment_names must be a list" in error
        assert "invalid date string" in error

    def test_numeric_fields_zero_value_passes(self):
        """Test that zero is valid for numeric fields."""
        data = {
            "total_deployments": 0,
            "success_rate": 0.0,
            "deployment_frequency_per_day": 0
        }
        schema = {
            "total_deployments": int,
            "success_rate": float,
            "deployment_frequency_per_day": float
        }
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_list_field_empty_list_passes(self):
        """Test that empty list is valid for list fields."""
        data = {"deployment_names": []}
        schema = {"deployment_names": list}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_string_field_empty_string_passes(self):
        """Test that empty string is valid for string fields."""
        data = {"service": ""}
        schema = {"service": str}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_negative_numbers_valid_for_types(self):
        """Test that negative numbers are valid for numeric types (type checking only)."""
        data = {
            "total_deployments": -10,
            "success_rate": -80.0
        }
        schema = {
            "total_deployments": int,
            "success_rate": float
        }
        is_valid, error = validate_data_types(data, schema)
        # Type validation should pass (negative numbers are still valid types)
        assert is_valid is True
        assert error == ""

    def test_timestamp_field_various_formats(self):
        """Test various valid timestamp formats."""
        valid_timestamps = [
            "2026-08-06T12:00:00Z",
            "2026-08-06T12:00:00+00:00",
            "2026-08-06T12:00:00",
            "2026-08-06T12:00:00.123Z",
            "2024-02-29T12:00:00Z"  # Leap year
        ]

        for timestamp in valid_timestamps:
            data = {"created_at": timestamp}
            schema = {"created_at": str}
            is_valid, error = validate_data_types(data, schema)
            assert is_valid is True, f"Timestamp {timestamp} should be valid: {error}"
            assert error == ""

    def test_boolean_field_type_validation(self):
        """Test that boolean type validation works correctly."""
        data = {"is_active": True}
        schema = {"is_active": bool}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is True
        assert error == ""

    def test_boolean_field_wrong_type_fails(self):
        """Test that boolean field with wrong type fails."""
        data = {"is_active": "true"}  # Should be bool
        schema = {"is_active": bool}
        is_valid, error = validate_data_types(data, schema)
        assert is_valid is False
        assert "is_active must be bool" in error
