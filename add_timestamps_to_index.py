#!/usr/bin/env python3
"""
Add timestamp metadata to pod-logs-index.jsonl.

This script reads the pod-logs-index.jsonl and adds:
- creation_timestamp (ISO string, from file mtime or log content)
- deletion_timestamp (ISO string or null, from analysis or log content)
- first_log_timestamp (from first log line if available)

The output is an updated pod-logs-index.jsonl with all collected fields.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional


def get_file_mtime(file_path: str) -> Optional[str]:
    """Get file modification time as ISO string."""
    try:
        timestamp = os.path.getmtime(file_path)
        return datetime.fromtimestamp(timestamp).isoformat()
    except (OSError, FileNotFoundError) as e:
        # File doesn't exist or can't be accessed
        return None


def extract_deletion_timestamp_from_log(file_path: str) -> Optional[str]:
    """
    Extract deletion timestamp from log content if available.

    Looks for patterns like:
    - Pod deletion events
    - Container termination messages
    - Last log entries indicating shutdown
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
                                return part.split('+')[0].split('Z')[0]
                            # Try other common formats
                            try:
                                # Try RFC3339-like format
                                if '-' in part and ':' in part:
                                    return part
                            except:
                                pass

            return None
    except (OSError, FileNotFoundError, UnicodeDecodeError) as e:
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


def extract_deletion_from_analysis(analysis_file_path: str) -> Optional[str]:
    """Extract deletion timestamp from analysis metadata file."""
    if not analysis_file_path:
        return None

    try:
        with open(analysis_file_path, 'r') as f:
            analysis_data = json.load(f)

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
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        return None


def update_pod_logs_index(input_file: Path, output_file: Path):
    """Update pod logs index with timestamp metadata."""

    updated_entries = []

    # Read existing index
    print(f"Reading pod logs index from: {input_file}")
    with open(input_file, 'r') as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                updated_entries.append(entry)

    print(f"Loaded {len(updated_entries)} entries")

    # Update each entry
    for i, entry in enumerate(updated_entries):
        log_file_path = entry.get("log_file_path")

        if not log_file_path:
            continue

        # Skip entries that are just summaries
        if log_file_path.startswith("summary/"):
            continue

        # Get file modification time (creation timestamp)
        if not entry.get("creation_timestamp"):
            creation_timestamp = get_file_mtime(log_file_path)
            if creation_timestamp:
                entry["creation_timestamp"] = creation_timestamp

        # Extract timestamps from log content
        if not entry.get("first_log_timestamp"):
            first_log_timestamp = extract_first_log_timestamp(log_file_path)
            if first_log_timestamp:
                entry["first_log_timestamp"] = first_log_timestamp

        # Extract deletion timestamp from log content
        if not entry.get("deletion_timestamp"):
            deletion_timestamp = extract_deletion_timestamp_from_log(log_file_path)
            if deletion_timestamp:
                entry["deletion_timestamp"] = deletion_timestamp

        # Also check analysis data for deletion timestamp
        analysis_file_path = entry.get("analysis_file_path")
        if not entry.get("deletion_timestamp") and analysis_file_path:
            analysis_deletion = extract_deletion_from_analysis(analysis_file_path)
            if analysis_deletion:
                entry["deletion_timestamp"] = analysis_deletion

        # Use first log timestamp as creation timestamp if we don't have one
        if not entry.get("creation_timestamp") and entry.get("first_log_timestamp"):
            entry["creation_timestamp"] = entry["first_log_timestamp"]

        # Show progress for every 10th entry
        if (i + 1) % 10 == 0:
            print(f"Processed {i + 1}/{len(updated_entries)} entries")

    # Write updated index
    print(f"\nWriting updated index to: {output_file}")
    with open(output_file, 'w') as f:
        for entry in updated_entries:
            f.write(json.dumps(entry) + '\n')

    # Calculate statistics
    with_creation = sum(1 for e in updated_entries if e.get("creation_timestamp"))
    with_deletion = sum(1 for e in updated_entries if e.get("deletion_timestamp"))
    with_first_log = sum(1 for e in updated_entries if e.get("first_log_timestamp"))

    print(f"\n=== Summary ===")
    print(f"Total entries: {len(updated_entries)}")
    print(f"With creation_timestamp: {with_creation}")
    print(f"With deletion_timestamp: {with_deletion}")
    print(f"With first_log_timestamp: {with_first_log}")

    # Show a few sample records
    print(f"\n=== Sample Records ===")
    for i, entry in enumerate(updated_entries[:3]):
        print(f"\n{i+1}. {entry.get('log_file_path', 'N/A')}")
        print(f"   Size: {entry.get('log_size_bytes', 'N/A')} bytes")
        print(f"   Created: {entry.get('creation_timestamp', 'N/A')}")
        print(f"   Deleted: {entry.get('deletion_timestamp', 'N/A')}")
        print(f"   First log: {entry.get('first_log_timestamp', 'N/A')}")


def main():
    """Main function to update pod logs index with timestamp metadata."""
    root_dir = Path("/home/coding/aide-de-camp")
    input_file = root_dir / "pod-logs-index.jsonl"
    output_file = root_dir / "pod-logs-index-updated.jsonl"

    update_pod_logs_index(input_file, output_file)

    print(f"\nUpdated index written to: {output_file}")
    print("You can replace the original file with:")
    print(f"  mv {output_file} {input_file}")


if __name__ == "__main__":
    main()