#!/usr/bin/env python3
"""
Process all pod log files and generate complete JSONL with extracted metadata.

This script:
1. Loads the pod-logs inventory
2. Applies extraction function to all log files
3. Combines with existing inventory data
4. Outputs complete records as JSONL
5. Verifies all pods have metadata extracted
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add the src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from extract_log_file_metadata import (
    extract_pod_metadata,
    get_file_size,
    get_file_mtime,
    extract_first_log_timestamp,
    extract_deletion_timestamp_from_log,
    is_valid_iso_timestamp
)


def load_inventory(inventory_file: Path) -> Dict[str, Any]:
    """Load the pod logs inventory."""
    try:
        with open(inventory_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading inventory: {e}")
        return {}


def get_analysis_data(analysis_path: Optional[str], repo_root: Path) -> Dict[str, Any]:
    """Load analysis data if it exists."""
    if not analysis_path:
        return {}

    full_path = repo_root / analysis_path
    if not full_path.exists():
        return {}

    try:
        with open(full_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load analysis file {analysis_path}: {e}")
        return {}


def extract_deletion_from_analysis(analysis_data: Dict[str, Any]) -> Optional[str]:
    """Extract deletion timestamp from analysis metadata."""
    if not analysis_data:
        return None

    # Check if there's deletion info in pattern timestamps
    key_timestamps = analysis_data.get("key_timestamps", {})

    # Look for deletion-related timestamps
    for key in ["deletion_timestamp", "deleted_at", "termination_timestamp", "terminated_at"]:
        if key in key_timestamps:
            return key_timestamps[key]

    # Check pattern timestamps for deletion indicators
    for pattern_type in ["oom_kill", "error", "crash"]:
        last_key = f"{pattern_type}_last"
        if last_key in key_timestamps:
            # For these patterns, the last occurrence might indicate deletion
            return key_timestamps[last_key]

    return None


def create_complete_record(
    inventory_item: Dict[str, Any],
    repo_root: Path,
    analysis_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a complete record with all metadata."""

    # Start with inventory data
    record = inventory_item.copy()

    # Get log file path
    log_file_relative = inventory_item.get('log_file_path')
    if not log_file_relative:
        return record

    log_file_full = repo_root / log_file_relative

    # Extract metadata from log file
    file_metadata = extract_pod_metadata(str(log_file_full))

    # Add metadata to record
    record.update({
        'log_size_bytes': file_metadata.get('log_size_bytes'),
        'creation_timestamp': file_metadata.get('creation_timestamp'),
        'deletion_timestamp': file_metadata.get('deletion_timestamp'),
        'first_log_timestamp': file_metadata.get('first_log_timestamp') if 'first_log_timestamp' in file_metadata else None
    })

    # Try to get deletion timestamp from analysis data if not found in log
    if not record.get('deletion_timestamp') and analysis_data:
        analysis_deletion = extract_deletion_from_analysis(analysis_data)
        if analysis_deletion:
            record['deletion_timestamp'] = analysis_deletion
            record['deletion_source'] = 'analysis_metadata'
    elif record.get('deletion_timestamp'):
        record['deletion_source'] = 'log_content'

    # Add file existence check
    record['file_exists'] = log_file_full.exists()

    # Add processing timestamp
    record['processed_at'] = datetime.now().isoformat()

    # Add detected patterns from analysis if available
    if analysis_data:
        record['detected_patterns'] = analysis_data.get('detected_patterns', [])
        record['analysis_timestamps'] = analysis_data.get('key_timestamps', {})
    else:
        record['detected_patterns'] = []
        record['analysis_timestamps'] = {}

    return record


