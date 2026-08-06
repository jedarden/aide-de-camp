#!/usr/bin/env python3
"""
Analysis Pattern Extraction Script

Extracts detected patterns and key timestamps from analysis files.
Corresponds to log files and extracts pattern information from analysis JSON files.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def find_analysis_file(log_file_path: str, research_base: str = "research") -> Optional[str]:
    """
    Find the corresponding analysis file for a given log file.

    Args:
        log_file_path: Path to the log file (relative or absolute)
        research_base: Base directory for research files (default: "research")

    Returns:
        Relative path to analysis file, or None if not found
    """
    # Convert to Path object for manipulation
    log_path = Path(log_file_path)

    # Construct potential analysis file paths
    # Pattern 1: research/<namespace>-30days/pod-logs/<log_file_name>-analysis.json
    # Pattern 2: research/<namespace>-30days/<log_file_path>-analysis.json

    analysis_candidates = []

    # Try to determine namespace from path
    path_parts = log_path.parts

    # Look for namespace-30days pattern
    namespace = None
    for part in path_parts:
        if part.endswith("-30days"):
            namespace = part.replace("-30days", "")
            break

    if namespace:
        # Build analysis path based on log file location
        log_name = log_path.stem  # filename without extension

        # Candidate 1: research/<namespace>-30days/pod-logs/<log_name>-analysis.json
        analysis_candidates.append(f"{research_base}/{namespace}-30days/pod-logs/{log_name}-analysis.json")

        # Candidate 2: research/<namespace>-30days/pod-logs/<original_path>-analysis.json
        # Keep the full relative path structure
        relative_path = str(log_path).split("/", 1)[-1] if "/" in str(log_path) else str(log_path)
        analysis_candidates.append(f"{research_base}/{namespace}-30days/{relative_path}-analysis.json")

    # Check if any candidate exists
    for candidate in analysis_candidates:
        if Path(candidate).exists():
            return candidate

    return None


def extract_patterns_from_analysis(analysis_file_path: str) -> List[str]:
    """
    Extract detected patterns from an analysis file.

    Args:
        analysis_file_path: Path to the analysis JSON file

    Returns:
        List of detected pattern types (startup, oom_kill, error, performance)
    """
    detected_patterns = []

    try:
        with open(analysis_file_path, 'r') as f:
            analysis_data = json.load(f)

        patterns = analysis_data.get('patterns', {})

        # Check each pattern type and add if count > 0
        for pattern_type in ['startup', 'oom_kill', 'error', 'performance']:
            pattern_info = patterns.get(pattern_type, {})
            count = pattern_info.get('count', 0)
            if count > 0:
                detected_patterns.append(pattern_type)

    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        # Return empty list if file can't be read
        pass

    return detected_patterns


def extract_key_timestamps(analysis_file_path: str) -> Optional[Dict[str, Any]]:
    """
    Extract key timestamps from an analysis file.

    Args:
        analysis_file_path: Path to the analysis JSON file

    Returns:
        Dictionary with key timestamps, or None if file not accessible
    """
    try:
        with open(analysis_file_path, 'r') as f:
            analysis_data = json.load(f)

        timestamps = {}

        # Add analysis date
        analysis_date = analysis_data.get('analysis_date')
        if analysis_date:
            timestamps['analysis_date'] = analysis_date

        # Add log file name
        file_name = analysis_data.get('file_name')
        if file_name:
            timestamps['log_file'] = file_name

        # Extract pattern-specific timestamps
        patterns = analysis_data.get('patterns', {})

        # For each pattern type with count > 0, extract first/last occurrences
        for pattern_type in ['startup', 'oom_kill', 'error', 'performance']:
            pattern_info = patterns.get(pattern_type, {})
            count = pattern_info.get('count', 0)

            if count > 0:
                timestamps_list = pattern_info.get('timestamps', [])
                if timestamps_list:
                    # Get first known timestamp (not "unknown")
                    first_ts = next((ts for ts in timestamps_list if ts != "unknown"), None)
                    if first_ts:
                        timestamps[f'{pattern_type}_first'] = first_ts

                    # Get last known timestamp
                    last_ts = next((ts for ts in reversed(timestamps_list) if ts != "unknown"), None)
                    if last_ts:
                        timestamps[f'{pattern_type}_last'] = last_ts

        return timestamps if timestamps else None

    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def process_log_file(log_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single log file entry and extract analysis patterns.

    Args:
        log_entry: Dictionary containing log file metadata

    Returns:
        Dictionary with extracted analysis data
    """
    log_file_path = log_entry.get('log_file_path', '')

    # Find corresponding analysis file
    analysis_file = find_analysis_file(log_file_path)

    result = {
        'log_file_path': log_file_path,
        'pod_name': log_entry.get('pod_name'),
        'namespace': log_entry.get('namespace'),
        'analysis_file_path': None,
        'detected_patterns': [],
        'key_timestamps': None
    }

    if analysis_file:
        result['analysis_file_path'] = analysis_file
        result['detected_patterns'] = extract_patterns_from_analysis(analysis_file)
        result['key_timestamps'] = extract_key_timestamps(analysis_file)

    return result


