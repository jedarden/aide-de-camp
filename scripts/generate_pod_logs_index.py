#!/usr/bin/env python3
"""
Generate pod-logs-index.jsonl from combined metadata and pattern data.

This script reads the combined output from combine_metadata_and_patterns.py
and transforms it into the proper JSONL schema format defined in pod-logs-schema.md.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


def load_json_file(file_path: str) -> Optional[Any]:
    """Load a JSON file safely."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}", file=sys.stderr)
        return None


def extract_collection_date(log_file_path: str) -> Optional[str]:
    """Extract collection date from log file path."""
    # Look for patterns like 2026-08-06 in the filename
    parts = log_file_path.split('/')
    filename = parts[-1] if parts else log_file_path

    # Try to extract date from filename
    for part in filename.split('-'):
        if len(part) == 10 and part.count('-') == 2:
            try:
                # Validate it's a real date
                datetime.strptime(part, '%Y-%m-%d')
                return part
            except ValueError:
                continue
    return None


def extract_log_type(log_file_path: str) -> Optional[str]:
    """Extract log type from log file path."""
    if 'current' in log_file_path and 'log' in log_file_path:
        return 'current'
    elif 'previous' in log_file_path and 'log' in log_file_path:
        return 'previous'
    elif 'stderr' in log_file_path:
        return 'stderr'
    return None