def main():
    """Main function to process all pod log files."""
    repo_root = Path('/home/coding/aide-de-camp')
    inventory_file = repo_root / 'tmp' / 'pod-logs-inventory.json'
    output_jsonl = repo_root / 'pod-logs-complete-unified.jsonl'

    # Load inventory
    print("Loading pod logs inventory...")
    inventory_data = load_inventory(inventory_file)

    if not inventory_data:
        print("Error: No inventory data found")
        return

    inventory_items = inventory_data.get('inventory', [])
    print(f"Found {len(inventory_items)} items in inventory")

    # Process each item
    complete_records = []
    successful_count = 0
    missing_files = 0
    no_metadata = 0

    for i, item in enumerate(inventory_items, 1):
        print(f"Processing {i}/{len(inventory_items)}: {item.get('pod_name')}", end='\r')

        # Load analysis data if available
        analysis_path = item.get('analysis_file_path')
        analysis_data = None
        if analysis_path:
            analysis_data = get_analysis_data(analysis_path, repo_root)

        # Create complete record
        record = create_complete_record(item, repo_root, analysis_data)
        complete_records.append(record)

        # Track statistics
        if not record.get('file_exists'):
            missing_files += 1
        elif record.get('creation_timestamp') or record.get('log_size_bytes'):
            successful_count += 1
        else:
            no_metadata += 1

    # Write to JSONL
    print(f"\n\nWriting complete records to: {output_jsonl}")
    with open(output_jsonl, 'w') as f:
        for record in complete_records:
            f.write(json.dumps(record) + '\n')

    # Print summary
    print(f"\n{'='*60}")
    print("PROCESSING SUMMARY")
    print(f"{'='*60}")
    print(f"Total records: {len(complete_records)}")
    print(f"Successfully extracted metadata: {successful_count}")
    print(f"Missing log files: {missing_files}")
    print(f"No metadata extracted: {no_metadata}")

    # Calculate total size
    total_size = sum(
        record.get('log_size_bytes') or 0
        for record in complete_records
        if record.get('file_exists')
    )
    print(f"Total log file size: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")

    # Count entries with various timestamps
    with_creation = sum(1 for r in complete_records if r.get('creation_timestamp'))
    with_deletion = sum(1 for r in complete_records if r.get('deletion_timestamp'))
    with_size = sum(1 for r in complete_records if r.get('log_size_bytes'))

    print(f"\nRecords with creation_timestamp: {with_creation}")
    print(f"Records with deletion_timestamp: {with_deletion}")
    print(f"Records with log_size_bytes: {with_size}")

    # Show sample records
    print(f"\n{'='*60}")
    print("SAMPLE RECORDS (first 3)")
    print(f"{'='*60}")
    for i, record in enumerate(complete_records[:3], 1):
        print(f"\n{i}. Pod: {record.get('pod_name')}")
        print(f"   Namespace: {record.get('namespace')}")
        print(f"   Log file: {record.get('log_file_path')}")
        print(f"   File exists: {record.get('file_exists')}")
        print(f"   Size: {record.get('log_size_bytes', 'N/A')} bytes")
        print(f"   Created: {record.get('creation_timestamp', 'N/A')}")
        print(f"   Deleted: {record.get('deletion_timestamp', 'N/A')}")
        print(f"   First log: {record.get('first_log_timestamp', 'N/A')}")
        print(f"   Analysis: {'Yes' if record.get('has_analysis') else 'No'}")
        if record.get('detected_patterns'):
            print(f"   Patterns: {', '.join(record.get('detected_patterns', []))}")

    # Verification
    print(f"\n{'='*60}")
    print("VERIFICATION")
    print(f"{'='*60}")

    # Check that all pods in inventory have been processed
    expected_count = len(inventory_items)
    actual_count = len(complete_records)

    if expected_count == actual_count:
        print(f"✓ All {expected_count} pods from inventory have been processed")
    else:
        print(f"✗ Expected {expected_count} records, got {actual_count}")

    # Check for missing critical fields
    missing_creation = [r for r in complete_records if r.get('file_exists') and not r.get('creation_timestamp')]
    missing_size = [r for r in complete_records if r.get('file_exists') and not r.get('log_size_bytes')]

    if missing_creation:
        print(f"⚠ {len(missing_creation)} records exist but have no creation_timestamp")
    if missing_size:
        print(f"⚠ {len(missing_size)} records exist but have no log_size_bytes")

    print(f"\n✓ Complete JSONL written to: {output_jsonl}")
    print(f"✓ Total records: {len(complete_records)}")


if __name__ == "__main__":
    main()