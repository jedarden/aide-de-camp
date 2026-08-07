#!/usr/bin/env python3
"""
Parse all .analysis.json files and extract pattern and timestamp data.

This script reads all analysis JSON files found in the workspace and extracts:
- detected_patterns (array: startup, oom_kill, error, performance)
- key_timestamps (object with relevant dates from analysis)

The extracted data is stored in a structured format keyed by log_file_path.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any


def find_analysis_files(root_dir: Path) -> List[Path]:
    """Find all analysis JSON files."""
    return sorted(root_dir.rglob("*-analysis.json"))


def extract_patterns_from_analysis(analysis_data: Dict[str, Any]) -> List[str]:
    """
    Extract detected patterns from analysis data.

    Returns a list of pattern types that have at least one occurrence.
    Handles both log-level and summary-level analysis formats.
    """
    detected_patterns = []

    patterns = analysis_data.get("patterns", {})
    for pattern_type, pattern_data in patterns.items():
        count = pattern_data.get("count", 0)
        if count > 0:
            detected_patterns.append(pattern_type)

    return detected_patterns


def extract_key_timestamps(analysis_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract key timestamps from analysis data.

    Returns a dictionary with relevant dates from the analysis.
    """
    key_timestamps = {}

    # Add analysis date if present
    if "analysis_date" in analysis_data:
        key_timestamps["analysis_date"] = analysis_data["analysis_date"]

    # Collect timestamps from patterns
    patterns = analysis_data.get("patterns", {})
    for pattern_type, pattern_data in patterns.items():
        timestamps = pattern_data.get("timestamps", [])
        if timestamps:
            # Store first and last occurrence for each pattern type
            key_timestamps[f"{pattern_type}_first"] = timestamps[0]
            if len(timestamps) > 1:
                key_timestamps[f"{pattern_type}_last"] = timestamps[-1]

    return key_timestamps


def parse_analysis_file(file_path: Path) -> Dict[str, Any]:
    """
    Parse a single analysis file and extract metadata.

    Returns:
        Dictionary with extracted data keyed by log_file_path, or None if parsing fails
    """
    try:
        with open(file_path, 'r') as f:
            analysis_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to parse {file_path}: {e}")
        return None

    # Handle case where JSON loads as a list instead of dict
    if isinstance(analysis_data, list):
        # This is an array format (e.g., replicaset data)
        # Extract timestamp from the first item if available
        first_timestamp = ""
        if analysis_data and len(analysis_data) > 0:
            first_item = analysis_data[0]
            if isinstance(first_item, dict) and "creationTimestamp" in first_item:
                first_timestamp = first_item["creationTimestamp"]

        return {
            "analysis_file_path": str(file_path),
            "log_file_path": f"array-data/{file_path.stem}",
            "log_file_name": file_path.name,
            "analysis_type": "array",
            "detected_patterns": [],
            "key_timestamps": {
                "first_timestamp": first_timestamp,
                "item_count": len(analysis_data)
            },
            "pattern_counts": {},
            "data_structure": "array"
        }

    if not isinstance(analysis_data, dict):
        print(f"Warning: Unexpected format in {file_path} (expected dict, got {type(analysis_data).__name__})")
        return None

    # Get the log file path (this is the key) - handle both formats
    log_file_path = analysis_data.get("file", str(file_path))

    # For summary-level analysis files, extract metadata differently
    if "metadata" in analysis_data or "report_metadata" in analysis_data:
        # This is a summary analysis file, not a log-level one
        metadata_key = "metadata" if "metadata" in analysis_data else "report_metadata"
        metadata = analysis_data.get(metadata_key, {})

        # Return a simplified structure for summary files
        return {
            "analysis_file_path": str(file_path),
            "log_file_path": f"summary/{metadata.get('analysis_type', 'unknown')}",
            "log_file_name": metadata.get("analysis_type", "summary-analysis"),
            "analysis_type": "summary",
            "detected_patterns": [],
            "key_timestamps": {
                "generated_at": metadata.get("generated_at", ""),
                "analysis_period": metadata.get("analysis_period", "")
            },
            "pattern_counts": {},
            "services_analyzed": metadata.get("services_analyzed", [])
        }

    # Extract detected patterns (for log-level analysis files)
    detected_patterns = extract_patterns_from_analysis(analysis_data)

    # Extract key timestamps
    key_timestamps = extract_key_timestamps(analysis_data)

    # Build the extracted data structure
    extracted_data = {
        "analysis_file_path": str(file_path),
        "log_file_path": log_file_path,
        "log_file_name": analysis_data.get("file_name", ""),
        "analysis_type": "log-level",
        "detected_patterns": detected_patterns,
        "key_timestamps": key_timestamps,
        "pattern_counts": {
            pattern_type: pattern_data.get("count", 0)
            for pattern_type, pattern_data in analysis_data.get("patterns", {}).items()
        }
    }

    return extracted_data


def main():
    """Main function to parse all analysis files."""
    root_dir = Path("/home/coding/aide-de-camp")

    # Find all analysis files
    analysis_files = find_analysis_files(root_dir)
    print(f"Found {len(analysis_files)} analysis files")

    # Parse each analysis file
    extracted_data = {}
    successful_count = 0
    failed_count = 0

    for analysis_file in analysis_files:
        data = parse_analysis_file(analysis_file)
        if data:
            log_file_path = data["log_file_path"]
            extracted_data[log_file_path] = data
            successful_count += 1
        else:
            failed_count += 1

    print(f"Successfully parsed: {successful_count} files")
    print(f"Failed to parse: {failed_count} files")

    # Create output directory if it doesn't exist
    output_dir = Path("/home/coding/aide-de-camp/data")
    output_dir.mkdir(exist_ok=True)

    # Write the extracted data to a JSON file
    output_file = output_dir / "analysis-metadata-extracted.json"
    with open(output_file, 'w') as f:
        json.dump(extracted_data, f, indent=2)

    print(f"\nExtracted data written to: {output_file}")
    print(f"Total log files processed: {len(extracted_data)}")

    # Print summary statistics
    print("\n=== Summary Statistics ===")
    pattern_counts = {}
    for log_file, data in extracted_data.items():
        for pattern in data["detected_patterns"]:
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

    print("Patterns detected across all files:")
    for pattern, count in sorted(pattern_counts.items()):
        print(f"  {pattern}: {count} files")


if __name__ == "__main__":
    main()