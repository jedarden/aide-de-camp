#!/usr/bin/env python3
"""
Extract and parse deployment failure data from log files.

This script reads deployment log files and parses:
- timestamp: datetime strings converted to timestamp objects
- pattern_type: failure pattern category
- service: service name
- image_version: container image tag

Output: Structured data list to console for verification.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """
    Parse timestamp string into datetime object.

    Handles multiple ISO 8601 formats with/without microseconds and 'Z' suffix.
    """
    if not timestamp_str:
        return None

    # Common ISO 8601 formats to try
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",  # With microseconds and Z
        "%Y-%m-%dT%H:%M:%SZ",     # Without microseconds and Z
        "%Y-%m-%dT%H:%M:%S.%f",   # With microseconds, no Z
        "%Y-%m-%dT%H:%M:%S",      # Without microseconds, no Z
        "%Y-%m-%d",               # Date only
    ]

    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue

    print(f"Warning: Could not parse timestamp: {timestamp_str}", file=sys.stderr)
    return None


def extract_image_version(image: str) -> Optional[str]:
    """
    Extract version from image string (e.g., "ronaldraygun/pbx-web:1.0.9" -> "1.0.9").
    """
    if not image:
        return None

    if ":" in image:
        return image.split(":", 1)[1]
    return None


def parse_classified_failures_file(filepath: Path) -> List[Dict[str, Any]]:
    """
    Parse classified-failures.json and extract structured records.
    """
    records = []

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        classified_failures = data.get("classified_failures", [])

        for entry in classified_failures:
            timestamp = parse_timestamp(entry.get("timestamp"))
            image_version = extract_image_version(entry.get("image"))

            record = {
                "timestamp": timestamp,
                "timestamp_raw": entry.get("timestamp"),
                "pattern_type": entry.get("pattern_type"),
                "service": entry.get("service"),
                "image_version": image_version,
                "image_full": entry.get("image"),
                "event_type": entry.get("event_type"),
                "severity": entry.get("pattern_severity"),
                "source_file": entry.get("source_file")
            }
            records.append(record)

    except FileNotFoundError:
        print(f"Warning: File not found: {filepath}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Warning: Invalid JSON in {filepath}: {e}", file=sys.stderr)

    return records


def parse_deployment_data_file(filepath: Path) -> List[Dict[str, Any]]:
    """
    Parse deployment data file (pbx-web-deployment-data-30days.json, etc.).
    """
    records = []

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        deployment_events = data.get("deployment_events_last_30_days", [])
        service = data.get("metadata", {}).get("service")

        for entry in deployment_events:
            timestamp = parse_timestamp(entry.get("timestamp"))
            image_version = extract_image_version(entry.get("image"))

            # Derive pattern_type from event_type
            event_type = entry.get("event_type", "")
            pattern_type = "Other"
            if "rollback" in event_type.lower():
                pattern_type = "CrashLoopBackOff"  # Rollbacks often indicate crashes
            elif "rollout" in event_type.lower():
                pattern_type = "deployment_rollout"  # Not a failure, normal operation

            record = {
                "timestamp": timestamp,
                "timestamp_raw": entry.get("timestamp"),
                "pattern_type": pattern_type,
                "service": service,
                "image_version": image_version,
                "image_full": entry.get("image"),
                "event_type": event_type,
                "revision": entry.get("revision"),
                "source_file": filepath.name
            }
            records.append(record)

    except FileNotFoundError:
        print(f"Warning: File not found: {filepath}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Warning: Invalid JSON in {filepath}: {e}", file=sys.stderr)

    return records


def main():
    """Main extraction and parsing routine."""
    base_dir = Path("/home/coding/aide-de-camp/docs/research/deployment-data/")

    all_records = []

    # Parse classified failures file (primary source of pattern data)
    classified_file = base_dir / "classified-failures.json"
    if classified_file.exists():
        print(f"Reading: {classified_file.name}")
        records = parse_classified_failures_file(classified_file)
        all_records.extend(records)
        print(f"  → Extracted {len(records)} records\n")

    # Parse deployment data files (additional source)
    deployment_files = [
        "pbx-web-deployment-data-30days.json",
        "whisper-stt-deployment-data-30days.json",
    ]

    for filename in deployment_files:
        filepath = base_dir / filename
        if filepath.exists():
            print(f"Reading: {filename}")
            records = parse_deployment_data_file(filepath)
            all_records.extend(records)
            print(f"  → Extracted {len(records)} records\n")

    # Sort by timestamp
    all_records.sort(key=lambda r: r["timestamp"] or datetime.min)

    # Output summary
    print("=" * 80)
    print(f"TOTAL RECORDS: {len(all_records)}")
    print("=" * 80)

    # Output structured data
    print("\nSTRUCTURED DATA OUTPUT:")
    print("-" * 80)

    for i, record in enumerate(all_records, 1):
        print(f"\nRecord {i}:")
        print(f"  Timestamp:        {record['timestamp']}")
        print(f"  Timestamp (raw):  {record['timestamp_raw']}")
        print(f"  Pattern Type:     {record['pattern_type']}")
        print(f"  Service:          {record['service']}")
        print(f"  Image Version:    {record['image_version']}")
        print(f"  Image Full:       {record['image_full']}")
        if 'event_type' in record:
            print(f"  Event Type:       {record['event_type']}")
        if 'severity' in record:
            print(f"  Severity:         {record['severity']}")
        if 'revision' in record:
            print(f"  Revision:         {record['revision']}")
        print(f"  Source File:      {record.get('source_file', 'N/A')}")

    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS:")
    print("=" * 80)

    services = set(r['service'] for r in all_records if r['service'])
    pattern_types = set(r['pattern_type'] for r in all_records if r['pattern_type'])

    print(f"Services found: {', '.join(sorted(services))}")
    print(f"Pattern types found: {', '.join(sorted(pattern_types))}")
    print(f"Records with valid timestamps: {sum(1 for r in all_records if r['timestamp'])}")
    print(f"Records with image versions: {sum(1 for r in all_records if r['image_version'])}")

    # Records with parsing issues
    missing_timestamps = [r for r in all_records if not r['timestamp']]
    if missing_timestamps:
        print(f"\n⚠ Records with unparseable timestamps: {len(missing_timestamps)}")

    missing_patterns = [r for r in all_records if not r['pattern_type']]
    if missing_patterns:
        print(f"⚠ Records without pattern type: {len(missing_patterns)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
