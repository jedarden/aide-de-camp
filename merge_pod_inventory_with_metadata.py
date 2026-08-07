#!/usr/bin/env python3
"""
Merge pod inventory data with extracted metadata to create complete pod records.

This script combines:
- Existing pod inventory (pod_name, namespace, log_file_path, analysis_file_path, log_line_count)
- Extracted metadata (creation_timestamp, deletion_timestamp, log_size_bytes)

Output: Combined dataset with all fields ready for JSONL generation.
"""

import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone


def load_inventory(inventory_path: str) -> Dict[str, Any]:
    """Load pod inventory JSON file."""
    with open(inventory_path, 'r') as f:
        data = json.load(f)

    # Create a map for easy lookup
    inventory_map = {}
    for record in data['inventory']:
        key = (record['pod_name'], record['namespace'], record['log_file_path'])
        inventory_map[key] = record

    return inventory_map


def load_metadata(metadata_path: str) -> List[Dict[str, Any]]:
    """Load pod metadata JSONL file."""
    metadata_records = []
    with open(metadata_path, 'r') as f:
        for line in f:
            if line.strip():
                metadata_records.append(json.loads(line))

    return metadata_records


def merge_records(inventory_map: Dict[str, Any], metadata_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge inventory and metadata records."""
    merged_records = []
    missing_in_inventory = []

    for metadata_record in metadata_records:
        key = (metadata_record['pod_name'], metadata_record['namespace'], metadata_record['log_file_path'])

        # Start with metadata record as base (it has more complete timestamp info)
        merged_record = metadata_record.copy()

        # Add log_line_count from inventory if available
        if key in inventory_map:
            inventory_record = inventory_map[key]
            if 'log_line_count' in inventory_record:
                merged_record['log_line_count'] = inventory_record['log_line_count']
        else:
            missing_in_inventory.append(key)

        merged_records.append(merged_record)

    if missing_in_inventory:
        print(f"Warning: {len(missing_in_inventory)} metadata records not found in inventory")
        for key in missing_in_inventory[:5]:
            print(f"  - {key}")

    return merged_records


def validate_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate that all required fields are present."""
    required_fields = ['pod_name', 'namespace', 'log_file_path', 'analysis_file_path']
    optional_fields = ['creation_timestamp', 'deletion_timestamp', 'log_size_bytes', 'log_line_count', 'has_analysis', 'collection_source']

    validated_records = []
    issues = []

    for i, record in enumerate(records):
        # Check required fields (field must be present, but can be None/null)
        missing_required = [field for field in required_fields if field not in record]

        if missing_required:
            issues.append({
                'record_index': i,
                'pod_name': record.get('pod_name', 'UNKNOWN'),
                'missing_fields': missing_required,
                'issue': 'Missing required fields'
            })
            continue

        # Ensure optional fields have defaults
        for field in optional_fields:
            if field not in record:
                record[field] = None

        validated_records.append(record)

    if issues:
        print(f"Validation found {len(issues)} issues:")
        for issue in issues[:10]:
            print(f"  - Record {issue['record_index']} ({issue['pod_name']}): {issue['issue']}")
            print(f"    Missing: {issue['missing_fields']}")

    return validated_records


def save_combined_jsonl(records: List[Dict[str, Any]], output_path: str) -> None:
    """Save merged records as JSONL."""
    with open(output_path, 'w') as f:
        for record in records:
            f.write(json.dumps(record, separators=(',', ':')) + '\n')


def generate_summary_report(records: List[Dict[str, Any]], output_path: str) -> None:
    """Generate summary report of merged dataset."""
    total_records = len(records)

    # Count by namespace
    namespace_counts = {}
    for record in records:
        namespace = record['namespace']
        namespace_counts[namespace] = namespace_counts.get(namespace, 0) + 1

    # Count fields completeness
    field_completeness = {}
    for field in ['creation_timestamp', 'deletion_timestamp', 'log_size_bytes', 'log_line_count', 'analysis_file_path']:
        count = sum(1 for r in records if r.get(field) is not None)
        field_completeness[field] = {
            'present': count,
            'total': total_records,
            'percentage': round(count / total_records * 100, 1) if total_records > 0 else 0
        }

    summary = {
        'merge_date': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'total_records': total_records,
        'namespaces': namespace_counts,
        'field_completeness': field_completeness,
        'sample_records': records[:3]
    }

    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2)


def main():
    """Main execution function."""
    base_path = Path('/home/coding/aide-de-camp/tmp')

    inventory_path = base_path / 'pod-logs-inventory.json'
    metadata_path = base_path / 'pod-metadata-complete.jsonl'
    output_jsonl_path = base_path / 'pod-logs-complete-merged.jsonl'
    summary_path = base_path / 'pod-merge-summary.json'

    print("=== Merging Pod Inventory with Metadata ===")

    # Load datasets
    print("Loading inventory...")
    inventory_map = load_inventory(str(inventory_path))
    print(f"  Loaded {len(inventory_map)} inventory records")

    print("Loading metadata...")
    metadata_records = load_metadata(str(metadata_path))
    print(f"  Loaded {len(metadata_records)} metadata records")

    # Merge records
    print("Merging records...")
    merged_records = merge_records(inventory_map, metadata_records)
    print(f"  Merged {len(merged_records)} records")

    # Validate records
    print("Validating records...")
    validated_records = validate_records(merged_records)
    print(f"  {len(validated_records)} records validated")

    # Save combined dataset
    print("Saving combined dataset...")
    save_combined_jsonl(validated_records, str(output_jsonl_path))
    print(f"  Saved to {output_jsonl_path}")

    # Generate summary
    print("Generating summary report...")
    generate_summary_report(validated_records, str(summary_path))
    print(f"  Saved to {summary_path}")

    print("\n=== Merge Complete ===")
    print(f"Total valid records: {len(validated_records)}")
    print(f"Output file: {output_jsonl_path}")
    print(f"Summary file: {summary_path}")


if __name__ == '__main__':
    main()