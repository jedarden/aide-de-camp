#!/usr/bin/env python3
"""
Load and validate categorized failures dataset from adc-c2mam output.

Validates that each record has required fields: pattern_category, service, image_tag, timestamp
Handles missing or malformed records gracefully.
Groups records by pattern_category for downstream processing.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple
from pathlib import Path


# Default input file path
DEFAULT_INPUT_FILE = "validated-failures-dataset.json"


def load_categorized_failures(input_file: str = None) -> Dict[str, Any]:
    """
    Load the categorized failures JSON file.

    Args:
        input_file: Path to the input JSON file (default: validated-failures-dataset.json)

    Returns:
        Dict containing the parsed JSON data
    """
    if input_file is None:
        input_file = os.getenv("CATEGORIZED_FAILURES_INPUT", DEFAULT_INPUT_FILE)

    file_path = Path(input_file)
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    print(f"Loading categorized failures from: {input_file}")
    with open(file_path, 'r') as f:
        data = json.load(f)

    print(f"  Generated at: {data.get('generated_at', 'unknown')}")
    print(f"  Total categories: {data.get('total_categories', 'unknown')}")

    return data


def validate_record(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that a record has required fields.

    Args:
        record: A single failure record

    Returns:
        Tuple of (is_valid, list_of_missing_fields)
    """
    required_fields = ['pattern_category', 'service', 'image_tag', 'timestamp']
    missing_fields = []

    for field in required_fields:
        if field not in record:
            missing_fields.append(field)

    # Note: service, image_tag, and timestamp can be null, but the key must exist
    is_valid = len(missing_fields) == 0

    return is_valid, missing_fields


def process_categories(data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Process and validate all records, grouping by pattern_category.

    Args:
        data: The loaded JSON data structure

    Returns:
        Dict mapping pattern_category to list of validated records
    """
    categories = data.get('categories', {})
    validated_dataset = {}
    total_records = 0
    skipped_records = 0
    validation_errors = []

    for category_name, category_data in categories.items():
        if not isinstance(category_data, dict):
            print(f"Warning: Category '{category_name}' has invalid structure, skipping")
            continue

        sample_records = category_data.get('sample_records', [])
        if not sample_records:
            print(f"Warning: Category '{category_name}' has no sample records")
            validated_dataset[category_name] = []
            continue

        validated_records = []

        for idx, record in enumerate(sample_records):
            total_records += 1
            is_valid, missing_fields = validate_record(record)

            if is_valid:
                validated_records.append(record)
            else:
                skipped_records += 1
                error_msg = (f"Category '{category_name}', record {idx}: "
                           f"missing fields {missing_fields}")
                validation_errors.append(error_msg)
                if len(validation_errors) <= 10:  # Show first 10 errors
                    print(f"  ERROR: {error_msg}")

        validated_dataset[category_name] = validated_records
        print(f"  Category '{category_name}': {len(validated_records)} validated records")

    # Print summary
    print(f"\nValidation Summary:")
    print(f"  Total records processed: {total_records}")
    print(f"  Valid records: {total_records - skipped_records}")
    print(f"  Skipped records: {skipped_records}")

    if validation_errors:
        print(f"  Total validation errors: {len(validation_errors)}")
        if len(validation_errors) > 10:
            print(f"  (First 10 errors shown above)")

    return validated_dataset


def output_validated_dataset(validated_dataset: Dict[str, List[Dict[str, Any]]],
                           output_file: str = None) -> None:
    """
    Output the validated dataset ready for downstream processing.

    Args:
        validated_dataset: Dict mapping pattern_category to list of records
        output_file: Optional path to write output JSON
    """
    # Generate summary
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "total_categories": len(validated_dataset),
        "total_records": sum(len(records) for records in validated_dataset.values()),
        "categories": {}
    }

    for category, records in validated_dataset.items():
        summary["categories"][category] = {
            "count": len(records),
            "sample_keys": list(records[0].keys()) if records else []
        }

    # Print to stdout
    print("\n=== Validated Dataset Ready ===")
    print(json.dumps(summary, indent=2))

    # Optionally write to file
    if output_file:
        output_path = Path(output_file)
        output_data = {
            "summary": summary,
            "data": validated_dataset
        }
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\nOutput written to: {output_file}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Load and validate categorized failures dataset"
    )
    parser.add_argument(
        '--input',
        default=None,
        help=f'Input JSON file path (default: {DEFAULT_INPUT_FILE} or CATEGORIZED_FAILURES_INPUT env var)'
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Output JSON file path (optional)'
    )

    args = parser.parse_args()

    try:
        # Load
        data = load_categorized_failures(args.input)

        # Validate and group
        validated_dataset = process_categories(data)

        # Output
        output_validated_dataset(validated_dataset, args.output)

        # Return success
        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in input file: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
