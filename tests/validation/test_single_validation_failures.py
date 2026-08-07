#!/usr/bin/env python3
"""
Single-failure validation tests.

Tests each individual validation failure scenario in isolation:
- Test case 1: Invalid JSON syntax → fails at JSON validation step
- Test case 2: Missing required fields → fails at required fields check
- Test case 3: Wrong data types (e.g., string instead of int) → fails at data types check
- Test case 4: Incomplete data (missing expected values) → fails at completeness check

Each test expects (False, [relevant_errors])
"""

import sys
import tempfile
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.validation.integration import validate_all


def test_1_invalid_json_syntax():
    """
    Test case 1: Invalid JSON syntax → fails at JSON validation step.

    Creates a file with invalid JSON syntax and verifies that:
    - validate_all returns (False, [relevant_errors])
    - Error message indicates JSON parsing failure
    - No further validation is attempted (early termination)

    Expected: (False, [errors containing "JSON"])
    """
    print("TEST 1: Invalid JSON syntax → fails at JSON validation step")

    # Create file with invalid JSON
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
        f.write('{"service": "test", invalid json}')

    try:
        is_valid, errors = validate_all(file_path=temp_path)

        print(f"  Result: is_valid={is_valid}")
        print(f"  Errors: {errors}")

        # Explicit assertions for expected (False, [relevant_errors]) result
        assert is_valid == False, f"Expected is_valid=False, got {is_valid}"
        assert len(errors) > 0, "Expected at least one error"
        assert any("JSON" in error for error in errors), f"Expected JSON-related error, got {errors}"

        # Verify early termination (only JSON errors, no other validation errors)
        assert len(errors) == 1, f"Expected early termination with single JSON error, got {len(errors)} errors"

        print(f"  ✓ PASS - Invalid JSON correctly detected at JSON validation step")
        print(f"  ✓ PASS - Early termination prevents further validation")
        print()
        return True

    finally:
        Path(temp_path).unlink()


def test_2_missing_required_fields():
    """
    Test case 2: Missing required fields → fails at required fields check.

    Creates data with missing required fields and verifies that:
    - validate_all returns (False, [relevant_errors])
    - Error message indicates missing required fields
    - JSON validation passes (data is well-formed)
    - Required fields validation fails

    Expected: (False, [errors containing "Missing required field"])
    """
    print("TEST 2: Missing required fields → fails at required fields check")

    # Valid JSON but missing required fields
    data = {
        "service": "pbx-web"
        # Missing: period_days, total_deployments, successful_deployments,
        # failed_deployments, success_rate, failure_rate,
        # deployment_frequency_per_day, mean_time_between_deployments_hours,
        # deployment_names, first_deployment, last_deployment
    }

    is_valid, errors = validate_all(data=data)

    print(f"  Result: is_valid={is_valid}")
    print(f"  Errors: {errors}")

    # Explicit assertions for expected (False, [relevant_errors]) result
    assert is_valid == False, f"Expected is_valid=False, got {is_valid}"
    assert len(errors) > 0, "Expected at least one error"
    assert any("Missing required field" in error for error in errors), \
        f"Expected 'Missing required field' error, got {errors}"

    # Verify that JSON validation passed (no JSON errors)
    assert not any("JSON" in error for error in errors), \
        f"JSON validation should have passed, but got JSON error: {errors}"

    print(f"  ✓ PASS - Missing required fields correctly detected")
    print(f"  ✓ PASS - JSON validation passed (data is well-formed)")
    print()
    return True


def test_3_wrong_data_types():
    """
    Test case 3: Wrong data types (e.g., string instead of int) → fails at data types check.

    Creates data with incorrect data types and verifies that:
    - validate_all returns (False, [relevant_errors])
    - Error message indicates type mismatches
    - JSON validation passes (data is well-formed)
    - Required fields validation passes (all fields present)
    - Data types validation fails

    Expected: (False, [errors containing "must be" or "numeric"])
    """
    print("TEST 3: Wrong data types (e.g., string instead of int) → fails at data types check")

    # All required fields present, but with wrong types
    data = {
        "service": 123,  # Should be string, is int
        "period_days": "30",  # Should be int, is string
        "total_deployments": 10,
        "successful_deployments": 8,
        "failed_deployments": 2,
        "success_rate": 80.0,
        "failure_rate": 20.0,
        "deployment_frequency_per_day": 0.33,
        "mean_time_between_deployments_hours": 72.0,
        "deployment_names": "pbx-web",  # Should be list, is string
        "first_deployment": "2026-07-01T00:00:00Z",
        "last_deployment": "2026-07-30T23:59:59Z",
        # Add deployment_events for completeness check (even though it should fail earlier)
        "deployment_events_last_30_days": []
    }

    is_valid, errors = validate_all(data=data)

    print(f"  Result: is_valid={is_valid}")
    print(f"  Errors: {errors}")

    # Explicit assertions for expected (False, [relevant_errors]) result
    assert is_valid == False, f"Expected is_valid=False, got {is_valid}"
    assert len(errors) > 0, "Expected at least one error"

    # Check for type-related errors
    has_type_error = any("must be" in error or "numeric" in error for error in errors)
    assert has_type_error, f"Expected type-related error, got {errors}"

    # Verify that JSON and required fields validations passed
    assert not any("JSON" in error for error in errors), \
        f"JSON validation should have passed, but got JSON error: {errors}"
    assert not any("Missing required field" in error for error in errors), \
        f"Required fields validation should have passed, but got missing field error: {errors}"

    print(f"  ✓ PASS - Wrong data types correctly detected")
    print(f"  ✓ PASS - JSON validation passed (data is well-formed)")
    print(f"  ✓ PASS - Required fields validation passed (all fields present)")
    print()
    return True


