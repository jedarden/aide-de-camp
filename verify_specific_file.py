#!/usr/bin/env python3
"""
Detailed analysis of the whisper-stt-30day.jsonl file to understand extraction errors.
"""

import json
import os
from pathlib import Path

def analyze_jsonl_structure(file_path: str):
    """Analyze the structure of a JSONL file."""

    print(f"Analyzing: {file_path}")
    print(f"File size: {os.path.getsize(file_path)} bytes")

    # Count lines the traditional way
    with open(file_path, 'r') as f:
        lines = f.readlines()

    print(f"Number of lines (readlines): {len(lines)}")

    # Check if it's valid JSONL (one JSON object per line)
    valid_jsonl_count = 0
    invalid_lines = []

    for i, line in enumerate(lines[:20]):  # Check first 20 lines
        try:
            json.loads(line.strip())
            valid_jsonl_count += 1
        except json.JSONDecodeError as e:
            invalid_lines.append((i, str(e)))

    print(f"Valid JSONL objects in first 20 lines: {valid_jsonl_count}")

    if invalid_lines:
        print("Invalid JSONL lines found:")
        for line_num, error in invalid_lines[:5]:
            print(f"  Line {line_num}: {error}")

    # Check if the entire file is one JSON object
    try:
        with open(file_path, 'r') as f:
            full_content = f.read()
        data = json.loads(full_content)
        print("✅ File is a single JSON object (not JSONL format)")
        print(f"Root keys: {list(data.keys())[:10]}")
    except json.JSONDecodeError:
        print("❌ File is NOT a single JSON object")

    # Show first few lines with line numbers
    print("\nFirst 5 lines with line numbers:")
    for i, line in enumerate(lines[:5]):
        print(f"Line {i}: {line[:100]}")

def check_extraction_record():
    """Check what was recorded in the extraction results."""
    unified_file = Path("/home/coding/aide-de-camp/data/log-files-unified.json")

    if not unified_file.exists():
        print("Unified file not found")
        return

    with open(unified_file, 'r') as f:
        data = json.load(f)

    # Find the whisper-stt-30day.jsonl entry
    for key, value in data.items():
        if "whisper-stt-30day.jsonl" in key:
            print(f"\n=== Extraction Record ===")
            print(f"Key: {key}")
            print(f"log_file_path: {value.get('log_file_path')}")
            print(f"log_size_bytes: {value.get('log_size_bytes')}")
            print(f"creation_timestamp: {value.get('creation_timestamp')}")
            print(f"deletion_timestamp: {value.get('deletion_timestamp')}")
            print(f"first_log_timestamp: {value.get('first_log_timestamp')}")

            # Check for other metadata
            if 'line_count' in value:
                print(f"line_count: {value.get('line_count')}")
            break

if __name__ == "__main__":
    file_path = "/home/coding/aide-de-camp/logs/whisper-stt-30day.jsonl"
    analyze_jsonl_structure(file_path)
    check_extraction_record()