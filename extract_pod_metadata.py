#!/usr/bin/env python3
"""
Extract pod metadata from log files including timestamps and file size.
Combines with existing inventory data to create comprehensive metadata.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

def get_file_metadata(file_path: str) -> Dict[str, Optional[str]]:
    """
    Extract file metadata including creation and modification timestamps.

    Args:
        file_path: Path to the log file

    Returns:
        Dict with creation_timestamp, modification_timestamp, and log_size_bytes
    """
    try:
        stat = os.stat(file_path)

        # Get modification time (always available on Unix)
        mod_time = datetime.fromtimestamp(stat.st_mtime).isoformat()

        # Get birth time (creation time) - available on some Unix systems
        # Fall back to modification time if not available
        if hasattr(stat, 'st_birthtime'):
            creation_time = datetime.fromtimestamp(stat.st_birthtime).isoformat()
        else:
            # On Linux, st_birthtime is not available; use modification time as fallback
            creation_time = mod_time

        # Get file size
        file_size = stat.st_size

        return {
            "creation_timestamp": creation_time,
            "modification_timestamp": mod_time,
            "log_size_bytes": file_size
        }
    except Exception as e:
        print(f"Error getting metadata for {file_path}: {e}")
        return {
            "creation_timestamp": None,
            "modification_timestamp": None,
            "log_size_bytes": None
        }

def extract_timestamps_from_log_content(file_path: str) -> Dict[str, Optional[str]]:
    """
    Try to extract creation and deletion timestamps from log file content.

    This looks for Kubernetes pod lifecycle events in the logs.

    Args:
        file_path: Path to the log file

    Returns:
        Dict with creation_timestamp and deletion_timestamp if found
    """
    try:
        with open(file_path, 'r', errors='ignore') as f:
            # Read first 100 lines to find creation timestamp
            first_lines = []
            for i, line in enumerate(f):
                if i >= 100:
                    break
                first_lines.append(line.strip())

        # Reset and read last 100 lines to find deletion timestamp
        with open(file_path, 'r', errors='ignore') as f:
            # Read all lines and take last 100
            all_lines = f.readlines()
            last_lines = [line.strip() for line in all_lines[-100:]]

        # Look for common patterns in pod logs
        # These are heuristic - actual format varies by application
        creation_ts = None
        deletion_ts = None

        # Patterns that might indicate timestamps
        timestamp_patterns = [
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO format
            r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',  # Space-separated
            r'\w{3} \d{1,2} \d{2}:\d{2}:\d{2}',       # Syslog format
        ]

        # Try to extract first timestamp as creation hint
        for line in first_lines[:20]:  # Check first 20 lines
            # Simple extraction - look for ISO-like timestamps
            if 'T' in line and len(line) > 10:
                parts = line.split('T')
                if len(parts) >= 2:
                    date_part = parts[0].split()[-1]  # Get last part before T
                    time_part = parts[1].split()[0]   # Get first part after T
                    if len(date_part) == 10 and len(time_part) >= 8:
                        try:
                            # Try to parse as ISO timestamp
                            potential_ts = f"{date_part}T{time_part[:8]}"
                            datetime.fromisoformat(potential_ts.replace('Z', '+00:00'))
                            creation_ts = potential_ts
                            break
                        except:
                            continue

        # Try to extract last timestamp as deletion hint
        for line in reversed(last_lines[-20:]):  # Check last 20 lines
            if 'T' in line and len(line) > 10:
                parts = line.split('T')
                if len(parts) >= 2:
                    date_part = parts[0].split()[-1]
                    time_part = parts[1].split()[0]
                    if len(date_part) == 10 and len(time_part) >= 8:
                        try:
                            potential_ts = f"{date_part}T{time_part[:8]}"
                            datetime.fromisoformat(potential_ts.replace('Z', '+00:00'))
                            deletion_ts = potential_ts
                            break
                        except:
                            continue

        return {
            "creation_timestamp_from_content": creation_ts,
            "deletion_timestamp_from_content": deletion_ts
        }
    except Exception as e:
        print(f"Error extracting timestamps from {file_path}: {e}")
        return {
            "creation_timestamp_from_content": None,
            "deletion_timestamp_from_content": None
        }

def extract_pod_metadata(inventory_file: str, output_jsonl: str, output_json: str) -> None:
    """
    Extract complete pod metadata from log files and combine with existing inventory.

    Args:
        inventory_file: Path to the existing inventory JSON
        output_jsonl: Path to write the enhanced metadata as JSONL
        output_json: Path to write the enhanced metadata as JSON
    """
    # Load existing inventory
    print(f"Loading inventory from {inventory_file}...")
    with open(inventory_file, 'r') as f:
        inventory = json.load(f)

    entries = inventory.get('inventory', [])
    total = len(entries)

    print(f"Processing {total} pod log files...")

    complete_metadata = []

    for i, entry in enumerate(entries, 1):
        log_file_path = entry.get('log_file_path')
        if not log_file_path:
            continue

        # Convert relative path to absolute
        full_path = os.path.join('/home/coding/aide-de-camp', log_file_path)

        if not os.path.exists(full_path):
            print(f"Warning: File not found: {full_path}")
            # Add entry with null metadata
            complete_metadata.append({
                'pod_name': entry.get('pod_name'),
                'namespace': entry.get('namespace'),
                'log_file_path': log_file_path,
                'analysis_file_path': entry.get('analysis_file_path'),
                'creation_timestamp': None,
                'deletion_timestamp': None,
                'log_size_bytes': 0,
                'error': 'File not found'
            })
            continue

        print(f"[{i}/{total}] Processing {entry.get('pod_name')}...")

        # Get file metadata
        file_metadata = get_file_metadata(full_path)

        # Try to extract timestamps from content
        content_timestamps = extract_timestamps_from_log_content(full_path)

        # Combine all metadata
        combined_entry = {
            # Existing fields
            'pod_name': entry.get('pod_name'),
            'namespace': entry.get('namespace'),
            'log_file_path': log_file_path,
            'analysis_file_path': entry.get('analysis_file_path'),

            # Timestamp fields
            'creation_timestamp': content_timestamps.get('creation_timestamp_from_content') or file_metadata.get('creation_timestamp'),
            'deletion_timestamp': content_timestamps.get('deletion_timestamp_from_content'),
            'file_creation_timestamp': file_metadata.get('creation_timestamp'),
            'file_modification_timestamp': file_metadata.get('modification_timestamp'),

            # Size
            'log_size_bytes': file_metadata.get('log_size_bytes'),

            # Additional metadata
            'has_analysis': entry.get('has_analysis', False),
            'collection_source': entry.get('collection_source'),
        }

        complete_metadata.append(combined_entry)

    # Write JSONL output
    print(f"\nWriting JSONL to {output_jsonl}...")
    with open(output_jsonl, 'w') as f:
        for entry in complete_metadata:
            f.write(json.dumps(entry) + '\n')

    # Write JSON output
    print(f"Writing JSON to {output_json}...")
    with open(output_json, 'w') as f:
        json.dump(complete_metadata, f, indent=2)

    # Statistics
    with_creation = sum(1 for m in complete_metadata if m.get('creation_timestamp'))
    with_deletion = sum(1 for m in complete_metadata if m.get('deletion_timestamp'))
    total_size = sum(m.get('log_size_bytes', 0) for m in complete_metadata)

    print(f"\nDone! Processed {total} files.")
    print(f"  Files with creation timestamp: {with_creation} ({with_creation*100//total}%)")
    print(f"  Files with deletion timestamp: {with_deletion} ({with_deletion*100//total if total > 0 else 0}%)")
    print(f"  Total size: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")

def main():
    """Main entry point."""
    inventory_file = '/home/coding/aide-de-camp/tmp/pod-logs-inventory.json'
    output_jsonl = '/home/coding/aide-de-camp/tmp/pod-metadata-complete.jsonl'
    output_json = '/home/coding/aide-de-camp/tmp/pod-metadata-complete.json'

    extract_pod_metadata(inventory_file, output_jsonl, output_json)

if __name__ == '__main__':
    main()