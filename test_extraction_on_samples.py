#!/usr/bin/env python3
"""
Test extraction on sample log files to validate the timestamp extraction function.

This script:
1. Tests extraction on 5-10 sample log files
2. Verifies creation_timestamp parsing is correct
3. Verifies deletion_timestamp is null when expected
4. Verifies log_size_bytes matches file size
5. Handles any parsing errors or edge cases found
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add the parent directory to the path to import the extraction module
sys.path.insert(0, str(Path(__file__).parent))

# Import functions from the extract_log_file_metadata module
from extract_log_file_metadata import (
    extract_pod_metadata,
    get_file_size,
    get_file_mtime,
    is_valid_iso_timestamp,
    extract_first_log_timestamp,
    extract_deletion_timestamp_from_log,
    load_analysis_metadata
)


def verify_timestamp_format(timestamp: Optional[str], field_name: str) -> Dict[str, Any]:
    """Verify that a timestamp is in valid ISO format."""
    result = {
        "field_name": field_name,
        "is_valid": False,
        "value": timestamp,
        "error": None
    }

    if timestamp is None:
        result["error"] = "Timestamp is None"
        return result

    if not timestamp:
        result["error"] = "Timestamp is empty string"
        return result

    if not is_valid_iso_timestamp(timestamp):
        result["error"] = f"Invalid ISO format: {timestamp}"
        return result

    result["is_valid"] = True
    return result


def verify_file_size_match(log_file_path: str, reported_size: Optional[int]) -> Dict[str, Any]:
    """Verify that the reported file size matches the actual file size."""
    result = {
        "file_path": log_file_path,
        "reported_size": reported_size,
        "actual_size": None,
        "matches": False,
        "error": None
    }

    if reported_size is None:
        result["error"] = "Reported size is None"
        return result

    try:
        actual_size = os.path.getsize(log_file_path)
        result["actual_size"] = actual_size
        result["matches"] = (actual_size == reported_size)
    except (OSError, FileNotFoundError) as e:
        result["error"] = f"File not found or inaccessible: {e}"

    return result


def test_single_log_file(log_file_path: str, expected_deletion: bool = False) -> Dict[str, Any]:
    """
    Test extraction on a single log file.

    Args:
        log_file_path: Path to the log file
        expected_deletion: Whether we expect a deletion timestamp

    Returns:
        Dictionary with test results
    """
    test_result = {
        "log_file_path": log_file_path,
        "file_exists": False,
        "extraction_success": False,
        "timestamp_checks": {},
        "file_size_check": {},
        "deletion_check": {},
        "errors": []
    }

    # Check if file exists
    if not os.path.exists(log_file_path):
        test_result["errors"].append(f"File does not exist: {log_file_path}")
        return test_result

    test_result["file_exists"] = True

    try:
        # Extract metadata using the function under test
        metadata = extract_pod_metadata(log_file_path)

        if not metadata:
            test_result["errors"].append("extract_pod_metadata returned None/empty")
            return test_result

        test_result["extraction_success"] = True

        # Verify creation_timestamp
        creation_check = verify_timestamp_format(
            metadata.get("creation_timestamp"),
            "creation_timestamp"
        )
        test_result["timestamp_checks"]["creation_timestamp"] = creation_check

        # Verify deletion_timestamp
        deletion_check = verify_timestamp_format(
            metadata.get("deletion_timestamp"),
            "deletion_timestamp"
        )
        test_result["timestamp_checks"]["deletion_timestamp"] = deletion_check

        # Check if deletion timestamp matches expectation
        if expected_deletion:
            if metadata.get("deletion_timestamp") is None:
                test_result["deletion_check"]["expected_deletion_missing"] = True
                test_result["errors"].append("Expected deletion timestamp but got None")
            else:
                test_result["deletion_check"]["expected_deletion_found"] = True
        else:
            if metadata.get("deletion_timestamp") is not None:
                test_result["deletion_check"]["unexpected_deletion_found"] = True
                test_result["errors"].append(f"Unexpected deletion timestamp: {metadata.get('deletion_timestamp')}")

        # Verify file size
        file_size_check = verify_file_size_match(
            log_file_path,
            metadata.get("log_size_bytes")
        )
        test_result["file_size_check"] = file_size_check

    except Exception as e:
        test_result["errors"].append(f"Exception during extraction: {e}")

    return test_result


def run_comprehensive_tests():
    """Run comprehensive tests on sample log files."""
    print("=== Extraction Function Test Suite ===\n")

    # Load analysis metadata to get sample log files
    root_dir = Path("/home/coding/aide-de-camp")
    metadata_file = root_dir / "data" / "analysis-metadata-extracted.json"

    if not metadata_file.exists():
        print(f"ERROR: Metadata file not found: {metadata_file}")
        return

    analysis_data = load_analysis_metadata(metadata_file)

    # Select sample log files for testing
    sample_files = []

    # Get first 5 actual log files (not summaries or array data)
    for log_path, entry_data in list(analysis_data.items())[:20]:
        if log_path and not log_path.startswith("summary/") and not log_path.startswith("array-data/"):
            if os.path.exists(log_path):
                sample_files.append(log_path)
                if len(sample_files) >= 5:
                    break

    if not sample_files:
        print("ERROR: No sample log files found for testing")
        return

    print(f"Selected {len(sample_files)} sample log files for testing:\n")

    # Run tests on each sample file
    all_test_results = []
    for i, log_file in enumerate(sample_files, 1):
        print(f"Test {i}: {log_file}")
        result = test_single_log_file(log_file)
        all_test_results.append(result)

        # Print results for this file
        if result["file_exists"]:
            print(f"  ✓ File exists")
        else:
            print(f"  ✗ File does not exist")

        if result["extraction_success"]:
            print(f"  ✓ Extraction successful")
        else:
            print(f"  ✗ Extraction failed")

        # Timestamp checks
        creation_check = result["timestamp_checks"].get("creation_timestamp", {})
        if creation_check.get("is_valid"):
            print(f"  ✓ Creation timestamp valid: {creation_check.get('value')}")
        else:
            print(f"  ✗ Creation timestamp invalid: {creation_check.get('error')}")

        deletion_check = result["timestamp_checks"].get("deletion_timestamp", {})
        if deletion_check.get("is_valid"):
            print(f"  ✓ Deletion timestamp valid: {deletion_check.get('value')}")
        elif deletion_check.get("value") is None:
            print(f"  ✓ Deletion timestamp is None (as expected)")
        else:
            print(f"  ✗ Deletion timestamp invalid: {deletion_check.get('error')}")

        # File size check
        size_check = result.get("file_size_check", {})
        if size_check.get("matches"):
            print(f"  ✓ File size matches: {size_check.get('actual_size')} bytes")
        else:
            print(f"  ✗ File size mismatch: {size_check.get('error')}")

        # Print any errors
        if result["errors"]:
            print(f"  Errors:")
            for error in result["errors"]:
                print(f"    - {error}")

        print()

    # Generate summary report
    print("=== Test Summary ===\n")

    total_tests = len(all_test_results)
    passed_tests = sum(1 for r in all_test_results if r["extraction_success"] and not r["errors"])
    failed_tests = total_tests - passed_tests

    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")

    # Count specific validation results
    valid_creation = sum(1 for r in all_test_results
                       if r["timestamp_checks"].get("creation_timestamp", {}).get("is_valid"))

    valid_deletion = sum(1 for r in all_test_results
                       if r["timestamp_checks"].get("deletion_timestamp", {}).get("is_valid"))

    null_deletion = sum(1 for r in all_test_results
                      if r["timestamp_checks"].get("deletion_timestamp", {}).get("value") is None)

    size_matches = sum(1 for r in all_test_results
                      if r.get("file_size_check", {}).get("matches"))

    print(f"\nTimestamp Validation:")
    print(f"  Valid creation timestamps: {valid_creation}/{total_tests}")
    print(f"  Valid deletion timestamps: {valid_deletion}/{total_tests}")
    print(f"  Null deletion timestamps: {null_deletion}/{total_tests}")
    print(f"  File size matches: {size_matches}/{total_tests}")

    # Save detailed results to file
    output_file = root_dir / "extraction_test_results.json"
    with open(output_file, 'w') as f:
        json.dump(all_test_results, f, indent=2)

    print(f"\nDetailed results saved to: {output_file}")

    # Return pass/fail status
    return passed_tests == total_tests


if __name__ == "__main__":
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)