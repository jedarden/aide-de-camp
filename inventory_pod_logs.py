#!/usr/bin/env python3
"""
Discover and inventory all pod log files in the aide-de-camp project.
Scans multiple directories and creates a comprehensive inventory with:
- pod_name (extracted from filename)
- namespace (inferred from directory structure)
- log_file_path (absolute path)
- Additional metadata
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

def extract_pod_name_from_filename(filename: str) -> str:
    """Extract pod name from log filename."""
    # Remove .log extension
    pod_name = filename.replace('.log', '')

    # Handle different naming patterns
    # Pattern 1: pod-{name}-{date}.log -> {name}
    if pod_name.startswith('pod-'):
        parts = pod_name.split('-')
        # Remove 'pod' prefix and date suffix if present
        if len(parts) > 1:
            # Try to remove date-like suffix (YYYY-MM-DD)
            if re.search(r'\d{4}-\d{2}-\d{2}', pod_name):
                pod_name = re.sub(r'-\d{4}-\d{2}-\d{2}', '', pod_name)
            pod_name = pod_name.replace('pod-', '', 1)

    # Pattern 2: {component}-{pod-hash}-{container}.log
    # Keep the full name as it identifies the specific pod

    return pod_name

def infer_namespace_from_path(filepath: str) -> str:
    """Infer namespace from directory structure."""
    # Default namespace for most pods in this project
    if 'pbx-web' in filepath.lower():
        return 'pbx-web'
    elif 'whisper-stt' in filepath.lower():
        return 'pbx-web'  # whisper-stt pods are also in pbx-web namespace
    elif 'apexalgo' in filepath.lower():
        return 'apexalgo-iad'
    elif 'ardenone' in filepath.lower():
        return 'ardenone-cluster'

    return 'unknown'

def get_log_file_metadata(filepath: str) -> Dict[str, Any]:
    """Extract metadata from a log file."""
    try:
        stat = os.stat(filepath)
        return {
            'size_bytes': stat.st_size,
            'modified_time': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'created_time': datetime.fromtimestamp(stat.st_ctime).isoformat(),
        }
    except Exception as e:
        return {
            'size_bytes': 0,
            'error': str(e)
        }

def scan_directory_for_logs(base_dir: str, pattern: str = '*.log') -> List[str]:
    """Scan directory recursively for log files."""
    log_files = []
    base_path = Path(base_dir)

    if not base_path.exists():
        return log_files

    for log_file in base_path.rglob(pattern):
        # Skip .venv, .git, node_modules
        if any(skip in str(log_file) for skip in ['.venv', '.git', 'node_modules']):
            continue
        log_files.append(str(log_file))

    return sorted(log_files)

def create_inventory_entry(filepath: str, base_dir: str = '/home/coding/aide-de-camp') -> Dict[str, Any]:
    """Create inventory entry for a log file."""
    filename = os.path.basename(filepath)
    relative_path = os.path.relpath(filepath, base_dir)

    # Extract pod name
    pod_name = extract_pod_name_from_filename(filename)

    # Infer namespace
    namespace = infer_namespace_from_path(filepath)

    # Get file metadata
    metadata = get_log_file_metadata(filepath)

    return {
        'pod_name': pod_name,
        'namespace': namespace,
        'log_file_path': filepath,
        'relative_path': relative_path,
        'filename': filename,
        'metadata': metadata
    }

def main():
    """Main function to scan and inventory all pod logs."""
    base_dir = '/home/coding/aide-de-camp'

    # Define directories to scan
    directories_to_scan = [
        f'{base_dir}/research/pbx-web-30days/pod-logs',
        f'{base_dir}/research/whisper-stt-30days/pod-logs',
        f'{base_dir}/logs',
        f'{base_dir}/data',
        f'{base_dir}/research-data',
    ]

    print("Scanning for pod log files...")
    all_log_files = []

    for directory in directories_to_scan:
        print(f"  Scanning {directory}...")
        log_files = scan_directory_for_logs(directory)
        all_log_files.extend(log_files)
        print(f"    Found {len(log_files)} log files")

    # Remove duplicates and sort
    all_log_files = sorted(set(all_log_files))
    print(f"\nTotal unique log files found: {len(all_log_files)}")

    # Create inventory
    inventory = []
    for log_file in all_log_files:
        entry = create_inventory_entry(log_file, base_dir)
        inventory.append(entry)

    # Output JSON
    output_file = '/tmp/pod-logs-inventory.json'
    with open(output_file, 'w') as f:
        json.dump(inventory, f, indent=2)

    print(f"\nInventory saved to: {output_file}")

    # Print summary statistics
    print("\n=== Inventory Summary ===")
    namespaces = {}
    for entry in inventory:
        ns = entry['namespace']
        namespaces[ns] = namespaces.get(ns, 0) + 1

    print(f"Total entries: {len(inventory)}")
    print("By namespace:")
    for ns, count in sorted(namespaces.items()):
        print(f"  {ns}: {count} files")

    # Show sample entries
    print(f"\nSample entries (first 3):")
    for entry in inventory[:3]:
        print(f"  - Pod: {entry['pod_name']}")
        print(f"    Namespace: {entry['namespace']}")
        print(f"    Path: {entry['relative_path']}")
        print(f"    Size: {entry['metadata'].get('size_bytes', 0)} bytes")

    return inventory

if __name__ == '__main__':
    inventory = main()
