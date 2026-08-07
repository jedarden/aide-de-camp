#!/usr/bin/env python3
"""
Multi-failure validation test.

Tests that multiple validation errors are collected and reported together:
- Missing required fields
- Wrong data types for present fields
- Incomplete data

This test expects (False, [errors_from_all_steps]) where all errors
from different validation steps are collected and returned together.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.validation.integration import validate_all


def test_multiple_validation_failures():
    """
    Test case: Multiple validation errors collected and reported together.

    Creates data with multiple issues and verifies that:
    - validate_all returns (False, [errors_from_all_steps])
    - JSON validation passes (data is well-formed)
    - Required fields validation fails (missing fields)
    - Data types validation fails (wrong types for present fields)
    - Completeness validation fails (incomplete date coverage)
    - All errors are present in the returned list
    - Errors from all steps are collected together

    Expected: (False, [errors containing "Missing required field", "must be", "completeness/gap"])
    """
    print("TEST: Multiple validation failures → errors collected from all steps")

    # Valid JSON syntax but with multiple issues:
    # 1. Missing required fields: total_deployments, successful_deployments, failed_deployments
    # 2. Wrong data types: service is int (should be str), period_days is str (should be int)
    # 3. Incomplete data: deployment_events_last_30_days has gaps (missing dates)
    data = {
        "service": 123,  # Wrong type: should be string, is int
        "period_days": "30",  # Wrong type: should be int, is string
        "success_rate": 80.0,  # Valid type
        "failure_rate": 20.0,  # Valid type
        "deployment_frequency_per_day": 0.33,  # Valid type
        "mean_time_between_deployments_hours": 72.0,  # Valid type
        "deployment_names": "pbx-web",  # Wrong type: should be list, is string
        "first_deployment": "2026-07-01T00:00:00Z",  # Valid
        "last_deployment": "2026-07-30T23:59:59Z",  # Valid
        # Missing required fields: total_deployments, successful_deployments, failed_deployments
        # Incomplete deployment events (has gaps: missing 2026-07-04, 2026-07-15, 2026-07-29, 2026-07-30)
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
            # Missing 2026-07-15 (gap)
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
            # Missing 2026-07-29 and 2026-07-30 (gaps)
        ]
    }

    is_valid, errors = validate_all(data=data)

    print(f"  Result: is_valid={is_valid}")
    print(f"  Errors: {errors}")

    # Primary assertion: expects (False, [errors_from_all_steps])
    assert is_valid == False, f"Expected is_valid=False, got {is_valid}"
    assert len(errors) > 0, "Expected at least one error"

    # Verify that JSON validation passed (no JSON errors in the list)
    assert not any("JSON validation" in error for error in errors), \
        f"JSON validation should have passed, but got JSON error: {errors}"

    # Verify errors from all validation steps are present
    # Step 2: Required fields validation - should have missing field errors
    has_missing_field_error = any("Missing required field" in error for error in errors)
    assert has_missing_field_error, \
        f"Expected 'Missing required field' error from step 2, got {errors}"

    # Step 3: Data types validation - should have type error
    has_type_error = any("must be" in error or "Data types validation" in error for error in errors)
    assert has_type_error, \
        f"Expected type-related error from step 3, got {errors}"

    # Step 4: Completeness validation - should have completeness error
    has_completeness_error = any(
        "completeness" in error.lower() or "gap" in error.lower() or
        "expected 30" in error.lower() or "Completeness validation" in error
        for error in errors
    )
    assert has_completeness_error, \
        f"Expected completeness-related error from step 4, got {errors}"

    # Verify we have errors from multiple steps (not just one)
    # We should have at least 3 errors: one from each validation step
    assert len(errors) >= 3, \
        f"Expected errors from at least 3 validation steps, got {len(errors)} errors: {errors}"

    # Verify error categorization - each error should indicate which step it came from
    error_prefixes = [error.split(":")[0] if ":" in error else "" for error in errors]
    assert any("Required fields validation" in prefix for prefix in error_prefixes), \
        f"Expected error from 'Required fields validation' step, got prefixes: {error_prefixes}"
    assert any("Data types validation" in prefix for prefix in error_prefixes), \
        f"Expected error from 'Data types validation' step, got prefixes: {error_prefixes}"
    assert any("Completeness validation" in prefix for prefix in error_prefixes), \
        f"Expected error from 'Completeness validation' step, got prefixes: {error_prefixes}"

    print(f"  ✓ PASS - Multiple validation errors correctly detected")
    print(f"  ✓ PASS - JSON validation passed (data is well-formed)")
    print(f"  ✓ PASS - Required fields validation failed (missing fields detected)")
    print(f"  ✓ PASS - Data types validation failed (wrong types detected)")
    print(f"  ✓ PASS - Completeness validation failed (gaps detected)")
    print(f"  ✓ PASS - All errors from all steps collected together")
    print(f"  ✓ PASS - Got {len(errors)} errors from multiple validation steps")
    print()
    return True


def main():
    """Run the multi-failure validation test."""
    print("=" * 80)
    print("MULTI-FAILURE VALIDATION TEST")
    print("=" * 80)
    print()
    print("Testing that multiple validation errors are collected and reported together:")
    print("  1. Missing required fields")
    print("  2. Wrong data types for present fields")
    print("  3. Incomplete data")
    print()
    print("Expected: (False, [errors_from_all_steps])")
    print("=" * 80)
    print()

    try:
        result = test_multiple_validation_failures()

        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Test result: {'PASS' if result else 'FAIL'}")
        print()

        if result:
            print("✅ TEST PASSED")
            print()
            print("Multi-failure validation scenario tested successfully:")
            print("  ✓ Multiple validation errors correctly collected from all steps")
            print("  ✓ Missing required fields detected")
            print("  ✓ Wrong data types detected")
            print("  ✓ Incomplete data detected")
            print("  ✓ All errors reported together in a single list")
            return 0
        else:
            print("❌ TEST FAILED")
            return 1

    except AssertionError as e:
        print(f"  ✗ ASSERTION FAILED: {e}")
        print()
        print("=" * 80)
        print("❌ TEST FAILED")
        return 1
    except Exception as e:
        print(f"  ✗ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("=" * 80)
        print("❌ TEST FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
