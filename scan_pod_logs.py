#!/usr/bin/env python3
"""
Scan pod-logs directory and create file mapping.
Maps .log files to their corresponding .analysis.json files with metadata.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional

def extract_pod_name(log_path: Path) -> str:
    """Extract pod name from log filename."""
    # Remove .log extension
    name = log_path.stem
    # Remove -current, -recent suffixes if present
    for suffix in ['-current', '-recent']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name

def extract_namespace(log_path: Path) -> Optional[str]:
    """
    Extract namespace from path structure.
    If path contains subdirectories, first subdir might be namespace.
    """
    parts = log_path.relative_to('logs').parts
    if len(parts) > 1:
        # First directory component might be namespace
        return parts[0]
    return None

def scan_logs_directory(base_dir: Path = Path('logs')) -> List[Dict]:
    """
    Scan logs directory for .log files and create mapping.

    Returns:
        List of dicts with keys:
        - log_file_path: str (relative to repo root)
        - analysis_file_path: Optional[str] (relative to repo root, or null)
        - pod_name: str
        - namespace: Optional[str]
    """
    mappings = []

    # Find all .log files
    log_files = sorted(base_dir.rglob('*.log'))

    for log_file in log_files:
        # Calculate relative path from repo root
        log_rel_path = str(log_file)

        # Check for corresponding .analysis.json file
        analysis_file = log_file.with_suffix('.log.analysis.json')
        analysis_rel_path = str(analysis_file) if analysis_file.exists() else None

        # Extract metadata
        pod_name = extract_pod_name(log_file)
        namespace = extract_namespace(log_file)

        mapping = {
            'log_file_path': log_rel_path,
            'analysis_file_path': analysis_rel_path,
            'pod_name': pod_name,
            'namespace': namespace
        }
        mappings.append(mapping)

    return mappings

def main():
    """Main entry point."""
    repo_root = Path.cwd()
    print(f"Scanning from: {repo_root}")

    mappings = scan_logs_directory()

    print(f"\nFound {len(mappings)} log files:")

    # Group by namespace
    by_namespace: Dict[str, List[Dict]] = {}
    for mapping in mappings:
        ns = mapping['namespace'] or '<root>'
        if ns not in by_namespace:
            by_namespace[ns] = []
        by_namespace[ns].append(mapping)

    for ns, items in sorted(by_namespace.items()):
        print(f"\n  Namespace: {ns}")
        for item in items:
            has_analysis = '✓' if item['analysis_file_path'] else '✗'
            print(f"    {has_analysis} {item['pod_name']}")
            print(f"       Log: {item['log_file_path']}")
            if item['analysis_file_path']:
                print(f"       Analysis: {item['analysis_file_path']}")

    # Write to temporary file
    output_file = '/tmp/pod_logs_mapping.json'
    with open(output_file, 'w') as f:
        json.dump({
            'total_count': len(mappings),
            'with_analysis': sum(1 for m in mappings if m['analysis_file_path']),
            'without_analysis': sum(1 for m in mappings if not m['analysis_file_path']),
            'mappings': mappings
        }, f, indent=2)

    print(f"\n✓ Mapping written to: {output_file}")
    print(f"  Total files: {len(mappings)}")
    print(f"  With analysis: {sum(1 for m in mappings if m['analysis_file_path'])}")
    print(f"  Without analysis: {sum(1 for m in mappings if not m['analysis_file_path'])}")

if __name__ == '__main__':
    main()
