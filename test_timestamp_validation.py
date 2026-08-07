#!/usr/bin/env python3
"""
Test the ISO timestamp validation fix.
"""

import sys
sys.path.insert(0, '/home/coding/aide-de-camp')

from extract_log_file_metadata import is_valid_iso_timestamp
from datetime import datetime

def test_is_valid_iso_timestamp():
    """Test the ISO timestamp validation function."""
    print("=" * 70)
    print("Testing ISO Timestamp Validation")
    print("=" * 70)

    test_cases = [
        # (input, expected_result, description)
        ("2026-08-06T15:30:00Z", True, "Valid ISO with Z"),
        ("2026-08-06T15:30:00+00:00", True, "Valid ISO with +00:00"),
        ("2026-08-06T15:30:00", True, "Valid ISO without timezone"),
        ("2026-08-06 15:30:00", False, "Not ISO format (space instead of T)"),
        ("unknown", False, "String value 'unknown'"),
        ("", False, "Empty string"),
        (None, False, "None value"),
        ("15:30:00", False, "Time only, no date"),
        ("2026-08-06", False, "Date only, no time"),
        ("2026-08-06T15:30:00.123456Z", True, "Valid ISO with microseconds"),
        ("invalid-timestamp", False, "Invalid format"),
    ]

    passed = 0
    failed = 0

    for input_val, expected, description in test_cases:
        result = is_valid_iso_timestamp(input_val)
        status = "✅" if result == expected else "❌"

        if result == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} {description}")
        print(f"   Input: {input_val!r}")
        print(f"   Expected: {expected}, Got: {result}")
        print()

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0

if __name__ == "__main__":
    success = test_is_valid_iso_timestamp()
    sys.exit(0 if success else 1)