#!/usr/bin/env python3
"""
Parse and categorize deployment events into structured CSV dataset.

This script orchestrates the complete pipeline:
1. Load JSONL files from both services (pbx-web, whisper-stt)
2. Parse entries using src/parse_log.py
3. Categorize events using src/categorize_events.py
4. Write to CSV with validation and error reporting

Output columns: timestamp, service, event_type, status, error_code, duration
"""

import json
import csv
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
import logging

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parse_log import load_jsonl, parse_entry, normalize_timestamp
from src.categorize_events import categorize_event, EventType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Data sources - JSONL files from both services
DATA_SOURCES = {
    'pbx-web': [
        'data/pbx-web-events.jsonl',
        'data/pbx-web-pods.jsonl',
        'data/pbx-web-replicasets.jsonl',
        'data/pbx-web-logs.jsonl',
        'data/pbx-web-logs-old.jsonl',
    ],
    'whisper-stt': [
        'data/whisper-stt-pods.jsonl',
        'data/whisper-stt-replicasets.jsonl',
    ]
}

# Output CSV headers
CSV_HEADERS = [
    'timestamp',
    'service',
    'event_type',
    'status',
    'error_code',
    'duration'
]


def load_all_entries() -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, int]]]:
    """
    Load all entries from JSONL files for both services.

    Returns:
        Tuple of (all_raw_entries, stats_dict) where stats_dict contains
        loading statistics per service
    """
    all_entries = []
    stats = {}

    for service, filepaths in DATA_SOURCES.items():
        service_stats = {
            'files_loaded': 0,
            'entries_loaded': 0,
            'parse_errors': 0,
            'skipped_lines': 0
        }

        logger.info(f"Loading {service} data files...")

        for filepath in filepaths:
            full_path = Path(__file__).parent.parent / filepath
            if not full_path.exists():
                logger.warning(f"File not found: {filepath}")
                continue

            try:
                entries, errors, skipped = load_jsonl(str(full_path))
                service_stats['files_loaded'] += 1
                service_stats['entries_loaded'] += len(entries)
                service_stats['parse_errors'] += errors
                service_stats['skipped_lines'] += skipped

                # Add service context to each entry
                for entry in entries:
                    entry['service'] = service

                all_entries.extend(entries)
                logger.debug(f"  Loaded {len(entries)} entries from {filepath}")

            except Exception as e:
                logger.error(f"Failed to load {filepath}: {e}")
                continue

        stats[service] = service_stats
        logger.info(f"  {service}: {service_stats['entries_loaded']} entries from {service_stats['files_loaded']} files")

    return all_entries, stats


