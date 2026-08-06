#!/usr/bin/env python3
"""Validate deployment JSON structure and parseability."""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Dict, Any


def validate_required_fields(deployments: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Validate required fields in deployment entries.

    Args:
        deployments: List of deployment entry dictionaries

    Returns:
        Tuple of (is_valid: bool, errors: List[str])
        - is_valid: True if all required fields are present in all entries
        - errors: List of error messages for missing required fields

    Required fields:
    - date (timestamp): Deployment date/time
    - environment: Deployment environment (e.g., production, staging)
    - region: Deployment region (e.g., us-east-1, eu-west-1)
    - deployment_id: Unique deployment identifier
    - status: Deployment status (success, failed, unknown)
    """
    required_fields = ["date", "environment", "region", "deployment_id", "status"]
    errors = []

    for entry_idx, entry in enumerate(deployments):
        entry_id = entry.get("deployment_id", f"entry_{entry_idx}")

        for field in required_fields:
            if field not in entry:
                errors.append(f"Missing required field {field} in entry {entry_id}")

    is_valid = len(errors) == 0
    return is_valid, errors


def map_deployment_to_standard_format(deployment: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map deployment entry to standard format with required fields.

    Maps existing deployment fields to the standard required field names:
    - timestamp -> date
    - cluster/namespace -> environment
    - cluster -> region
    - replicaSet/deployment -> deployment_id
    - status -> status (unchanged)
    """
    standard_entry = {
        "date": deployment.get("timestamp"),
        "environment": f"{metadata.get('namespace', 'unknown')}/{metadata.get('cluster', 'unknown')}",
        "region": metadata.get("cluster", "unknown"),
        "deployment_id": deployment.get("replicaSet") or deployment.get("deployment") or f"deploy-{deployment.get('revision', 'unknown')}",
        "status": deployment.get("status", "unknown")
    }
    return standard_entry


def validate_deployment_file(filepath: Path, include_required_fields_validation: bool = True) -> bool:
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

        # Test 4.5: Validate required fields (if enabled)
        if include_required_fields_validation:
            print("  ✓ Checking required fields (date, environment, region, deployment_id, status)...")

            # Prepare metadata for field mapping
            metadata = {
                "service": data.get("service", "unknown"),
                "namespace": data.get("namespace", "unknown"),
                "cluster": data.get("cluster", "unknown")
            }

            # Map deployments to standard format and validate required fields
            standard_deployments = [
                map_deployment_to_standard_format(deployment, metadata)
                for deployment in deployments
            ]

            is_valid, errors = validate_required_fields(standard_deployments)

            if not is_valid:
                print("  ✗ Required fields validation failed:")
                for error in errors:
                    print(f"    • {error}")
                return False
            else:
                print("  ✓ All required fields present in all deployment entries")

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
