#!/usr/bin/env python3
"""
Validate pod-logs-index.jsonl against acceptance criteria schema.

Required fields:
- pod_name (string)
- namespace (string)
- creation_timestamp (ISO string or null)
- deletion_timestamp (ISO string or null)
- log_file_path (relative path)
- analysis_file_path (relative path or null)
- detected_patterns (array: startup, oom_kill, error, performance)
- key_timestamps (object with relevant dates)
- log_size_bytes (integer)
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any


def validate_iso_timestamp(timestamp: Any) -> bool:
    """Validate ISO timestamp format."""
    if timestamp is None:
        return True
    if not isinstance(timestamp, str):
        return False
    # Basic ISO format check (YYYY-MM-DDTHH:MM:SS...)
    iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
    return bool(re.match(iso_pattern, timestamp))


def validate_detected_patterns(patterns: List[str]) -> bool:
    """Validate detected patterns array."""
    if not isinstance(patterns, list):
        return False
    valid_patterns = {"startup", "oom_kill", "error", "performance"}
    for pattern in patterns:
        if pattern not in valid_patterns:
            return False
    return True


def validate_key_timestamps(timestamps: Dict[str, str]) -> bool:
    """Validate key timestamps object."""
    if not isinstance(timestamps, dict):
        return False
    # All values should be strings or null
    for key, value in timestamps.items():
        if value is not None and not isinstance(value, str):
            return False
    return True


def validate_entry(entry: Dict[str, Any], entry_num: int) -> List[str]:
    """Validate a single index entry and return list of errors."""
    errors = []

    # Check required fields exist
    required_fields = [
        "pod_name", "namespace", "creation_timestamp", "deletion_timestamp",
        "log_file_path", "analysis_file_path", "detected_patterns",
        "key_timestamps", "log_size_bytes"
    ]

    for field in required_fields:
        if field not in entry:
            errors.append(f"Entry {entry_num}: Missing required field '{field}'")

    # Validate field types and formats
    if "pod_name" in entry and not isinstance(entry["pod_name"], str):
        errors.append(f"Entry {entry_num}: pod_name must be string")

    if "namespace" in entry and not isinstance(entry["namespace"], str):
        errors.append(f"Entry {entry_num}: namespace must be string")

    if "creation_timestamp" in entry and not validate_iso_timestamp(entry["creation_timestamp"]):
        errors.append(f"Entry {entry_num}: creation_timestamp has invalid ISO format")

    if "deletion_timestamp" in entry and not validate_iso_timestamp(entry["deletion_timestamp"]):
        errors.append(f"Entry {entry_num}: deletion_timestamp has invalid ISO format")

    if "log_file_path" in entry and not isinstance(entry["log_file_path"], str):
        errors.append(f"Entry {entry_num}: log_file_path must be string")

    if "analysis_file_path" in entry:
        if entry["analysis_file_path"] is not None and not isinstance(entry["analysis_file_path"], str):
            errors.append(f"Entry {entry_num}: analysis_file_path must be string or null")

    if "detected_patterns" in entry and not validate_detected_patterns(entry["detected_patterns"]):
        errors.append(f"Entry {entry_num}: detected_patterns has invalid format or contains invalid pattern types")

    if "key_timestamps" in entry and not validate_key_timestamps(entry["key_timestamps"]):
        errors.append(f"Entry {entry_num}: key_timestamps must be an object with string values")

    if "log_size_bytes" in entry and not isinstance(entry["log_size_bytes"], int):
        errors.append(f"Entry {entry_num}: log_size_bytes must be integer")

    return errors


def validate_jsonl_syntax(file_path: Path) -> List[str]:
    """Validate JSONL syntax (one valid JSON object per line)."""
    errors = []

    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue  # Skip empty lines
                try:
                    json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")
    except Exception as e:
        errors.append(f"Error reading file: {e}")

    return errors


def main():
    """Main validation function."""
    index_file = Path.cwd() / "pod-logs-index.jsonl"

    if not index_file.exists():
        print("✗ pod-logs-index.jsonl does not exist")
        return 1

    print("Validating pod-logs-index.jsonl...")

    # First validate JSONL syntax
    print("1. Validating JSONL syntax...")
    syntax_errors = validate_jsonl_syntax(index_file)
    if syntax_errors:
        print("✗ JSONL syntax validation failed:")
        for error in syntax_errors:
            print(f"  {error}")
        return 1
    else:
        print("   ✓ JSONL syntax is valid")

    # Then validate each entry against schema
    print("2. Validating entries against schema...")
    all_errors = []
    entry_count = 0

    with open(index_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                entry_count += 1
                errors = validate_entry(entry, entry_count)
                all_errors.extend(errors)
            except json.JSONDecodeError:
                pass  # Already handled in syntax validation

    if all_errors:
        print(f"✗ Schema validation failed with {len(all_errors)} errors:")
        for error in all_errors[:10]:  # Show first 10 errors
            print(f"  {error}")
        if len(all_errors) > 10:
            print(f"  ... and {len(all_errors) - 10} more errors")
        return 1
    else:
        print(f"   ✓ All {entry_count} entries validate against schema")

    # Additional validation checks
    print("3. Additional validation checks...")

    # Check that file paths are relative
    with open(index_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry["log_file_path"].startswith("/"):
                print(f"   ✗ Entry {entry_num}: log_file_path should be relative, not absolute")
                return 1

    print("   ✓ All file paths are relative")

    print("\n✓ All validation checks passed!")
    print(f"  - Total entries: {entry_count}")
    print(f"  - JSONL syntax: Valid")
    print(f"  - Schema compliance: Valid")

    return 0


if __name__ == "__main__":
    exit(main())