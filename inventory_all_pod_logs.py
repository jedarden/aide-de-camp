#!/usr/bin/env python3
"""
Comprehensive pod logs inventory script.
Scans all pod-logs directories across the project and creates a complete inventory.
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


def extract_pod_name_from_filename(filename: str) -> str:
    """Extract pod name from log filename."""
    # Remove .log extension
    name = filename.replace('.log', '')

    # Remove common suffixes
    for suffix in ['-current', '-previous', '-stderr', '-nginx', '-site-generator',
                   '-recent', '-pod', '-openai', '-stt']:
        name = name.removesuffix(suffix)

    # Remove date suffix (format: -YYYY-MM-DD)
    name = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', name)

    # Remove 'pod-' prefix if present
    if name.startswith('pod-'):
        name = name[4:]

    return name


def determine_namespace(file_path: Path) -> str:
    """Determine namespace from file path."""
    path_str = str(file_path)

    # Check path hierarchy
    if 'pbx-web-30days' in path_str:
        return 'pbx-web'
    elif 'whisper-stt-30days' in path_str:
        return 'whisper-stt'
    elif 'pbx-web-30day' in path_str:
        return 'pbx-web'
    elif 'pbx-web-apexalgo-iad' in path_str:
        return 'pbx-web'
    elif 'pbx-web-ardenone-cluster' in path_str:
        return 'pbx-web'

    # Try to infer from filename
    filename = file_path.name.lower()
    if 'pbx-web' in filename or 'pbx-' in filename:
        return 'pbx-web'
    elif 'whisper' in filename:
        return 'whisper-stt'

    return 'unknown'


def find_analysis_file(log_path: Path) -> Optional[Path]:
    """Find corresponding analysis.json file for a log file."""
    # Try the common pattern: replace .log with -analysis.json
    analysis_path = Path(str(log_path).replace('.log', '-analysis.json'))
    if analysis_path.exists():
        return analysis_path

    # Try exact name match with .log.analysis.json extension
    analysis_path = log_path.with_suffix('.log.analysis.json')
    if analysis_path.exists():
        return analysis_path

    # Try with just .analysis.json (no .log in middle)
    analysis_path = log_path.with_suffix('.analysis.json')
    if analysis_path.exists():
        return analysis_path

    return None


def scan_directory_for_logs(directory: Path, repo_root: Path) -> List[Dict]:
    """Scan a directory for pod log files."""
    mappings = []

    if not directory.exists():
        print(f"  Warning: Directory {directory} does not exist")
        return mappings

    # Find all .log files recursively
    log_files = sorted(directory.rglob('*.log'))

    for log_file in log_files:
        # Get relative path from repo root
        try:
            log_file_relative = log_file.relative_to(repo_root)
        except ValueError:
            # If file is not under repo_root, use absolute path
            log_file_relative = log_file

        # Find corresponding analysis file
        analysis_file = find_analysis_file(log_file)
        analysis_file_relative = None
        if analysis_file:
            try:
                analysis_file_relative = analysis_file.relative_to(repo_root)
            except ValueError:
                analysis_file_relative = analysis_file

        # Extract metadata
        filename = log_file.name
        pod_name = extract_pod_name_from_filename(filename)
        namespace = determine_namespace(log_file)

        # Get file stats
        try:
            file_size = log_file.stat().st_size
            # Count lines
            with open(log_file, 'r', errors='ignore') as f:
                line_count = sum(1 for _ in f)
        except Exception as e:
            file_size = 0
            line_count = 0

        mapping = {
            'pod_name': pod_name,
            'namespace': namespace,
            'log_file_path': str(log_file_relative),
            'log_file_size_bytes': file_size,
            'log_line_count': line_count,
            'has_analysis': analysis_file is not None,
            'analysis_file_path': str(analysis_file_relative) if analysis_file_relative else None,
            'collection_source': str(log_file.relative_to(directory).parts[0] if log_file.relative_to(directory).parts else 'root')
        }

        mappings.append(mapping)

    return mappings


def main():
    """Main function to scan all pod-logs directories."""
    repo_root = Path('/home/coding/aide-de-camp')

    # Define all pod-logs directories to scan
    pod_logs_dirs = [
        repo_root / 'research' / 'pbx-web-30days' / 'pod-logs',
        repo_root / 'research' / 'whisper-stt-30days' / 'pod-logs',
        repo_root / 'logs',  # Also scan the main logs directory
    ]

    print("Comprehensive Pod Logs Inventory")
    print("=" * 50)
    print(f"Scanning from: {repo_root}\n")

    all_mappings = []

    for pod_dir in pod_logs_dirs:
        print(f"Scanning: {pod_dir.relative_to(repo_root)}")
        mappings = scan_directory_for_logs(pod_dir, repo_root)
        all_mappings.extend(mappings)
        print(f"  Found {len(mappings)} log files\n")

    # Sort by namespace and then by log_file_path
    all_mappings.sort(key=lambda x: (x['namespace'], x['log_file_path']))

    # Create summary statistics
    total_files = len(all_mappings)
    files_with_analysis = sum(1 for m in all_mappings if m['has_analysis'])
    files_without_analysis = total_files - files_with_analysis

    # Group by namespace
    by_namespace = {}
    for mapping in all_mappings:
        ns = mapping['namespace']
        if ns not in by_namespace:
            by_namespace[ns] = []
        by_namespace[ns].append(mapping)

    # Output to temporary JSON file
    output_file = repo_root / 'tmp' / 'pod-logs-inventory.json'
    output_file.parent.mkdir(exist_ok=True)

    inventory_data = {
        'inventory_date': datetime.now().isoformat(),
        'total_log_files': total_files,
        'files_with_analysis': files_with_analysis,
        'files_without_analysis': files_without_analysis,
        'namespaces': {
            ns: {
                'count': len(items),
                'with_analysis': sum(1 for m in items if m['has_analysis']),
                'total_size_bytes': sum(m['log_file_size_bytes'] for m in items),
                'total_lines': sum(m['log_line_count'] for m in items)
            }
            for ns, items in sorted(by_namespace.items())
        },
        'inventory': all_mappings
    }

    with open(output_file, 'w') as f:
        json.dump(inventory_data, f, indent=2)

    # Print summary
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Total log files: {total_files}")
    print(f"Files with analysis: {files_with_analysis}")
    print(f"Files without analysis: {files_without_analysis}")
    print(f"\nInventory written to: {output_file}")

    print("\nBy Namespace:")
    for ns, stats in inventory_data['namespaces'].items():
        print(f"  {ns}:")
        print(f"    Files: {stats['count']}")
        print(f"    With analysis: {stats['with_analysis']}")
        print(f"    Total size: {stats['total_size_bytes']:,} bytes ({stats['total_size_bytes'] / 1024 / 1024:.2f} MB)")
        print(f"    Total lines: {stats['total_lines']:,}")

    # Print sample of inventory (first 5)
    print("\nSample Inventory Entries (first 5):")
    for mapping in all_mappings[:5]:
        print(f"\n  Pod: {mapping['pod_name']}")
        print(f"  Namespace: {mapping['namespace']}")
        print(f"  Log: {mapping['log_file_path']}")
        print(f"  Size: {mapping['log_file_size_bytes']:,} bytes, Lines: {mapping['log_line_count']:,}")
        print(f"  Analysis: {'Yes' if mapping['has_analysis'] else 'No'}")

    return all_mappings


if __name__ == '__main__':
    main()