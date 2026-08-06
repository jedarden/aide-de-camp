#!/usr/bin/env python3
"""
Pod Logs Scanner Script

Scans pod-logs/ directories and extracts all required metadata according to the
schema defined in pod-logs-schema.md.

Usage:
    python scripts/scan-pod-logs.py <pod-logs-dir> [--validate] [--output OUTPUT]

Examples:
    python scripts/scan-pod-logs.py research/pbx-web-30days/pod-logs
    python scripts/scan-pod-logs.py research/pbx-web-30days/pod-logs --validate
    python scripts/scan-pod-logs.py research/pbx-web-30days/pod-logs --output pod-logs-index.jsonl
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Pattern categories according to schema
PATTERN_CATEGORIES = ["startup", "oom_kill", "error", "performance"]


def parse_log_filename(filename: str) -> Dict[str, Optional[str]]:
    """
    Extract pod name, date, and log type from log filename.

    Examples:
        pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log
        pod-pbx-web-5ff68464d-mkn8n-2026-08-06-current.log
        pod-pbx-web-5ff68464d-mkn8n-2026-08-06-previous.log
        pbx-web-current-nginx.log
    """
    result = {
        "pod_name": None,
        "collection_date": None,
        "log_type": None,
    }

    # Pattern: {prefix}-{pod-name}-{date}[-{suffix}].log
    # Extract date first (YYYY-MM-DD format)
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if date_match:
        result["collection_date"] = date_match.group(1)

    base_name = filename.replace('.log', '')

    # Try to identify pod name pattern
    if base_name.startswith('pod-'):
        # Pattern: pod-{pod-name}-{date}[-{type}]
        remaining = base_name[4:]  # Remove 'pod-' prefix

        # Extract log type first
        for log_type in ['current', 'previous', 'stderr']:
            if remaining.endswith(f'-{log_type}'):
                result["log_type"] = log_type
                remaining = remaining[:-len(log_type)-1]  # Remove -{type}
                break

        # Now extract date and pod name
        date_match = re.search(r'-(\d{4}-\d{2}-\d{2})$', remaining)
        if date_match:
            result["collection_date"] = date_match.group(1)
            pod_part = remaining[:date_match.start()]
            result["pod_name"] = pod_part
    else:
        # Pattern: {prefix}-{date}-{type}.log or {prefix}-{pod}-{date}.log
        # For pbx-web-current-nginx.log, this means current type, nginx container
        # For pbx-web-lab-rebuild-relay-79d6d858bb-lpqdb.log, this is the full pod name
        parts = base_name.split('-')

        if 'current' in parts:
            current_idx = parts.index('current')
            # Before 'current' is app name, after is container
            result["log_type"] = "current"
            if current_idx < len(parts) - 1:
                result["pod_name"] = '-'.join(parts[current_idx+1:])
        elif 'previous' in parts:
            prev_idx = parts.index('previous')
            result["log_type"] = "previous"
            if prev_idx < len(parts) - 1:
                result["pod_name"] = '-'.join(parts[prev_idx+1:])
        elif 'stderr' in parts:
            stderr_idx = parts.index('stderr')
            result["log_type"] = "stderr"
            if stderr_idx < len(parts) - 1:
                result["pod_name"] = '-'.join(parts[stderr_idx+1:])
        else:
            # No type suffix, entire filename except date might be pod name
            # Try to find and remove date
            date_match = re.search(r'-(\d{4}-\d{2}-\d{2})$', base_name)
            if date_match:
                result["pod_name"] = base_name[:date_match.start()]
            else:
                result["pod_name"] = base_name

    return result


def read_analysis_file(analysis_path: Path) -> Dict[str, Any]:
    """
    Read analysis JSON file and extract pattern data.

    Returns dict with patterns, total_lines, and analysis_date.
    Returns default empty dict if file not found or invalid.
    """
    if not analysis_path.exists():
        return {
            "patterns": {cat: {"count": 0, "timestamps": [], "samples": []}
                        for cat in PATTERN_CATEGORIES},
            "total_lines": None,
            "analysis_date": None,
        }

    try:
        with open(analysis_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Extract key fields
        return {
            "patterns": data.get("patterns", {}),
            "total_lines": data.get("total_lines"),
            "analysis_date": data.get("analysis_date"),
        }
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to read analysis file {analysis_path}: {e}",
              file=sys.stderr)
        return {
            "patterns": {cat: {"count": 0, "timestamps": [], "samples": []}
                        for cat in PATTERN_CATEGORIES},
            "total_lines": None,
            "analysis_date": None,
        }


def read_pods_metadata(pods_list_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Read pods-list.jsonl and create index by pod name.

    Handles both single-line JSONL and multi-line JSON objects.

    Returns dict mapping pod_name -> metadata dict.
    """
    pods_index = {}

    if not pods_list_path.exists():
        print(f"Warning: pods-list.jsonl not found at {pods_list_path}", file=sys.stderr)
        return pods_index

    try:
        with open(pods_list_path, 'r', encoding='utf-8') as f:
            content = f.read()

            # Try parsing as multi-line JSON objects first
            # Pattern: Find all {...} blocks
            json_objects = []
            brace_depth = 0
            current_obj = []

            for char in content:
                if char == '{':
                    if brace_depth == 0:
                        current_obj = []
                    brace_depth += 1
                    current_obj.append(char)
                elif char == '}':
                    brace_depth -= 1
                    current_obj.append(char)
                    if brace_depth == 0 and current_obj:
                        # Complete object
                        obj_str = ''.join(current_obj).strip()
                        if obj_str:
                            json_objects.append(obj_str)
                        current_obj = []
                elif brace_depth > 0:
                    current_obj.append(char)

            # Parse each JSON object
            for obj_str in json_objects:
                try:
                    pod_data = json.loads(obj_str)
                    pod_name = pod_data.get("name")
                    if pod_name:
                        pods_index[pod_name] = pod_data
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse JSON object: {e}", file=sys.stderr)
                    continue

        print(f"Successfully read {len(pods_index)} pods from pods-list.jsonl", file=sys.stderr)
    except IOError as e:
        print(f"Warning: Failed to read pods-list.jsonl: {e}", file=sys.stderr)

    return pods_index