def parse_and_categorize_entries(raw_entries: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Parse and categorize all raw entries.

    Args:
        raw_entries: List of raw log entries from JSONL files

    Returns:
        Tuple of (parsed_entries, parse_stats) where parse_stats contains
        parsing and categorization statistics
    """
    parsed_entries = []
    stats = {
        'total_processed': len(raw_entries),
        'parse_success': 0,
        'parse_failed': 0,
        'categorized': {
            event_type.value: 0 for event_type in EventType
        }
    }

    logger.info(f"Parsing and categorizing {len(raw_entries)} entries...")

    for raw_entry in raw_entries:
        try:
            # Parse entry using parse_log module
            parsed = parse_entry(raw_entry)
            stats['parse_success'] += 1

            # Categorize event using categorize_events module
            event_category = categorize_event(parsed)
            stats['categorized'][event_category.value] += 1

            # Add categorized event type to parsed entry
            parsed['categorized_event_type'] = event_category.value

            parsed_entries.append(parsed)

        except Exception as e:
            stats['parse_failed'] += 1
            logger.warning(f"Failed to parse entry: {e}")
            continue

    logger.info(f"  Successfully parsed: {stats['parse_success']}")
    logger.info(f"  Failed to parse: {stats['parse_failed']}")

    return parsed_entries, stats


def validate_csv_structure(filepath: str) -> Tuple[bool, List[str]]:
    """
    Validate the generated CSV file.

    Checks:
    - File exists and is non-empty
    - Has correct headers
    - Has valid data types

    Args:
        filepath: Path to CSV file

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    if not Path(filepath).exists():
        errors.append(f"CSV file does not exist: {filepath}")
        return False, errors

    # Check file size
    file_size = Path(filepath).stat().st_size
    if file_size == 0:
        errors.append("CSV file is empty")
        return False, errors

    try:
        with open(filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader, None)

            if headers is None:
                errors.append("CSV file has no headers")
                return False, errors

            # Check headers
            if headers != CSV_HEADERS:
                errors.append(f"Invalid headers. Expected {CSV_HEADERS}, got {headers}")
                return False, errors

            # Check data rows
            row_count = 0
            for row_num, row in enumerate(reader, 2):  # Start at 2 (header is row 1)
                row_count += 1

                # Validate column count
                if len(row) != len(CSV_HEADERS):
                    errors.append(f"Row {row_num}: Expected {len(CSV_HEADERS)} columns, got {len(row)}")

                # Validate timestamp format (if present)
                timestamp = row[0] if row else ''
                if timestamp and timestamp != '':
                    # Check if timestamp is ISO 8601 format or empty
                    if not (timestamp.startswith('20') or timestamp == ''):
                        errors.append(f"Row {row_num}: Invalid timestamp format '{timestamp}'")

                # Validate service name
                service = row[1] if len(row) > 1 else ''
                if service and service not in ['pbx-web', 'whisper-stt', 'unknown']:
                    errors.append(f"Row {row_num}: Unknown service '{service}'")

                # Validate status
                status = row[3] if len(row) > 3 else ''
                if status and status not in ['success', 'failure', 'warning', 'unknown']:
                    errors.append(f"Row {row_num}: Invalid status '{status}'")

                # Validate duration (if present)
                duration = row[5] if len(row) > 5 else ''
                if duration and duration != '':
                    try:
                        float(duration)
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid duration '{duration}'")

            if row_count == 0:
                errors.append("CSV file has no data rows")

    except Exception as e:
        errors.append(f"Error reading CSV: {e}")
        return False, errors

    is_valid = len(errors) == 0
    return is_valid, errors


def write_csv(parsed_entries: List[Dict[str, Any]], output_path: str) -> int:
    """
    Write parsed entries to CSV file.

    Args:
        parsed_entries: List of parsed event dictionaries
        output_path: Path to output CSV file

    Returns:
        Number of rows written
    """
    logger.info(f"Writing CSV to {output_path}...")

    rows_written = 0

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Write headers
        writer.writerow(CSV_HEADERS)

        # Write data rows
        for entry in parsed_entries:
            # Extract and format fields for CSV output
            timestamp = entry.get('timestamp', '')
            service = entry.get('service', 'unknown')
            event_type = entry.get('categorized_event_type', entry.get('event_type', 'unknown'))
            status = entry.get('status', 'unknown')
            error_code = entry.get('error_code', '')
            duration_ms = entry.get('duration_ms')

            # Convert duration to seconds (or empty if None)
            duration = ''
            if duration_ms is not None:
                try:
                    duration = str(duration_ms / 1000.0)  # Convert ms to seconds
                except (TypeError, ValueError):
                    duration = ''

            writer.writerow([
                timestamp,
                service,
                event_type,
                status,
                error_code,
                duration
            ])
            rows_written += 1

    logger.info(f"  Wrote {rows_written} data rows")
    return rows_written


def generate_summary_report(
    loading_stats: Dict[str, Dict[str, int]],
    parse_stats: Dict[str, Any],
    validation_result: Tuple[bool, List[str]],
    output_path: str
) -> Dict[str, Any]:
    """
    Generate comprehensive summary report.

    Args:
        loading_stats: Statistics from loading JSONL files
        parse_stats: Statistics from parsing and categorization
        validation_result: Tuple of (is_valid, error_list) from validation
        output_path: Path to output summary JSON

    Returns:
        Summary report dictionary
    """
    is_valid, validation_errors = validation_result

    summary = {
        'pipeline_status': 'success' if is_valid else 'validation_failed',
        'data_sources': loading_stats,
        'parsing': {
            'total_entries': parse_stats['total_processed'],
            'parse_success': parse_stats['parse_success'],
            'parse_failed': parse_stats['parse_failed'],
            'success_rate': f"{(parse_stats['parse_success'] / parse_stats['total_processed'] * 100):.2f}%" if parse_stats['total_processed'] > 0 else 'N/A'
        },
        'categorization': {
            'event_counts': parse_stats['categorized']
        },
        'validation': {
            'csv_valid': is_valid,
            'error_count': len(validation_errors),
            'errors': validation_errors
        }
    }

    # Write summary to JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    return summary


def main():
    """
    Main execution function.
    """
    logger.info("=== Starting Deployment Log Parsing Pipeline ===")

    # Step 1: Load all entries from JSONL files
    logger.info("Step 1: Loading JSONL files...")
    raw_entries, loading_stats = load_all_entries()
    total_loaded = sum(s['entries_loaded'] for s in loading_stats.values())
    logger.info(f"  Loaded {total_loaded} total entries from all sources")

    if not raw_entries:
        logger.error("No entries loaded from any data source!")
        return

    # Step 2: Parse and categorize entries
    logger.info("\nStep 2: Parsing and categorizing entries...")
    parsed_entries, parse_stats = parse_and_categorize_entries(raw_entries)

    if not parsed_entries:
        logger.error("No entries successfully parsed!")
        return

    # Step 3: Write to CSV
    logger.info("\nStep 3: Writing CSV output...")
    output_dir = Path(__file__).parent.parent / 'data'
    output_dir.mkdir(exist_ok=True)
    csv_path = output_dir / 'parsed_deployments.csv'

    rows_written = write_csv(parsed_entries, str(csv_path))

    # Step 4: Validate CSV
    logger.info("\nStep 4: Validating CSV output...")
    is_valid, validation_errors = validate_csv_structure(str(csv_path))

    if is_valid:
        logger.info(f"  ✓ CSV validation passed")
    else:
        logger.error(f"  ✗ CSV validation failed with {len(validation_errors)} errors:")
        for error in validation_errors:
            logger.error(f"    - {error}")

    # Step 5: Generate summary report
    logger.info("\nStep 5: Generating summary report...")
    summary_path = output_dir / 'parsing_summary.json'
    summary = generate_summary_report(
        loading_stats,
        parse_stats,
        (is_valid, validation_errors),
        str(summary_path)
    )
    logger.info(f"  Summary report written to: {summary_path}")

    # Print summary to console
    print("\n" + "=" * 70)
    print("DEPLOYMENT LOG PARSING SUMMARY")
    print("=" * 70)

    print(f"\nPipeline Status: {'✓ SUCCESS' if is_valid else '✗ VALIDATION FAILED'}")
    print(f"\nCSV Output: {csv_path}")
    print(f"Summary Report: {summary_path}")

    print(f"\n--- Data Loading ---")
    for service, stats in loading_stats.items():
        print(f"\n{service}:")
        print(f"  Files loaded: {stats['files_loaded']}")
        print(f"  Entries loaded: {stats['entries_loaded']}")
        print(f"  Parse errors: {stats['parse_errors']}")
        print(f"  Skipped lines: {stats['skipped_lines']}")

    print(f"\n--- Parsing & Categorization ---")
    print(f"Total entries processed: {parse_stats['total_processed']}")
    print(f"Successfully parsed: {parse_stats['parse_success']}")
    print(f"Failed to parse: {parse_stats['parse_failed']}")
    # Calculate success rate on the fly
    success_rate = f"{(parse_stats['parse_success'] / parse_stats['total_processed'] * 100):.2f}%" if parse_stats['total_processed'] > 0 else 'N/A'
    print(f"Success rate: {success_rate}")

    print(f"\n--- Event Categorization ---")
    for event_type, count in parse_stats['categorized'].items():
        if count > 0:
            print(f"  {event_type}: {count}")

    print(f"\n--- CSV Validation ---")
    print(f"Valid: {is_valid}")
    if not is_valid:
        print(f"Errors found: {len(validation_errors)}")

    print("\n" + "=" * 70)

    # Exit with appropriate code
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()
