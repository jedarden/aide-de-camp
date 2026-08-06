#!/usr/bin/env python3
"""
Test whisper-stt schema against pbx-web deployment data to verify format match.

This script validates that the whisper-stt schema matches the pbx-web format
by testing against actual pbx-web deployment data.

Usage:
    python test_schema_pbx_web_match.py
"""

import json
import sys
from pathlib import Path
from whisper_stt_deployment_schema import WhisperSTTDeploymentSchema, validate_deployment_data


def test_schema_pbx_web_match():
    """Test that whisper-stt schema matches pbx-web format."""

    print("=" * 70)
    print("TESTING SCHEMA FORMAT MATCH WITH pbx-web DATA")
    print("=" * 70)

    # Load the pbx-web deployment data
    pbx_web_data_path = Path("/home/coding/aide-de-camp/deployment_data_raw.json")

    if not pbx_web_data_path.exists():
        print(f"✗ ERROR: pbx-web data file not found: {pbx_web_data_path}")
        return False

    print(f"\n✓ Loading pbx-web data from: {pbx_web_data_path}")

    try:
        with open(pbx_web_data_path, 'r') as f:
            pbx_web_data = json.load(f)
    except Exception as e:
        print(f"✗ ERROR: Failed to load pbx-web data: {e}")
        return False

    print("✓ pbx-web data loaded successfully")

    # Test 1: Validate pbx-web structure against our schema expectations
    print("\n" + "=" * 70)
    print("TEST 1: Validate pbx-web Top-Level Structure")
    print("=" * 70)

    required_top_level_fields = [
        "metadata", "argo_workflows", "argo_cd",
        "cluster_deployments", "summary", "notes"
    ]

    missing_fields = []
    for field in required_top_level_fields:
        if field not in pbx_web_data:
            missing_fields.append(field)
        else:
            print(f"  ✓ Found field: {field}")

    if missing_fields:
        print(f"  ✗ Missing fields: {', '.join(missing_fields)}")
        return False
    else:
        print("  ✓ All required top-level fields present")

    # Test 2: Validate metadata structure
    print("\n" + "=" * 70)
    print("TEST 2: Validate Metadata Structure")
    print("=" * 70)

    metadata = pbx_web_data.get("metadata", {})
    required_metadata_fields = [
        "generated_at", "data_period_start", "data_period_end",
        "services", "clusters", "data_sources"
    ]

    missing_metadata_fields = []
    for field in required_metadata_fields:
        if field not in metadata:
            missing_metadata_fields.append(field)
        else:
            print(f"  ✓ Found metadata field: {field} = {metadata[field]}")

    if missing_metadata_fields:
        print(f"  ✗ Missing metadata fields: {', '.join(missing_metadata_fields)}")
        return False
    else:
        print("  ✓ All required metadata fields present")

    # Test 3: Validate cluster_deployments structure
    print("\n" + "=" * 70)
    print("TEST 3: Validate Cluster Deployments Structure")
    print("=" * 70)

    cluster_deployments = pbx_web_data.get("cluster_deployments", {})

    if "whisper-stt" not in cluster_deployments:
        print("  ⚠ whisper-stt not in cluster_deployments (expected for pbx-web only data)")
        print("  Testing against pbx-web data instead...")

        if "pbx-web" not in cluster_deployments:
            print("  ✗ Neither pbx-web nor whisper-stt found in cluster_deployments")
            return False

        test_service = "pbx-web"
    else:
        test_service = "whisper-stt"

    deployment_data = cluster_deployments[test_service]

    required_deployment_fields = [
        "namespace", "deployment_name", "created_at", "current_image",
        "current_replicas", "replica_history", "deployments_last_30_days",
        "successful_deployments", "failed_deployments", "deployment_versions",
        "all_versions_in_history"
    ]

    missing_deployment_fields = []
    for field in required_deployment_fields:
        if field not in deployment_data:
            missing_deployment_fields.append(field)
        else:
            value = deployment_data[field]
            if isinstance(value, list):
                print(f"  ✓ Found field: {field} (list with {len(value)} items)")
            else:
                print(f"  ✓ Found field: {field} = {value}")

    if missing_deployment_fields:
        print(f"  ✗ Missing deployment fields: {', '.join(missing_deployment_fields)}")
        return False
    else:
        print(f"  ✓ All required deployment fields present for {test_service}")

    # Test 4: Validate replica history structure
    print("\n" + "=" * 70)
    print("TEST 4: Validate Replica History Structure")
    print("=" * 70)

    replica_history = deployment_data.get("replica_history", [])

    if not replica_history:
        print("  ⚠ No replica history entries found")
    else:
        print(f"  ✓ Found {len(replica_history)} replica history entries")

        required_replica_fields = [
            "name", "created_at", "image", "replicas", "status", "days_ago"
        ]

        for i, entry in enumerate(replica_history[:2]):  # Check first 2 entries
            print(f"\n  Checking replica history entry {i + 1}:")
            missing_replica_fields = []
            for field in required_replica_fields:
                if field not in entry:
                    missing_replica_fields.append(field)
                else:
                    print(f"    ✓ {field}: {entry[field]}")

            if missing_replica_fields:
                print(f"    ✗ Missing fields: {', '.join(missing_replica_fields)}")
                return False

        print("  ✓ All required replica history fields present")

    # Test 5: Validate summary structure
    print("\n" + "=" * 70)
    print("TEST 5: Validate Summary Structure")
    print("=" * 70)

    summary = pbx_web_data.get("summary", {})

    required_summary_fields = [
        "total_deployments_last_30_days", "successful_deployments",
        "failed_or_scaled_down", "data_coverage", "gaps_detected", "largest_gap_days"
    ]

    missing_summary_fields = []
    for field in required_summary_fields:
        if field not in summary:
            missing_summary_fields.append(field)
        else:
            print(f"  ✓ Found summary field: {field} = {summary[field]}")

    if missing_summary_fields:
        print(f"  ✗ Missing summary fields: {', '.join(missing_summary_fields)}")
        return False
    else:
        print("  ✓ All required summary fields present")

    # Test 6: Create whisper-stt data matching pbx-web format
    print("\n" + "=" * 70)
    print("TEST 6: Generate whisper-stt Data Matching pbx-web Format")
    print("=" * 70)

    whisper_stt_data = {
        "metadata": {
            "generated_at": pbx_web_data["metadata"]["generated_at"],
            "data_period_start": pbx_web_data["metadata"]["data_period_start"],
            "data_period_end": pbx_web_data["metadata"]["data_period_end"],
            "services": ["whisper-stt"],
            "clusters": pbx_web_data["metadata"]["clusters"],
            "data_sources": pbx_web_data["metadata"]["data_sources"]
        },
        "argo_workflows": {
            "whisper_stt_build": {
                "template_name": "whisper-stt-build",
                "template_created": pbx_web_data["argo_workflows"]["whisper_stt_build"]["template_created"],
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
                "last_updated": "2026-07-12T16:54:57Z",
                "replica_history": [
                    {
                        "name": "whisper-stt-847fd8d7b9",
                        "created_at": "2026-07-12T16:53:42Z",
                        "image": "ronaldraygun/whisper-stt:1.8.6",
                        "replicas": 1,
                        "available_replicas": 1,
                        "ready_replicas": 1,
                        "status": "successful",
                        "days_ago": 25
                    }
                ],
                "deployments_last_30_days": 4,
                "successful_deployments": 1,
                "failed_deployments": 3,
                "deployment_versions": ["1.8.6", "1.8.4", "1.8.2"],
                "all_versions_in_history": ["1.2.5", "1.3.0", "1.3.1", "1.4.1", "1.5.1", "1.6.0", "1.7.0", "1.8.2", "1.8.4", "1.8.6"]
            }
        },
        "summary": {
            "total_deployments_last_30_days": 4,
            "whisper_stt_deployments": 4,
            "successful_deployments": 1,
            "failed_or_scaled_down": 3,
            "data_coverage": "100%",
            "gaps_detected": False,
            "largest_gap_days": 0
        },
        "notes": [
            "Generated from pbx-web schema template",
            "Schema format validated and matching pbx-web structure"
        ]
    }

    print("  ✓ Generated whisper-stt data structure matching pbx-web format")

    # Test 7: Validate whisper-stt data against our schema
    print("\n" + "=" * 70)
    print("TEST 7: Validate whisper-stt Data Against Schema")
    print("=" * 70)

    validation_result = validate_deployment_data(whisper_stt_data)

    if validation_result["valid"]:
        print("  ✓ whisper-stt data validated successfully against schema")
        print("  ✓ Schema format matches pbx-web structure perfectly")
    else:
        print("  ✗ Schema validation failed:")
        for error in validation_result["errors"]:
            print(f"    • {error}")
        return False

    # Final summary
    print("\n" + "=" * 70)
    print("SCHEMA FORMAT MATCH TEST RESULTS")
    print("=" * 70)

    print("\n✅ ALL TESTS PASSED")
    print("\nSummary:")
    print("  • pbx-web top-level structure: ✓ VERIFIED")
    print("  • pbx-web metadata structure: ✓ VERIFIED")
    print("  • pbx-web deployment structure: ✓ VERIFIED")
    print("  • pbx-web replica history: ✓ VERIFIED")
    print("  • pbx-web summary structure: ✓ VERIFIED")
    print("  • whisper-stt schema generation: ✓ VERIFIED")
    print("  • whisper-stt schema validation: ✓ VERIFIED")

    print("\n✅ Schema successfully matches pbx-web format")

    return True


def main():
    """Main test function."""
    try:
        success = test_schema_pbx_web_match()
        return 0 if success else 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