def extract_namespace_from_path(pod_logs_dir: Path) -> str:
    """
    Extract namespace from directory path.

    Expected path: research/<service>-30days/pod-logs/
    Returns the service name as namespace.
    """
    parts = pod_logs_dir.parts
    # Look for parent directory name (e.g., pbx-web-30days)
    if len(parts) >= 2:
        parent_dir = parts[-2]  # pod-logs parent
        # Extract service name (remove -30days suffix)
        if parent_dir.endswith('-30days'):
            namespace = parent_dir[:-7]  # Remove '-30days' suffix (7 chars)
        else:
            namespace = parent_dir
        return namespace
    return "unknown"


def get_temporal_boundaries(analysis_data: Dict[str, Any],
                           log_file_path: Path) -> Dict[str, Optional[str]]:
    """
    Extract temporal boundaries from analysis file or log file.

    Returns dict with first_log_entry, last_log_entry.
    """
    # Try to read from analysis summary
    first_entry = None
    last_entry = None

    # Check if analysis file has temporal data
    if "summary" in analysis_data and analysis_data["summary"]:
        for summary_item in analysis_data["summary"]:
            first_occurrence = summary_item.get("first_occurrence")
            last_occurrence = summary_item.get("last_occurrence")

            if first_occurrence and first_occurrence != "unknown":
                # Convert Unix timestamp to ISO 8601 if needed
                if first_occurrence.isdigit():
                    first_entry = datetime.fromtimestamp(int(first_occurrence),
                                                        tz=datetime.now().astimezone().tzinfo)
                    first_entry = first_entry.strftime("%Y-%m-%dT%H:%M:%SZ")

            if last_occurrence and last_occurrence != "unknown":
                if last_occurrence.isdigit():
                    last_entry = datetime.fromtimestamp(int(last_occurrence),
                                                      tz=datetime.now().astimezone().tzinfo)
                    last_entry = last_entry.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "first_log_entry": first_entry,
        "last_log_entry": last_entry,
    }


