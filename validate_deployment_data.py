#!/usr/bin/env python3
"""
Parse and validate all JSON files from docs/research/deployment-data/
Loads them into memory for analysis and reports any errors.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from collections import defaultdict
from datetime import datetime

def parse_json_file(filepath: Path) -> Tuple[bool, Any, str]:
    """
    Parse a JSON file and return (success, data, error_message).
    """
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return True, data, ""
    except json.JSONDecodeError as e:
        return False, None, f"JSON decode error: {e.msg} at line {e.lineno}, column {e.colno}"
    except Exception as e:
        return False, None, f"Error reading file: {str(e)}"


def validate_structure(data: Any, filepath: Path) -> List[str]:
    """
    Validate the structure of parsed JSON data.
    Returns a list of validation warnings/errors.
    """
    issues = []

    if data is None:
        issues.append("Data is None")
        return issues

    if not isinstance(data, (dict, list)):
        issues.append(f"Root is not a dict or list, got type: {type(data).__name__}")

    return issues


def analyze_service_data(data: Dict[str, Any]) -> Dict[str, int]:
    """
    Analyze the loaded data to extract record counts by service.
    Returns a dictionary with service names and their record counts.
    """
    service_counts = defaultdict(int)

    # Check for common deployment data structures
    if isinstance(data, list):
        # Array of deployment records
        service_counts["total_records"] = len(data)

        # Try to extract service names from records
        for record in data:
            if isinstance(record, dict):
                # Common service identifier fields
                for key in ['service', 'serviceName', 'service_name', 'app', 'application']:
                    if key in record:
                        service = record[key]
                        if isinstance(service, str):
                            service_counts[service] += 1
                            break
    elif isinstance(data, dict):
        # Object with potentially nested data
        if 'deployments' in data and isinstance(data['deployments'], list):
            service_counts["total_records"] = len(data['deployments'])
        elif 'items' in data and isinstance(data['items'], list):
            service_counts["total_records"] = len(data['items'])
        elif 'workflows' in data and isinstance(data['workflows'], list):
            service_counts["total_records"] = len(data['workflows'])
        elif 'data' in data and isinstance(data['data'], list):
            service_counts["total_records"] = len(data['data'])
        else:
            # Count top-level keys
            service_counts["total_records"] = len(data)

    return dict(service_counts)


def main():
    """Main validation routine."""
    data_dir = Path("docs/research/deployment-data/")

    if not data_dir.exists():
        print(f"ERROR: Directory {data_dir} does not exist")
        sys.exit(1)

    # Find all JSON files
    json_files = sorted(data_dir.glob("*.json"))

    if not json_files:
        print(f"ERROR: No JSON files found in {data_dir}")
        sys.exit(1)

    print(f"Found {len(json_files)} JSON files to validate\n")
    print("=" * 80)

    # Results tracking
    valid_files = []
    invalid_files = []
    all_data = {}  # Consolidated in-memory structure
    service_summary = defaultdict(lambda: defaultdict(int))

    # Process each file
    for filepath in json_files:
        filename = filepath.name
        print(f"\nProcessing: {filename}")
        print("-" * 80)

        # Parse the file
        success, data, error = parse_json_file(filepath)

        if not success:
            print(f"  ❌ FAILED TO PARSE: {error}")
            invalid_files.append((filename, error))
            continue

        # Validate structure
        issues = validate_structure(data, filepath)

        if issues:
            print(f"  ⚠️  STRUCTURE ISSUES:")
            for issue in issues:
                print(f"     - {issue}")

        # Load into memory
        all_data[filename] = data
        valid_files.append(filename)

        # Analyze service data
        service_counts = analyze_service_data(data) if isinstance(data, (dict, list)) else {}

        if service_counts:
            print(f"  ✓ Parsed successfully")
            for service, count in service_counts.items():
                print(f"     - {service}: {count} records")
                service_summary[filename][service] = count
        else:
            print(f"  ✓ Parsed successfully (unknown structure)")

        # Basic stats
        if isinstance(data, list):
            print(f"     Structure: Array with {len(data)} items")
        elif isinstance(data, dict):
            print(f"     Structure: Object with {len(data)} top-level keys")

    # Summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    print(f"\nTotal files processed: {len(json_files)}")
    print(f"✓ Valid files: {len(valid_files)}")
    print(f"❌ Invalid files: {len(invalid_files)}")

    if invalid_files:
        print(f"\nInvalid files:")
        for filename, error in invalid_files:
            print(f"  - {filename}: {error}")

    print(f"\nValid files loaded into memory:")
    for filename in valid_files:
        print(f"  - {filename}")

    print(f"\nRecord counts by file:")
    for filename, services in sorted(service_summary.items()):
        if services:
            print(f"\n  {filename}:")
            for service, count in services.items():
                print(f"    - {service}: {count}")

    # Print consolidated data structure info
    print(f"\nConsolidated data structure loaded: {len(all_data)} files")

    # Save validation results to a file
    results = {
        "total_files": len(json_files),
        "valid_files": valid_files,
        "invalid_files": [{"file": f, "error": e} for f, e in invalid_files],
        "service_summary": {k: dict(v) for k, v in service_summary.items()}
    }

    output_file = data_dir / "validation-results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nValidation results saved to: {output_file}")

    return 0 if len(invalid_files) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())