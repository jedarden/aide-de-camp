#!/usr/bin/env python3
"""
Extract log file sizes and timestamps for all log files.

This script reads the analysis metadata file and adds:
- log_size_bytes (file size on disk)
- creation_timestamp (ISO string, from file mtime)
- deletion_timestamp (ISO string or null, from analysis or log content)

The output is a unified dataset with all collected fields.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


def load_analysis_metadata(metadata_file: Path) -> Dict[str, Any]:
    """Load the existing analysis metadata."""
    try:
        with open(metadata_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading analysis metadata: {e}")
        return {}


def get_file_size(file_path: str) -> Optional[int]:
    """Get file size in bytes."""
    try:
        return os.path.getsize(file_path)
    except (OSError, FileNotFoundError) as e:
        # File doesn't exist or can't be accessed
        return None


def get_file_mtime(file_path: str) -> Optional[str]:
    """Get file modification time as ISO string."""
    try:
        timestamp = os.path.getmtime(file_path)
        return datetime.fromtimestamp(timestamp).isoformat()
    except (OSError, FileNotFoundError) as e:
        # File doesn't exist or can't be accessed
        return None


def is_valid_iso_timestamp(timestamp: str) -> bool:
    """Check if a string is a valid ISO 8601 timestamp."""
    if not timestamp:
        return False
    try:
        # Try to parse as ISO format, handling both Z and +00:00 timezone formats
        normalized = timestamp.replace('Z', '+00:00')
        datetime.fromisoformat(normalized)
        return True
    except (ValueError, AttributeError):
        return False


def extract_deletion_timestamp_from_log(file_path: str) -> Optional[str]:
    """
    Extract deletion timestamp from log content if available.

    Looks for patterns like:
    - Pod deletion events
    - Container termination messages
    - Last log entries indicating shutdown

    Returns:
        ISO 8601 timestamp string or None. Invalid timestamp formats are filtered out.
    """
    try:
        with open(file_path, 'r', errors='ignore') as f:
            # Read last few lines looking for deletion indicators
            lines = f.readlines()
            if not lines:
                return None

            # Check last 100 lines for deletion patterns
            recent_lines = lines[-100:] if len(lines) > 100 else lines

            for line in reversed(recent_lines):
                line_lower = line.lower()
                # Look for deletion/termination patterns
                if any(pattern in line_lower for pattern in [
                    'pod deleted',
                    'container terminated',
                    'stopping container',
                    'killing container',
                    'sigterm',
                    'exit code'
                ]):
                    # Try to extract timestamp from the line
                    # Assuming Kubernetes log format with timestamp at start
                    parts = line.strip().split()
                    if parts:
                        # Try common timestamp formats
                        for i, part in enumerate(parts[:5]):  # Check first 5 parts
                            # Try ISO format
                            if 'T' in part and ('Z' in part or '+' in part):
                                candidate = part.split('+')[0].split('Z')[0]
                                if is_valid_iso_timestamp(candidate):
                                    return candidate
                            # Try other common formats
                            try:
                                # Try RFC3339-like format
                                if '-' in part and ':' in part:
                                    if is_valid_iso_timestamp(part):
                                        return part
                            except:
                                pass

            return None
    except (OSError, FileNotFoundError, UnicodeDecodeError) as e:
        return None


def extract_deletion_from_analysis(analysis_data: Dict[str, Any]) -> Optional[str]:
    """Extract deletion timestamp from analysis metadata."""
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


def extract_first_log_timestamp(file_path: str) -> Optional[str]:
    """Extract timestamp from first log line if available."""
    try:
        with open(file_path, 'r', errors='ignore') as f:
            first_line = f.readline()
            if not first_line:
                return None

            # Try to extract timestamp from first line
            parts = first_line.strip().split()
            if parts:
                # Try ISO format with T
                for part in parts[:3]:
                    if 'T' in part and ('Z' in part or '+' in part):
                        return part.split('+')[0].split('Z')[0]
                    # Try other formats
                    if '-' in part and ':' in part and len(part) > 10:
                        return part

            return None
    except (OSError, FileNotFoundError, UnicodeDecodeError):
        return None


def extract_pod_deletion_from_replicaset_data(log_file_path: str, analysis_data: Dict[str, Any]) -> Optional[str]:
    """Extract deletion timestamp from replicaset data if this is array format."""
    if analysis_data.get("data_structure") != "array":
        return None

    # For array format data (replicasets), check if there's deletion info
    key_timestamps = analysis_data.get("key_timestamps", {})

    # Check for deleted_at or similar fields
    for key in ["deleted_at", "deletion_timestamp", "termination_timestamp"]:
        if key in key_timestamps:
            return key_timestamps[key]

    return None


def extract_pod_metadata(log_file_path: str) -> Dict[str, Optional[str]]:
    """
    Extract creation_timestamp, deletion_timestamp, and log_size_bytes from a log file.

    Args:
        log_file_path: Path to the log file

    Returns:
        Dictionary with:
        - creation_timestamp: ISO string from file mtime or first log line
        - deletion_timestamp: ISO string from deletion indicators in log, or None
        - log_size_bytes: File size in bytes

    Handles edge cases:
    - Missing timestamps (returns None)
    - Malformed files (returns None with graceful error handling)
    - Missing files (returns None for all fields)
    """
    result = {
        "creation_timestamp": None,
        "deletion_timestamp": None,
        "log_size_bytes": None
    }

    try:
        # Get file size
        result["log_size_bytes"] = get_file_size(log_file_path)
        if result["log_size_bytes"] is None:
            return result

        # Get creation timestamp from file mtime
        creation_from_mtime = get_file_mtime(log_file_path)
        if creation_from_mtime:
            result["creation_timestamp"] = creation_from_mtime

        # Also try to get creation timestamp from first log line
        first_log_timestamp = extract_first_log_timestamp(log_file_path)
        if first_log_timestamp and not result["creation_timestamp"]:
            result["creation_timestamp"] = first_log_timestamp

        # Get deletion timestamp from log content
        deletion_from_log = extract_deletion_timestamp_from_log(log_file_path)
        result["deletion_timestamp"] = deletion_from_log

    except Exception as e:
        # Handle unexpected errors gracefully
        print(f"Error processing {log_file_path}: {e}")
        return {
            "creation_timestamp": None,
            "deletion_timestamp": None,
            "log_size_bytes": None
        }

    return result


def create_unified_record(log_file_path: str, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a unified record with all collected fields."""

    # Start with existing analysis data
    unified = analysis_data.copy()

    # Extract file metadata (only for real files, not array or summary data)
    file_size = None
    creation_timestamp = None
    deletion_timestamp = None
    first_log_timestamp = None

    # Skip file operations for summary and array entries
    if not analysis_data.get("log_file_path", "").startswith(("summary/", "array-data/")):
        # Get file size
        file_size = get_file_size(log_file_path)

        # Get file modification time (creation timestamp)
        creation_timestamp = get_file_mtime(log_file_path)

        # Extract timestamps from log content
        first_log_timestamp = extract_first_log_timestamp(log_file_path)
        deletion_timestamp = extract_deletion_timestamp_from_log(log_file_path)

    # Also check analysis data for deletion timestamp
    analysis_deletion = extract_deletion_from_analysis(analysis_data)
    if analysis_deletion and not deletion_timestamp:
        deletion_timestamp = analysis_deletion

    # Check replicaset data for deletion info
    replicaset_deletion = extract_pod_deletion_from_replicaset_data(log_file_path, analysis_data)
    if replicaset_deletion and not deletion_timestamp:
        deletion_timestamp = replicaset_deletion

    # Add file metadata to unified record
    unified["log_size_bytes"] = file_size
    unified["creation_timestamp"] = creation_timestamp
    unified["deletion_timestamp"] = deletion_timestamp
    unified["first_log_timestamp"] = first_log_timestamp

    # Use first log timestamp as creation timestamp if we don't have one
    if not creation_timestamp and first_log_timestamp:
        unified["creation_timestamp"] = first_log_timestamp

    return unified


