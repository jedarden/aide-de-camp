#!/usr/bin/env python3
"""Validate pod inventory log file paths."""

import json
import os
from pathlib import Path
from typing import Dict, List, Any

# Workspace root
WORKSPACE_ROOT = Path("/home/coding/aide-de-camp")
INVENTORY_FILE = WORKSPACE_ROOT / "tmp" / "pod-logs-inventory.json"


def validate_inventory(inventory_path: Path) -> Dict[str, Any]:
    """Validate all log file paths in the inventory."""

    # Load inventory
    with open(inventory_path, 'r') as f:
        inventory = json.load(f)

    results = {
        "total_entries": len(inventory["inventory"]),
        "valid_files": [],
        "missing_files": [],
        "unreadable_files": [],
        "empty_files": [],
        "summary": {}
    }

    for entry in inventory["inventory"]:
        log_path = entry["log_file_path"]
        full_path = WORKSPACE_ROOT / log_path

        status = {
            "pod_name": entry["pod_name"],
            "namespace": entry["namespace"],
            "log_file_path": log_path,
            "file_exists": False,
            "is_readable": False,
            "is_empty": False,
            "file_size_bytes": entry.get("log_file_size_bytes", 0)
        }

        # Check if file exists
        if not full_path.exists():
            status["error"] = f"File does not exist: {full_path}"
            results["missing_files"].append(status)
            continue

        status["file_exists"] = True

        # Check if file is readable
        if not os.access(full_path, os.R_OK):
            status["error"] = f"File is not readable: {full_path}"
            results["unreadable_files"].append(status)
            continue

        status["is_readable"] = True

        # Check if file is empty
        if full_path.stat().st_size == 0:
            status["is_empty"] = True
            results["empty_files"].append(status)
        else:
            results["valid_files"].append(status)

    # Build summary
    results["summary"] = {
        "total_entries": results["total_entries"],
        "valid_count": len(results["valid_files"]),
        "missing_count": len(results["missing_files"]),
        "unreadable_count": len(results["unreadable_files"]),
        "empty_count": len(results["empty_files"]),
        "validation_success": len(results["missing_files"]) == 0 and len(results["unreadable_files"]) == 0
    }

    return results


def main():
    """Main validation function."""
    print(f"Validating pod inventory: {INVENTORY_FILE}")
    print(f"Workspace root: {WORKSPACE_ROOT}\n")

    if not INVENTORY_FILE.exists():
        print(f"ERROR: Inventory file not found: {INVENTORY_FILE}")
        return 1

    results = validate_inventory(INVENTORY_FILE)

    # Print summary
    summary = results["summary"]
    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total entries:              {summary['total_entries']}")
    print(f"Valid files:                {summary['valid_count']}")
    print(f"Missing files:              {summary['missing_count']}")
    print(f"Unreadable files:            {summary['unreadable_count']}")
    print(f"Empty files:                 {summary['empty_count']}")
    print(f"Validation success:          {summary['validation_success']}")
    print("=" * 60)

    # Print missing files
    if results["missing_files"]:
        print(f"\n❌ MISSING FILES ({len(results['missing_files'])}):")
        for f in results["missing_files"]:
            print(f"  - {f['pod_name']} ({f['namespace']}): {f['log_file_path']}")
            print(f"    Error: {f['error']}")

    # Print unreadable files
    if results["unreadable_files"]:
        print(f"\n❌ UNREADABLE FILES ({len(results['unreadable_files'])}):")
        for f in results["unreadable_files"]:
            print(f"  - {f['pod_name']} ({f['namespace']}): {f['log_file_path']}")
            print(f"    Error: {f['error']}")

    # Print empty files (informational, not an error)
    if results["empty_files"]:
        print(f"\n⚠️  EMPTY FILES ({len(results['empty_files'])}):")
        for f in results["empty_files"]:
            print(f"  - {f['pod_name']} ({f['namespace']}): {f['log_file_path']}")

    # Print valid files sample
    if results["valid_files"]:
        print(f"\n✓ VALID FILES ({len(results['valid_files'])}):")
        for f in results["valid_files"][:5]:  # Show first 5
            print(f"  - {f['pod_name']} ({f['namespace']}): {f['log_file_path']} ({f['file_size_bytes']} bytes)")
        if len(results["valid_files"]) > 5:
            print(f"  ... and {len(results['valid_files']) - 5} more")

    # Save detailed results
    output_file = WORKSPACE_ROOT / "tmp" / "pod-logs-validation-results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nDetailed results saved to: {output_file}")

    # Return exit code
    return 0 if summary["validation_success"] else 1


if __name__ == "__main__":
    exit(main())
