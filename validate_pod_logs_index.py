#!/usr/bin/env python3
"""
Validate pod-logs-index.jsonl for syntax correctness and completeness.
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

# Required field structure
REQUIRED_SECTIONS = [
    "pod_identification",
    "log_file_metadata",
    "analysis_metadata",
    "pattern_detection",
    "temporal_boundaries"
]

REQUIRED_POD_IDENTIFICATION_FIELDS = [
    "pod_name",
    "namespace"
]

REQUIRED_LOG_FILE_METADATA_FIELDS = [
    "log_file_path",
    "log_size_bytes",
    "collection_date"
]

REQUIRED_PATTERN_DETECTION_FIELDS = [
    "startup",
    "oom_kill",
    "error",
    "performance"
]

REQUIRED_TEMPORAL_BOUNDARIES_FIELDS = [
    "analysis_date",
    "collection_date"
]

def parse_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """Parse JSONL file and return list of records."""
    records = []
    errors = []

    with open(file_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                errors.append(f"Line {line_num}: Empty line")
                continue

            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: JSON parse error - {str(e)}")

    return records, errors

def validate_record(record: Dict[str, Any], line_num: int) -> List[str]:
    """Validate a single record for required fields."""
    issues = []

    # Check required sections exist
    for section in REQUIRED_SECTIONS:
        if section not in record:
            issues.append(f"Line {line_num}: Missing required section '{section}'")
            continue

        # Validate section-specific fields
        if section == "pod_identification":
            for field in REQUIRED_POD_IDENTIFICATION_FIELDS:
                if field not in record.get(section, {}):
                    issues.append(f"Line {line_num}: Missing required field '{section}.{field}'")

        elif section == "log_file_metadata":
            for field in REQUIRED_LOG_FILE_METADATA_FIELDS:
                if field not in record.get(section, {}):
                    issues.append(f"Line {line_num}: Missing required field '{section}.{field}'")

        elif section == "pattern_detection":
            for field in REQUIRED_PATTERN_DETECTION_FIELDS:
                if field not in record.get(section, {}):
                    issues.append(f"Line {line_num}: Missing required field '{section}.{field}'")
                else:
                    # Check pattern structure
                    pattern = record[section][field]
                    if not isinstance(pattern, dict):
                        issues.append(f"Line {line_num}: Field '{section}.{field}' must be a dictionary")
                    else:
                        for required_key in ["count", "timestamps", "samples"]:
                            if required_key not in pattern:
                                issues.append(f"Line {line_num}: Missing required key '{section}.{field}.{required_key}'")

        elif section == "temporal_boundaries":
            for field in REQUIRED_TEMPORAL_BOUNDARIES_FIELDS:
                if field not in record.get(section, {}):
                    issues.append(f"Line {line_num}: Missing required field '{section}.{field}'")

    return issues

def check_data_coverage(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Check data completeness and coverage."""
    coverage_info = {
        "total_records": len(records),
        "unique_pods": set(),
        "namespaces": defaultdict(int),
        "log_type_distribution": defaultdict(int),
        "records_with_analysis": 0,
        "records_with_null_analysis": 0,
        "empty_log_files": 0,
        "logs_with_errors": 0,
        "logs_with_patterns": defaultdict(int)
    }

    for record in records:
        # Track unique pods
        pod_name = record.get("pod_identification", {}).get("pod_name", "UNKNOWN")
        coverage_info["unique_pods"].add(pod_name)

        # Track namespaces
        namespace = record.get("pod_identification", {}).get("namespace", "UNKNOWN")
        coverage_info["namespaces"][namespace] += 1

        # Track log types
        log_type = record.get("log_file_metadata", {}).get("log_type")
        if log_type:
            coverage_info["log_type_distribution"][log_type] += 1

        # Track analysis availability
        analysis_path = record.get("analysis_metadata", {}).get("analysis_file_path")
        if analysis_path:
            coverage_info["records_with_analysis"] += 1
        else:
            coverage_info["records_with_null_analysis"] += 1

        # Track empty log files
        log_size = record.get("log_file_metadata", {}).get("log_size_bytes", 0)
        if log_size == 0:
            coverage_info["empty_log_files"] += 1

        # Track error patterns
        patterns = record.get("pattern_detection", {})
        for pattern_type, pattern_data in patterns.items():
            if isinstance(pattern_data, dict) and pattern_data.get("count", 0) > 0:
                coverage_info["logs_with_patterns"][pattern_type] += 1
                if pattern_type == "error":
                    coverage_info["logs_with_errors"] += 1

    coverage_info["unique_pods"] = len(coverage_info["unique_pods"])
    coverage_info["namespaces"] = dict(coverage_info["namespaces"])
    coverage_info["log_type_distribution"] = dict(coverage_info["log_type_distribution"])
    coverage_info["logs_with_patterns"] = dict(coverage_info["logs_with_patterns"])

    return coverage_info

