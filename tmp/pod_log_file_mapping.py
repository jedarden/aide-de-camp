#!/usr/bin/env python3
"""
Enumerate pod-logs directory and create file mapping.

Scans research/ subdirectories for pod-logs containing .log files,
identifies corresponding .analysis.json files, extracts metadata,
and outputs a comprehensive mapping structure.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional
import re


def extract_pod_name_from_path(file_path: Path) -> str:
    """Extract pod name from log file path."""
    # Try to get from filename first
    stem = file_path.stem

    # Common patterns: pod-name.log, pod-name-container.log, pod-name-namespace.log
    # Remove common suffixes
    for suffix in ['-logs', '-log', '_logs', '_log', '-container', '-main']:
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]

    return stem


def extract_namespace_from_path(file_path: Path) -> Optional[str]:
    """Extract namespace from file path or name."""
    # Check if namespace is in the path (common structure: namespace/pod-name.log)
    parts = file_path.parts

    # Look for common namespace indicators in path
    for i, part in enumerate(parts):
        if 'pod-logs' in part:
            # The directory after pod-logs might be namespace or cluster
            if i + 1 < len(parts):
                return parts[i + 1]

    # Try to extract from filename pattern: pod-name-namespace.log
    stem = file_path.stem
    match = re.search(r'-([a-z]+-[a-z]+)$', stem)
    if match:
        return match.group(1)

    return None


def find_analysis_file(log_file: Path) -> Optional[Path]:
    """Find corresponding .analysis.json file for a log file."""
    # Common patterns for analysis file naming
    possible_names = [
        log_file.with_suffix('.analysis.json'),  # log.log -> log.analysis.json
        log_file.with_name(f'{log_file.stem}.analysis.json'),  # Same as above
    ]

    for analysis_file in possible_names:
        if analysis_file.exists():
            return analysis_file

    return None


def scan_pod_logs_directory(pod_logs_dir: Path) -> List[Dict]:
    """Scan a pod-logs directory and return mapping entries."""
    entries = []

    if not pod_logs_dir.exists():
        print(f"Warning: Directory {pod_logs_dir} does not exist")
        return entries

    # Recursively find all .log files
    log_files = list(pod_logs_dir.rglob('*.log'))

    for log_file in log_files:
        # Get relative path from repo root
        repo_root = Path.cwd()
        try:
            rel_path = log_file.relative_to(repo_root)
        except ValueError:
            # File not under repo root (shouldn't happen)
            continue

        # Find corresponding analysis file
        analysis_file = find_analysis_file(log_file)
        analysis_rel_path = None
        if analysis_file:
            try:
                analysis_rel_path = analysis_file.relative_to(repo_root)
            except ValueError:
                pass

        # Extract metadata
        pod_name = extract_pod_name_from_path(log_file)
        namespace = extract_namespace_from_path(log_file)

        entry = {
            'log_file_path': str(rel_path),
            'analysis_file_path': str(analysis_rel_path) if analysis_rel_path else None,
            'pod_name': pod_name,
            'namespace': namespace,
            'has_analysis': analysis_file is not None,
            'log_file_size': log_file.stat().st_size if log_file.exists() else 0
        }

        entries.append(entry)

    return entries


def main():
    """Main function to scan all pod-logs directories."""
    repo_root = Path.cwd()

    # Define pod-logs directories to scan
    pod_logs_dirs = [
        repo_root / 'research' / 'pbx-web-30days' / 'pod-logs',
        repo_root / 'research' / 'whisper-stt-30days' / 'pod-logs',
    ]

    all_entries = []

    for pod_logs_dir in pod_logs_dirs:
        print(f"Scanning {pod_logs_dir}...")
        entries = scan_pod_logs_directory(pod_logs_dir)
        print(f"  Found {len(entries)} log files")
        all_entries.extend(entries)

    # Create mapping structure
    mapping = {
        'scan_timestamp': '2026-08-06T20:47:00Z',
        'total_log_files': len(all_entries),
        'files_with_analysis': sum(1 for e in all_entries if e['has_analysis']),
        'files_without_analysis': sum(1 for e in all_entries if not e['has_analysis']),
        'entries': all_entries
    }

    # Output to temporary file for next step
    output_file = repo_root / 'tmp' / 'pod_log_mapping.json'
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump(mapping, f, indent=2)

    print(f"\nMapping saved to {output_file}")
    print(f"Summary:")
    print(f"  Total log files: {mapping['total_log_files']}")
    print(f"  With analysis: {mapping['files_with_analysis']}")
    print(f"  Without analysis: {mapping['files_without_analysis']}")


if __name__ == '__main__':
    main()
