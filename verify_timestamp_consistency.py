#!/usr/bin/env python3
"""
Verify that extraction results match creation_timestamp expectations.
"""

import json
import os
from pathlib import Path
from datetime import datetime

def verify_creation_timestamp_accuracy():
    """Verify that creation_timestamps match actual file mtime."""

    print("=" * 70)
    print("CREATION TIMESTAMP ACCURACY VERIFICATION")
    print("=" * 70)

    unified_file = Path("/home/coding/aide-de-camp/data/log-files-unified.json")

    with open(unified_file, 'r') as f:
        data = json.load(f)

    # Check actual files only
    actual_files = [k for k, v in data.items()
                    if not v.get('log_file_path', '').startswith(('summary/', 'array-data/'))
                    and os.path.exists(k)]

    print(f"\nChecking {len(actual_files)} actual files...")

    mismatches = []
    matches = []

    for file_path in actual_files:
        entry = data[file_path]

        # Get actual file mtime
        actual_mtime = os.path.getmtime(file_path)
        actual_timestamp = datetime.fromtimestamp(actual_mtime).isoformat()

        # Get extracted creation timestamp
        extracted_timestamp = entry.get('creation_timestamp')

        if extracted_timestamp:
            # Compare (allow for minor timezone format differences)
            extracted_normalized = extracted_timestamp.replace('+00:00', 'Z').split('.')[0]
            actual_normalized = actual_timestamp.replace('+00:00', 'Z').split('.')[0]

            if extracted_normalized == actual_normalized:
                matches.append(file_path)
            else:
                mismatches.append({
                    'file': file_path,
                    'extracted': extracted_timestamp,
                    'actual': actual_timestamp,
                    'extracted_size': entry.get('log_size_bytes'),
                    'actual_size': os.path.getsize(file_path)
                })

    print(f"\n✅ Matches: {len(matches)}")
    print(f"❌ Mismatches: {len(mismatches)}")

    if mismatches:
        print(f"\n=== TIMESTAMP MISMATCHES ===")
        for mismatch in mismatches[:5]:
            print(f"\n{mismatch['file']}")
            print(f"  Extracted: {mismatch['extracted']}")
            print(f"  Actual:   {mismatch['actual']}")
            print(f"  Size: extracted={mismatch['extracted_size']}, actual={mismatch['actual_size']}")

def verify_deletion_timestamp_expectations():
    """Verify deletion_timestamp expectations."""

    print("\n" + "=" * 70)
    print("DELETION TIMESTAMP EXPECTATIONS")
    print("=" * 70)

    unified_file = Path("/home/coding/aide-de-camp/data/log-files-unified.json")

    with open(unified_file, 'r') as f:
        data = json.load(f)

    # Files with deletion timestamps
    with_deletion = [(k, v) for k, v in data.items()
                     if v.get('deletion_timestamp') and not k.startswith(('summary/', 'array-data/'))]

    print(f"\nFiles with deletion timestamps: {len(with_deletion)}")

    for file_path, entry in with_deletion:
        print(f"\n{file_path}")
        print(f"  Deletion timestamp: {entry.get('deletion_timestamp')}")
        print(f"  File exists: {os.path.exists(file_path)}")

        # If file still exists, deletion_timestamp might indicate when it WILL be deleted
        # or it might be erroneous
        if os.path.exists(file_path):
            print(f"  ⚠️  File still exists - deletion timestamp may be pending or erroneous")

def check_jsonl_file_patterns():
    """Check for JSONL format variations and edge cases."""

    print("\n" + "=" * 70)
    print("JSONL FILE FORMAT ANALYSIS")
    print("=" * 70)

    jsonl_files = list(Path("/home/coding/aide-de-camp/logs").glob("*.jsonl"))

    print(f"\nFound {len(jsonl_files)} JSONL files in logs/")

    for jsonl_file in jsonl_files:
        print(f"\n{jsonl_file.name}:")

        # Check if it's valid JSONL
        try:
            with open(jsonl_file, 'r') as f:
                lines = f.readlines()

            line_count = len(lines)
            file_size = jsonl_file.stat().st_size

            print(f"  Lines: {line_count}, Size: {file_size:,} bytes")

            # Check first few lines for JSON validity
            valid_json = 0
            for i, line in enumerate(lines[:5]):
                try:
                    json.loads(line.strip())
                    valid_json += 1
                except json.JSONDecodeError:
                    pass

            if line_count == 1 and valid_json == 1:
                # Single JSON object on one line
                print(f"  Format: Single JSON object (not JSONL)")
            elif valid_json == min(5, line_count):
                print(f"  Format: Valid JSONL (one JSON per line)")
            else:
                print(f"  Format: Mixed or invalid JSONL ({valid_json}/{min(5, line_count)} valid)")

        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    verify_creation_timestamp_accuracy()
    verify_deletion_timestamp_expectations()
    check_jsonl_file_patterns()