#!/usr/bin/env python3
"""
Combine metadata and pattern extraction outputs into a unified data structure.

This script reads both the metadata output (from pod-log-metadata.json or similar)
and the pattern extraction output (from extract_analysis_patterns.py) and merges
them by matching pod log entries via the log_file_path field.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


def load_json_file(file_path: str) -> Optional[Any]:
    """
    Load a JSON file safely.

    Args:
        file_path: Path to the JSON file

    Returns:
        Parsed JSON data, or None if loading fails
    """
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}", file=sys.stderr)
        return None


def create_lookup_dict(patterns: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Create a lookup dictionary from pattern data indexed by log_file_path.

    Args:
        patterns: List of pattern extraction dictionaries

    Returns:
        Dictionary mapping log_file_path to pattern data
    """
    lookup = {}
    for pattern in patterns:
        log_file_path = pattern.get('log_file_path')
        if log_file_path:
            lookup[log_file_path] = pattern
    return lookup


def combine_metadata_with_patterns(
    metadata: List[Dict[str, Any]],
    patterns: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Combine metadata and pattern data by matching log_file_path.

    Args:
        metadata: List of metadata entries from pod-log-metadata.json
        patterns: List of pattern entries from pattern extraction output

    Returns:
        List of combined entries with all fields from both sources
    """
    # Create lookup for patterns
    pattern_lookup = create_lookup_dict(patterns)

    combined = []
    mismatched_log_files = []

    for meta_entry in metadata:
        log_file_path = meta_entry.get('log_file_path')

        # Create combined entry starting with all metadata fields
        combined_entry = meta_entry.copy()

        # Add pattern-specific fields with default values
        combined_entry['analysis_file_path'] = None
        combined_entry['detected_patterns'] = []
        combined_entry['key_timestamps'] = None
        combined_entry['pattern_data_available'] = False

        if log_file_path and log_file_path in pattern_lookup:
            # Found matching pattern data
            pattern_entry = pattern_lookup[log_file_path]

            # Merge pattern fields
            combined_entry.update({
                'analysis_file_path': pattern_entry.get('analysis_file_path'),
                'detected_patterns': pattern_entry.get('detected_patterns', []),
                'key_timestamps': pattern_entry.get('key_timestamps'),
                'pattern_data_available': True
            })

            # Validate that pod names match (if both exist)
            meta_pod = meta_entry.get('pod_name')
            pattern_pod = pattern_entry.get('pod_name')
            if meta_pod and pattern_pod and meta_pod != pattern_pod:
                mismatched_log_files.append({
                    'log_file_path': log_file_path,
                    'metadata_pod': meta_pod,
                    'pattern_pod': pattern_pod
                })
        else:
            # No pattern data found for this log file
            combined_entry['pattern_data_available'] = False

        combined.append(combined_entry)

    return combined, mismatched_log_files


def generate_summary(combined: List[Dict[str, Any]], mismatched: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate summary statistics for the combined dataset.

    Args:
        combined: List of combined entries
        mismatched: List of entries with mismatched pod names

    Returns:
        Dictionary with summary statistics
    """
    total = len(combined)
    with_pattern_data = sum(1 for entry in combined if entry.get('pattern_data_available'))
    without_pattern_data = total - with_pattern_data

    # Count pattern types
    pattern_counts = {
        'startup': 0,
        'oom_kill': 0,
        'error': 0,
        'performance': 0
    }

    for entry in combined:
        for pattern in entry.get('detected_patterns', []):
            if pattern in pattern_counts:
                pattern_counts[pattern] += 1

    return {
        'total_entries': total,
        'with_pattern_data': with_pattern_data,
        'without_pattern_data': without_pattern_data,
        'pattern_type_counts': pattern_counts,
        'mismatched_pod_names': len(mismatched),
        'mismatched_details': mismatched[:5]  # First 5 mismatches
    }


def save_combined_data(
    combined: List[Dict[str, Any]],
    summary: Dict[str, Any],
    metadata_file: str,
    patterns_file: str,
    output_file: str
) -> None:
    """
    Save combined data to JSON file with metadata header.

    Args:
        combined: List of combined entries
        summary: Summary statistics
        metadata_file: Source metadata file path
        patterns_file: Source patterns file path
        output_file: Output file path
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'source_metadata_file': metadata_file,
            'source_patterns_file': patterns_file,
            'combination_type': 'metadata_and_patterns'
        },
        'summary': summary,
        'data': combined
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ Combined data saved to {output_path}")


def print_summary(summary: Dict[str, Any]) -> None:
    """Print summary statistics to console."""
    print("\n" + "="*60)
    print("COMBINED DATA SUMMARY")
    print("="*60)

    print(f"\nTotal entries: {summary['total_entries']}")
    print(f"  With pattern data: {summary['with_pattern_data']}")
    print(f"  Without pattern data: {summary['without_pattern_data']}")

    pattern_counts = summary.get('pattern_type_counts', {})
    if any(pattern_counts.values()):
        print("\nPattern type counts:")
        for pattern_type, count in pattern_counts.items():
            if count > 0:
                print(f"  - {pattern_type}: {count}")

    mismatched = summary.get('mismatched_pod_names', 0)
    if mismatched > 0:
        print(f"\n⚠ Mismatched pod names: {mismatched}")
        print("  Details (first 5):")
        for detail in summary.get('mismatched_details', []):
            print(f"    - {detail['log_file_path']}")
            print(f"      metadata: {detail['metadata_pod']}")
            print(f"      pattern:  {detail['pattern_pod']}")

    print("="*60 + "\n")


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 3:
        print("Usage: combine_metadata_and_patterns.py <metadata_file> <patterns_file> [output_file]")
        print("\nArguments:")
        print("  metadata_file  Path to metadata JSON file (e.g., data/pod-log-metadata.json)")
        print("  patterns_file  Path to pattern extraction JSON file")
        print("  output_file    Optional output file path (default: data/combined-metadata-patterns.json)")
        sys.exit(1)

    metadata_file = sys.argv[1]
    patterns_file = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else "data/combined-metadata-patterns.json"

    print("Combining metadata and pattern extraction data...")
    print(f"  Metadata source: {metadata_file}")
    print(f"  Patterns source: {patterns_file}")

    # Load input files
    metadata = load_json_file(metadata_file)
    if metadata is None:
        sys.exit(1)

    patterns = load_json_file(patterns_file)
    if patterns is None:
        sys.exit(1)

    print("✓ Loaded input files")

    # Validate data types
    if not isinstance(metadata, list):
        print(f"Error: Expected metadata to be a list, got {type(metadata).__name__}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(patterns, list):
        print(f"Error: Expected patterns to be a list, got {type(patterns).__name__}", file=sys.stderr)
        sys.exit(1)

    print(f"  Metadata entries: {len(metadata)}")
    print(f"  Pattern entries: {len(patterns)}")

    # Combine data
    combined, mismatched = combine_metadata_with_patterns(metadata, patterns)
    print(f"✓ Combined {len(combined)} entries")

    # Generate summary
    summary = generate_summary(combined, mismatched)

    # Save output
    save_combined_data(
        combined,
        summary,
        metadata_file,
        patterns_file,
        output_file
    )

    # Print summary
    print_summary(summary)

    print(f"✓ Combination complete!")


if __name__ == '__main__':
    main()
