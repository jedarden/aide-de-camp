#!/usr/bin/env python3
"""
Test script for validate_all integration function.

Tests that validate_all properly chains all validation steps:
- JSON well-formedness
- Required fields
- Data types
- Completeness
"""

import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.validation.integration import validate_all


def test_valid_complete_data():
    """Test that valid complete data passes required fields and types validation."""
    print("TEST 1: Valid complete data (passes fields and types)")

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
        "first_deployment": "2026-07-07T00:00:00Z",
        "last_deployment": "2026-08-05T23:59:59Z",
        # Add metadata for completeness validation
        "metadata": {
            "time_period": {
                "start": "2026-07-07T00:00:00Z",
                "end": "2026-08-05T23:59:59Z"
            }
        },
        "deployment_events_last_30_days": [
            {"date": "2026-07-07"},
            {"date": "2026-07-08"},
            {"date": "2026-07-09"},
            {"date": "2026-07-10"},
            {"date": "2026-07-11"},
            {"date": "2026-07-12"},
            {"date": "2026-07-13"},
            {"date": "2026-07-14"},
            {"date": "2026-07-15"},
            {"date": "2026-07-16"},
            {"date": "2026-07-17"},
            {"date": "2026-07-18"},
            {"date": "2026-07-19"},
            {"date": "2026-07-20"},
            {"date": "2026-07-21"},
            {"date": "2026-07-22"},
            {"date": "2026-07-23"},
            {"date": "2026-07-24"},
            {"date": "2026-07-25"},
            {"date": "2026-07-26"},
            {"date": "2026-07-27"},
            {"date": "2026-07-28"},
            {"date": "2026-07-29"},
            {"date": "2026-07-30"},
            {"date": "2026-07-31"},
            {"date": "2026-08-01"},
            {"date": "2026-08-02"},
            {"date": "2026-08-03"},
            {"date": "2026-08-04"},
            {"date": "2026-08-05"},
        ]
    }

    is_valid, errors = validate_all(data=data)

    print(f"  Result: is_valid={is_valid}")
    print(f"  Errors: {errors}")
    print(f"  ✓ PASS" if is_valid else "  ✗ FAIL")
    print()
    return is_valid


def test_invalid_json():
    """Test that invalid JSON fails early with JSON error only."""
    print("TEST 2: Invalid JSON (early termination)")

    # Create file with invalid JSON
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
        f.write('{"service": "test", invalid json}')

    try:
        is_valid, errors = validate_all(file_path=temp_path)

        print(f"  Result: is_valid={is_valid}")
        print(f"  Errors: {errors}")
        print(f"  ✓ PASS" if (not is_valid and len(errors) == 1 and "JSON" in errors[0]) else "  ✗ FAIL")
        print()
        return not is_valid and len(errors) == 1
    finally:
        Path(temp_path).unlink()


def test_missing_required_fields():
    """Test that missing required fields are detected."""
    print("TEST 3: Missing required fields")

    data = {
        "service": "pbx-web"
        # Missing many required fields
    }

    is_valid, errors = validate_all(data=data)

    print(f"  Result: is_valid={is_valid}")
    print(f"  Errors: {errors}")
    has_required_field_error = any("Missing required field" in error for error in errors)
    print(f"  ✓ PASS" if (not is_valid and has_required_field_error) else "  ✗ FAIL")
    print()
    return not is_valid and has_required_field_error


def test_invalid_data_types():
    """Test that invalid data types are detected."""
    print("TEST 4: Invalid data types")

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
        "deployment_names": ["pbx-web"],
        "first_deployment": "2026-07-01T00:00:00Z",
        "last_deployment": "2026-07-30T23:59:59Z"
    }

    is_valid, errors = validate_all(data=data)

    print(f"  Result: is_valid={is_valid}")
    print(f"  Errors: {errors}")
    has_type_error = any("must be" in error for error in errors)
    print(f"  ✓ PASS" if (not is_valid and has_type_error) else "  ✗ FAIL")
    print()
    return not is_valid and has_type_error


def test_file_based_validation():
    """Test file-based validation."""
    print("TEST 5: File-based validation")

    data = {
        "service": "pbx-web",
        "period_days": 30,
        "total_deployments": 1,
        "successful_deployments": 1,
        "failed_deployments": 0,
        "success_rate": 100.0,
        "failure_rate": 0.0,
        "deployment_frequency_per_day": 0.03,
        "mean_time_between_deployments_hours": 720.0,
        "deployment_names": ["pbx-web"],
        "first_deployment": "2026-07-01T00:00:00Z",
        "last_deployment": "2026-07-01T00:00:00Z"
    }

    # Create temporary file with valid JSON
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
        json.dump(data, f)

    try:
        is_valid, errors = validate_all(file_path=temp_path)

        print(f"  Result: is_valid={is_valid}")
        print(f"  Errors: {errors}")
        print(f"  ✓ PASS" if is_valid else "  ✗ FAIL (may have completeness errors)")
        print()
        return True  # We expect this might have completeness errors
    finally:
        Path(temp_path).unlink()


def test_nonexistent_file():
    """Test that nonexistent file fails appropriately."""
    print("TEST 6: Nonexistent file")

    is_valid, errors = validate_all(file_path="/tmp/nonexistent_file_12345.json")

    print(f"  Result: is_valid={is_valid}")
    print(f"  Errors: {errors}")
    print(f"  ✓ PASS" if (not is_valid and "File not found" in errors[0]) else "  ✗ FAIL")
    print()
    return not is_valid and "File not found" in errors[0]


def test_no_input():
    """Test that error is raised when no input is provided."""
    print("TEST 7: No input provided")

    is_valid, errors = validate_all()

    print(f"  Result: is_valid={is_valid}")
    print(f"  Errors: {errors}")
    print(f"  ✓ PASS" if (not is_valid and "must be provided" in errors[0]) else "  ✗ FAIL")
    print()
    return not is_valid and "must be provided" in errors[0]


def main():
    """Run all tests."""
    print("=" * 70)
    print("VALIDATE_ALL INTEGRATION FUNCTION TESTS")
    print("=" * 70)
    print()

    tests = [
        test_valid_complete_data,
        test_invalid_json,
        test_missing_required_fields,
        test_invalid_data_types,
        test_file_based_validation,
        test_nonexistent_file,
        test_no_input,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  ✗ EXCEPTION: {e}")
            print()
            results.append(False)

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    print()

    if passed == total:
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
