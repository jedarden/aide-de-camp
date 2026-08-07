#!/usr/bin/env python3
"""
Create comprehensive pod-logs-index.jsonl with proper schema according to acceptance criteria.

Schema:
- pod_name (string)
- namespace (string)
- creation_timestamp (ISO string)
- deletion_timestamp (ISO string or null)
- log_file_path (relative path)
- analysis_file_path (relative path)
- detected_patterns (array: startup, oom_kill, error, performance)
- key_timestamps (object with relevant dates)
- log_size_bytes (integer)
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


def find_pod_log_files(base_dir: Path) -> List[Path]:
    """Find all pod log files in research directories."""
    log_files = []
    for log_file in base_dir.rglob("*.log"):
        # Skip if this is an analysis file
        if "analysis" in log_file.name:
            continue
        log_files.append(log_file)
    return sorted(log_files)


def find_analysis_files(base_dir: Path) -> Dict[str, Path]:
    """Find all analysis files and create mapping."""
    analysis_map = {}
    for analysis_file in base_dir.rglob("*analysis*.json"):
        # Extract the base log file name from the analysis filename
        # e.g., "pod-pbx-web-5ff68464d-mkn8n-2026-08-06-analysis.json"
        # -> "pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log"
        base_name = analysis_file.name.replace("-analysis.json", ".log")
        analysis_map[base_name] = analysis_file
    return analysis_map


def extract_pod_info_from_filename(log_file: Path) -> Dict[str, Any]:
    """Extract pod information from log filename."""
    filename = log_file.name

    # Try to match various filename patterns
    # Pattern 1: pod-{pod_name}-{date}.log
    match1 = re.match(r'pod-([^-]+(?:-[^-]+)*)-(\d{4}-\d{2}-\d{2})(?:-[^.]*)?\.log$', filename)
    if match1:
        pod_name = match1.group(1)
        date_str = match1.group(2)
        return {"pod_name": pod_name, "date": date_str, "confidence": "high"}

    # Pattern 2: {pod_name}.log (simple case)
    match2 = re.match(r'^([^-]+(?:-[^-]+)*)\.log$', filename)
    if match2:
        pod_name = match2.group(1)
        return {"pod_name": pod_name, "date": None, "confidence": "medium"}

    # Pattern 3: {anything}-{namespace}-{deployment}-{replicaset}-{random}.log
    match3 = re.match(r'^(?:[^-]+-)?([^-]+)-([^-]+)-([^-]+)-([a-z0-9]+)-([a-z0-9]+)\.log$', filename)
    if match3:
        # This seems to be a full k8s pod name
        full_pod_name = match3.group(0)
        return {"pod_name": full_pod_name, "date": None, "confidence": "high"}

    # Default: use full filename as pod name
    return {"pod_name": filename.replace(".log", ""), "date": None, "confidence": "low"}


def load_analysis_file(analysis_path: Path) -> Optional[Dict[str, Any]]:
    """Load and parse analysis file."""
    try:
        with open(analysis_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading analysis file {analysis_path}: {e}")
        return None


def extract_namespace_from_path(log_file: Path) -> str:
    """Extract namespace from directory path."""
    parts = log_file.parts
    # Look for patterns like pbx-web-30days or whisper-stt-30days
    for i, part in enumerate(parts):
        if "pbx-web" in part.lower():
            return "pbx-web"
        elif "whisper-stt" in part.lower():
            return "whisper-stt"
    return "unknown"


def get_log_file_size(log_file: Path) -> int:
    """Get log file size in bytes."""
    try:
        return log_file.stat().st_size
    except Exception:
        return 0


def extract_detected_patterns(analysis_data: Optional[Dict[str, Any]]) -> List[str]:
    """Extract detected patterns from analysis data."""
    if not analysis_data or "patterns" not in analysis_data:
        return []

    patterns = []
    for pattern_type in ["startup", "oom_kill", "error", "performance"]:
        pattern_info = analysis_data["patterns"].get(pattern_type, {})
        count = pattern_info.get("count", 0)
        if count > 0:
            patterns.append(pattern_type)

    return patterns


def extract_key_timestamps(analysis_data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Extract key timestamps from analysis data."""
    timestamps = {}

    if not analysis_data:
        return timestamps

    # Analysis date
    if "analysis_date" in analysis_data:
        timestamps["analysis_date"] = analysis_data["analysis_date"]

    # Pattern timestamps
    if "patterns" in analysis_data:
        for pattern_type, pattern_data in analysis_data["patterns"].items():
            if pattern_data.get("timestamps") and len(pattern_data["timestamps"]) > 0:
                first_ts = pattern_data["timestamps"][0]
                if first_ts and first_ts != "unknown":
                    timestamps[f"{pattern_type}_first"] = first_ts

    # Summary timestamps
    if "summary" in analysis_data:
        for item in analysis_data["summary"]:
            category = item.get("category", "")
            if "first_occurrence" in item and item["first_occurrence"]:
                timestamps[f"{category}_first"] = item["first_occurrence"]
            if "last_occurrence" in item and item["last_occurrence"]:
                timestamps[f"{category}_last"] = item["last_occurrence"]

    return timestamps