def main():
    """Main function to extract and merge file metadata."""
    # File paths
    root_dir = Path("/home/coding/aide-de-camp")
    metadata_file = root_dir / "data" / "analysis-metadata-extracted.json"
    output_file = root_dir / "data" / "log-files-unified.json"

    # Load existing analysis metadata
    print("Loading analysis metadata...")
    analysis_data = load_analysis_metadata(metadata_file)
    print(f"Loaded {len(analysis_data)} entries")

    # Create unified records
    unified_data = {}
    successful_count = 0
    missing_files = 0
    summary_entries = 0

    for log_file_path, entry_data in analysis_data.items():
        # Create unified record
        unified_record = create_unified_record(log_file_path, entry_data)
        unified_data[log_file_path] = unified_record

        # Track statistics
        if unified_record.get("log_file_path", "").startswith("summary/"):
            summary_entries += 1
        elif unified_record.get("log_file_path", "").startswith("array-data/"):
            successful_count += 1  # Array data counts as successful
        elif unified_record.get("log_size_bytes") is not None:
            successful_count += 1
        else:
            missing_files += 1

    # Write unified data
    print(f"\nWriting unified data to: {output_file}")
    with open(output_file, 'w') as f:
        json.dump(unified_data, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Total entries: {len(unified_data)}")
    print(f"Successfully processed with file metadata: {successful_count}")
    print(f"Summary/array entries (no file operations): {summary_entries}")
    print(f"Missing log files: {missing_files}")

    # Calculate total size
    total_size = sum(
        entry.get("log_size_bytes", 0) or 0
        for entry in unified_data.values()
        if entry.get("log_size_bytes") is not None
    )
    print(f"Total log file size: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")

    # Show samples with deletion timestamps
    deletion_count = sum(
        1 for entry in unified_data.values()
        if entry.get("deletion_timestamp")
    )
    print(f"Entries with deletion timestamps: {deletion_count}")

    # Show a few sample records
    print(f"\n=== Sample Records ===")
    for i, (log_path, record) in enumerate(list(unified_data.items())[:3]):
        print(f"\n{i+1}. {log_path}")
        print(f"   Size: {record.get('log_size_bytes', 'N/A')} bytes")
        print(f"   Created: {record.get('creation_timestamp', 'N/A')}")
        print(f"   Deleted: {record.get('deletion_timestamp', 'N/A')}")
        print(f"   First log: {record.get('first_log_timestamp', 'N/A')}")


if __name__ == "__main__":
    main()