#!/usr/bin/env python3
"""
Generate pod-logs-index.jsonl from metadata and pattern extraction data.

Combines:
- data/pod-log-metadata.json (pod identification and log file metadata)
- data/analysis-patterns-extracted.json (pattern detection results)

Outputs: pod-logs-index.jsonl (complete schema-compliant JSONL)
"""

import json
from pathlib import Path
from typing import Any, Dict
from datetime import datetime


def load_json_file(path: Path) -> Any:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_default_pattern_detection() -> Dict[str, Any]:
    """Create default pattern detection structure."""
    return {
        "startup": {"count": 0, "timestamps": [], "samples": []},
        "oom_kill": {"count": 0, "timestamps": [], "samples": []},
        "error": {"count": 0, "timestamps": [], "samples": []},
        "performance": {"count": 0, "timestamps": [], "samples": []}
    }


def merge_pattern_detection(patterns_data: Dict[str, Any], metadata_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge pattern detection data with metadata.

    patterns_data comes from analysis-patterns-extracted.json
    metadata_entry comes from pod-log-metadata.json
    """
    pattern_detection = create_default_pattern_detection()

    # If no analysis file exists, return defaults
    if not patterns_data or not patterns_data.get("detected_patterns"):
        return pattern_detection

    detected_patterns = patterns_data.get("detected_patterns", [])
    key_timestamps = patterns_data.get("key_timestamps", {})

    # Map detected patterns to pattern categories
    for pattern in detected_patterns:
        if pattern == "startup":
            pattern_detection["startup"]["count"] = key_timestamps.get("startup_count", 0)
            pattern_detection["startup"]["timestamps"] = key_timestamps.get("startup_timestamps", [])
            pattern_detection["startup"]["samples"] = key_timestamps.get("startup_samples", [])
        elif pattern == "oom_kill":
            pattern_detection["oom_kill"]["count"] = key_timestamps.get("oom_kill_count", 0)
            pattern_detection["oom_kill"]["timestamps"] = key_timestamps.get("oom_kill_timestamps", [])
            pattern_detection["oom_kill"]["samples"] = key_timestamps.get("oom_kill_samples", [])
        elif pattern == "error":
            # Get error details from key_timestamps
            error_count = key_timestamps.get("error_count", 1 if pattern == "error" else 0)
            pattern_detection["error"]["count"] = error_count
            pattern_detection["error"]["timestamps"] = key_timestamps.get("error_timestamps", ["unknown"])
            pattern_detection["error"]["samples"] = key_timestamps.get("error_samples", ["Error pattern detected"])
        elif pattern == "performance":
            pattern_detection["performance"]["count"] = key_timestamps.get("performance_count", 0)
            pattern_detection["performance"]["timestamps"] = key_timestamps.get("performance_timestamps", [])
            pattern_detection["performance"]["samples"] = key_timestamps.get("performance_samples", [])

    return pattern_detection


def create_temporal_boundaries(metadata_entry: Dict[str, Any], patterns_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create temporal boundaries section."""
    collection_date = metadata_entry.get("collection_date", "2026-08-06")

    # Get analysis date from patterns data
    analysis_date = None
    first_log_entry = None
    last_log_entry = None

    if patterns_data and patterns_data.get("key_timestamps"):
        key_timestamps = patterns_data["key_timestamps"]
        analysis_date_str = key_timestamps.get("analysis_date")
        if analysis_date_str:
            # Ensure it has Z suffix
            if not analysis_date_str.endswith('Z'):
                analysis_date_str += 'Z'
            analysis_date = analysis_date_str

        # Get first and last log entry from patterns data if available
        first_log_entry = key_timestamps.get("first_log_entry")
        last_log_entry = key_timestamps.get("last_log_entry")

    return {
        "first_log_entry": first_log_entry,
        "last_log_entry": last_log_entry,
        "analysis_date": analysis_date,
        "collection_date": collection_date
    }


def generate_jsonl_entry(metadata_entry: Dict[str, Any], patterns_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a complete JSONL entry combining metadata and pattern detection."""

    # Extract log file path and ensure it has the correct prefix
    log_file_path = metadata_entry.get("log_file_path", "")
    if not log_file_path.startswith("research/"):
        log_file_path = f"research/{log_file_path}"

    # Determine analysis file path
    analysis_file_path = None
    if patterns_data and patterns_data.get("analysis_file_path"):
        analysis_file_path = patterns_data["analysis_file_path"]
        if analysis_file_path and not analysis_file_path.startswith("research/"):
            analysis_file_path = f"research/{analysis_file_path}"

    # Get analysis date for temporal_boundaries
    analysis_date = None
    if patterns_data and patterns_data.get("key_timestamps"):
        key_timestamps = patterns_data["key_timestamps"]
        analysis_date_str = key_timestamps.get("analysis_date")
        if analysis_date_str:
            if not analysis_date_str.endswith('Z'):
                analysis_date_str += 'Z'
            analysis_date = analysis_date_str

    # Create temporal boundaries
    temporal_boundaries = create_temporal_boundaries(metadata_entry, patterns_data)

    # Create pattern detection
    pattern_detection = merge_pattern_detection(patterns_data, metadata_entry)

    return {
        "pod_identification": {
            "pod_name": metadata_entry.get("pod_name", "unknown"),
            "namespace": metadata_entry.get("namespace", "unknown"),
            "pod_phase": metadata_entry.get("pod_phase", "Unknown"),
            "restart_count": metadata_entry.get("restart_count", 0),
            "creation_timestamp": metadata_entry.get("creation_timestamp"),
            "deletion_timestamp": metadata_entry.get("deletion_timestamp"),
            "container_image": metadata_entry.get("container_image"),
            "node_name": metadata_entry.get("node_name")
        },
        "log_file_metadata": {
            "log_file_path": log_file_path,
            "log_size_bytes": metadata_entry.get("log_size_bytes", 0),
            "log_line_count": metadata_entry.get("log_line_count"),
            "collection_date": metadata_entry.get("collection_date", "2026-08-06"),
            "log_type": metadata_entry.get("log_type")
        },
        "analysis_metadata": {
            "analysis_file_path": analysis_file_path,
            "analysis_date": analysis_date
        },
        "pattern_detection": pattern_detection,
        "temporal_boundaries": temporal_boundaries
    }


def main():
    """Main generation function."""
    print("Loading data files...")

    # Load metadata
    metadata_path = Path("data/pod-log-metadata.json")
    if not metadata_path.exists():
        print(f"Error: {metadata_path} not found")
        return 1

    metadata_list = load_json_file(metadata_path)
    print(f"  Loaded {len(metadata_list)} metadata entries from {metadata_path}")

    # Load pattern extraction results
    patterns_path = Path("data/analysis-patterns-extracted.json")
    if not patterns_path.exists():
        print(f"Error: {patterns_path} not found")
        return 1

    patterns_list = load_json_file(patterns_path)
    print(f"  Loaded {len(patterns_list)} pattern entries from {patterns_path}")

    # Create a lookup dictionary for patterns data by log_file_path
    patterns_lookup = {
        entry.get("log_file_path", ""): entry
        for entry in patterns_list
    }

    # Generate JSONL entries
    print("\nGenerating JSONL entries...")
    jsonl_entries = []

    for metadata_entry in metadata_list:
        log_file_path = metadata_entry.get("log_file_path", "")
        patterns_data = patterns_lookup.get(log_file_path, {})

        jsonl_entry = generate_jsonl_entry(metadata_entry, patterns_data)
        jsonl_entries.append(jsonl_entry)

    print(f"  Generated {len(jsonl_entries)} JSONL entries")

    # Write to output file
    output_path = Path("pod-logs-index.jsonl")
    print(f"\nWriting to {output_path}...")

    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in jsonl_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    file_size = output_path.stat().st_size
    print(f"  Wrote {len(jsonl_entries)} entries ({file_size:,} bytes)")

    print(f"\n✅ Generated {output_path}")
    return 0


if __name__ == "__main__":
    exit(main())
