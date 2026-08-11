#!/usr/bin/env python3
"""
Comprehensive deployment schema validation test.

Tests the deployment-data-schema-comprehensive.json schema against
various deployment data scenarios to ensure validation rules work correctly.
"""

import json
from jsonschema import validate, ValidationError
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List


def load_schema() -> Dict[str, Any]:
    """Load the comprehensive deployment schema."""
    with open('deployment-data-schema-comprehensive.json', 'r') as f:
        return json.load(f)


def create_minimal_valid_data() -> Dict[str, Any]:
    """Create minimal deployment data that meets 30-day completeness requirements."""

    # Generate timestamps for 30-day period with 5+ deployment days
    end_time = datetime.now()
    start_time = end_time - timedelta(days=30)

    # Create 5 deployment days with proper spacing
    deployment_days = []
    for i in range(5):
        day_offset = i * 6  # Space deployments every 6 days
        deployment_time = start_time + timedelta(days=day_offset)
        deployment_days.append(deployment_time)

    # Build replica history
    replica_history = []
    for i, deploy_time in enumerate(deployment_days):
        days_ago = (end_time - deploy_time).days
        replica_history.append({
            "name": f"whisper-stt-{i:08d}abcd",
            "created_at": deploy_time.isoformat() + "Z",
            "image": "ronaldraygun/whisper-stt:1.8.6",
            "replicas": 1,
            "available_replicas": 1,
            "ready_replicas": 1,
            "status": "successful",
            "days_ago": days_ago
        })

    return {
        "metadata": {
            "generated_at": end_time.isoformat() + "Z",
            "data_period_start": start_time.isoformat() + "Z",
            "data_period_end": end_time.isoformat() + "Z",
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes_replicasets"]
        },
        "argo_workflows": {
            "whisper_stt_build": {
                "template_name": "whisper-stt-build",
                "template_created": "2026-05-27T02:26:47Z",
                "workflow_runs_last_30_days": 0,
                "workflow_runs": []
            }
        },
        "argo_cd": {
            "whisper-stt": {
                "application_found": False,
                "applications": []
            }
        },
        "cluster_deployments": {
            "whisper-stt": {
                "namespace": "whisper-stt",
                "deployment_name": "whisper-stt",
                "created_at": "2026-05-01T17:26:49Z",
                "current_image": "ronaldraygun/whisper-stt:1.8.6",
                "current_replicas": 1,
                "last_updated": deployment_days[-1].isoformat() + "Z",
                "replica_history": replica_history,
                "deployments_last_30_days": 5,
                "successful_deployments": 5,
                "failed_deployments": 0,
                "deployment_versions": ["1.8.6"],
                "all_versions_in_history": ["1.8.6"]
            }
        },
        "summary": {
            "total_deployments_last_30_days": 5,
            "whisper_stt_deployments": 5,
            "successful_deployments": 5,
            "failed_or_scaled_down": 0,
            "data_coverage": "100%",
            "gaps_detected": False,
            "largest_gap_days": 0
        }
    }


def create_invalid_data_missing_required_field() -> Dict[str, Any]:
    """Create deployment data missing a required field."""
    data = create_minimal_valid_data()
    # Remove required metadata field
    del data["metadata"]["generated_at"]
    return data


def create_invalid_data_insufficient_history() -> Dict[str, Any]:
    """Create deployment data with insufficient replica history (< 5 entries)."""
    data = create_minimal_valid_data()
    # Reduce to only 2 replica history entries
    data["cluster_deployments"]["whisper-stt"]["replica_history"] = \
        data["cluster_deployments"]["whisper-stt"]["replica_history"][:2]
    data["cluster_deployments"]["whisper-stt"]["deployments_last_30_days"] = 2
    data["cluster_deployments"]["whisper-stt"]["successful_deployments"] = 2
    data["summary"]["total_deployments_last_30_days"] = 2
    data["summary"]["whisper_stt_deployments"] = 2
    data["summary"]["successful_deployments"] = 2
    return data


def create_invalid_data_invalid_timestamp() -> Dict[str, Any]:
    """Create deployment data with invalid timestamp format."""
    data = create_minimal_valid_data()
    # Use invalid timestamp format
    data["metadata"]["generated_at"] = "invalid-timestamp"
    return data


