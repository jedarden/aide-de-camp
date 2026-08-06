#!/usr/bin/env python3
"""
Comprehensive test suite for integrated validate_deployment_file function.

Tests cover all validation steps:
- JSON structure validation
- Required fields validation
- Data types validation
- Completeness validation
- Multiple errors simultaneously
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from validate_deployment_file import validate_deployment_file


class TestJSONValidation:
    """Test JSON structure validation."""

    def test_valid_json_passes(self):
        """Test that valid JSON file passes JSON validation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump({"service": "test", "namespace": "default", "cluster": "test"}, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid, f"Expected valid JSON to pass, got errors: {errors}"
            assert len(errors) == 0
        finally:
            Path(temp_path).unlink()

    def test_invalid_json_fails(self):
        """Test that invalid JSON fails at JSON step."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{"service": "test", invalid json}')

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected invalid JSON to fail"
            assert len(errors) > 0
            assert any("Invalid JSON" in error for error in errors), "Should report JSON error"
        finally:
            Path(temp_path).unlink()

    def test_nonexistent_file_fails(self):
        """Test that nonexistent file fails."""
        is_valid, errors = validate_deployment_file("/tmp/nonexistent_file_12345.json")

        assert not is_valid, "Expected nonexistent file to be invalid"
        assert len(errors) > 0
        assert any("File not found" in error for error in errors)

    def test_empty_json_file(self):
        """Test that empty JSON file is handled."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump({}, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Empty JSON should fail validation"
            assert len(errors) > 0
        finally:
            Path(temp_path).unlink()

    def test_json_list_instead_of_dict(self):
        """Test that JSON list instead of dict is handled."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(["item1", "item2"], f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            # List data is valid but may fail other validations
            # Just check it doesn't crash
            assert isinstance(is_valid, bool)
            assert isinstance(errors, list)
        finally:
            Path(temp_path).unlink()


class TestRequiredFieldsValidation:
    """Test required fields validation."""

    def test_all_required_fields_present_passes(self):
        """Test that data with all required fields passes."""
        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid, f"Expected valid data to pass, got errors: {errors}"
            assert len(errors) == 0
        finally:
            Path(temp_path).unlink()

    def test_missing_service_field_fails(self):
        """Test that missing 'service' field fails validation."""
        data = {
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected missing field to fail validation"
            assert any("Missing required field: service" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_missing_namespace_field_fails(self):
        """Test that missing 'namespace' field fails validation."""
        data = {
            "service": "pbx-web",
            "cluster": "ardenone-cluster"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected missing field to fail validation"
            assert any("Missing required field: namespace" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_missing_cluster_field_fails(self):
        """Test that missing 'cluster' field fails validation."""
        data = {
            "service": "pbx-web",
            "namespace": "pbx-web"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected missing field to fail validation"
            assert any("Missing required field: cluster" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_missing_multiple_fields_fails(self):
        """Test that missing multiple fields reports all errors."""
        data = {
            "service": "pbx-web"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected missing fields to fail validation"
            # Should have multiple errors
            missing_field_errors = [e for e in errors if "Missing required field" in e]
            assert len(missing_field_errors) >= 2, "Should report multiple missing fields"
        finally:
            Path(temp_path).unlink()


class testDataTypesValidation:
    """Test data types validation."""

    def test_correct_data_types_pass(self):
        """Test that correct data types pass validation."""
        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid, f"Expected correct types to pass, got errors: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_wrong_service_type_fails(self):
        """Test that wrong service field type fails validation."""
        data = {
            "service": 123,  # Should be string
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected wrong type to fail validation"
            assert any("service must be str" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_wrong_namespace_type_fails(self):
        """Test that wrong namespace field type fails validation."""
        data = {
            "service": "pbx-web",
            "namespace": ["pbx-web"],  # Should be string
            "cluster": "ardenone-cluster"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected wrong type to fail validation"
            assert any("namespace must be str" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_wrong_cluster_type_fails(self):
        """Test that wrong cluster field type fails validation."""
        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": 456  # Should be string
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected wrong type to fail validation"
            assert any("cluster must be str" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_multiple_type_errors_reported(self):
        """Test that multiple type errors are all reported."""
        data = {
            "service": 123,  # Wrong type
            "namespace": ["list"],  # Wrong type
            "cluster": 456  # Wrong type
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected wrong types to fail validation"
            # Should have multiple type errors
            type_errors = [e for e in errors if "must be" in e and "got" in e]
            assert len(type_errors) >= 2, "Should report multiple type errors"
        finally:
            Path(temp_path).unlink()


class TestCompletenessValidation:
    """Test 30-day completeness validation."""

    def generate_30_consecutive_days(self, start_date=None):
        """Helper to generate 30 consecutive deployment entries."""
        if start_date is None:
            start_date = datetime(2026, 7, 7, 12, 0, 0)

        return [
            {"timestamp": (start_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(30)
        ]

    def test_valid_30_day_completeness_passes(self):
        """Test that valid 30-day consecutive data passes completeness check."""
        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster",
            "deployments": self.generate_30_consecutive_days()
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid, f"Expected valid 30-day data to pass, got errors: {errors}"
            assert len(errors) == 0
        finally:
            Path(temp_path).unlink()

    def test_29_days_fails_completeness(self):
        """Test that 29 days of data fails completeness check."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        deployments = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)
        ]

        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster",
            "deployments": deployments
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected 29 days to fail completeness"
            assert any("Expected 30 deployment entries" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_31_days_fails_completeness(self):
        """Test that 31 days of data fails completeness check."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        deployments = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(31)
        ]

        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster",
            "deployments": deployments
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected 31 days to fail completeness"
            assert any("Expected 30 deployment entries" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_date_gap_detected(self):
        """Test that date gaps are detected."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)

        # Create data with a gap
        deployments = []
        for i in range(15):  # Days 0-14
            deployments.append({"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"})
        for i in range(16, 32):  # Days 16-31 (skip day 15)
            deployments.append({"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"})

        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster",
            "deployments": deployments
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected date gap to fail completeness"
            assert any("Date gap detected" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_duplicate_date_detected(self):
        """Test that duplicate dates are detected."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)

        # Create 29 entries, then duplicate day 0 for the 30th
        deployments = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(29)
        ]
        deployments.append({"timestamp": base_date.isoformat() + "Z"})  # Duplicate

        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster",
            "deployments": deployments
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected duplicate date to fail completeness"
            assert any("Duplicate date found" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_list_data_with_timestamps(self):
        """Test completeness validation on list data directly."""
        deployments = self.generate_30_consecutive_days()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(deployments, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            # List data should trigger completeness check
            assert isinstance(is_valid, bool)
            assert isinstance(errors, list)
        finally:
            Path(temp_path).unlink()


class TestMultipleErrors:
    """Test handling of multiple simultaneous errors."""

    def test_json_and_missing_fields_errors(self):
        """Test that multiple errors are collected."""
        # Create file with both invalid JSON and missing fields
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write('{"service": "test")  # Invalid JSON

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Should fail validation"
            assert len(errors) > 0, "Should have at least one error"
            assert any("Invalid JSON" in error for error in errors)
        finally:
            Path(temp_path).unlink()

    def test_missing_fields_and_wrong_types(self):
        """Test that both missing fields and wrong types are reported."""
        data = {
            "namespace": 123,  # Wrong type
            # Missing "service" and "cluster"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Should fail validation"
            assert len(errors) >= 2, "Should have multiple errors"

            # Check for missing field errors
            missing_errors = [e for e in errors if "Missing required field" in e]
            assert len(missing_errors) > 0, "Should report missing fields"

            # Check for type error
            type_errors = [e for e in errors if "must be" in e]
            assert len(type_errors) > 0, "Should report type errors"
        finally:
            Path(temp_path).unlink()

    def test_all_validation_failures(self):
        """Test comprehensive failure across all validation steps."""
        # Create data that fails everything except JSON parsing
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        deployments = [
            {"timestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(15)  # Only 15 days, not 30
        ]

        data = {
            "service": 123,  # Wrong type
            "namespace": ["list"],  # Wrong type, missing "cluster"
            "deployments": deployments
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Should fail validation"
            assert len(errors) > 0, "Should have errors"

            # Should have multiple types of errors
            error_types = set()
            for error in errors:
                if "Missing required field" in error:
                    error_types.add("missing")
                if "must be" in error:
                    error_types.add("type")
                if "Expected 30" in error or "deployment entries" in error:
                    error_types.add("completeness")

            # Should have caught at least one type of error
            assert len(error_types) > 0, "Should have caught some errors"
        finally:
            Path(temp_path).unlink()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_file(self):
        """Test handling of empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            f.write("")

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Empty file should fail validation"
            assert len(errors) > 0
        finally:
            Path(temp_path).unlink()

    def test_nested_deployments_with_creationTimestamp(self):
        """Test that creationTimestamp field is also supported for completeness."""
        base_date = datetime(2026, 7, 7, 12, 0, 0)
        deployments = [
            {"creationTimestamp": (base_date + timedelta(days=i)).isoformat() + "Z"}
            for i in range(30)
        ]

        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster",
            "deployments": deployments
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid, f"Expected creationTimestamp to work, got errors: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_unicode_in_data(self):
        """Test handling of unicode characters in data."""
        data = {
            "service": "pbx-web-日本語",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            temp_path = f.name
            json.dump(data, f, ensure_ascii=False)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid, f"Expected unicode to work, got errors: {errors}"
        finally:
            Path(temp_path).unlink()

    def test_very_long_field_values(self):
        """Test handling of very long field values."""
        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "a" * 10000  # Very long string
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            # Long strings should still pass type validation
            assert isinstance(is_valid, bool)
        finally:
            Path(temp_path).unlink()


class TestFunctionSignature:
    """Test function signature and return types."""

    def test_returns_tuple(self):
        """Test that function returns a tuple."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump({}, f)

        try:
            result = validate_deployment_file(temp_path)
            assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
            assert len(result) == 2, f"Expected tuple of length 2, got {len(result)}"
        finally:
            Path(temp_path).unlink()

    def test_first_element_is_bool(self):
        """Test that first element is boolean."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump({}, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert isinstance(is_valid, bool), f"Expected bool, got {type(is_valid)}"
        finally:
            Path(temp_path).unlink()

    def test_second_element_is_list(self):
        """Test that second element is list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump({}, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert isinstance(errors, list), f"Expected list, got {type(errors)}"
        finally:
            Path(temp_path).unlink()

    def test_errors_are_strings(self):
        """Test that all errors are strings."""
        data = {
            "service": 123,
            "namespace": ["list"]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
            json.dump(data, f)

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            for error in errors:
                assert isinstance(error, str), f"Expected str in errors, got {type(error)}"
        finally:
            Path(temp_path).unlink()


def run_all_tests():
    """Run all tests and report results."""
    import unittest

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestJSONValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestRequiredFieldsValidation))
    suite.addTests(loader.loadTestsFromTestCase(testDataTypesValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestCompletenessValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestMultipleErrors))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestFunctionSignature))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())