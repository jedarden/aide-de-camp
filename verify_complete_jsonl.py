#!/usr/bin/env python3
"""
Verify the complete JSONL output for pod logs metadata extraction.

This script:
1. Verifies all 48 records are present
2. Checks JSONL formatting
3. Validates required fields are present
4. Compares with original inventory
5. Generates verification report
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


def load_jsonl(jsonl_path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file and return list of records."""
    records = []
    try:
        with open(jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    except Exception as e:
        print(f"Error loading JSONL: {e}")
        return []
    return records


def load_inventory(inventory_path: Path) -> Dict[str, Any]:
    """Load the inventory file."""
    try:
        with open(inventory_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading inventory: {e}")
        return {}


def verify_record_structure(record: Dict[str, Any], index: int) -> List[str]:
    """Verify a single record has required structure and return any issues."""
    issues = []

    # Required fields
    required_fields = ['pod_name', 'namespace', 'log_file_path', 'file_exists',
                      'log_size_bytes', 'creation_timestamp', 'processed_at']

    for field in required_fields:
        if field not in record:
            issues.append(f"Record {index}: Missing required field '{field}'")

    # Check data types
    if 'log_size_bytes' in record and record['log_size_bytes'] is not None:
        if not isinstance(record['log_size_bytes'], int):
            issues.append(f"Record {index}: log_size_bytes should be int, got {type(record['log_size_bytes'])}")

    if 'file_exists' in record and not isinstance(record['file_exists'], bool):
        issues.append(f"Record {index}: file_exists should be bool")

    # Check that file existence matches size availability (0 is valid for empty files)
    if record.get('file_exists') and record.get('log_size_bytes') is None:
        issues.append(f"Record {index}: File exists but no log_size_bytes")

    return issues


def verify_jsonl_formatting(jsonl_path: Path) -> List[str]:
    """Verify JSONL formatting is correct."""
    issues = []

    try:
        with open(jsonl_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    json.loads(line)
                except json.JSONDecodeError as e:
                    issues.append(f"Line {line_num}: Invalid JSON - {e}")

    except Exception as e:
        issues.append(f"Could not read file: {e}")

    return issues


def compare_with_inventory(records: List[Dict[str, Any]], inventory: Dict[str, Any]) -> List[str]:
    """Compare records with original inventory."""
    issues = []

    inventory_items = inventory.get('inventory', [])

    # Check count matches
    if len(records) != len(inventory_items):
        issues.append(f"Record count mismatch: JSONL has {len(records)}, inventory has {len(inventory_items)}")

    # Create maps for comparison
    records_by_pod = {r['pod_name']: r for r in records}
    inventory_by_pod = {i['pod_name']: i for i in inventory_items}

    # Check for missing pods
    missing_in_jsonl = set(inventory_by_pod.keys()) - set(records_by_pod.keys())
    if missing_in_jsonl:
        issues.append(f"Pods in inventory but missing in JSONL: {missing_in_jsonl}")

    extra_in_jsonl = set(records_by_pod.keys()) - set(inventory_by_pod.keys())
    if extra_in_jsonl:
        issues.append(f"Pods in JSONL but missing from inventory: {extra_in_jsonl}")

    # Verify file existence consistency
    for pod_name, record in records_by_pod.items():
        if pod_name in inventory_by_pod:
            expected_path = inventory_by_pod[pod_name]['log_file_path']
            actual_path = record['log_file_path']
            if expected_path != actual_path:
                issues.append(f"Pod {pod_name}: Path mismatch - inventory says '{expected_path}', JSONL has '{actual_path}'")

    return issues


def generate_verification_report(records: List[Dict[str, Any]], issues: List[str]) -> Dict[str, Any]:
    """Generate comprehensive verification report."""
    report = {
        'verification_timestamp': datetime.now().isoformat(),
        'total_records': len(records),
        'total_issues': len(issues),
        'issues': issues,
        'statistics': {}
    }

    if not records:
        return report

    # Calculate statistics
    with_creation = sum(1 for r in records if r.get('creation_timestamp'))
    with_deletion = sum(1 for r in records if r.get('deletion_timestamp'))
    with_size = sum(1 for r in records if r.get('log_size_bytes'))
    files_exist = sum(1 for r in records if r.get('file_exists'))
    with_patterns = sum(1 for r in records if r.get('detected_patterns'))

    total_size = sum(r.get('log_size_bytes', 0) for r in records)

    # Namespace breakdown
    by_namespace = {}
    for record in records:
        ns = record.get('namespace', 'unknown')
        if ns not in by_namespace:
            by_namespace[ns] = {'count': 0, 'total_size': 0}
        by_namespace[ns]['count'] += 1
        by_namespace[ns]['total_size'] += record.get('log_size_bytes', 0)

    report['statistics'] = {
        'records_with_creation_timestamp': with_creation,
        'records_with_deletion_timestamp': with_deletion,
        'records_with_log_size_bytes': with_size,
        'files_existing': files_exist,
        'records_with_detected_patterns': with_patterns,
        'total_log_size_bytes': total_size,
        'total_log_size_mb': total_size / 1024 / 1024,
        'namespaces': by_namespace
    }

    return report


def main():
    """Main verification function."""
    repo_root = Path('/home/coding/aide-de-camp')
    jsonl_path = repo_root / 'pod-logs-complete-unified.jsonl'
    inventory_path = repo_root / 'tmp' / 'pod-logs-inventory.json'

    print("="*60)
    print("POD LOGS JSONL VERIFICATION")
    print("="*60)

    # Load files
    print("Loading JSONL file...")
    records = load_jsonl(jsonl_path)
    print(f"Loaded {len(records)} records")

    print("Loading inventory file...")
    inventory = load_inventory(inventory_path)
    print("Inventory loaded")

    all_issues = []

    # Verify JSONL formatting
    print("Verifying JSONL formatting...")
    format_issues = verify_jsonl_formatting(jsonl_path)
    all_issues.extend(format_issues)
    if format_issues:
        print(f"  ✗ Found {len(format_issues)} formatting issues")
    else:
        print("  ✓ JSONL formatting is correct")

    # Verify record structure
    print("Verifying record structure...")
    structure_issues = []
    for i, record in enumerate(records, 1):
        issues = verify_record_structure(record, i)
        structure_issues.extend(issues)

    all_issues.extend(structure_issues)
    if structure_issues:
        print(f"  ✗ Found {len(structure_issues)} structure issues")
    else:
        print("  ✓ All records have correct structure")

    # Compare with inventory
    print("Comparing with inventory...")
    inventory_issues = compare_with_inventory(records, inventory)
    all_issues.extend(inventory_issues)
    if inventory_issues:
        print(f"  ✗ Found {len(inventory_issues)} inventory mismatches")
    else:
        print("  ✓ JSONL matches inventory")

    # Generate report
    print("Generating verification report...")
    report = generate_verification_report(records, all_issues)

    # Print summary
    print(f"\n{'='*60}")
    print("VERIFICATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total records: {report['total_records']}")
    print(f"Total issues: {report['total_issues']}")

    stats = report['statistics']
    print(f"\nField Coverage:")
    print(f"  Creation timestamp: {stats['records_with_creation_timestamp']}/{report['total_records']}")
    print(f"  Deletion timestamp: {stats['records_with_deletion_timestamp']}/{report['total_records']}")
    print(f"  Log size bytes: {stats['records_with_log_size_bytes']}/{report['total_records']}")
    print(f"  Files exist: {stats['files_existing']}/{report['total_records']}")
    print(f"  Detected patterns: {stats['records_with_detected_patterns']}/{report['total_records']}")

    print(f"\nData Volume:")
    print(f"  Total log size: {stats['total_log_size_bytes']:,} bytes ({stats['total_log_size_mb']:.2f} MB)")

    print(f"\nBy Namespace:")
    for ns, ns_stats in stats['namespaces'].items():
        print(f"  {ns}:")
        print(f"    Records: {ns_stats['count']}")
        print(f"    Total size: {ns_stats['total_size']:,} bytes ({ns_stats['total_size'] / 1024 / 1024:.2f} MB)")

    if all_issues:
        print(f"\n{'='*60}")
        print("ISSUES FOUND")
        print(f"{'='*60}")
        for issue in all_issues[:20]:  # Show first 20 issues
            print(f"  • {issue}")
        if len(all_issues) > 20:
            print(f"  ... and {len(all_issues) - 20} more issues")
    else:
        print(f"\n{'='*60}")
        print("✓ VERIFICATION PASSED - No issues found")
        print(f"{'='*60}")

    # Save report
    report_path = repo_root / 'pod-logs-verification-report.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n✓ Report saved to: {report_path}")

    return len(all_issues) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)