def test_4_incomplete_data():
    """
    Test case 4: Incomplete data (missing expected values) → fails at completeness check.

    Creates data with valid structure but incomplete date coverage and verifies that:
    - validate_all returns (False, [relevant_errors])
    - Error message indicates completeness issues
    - JSON validation passes (data is well-formed)
    - Required fields validation passes (all fields present)
    - Data types validation passes (all types correct)
    - Completeness validation fails (missing dates/gaps)

    Expected: (False, [errors containing "completeness", "gap", or "Expected 30"])
    """
    print("TEST 4: Incomplete data (missing expected values) → fails at completeness check")

    # Valid structure with all fields and correct types, but incomplete date coverage
    data = {
        "service": "pbx-web",
        "period_days": 30,
        "total_deployments": 28,  # Less than 30
        "successful_deployments": 28,
        "failed_deployments": 0,
        "success_rate": 100.0,
        "failure_rate": 0.0,
        "deployment_frequency_per_day": 0.93,
        "mean_time_between_deployments_hours": 25.7,
        "deployment_names": ["pbx-web"],
        "first_deployment": "2026-07-01T00:00:00Z",
        "last_deployment": "2026-07-30T23:59:59Z",
        # Incomplete deployment events (only 28 days instead of 30)
        "deployment_events_last_30_days": [
            {"date": "2026-07-01"},
            {"date": "2026-07-02"},
            {"date": "2026-07-03"},
            # Missing 2026-07-04 (gap)
            {"date": "2026-07-05"},
            {"date": "2026-07-06"},
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
            # Missing 2026-07-29 and 2026-07-30
        ]
    }

    is_valid, errors = validate_all(data=data)

    print(f"  Result: is_valid={is_valid}")
    print(f"  Errors: {errors}")

    # Explicit assertions for expected (False, [relevant_errors]) result
    assert is_valid == False, f"Expected is_valid=False, got {is_valid}"
    assert len(errors) > 0, "Expected at least one error"

    # Check for completeness-related errors
    has_completeness_error = any(
        "completeness" in error.lower() or "gap" in error.lower() or
        "expected 30" in error.lower() or "missing data" in error.lower()
        for error in errors
    )
    assert has_completeness_error, f"Expected completeness-related error, got {errors}"

    # Verify that earlier validations passed
    assert not any("JSON" in error for error in errors), \
        f"JSON validation should have passed, but got JSON error: {errors}"
    assert not any("Missing required field" in error for error in errors), \
        f"Required fields validation should have passed, but got missing field error: {errors}"
    assert not any("must be" in error or "numeric" in error for error in errors), \
        f"Data types validation should have passed, but got type error: {errors}"

    print(f"  ✓ PASS - Incomplete data correctly detected at completeness check")
    print(f"  ✓ PASS - JSON validation passed (data is well-formed)")
    print(f"  ✓ PASS - Required fields validation passed (all fields present)")
    print(f"  ✓ PASS - Data types validation passed (all types correct)")
    print()
    return True


def main():
    """Run all single-failure validation tests."""
    print("=" * 80)
    print("SINGLE-FAILURE VALIDATION TESTS")
    print("=" * 80)
    print()
    print("Testing each individual validation failure scenario in isolation:")
    print("  1. Invalid JSON syntax → fails at JSON validation step")
    print("  2. Missing required fields → fails at required fields check")
    print("  3. Wrong data types → fails at data types check")
    print("  4. Incomplete data → fails at completeness check")
    print()
    print("Each test expects (False, [relevant_errors])")
    print("=" * 80)
    print()

    tests = [
        test_1_invalid_json_syntax,
        test_2_missing_required_fields,
        test_3_wrong_data_types,
        test_4_incomplete_data,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except AssertionError as e:
            print(f"  ✗ ASSERTION FAILED: {e}")
            print()
            results.append(False)
        except Exception as e:
            print(f"  ✗ EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            print()
            results.append(False)

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    print()

    if passed == total:
        print("✅ ALL TESTS PASSED")
        print()
        print("All 4 single-failure validation scenarios tested successfully:")
        print("  ✓ Invalid JSON syntax correctly fails at JSON validation step")
        print("  ✓ Missing required fields correctly fails at required fields check")
        print("  ✓ Wrong data types correctly fails at data types check")
        print("  ✓ Incomplete data correctly fails at completeness check")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print(f"   {total - passed} out of {total} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
