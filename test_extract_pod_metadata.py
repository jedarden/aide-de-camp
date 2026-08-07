#!/usr/bin/env python3
"""
Test script for extract_pod_metadata function.

Tests the function against real log files to verify it correctly extracts:
- creation_timestamp
- deletion_timestamp
- log_size_bytes
"""

import sys
from pathlib import Path

# Add the parent directory to the path to import the function
sys.path.insert(0, str(Path(__file__).parent))

from extract_log_file_metadata import extract_pod_metadata


def test_extract_pod_metadata():
    """Test the extract_pod_metadata function with sample log files."""

    # Test files
    test_files = [
        "logs/pbx-web-nginx.log",
        "logs/pbx-web-site-generator.log",
        "logs/pbx-web-site-generator-recent.log",
    ]

    print("=" * 80)
    print("Testing extract_pod_metadata function")
    print("=" * 80)

    for log_file in test_files:
        print(f"\n--- Testing: {log_file} ---")

        # Get absolute path
        log_path = Path(__file__).parent / log_file

        if not log_path.exists():
            print(f"  ⚠ File does not exist: {log_path}")
            continue

        # Call the function
        result = extract_pod_metadata(str(log_path))

        # Display results
        print(f"  log_size_bytes: {result.get('log_size_bytes')}")
        print(f"  creation_timestamp: {result.get('creation_timestamp')}")
        print(f"  deletion_timestamp: {result.get('deletion_timestamp')}")

        # Verify expected fields are present
        assert "creation_timestamp" in result, "Missing creation_timestamp field"
        assert "deletion_timestamp" in result, "Missing deletion_timestamp field"
        assert "log_size_bytes" in result, "Missing log_size_bytes field"

        # Verify log_size_bytes is not None for existing files
        assert result["log_size_bytes"] is not None, f"log_size_bytes should not be None for existing file {log_file}"

        # Verify creation_timestamp is not None for existing files with content
        if result["log_size_bytes"] > 0:
            assert result["creation_timestamp"] is not None, f"creation_timestamp should not be None for non-empty file {log_file}"

        print(f"  ✓ All assertions passed")


def test_nonexistent_file():
    """Test handling of non-existent files."""
    print("\n" + "=" * 80)
    print("Testing non-existent file handling")
    print("=" * 80)

    result = extract_pod_metadata("/path/to/nonexistent/file.log")

    print(f"\n--- Testing: /path/to/nonexistent/file.log ---")
    print(f"  log_size_bytes: {result.get('log_size_bytes')}")
    print(f"  creation_timestamp: {result.get('creation_timestamp')}")
    print(f"  deletion_timestamp: {result.get('deletion_timestamp')}")

    # Should return None for all fields
    assert result["log_size_bytes"] is None, "log_size_bytes should be None for non-existent file"
    assert result["creation_timestamp"] is None, "creation_timestamp should be None for non-existent file"
    assert result["deletion_timestamp"] is None, "deletion_timestamp should be None for non-existent file"

    print(f"  ✓ Correctly handled non-existent file")


def test_function_signature():
    """Verify the function signature matches requirements."""
    print("\n" + "=" * 80)
    print("Verifying function signature")
    print("=" * 80)

    import inspect
    sig = inspect.signature(extract_pod_metadata)
    params = list(sig.parameters.keys())

    print(f"\nFunction signature: {sig}")
    print(f"Parameters: {params}")

    # Verify signature
    assert len(params) == 1, f"Expected 1 parameter, got {len(params)}"
    assert params[0] == "log_file_path", f"Expected parameter 'log_file_path', got '{params[0]}'"

    # Verify return type hints
    return_annotation = sig.return_annotation
    print(f"Return type annotation: {return_annotation}")

    # Test it actually returns a dict
    test_path = Path(__file__).parent / "logs/pbx-web-nginx.log"
    result = extract_pod_metadata(str(test_path))
    assert isinstance(result, dict), f"Expected dict return type, got {type(result)}"

    print(f"  ✓ Function signature verified")


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("EXTRACT_POD_METADATA FUNCTION TEST SUITE")
    print("=" * 80)

    try:
        test_function_signature()
        test_nonexistent_file()
        test_extract_pod_metadata()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
