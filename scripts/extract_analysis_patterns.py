#!/usr/bin/env python3
"""
Analysis Pattern Extraction Script

Extracts detected patterns and key timestamps from analysis files corresponding to log files.
Handles missing analysis files by returning empty patterns/null timestamps.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any


def find_analysis_file(log_file_path: str, base_dirs: List[str]) -> Optional[str]:
    """
    Find the corresponding analysis file for a given log file.

    Args:
        log_file_path: Path to the log file (relative path like 'pbx-web-30days/pod-logs/pod-name.log')
        base_dirs: List of base directories to search for analysis files

    Returns:
        Path to analysis file if found, None otherwise
    """
    # Extract the filename from the log file path
    log_filename = Path(log_file_path).name

    # Generate the expected analysis filename
    analysis_filename = log_filename.replace('.log', '-analysis.json')

    # Search in each base directory
    for base_dir in base_dirs:
        # Try direct path
        analysis_path = Path(base_dir) / analysis_filename
        if analysis_path.exists():
            return str(analysis_path)

        # Try in pod-logs subdirectory
        pod_logs_path = Path(base_dir) / 'pod-logs' / analysis_filename
        if pod_logs_path.exists():
            return str(pod_logs_path)

        # Try with 'pod-' prefix if the log filename doesn't have it
        if not log_filename.startswith('pod-'):
            pod_prefixed = f"pod-{analysis_filename}"
            pod_prefix_path = Path(base_dir) / 'pod-logs' / pod_prefixed
            if pod_prefix_path.exists():
                return str(pod_prefix_path)

    return None


def extract_patterns_from_analysis(analysis_file_path: str) -> Dict[str, Any]:
    """
    Extract detected patterns and timestamps from an analysis file.

    Args:
        analysis_file_path: Path to the analysis JSON file

    Returns:
        Dictionary containing detected patterns and key timestamps
    """
    try:
        with open(analysis_file_path, 'r') as f:
            analysis_data = json.load(f)

        # Extract detected patterns
        detected_patterns = []
        patterns = analysis_data.get('patterns', {})

        for pattern_type, pattern_data in patterns.items():
            if pattern_data.get('count', 0) > 0:
                detected_patterns.append(pattern_type)

        # Extract key timestamps
        key_timestamps = {}

        # Add analysis date
        if 'analysis_date' in analysis_data:
            key_timestamps['analysis_date'] = analysis_data['analysis_date']

        # Collect timestamps from each pattern type
        for pattern_type, pattern_data in patterns.items():
            if pattern_data.get('timestamps'):
                pattern_timestamps = pattern_data['timestamps']
                if pattern_timestamps:
                    key_timestamps[f'{pattern_type}_first'] = pattern_timestamps[0]
                    key_timestamps[f'{pattern_type}_last'] = pattern_timestamps[-1]

        # Extract file metadata
        key_timestamps['log_file'] = analysis_data.get('file_name', 'unknown')

        return {
            'detected_patterns': detected_patterns,
            'key_timestamps': key_timestamps if key_timestamps else None
        }

    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to parse {analysis_file_path}: {e}")
        return {
            'detected_patterns': [],
            'key_timestamps': None
        }


def extract_analysis_data(
    log_metadata_file: str,
    analysis_base_dirs: List[str],
    output_file: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extract analysis pattern data for all log files.

    Args:
        log_metadata_file: Path to pod-log-metadata.json
        analysis_base_dirs: List of base directories containing analysis files
        output_file: Optional path to save output JSON

    Returns:
        List of dictionaries containing analysis data for each log file
    """
    # Load log metadata
    with open(log_metadata_file, 'r') as f:
        log_metadata = json.load(f)

    results = []

    for log_entry in log_metadata:
        log_file_path = log_entry.get('log_file_path', '')
        pod_name = log_entry.get('pod_name', 'unknown')
        namespace = log_entry.get('namespace', 'unknown')

        # Find corresponding analysis file
        analysis_file = find_analysis_file(log_file_path, analysis_base_dirs)

        if analysis_file:
            # Extract patterns and timestamps from analysis file
            analysis_data = extract_patterns_from_analysis(analysis_file)
            analysis_file_path = os.path.relpath(analysis_file, '/home/coding/aide-de-camp')
        else:
            # Handle missing analysis file
            analysis_data = {
                'detected_patterns': [],
                'key_timestamps': None
            }
            analysis_file_path = None

        result_entry = {
            'log_file_path': log_file_path,
            'pod_name': pod_name,
            'namespace': namespace,
            'analysis_file_path': analysis_file_path,
            'detected_patterns': analysis_data['detected_patterns'],
            'key_timestamps': analysis_data['key_timestamps']
        }

        results.append(result_entry)

    # Save to output file if specified
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"Extracted analysis data for {len(results)} log files")
        print(f"Results saved to: {output_file}")

        # Print summary statistics
        patterns_count = sum(1 for r in results if r['detected_patterns'])
        print(f"Log files with detected patterns: {patterns_count}/{len(results)}")

        analysis_found = sum(1 for r in results if r['analysis_file_path'])
        print(f"Log files with analysis files: {analysis_found}/{len(results)}")

    return results


def main():
    """Main execution function."""
    # Define paths
    log_metadata_file = '/home/coding/aide-de-camp/data/pod-log-metadata.json'
    output_file = '/home/coding/aide-de-camp/data/analysis-patterns-extracted.json'

    # Define base directories to search for analysis files
    analysis_base_dirs = [
        '/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs',
        '/home/coding/aide-de-camp/research/whisper-stt-30days/pod-logs',
        '/home/coding/aide-de-camp/research/pbx-web-30days',
        '/home/coding/aide-de-camp/research/whisper-stt-30days',
        '/home/coding/aide-de-camp/research/pbx-whisper-deployments-30days',
        '/home/coding/aide-de-camp/research'
    ]

    # Extract analysis data
    results = extract_analysis_data(
        log_metadata_file=log_metadata_file,
        analysis_base_dirs=analysis_base_dirs,
        output_file=output_file
    )

    # Print sample results
    print("\n" + "="*50)
    print("SAMPLE RESULTS (first 3 entries):")
    print("="*50)

    for entry in results[:3]:
        print(f"\nPod: {entry['pod_name']}")
        print(f"Namespace: {entry['namespace']}")
        print(f"Log file: {entry['log_file_path']}")
        print(f"Analysis file: {entry['analysis_file_path'] or 'NOT FOUND'}")
        print(f"Detected patterns: {entry['detected_patterns'] or 'None'}")
        if entry['key_timestamps']:
            print(f"Key timestamps: {json.dumps(entry['key_timestamps'], indent=2)}")
        else:
            print(f"Key timestamps: None")


if __name__ == '__main__':
    main()