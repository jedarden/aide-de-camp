#!/usr/bin/env python3
"""
Extract and record log file sizes for all pod logs.
Creates a structured dict mapping file → size_bytes.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any

def get_file_size(file_path: str) -> int:
    """Get file size in bytes, handling errors gracefully."""
    try:
        return os.path.getsize(file_path)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"Warning: Could not get size for {file_path}: {e}")
        return -1

def find_all_pod_logs() -> Dict[str, int]:
    """Find all pod log files and extract their sizes."""
    workspace = Path("/home/coding/aide-de-camp")
    file_sizes: Dict[str, int] = {}

    # Define search directories for pod logs
    search_dirs = [
        workspace / "research" / "pbx-web-30days" / "pod-logs",
        workspace / "research" / "whisper-stt-30days" / "pod-logs",
        workspace / "logs",
        workspace / "logs" / "pbx-web-30day",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            print(f"Directory does not exist: {search_dir}")
            continue

        print(f"\nScanning directory: {search_dir}")
        # Find all .log files
        log_files = list(search_dir.glob("**/*.log"))

        for log_file in log_files:
            # Get relative path from workspace for cleaner output
            try:
                rel_path = str(log_file.relative_to(workspace))
            except ValueError:
                # If file is not relative to workspace, use absolute path
                rel_path = str(log_file)

            size = get_file_size(str(log_file))
            if size >= 0:  # Only include successfully accessed files
                file_sizes[rel_path] = size
                print(f"  {rel_path}: {size} bytes")

    return file_sizes

def verify_sizes(file_sizes: Dict[str, int]) -> Dict[str, Any]:
    """Verify that sizes are reasonable."""
    verification = {
        "total_files": len(file_sizes),
        "files_with_zero_size": [],
        "files_large": [],  # > 10MB
        "suspicious_sizes": [],
    }

    for file_path, size in file_sizes.items():
        if size == 0:
            verification["files_with_zero_size"].append(file_path)
        elif size > 10_000_000:  # > 10MB
            verification["files_large"].append(file_path)

    # Check for suspicious patterns (e.g., extremely small but not zero)
    for file_path, size in file_sizes.items():
        if 0 < size < 10:  # Less than 10 bytes but not zero
            verification["suspicious_sizes"].append((file_path, size))

    return verification

def main():
    print("=" * 60)
    print("Extracting pod log file sizes")
    print("=" * 60)

    # Extract file sizes
    file_sizes = find_all_pod_logs()

    print(f"\n{'=' * 60}")
    print(f"Found {len(file_sizes)} pod log files")
    print(f"{'=' * 60}")

    # Verify sizes
    verification = verify_sizes(file_sizes)

    print("\nVerification Results:")
    print(f"  Total files: {verification['total_files']}")
    print(f"  Files with zero size: {len(verification['files_with_zero_size'])}")
    print(f"  Large files (>10MB): {len(verification['files_large'])}")
    print(f"  Suspiciously small files: {len(verification['suspicious_sizes'])}")

    if verification['files_with_zero_size']:
        print("\n  Zero-size files:")
        for f in verification['files_with_zero_size'][:5]:  # Show first 5
            print(f"    - {f}")
        if len(verification['files_with_zero_size']) > 5:
            print(f"    ... and {len(verification['files_with_zero_size']) - 5} more")

    if verification['files_large']:
        print("\n  Large files:")
        for f in verification['files_large']:
            size = file_sizes[f]
            print(f"    - {f}: {size:,} bytes ({size / 1_000_000:.1f} MB)")

    # Save to JSON file
    output_file = "/home/coding/aide-de-camp/pod_log_sizes.json"
    with open(output_file, 'w') as f:
        json.dump({
            "file_sizes": file_sizes,
            "verification": verification,
            "extraction_timestamp": "2026-08-07T00:00:00Z"
        }, f, indent=2)

    print(f"\n✅ File sizes saved to: {output_file}")

    # Summary statistics
    total_size = sum(file_sizes.values())
    print(f"\nSummary:")
    print(f"  Total size across all files: {total_size:,} bytes ({total_size / 1_000_000:.1f} MB)")
    print(f"  Average file size: {total_size / len(file_sizes):,.0f} bytes")

    return file_sizes

if __name__ == "__main__":
    main()