def main():
    index_file = Path("/home/coding/aide-de-camp/pod-logs-index.jsonl")

    if not index_file.exists():
        print(f"ERROR: File not found: {index_file}")
        sys.exit(1)

    print("=" * 80)
    print("POD LOGS INDEX VALIDATION REPORT")
    print("=" * 80)
    print()

    # Parse JSONL
    print("Step 1: Parsing JSONL syntax...")
    records, parse_errors = parse_jsonl(index_file)

    if parse_errors:
        print(f"  ❌ Found {len(parse_errors)} JSON parsing errors:")
        for error in parse_errors[:10]:  # Show first 10
            print(f"    - {error}")
        if len(parse_errors) > 10:
            print(f"    ... and {len(parse_errors) - 10} more")
    else:
        print(f"  ✓ All {len(records)} lines parsed successfully as valid JSON")

    print()

    # Validate required fields
    print("Step 2: Validating required fields...")
    field_issues = []
    for i, record in enumerate(records, 1):
        field_issues.extend(validate_record(record, i))

    if field_issues:
        print(f"  ❌ Found {len(field_issues)} field validation issues:")
        for issue in field_issues[:10]:
            print(f"    - {issue}")
        if len(field_issues) > 10:
            print(f"    ... and {len(field_issues) - 10} more")
    else:
        print(f"  ✓ All records contain required fields")

    print()

    # Check data coverage
    print("Step 3: Analyzing data coverage...")
    coverage = check_data_coverage(records)

    print(f"  Total records: {coverage['total_records']}")
    print(f"  Unique pods: {coverage['unique_pods']}")
    print(f"  Namespaces: {list(coverage['namespaces'].keys())}")
    print(f"  Records with analysis: {coverage['records_with_analysis']}")
    print(f"  Records without analysis: {coverage['records_with_null_analysis']}")
    print(f"  Empty log files (0 bytes): {coverage['empty_log_files']}")
    print(f"  Logs with error patterns: {coverage['logs_with_errors']}")

    if coverage['log_type_distribution']:
        print(f"  Log type distribution:")
        for log_type, count in coverage['log_type_distribution'].items():
            print(f"    - {log_type}: {count}")

    if coverage['logs_with_patterns']:
        print(f"  Pattern detection results:")
        for pattern_type, count in coverage['logs_with_patterns'].items():
            print(f"    - {pattern_type}: {count} logs")

    print()

    # Final verdict
    print("=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    total_issues = len(parse_errors) + len(field_issues)

    if total_issues == 0:
        print("✓ PASSED: pod-logs-index.jsonl is syntactically valid and complete")
        print(f"  - All {len(records)} records are valid JSON")
        print(f"  - All required fields present")
        print(f"  - {coverage['unique_pods']} unique pods indexed")
        print(f"  - {coverage['records_with_analysis']} records have analysis files")
        return 0
    else:
        print(f"❌ FAILED: Found {total_issues} issues")
        print(f"  - JSON parsing errors: {len(parse_errors)}")
        print(f"  - Field validation issues: {len(field_issues)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
