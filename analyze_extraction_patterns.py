#!/usr/bin/env python3
"""
Analyze extraction results to identify patterns and edge cases.
"""

import json
import os
from pathlib import Path
from collections import defaultdict

def analyze_extraction_results():
    """Analyze the unified extraction results to find patterns."""

    unified_file = Path("/home/coding/aide-de-camp/data/log-files-unified.json")

    with open(unified_file, 'r') as f:
        data = json.load(f)

    # Categorize entries
    categories = {
        'summary': [],
        'array_data': [],
        'actual_files': [],
        'missing_files': [],
        'with_deletion_timestamp': [],
        'with_creation_timestamp': [],
        'timestamp_issues': []
    }

    # Analysis counters
    stats = {
        'total_entries': len(data),
        'null_file_sizes': 0,
        'null_creation': 0,
        'with_deletion': 0,
        'actual_file_count': 0
    }

    for key, value in data.items():
        log_path = value.get('log_file_path', '')

        # Categorize by type
        if log_path.startswith('summary/'):
            categories['summary'].append(key)
        elif log_path.startswith('array-data/'):
            categories['array_data'].append(key)
        else:
            # This is an actual file path
            categories['actual_files'].append(key)
            stats['actual_file_count'] += 1

            # Check if file exists
            if os.path.exists(log_path):
                # Check metadata
                if value.get('log_size_bytes') is None:
                    categories['missing_files'].append(key)
                    stats['null_file_sizes'] += 1

                if value.get('creation_timestamp') is None:
                    stats['null_creation'] += 1

                if value.get('deletion_timestamp'):
                    categories['with_deletion_timestamp'].append(key)
                    stats['with_deletion'] += 1

                if value.get('creation_timestamp'):
                    categories['with_creation_timestamp'].append(key)

                # Check for timestamp format issues
                for ts_field in ['creation_timestamp', 'deletion_timestamp', 'first_log_timestamp']:
                    ts = value.get(ts_field)
                    if ts:
                        try:
                            # Try to parse as ISO format
                            if 'T' not in ts or not any(ts.endswith(x) for x in ['Z', '+00:00', '+00:00:00']):
                                if not ts.startswith('20'):  # Basic sanity check
                                    categories['timestamp_issues'].append((key, ts_field, ts))
                        except Exception as e:
                            categories['timestamp_issues'].append((key, ts_field, ts))

    # Print analysis
    print("=" * 70)
    print("EXTRACTION RESULTS ANALYSIS")
    print("=" * 70)

    print(f"\nTotal entries: {stats['total_entries']}")
    print(f"Summary entries: {len(categories['summary'])}")
    print(f"Array-data entries: {len(categories['array_data'])}")
    print(f"Actual file entries: {stats['actual_file_count']}")

    print(f"\n=== Actual Files Analysis ===")
    print(f"Files with null sizes: {stats['null_file_sizes']}")
    print(f"Files with null creation timestamps: {stats['null_creation']}")
    print(f"Files with deletion timestamps: {stats['with_deletion']}")

    print(f"\n=== Timestamp Issues ===")
    if categories['timestamp_issues']:
        print(f"Found {len(categories['timestamp_issues'])} potential timestamp format issues:")
        for key, field, value in categories['timestamp_issues'][:5]:
            print(f"  - {key}: {field} = {value}")
    else:
        print("No obvious timestamp format issues")

    # Sample analysis of actual files
    print(f"\n=== Sample Actual Files ===")
    sample_files = categories['actual_files'][:5]
    for key in sample_files:
        entry = data[key]
        print(f"\n{key}:")
        print(f"  Size: {entry.get('log_size_bytes')} bytes")
        print(f"  Creation: {entry.get('creation_timestamp')}")
        print(f"  Deletion: {entry.get('deletion_timestamp')}")

    # Check for JSONL files
    print(f"\n=== JSONL Files Analysis ===")
    jsonl_files = [k for k in categories['actual_files'] if k.endswith('.jsonl')]
    print(f"Found {len(jsonl_files)} JSONL files")

    for jsonl_file in jsonl_files[:3]:
        entry = data[jsonl_file]
        print(f"\n{jsonl_file}:")
        print(f"  Size: {entry.get('log_size_bytes')} bytes")
        print(f"  Creation: {entry.get('creation_timestamp')}")

        # Verify actual file properties
        if os.path.exists(jsonl_file):
            actual_size = os.path.getsize(jsonl_file)
            with open(jsonl_file, 'r') as f:
                actual_lines = len(f.readlines())

            print(f"  Actual size: {actual_size} bytes")
            print(f"  Actual lines: {actual_lines}")

            if entry.get('log_size_bytes') != actual_size:
                print(f"  ⚠️ SIZE MISMATCH!")
            if 'line_count' in entry and entry['line_count'] != actual_lines:
                print(f"  ⚠️ LINE COUNT MISMATCH!")

if __name__ == "__main__":
    analyze_extraction_results()