def create_index_entry(log_file: Path, analysis_file: Optional[Path]) -> Dict[str, Any]:
    """Create a single index entry."""
    # Extract pod information
    pod_info = extract_pod_info_from_filename(log_file)
    pod_name = pod_info["pod_name"]
    namespace = extract_namespace_from_path(log_file)

    # Get file size
    log_size = get_log_file_size(log_file)

    # Get relative paths
    relative_log_path = str(log_file.relative_to(Path.cwd()))
    relative_analysis_path = str(analysis_file.relative_to(Path.cwd())) if analysis_file else None

    # Load analysis data if available
    analysis_data = load_analysis_file(analysis_file) if analysis_file else None

    # Extract creation/deletion timestamps (from analysis or use defaults)
    creation_timestamp = None
    deletion_timestamp = None

    if analysis_data:
        # Try to get timestamps from analysis metadata
        if "pod_identification" in analysis_data:
            creation_timestamp = analysis_data["pod_identification"].get("creation_timestamp")
            deletion_timestamp = analysis_data["pod_identification"].get("deletion_timestamp")

    # Extract patterns and timestamps
    detected_patterns = extract_detected_patterns(analysis_data)
    key_timestamps = extract_key_timestamps(analysis_data)

    # Add file creation timestamp if available
    if key_timestamps and "analysis_date" in key_timestamps:
        key_timestamps["index_created"] = datetime.now().isoformat()

    # Create the index entry according to schema
    entry = {
        "pod_name": pod_name,
        "namespace": namespace,
        "creation_timestamp": creation_timestamp,
        "deletion_timestamp": deletion_timestamp,
        "log_file_path": relative_log_path,
        "analysis_file_path": relative_analysis_path,
        "detected_patterns": detected_patterns,
        "key_timestamps": key_timestamps,
        "log_size_bytes": log_size
    }

    return entry


def validate_jsonl(output_file: Path) -> bool:
    """Validate the JSONL file format."""
    try:
        with open(output_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue  # Skip empty lines
                try:
                    json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"JSON validation error on line {line_num}: {e}")
                    return False
        return True
    except Exception as e:
        print(f"Error validating JSONL file: {e}")
        return False


def main():
    """Main function to create comprehensive pod logs index."""
    base_dir = Path.cwd()
    research_dir = base_dir / "research"

    print(f"Scanning for pod log files in {research_dir}...")

    # Find all pod log files
    log_files = find_pod_log_files(research_dir)
    print(f"Found {len(log_files)} pod log files")

    # Find all analysis files
    analysis_files = find_analysis_files(research_dir)
    print(f"Found {len(analysis_files)} analysis files")

    # Create index entries
    index_entries = []

    for log_file in log_files:
        # Find corresponding analysis file
        analysis_file = analysis_files.get(log_file.name)

        # Create index entry
        entry = create_index_entry(log_file, analysis_file)
        index_entries.append(entry)

    # Sort by pod name for consistency
    index_entries.sort(key=lambda x: x["pod_name"])

    # Write to JSONL file
    output_file = base_dir / "pod-logs-index.jsonl"
    print(f"Writing {len(index_entries)} entries to {output_file}...")

    with open(output_file, 'w') as f:
        for entry in index_entries:
            f.write(json.dumps(entry) + '\n')

    # Validate the JSONL file
    print("Validating JSONL format...")
    if validate_jsonl(output_file):
        print("✓ JSONL validation passed")
    else:
        print("✗ JSONL validation failed")
        return 1

    # Print summary statistics
    print(f"\nIndex created successfully!")
    print(f"Total entries: {len(index_entries)}")

    # Count patterns
    pattern_counts = {}
    for entry in index_entries:
        for pattern in entry["detected_patterns"]:
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

    if pattern_counts:
        print(f"\nDetected patterns summary:")
        for pattern, count in sorted(pattern_counts.items()):
            print(f"  {pattern}: {count}")

    # Calculate total log size
    total_size = sum(entry["log_size_bytes"] for entry in index_entries)
    print(f"\nTotal log data: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")

    return 0


if __name__ == "__main__":
    exit(main())