def normalize_pattern_detection(detected_patterns: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Normalize detected patterns into the schema format.

    Args:
        detected_patterns: List of pattern names (e.g., ['error', 'startup'])

    Returns:
        Dictionary with 4 pattern categories, each with count, timestamps, samples
    """
    # Initialize all pattern categories with defaults
    pattern_detection = {
        'startup': {'count': 0, 'timestamps': [], 'samples': []},
        'oom_kill': {'count': 0, 'timestamps': [], 'samples': []},
        'error': {'count': 0, 'timestamps': [], 'samples': []},
        'performance': {'count': 0, 'timestamps': [], 'samples': []}
    }

    # Note: The current pattern extraction only provides pattern category names,
    # not detailed samples and timestamps. To maintain schema consistency
    # (count === timestamps.length === samples.length), we set all counts to 0.
    #
    # Future enhancement: When pattern extraction includes detailed data with
    # individual timestamps and sample messages, we can populate arrays here.
    #
    # For now, detected_patterns is informational only - it indicates which
    # categories were detected during analysis, but we don't have the detailed
    # event-level data required by the schema.

    return pattern_detection


def transform_to_schema_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a combined entry into the schema format.

    Args:
        entry: Combined entry from pod-logs-combined.json

    Returns:
        Schema-formatted entry ready for JSONL output
    """
    # Extract collection date if not present
    collection_date = entry.get('collection_date') or extract_collection_date(entry.get('log_file_path', ''))

    # Extract log type if not present
    log_type = entry.get('log_type') or extract_log_type(entry.get('log_file_path', ''))

    # Get analysis date from key_timestamps
    analysis_date = None
    if entry.get('key_timestamps') and isinstance(entry['key_timestamps'], dict):
        analysis_date = entry['key_timestamps'].get('analysis_date')
        if analysis_date and not analysis_date.endswith('Z'):
            # Add Z suffix if missing
            analysis_date = analysis_date + 'Z'

    # Build schema entry
    schema_entry = {
        'pod_identification': {
            'pod_name': entry.get('pod_name'),
            'namespace': entry.get('namespace'),
            'pod_phase': entry.get('pod_phase', 'Unknown'),
            'restart_count': entry.get('restart_count', 0),
            'creation_timestamp': entry.get('creation_timestamp'),
            'deletion_timestamp': entry.get('deletion_timestamp'),
            'container_image': entry.get('container_image'),
            'node_name': entry.get('node_name')
        },
        'log_file_metadata': {
            'log_file_path': f"research/{entry.get('log_file_path', '')}",
            'log_size_bytes': entry.get('log_size_bytes', 0),
            'log_line_count': entry.get('log_line_count'),
            'collection_date': collection_date,
            'log_type': log_type
        },
        'analysis_metadata': {
            'analysis_file_path': entry.get('analysis_file_path'),
            'analysis_date': analysis_date
        },
        'pattern_detection': normalize_pattern_detection(entry.get('detected_patterns', [])),
        'temporal_boundaries': {
            'first_log_entry': None,  # Would come from detailed analysis
            'last_log_entry': None,   # Would come from detailed analysis
            'analysis_date': analysis_date,
            'collection_date': collection_date
        }
    }

    return schema_entry


def generate_jsonl(
    combined_data: List[Dict[str, Any]],
    output_file: str
) -> int:
    """
    Generate JSONL output file from combined data.

    Args:
        combined_data: List of combined entries
        output_file: Path to output JSONL file

    Returns:
        Number of entries written
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    entries_written = 0

    with open(output_path, 'w') as f:
        for entry in combined_data:
            schema_entry = transform_to_schema_entry(json_line := entry)
            f.write(json.dumps(schema_entry) + '\n')
            entries_written += 1

    return entries_written


def validate_jsonl(jsonl_file: str) -> Dict[str, Any]:
    """
    Validate the generated JSONL file.

    Args:
        jsonl_file: Path to JSONL file to validate

    Returns:
        Validation results with error count and details
    """
    errors = []
    line_num = 0
    entries = []

    try:
        with open(jsonl_file, 'r') as f:
            for line in f:
                line_num += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")

        return {
            'valid': len(errors) == 0,
            'total_lines': line_num,
            'valid_entries': len(entries),
            'errors': errors[:10],  # First 10 errors
            'error_count': len(errors)
        }
    except FileNotFoundError:
        return {
            'valid': False,
            'total_lines': 0,
            'valid_entries': 0,
            'errors': [f"File not found: {jsonl_file}"],
            'error_count': 1
        }


def print_validation_results(validation: Dict[str, Any]) -> None:
    """Print validation results to console."""
    print("\n" + "="*60)
    print("JSONL VALIDATION RESULTS")
    print("="*60)

    print(f"\nValid: {validation['valid']}")
    print(f"Total lines: {validation['total_lines']}")
    print(f"Valid entries: {validation['valid_entries']}")
    print(f"Errors: {validation['error_count']}")

    if validation['errors']:
        print("\nErrors (first 10):")
        for error in validation['errors']:
            print(f"  - {error}")

    print("="*60 + "\n")


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 3:
        print("Usage: generate_pod_logs_index.py <combined_json> <output_jsonl>")
        print("\nArguments:")
        print("  combined_json  Path to combined JSON file (e.g., data/pod-logs-combined.json)")
        print("  output_jsonl   Path to output JSONL file (e.g., pod-logs-index.jsonl)")
        sys.exit(1)

    combined_file = sys.argv[1]
    output_file = sys.argv[2]

    print("Generating pod-logs-index.jsonl...")
    print(f"  Input: {combined_file}")
    print(f"  Output: {output_file}")

    # Load combined data
    combined_data = load_json_file(combined_file)
    if combined_data is None:
        sys.exit(1)

    # Extract data array if present
    if isinstance(combined_data, dict) and 'data' in combined_data:
        combined_data = combined_data['data']

    if not isinstance(combined_data, list):
        print(f"Error: Expected list of entries, got {type(combined_data).__name__}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ Loaded {len(combined_data)} entries")

    # Generate JSONL
    entries_written = generate_jsonl(combined_data, output_file)
    print(f"✓ Generated {entries_written} entries in {output_file}")

    # Validate output
    print("\nValidating output...")
    validation = validate_jsonl(output_file)
    print_validation_results(validation)

    if validation['valid']:
        print(f"✓ Successfully generated and validated {output_file}")
        print(f"  Total entries: {validation['valid_entries']}")
        sys.exit(0)
    else:
        print(f"✗ Validation failed with {validation['error_count']} errors")
        sys.exit(1)


if __name__ == '__main__':
    main()