def extract_patterns_from_metadata(metadata_file: str = "data/pod-log-metadata.json") -> List[Dict[str, Any]]:
    """
    Extract patterns from all log files referenced in a metadata file.

    Args:
        metadata_file: Path to JSON file containing log metadata

    Returns:
        List of dictionaries with extracted pattern data
    """
    if not Path(metadata_file).exists():
        print(f"Error: Metadata file '{metadata_file}' not found")
        return []

    with open(metadata_file, 'r') as f:
        log_entries = json.load(f)

    results = []

    for log_entry in log_entries:
        result = process_log_file(log_entry)
        results.append(result)

    return results


def extract_patterns_from_file_list(file_list: List[str]) -> List[Dict[str, Any]]:
    """
    Extract patterns from a list of log file paths.

    Args:
        file_list: List of log file paths (relative or absolute)

    Returns:
        List of dictionaries with extracted pattern data
    """
    results = []

    for log_file_path in file_list:
        log_entry = {'log_file_path': log_file_path}
        result = process_log_file(log_entry)
        results.append(result)

    return results


def main():
    """Main entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract analysis patterns and timestamps from log analysis files'
    )
    parser.add_argument(
        '--metadata',
        default='data/pod-log-metadata.json',
        help='Path to metadata JSON file containing log file information'
    )
    parser.add_argument(
        '--output',
        help='Output JSON file path (default: print to stdout)'
    )
    parser.add_argument(
        '--log-files',
        nargs='+',
        help='Specific log files to process (instead of using metadata file)'
    )

    args = parser.parse_args()

    # Extract patterns
    if args.log_files:
        results = extract_patterns_from_file_list(args.log_files)
    else:
        results = extract_patterns_from_metadata(args.metadata)

    # Output results
    json_output = json.dumps(results, indent=2)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(json_output)
        print(f"Results written to {args.output}")
    else:
        print(json_output)

    # Print summary statistics
    total_files = len(results)
    files_with_analysis = sum(1 for r in results if r['analysis_file_path'])
    files_with_patterns = sum(1 for r in results if r['detected_patterns'])

    print(f"\nSummary:", file=__import__('sys').stderr)
    print(f"  Total log files: {total_files}", file=__import__('sys').stderr)
    print(f"  Files with analysis: {files_with_analysis}", file=__import__('sys').stderr)
    print(f"  Files with detected patterns: {files_with_patterns}", file=__import__('sys').stderr)

    # Pattern breakdown
    pattern_counts = {}
    for result in results:
        for pattern in result['detected_patterns']:
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

    if pattern_counts:
        print(f"  Pattern breakdown:", file=__import__('sys').stderr)
        for pattern, count in sorted(pattern_counts.items()):
            print(f"    {pattern}: {count}", file=__import__('sys').stderr)


if __name__ == '__main__':
    main()
