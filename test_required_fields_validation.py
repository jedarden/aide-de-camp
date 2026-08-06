#!/usr/bin/env python3
"""
Test the required fields validation functionality.

Tests validate_required_fields function with various scenarios.
"""

import sys
from pathlib import Path

# Add the deployment-data directory to the path to import the validation function
sys.path.insert(0, str(Path(__file__).parent / "docs/research/deployment-data"))

from validate_deployment_file import validate_required_fields, map_deployment_to_standard_format


def test_missing_required_field():
    """Test validation with missing required field."""
    print("Test 1: Missing required field")
    deployments = [
        {
            "date": "2026-07-13T18:07:55Z",
            "environment": "production",
            "region": "us-east-1",
            "deployment_id": "deploy-123",
            # Missing "status"
        }
    ]

    is_valid, errors = validate_required_fields(deployments)

    assert not is_valid, "Expected validation to fail with missing status field"
    assert len(errors) == 1, f"Expected 1 error, got {len(errors)}"
    assert "Missing required field status" in errors[0], f"Unexpected error message: {errors[0]}"
    print("  ✓ Correctly detected missing status field")


def test_all_required_fields_present():
    """Test validation with all required fields present."""
    print("\nTest 2: All required fields present")
    deployments = [
        {
            "date": "2026-07-13T18:07:55Z",
            "environment": "production",
            "region": "us-east-1",
            "deployment_id": "deploy-123",
            "status": "success"
        }
    ]

    is_valid, errors = validate_required_fields(deployments)

    assert is_valid, "Expected validation to pass with all fields present"
    assert len(errors) == 0, f"Expected no errors, got {errors}"
    print("  ✓ Correctly validated entry with all required fields")


def test_multiple_entries_with_missing_fields():
    """Test validation collects all errors across multiple entries."""
    print("\nTest 3: Multiple entries with missing fields")
    deployments = [
        {
            "date": "2026-07-13T18:07:55Z",
            "environment": "production",
            # Missing "region", "deployment_id", "status"
        },
        {
            "date": "2026-07-13T18:18:07Z",
            "environment": "staging",
            "region": "us-west-2",
            "deployment_id": "deploy-456",
            # Missing "status"
        }
    ]

    is_valid, errors = validate_required_fields(deployments)

    assert not is_valid, "Expected validation to fail with missing fields"
    assert len(errors) == 4, f"Expected 4 errors (3 in first entry, 1 in second), got {len(errors)}"
    print(f"  ✓ Correctly collected {len(errors)} errors across entries:")
    for error in errors:
        print(f"    • {error}")


def test_deployment_mapping():
    """Test the mapping function from deployment data to standard format."""
    print("\nTest 4: Deployment data mapping")

    deployment = {
        "timestamp": "2026-07-13T18:07:55Z",
        "status": "success",
        "revision": 14,
        "replicaSet": "pbx-web-5ff68464d"
    }

    metadata = {
        "service": "pbx-web",
        "namespace": "pbx-web",
        "cluster": "ardenone-cluster"
    }

    standard_entry = map_deployment_to_standard_format(deployment, metadata)

    # Verify all required fields are present
    assert "date" in standard_entry, "Missing 'date' field"
    assert "environment" in standard_entry, "Missing 'environment' field"
    assert "region" in standard_entry, "Missing 'region' field"
    assert "deployment_id" in standard_entry, "Missing 'deployment_id' field"
    assert "status" in standard_entry, "Missing 'status' field"

    # Verify field mappings
    assert standard_entry["date"] == "2026-07-13T18:07:55Z", "Incorrect date mapping"
    assert "pbx-web" in standard_entry["environment"], "Incorrect environment mapping"
    assert standard_entry["region"] == "ardenone-cluster", "Incorrect region mapping"
    assert standard_entry["deployment_id"] == "pbx-web-5ff68464d", "Incorrect deployment_id mapping"
    assert standard_entry["status"] == "success", "Incorrect status mapping"

    print("  ✓ Deployment data correctly mapped to standard format")
    print(f"    • date: {standard_entry['date']}")
    print(f"    • environment: {standard_entry['environment']}")
    print(f"    • region: {standard_entry['region']}")
    print(f"    • deployment_id: {standard_entry['deployment_id']}")
    print(f"    • status: {standard_entry['status']}")


def test_integration_with_real_data():
    """Test validation with real deployment data structure."""
    print("\nTest 5: Integration with real deployment data structure")

    # Simulate the structure from pbx-web-deployments.json
    deployment_data = {
        "service": "pbx-web",
        "namespace": "pbx-web",
        "cluster": "ardenone-cluster",
        "deployments": [
            {
                "timestamp": "2026-07-13T18:07:55Z",
                "image_tag": "1.0.8",
                "status": "failed",
                "duration_seconds": None,
                "revision": 11,
                "replicaSet": "pbx-web-754f4cfdf7"
            }
        ]
    }

    metadata = {
        "service": deployment_data["service"],
        "namespace": deployment_data["namespace"],
        "cluster": deployment_data["cluster"]
    }

    standard_deployments = [
        map_deployment_to_standard_format(deployment, metadata)
        for deployment in deployment_data["deployments"]
    ]

    is_valid, errors = validate_required_fields(standard_deployments)

    assert is_valid, f"Expected validation to pass for real deployment data, got errors: {errors}"
    print("  ✓ Real deployment data structure validated successfully")


def main():
    """Run all tests."""
    print("=" * 70)
    print("TESTING REQUIRED FIELDS VALIDATION")
    print("=" * 70)

    try:
        test_missing_required_field()
        test_all_required_fields_present()
        test_multiple_entries_with_missing_fields()
        test_deployment_mapping()
        test_integration_with_real_data()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
