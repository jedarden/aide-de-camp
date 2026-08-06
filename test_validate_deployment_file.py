#!/usr/bin/env python3
"""
Test suite for validate_deployment_file function.

Tests confirm the function exists and returns expected types.
"""

import sys
import tempfile
from pathlib import Path

# Add the parent directory to the path to import the module
sys.path.insert(0, '/home/coding/aide-de-camp')
from validate_deployment_file import validate_deployment_file


def test_function_exists():
    """Test that validate_deployment_file function exists."""
    assert callable(validate_deployment_file), "validate_deployment_file should be a callable function"
    print("✓ Function exists")


def test_function_returns_tuple():
    """Test that validate_deployment_file returns a tuple."""
    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
        f.write('{}')

    try:
        result = validate_deployment_file(temp_path)
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 2, f"Expected tuple of length 2, got {len(result)}"
        print(f"✓ Function returns tuple with 2 elements")
    finally:
        # Clean up temp file
        Path(temp_path).unlink()


def test_function_returns_correct_types():
    """Test that validate_deployment_file returns (bool, List[str])."""
    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
        f.write('{}')

    try:
        is_valid, errors = validate_deployment_file(temp_path)

        # Check first element is bool
        assert isinstance(is_valid, bool), f"Expected bool, got {type(is_valid)}"
        print(f"✓ First element is bool: {is_valid}")

        # Check second element is list
        assert isinstance(errors, list), f"Expected list, got {type(errors)}"
        print(f"✓ Second element is list: {errors}")

        # Check list elements are strings (if any)
        for error in errors:
            assert isinstance(error, str), f"Expected str in errors list, got {type(error)}"
        print(f"✓ List elements are strings")

    finally:
        # Clean up temp file
        Path(temp_path).unlink()


def test_function_handles_nonexistent_file():
    """Test that validate_deployment_file handles nonexistent files gracefully."""
    nonexistent_path = "/tmp/nonexistent_file_12345.json"

    is_valid, errors = validate_deployment_file(nonexistent_path)

    assert isinstance(is_valid, bool), "Should return bool for validity"
    assert isinstance(errors, list), "Should return list of errors"
    assert not is_valid, "Nonexistent file should be invalid"
    assert len(errors) > 0, "Should have at least one error message"
    assert any("File not found" in error for error in errors), "Should report file not found"

    print(f"✓ Handles nonexistent file correctly")
    print(f"  - is_valid: {is_valid}")
    print(f"  - errors: {errors}")


def test_function_signature():
    """Test that function has correct signature."""
    import inspect

    sig = inspect.signature(validate_deployment_file)
    params = list(sig.parameters.keys())

    assert len(params) == 1, f"Expected 1 parameter, got {len(params)}"
    assert 'file_path' in params, "Should have 'file_path' parameter"

    # Check parameter type hint
    file_path_param = sig.parameters['file_path']
    assert file_path_param.annotation == str, f"file_path should be annotated as str"

    # Check return type hint
    assert sig.return_annotation != inspect.Parameter.empty, "Should have return type hint"

    print(f"✓ Function signature is correct")
    print(f"  - Parameters: {params}")
    print(f"  - Return annotation: {sig.return_annotation}")


def test_function_has_docstring():
    """Test that function has docstring."""
    assert validate_deployment_file.__doc__ is not None, "Function should have docstring"
    assert len(validate_deployment_file.__doc__) > 50, "Docstring should be descriptive"
    print(f"✓ Function has docstring")


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        ("Function exists", test_function_exists),
        ("Function returns tuple", test_function_returns_tuple),
        ("Function returns correct types", test_function_returns_correct_types),
        ("Handles nonexistent file", test_function_handles_nonexistent_file),
        ("Function signature", test_function_signature),
        ("Function has docstring", test_function_has_docstring),
    ]

    print("=" * 70)
    print("TESTING validate_deployment_file function")
    print("=" * 70)

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            print(f"\n[Test] {test_name}")
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(run_all_tests())