#!/usr/bin/env python3
"""Validate deployment JSON structure and parseability."""

import json
import sys
from pathlib import Path
from datetime import datetime


def validate_deployment_file(filepath: Path) -> bool:
    """Validate a deployment JSON file."""
    print(f"\nValidating {filepath.name}...")

    try:
        # Test 1: Parse JSON
        with open(filepath, "r") as f:
            data = json.load(f)
        print("  ✓ JSON is parseable")

        # Test 2: Check required top-level fields
        required_fields = ["service", "namespace", "cluster", "deployments"]
        for field in required_fields:
            if field not in data:
                print(f"  ✗ Missing required field: {field}")
                return False
        print("  ✓ All required top-level fields present")

        # Test 3: Validate deployments array structure
        deployments = data["deployments"]
        if not isinstance(deployments, list):
            print("  ✗ 'deployments' must be an array")
            return False

        print(f"  ✓ Found {len(deployments)} deployment records")

        # Test 4: Validate each deployment record has required fields
        required_record_fields = ["timestamp", "image_tag", "status", "duration_seconds"]
        for i, deployment in enumerate(deployments):
            for field in required_record_fields:
                if field not in deployment:
                    print(f"  ✗ Deployment {i} missing field: {field}")
                    return False

            # Validate status values
            if deployment["status"] not in ["success", "failed", "unknown"]:
                print(f"  ✗ Deployment {i} has invalid status: {deployment['status']}")
                return False

            # Validate timestamp format (ISO 8601)
            try:
                datetime.fromisoformat(deployment["timestamp"].replace("Z", "+00:00"))
            except ValueError as e:
                print(f"  ✗ Deployment {i} has invalid timestamp: {deployment['timestamp']}")
                return False

        print("  ✓ All deployment records have valid structure")

        # Test 5: Check status mapping
        success_count = sum(1 for d in deployments if d["status"] == "success")
        failed_count = sum(1 for d in deployments if d["status"] == "failed")
        unknown_count = sum(1 for d in deployments if d["status"] == "unknown")

        print(f"  ✓ Status breakdown: {success_count} success, {failed_count} failed, {unknown_count} unknown")

        # Test 6: Check for duration_seconds (should be number or null)
        for i, deployment in enumerate(deployments):
            duration = deployment["duration_seconds"]
            if duration is not None and not isinstance(duration, (int, float)):
                print(f"  ✗ Deployment {i} has invalid duration_seconds type: {type(duration)}")
                return False

        print("  ✓ duration_seconds field valid (number or null)")

        return True

    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parsing failed: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Validation failed: {e}")
        return False


def main():
    base_dir = Path("/home/coding/aide-de-camp/docs/research/deployment-data")

    files_to_validate = [
        base_dir / "pbx-web-deployments.json",
        base_dir / "whisper-stt-deployments.json"
    ]

    all_valid = True
    for filepath in files_to_validate:
        if not filepath.exists():
            print(f"\n✗ File not found: {filepath}")
            all_valid = False
            continue

        if not validate_deployment_file(filepath):
            all_valid = False

    if all_valid:
        print("\n✅ All validation checks passed!")
        return 0
    else:
        print("\n❌ Some validation checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
