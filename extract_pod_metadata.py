#!/usr/bin/env python3
"""
Extract pod metadata from log files.

This script reads the existing pod-logs-index.jsonl and enhances it with
additional metadata extracted from the log files themselves, including:
- creation_timestamp (from file metadata or first log entry)
- deletion_timestamp (null unless explicitly found)
- log_size_bytes (verified from file stats)
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple


# Timestamp patterns found in log files
TIMESTAMP_PATTERNS = [
    # ISO 8601 with timezone (like 2026-08-03T17:03:54.634456037-04:00)
    r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z))',
    # Common log format (like [03/Aug/2026:21:03:54 +0000])
    r'\[(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}\s[+-]\d{4})\]',
    # Simple ISO (like 2026-08-03 17:03:54)
    r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
    # Syslog format (like Aug  3 17:03:54)
    r'^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})',
]


def parse_timestamp(ts_string: str) -> Optional[datetime]:
    """Parse a timestamp string into a datetime object."""
    if not ts_string:
        return None

    # Try different datetime formats
    formats = [
        '%Y-%m-%dT%H:%M:%S.%f%z',  # ISO 8601 with microseconds and timezone
        '%Y-%m-%dT%H:%M:%S%z',     # ISO 8601 with timezone
        '%Y-%m-%dT%H:%M:%S.%f',    # ISO 8601 with microseconds, no timezone
        '%Y-%m-%dT%H:%M:%S',       # ISO 8601, no timezone
        '%Y-%m-%d %H:%M:%S',       # Simple date time
        '%d/%b/%Y:%H:%M:%S %z',    # Common log format
        '%b %d %H:%M:%S',          # Syslog format (no year)
    ]

    for fmt in formats:
        try:
            return datetime.strptime(ts_string, fmt)
        except (ValueError, TypeError):
            continue

    return None


def extract_timestamps_from_log(log_path: Path) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Extract first and last timestamps from a log file.

    Returns:
        Tuple of (first_timestamp, last_timestamp) as datetime objects or None
    """
    if not log_path.exists() or log_path.stat().st_size == 0:
        return None, None

    first_ts = None
    last_ts = None

    try:
        with open(log_path, 'r', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Try each timestamp pattern
                for pattern in TIMESTAMP_PATTERNS:
                    match = re.search(pattern, line)
                    if match:
                        ts_str = match.group(1)
                        parsed_ts = parse_timestamp(ts_str)
                        if parsed_ts:
                            if first_ts is None:
                                first_ts = parsed_ts
                            last_ts = parsed_ts
                            break  # Found a timestamp in this line, move to next line
                if first_ts is not None:
                    break  # Found first timestamp, can stop scanning for first

        # If we found first timestamp, scan entire file for last timestamp
        if first_ts is not None:
            with open(log_path, 'r', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    for pattern in TIMESTAMP_PATTERNS:
                        match = re.search(pattern, line)
                        if match:
                            ts_str = match.group(1)
                            parsed_ts = parse_timestamp(ts_str)
                            if parsed_ts:
                                last_ts = parsed_ts
                                break
    except Exception as e:
        print(f"  Error reading {log_path}: {e}")

    return first_ts, last_ts


def get_file_metadata(log_path: Path) -> Dict:
    """
    Get file metadata including timestamps and size.

    Returns:
        Dict with creation_timestamp, deletion_timestamp, and log_size_bytes
    """
    metadata = {
        'creation_timestamp': None,
        'deletion_timestamp': None,
        'log_size_bytes': 0
    }

    if not log_path.exists():
        return metadata

    try:
        stat_info = log_path.stat()
        metadata['log_size_bytes'] = stat_info.st_size

        # Use birth time (creation time) as creation_timestamp
        # Convert to ISO 8601 format
        if hasattr(stat_info, 'st_birthtime'):
            birth_time = datetime.fromtimestamp(stat_info.st_birthtime)
            metadata['creation_timestamp'] = birth_time.isoformat()
        else:
            # Fallback to ctime (metadata change time) on systems without birthtime
            birth_time = datetime.fromtimestamp(stat_info.st_ctime)
            metadata['creation_timestamp'] = birth_time.isoformat()

        # Also extract timestamps from log content for better accuracy
        first_ts, last_ts = extract_timestamps_from_log(log_path)

        # Use log timestamp if available and more recent than file birth
        if first_ts:
            log_first_ts = first_ts.isoformat()
            # Prefer log timestamp if file birth time is not available
            if not metadata['creation_timestamp']:
                metadata['creation_timestamp'] = log_first_ts
            # Could also compare and use the more accurate one, but file birth is fine

        # deletion_timestamp stays null unless there's explicit deletion info
        # (not typically found in log files)

    except Exception as e:
        print(f"  Error getting metadata for {log_path}: {e}")

    return metadata


def update_index_with_metadata(index_file: Path, repo_root: Path):
    """
    Update the pod-logs-index.jsonl with extracted metadata.
    """
    if not index_file.exists():
        print(f"Error: Index file {index_file} does not exist")
        return

    # Read existing index
    updated_entries = []
    missing_files = []
    updated_count = 0

    print(f"Reading index from: {index_file}")

    with open(index_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                entry = json.loads(line)

                # Get log file path
                log_file_rel = entry.get('log_file_metadata', {}).get('log_file_path')
                if not log_file_rel:
                    print(f"  Line {line_num}: Missing log_file_path")
                    updated_entries.append(entry)
                    continue

                # Resolve full path
                log_file_abs = repo_root / log_file_rel

                if not log_file_abs.exists():
                    missing_files.append(log_file_rel)
                    print(f"  Line {line_num}: File not found: {log_file_rel}")
                    updated_entries.append(entry)
                    continue

                # Extract metadata from log file
                file_metadata = get_file_metadata(log_file_abs)

                # Update entry if metadata was missing or different
                needs_update = False
                pod_id = entry.get('pod_identification', {})

                if not pod_id.get('creation_timestamp') and file_metadata['creation_timestamp']:
                    pod_id['creation_timestamp'] = file_metadata['creation_timestamp']
                    needs_update = True

                # deletion_timestamp is typically null, so we don't overwrite it
                # log_size_bytes might already be set, but we verify it
                log_metadata = entry.get('log_file_metadata', {})
                if log_metadata.get('log_size_bytes') != file_metadata['log_size_bytes']:
                    log_metadata['log_size_bytes'] = file_metadata['log_size_bytes']
                    needs_update = True

                if needs_update:
                    updated_count += 1

                entry['pod_identification'] = pod_id
                entry['log_file_metadata'] = log_metadata
                updated_entries.append(entry)

            except json.JSONDecodeError as e:
                print(f"  Line {line_num}: JSON decode error: {e}")
                continue
            except Exception as e:
                print(f"  Line {line_num}: Error processing entry: {e}")
                continue

    # Write updated index
    print(f"\nWriting updated index to: {index_file}")
    with open(index_file, 'w') as f:
        for entry in updated_entries:
            f.write(json.dumps(entry) + '\n')

    print(f"Updated {updated_count} entries")
    if missing_files:
        print(f"Warning: {len(missing_files)} log files were not found:")
        for mf in missing_files[:5]:  # Show first 5
            print(f"  - {mf}")
        if len(missing_files) > 5:
            print(f"  ... and {len(missing_files) - 5} more")


def main():
    """Main function."""
    repo_root = Path('/home/coding/aide-de-camp')
    index_file = repo_root / 'pod-logs-index.jsonl'

    print("Extracting Pod Metadata from Log Files")
    print("=" * 50)

    update_index_with_metadata(index_file, repo_root)

    print("\nDone!")


if __name__ == '__main__':
    main()