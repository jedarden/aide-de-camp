#!/usr/bin/env python3
"""
Extract complete pod metadata from log files including timestamps and file size.
Combines with existing inventory data to create comprehensive metadata ready for JSONL.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

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
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            return {
                "creation_timestamp_from_content": None,
                "deletion_timestamp_from_content": None
            }

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

        creation_ts = None
        deletion_ts = None

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

def extract_pod_metadata(inventory_file: str, output_jsonl: str) -> None:
    """
    Extract complete pod metadata from log files and write to JSONL.

    Args:
        inventory_file: Path to the existing inventory JSON
        output_jsonl: Path to write the enhanced metadata JSONL
    """
    # Load existing inventory
    print(f"Loading inventory from {inventory_file}...")
    with open(inventory_file, 'r') as f:
        inventory = json.load(f)

    inventory_items = inventory.get('inventory', [])
    total = len(inventory_items)

    print(f"Processing {total} pod log files...")

    results = []

    for i, item in enumerate(inventory_items, 1):
        log_file_path = item.get('log_file_path')
        if not log_file_path:
            continue

        # Convert relative path to absolute
        full_path = os.path.join('/home/coding/aide-de-camp', log_file_path)

        if not os.path.exists(full_path):
            print(f"Warning: File not found: {full_path}")
            # Still include the record with null metadata
            result = {
                "pod_name": item.get('pod_name'),
                "namespace": item.get('namespace'),
                "creation_timestamp": None,
                "deletion_timestamp": None,
                "log_file_path": log_file_path,
                "analysis_file_path": item.get('analysis_file_path'),
                "log_size_bytes": None,
                "file_exists": False
            }
            results.append(result)
            continue

        print(f"[{i}/{total}] Processing {log_file_path}...")

        # Get file metadata
        file_metadata = get_file_metadata(full_path)

        # Try to extract timestamps from content
        content_timestamps = extract_timestamps_from_log_content(full_path)

        # Determine best creation timestamp (prefer content, fall back to file metadata)
        if content_timestamps['creation_timestamp_from_content']:
            creation_ts = content_timestamps['creation_timestamp_from_content']
        else:
            creation_ts = file_metadata['creation_timestamp']

        # Deletion timestamp only from content (if present)
        deletion_ts = content_timestamps['deletion_timestamp_from_content']

        result = {
            "pod_name": item.get('pod_name'),
            "namespace": item.get('namespace'),
            "creation_timestamp": creation_ts,
            "deletion_timestamp": deletion_ts,
            "log_file_path": log_file_path,
            "analysis_file_path": item.get('analysis_file_path'),
            "log_size_bytes": file_metadata['log_size_bytes'],
            "file_exists": True,
            "file_creation_timestamp": file_metadata['creation_timestamp'],
            "file_modification_timestamp": file_metadata['modification_timestamp'],
            "creation_timestamp_from_content": content_timestamps['creation_timestamp_from_content'],
            "deletion_timestamp_from_content": content_timestamps['deletion_timestamp_from_content']
        }

        results.append(result)

    # Write to JSONL
    print(f"\nWriting enhanced metadata to {output_jsonl}...")
    with open(output_jsonl, 'w') as f:
        for result in results:
            f.write(json.dumps(result) + '\n')

    # Summary statistics
    files_with_creation = sum(1 for r in results if r.get('creation_timestamp'))
    files_with_deletion = sum(1 for r in results if r.get('deletion_timestamp'))
    files_with_content_creation = sum(1 for r in results if r.get('creation_timestamp_from_content'))
    total_size = sum(r.get('log_size_bytes', 0) or 0 for r in results)

    print(f"\nDone! Processed {total} files.")
    print(f"  Files with creation timestamp: {files_with_creation}/{total}")
    print(f"  Files with deletion timestamp: {files_with_deletion}/{total}")
    print(f"  Files with content-based creation timestamp: {files_with_content_creation}/{total}")
    print(f"  Total log size: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")
    print(f"  Output written to: {output_jsonl}")

def main():
    """Main entry point."""
    inventory_file = '/home/coding/aide-de-camp/tmp/pod-logs-inventory.json'
    output_jsonl = '/home/coding/aide-de-camp/pod-logs-complete-metadata.jsonl'

    extract_pod_metadata(inventory_file, output_jsonl)

if __name__ == '__main__':
    main()