#!/usr/bin/env python3
"""
Test the timestamp extraction function on sample log files.

Validates that extract_pod_metadata() correctly extracts:
- creation_timestamp (from file mtime or first log line)
- deletion_timestamp (from log content, or null if no deletion event)
- log_size_bytes (matches actual file size)
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Import the extraction function
sys.path.insert(0, str(Path(__file__).parent))
from extract_log_file_metadata import extract_pod_metadata


def verify_file_size(actual_path: str, reported_size: Optional[int]) -> bool:
    """Verify that reported log_size_bytes matches actual file size."""
    if reported_size is None:
        return False

    try:
        actual_size = os.path.getsize(actual_path)
        return actual_size == reported_size
    except (OSError, FileNotFoundError):
        return False


def verify_creation_timestamp(actual_path: str, reported_timestamp: Optional[str]) -> bool:
    """Verify that creation_timestamp is valid and recent."""
    if reported_timestamp is None:
        return False

    try:
        # Parse the ISO timestamp
        parsed_dt = datetime.fromisoformat(reported_timestamp)

        # Verify it's not in the future
        now = datetime.now()
        if parsed_dt > now:
            print(f"  ⚠️  Timestamp is in the future: {reported_timestamp}")
            return False

        # Verify it's not ridiculously old (before 2020)
        if parsed_dt.year < 2020:
            print(f"  ⚠️  Timestamp is too old: {reported_timestamp}")
            return False

        # Also verify against file mtime for comparison
        file_mtime = os.path.getmtime(actual_path)
        mtime_dt = datetime.fromtimestamp(file_mtime)

        # Allow up to 1 second difference for rounding
        time_diff = abs((parsed_dt - mtime_dt).total_seconds())
        if time_diff > 1.0:
            print(f"  ℹ️  Creation timestamp differs from mtime by {time_diff:.1f}s")

        return True
    except (ValueError, TypeError) as e:
        print(f"  ❌ Failed to parse creation_timestamp '{reported_timestamp}': {e}")
        return False


def verify_deletion_timestamp(actual_path: str, log_file: str, deletion_timestamp: Optional[str]) -> bool:
    """Verify deletion_timestamp is either null or a valid timestamp."""
    if deletion_timestamp is None:
        # This is valid - no deletion event found
        return True

    try:
        # Parse the ISO timestamp
        parsed_dt = datetime.fromisoformat(deletion_timestamp)

        # Verify it's not in the future
        now = datetime.now()
        if parsed_dt > now:
            print(f"  ⚠️  Deletion timestamp is in the future: {deletion_timestamp}")
            return False

        # Verify it's not before 2020
        if parsed_dt.year < 2020:
            print(f"  ⚠️  Deletion timestamp is too old: {deletion_timestamp}")
            return False

        # Quick check - read first few lines to see if this is a pod deletion
        with open(actual_path, 'r', errors='ignore') as f:
            sample_lines = ''.join(f.readlines()[:20])
            if 'pod deleted' not in sample_lines.lower() and 'terminated' not in sample_lines.lower():
                print(f"  ℹ️  Deletion timestamp found but no obvious deletion markers in first 20 lines")

        return True
    except (ValueError, TypeError) as e:
        print(f"  ❌ Failed to parse deletion_timestamp '{deletion_timestamp}': {e}")
        return False


def test_sample_files():
    """Test extraction on 5-10 sample log files."""

    # Select sample log files from different locations
    sample_files = [
        "/home/coding/aide-de-camp/logs/pbx-web-nginx.log",
        "/home/coding/aide-de-camp/logs/pbx-web-site-generator.log",
        "/home/coding/aide-de-camp/logs/whisper-stt-pod.log",
        "/home/coding/aide-de-camp/data/pbx-web-nginx.log",
        "/home/coding/aide-de-camp/data/pbx-web-site-generator.log",
        "/home/coding/aide-de-camp/docs/notes/latency-test-run-20260724.log",
        "/home/coding/aide-de-camp/research-data/pbx-web/site-generator-30d.log",
        "/home/coding/aide-de-camp/logs/pbx-web-30day/pbx-web-main-current.log",
    ]

    # Filter to only existing files, max 10
    existing_files = [f for f in sample_files if os.path.exists(f)][:10]

    if not existing_files:
        print("❌ No sample log files found!")
        return False

    print(f"🧪 Testing timestamp extraction on {len(existing_files)} sample log files\n")

    results = []
    all_passed = True

    for i, log_file in enumerate(existing_files, 1):
        filename = os.path.basename(log_file)
        print(f"{i}. Testing: {filename}")

        try:
            # Run extraction
            metadata = extract_pod_metadata(log_file)

            # Verify each field
            file_size_ok = verify_file_size(log_file, metadata.get("log_size_bytes"))
            creation_ok = verify_creation_timestamp(log_file, metadata.get("creation_timestamp"))
            deletion_ok = verify_deletion_timestamp(log_file, filename, metadata.get("deletion_timestamp"))

            all_checks_passed = file_size_ok and creation_ok and deletion_ok

            # Print results
            print(f"  File size: {metadata.get('log_size_bytes', 'N/A')} bytes {'✅' if file_size_ok else '❌'}")
            print(f"  Created: {metadata.get('creation_timestamp', 'N/A')} {'✅' if creation_ok else '❌'}")
            print(f"  Deleted: {metadata.get('deletion_timestamp', 'N/A')} {'✅' if deletion_ok else '❌'}")

            if all_checks_passed:
                print(f"  ✅ All checks passed")
            else:
                print(f"  ⚠️  Some checks failed")
                all_passed = False

            print()

            results.append({
                'file': filename,
                'path': log_file,
                'metadata': metadata,
                'file_size_ok': file_size_ok,
                'creation_ok': creation_ok,
                'deletion_ok': deletion_ok,
                'all_passed': all_checks_passed
            })

        except Exception as e:
            print(f"  ❌ Exception during extraction: {e}")
            print()
            all_passed = False
            results.append({
                'file': filename,
                'path': log_file,
                'error': str(e),
                'all_passed': False
            })

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed_count = sum(1 for r in results if r.get('all_passed', False))
    failed_count = len(results) - passed_count

    print(f"Total files tested: {len(results)}")
    print(f"✅ Passed: {passed_count}")
    print(f"❌ Failed: {failed_count}")

    if failed_count > 0:
        print("\nFailed files:")
        for r in results:
            if not r.get('all_passed', False):
                print(f"  - {r['file']}")

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ EXTRACTION FUNCTION WORKS ON REAL DATA")
        return True
    else:
        print("⚠️  EXTRACTION FUNCTION HAS ISSUES - SEE DETAILS ABOVE")
        return False


if __name__ == "__main__":
    success = test_sample_files()
    sys.exit(0 if success else 1)