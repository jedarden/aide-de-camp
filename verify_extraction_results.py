#!/usr/bin/env python3
"""
Verify extraction results against actual file system.

This script verifies:
1. File sizes match actual file sizes
2. Creation timestamps are valid ISO format
3. Deletion timestamps are null when expected
4. Line counts are correct
"""

import json
import os
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

def count_lines(file_path: str) -> int:
    """Count lines in a file."""
    try:
        with open(file_path, 'r', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def verify_file_metadata(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Verify extracted metadata against actual file."""
    file_path = extracted.get("file_path")

    if not file_path or not Path(file_path).exists():
        return {
            "file_path": file_path,
            "valid": False,
            "error": "File not found"
        }

    verification = {
        "file_path": file_path,
        "valid": True,
        "errors": [],
        "warnings": []
    }

    # Check file size
    actual_size = os.path.getsize(file_path)
    extracted_size = extracted.get("size_bytes")

    if extracted_size != actual_size:
        verification["valid"] = False
        verification["errors"].append(
            f"Size mismatch: extracted={extracted_size}, actual={actual_size}"
        )

    # Check creation timestamp format
    creation_ts = extracted.get("creation_timestamp")
    if creation_ts:
        try:
            # Verify ISO format
            datetime.fromisoformat(creation_ts)
        except ValueError:
            verification["valid"] = False
            verification["errors"].append(
                f"Invalid creation timestamp format: {creation_ts}"
            )
    else:
        verification["warnings"].append("Missing creation timestamp")

    # Check deletion timestamp (should be null for most files)
    deletion_ts = extracted.get("deletion_timestamp")
    if deletion_ts:
        try:
            datetime.fromisoformat(deletion_ts)
        except ValueError:
            verification["valid"] = False
            verification["errors"].append(
                f"Invalid deletion timestamp format: {deletion_ts}"
            )

    # Check line count
    extracted_lines = extracted.get("line_count")
    if extracted_lines is not None:
        actual_lines = count_lines(file_path)
        if extracted_lines != actual_lines:
            verification["valid"] = False
            verification["errors"].append(
                f"Line count mismatch: extracted={extracted_lines}, actual={actual_lines}"
            )

    return verification

def main():
    """Verify all extraction results."""
    print("=" * 70)
    print("EXTRACTION RESULTS VERIFICATION")
    print("=" * 70)

    # Load the extraction results
    results_file = Path("/home/coding/aide-de-camp/sample_extraction_results.log")

    if not results_file.exists():
        print(f"❌ Results file not found: {results_file}")
        return

    # Parse the results file
    with open(results_file, 'r') as f:
        content = f.read()

    # Extract JSON blocks from the output
    import re
    json_pattern = r'\{[^{}]*"file_path"[^{}]*\}'
    json_matches = re.findall(json_pattern, content, re.DOTALL)

    print(f"\nFound {len(json_matches)} extraction results")

    all_verifications = []
    valid_count = 0
    error_count = 0

    for json_str in json_matches:
        try:
            extracted = json.loads(json_str)
            verification = verify_file_metadata(extracted)
            all_verifications.append(verification)

            if verification["valid"]:
                valid_count += 1
            else:
                error_count += 1
        except json.JSONDecodeError as e:
            print(f"⚠️  Failed to parse JSON: {e}")

    # Print summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    print(f"Total files: {len(all_verifications)}")
    print(f"✅ Valid: {valid_count}")
    print(f"❌ Errors: {error_count}")

    # Print detailed results
    print("\n" + "=" * 70)
    print("DETAILED VERIFICATION RESULTS")
    print("=" * 70)

    for v in all_verifications:
        print(f"\n{'✅' if v['valid'] else '❌'} {v['file_path']}")

        if v["errors"]:
            print("  Errors:")
            for error in v["errors"]:
                print(f"    - {error}")

        if v["warnings"]:
            print("  Warnings:")
            for warning in v["warnings"]:
                print(f"    - {warning}")

    # Check for patterns
    print("\n" + "=" * 70)
    print("EDGE CASES AND PATTERNS")
    print("=" * 70)

    # Check for empty files
    empty_files = [v for v in all_verifications if "size_bytes" in v.get("errors", [])]
    if empty_files:
        print(f"\n⚠️  Files with size issues: {len(empty_files)}")
        for v in empty_files:
            print(f"  - {v['file_path']}")

    # Check for timestamp issues
    timestamp_issues = [v for v in all_verifications if "timestamp" in str(v.get("errors", []))]
    if timestamp_issues:
        print(f"\n⚠️  Files with timestamp issues: {len(timestamp_issues)}")
        for v in timestamp_issues:
            print(f"  - {v['file_path']}")
            for error in v["errors"]:
                if "timestamp" in error.lower():
                    print(f"    {error}")

    # Check for line count issues
    line_issues = [v for v in all_verifications if "line" in str(v.get("errors", []))]
    if line_issues:
        print(f"\n⚠️  Files with line count issues: {len(line_issues)}")
        for v in line_issues:
            print(f"  - {v['file_path']}")
            for error in v["errors"]:
                if "line" in error.lower():
                    print(f"    {error}")

if __name__ == "__main__":
    main()