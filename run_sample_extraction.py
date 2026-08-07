#!/usr/bin/env python3
"""
Run extraction on sample log files and capture results.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any

# Select 10 representative sample log files
SAMPLE_FILES = [
    "/home/coding/aide-de-camp/logs/whisper-stt-single-test.jsonl",  # 480 lines - JSONL format
    "/home/coding/aide-de-camp/logs/pbx-web-nginx.log",               # 1000 lines - nginx format
    "/home/coding/aide-de-camp/logs/pbx-web-site-generator.log",      # 2761 lines - application logs
    "/home/coding/aide-de-camp/logs/whisper-openai.log",              # 97658 lines - large file
    "/home/coding/aide-de-camp/logs/whisper-openai-pod.log",          # 10000 lines - pod logs
    "/home/coding/aide-de-camp/logs/whisper-openai-raw.log",          # 96086 lines - raw logs
    "/home/coding/aide-de-camp/logs/whisper-stt-main.log",            # 0 lines - empty file
    "/home/coding/aide-de-camp/logs/whisper-stt-pod.log",              # 0 lines - empty file
    "/home/coding/aide-de-camp/logs/pbx-web-site-generator-recent.log", # 1 line - tiny file
    "/home/coding/aide-de-camp/logs/whisper-stt-events.jsonl",         # 0 lines - empty JSONL
]

def extract_file_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extract metadata from a single log file using extract_single_file.py
    """
    try:
        result = subprocess.run(
            [sys.executable, "/home/coding/aide-de-camp/extract_single_file.py", file_path],
            capture_output=True,
            text=True,
            timeout=30
        )

        return {
            "file_path": file_path,
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "metadata": json.loads(result.stdout) if result.returncode == 0 else None
        }
    except subprocess.TimeoutExpired:
        return {
            "file_path": file_path,
            "success": False,
            "error": "Timeout after 30 seconds",
            "metadata": None
        }
    except Exception as e:
        return {
            "file_path": file_path,
            "success": False,
            "error": str(e),
            "metadata": None
        }

def main():
    """Run extraction on all sample files."""
    print("=" * 60)
    print("EXTRACTION TEST ON SAMPLE LOG FILES")
    print("=" * 60)

    results = []
    successful_count = 0
    failed_count = 0

    for i, file_path in enumerate(SAMPLE_FILES, 1):
        print(f"\n[{i}/{len(SAMPLE_FILES)}] Testing: {file_path}")

        # Check if file exists
        if not Path(file_path).exists():
            print(f"  ❌ FILE NOT FOUND")
            results.append({
                "file_path": file_path,
                "success": False,
                "error": "File not found"
            })
            failed_count += 1
            continue

        # Get file size
        file_size = Path(file_path).stat().st_size
        print(f"  📁 Size: {file_size:,} bytes")

        # Extract metadata
        result = extract_file_metadata(file_path)
        results.append(result)

        if result["success"]:
            successful_count += 1
            print(f"  ✅ SUCCESS")

            # Display key metadata
            if result["metadata"]:
                meta = result["metadata"]
                print(f"     - Lines: {meta.get('line_count', 'N/A')}")
                print(f"     - First timestamp: {meta.get('first_timestamp', 'N/A')}")
                print(f"     - Last timestamp: {meta.get('last_timestamp', 'N/A')}")
                print(f"     - Created: {meta.get('creation_timestamp', 'N/A')}")
        else:
            failed_count += 1
            print(f"  ❌ FAILED")
            if "error" in result:
                print(f"     Error: {result['error']}")
            if result.get("stderr"):
                print(f"     Stderr: {result['stderr'][:200]}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total files tested: {len(SAMPLE_FILES)}")
    print(f"Successful: {successful_count}")
    print(f"Failed: {failed_count}")

    # Save results to file
    output_file = Path("/home/coding/aide-de-camp/sample_extraction_results.json")
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": "2026-08-07T02:30:00Z",
            "total_files": len(SAMPLE_FILES),
            "successful": successful_count,
            "failed": failed_count,
            "results": results
        }, f, indent=2)

    print(f"\n✅ Results saved to: {output_file}")

    # List successful files
    print("\n✅ SUCCESSFUL FILES:")
    for result in results:
        if result["success"]:
            print(f"   - {result['file_path']}")

    # List failed files
    print("\n❌ FAILED FILES:")
    for result in results:
        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            print(f"   - {result['file_path']}: {error_msg}")

if __name__ == "__main__":
    main()