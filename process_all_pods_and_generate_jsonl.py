#!/usr/bin/env python3
"""
Process all pod logs and generate complete JSONL output.

This script:
1. Reads the existing pod-logs-index.jsonl catalog
2. Extracts metadata from each log file using the proven extraction function
3. Combines extracted metadata with existing inventory data
4. Outputs complete records as JSONL
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


def load_catalog(catalog_file: Path) -> List[Dict[str, Any]]:
    """Load the existing catalog from JSONL file."""
    records = []
    try:
        with open(catalog_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading catalog: {e}")
        return []
    return records


def get_file_size(file_path: str) -> Optional[int]:
    """Get file size in bytes."""
    try:
        return os.path.getsize(file_path)
    except (OSError, FileNotFoundError):
        return None


def get_file_mtime(file_path: str) -> Optional[str]:
    """Get file modification time as ISO string."""
    try:
        timestamp = os.path.getmtime(file_path)
        return datetime.fromtimestamp(timestamp).isoformat()
    except (OSError, FileNotFoundError):
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


def extract_deletion_timestamp_from_log(file_path: str) -> Optional[str]:
    """Extract deletion timestamp from log content if available."""
    try:
        with open(file_path, 'r', errors='ignore') as f:
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
                    parts = line.strip().split()
                    if parts:
                        # Try common timestamp formats
                        for i, part in enumerate(parts[:5]):
                            # Try ISO format
                            if 'T' in part and ('Z' in part or '+' in part):
                                return part.split('+')[0].split('Z')[0]
                            # Try other common formats
                            try:
                                if '-' in part and ':' in part:
                                    return part
                            except:
                                pass
            return None
    except (OSError, FileNotFoundError, UnicodeDecodeError):
        return None


def extract_metadata_from_log_file(log_file_path: str) -> Dict[str, Optional[str]]:
    """
    Extract metadata from a log file.

    Returns:
        Dictionary with:
        - log_size_bytes: File size in bytes
        - creation_timestamp: ISO string from file mtime or first log line
        - deletion_timestamp: ISO string from deletion indicators, or None
    """
    result = {
        "log_size_bytes": None,
        "creation_timestamp": None,
        "deletion_timestamp": None
    }

    try:
        # Get file size
        result["log_size_bytes"] = get_file_size(log_file_path)

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
        print(f"Error processing {log_file_path}: {e}")
        return {
            "log_size_bytes": None,
            "creation_timestamp": None,
            "deletion_timestamp": None
        }

    return result


def merge_record_with_extracted_metadata(record: Dict[str, Any], extracted: Dict[str, Optional[str]]) -> Dict[str, Any]:
    """Merge existing record with extracted metadata."""
    merged = record.copy()

    # Update fields with extracted data
    if extracted.get("log_size_bytes") is not None:
        merged["log_size_bytes"] = extracted["log_size_bytes"]

    # Use creation_timestamp if it's currently None
    if merged.get("creation_timestamp") is None and extracted.get("creation_timestamp"):
        merged["creation_timestamp"] = extracted["creation_timestamp"]

    # Use deletion_timestamp if it's currently None
    if merged.get("deletion_timestamp") is None and extracted.get("deletion_timestamp"):
        merged["deletion_timestamp"] = extracted["deletion_timestamp"]

    return merged


def main():
    """Main processing function."""
    root_dir = Path("/home/coding/aide-de-camp")
    catalog_file = root_dir / "pod-logs-index.jsonl"
    output_file = root_dir / "pod-logs-complete.jsonl"

    # Load existing catalog
    print("Loading existing catalog...")
    catalog_records = load_catalog(catalog_file)
    print(f"Loaded {len(catalog_records)} catalog records")

    # Process each record
    complete_records = []
    missing_files = 0
    updated_creation = 0
    updated_deletion = 0
    updated_size = 0

    for record in catalog_records:
        log_file_path = record.get("log_file_path")

        if not log_file_path:
            print(f"Warning: Record missing log_file_path: {record.get('pod_name')}")
            complete_records.append(record)
            continue

        # Make absolute path
        full_log_path = root_dir / log_file_path

        # Check if file exists
        if not full_log_path.exists():
            print(f"Warning: Log file not found: {log_file_path}")
            missing_files += 1
            complete_records.append(record)
            continue

        # Extract metadata from log file
        extracted = extract_metadata_from_log_file(str(full_log_path))

        # Track what was updated
        if record.get("creation_timestamp") is None and extracted.get("creation_timestamp"):
            updated_creation += 1

        if record.get("deletion_timestamp") is None and extracted.get("deletion_timestamp"):
            updated_deletion += 1

        if record.get("log_size_bytes") is None and extracted.get("log_size_bytes") is not None:
            updated_size += 1

        # Merge extracted metadata with existing record
        merged_record = merge_record_with_extracted_metadata(record, extracted)
        complete_records.append(merged_record)

    # Write complete JSONL output
    print(f"\nWriting complete records to: {output_file}")
    with open(output_file, 'w') as f:
        for record in complete_records:
            f.write(json.dumps(record) + '\n')

    # Calculate total size
    total_size = sum(
        record.get("log_size_bytes", 0) or 0
        for record in complete_records
        if record.get("log_size_bytes") is not None
    )

    # Count pods with metadata
    with_creation = sum(1 for r in complete_records if r.get("creation_timestamp"))
    with_deletion = sum(1 for r in complete_records if r.get("deletion_timestamp"))
    with_size = sum(1 for r in complete_records if r.get("log_size_bytes") is not None)

    print(f"\n=== Processing Summary ===")
    print(f"Total records processed: {len(complete_records)}")
    print(f"Missing log files: {missing_files}")
    print(f"Records with creation_timestamp: {with_creation}/{len(complete_records)}")
    print(f"Records with deletion_timestamp: {with_deletion}/{len(complete_records)}")
    print(f"Records with log_size_bytes: {with_size}/{len(complete_records)}")
    print(f"Total log file size: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")

    print(f"\n=== Updates Applied ===")
    print(f"Creation timestamps added: {updated_creation}")
    print(f"Deletion timestamps added: {updated_deletion}")
    print(f"File sizes added: {updated_size}")

    # Show sample records
    print(f"\n=== Sample Records ===")
    for i, record in enumerate(complete_records[:3]):
        print(f"\n{i+1}. Pod: {record.get('pod_name')} (ns: {record.get('namespace')})")
        print(f"   Log file: {record.get('log_file_path')}")
        print(f"   Size: {record.get('log_size_bytes', 'N/A')} bytes")
        print(f"   Created: {record.get('creation_timestamp', 'N/A')}")
        print(f"   Deleted: {record.get('deletion_timestamp', 'N/A')}")

    print(f"\n✅ Complete JSONL generated: {output_file}")


if __name__ == "__main__":
    main()