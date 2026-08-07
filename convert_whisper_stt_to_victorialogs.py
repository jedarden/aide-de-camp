#!/usr/bin/env python3
"""
Convert whisper-stt logs to VictoriaLogs format for latency analysis.

This script reads the existing whisper-stt-30day.jsonl file and converts it
to VictoriaLogs format with _time and _msg fields, allowing the latency
query script to process the data properly.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

def convert_to_victorialogs_format(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert whisper-stt log entry to VictoriaLogs format.

    Args:
        entry: Original whisper-stt log entry

    Returns:
        VictoriaLogs-formatted entry
    """
    timestamp = entry.get("timestamp", "")
    message = entry.get("message", "")
    pod_name = entry.get("pod_name", "") or ""
    namespace = entry.get("namespace", "") or ""
    log_level = entry.get("log_level", "INFO")
    service = entry.get("service", "whisper-stt")

    # Convert timestamp to VictoriaLogs format if needed
    # Input format: "2026-07-10T13:39:33.767796087-04:00"
    # VictoriaLogs format: "2026-07-10T13:39:33.767796087-04:00" (can keep same format)

    vlogs_entry = {
        "_time": timestamp,
        "_stream_id": str(uuid.uuid4()).replace("-", "")[:24],
        "_stream": f'{{app="{service}",namespace="{namespace}"}}',
        "_msg": message,
        "app": service,
        "namespace": namespace,
        "log_level": log_level,
        "kubernetes": {
            "namespace_name": namespace,
            "pod_name": pod_name,
            "container_name": "whisper-openai" if pod_name and "whisper-openai" in pod_name else "whisper-stt"
        }
    }

    return vlogs_entry

def main():
    """Convert whisper-stt logs to VictoriaLogs format."""
    print("=" * 70)
    print("Converting whisper-stt logs to VictoriaLogs format")
    print("=" * 70)

    # Input file (existing whisper-stt data)
    input_file = Path("/home/coding/aide-de-camp/logs/whisper-stt-30day.jsonl")
    # Output file (VictoriaLogs format)
    output_file = Path("/home/coding/aide-de-camp/logs/whisper-stt-30day-victorialogs.jsonl")

    if not input_file.exists():
        print(f"✗ Input file not found: {input_file}")
        return

    print(f"\nInput file: {input_file}")
    print(f"Output file: {output_file}")
    print(f"Input size: {input_file.stat().st_size / (1024*1024):.1f} MB")

    entries_converted = 0
    entries_failed = 0

    print("\nConverting entries...")

    with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
        for line_num, line in enumerate(infile, 1):
            try:
                entry = json.loads(line.strip())
                vlogs_entry = convert_to_victorialogs_format(entry)
                outfile.write(json.dumps(vlogs_entry) + '\n')
                entries_converted += 1

                if line_num % 10000 == 0:
                    print(f"  Processed {line_num} lines...")

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                entries_failed += 1
                if entries_failed <= 10:  # Only show first 10 errors
                    print(f"  Error on line {line_num}: {e}")

    print(f"\n✓ Conversion complete!")
    print(f"  Entries converted: {entries_converted}")
    print(f"  Entries failed: {entries_failed}")
    print(f"  Output size: {output_file.stat().st_size / (1024*1024):.1f} MB")
    print(f"  Output file: {output_file}")

    # Verify the conversion
    print("\nVerifying conversion...")
    with open(output_file, 'r') as f:
        first_line = f.readline()
        try:
            sample = json.loads(first_line)
            print(f"  Sample entry has _time: {bool(sample.get('_time'))}")
            print(f"  Sample entry has _msg: {bool(sample.get('_msg'))}")
            print(f"  Sample entry has kubernetes.pod_name: {bool(sample.get('kubernetes', {}).get('pod_name'))}")
            print("  ✓ Conversion format verified")
        except Exception as e:
            print(f"  ✗ Verification failed: {e}")

if __name__ == "__main__":
    main()