def build_log_entry(log_file_path: Path, pod_logs_dir: Path,
                   pods_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a complete log entry according to the schema.

    Args:
        log_file_path: Path to the .log file
        pod_logs_dir: Base pod-logs directory
        pods_index: Index of pod metadata from pods-list.jsonl

    Returns:
        Dict matching the pod-logs-schema structure
    """
    filename = log_file_path.name
    log_stats = parse_log_filename(filename)

    # Get file size
    try:
        log_size_bytes = log_file_path.stat().st_size
    except OSError:
        log_size_bytes = 0

    # Find corresponding analysis file
    analysis_filename = filename.replace('.log', '-analysis.json')
    analysis_path = pod_logs_dir / analysis_filename

    # Read analysis data
    analysis_data = read_analysis_file(analysis_path)

    # Get temporal boundaries
    temporal = get_temporal_boundaries(analysis_data, log_file_path)

    # Determine collection date from filename or analysis
    collection_date = log_stats.get("collection_date")
    if not collection_date and analysis_data.get("analysis_date"):
        # Extract date from analysis_date
        analysis_date_str = analysis_data["analysis_date"]
        if analysis_date_str:
            try:
                # Parse ISO datetime and extract date
                dt = datetime.fromisoformat(analysis_date_str.replace('Z', '+00:00'))
                collection_date = dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                pass

    # Get collection date as fallback
    if not collection_date:
        collection_date = "2026-08-06"  # Default from schema examples

    # Get pod metadata from pods-list.jsonl
    pod_name = log_stats.get("pod_name")
    pod_metadata = pods_index.get(pod_name, {}) if pod_name else {}

    # Extract namespace from path
    namespace = extract_namespace_from_path(pod_logs_dir)

    # Normalize analysis_date (add Z suffix if missing)
    analysis_date = analysis_data.get("analysis_date")
    if analysis_date and not analysis_date.endswith('Z'):
        # Try to parse and reformat with Z
        try:
            dt = datetime.fromisoformat(analysis_date.replace('Z', '+00:00'))
            analysis_date = dt.strftime("%Y-%m-%dT%H:%M:%S")
            if '.' in analysis_date:
                # Preserve microseconds
                analysis_date = dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
            else:
                analysis_date = analysis_date + "Z"
        except (ValueError, AttributeError):
            analysis_date = None

    # Build pattern_detection structure
    pattern_detection = {}
    patterns = analysis_data.get("patterns", {})

    for category in PATTERN_CATEGORIES:
        cat_data = patterns.get(category, {})
        pattern_detection[category] = {
            "count": cat_data.get("count", 0),
            "timestamps": cat_data.get("timestamps", []),
            "samples": cat_data.get("samples", []),
        }

    # Build log_file_path relative to research root
    # Convert absolute path to relative if possible
    try:
        relative_log_path = str(log_file_path.relative_to(Path.cwd()))
    except ValueError:
        # If not relative to cwd, use full path
        relative_log_path = str(log_file_path)

    # Build analysis_file_path (or null if not exists)
    if analysis_path.exists():
        try:
            analysis_file_path = str(analysis_path.relative_to(Path.cwd()))
        except ValueError:
            analysis_file_path = str(analysis_path)
    else:
        analysis_file_path = None

    # Construct the complete entry
    entry = {
        "pod_identification": {
            "pod_name": pod_name or "unknown",
            "namespace": namespace,
            "pod_phase": pod_metadata.get("phase"),
            "restart_count": pod_metadata.get("restarts", 0),
            "creation_timestamp": pod_metadata.get("created"),
            "deletion_timestamp": pod_metadata.get("deletionTimestamp"),  # May be None
            "container_image": pod_metadata.get("image"),
            "node_name": pod_metadata.get("nodeName"),
        },
        "log_file_metadata": {
            "log_file_path": relative_log_path,
            "log_size_bytes": log_size_bytes,
            "log_line_count": analysis_data.get("total_lines"),
            "collection_date": collection_date,
            "log_type": log_stats.get("log_type"),
        },
        "analysis_metadata": {
            "analysis_file_path": analysis_file_path,
            "analysis_date": analysis_date,
        },
        "pattern_detection": pattern_detection,
        "temporal_boundaries": {
            "first_log_entry": temporal.get("first_log_entry"),
            "last_log_entry": temporal.get("last_log_entry"),
            "analysis_date": analysis_date,
            "collection_date": collection_date,
        },
    }

    return entry


def validate_entry(entry: Dict[str, Any]) -> List[str]:
    """
    Validate a log entry against schema rules.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    # Validate pod_identification
    pod_id = entry.get("pod_identification", {})
    if not pod_id.get("pod_name"):
        errors.append("Missing pod_name")

    # Validate log_file_metadata
    log_meta = entry.get("log_file_metadata", {})
    if log_meta.get("log_size_bytes", 0) < 0:
        errors.append(f"Invalid log_size_bytes: {log_meta.get('log_size_bytes')}")

    if not log_meta.get("collection_date"):
        errors.append("Missing collection_date")
    elif not re.match(r'^\d{4}-\d{2}-\d{2}$', log_meta.get("collection_date", "")):
        errors.append(f"Invalid collection_date format: {log_meta.get('collection_date')}")

    # Validate pattern_detection array consistency
    pattern_det = entry.get("pattern_detection", {})
    for category in PATTERN_CATEGORIES:
        cat_data = pattern_det.get(category, {})
        count = cat_data.get("count", 0)
        timestamps = cat_data.get("timestamps", [])
        samples = cat_data.get("samples", [])

        if count == 0:
            if timestamps or samples:
                errors.append(f"{category}: count=0 but non-empty arrays")
        else:
            if len(timestamps) != count:
                errors.append(f"{category}: count={count} but timestamps.length={len(timestamps)}")
            if len(samples) != count:
                errors.append(f"{category}: count={count} but samples.length={len(samples)}")

    # Validate temporal boundaries
    temporal = entry.get("temporal_boundaries", {})
    first = temporal.get("first_log_entry")
    last = temporal.get("last_log_entry")

    if first and last:
        try:
            first_dt = datetime.fromisoformat(first.replace('Z', '+00:00'))
            last_dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
            if first_dt > last_dt:
                errors.append(f"Temporal ordering: first_log_entry ({first}) > last_log_entry ({last})")
        except ValueError as e:
            errors.append(f"Invalid timestamp format: {e}")

    return errors


def scan_pod_logs(pod_logs_dir: str, validate: bool = False) -> List[Dict[str, Any]]:
    """
    Scan pod-logs directory and extract all metadata.

    Args:
        pod_logs_dir: Path to pod-logs directory
        validate: If True, validate each entry and report errors

    Returns:
        List of log entry dicts
    """
    pod_logs_path = Path(pod_logs_dir)

    if not pod_logs_path.exists():
        print(f"Error: Directory not found: {pod_logs_dir}", file=sys.stderr)
        return []

    # Read pods metadata
    pods_list_path = pod_logs_path / "pods-list.jsonl"
    pods_index = read_pods_metadata(pods_list_path)

    print(f"Scanning {pod_logs_dir}...", file=sys.stderr)
    print(f"Found {len(pods_index)} pods in pods-list.jsonl", file=sys.stderr)

    # Find all .log files
    log_files = sorted(pod_logs_path.glob("*.log"))

    print(f"Found {len(log_files)} log files", file=sys.stderr)

    entries = []
    validation_errors = []

    for log_file in log_files:
        entry = build_log_entry(log_file, pod_logs_path, pods_index)
        entries.append(entry)

        if validate:
            errors = validate_entry(entry)
            if errors:
                validation_errors.append({
                    "log_file": entry["log_file_metadata"]["log_file_path"],
                    "errors": errors,
                })

    if validate and validation_errors:
        print(f"\nValidation errors found in {len(validation_errors)} entries:",
              file=sys.stderr)
        for error_item in validation_errors[:10]:  # Show first 10
            print(f"  {error_item['log_file']}:", file=sys.stderr)
            for err in error_item['errors']:
                print(f"    - {err}", file=sys.stderr)
        if len(validation_errors) > 10:
            print(f"  ... and {len(validation_errors) - 10} more", file=sys.stderr)

    print(f"Successfully processed {len(entries)} log entries", file=sys.stderr)

    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Scan pod-logs directory and extract metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "pod_logs_dir",
        help="Path to pod-logs directory"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate entries against schema rules"
    )
    parser.add_argument(
        "--output", "-o",
        default="-",
        help="Output file path (default: stdout)"
    )

    args = parser.parse_args()

    # Scan and extract
    entries = scan_pod_logs(args.pod_logs_dir, args.validate)

    if not entries:
        print("No entries found or error occurred", file=sys.stderr)
        sys.exit(1)

    # Write output
    output_path = args.output
    if output_path == "-":
        # Write to stdout
        for entry in entries:
            print(json.dumps(entry, ensure_ascii=False))
    else:
        # Write to file
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        print(f"Output written to {output_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
