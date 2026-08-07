#!/usr/bin/env python3
"""
Load and validate categorized failures dataset.

This script loads the categorized failures output from adc-c2mam and validates
the data structure, grouping records by pattern_category for downstream processing.
"""

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Required field mappings
# Maps from logical field name to possible field names in the data
# pattern_category is REQUIRED - all other fields are OPTIONAL for statistics
FIELD_MAPPINGS = {
    'pattern_category': ['pattern_category'],  # REQUIRED
    'service': ['namespace', 'pod_name', 'pod'],  # OPTIONAL
    'image_tag': ['image'],  # OPTIONAL
    'timestamp': ['timestamp', 'data_collection_timestamp', 'time_period']  # OPTIONAL
}

# Only pattern_category is strictly required
REQUIRED_FIELDS = ['pattern_category']


class ValidationError(Exception):
    """Raised when a record fails validation."""
    pass


def find_field_value(record: Dict[str, Any], field_name: str) -> Any:
    """
    Find a field value in a record using possible field name variations.

    Args:
        record: The failure record
        field_name: The logical field name to find

    Returns:
        The field value if found, None otherwise
    """
    possible_names = FIELD_MAPPINGS.get(field_name, [])
    for possible_name in possible_names:
        if possible_name in record:
            value = record[possible_name]
            # Skip None or empty values
            if value is not None and value != '' and value != 'N/A':
                return value
    return None


def validate_record(record: Dict[str, Any], record_index: int) -> Dict[str, Any]:
    """
    Validate a single failure record and extract available fields.

    Only pattern_category is strictly required. All other fields are optional
    and will be extracted if available.

    Args:
        record: The failure record to validate
        record_index: Index of the record for logging purposes

    Returns:
        Dictionary with validated fields

    Raises:
        ValidationError: If the record is invalid and should be skipped
    """
    validated = {}
    missing_required = []

    # First check pattern_category (only truly required field)
    pattern_category = record.get('pattern_category')
    if not pattern_category:
        missing_required.append('pattern_category')
        logger.debug(
            f"Record {record_index}: Skipping - missing pattern_category"
        )
        raise ValidationError(f"Missing required field: pattern_category")

    validated['pattern_category'] = pattern_category

    # Extract optional fields for statistics (service, image_tag, timestamp)
    # These are not required but will be included if available
    for field_name in ['service', 'image_tag', 'timestamp']:
        value = find_field_value(record, field_name)
        if value is not None:
            validated[field_name] = value
        else:
            # Mark as None if not present (for downstream processing to handle)
            validated[field_name] = None

    # Preserve additional fields that might be useful for statistics
    # (error types, context, severity, etc.)
    validated['_original'] = record

    return validated


def load_categorized_failures(input_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load and validate categorized failures dataset.

    Args:
        input_path: Path to the categorized failures JSON file

    Returns:
        Dictionary mapping pattern_category to list of validated records

    Raises:
        FileNotFoundError: If input file doesn't exist
        json.JSONDecodeError: If JSON is malformed
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    logger.info(f"Loading categorized failures from: {input_path}")

    with open(input_file, 'r') as f:
        data = json.load(f)

    # Check if this is the expected format
    if 'failures' not in data:
        logger.error("Input file missing 'failures' key")
        raise ValueError("Invalid input format: expected 'failures' key")

    failures = data['failures']
    total_records = len(failures)
    logger.info(f"Total records in file: {total_records}")

    # Validate and group records
    grouped_records = defaultdict(list)
    valid_count = 0
    skip_count = 0
    error_count = 0

    for i, record in enumerate(failures):
        try:
            validated = validate_record(record, i)
            pattern_category = validated['pattern_category']
            grouped_records[pattern_category].append(validated)
            valid_count += 1

        except ValidationError as e:
            skip_count += 1
            logger.debug(f"Validation error at record {i}: {e}")

        except Exception as e:
            error_count += 1
            logger.error(f"Unexpected error processing record {i}: {e}")

    # Log summary
    logger.info(f"Validation complete:")
    logger.info(f"  - Valid records: {valid_count}")
    logger.info(f"  - Skipped (missing pattern_category): {skip_count}")
    logger.info(f"  - Errors: {error_count}")
    logger.info(f"  - Pattern categories found: {len(grouped_records)}")

    # Calculate field coverage statistics
    records_with_service = sum(1 for cat_records in grouped_records.values()
                                for r in cat_records if r.get('service'))
    records_with_image = sum(1 for cat_records in grouped_records.values()
                              for r in cat_records if r.get('image_tag'))
    records_with_timestamp = sum(1 for cat_records in grouped_records.values()
                                  for r in cat_records if r.get('timestamp'))

    logger.info(f"  - Field coverage:")
    logger.info(f"    - Records with service: {records_with_service} ({records_with_service/valid_count*100:.1f}%)")
    logger.info(f"    - Records with image_tag: {records_with_image} ({records_with_image/valid_count*100:.1f}%)")
    logger.info(f"    - Records with timestamp: {records_with_timestamp} ({records_with_timestamp/valid_count*100:.1f}%)")

    for category, records in sorted(grouped_records.items()):
        logger.info(f"    - {category}: {len(records)} records")

    # Convert defaultdict to regular dict for output
    return dict(grouped_records)


def save_validated_dataset(
    grouped_data: Dict[str, List[Dict[str, Any]]],
    output_path: str
) -> None:
    """
    Save validated dataset to JSON file.

    Args:
        grouped_data: Grouped and validated records
        output_path: Path to save the output
    """
    logger.info(f"Saving validated dataset to: {output_path}")

    # Prepare output structure
    output = {
        'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'total_categories': len(grouped_data),
        'categories': {}
    }

    for category, records in grouped_data.items():
        output['categories'][category] = {
            'count': len(records),
            'sample_records': records[:3]  # Include first 3 as samples
        }

    # Save full records
    output['records'] = grouped_data

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    logger.info(f"Saved validated dataset successfully")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Load and validate categorized failures dataset'
    )
    parser.add_argument(
        '--input',
        '-i',
        default=os.environ.get('CATEGORIZED_FAILURES_INPUT',
                              'categorized-failures-report.json'),
        help='Input JSON file path (default: CATEGORIZED_FAILURES_INPUT env var or categorized-failures-report.json)'
    )
    parser.add_argument(
        '--output',
        '-o',
        default=os.environ.get('VALIDATED_FAILURES_OUTPUT',
                              'validated-failures-dataset.json'),
        help='Output JSON file path (default: VALIDATED_FAILURES_OUTPUT env var or validated-failures-dataset.json)'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load and validate
        grouped_data = load_categorized_failures(args.input)

        # Save validated dataset
        save_validated_dataset(grouped_data, args.output)

        logger.info("Processing completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
