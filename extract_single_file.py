#!/usr/bin/env python3
"""
Extract metadata from a single log file.
This script reads a log file and extracts basic metadata information.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

def extract_file_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extract metadata from a single log file.

    Args:
        file_path: Path to the log file

    Returns:
        Dictionary with extracted metadata
    """
    result = {
        "file_path": file_path,
        "file_exists": False,
        "size_bytes": None,
        "creation_timestamp": None,
        "modification_timestamp": None,
        "line_count": None,
        "first_timestamp": None,
        "last_timestamp": None,
        "error": None
    }

    try:
        # Check if file exists
        if not os.path.exists(file_path):
            result["error"] = "File not found"
            return result

        result["file_exists"] = True

        # Get file size
        result["size_bytes"] = os.path.getsize(file_path)

        # Get timestamps
        stat_info = os.stat(file_path)
        result["modification_timestamp"] = datetime.fromtimestamp(stat_info.st_mtime).isoformat()

        # Try to get creation time (birth time on some systems)
        if hasattr(stat_info, 'st_birthtime'):
            result["creation_timestamp"] = datetime.fromtimestamp(stat_info.st_birthtime).isoformat()
        else:
            # On Linux, use modification time as fallback
            result["creation_timestamp"] = result["modification_timestamp"]

        # Count lines and extract timestamps from content
        try:
            with open(file_path, 'r', errors='ignore') as f:
                lines = f.readlines()
                result["line_count"] = len(lines)

                # Try to extract first and last timestamps from content
                if lines and result["line_count"] > 0:
                    # First line
                    first_line = lines[0].strip()
                    result["first_timestamp"] = extract_timestamp_from_line(first_line)

                    # Last line
                    if result["line_count"] > 1:
                        last_line = lines[-1].strip()
                        result["last_timestamp"] = extract_timestamp_from_line(last_line)

        except Exception as e:
            result["error"] = f"Error reading file content: {str(e)}"

    except Exception as e:
        result["error"] = f"Error accessing file: {str(e)}"

    return result

def extract_timestamp_from_line(line: str) -> Optional[str]:
    """Try to extract a timestamp from a log line."""
    if not line or len(line) < 10:
        return None

    # Try ISO format (2026-08-07T01:46:41)
    if 'T' in line and len(line) >= 19:
        parts = line.split('T')
        if len(parts) >= 2:
            date_part = parts[0].split()[-1] if ' ' in parts[0] else parts[0]
            time_part = parts[1].split()[0] if ' ' in parts[1] else parts[1]

            # Basic validation
            if len(date_part) == 10 and len(time_part) >= 8:
                try:
                    timestamp = f"{date_part}T{time_part[:8]}"
                    # Validate it's a real timestamp
                    test_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    return timestamp
                except:
                    pass

    return None

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: extract_single_file.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]

    # Extract metadata
    metadata = extract_file_metadata(file_path)

    # Output as JSON
    print(json.dumps(metadata, indent=2))

if __name__ == '__main__':
    main()