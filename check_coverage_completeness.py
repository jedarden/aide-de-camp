#!/usr/bin/env python3
"""
Check completeness of pod-logs-index.jsonl coverage by comparing with actual log files.
"""
import json
from pathlib import Path
from collections import defaultdict

def find_log_files(base_dirs):
    """Find all .log files in the specified directories."""
    log_files = []
    for base_dir in base_dirs:
        base_path = Path(base_dir)
        if base_path.exists():
            for log_file in base_path.rglob("*.log"):
                # Skip if it's an analysis file
                if "analysis" not in log_file.name:
                    log_files.append(log_file)
    return log_files

def extract_index_files(index_file):
    """Extract all log file paths from the index."""
    indexed_files = set()
    with open(index_file, 'r') as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                log_path = record.get("log_file_metadata", {}).get("log_file_path")
                if log_path:
                    indexed_files.add(log_path)
    return indexed_files

def main():
    base_dirs = [
        "/home/coding/aide-de-camp/research/pbx-web-30days/pod-logs",
        "/home/coding/aide-de-camp/research/whisper-stt-30days/pod-logs"
    ]
    index_file = "/home/coding/aide-de-camp/pod-logs-index.jsonl"

    print("=" * 80)
    print("COVERAGE COMPLETENESS CHECK")
    print("=" * 80)
    print()

    # Find all actual log files
    print("Scanning for log files in source directories...")
    actual_log_files = find_log_files(base_dirs)
    actual_log_files_rel = {str(f.relative_to("/home/coding/aide-de-camp")) for f in actual_log_files}

    print(f"  Found {len(actual_log_files)} log files:")
    for directory in base_dirs:
        dir_path = Path(directory)
        if dir_path.exists():
            files_in_dir = [f for f in actual_log_files if directory in str(f)]
            print(f"    - {directory}: {len(files_in_dir)} files")

    print()

    # Extract indexed files
    print("Extracting files from pod-logs-index.jsonl...")
    indexed_files = extract_index_files(index_file)
    print(f"  Found {len(indexed_files)} indexed log files")

    print()

    # Compare
    print("Checking coverage completeness...")

    # Files in index but not on disk
    missing_on_disk = indexed_files - actual_log_files_rel
    if missing_on_disk:
        print(f"  ⚠️  {len(missing_on_disk)} files in index but not found on disk:")
        for f in sorted(missing_on_disk)[:5]:
            print(f"      - {f}")
        if len(missing_on_disk) > 5:
            print(f"      ... and {len(missing_on_disk) - 5} more")
    else:
        print(f"  ✓ All indexed files exist on disk")

    print()

    # Files on disk but not in index
    missing_from_index = actual_log_files_rel - indexed_files
    if missing_from_index:
        print(f"  ⚠️  {len(missing_from_index)} files on disk but not in index:")
        for f in sorted(missing_from_index)[:10]:
            print(f"      - {f}")
        if len(missing_from_index) > 10:
            print(f"      ... and {len(missing_from_index) - 10} more")
    else:
        print(f"  ✓ All disk files are indexed")

    print()
    print("=" * 80)
    print("COVERAGE SUMMARY")
    print("=" * 80)

    coverage_percent = (len(indexed_files & actual_log_files_rel) / len(actual_log_files_rel) * 100) if actual_log_files_rel else 100

    if not missing_from_index and not missing_on_disk:
        print(f"✓ COMPLETE: 100% coverage")
        print(f"  - All {len(actual_log_files)} log files are indexed")
        print(f"  - All indexed files exist on disk")
        return 0
    else:
        print(f"⚠️  INCOMPLETE: {coverage_percent:.1f}% coverage")
        print(f"  - Files on disk: {len(actual_log_files)}")
        print(f"  - Files indexed: {len(indexed_files)}")
        print(f"  - Missing from index: {len(missing_from_index)}")
        print(f"  - Missing on disk: {len(missing_on_disk)}")

        if missing_from_index:
            print(f"  ⚠️  Some log files are not represented in the index")
        if missing_on_disk:
            print(f"  ⚠️  Some indexed files don't exist on disk (stale data)")

        return 1

if __name__ == "__main__":
    exit(main())
