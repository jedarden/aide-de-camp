#!/usr/bin/env python3
"""
Extract metadata from pod log files.

This script scans pod-logs directories, extracts metadata from log files and
associated analysis files, and outputs a structured list of pod log entries.

Usage:
    python scripts/extract_pod_log_metadata.py
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def extract_pod_name_from_filename(filename: str) -> Optional[str]:
    """Extract pod name from log filename.

    Examples:
        pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log -> pbx-web-5ff68464d-mkn8n
        pbx-web-current-nginx.log -> None (not a pod log)
    """
    # Match pattern: pod-<name>-<date>.log or prefix-<name>-<date>-analysis.json
    patterns = [
        r'^pod-([a-z0-9]([-a-z0-9]*[a-z0-9])?)-\d{4}-\d{2}-\d{2}',  # pod-<name>-YYYY-MM-DD
        r'^pod-([a-z0-9]([-a-z0-9]*[a-z0-9])?)-\d{4}-\d{2}-\d{2}-',  # pod-<name>-YYYY-MM-DD-<suffix>
    ]

    for pattern in patterns:
        match = re.match(pattern, filename)
        if match:
            return match.group(1)

    return None


def extract_namespace_from_path(file_path: Path) -> str:
    """Extract namespace from directory structure.

    Examples:
        research/pbx-web-30days/pod-logs/... -> pbx-web
        research/whisper-stt-30days/pod-logs/... -> whisper-stt
    """
    parts = file_path.parts
    for i, part in enumerate(parts):
        if part.endswith('-30days'):
            # Extract namespace from directory name like "pbx-web-30days"
            namespace = part.replace('-30days', '')
            return namespace
    return 'unknown'


def extract_collection_date(filename: str) -> Optional[str]:
    """Extract collection date from filename (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format)."""
    # Try YYYY-MM-DD format first
    match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if match:
        date_str = match.group(1)
        # Validate it's a reasonable date
        if date_str.startswith('20'):  # Filter for years 2000-2099
            return date_str
    return None


def extract_log_type(filename: str) -> Optional[str]:
    """Extract log type from filename."""
    if '-current.' in filename or filename.endswith('-current.log'):
        return 'current'
    elif '-previous.' in filename or filename.endswith('-previous.log'):
        return 'previous'
    elif '-stderr.' in filename or filename.endswith('-stderr.log'):
        return 'stderr'
    return None


def load_pods_metadata(pods_list_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load pod metadata from pods-list.jsonl file.

    Handles both proper JSONL (one JSON per line) and multi-line JSON objects.
    """
    pods_metadata = {}

    if not pods_list_path.exists():
        return pods_metadata

    try:
        with open(pods_list_path, 'r', encoding='utf-8') as f:
            content = f.read()

            # Try parsing as proper JSONL first (one JSON object per line)
            try:
                for line in content.strip().split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        pod_data = json.loads(line)
                        pod_name = pod_data.get('name')
                        if pod_name:
                            pods_metadata[pod_name] = pod_data
                    except json.JSONDecodeError:
                        # If line-by-line fails, try multi-line approach below
                        raise
            except json.JSONDecodeError:
                # Fall back to multi-line JSON parsing (handle brace-delimited objects)
                brace_count = 0
                current_obj = ''

                for char in content:
                    current_obj += char
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # Complete object found
                            try:
                                pod_data = json.loads(current_obj.strip())
                                pod_name = pod_data.get('name')
                                if pod_name:
                                    pods_metadata[pod_name] = pod_data
                            except json.JSONDecodeError:
                                pass
                            current_obj = ''

    except Exception as e:
        print(f"Warning: Failed to read {pods_list_path}: {e}")

    return pods_metadata


