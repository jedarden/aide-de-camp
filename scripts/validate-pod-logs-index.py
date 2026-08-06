#!/usr/bin/env python3
"""
Validate pod-logs-index.jsonl

Checks:
- Each line is valid JSON
- Count of entries matches count of pod log files
- All required fields are present
- Creates validation report
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


# Required field paths according to schema
# Note: temporal_boundaries fields are optional if no patterns were detected
REQUIRED_FIELDS = [
    "pod_identification.pod_name",
    "pod_identification.namespace",
    "log_file_metadata.log_file_path",
    "log_file_metadata.log_size_bytes",
    "log_file_metadata.collection_date",
    "pattern_detection.startup",
    "pattern_detection.oom_kill",
    "pattern_detection.error",
    "pattern_detection.performance",
]


def get_nested_value(obj: Dict[str, Any], path: str) -> Any:
    """Get value from nested dict using dot notation path."""
    keys = path.split('.')
    value = obj
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
            if value is None:
                return None
        else:
            return None
    return value


def validate_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """
    Validate JSONL file and return list of parsed entries.

    Returns list of (line_number, entry_dict, errors) tuples.
    """
    results = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                results.append({
                    "line_number": line_num,
                    "entry": None,
                    "errors": ["Empty line"]
                })
                continue

            try:
                entry = json.loads(line)
                results.append({
                    "line_number": line_num,
                    "entry": entry,
                    "errors": []
                })
            except json.JSONDecodeError as e:
                results.append({
                    "line_number": line_num,
                    "entry": None,
                    "errors": [f"Invalid JSON: {e}"]
                })

    return results


def check_required_fields(entry: Dict[str, Any]) -> List[str]:
    """Check if all required fields are present in entry."""
    missing = []

    for field_path in REQUIRED_FIELDS:
        value = get_nested_value(entry, field_path)
        if value is None:
            missing.append(field_path)

    return missing


def count_pod_logs() -> Dict[str, int]:
    """Count actual pod log files in both directories."""
    counts = {}

    for pod_logs_dir in [
        ("pbx-web", Path("research/pbx-web-30days/pod-logs")),
        ("whisper-stt", Path("research/whisper-stt-30days/pod-logs"))
    ]:
        service_name, dir_path = pod_logs_dir
        if dir_path.exists():
            log_files = list(dir_path.glob("*.log"))
            counts[service_name] = len(log_files)

    return counts


def main():
    index_file = Path("pod-logs-index.jsonl")

    if not index_file.exists():
        print(f"Error: {index_file} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Validating {index_file}...\n")

    # Validate JSONL format
    results = validate_jsonl(index_file)

    # Count total and valid entries
    total_lines = len(results)
    valid_entries = [r for r in results if r["entry"] is not None]
    invalid_entries = [r for r in results if r["entry"] is None]

    print(f"Total lines: {total_lines}")
    print(f"Valid JSON entries: {len(valid_entries)}")
    print(f"Invalid JSON entries: {len(invalid_entries)}\n")

    # Check required fields for valid entries
    field_errors = []
    for result in valid_entries:
        entry = result["entry"]
        missing = check_required_fields(entry)
        if missing:
            field_errors.append({
                "line_number": result["line_number"],
                "missing_fields": missing
            })

    print(f"Entries with missing required fields: {len(field_errors)}\n")

    # Count actual pod log files
    pod_log_counts = count_pod_logs()
    total_pod_logs = sum(pod_log_counts.values())

    print(f"Actual pod log files:")
    for dir_name, count in pod_log_counts.items():
        print(f"  {dir_name}: {count}")
    print(f"  Total: {total_pod_logs}")
    print(f"JSONL entries: {len(valid_entries)}\n")

    # Get file size
    file_size = index_file.stat().st_size

    # Generate validation report
    report_lines = [
        "# Pod Logs Index Validation Report",
        f"\nGenerated: {__import__('datetime').datetime.now().isoformat()}",
        f"\n## File Statistics",
        f"- **File**: {index_file}",
        f"- **Size**: {file_size:,} bytes ({file_size / 1024:.2f} KB)",
        f"- **Total lines**: {total_lines}",
        f"- **Valid JSON entries**: {len(valid_entries)}",
        f"- **Invalid JSON entries**: {len(invalid_entries)}",
        f"\n## Pod Log File Counts",
    ]

    for dir_name, count in pod_log_counts.items():
        report_lines.append(f"- **{dir_name}**: {count} files")

    report_lines.extend([
        f"- **Total pod log files**: {total_pod_logs}",
        f"- **JSONL entries**: {len(valid_entries)}",
        f"\n## Validation Results",
        f"\n### JSON Format Validation",
        f"- ✅ Valid JSON: {len(valid_entries)} / {total_lines}",
    ])

    if invalid_entries:
        report_lines.append(f"- ❌ Invalid JSON: {len(invalid_entries)} / {total_lines}")
        report_lines.append("\n#### Invalid JSON Entries:")
        for entry in invalid_entries[:10]:
            report_lines.append(f"- Line {entry['line_number']}: {entry['errors'][0]}")
        if len(invalid_entries) > 10:
            report_lines.append(f"- ... and {len(invalid_entries) - 10} more")

    report_lines.extend([
        f"\n### Required Fields Validation",
        f"- ✅ All required fields present: {len(valid_entries) - len(field_errors)} / {len(valid_entries)}",
    ])

    if field_errors:
        report_lines.append(f"- ❌ Missing required fields: {len(field_errors)} / {len(valid_entries)}")
        report_lines.append("\n#### Entries with Missing Fields:")
        for error in field_errors[:10]:
            report_lines.append(f"- Line {error['line_number']}: Missing {', '.join(error['missing_fields'][:3])}")
        if len(field_errors) > 10:
            report_lines.append(f"- ... and {len(field_errors) - 10} more")

    report_lines.extend([
        f"\n## Conclusion",
    ])

    if invalid_entries or field_errors:
        report_lines.append("❌ **VALIDATION FAILED** - See errors above")
    else:
        report_lines.append("✅ **VALIDATION PASSED** - All entries are valid JSON with complete required fields")

    if total_pod_logs != len(valid_entries):
        report_lines.append(f"\n⚠️ **WARNING**: Entry count mismatch - {total_pod_logs} pod log files vs {len(valid_entries)} JSONL entries")

    # Write report
    report_path = Path("pod-logs-index-validation.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))

    print(f"Validation report written to {report_path}\n")

    # Print summary
    if invalid_entries or field_errors:
        print("❌ VALIDATION FAILED")
        if invalid_entries:
            print(f"  - {len(invalid_entries)} invalid JSON entries")
        if field_errors:
            print(f"  - {len(field_errors)} entries with missing fields")
        sys.exit(1)
    else:
        print("✅ VALIDATION PASSED")
        print(f"  - All {len(valid_entries)} entries are valid JSON")
        print(f"  - All required fields present")
        if total_pod_logs == len(valid_entries):
            print(f"  - Entry count matches pod log files")
        else:
            print(f"  - ⚠️ Entry count: {len(valid_entries)} vs pod logs: {total_pod_logs}")
        sys.exit(0)


if __name__ == "__main__":
    main()