def create_invalid_data_negative_metric() -> Dict[str, Any]:
    """Create deployment data with negative metric value."""
    data = create_minimal_valid_data()
    # Set negative replica count
    data["cluster_deployments"]["whisper-stt"]["current_replicas"] = -1
    return data


def create_invalid_data_invalid_status() -> Dict[str, Any]:
    """Create deployment data with invalid status enum value."""
    data = create_minimal_valid_data()
    # Use invalid status
    data["cluster_deployments"]["whisper-stt"]["replica_history"][0]["status"] = "invalid_status"
    return data


def create_valid_data_with_optional_sections() -> Dict[str, Any]:
    """Create deployment data with all optional sections populated."""
    data = create_minimal_valid_data()

    # Add pod health
    data["pod_health"] = {
        "current_pods": [
            {
                "name": "whisper-stt-abc123",
                "created": datetime.now().isoformat() + "Z",
                "age_days": 1,
                "status": "Running",
                "containers": [
                    {
                        "name": "whisper-stt",
                        "image": "ronaldraygun/whisper-stt:1.8.6",
                        "ready": True,
                        "restartCount": 0
                    }
                ],
                "totalRestartCount": 0,
                "node": "node-1"
            }
        ],
        "pod_metrics": {
            "total_pods": 1,
            "running_pods": 1,
            "total_containers": 1,
            "total_restarts": 0,
            "crashloops": 0,
            "oomkills": 0,
            "failed_pods": 0,
            "pending_pods": 0
        }
    }

    # Add resources
    data["resources"] = {
        "whisper-stt": {
            "requests": {
                "cpu": "1",
                "memory": "4Gi"
            },
            "limits": {
                "cpu": "8",
                "memory": "8Gi"
            }
        }
    }

    # Add storage
    data["storage"] = {
        "whisper-model-cache": {
            "capacity": "10Gi",
            "storage_class": "standard",
            "status": "Bound",
            "age_days": 30
        }
    }

    # Add notes
    data["notes"] = [
        "All systems operational",
        "30-day completeness requirements met",
        "No deployment failures in period"
    ]

    return data


def test_validation(test_name: str, data: Dict[str, Any], schema: Dict[str, Any], should_pass: bool):
    """Run a single validation test."""
    print(f"\n{'=' * 70}")
    print(f"TEST: {test_name}")
    print(f"{'=' * 70}")

    try:
        validate(instance=data, schema=schema)
        if should_pass:
            print("✅ PASS: Data validated successfully as expected")
            return True
        else:
            print("❌ FAIL: Data should have failed validation but passed")
            return False
    except ValidationError as e:
        if not should_pass:
            print(f"✅ PASS: Data failed validation as expected")
            print(f"   Error: {e.message}")
            print(f"   Path: {'.'.join(str(p) for p in e.path) if e.path else 'root'}")
            return True
        else:
            print(f"❌ FAIL: Data should have passed validation but failed")
            print(f"   Error: {e.message}")
            print(f"   Path: {'.'.join(str(p) for p in e.path) if e.path else 'root'}")
            return False


def main():
    """Run comprehensive schema validation tests."""
    print("=" * 70)
    print("COMPREHENSIVE DEPLOYMENT SCHEMA VALIDATION TEST SUITE")
    print("=" * 70)

    # Load schema
    schema = load_schema()
    print("✅ Schema loaded successfully")

    # Run tests
    tests = [
        ("Valid: Minimal 30-day completeness data", create_minimal_valid_data(), True),
        ("Valid: Complete data with optional sections", create_valid_data_with_optional_sections(), True),
        ("Invalid: Missing required field (metadata.generated_at)", create_invalid_data_missing_required_field(), False),
        ("Invalid: Insufficient replica history (< 5 entries)", create_invalid_data_insufficient_history(), False),
        ("Invalid: Invalid timestamp format", create_invalid_data_invalid_timestamp(), False),
        ("Invalid: Negative metric value", create_invalid_data_negative_metric(), False),
        ("Invalid: Invalid status enum", create_invalid_data_invalid_status(), False),
    ]

    results = []
    for test_name, test_data, should_pass in tests:
        result = test_validation(test_name, test_data, schema, should_pass)
        results.append((test_name, result))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success rate: {(passed/total)*100:.1f}%")

    if passed == total:
        print("\n✅ All validation tests passed - schema is working correctly")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed - schema needs adjustment")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())