def load_analysis_metadata(analysis_path: Path) -> Optional[Dict[str, Any]]:
    """Load analysis metadata from -analysis.json file."""
    if not analysis_path.exists():
        return None

    try:
        with open(analysis_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to read {analysis_path}: {e}")
        return None


def scan_pod_logs_directory(base_dir: Path) -> List[Dict[str, Any]]:
    """Scan pod-logs directory and extract metadata from all log files."""
    results = []

    # Find all pod-logs directories
    pod_logs_dirs = list(base_dir.glob('research/*/pod-logs'))

    if not pod_logs_dirs:
        print(f"No pod-logs directories found in {base_dir}/research/")
        return results

    for pod_logs_dir in pod_logs_dirs:
        print(f"Scanning {pod_logs_dir}...")

        # Load pods metadata from pods-list.jsonl
        pods_list_path = pod_logs_dir / 'pods-list.jsonl'
        pods_metadata = load_pods_metadata(pods_list_path)
        print(f"  Loaded metadata for {len(pods_metadata)} pods from pods-list.jsonl")

        # Find all .log files
        log_files = list(pod_logs_dir.glob('*.log'))
        print(f"  Found {len(log_files)} log files")

        for log_file in log_files:
            metadata = extract_log_file_metadata(log_file, pods_metadata, pod_logs_dir)
            if metadata:
                results.append(metadata)

    return results


def extract_log_file_metadata(
    log_file: Path,
    pods_metadata: Dict[str, Dict[str, Any]],
    pod_logs_dir: Path
) -> Optional[Dict[str, Any]]:
    """Extract metadata from a single log file."""

    # Get relative path from base directory
    rel_path = log_file.relative_to(pod_logs_dir.parent.parent)
    log_file_path = str(rel_path).replace('\\', '/')

    # Get file size
    try:
        log_size_bytes = log_file.stat().st_size
    except Exception:
        log_size_bytes = 0

    # Extract information from filename
    filename = log_file.name
    pod_name = extract_pod_name_from_filename(filename)
    collection_date = extract_collection_date(filename)
    log_type = extract_log_type(filename)
    namespace = extract_namespace_from_path(log_file)

    # Skip files that don't match expected patterns
    if not pod_name:
        # It might be a non-pod log file (like nginx.log)
        # Still include it but with limited metadata
        pod_name = filename.replace('.log', '')

    # Get pod metadata from pods-list.jsonl
    pod_metadata = pods_metadata.get(pod_name, {})

    creation_timestamp = pod_metadata.get('created')
    deletion_timestamp = None  # Would need to be determined from pod phase

    # Handle pod phase - if "Running", no deletion timestamp
    pod_phase = pod_metadata.get('phase', 'Unknown')
    if pod_phase == 'Running':
        deletion_timestamp = None
    else:
        # For terminated pods, we'd need to get deletion timestamp
        # For now, set it to None if not available
        deletion_timestamp = pod_metadata.get('deletedAt')

    # Load analysis metadata if available
    analysis_file = log_file.parent / f"{log_file.stem}-analysis.json"
    analysis_metadata = load_analysis_metadata(analysis_file)

    log_line_count = None
    if analysis_metadata:
        log_line_count = analysis_metadata.get('total_lines')

    return {
        'pod_name': pod_name,
        'namespace': namespace,
        'creation_timestamp': creation_timestamp,
        'deletion_timestamp': deletion_timestamp,
        'log_file_path': log_file_path,
        'log_size_bytes': log_size_bytes,
        'log_line_count': log_line_count,
        'collection_date': collection_date,
        'log_type': log_type,
        'pod_phase': pod_phase,
        'restart_count': pod_metadata.get('restarts', 0),
        'container_image': pod_metadata.get('image'),
        'node_name': pod_metadata.get('nodeName'),
        'analysis_file_exists': analysis_file.exists(),
    }


def main():
    """Main entry point."""
    # Determine base directory (script location / aide-de-camp)
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent

    print(f"Scanning pod logs in {base_dir}")
    print("=" * 60)

    # Scan all pod-logs directories
    results = scan_pod_logs_directory(base_dir)

    print(f"\nTotal log files processed: {len(results)}")

    # Output results
    if results:
        output_file = base_dir / 'data' / 'pod-log-metadata.json'
        output_file.parent.mkdir(exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)

        print(f"Results saved to {output_file}")

        # Print summary statistics
        print("\nSummary:")
        print(f"  Total entries: {len(results)}")

        namespaces = set(r['namespace'] for r in results)
        print(f"  Namespaces: {', '.join(sorted(namespaces))}")

        total_size = sum(r['log_size_bytes'] for r in results)
        print(f"  Total log size: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")

        with_analysis = sum(1 for r in results if r['analysis_file_exists'])
        print(f"  Files with analysis: {with_analysis}/{len(results)}")

        # Print sample entry
        if results:
            print("\nSample entry:")
            print(json.dumps(results[0], indent=2))
    else:
        print("No results found.")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
