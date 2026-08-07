#!/usr/bin/env python3
"""
Construct pod-logs-index.jsonl from collected metadata.
Combines data from steps 1-3 and outputs schema-compliant JSONL.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

def parse_pod_name_from_log_path(log_path: str) -> Optional[str]:
    """Extract pod name from log file path."""
    # Try to match patterns like:
    # - pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log
    # - pbx-web-pbx-web-5ff68464d-lcfcp.log
    # - whisper-stt-whisper-stt-847fd8d7b9-b8rsj.log

    filename = Path(log_path).name

    # Remove file extension
    name_without_ext = filename.replace('.log', '')

    # Remove prefixes
    if name_without_ext.startswith('pod-'):
        name_without_ext = name_without_ext[4:]

    # Remove date suffix like -2026-08-06
    name_without_ext = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', name_without_ext)

    # Remove stream suffixes like -current, -previous, -stderr
    name_without_ext = re.sub(r'-(current|previous|stderr)$', '', name_without_ext)

    return name_without_ext if name_without_ext else None

def parse_namespace_from_path(log_path: str) -> Optional[str]:
    """Extract namespace from log file path."""
    # Try patterns like:
    # - research/pbx-web-30days/pod-logs/ -> pbx-web
    # - research/whisper-stt-30days/pod-logs/ -> whisper-stt

    if 'pbx-web-30days' in log_path:
        return 'pbx-web'
    elif 'whisper-stt-30days' in log_path:
        return 'whisper-stt'

    # Try to extract from the path
    match = re.search(r'([a-z][a-z0-9\-]*)-30days', log_path)
    if match:
        return match.group(1)

    return 'default'

def parse_log_type_from_path(log_path: str) -> Optional[str]:
    """Extract log type from filename."""
    filename = Path(log_path).name

    if '-stderr.log' in filename:
        return 'stderr'
    elif '-previous.log' in filename:
        return 'previous'
    elif '-current.log' in filename:
        return 'current'

    return None

def parse_collection_date_from_path(log_path: str) -> Optional[str]:
    """Extract collection date from filename."""
    # Look for patterns like -2026-08-06 in filename
    match = re.search(r'-(\d{4}-\d{2}-\d{2})', log_path)
    if match:
        return match.group(1)

    # Default to today if not found
    return datetime.now().strftime('%Y-%m-%d')

def format_timestamp_iso(timestamp: Any) -> Optional[str]:
    """Format timestamp to ISO 8601 with Z suffix."""
    if timestamp is None or timestamp == '' or timestamp == 'unknown':
        return None

    # If already in ISO format, ensure Z suffix
    ts_str = str(timestamp)
    if 'T' in ts_str:
        # Already ISO-like
        if ts_str.endswith('Z'):
            return ts_str
        # Add Z if missing timezone
        return ts_str + 'Z'

    return None

def normalize_pattern_detection(patterns: list, timestamps_obj: Dict, pattern_counts: Dict) -> Dict:
    """Normalize pattern detection data to schema format."""
    result = {
        "startup": {"count": 0, "timestamps": [], "samples": []},
        "oom_kill": {"count": 0, "timestamps": [], "samples": []},
        "error": {"count": 0, "timestamps": [], "samples": []},
        "performance": {"count": 0, "timestamps": [], "samples": []}
    }

    # Get detected pattern types
    detected = patterns if isinstance(patterns, list) else []

    for pattern_type in ['startup', 'oom_kill', 'error', 'performance']:
        count = pattern_counts.get(pattern_type, 0) if pattern_counts else 0

        # Extract timestamps for this pattern type
        timestamps = []
        if pattern_type in timestamps_obj:
            # Handle different timestamp formats
            ts_data = timestamps_obj[pattern_type]
            if isinstance(ts_data, list):
                timestamps = [str(t) for t in ts_data]
            elif isinstance(ts_data, str):
                timestamps = [ts_data]

        # Ensure we have exactly count timestamps
        if len(timestamps) > count:
            timestamps = timestamps[:count]
        elif len(timestamps) < count:
            # Pad with "unknown" if needed
            timestamps.extend(['unknown'] * (count - len(timestamps)))

        result[pattern_type] = {
            "count": count,
            "timestamps": timestamps,
            "samples": []  # We don't have sample messages in the current data
        }

    return result

def transform_to_schema(entry_key: str, entry_data: Dict) -> Optional[Dict]:
    """Transform a unified data entry to schema format."""

    # Skip non-pod entries (summaries, array-data, etc.)
    if not entry_key.startswith('/') and not entry_key.startswith('research/'):
        return None

    log_path = entry_data.get('log_file_path', entry_key)

    # Extract relative path
    if log_path.startswith('/home/coding/aide-de-camp/'):
        log_path = log_path.replace('/home/coding/aide-de-camp/', '')

    analysis_path = entry_data.get('analysis_file_path', '')
    if analysis_path.startswith('/home/coding/aide-de-camp/'):
        analysis_path = analysis_path.replace('/home/coding/aide-de-camp/', '')

    # Check if this is a pod log or something else
    if 'pod-logs' not in log_path and 'pod-' not in Path(log_path).name:
        return None

    # Parse pod information
    pod_name = parse_pod_name_from_log_path(log_path)
    if not pod_name:
        return None

    namespace = parse_namespace_from_path(log_path)
    log_type = parse_log_type_from_path(log_path)
    collection_date = parse_collection_date_from_path(log_path)

    # Get timestamps and pattern data
    key_timestamps = entry_data.get('key_timestamps', {})
    pattern_counts = entry_data.get('pattern_counts', {})
    detected_patterns = entry_data.get('detected_patterns', [])

    # Build pattern detection
    pattern_detection = normalize_pattern_detection(
        detected_patterns,
        key_timestamps,
        pattern_counts
    )

    # Get temporal boundaries
    analysis_date = key_timestamps.get('analysis_date')
    first_log = key_timestamps.get('first_log_timestamp') or key_timestamps.get('first_log_entry')
    last_log = key_timestamps.get('last_log_timestamp') or key_timestamps.get('last_log_entry')

    # Get pod identification data
    creation_ts = entry_data.get('creation_timestamp')
    deletion_ts = entry_data.get('deletion_timestamp')

    # Format timestamps
    creation_timestamp = format_timestamp_iso(creation_ts)
    deletion_timestamp = format_timestamp_iso(deletion_ts) if deletion_ts and deletion_ts != 'unknown' else None

    # Build the schema-compliant entry
    schema_entry = {
        "pod_identification": {
            "pod_name": pod_name,
            "namespace": namespace,
            "pod_phase": "Running",  # Default since we don't have this data
            "restart_count": 0,  # Default since we don't have this data
            "creation_timestamp": creation_timestamp,
            "deletion_timestamp": deletion_timestamp,
            "container_image": None,  # Not available in current data
            "node_name": None  # Not available in current data
        },
        "log_file_metadata": {
            "log_file_path": log_path,
            "log_size_bytes": entry_data.get('log_size_bytes', 0),
            "log_line_count": entry_data.get('log_line_count'),
            "collection_date": collection_date,
            "log_type": log_type
        },
        "analysis_metadata": {
            "analysis_file_path": analysis_path if analysis_path and 'analysis.json' in analysis_path else None,
            "analysis_date": format_timestamp_iso(analysis_date)
        },
        "pattern_detection": pattern_detection,
        "temporal_boundaries": {
            "first_log_entry": format_timestamp_iso(first_log),
            "last_log_entry": format_timestamp_iso(last_log),
            "analysis_date": format_timestamp_iso(analysis_date),
            "collection_date": collection_date
        }
    }

    return schema_entry

def main():
    """Main function to construct pod-logs-index.jsonl."""

    # Load the unified data
    unified_file = Path('/home/coding/aide-de-camp/data/log-files-unified.json')
    if not unified_file.exists():
        print(f"Error: Unified data file not found: {unified_file}")
        return 1

    with open(unified_file, 'r') as f:
        unified_data = json.load(f)

    # Transform each entry
    jsonl_entries = []
    pod_count = 0

    for entry_key, entry_data in unified_data.items():
        schema_entry = transform_to_schema(entry_key, entry_data)
        if schema_entry:
            jsonl_entries.append(schema_entry)
            pod_count += 1

    # Write to JSONL file
    output_file = Path('/home/coding/aide-de-camp/pod-logs-index.jsonl')

    with open(output_file, 'w') as f:
        for entry in jsonl_entries:
            f.write(json.dumps(entry, separators=(',', ':')) + '\n')

    print(f"Generated pod-logs-index.jsonl with {pod_count} pod entries")
    print(f"Output file: {output_file}")

    # Validation: check line count
    with open(output_file, 'r') as f:
        line_count = sum(1 for _ in f)

    print(f"Line count: {line_count}")

    # Basic validation
    errors = []
    with open(output_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                errors.append(f"Line {line_num}: Empty line")
                continue

            try:
                entry = json.loads(line)

                # Check required top-level keys
                required_keys = [
                    'pod_identification', 'log_file_metadata',
                    'analysis_metadata', 'pattern_detection',
                    'temporal_boundaries'
                ]

                for key in required_keys:
                    if key not in entry:
                        errors.append(f"Line {line_num}: Missing required key '{key}'")

            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: Invalid JSON: {e}")

    if errors:
        print(f"\nValidation errors found: {len(errors)}")
        for error in errors[:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
        return 1
    else:
        print("Validation passed: All lines are valid JSON objects")

    return 0

if __name__ == '__main__':
    exit(main())
