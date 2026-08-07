#!/usr/bin/env python3
"""
Generate pod-logs-index.jsonl from inventory and analysis data.
Combines data from:
- tmp/pod-logs-inventory.json (primary inventory)
- data/analysis-patterns-extracted.json (pattern detection results)
- data/analysis-metadata-extracted.json (timestamps and metadata)
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


def load_json(filepath: Path) -> Any:
    """Load JSON file if it exists."""
    if filepath.exists():
        with open(filepath, 'r') as f:
            return json.load(f)
    return None


def extract_pod_info_from_log_path(log_path: str) -> tuple:
    """Extract pod name and namespace from log file path."""
    # Try to extract from path structure
    parts = Path(log_path).parts

    # Look for common patterns
    for i, part in enumerate(parts):
        if 'pod-' in part and part.startswith('pod-'):
            # Extract pod name from pattern like "pod-pbx-web-5ff68464d-mkn8n-2026-08-06.log"
            pod_part = part.replace('pod-', '').replace('.log', '')
            return pod_part, 'unknown'  # namespace unknown from path alone
        elif 'research' in parts and i + 1 < len(parts):
            # research/namespace-30days/pod-logs/...
            if '30days' in parts[i + 1]:
                namespace = parts[i + 1].replace('-30days', '')
                return None, namespace

    return None, 'unknown'


def merge_pod_data(inventory: Dict, patterns: List, metadata: Dict) -> List[Dict]:
    """Merge inventory, patterns, and metadata into unified records."""
    merged = {}

    # First, create lookups for patterns and metadata
    patterns_lookup = {}
    if patterns:
        for pattern_item in patterns:
            key = pattern_item.get('log_file_path', '')
            if key:
                patterns_lookup[key] = pattern_item

    metadata_lookup = {}
    if metadata:
        for meta_key, meta_value in metadata.items():
            if isinstance(meta_value, dict) and 'log_file_path' in meta_value:
                log_path = meta_value.get('log_file_path', '')
                if log_path:
                    metadata_lookup[log_path] = meta_value

    # Process inventory items
    for item in inventory.get('inventory', []):
        log_file_path = item.get('log_file_path', '')
        pod_name = item.get('pod_name', 'unknown')
        namespace = item.get('namespace', 'unknown')

        # Create record key
        record_key = f"{namespace}:{pod_name}:{log_file_path}"

        # Build the unified record
        record = {
            'pod_name': pod_name,
            'namespace': namespace,
            'creation_timestamp': None,  # Not available in current data
            'deletion_timestamp': None,  # Not available in current data
            'log_file_path': log_file_path,
            'analysis_file_path': item.get('analysis_file_path'),
            'detected_patterns': [],  # Will be populated from patterns/metadata
            'key_timestamps': {},  # Will be populated from metadata
            'log_size_bytes': item.get('log_file_size_bytes', 0)
        }

        # Add pattern data if available
        if log_file_path in patterns_lookup:
            pattern_data = patterns_lookup[log_file_path]
            record['detected_patterns'] = pattern_data.get('detected_patterns', [])
            if pattern_data.get('key_timestamps'):
                record['key_timestamps'].update(pattern_data['key_timestamps'])

        # Add metadata data if available
        if log_file_path in metadata_lookup:
            meta_data = metadata_lookup[log_file_path]

            # Extract pattern counts as detected patterns
            pattern_counts = meta_data.get('pattern_counts', {})
            if pattern_counts:
                detected = []
                for pattern_type, count in pattern_counts.items():
                    if count > 0:
                        detected.append(pattern_type)
                if detected:
                    record['detected_patterns'] = detected

            # Add timestamps
            if meta_data.get('key_timestamps'):
                record['key_timestamps'].update(meta_data['key_timestamps'])

        # Store the record
        merged[record_key] = record

    return list(merged.values())


def validate_jsonl_structure(records: List[Dict]) -> List[str]:
    """Validate records meet acceptance criteria."""
    errors = []

    required_fields = [
        'pod_name', 'namespace', 'creation_timestamp',
        'deletion_timestamp', 'log_file_path', 'analysis_file_path',
        'detected_patterns', 'key_timestamps', 'log_size_bytes'
    ]

    for i, record in enumerate(records):
        # Check required fields exist
        for field in required_fields:
            if field not in record:
                errors.append(f"Record {i}: Missing required field '{field}'")

        # Validate field types
        if 'pod_name' in record and not isinstance(record['pod_name'], str):
            errors.append(f"Record {i}: 'pod_name' must be string")

        if 'namespace' in record and not isinstance(record['namespace'], str):
            errors.append(f"Record {i}: 'namespace' must be string")

        if 'log_file_path' in record and not isinstance(record['log_file_path'], str):
            errors.append(f"Record {i}: 'log_file_path' must be string")

        if 'analysis_file_path' in record and record['analysis_file_path'] is not None:
            if not isinstance(record['analysis_file_path'], str):
                errors.append(f"Record {i}: 'analysis_file_path' must be string or null")

        if 'detected_patterns' in record:
            if not isinstance(record['detected_patterns'], list):
                errors.append(f"Record {i}: 'detected_patterns' must be array")
            else:
                # Validate pattern names
                valid_patterns = {'startup', 'oom_kill', 'error', 'performance'}
                for pattern in record['detected_patterns']:
                    if pattern not in valid_patterns:
                        errors.append(f"Record {i}: Invalid pattern '{pattern}'")

        if 'key_timestamps' in record:
            if not isinstance(record['key_timestamps'], dict):
                errors.append(f"Record {i}: 'key_timestamps' must be object")

        if 'log_size_bytes' in record:
            if not isinstance(record['log_size_bytes'], int):
                errors.append(f"Record {i}: 'log_size_bytes' must be integer")
            elif record['log_size_bytes'] < 0:
                errors.append(f"Record {i}: 'log_size_bytes' must be non-negative")

    return errors


def write_jsonl(records: List[Dict], output_path: Path) -> None:
    """Write records as JSONL (one JSON object per line)."""
    with open(output_path, 'w') as f:
        for record in records:
            json.dump(record, f)
            f.write('\n')


def validate_jsonl_syntax(filepath: Path) -> List[str]:
    """Validate JSONL syntax by parsing each line."""
    errors = []
    line_number = 0

    with open(filepath, 'r') as f:
        for line in f:
            line_number += 1
            line = line.strip()
            if not line:
                continue

            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_number}: Invalid JSON - {e}")

    return errors


def main():
    """Main generation function."""
    workspace = Path('/home/coding/aide-de-camp')

    # Load data sources
    inventory_path = workspace / 'tmp/pod-logs-inventory.json'
    patterns_path = workspace / 'data/analysis-patterns-extracted.json'
    metadata_path = workspace / 'data/analysis-metadata-extracted.json'
    output_path = workspace / 'pod-logs-index.jsonl'

    print("Loading data sources...")
    inventory = load_json(inventory_path)
    patterns = load_json(patterns_path)
    metadata = load_json(metadata_path)

    if not inventory:
        print(f"ERROR: Could not load inventory from {inventory_path}")
        return 1

    print(f"  - Inventory: {len(inventory.get('inventory', []))} log files")
    print(f"  - Patterns: {len(patterns) if patterns else 0} entries")
    print(f"  - Metadata: {len(metadata) if metadata else 0} entries")

    # Merge data
    print("\nMerging data...")
    records = merge_pod_data(inventory, patterns, metadata)
    print(f"  - Created {len(records)} unified records")

    # Validate structure
    print("\nValidating record structure...")
    structure_errors = validate_jsonl_structure(records)
    if structure_errors:
        print("  - Structure validation FAILED:")
        for error in structure_errors[:10]:  # Show first 10 errors
            print(f"    * {error}")
        if len(structure_errors) > 10:
            print(f"    * ... and {len(structure_errors) - 10} more errors")
        return 1
    print("  - Structure validation PASSED")

    # Write output
    print(f"\nWriting JSONL to {output_path}...")
    write_jsonl(records, output_path)
    print(f"  - Wrote {len(records)} records")

    # Validate JSONL syntax
    print("\nValidating JSONL syntax...")
    syntax_errors = validate_jsonl_syntax(output_path)
    if syntax_errors:
        print("  - JSONL syntax validation FAILED:")
        for error in syntax_errors:
            print(f"    * {error}")
        return 1
    print("  - JSONL syntax validation PASSED")

    # Summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Total records: {len(records)}")

    # Count by namespace
    namespace_counts = {}
    for record in records:
        ns = record['namespace']
        namespace_counts[ns] = namespace_counts.get(ns, 0) + 1

    print("\nRecords by namespace:")
    for ns, count in sorted(namespace_counts.items()):
        print(f"  - {ns}: {count}")

    # Count records with analysis
    with_analysis = sum(1 for r in records if r['analysis_file_path'])
    print(f"\nRecords with analysis: {with_analysis}/{len(records)}")

    # Count detected patterns
    pattern_counts = {'startup': 0, 'oom_kill': 0, 'error': 0, 'performance': 0}
    for record in records:
        for pattern in record['detected_patterns']:
            if pattern in pattern_counts:
                pattern_counts[pattern] += 1

    print("\nDetected pattern frequencies:")
    for pattern, count in pattern_counts.items():
        print(f"  - {pattern}: {count}")

    print(f"\n✅ SUCCESS: {output_path} generated and validated")
    return 0


if __name__ == '__main__':
    exit(main())
