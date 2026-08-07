#!/usr/bin/env python3
"""
Test extraction edge cases and additional sample log files.

This script tests:
1. Log files with potential deletion timestamps
2. Empty or small log files
3. Log files with different formats
4. Files in different locations
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from extract_log_file_metadata import (
    extract_pod_metadata,
    is_valid_iso_timestamp,
    extract_deletion_timestamp_from_log,
    extract_first_log_timestamp
)


def test_edge_cases():
    """Test various edge cases."""
    print("=== Testing Edge Cases ===\n")

    test_cases = []

    # Test 1: Check if any log files have deletion indicators
    print("Test 1: Searching for log files with deletion indicators...")
    log_directories = [
        "/home/coding/aide-de-camp/logs",
        "/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs",
        "/home/coding/aide-de-camp/data"
    ]

    deletion_keywords = ['deleted', 'terminated', 'killing', 'sigterm', 'exit code']
    files_with_deletions = []

    for log_dir in log_directories:
        if os.path.exists(log_dir):
            for root, dirs, files in os.walk(log_dir):
                for file in files:
                    if file.endswith('.log'):
                        file_path = os.path.join(root, file)
                        try:
                            # Quick check for deletion indicators
                            with open(file_path, 'r', errors='ignore') as f:
                                # Read last 20 lines
                                lines = f.readlines()[-20:]
                                for line in lines:
                                    if any(keyword in line.lower() for keyword in deletion_keywords):
                                        files_with_deletions.append(file_path)
                                        break
                        except Exception:
                            continue

    if files_with_deletions:
        print(f"  Found {len(files_with_deletions)} files with deletion indicators")
        # Test up to 3 of them
        for file_path in files_with_deletions[:3]:
            print(f"  Testing: {os.path.basename(file_path)}")
            result = extract_pod_metadata(file_path)
            test_cases.append({
                "file": file_path,
                "type": "deletion_candidate",
                "result": result
            })
    else:
        print("  No files with deletion indicators found")

    print()

    # Test 2: Small log files
    print("Test 2: Testing small log files...")
    small_files = []
    for log_dir in log_directories:
        if os.path.exists(log_dir):
            for root, dirs, files in os.walk(log_dir):
                for file in files:
                    if file.endswith('.log'):
                        file_path = os.path.join(root, file)
                        try:
                            size = os.path.getsize(file_path)
                            if 0 < size < 500:  # Small but not empty
                                small_files.append(file_path)
                                if len(small_files) >= 3:
                                    break
                        except Exception:
                            continue
                if len(small_files) >= 3:
                    break
        if len(small_files) >= 3:
            break

    for file_path in small_files[:3]:
        print(f"  Testing: {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
        result = extract_pod_metadata(file_path)
        test_cases.append({
            "file": file_path,
            "type": "small_file",
            "result": result
        })

    print()

    # Test 3: Files from different locations
    print("Test 3: Testing files from different locations...")
    diverse_files = [
        "/home/coding/aide-de-camp/logs/whisper-stt-main.log",
        "/home/coding/aide-de-camp/logs/pbx-web-nginx.log",
        "/home/coding/aide-de-camp/data/pbx-web-nginx.log"
    ]

    for file_path in diverse_files:
        if os.path.exists(file_path):
            print(f"  Testing: {os.path.basename(file_path)}")
            result = extract_pod_metadata(file_path)
            test_cases.append({
                "file": file_path,
                "type": "diverse_location",
                "result": result
            })
        else:
            print(f"  Skipping (not found): {os.path.basename(file_path)}")

    print()

    # Analyze results
    print("=== Edge Case Test Results ===\n")

    successful_extractions = 0
    valid_creation_timestamps = 0
    files_with_deletion_timestamps = 0
    size_extraction_failures = 0

    for i, test_case in enumerate(test_cases, 1):
        file_path = test_case["file"]
        result = test_case["result"]
        test_type = test_case["type"]

        print(f"Test {i} ({test_type}): {os.path.basename(file_path)}")

        if result:
            successful_extractions += 1
            print(f"  ✓ Extraction successful")

            # Check creation timestamp
            creation = result.get("creation_timestamp")
            if creation and is_valid_iso_timestamp(creation):
                valid_creation_timestamps += 1
                print(f"  ✓ Creation timestamp: {creation}")
            else:
                print(f"  ✗ Creation timestamp invalid: {creation}")

            # Check deletion timestamp
            deletion = result.get("deletion_timestamp")
            if deletion:
                files_with_deletion_timestamps += 1
                print(f"  ⚠ Deletion timestamp found: {deletion}")
            else:
                print(f"  ✓ Deletion timestamp: None")

            # Check file size
            size = result.get("log_size_bytes")
            if size is not None:
                print(f"  ✓ File size: {size} bytes")
            else:
                size_extraction_failures += 1
                print(f"  ✗ File size extraction failed")
        else:
            print(f"  ✗ Extraction failed")

        print()

    # Summary
    print("=== Edge Case Summary ===\n")
    print(f"Total edge cases tested: {len(test_cases)}")
    print(f"Successful extractions: {successful_extractions}/{len(test_cases)}")
    print(f"Valid creation timestamps: {valid_creation_timestamps}/{len(test_cases)}")
    print(f"Files with deletion timestamps: {files_with_deletion_timestamps}/{len(test_cases)}")
    print(f"Size extraction failures: {size_extraction_failures}/{len(test_cases)}")

    return successful_extractions == len(test_cases)


if __name__ == "__main__":
    success = test_edge_cases()
    sys.exit(0 if success else 1)