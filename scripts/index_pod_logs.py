#!/usr/bin/env python3
"""
Generate pod-logs-index.jsonl from collected pod logs and their analysis files.
Scans multiple research directories and creates a unified index.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Base research directory
RESEARCH_BASE = Path("/home/coding/aide-de-camp/research")

# Known pod-logs directories
POD_LOGS_DIRS = [
    "pbx-web-30days/pod-logs",
    "whisper-stt-30days/pod-logs"
]


def extract_pod_info_from_filename(filename: str) -> Dict[str, Optional[str]]:
    """Extract pod name, namespace, and timestamps from log filename."""
    pod_name = None
    namespace = None
    creation_ts = None
    deletion_ts = None

    # Remove file extension
    name = filename.replace(".log", "").replace("-previous", "").replace("-current", "")

    # Pattern 1: pod-{podname}-{hash}-{date}.log (e.g., pod-whisper-openai-68966786fb-jsb5d-2026-08-06.log)
    match = re.match(r"pod-([^-]+(?:-[^-]+)*)-([a-z0-9]+)-(\d{4}-\d{2}-\d{2})", name)
    if match:
        pod_name = f"{match.group(1)}-{match.group(2)}"
        namespace = match.group(1).replace("-", "-")  # keep as-is
        creation_ts = match.group(3)
        return {"pod_name": pod_name, "namespace": namespace, "creation_timestamp": creation_ts, "deletion_timestamp": deletion_ts}

    # Pattern 2: {namespace}-{podname}-{hash}-{suffix}.log (e.g., pbx-web-pbx-web-5ff68464d-lcfcp.log)
    match = re.match(r"([^-]+)-([^-]+(?:-[^-]+)*)-([a-z0-9]+)-(?:[^-]+)$", name)
    if match:
        namespace = match.group(1)
        pod_name = f"{match.group(2)}-{match.group(3)}"
        return {"pod_name": pod_name, "namespace": namespace, "creation_timestamp": creation_ts, "deletion_timestamp": deletion_ts}

    # Pattern 3: {appname}-{hash}-{suffix}.log (e.g., whisper-openai-68966786fb-jsb5d.log)
    match = re.match(r"([^-]+)-([a-z0-9]+)-([^-]+)$", name)
    if match:
        pod_name = f"{match.group(1)}-{match.group(2)}"
        namespace = match.group(1)
        return {"pod_name": pod_name, "namespace": namespace, "creation_timestamp": creation_ts, "deletion_timestamp": deletion_ts}

    # Pattern 4: {name}-{hash}-{number}-{suffix}.log (e.g., pbx-web-5ff68464d-mkn8n-previous.log)
    match = re.match(r"([^-]+)-([a-z0-9]+)-([a-z0-9]+)-(?:previous|current)", name)
    if match:
        pod_name = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        namespace = match.group(1)
        return {"pod_name": pod_name, "namespace": namespace, "creation_timestamp": creation_ts, "deletion_timestamp": deletion_ts}

    # Fallback: use the name as pod_name
    return {"pod_name": name, "namespace": None, "creation_timestamp": creation_ts, "deletion_timestamp": deletion_ts}


def load_analysis_file(analysis_path: Path) -> Dict:
    """Load analysis JSON file if it exists."""
    if analysis_path.exists():
        try:
            with open(analysis_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {analysis_path}: {e}")
    return {}


def extract_patterns(analysis_data: Dict) -> List[str]:
    """Extract detected patterns from analysis data."""
    patterns = []
    if not analysis_data:
        return patterns

    patterns_dict = analysis_data.get("patterns", {})
    for pattern_type in ["startup", "oom_kill", "error", "performance"]:
        if patterns_dict.get(pattern_type, {}).get("count", 0) > 0:
            patterns.append(pattern_type)

    return patterns


def extract_key_timestamps(analysis_data: Dict, log_path: Path) -> Dict:
    """Extract key timestamps from analysis data."""
    timestamps = {}

    if not analysis_data:
        return timestamps

    patterns_dict = analysis_data.get("patterns", {})
    for pattern_type, pattern_data in patterns_dict.items():
        ts_list = pattern_data.get("timestamps", [])
        if ts_list:
            timestamps[f"{pattern_type}_first"] = ts_list[0]
            timestamps[f"{pattern_type}_last"] = ts_list[-1]

    # Add analysis date if available
    if "analysis_date" in analysis_data:
        timestamps["analysis_date"] = analysis_data["analysis_date"]

    # Add file modification time
    if log_path.exists():
        timestamps["file_modified"] = datetime.fromtimestamp(log_path.stat().st_mtime).isoformat()

    return timestamps


def scan_pod_logs_directory(dir_path: Path) -> List[Dict]:
    """Scan a single pod-logs directory and return index entries."""
    entries = []

    if not dir_path.exists():
        print(f"Warning: Directory {dir_path} does not exist")
        return entries

    # Get all log files
    log_files = list(dir_path.glob("*.log"))

    for log_path in log_files:
        # Skip analysis files
        if "analysis" in log_path.name or log_path.name.startswith("pods-list"):
            continue

        filename = log_path.name

        # Extract pod info from filename
        pod_info = extract_pod_info_from_filename(filename)

        # Look for corresponding analysis file
        analysis_path = dir_path / f"{log_path.stem}-analysis.json"
        if not analysis_path.exists():
            # Try alternative naming
            analysis_path = dir_path / f"{filename}-analysis.json"

        analysis_data = load_analysis_file(analysis_path)

        # Get file size
        file_size = log_path.stat().st_size if log_path.exists() else 0

        # Extract patterns and timestamps
        patterns = extract_patterns(analysis_data)
        key_timestamps = extract_key_timestamps(analysis_data, log_path)

        # Create index entry
        entry = {
            "pod_name": pod_info["pod_name"],
            "namespace": pod_info["namespace"],
            "creation_timestamp": pod_info["creation_timestamp"],
            "deletion_timestamp": pod_info["deletion_timestamp"],
            "log_file_path": str(log_path.relative_to(RESEARCH_BASE)),
            "analysis_file_path": str(analysis_path.relative_to(RESEARCH_BASE)) if analysis_path.exists() else None,
            "detected_patterns": patterns,
            "key_timestamps": key_timestamps,
            "log_size_bytes": file_size
        }

        entries.append(entry)

    return entries


def main():
    """Main function to generate the index."""
    all_entries = []

    for rel_dir in POD_LOGS_DIRS:
        dir_path = RESEARCH_BASE / rel_dir
        print(f"Scanning {dir_path}...")
        entries = scan_pod_logs_directory(dir_path)
        print(f"  Found {len(entries)} log files")
        all_entries.extend(entries)

    # Sort by pod_name
    all_entries.sort(key=lambda x: x["pod_name"])

    # Write to JSONL file
    output_path = RESEARCH_BASE / "pod-logs-index.jsonl"

    with open(output_path, "w") as f:
        for entry in all_entries:
            f.write(json.dumps(entry) + "\n")

    print(f"\n✓ Generated {output_path}")
    print(f"  Total entries: {len(all_entries)}")

    # Validate JSONL
    print("\nValidating JSONL syntax...")
    with open(output_path, "r") as f:
        line_num = 0
        for line in f:
            line_num += 1
            try:
                json.loads(line.strip())
            except json.JSONDecodeError as e:
                print(f"  ✗ Line {line_num}: Invalid JSON - {e}")
                return 1
        print(f"  ✓ All {line_num} lines are valid JSON")

    return 0


if __name__ == "__main__":
    exit(main())
