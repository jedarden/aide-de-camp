#!/usr/bin/env python3
"""
Parse deployment JSON files from docs/research/deployment-data/.

Reads all .json files, loads them into Python data structures, and outputs
a summary of files processed and record counts.
"""

import json
from pathlib import Path
from typing import Any, Dict


def parse_json_file(file_path: Path) -> Dict[str, Any] | None:
    """
    Parse a single JSON file.

    Args:
        file_path: Path to the JSON file

    Returns:
        Parsed JSON data as dict, or None if parsing fails
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"  ERROR: File not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"  ERROR: Invalid JSON in {file_path}: {e}")
        return None
    except Exception as e:
        print(f"  ERROR: Failed to read {file_path}: {e}")
        return None


def count_records(data: Any) -> int:
    """
    Count records in parsed JSON data.

    Args:
        data: Parsed JSON data (dict, list, or other)

    Returns:
        Number of records (0 for non-iterable top-level data)
    """
    if isinstance(data, list):
        return len(data)
    elif isinstance(data, dict):
        # If it's a dict with known record containers, count those
        for key in ('records', 'items', 'results', 'workflows', 'deployments', 'failures'):
            if key in data and isinstance(data[key], list):
                return len(data[key])
        # Otherwise count the dict itself as one record
        return 1
    else:
        return 0


def main():
    """Main entry point for parsing deployment JSON files."""
    # Directory containing deployment JSON files
    data_dir = Path('docs/research/deployment-data/')

    # Verify directory exists
    if not data_dir.exists():
        print(f"ERROR: Directory not found: {data_dir.absolute()}")
        return 1

    # Find all JSON files
    json_files = sorted(data_dir.glob('*.json'))

    if not json_files:
        print(f"No JSON files found in {data_dir.absolute()}")
        return 0

    print(f"Found {len(json_files)} JSON file(s) in {data_dir.absolute()}\\n")

    # Parse each file
    results = []
    total_records = 0
    errors = 0

    for file_path in json_files:
        print(f"Parsing: {file_path.name}")
        data = parse_json_file(file_path)

        if data is not None:
            record_count = count_records(data)
            total_records += record_count
            results.append({
                'file': file_path.name,
                'records': record_count,
                'size_kb': file_path.stat().st_size / 1024,
                'status': 'ok'
            })
            print(f"  ✓ {record_count} record(s), {file_path.stat().st_size / 1024:.1f} KB")
        else:
            errors += 1
            results.append({
                'file': file_path.name,
                'records': 0,
                'size_kb': file_path.stat().st_size / 1024,
                'status': 'error'
            })

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Files processed: {len(json_files)}")
    print(f"Successful: {len(json_files) - errors}")
    print(f"Errors: {errors}")
    print(f"Total records: {total_records}")
    print(f"Total data size: {sum(r['size_kb'] for r in results):.1f} KB")
    print(f"{'='*60}")

    return 0


if __name__ == '__main__':
    exit(main())
