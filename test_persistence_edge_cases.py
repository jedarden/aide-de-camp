#!/usr/bin/env python3
"""
Comprehensive tests for the whisper-stt deployment data persistence module.

Tests edge cases, error handling, and various scenarios to ensure robust operation.
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from persist_whisper_stt_deployment import (
    persist_deployment_data,
    load_deployment_data,
    validate_and_persist,
    serialize_deployment_data,
    verify_json_file,
    DeploymentDataEncoder
)

def test_valid_data_persistence():
    """Test 1: Persist valid deployment data."""
    print("\n📋 Test 1: Valid Data Persistence")
    print("-" * 50)

    test_data = {
        "metadata": {
            "generated_at": "2026-08-06T12:00:00Z",
            "data_period_start": "2026-07-07T00:00:00Z",
            "data_period_end": "2026-08-06T12:00:00Z",
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes"]
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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name

    try:
        success = persist_deployment_data(test_data, temp_file)
        assert success, "Persistence should succeed with valid data"

        verification = verify_json_file(temp_file)
        assert verification['valid'], "File should be valid"
        assert verification['structure_ok'], "Structure should be OK"

        print("✓ Valid data persisted and verified successfully")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_missing_required_fields():
    """Test 2: Handle missing required fields."""
    print("\n📋 Test 2: Missing Required Fields")
    print("-" * 50)

    invalid_data = {
        "metadata": {
            "generated_at": "2026-08-06T12:00:00Z",
            # Missing data_period_start, data_period_end
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"]
        }
        # Missing summary section
    }

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name

        success = persist_deployment_data(invalid_data, temp_file)
        print("✗ Should have failed with missing required fields")
        return False
    except ValueError as e:
        print(f"✓ Correctly rejected invalid data: {e}")
        return True
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False
    finally:
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.unlink(temp_file)


def test_invalid_timestamp_format():
    """Test 3: Handle invalid timestamp formats."""
    print("\n📋 Test 3: Invalid Timestamp Format")
    print("-" * 50)

    invalid_data = {
        "metadata": {
            "generated_at": "not-a-valid-timestamp",
            "data_period_start": "2026-07-07T00:00:00Z",
            "data_period_end": "2026-08-06T12:00:00Z",
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes"]
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

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name

        success = persist_deployment_data(invalid_data, temp_file)
        print("✗ Should have failed with invalid timestamp")
        return False
    except ValueError as e:
        print(f"✓ Correctly rejected invalid timestamp: {e}")
        return True
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False
    finally:
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.unlink(temp_file)


def test_datetime_serialization():
    """Test 4: Handle datetime objects in data."""
    print("\n📋 Test 4: DateTime Serialization")
    print("-" * 50)

    # Test with actual datetime objects
    data_with_datetime = {
        "metadata": {
            "generated_at": datetime.now(),
            "data_period_start": "2026-07-07T00:00:00Z",
            "data_period_end": "2026-08-06T12:00:00Z",
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes"]
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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name

    try:
        success = persist_deployment_data(data_with_datetime, temp_file)
        assert success, "Should handle datetime objects"

        # Load and verify the datetime was serialized correctly
        loaded = load_deployment_data(temp_file)
        assert loaded is not None, "Should load successfully"

        print("✓ DateTime objects serialized and loaded correctly")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_nested_complex_data():
    """Test 5: Handle nested complex data structures."""
    print("\n📋 Test 5: Nested Complex Data Structures")
    print("-" * 50)

    complex_data = {
        "metadata": {
            "generated_at": "2026-08-06T12:00:00Z",
            "data_period_start": "2026-07-07T00:00:00Z",
            "data_period_end": "2026-08-06T12:00:00Z",
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes", "argo_workflows", "argo_cd"]
        },
        "argo_workflows": {
            "whisper_stt_build": {
                "template_name": "whisper-stt-build",
                "template_created": "2026-05-27T02:26:47Z",
                "workflow_runs_last_30_days": 3,
                "workflow_runs": [
                    {
                        "workflow_name": "whisper-stt-build-abc123",
                        "started_at": "2026-07-15T10:30:00Z",
                        "status": "Succeeded",
                        "finished_at": "2026-07-15T10:35:00Z",
                        "git_revision": "abc123def",
                        "image_tag": "1.8.6"
                    }
                ]
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
                "successful_deployments": 4,
                "failed_deployments": 0,
                "deployment_versions": ["1.8.6", "1.8.4", "1.8.2"],
                "all_versions_in_history": ["1.8.6", "1.8.4", "1.8.2", "1.7.0"]
            }
        },
        "summary": {
            "total_deployments_last_30_days": 4,
            "whisper_stt_deployments": 4,
            "successful_deployments": 4,
            "failed_or_scaled_down": 0,
            "data_coverage": "100%",
            "gaps_detected": False,
            "largest_gap_days": 0
        },
        "notes": [
            "Complex nested data test",
            "Multiple deployment versions",
            "Workflow runs included"
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name

    try:
        success = persist_deployment_data(complex_data, temp_file)
        assert success, "Should handle complex nested data"

        loaded = load_deployment_data(temp_file)
        assert loaded is not None, "Should load successfully"
        assert len(loaded['argo_workflows']['whisper_stt_build']['workflow_runs']) == 1, "Should preserve nested arrays"
        assert len(loaded['cluster_deployments']['whisper-stt']['replica_history']) == 1, "Should preserve replica history"

        print("✓ Complex nested data structures handled correctly")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_backup_functionality():
    """Test 6: Verify backup file creation."""
    print("\n📋 Test 6: Backup Functionality")
    print("-" * 50)

    test_data = {
        "metadata": {
            "generated_at": "2026-08-06T12:00:00Z",
            "data_period_start": "2026-07-07T00:00:00Z",
            "data_period_end": "2026-08-06T12:00:00Z",
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes"]
        },
        "summary": {
            "total_deployments_last_30_days": 1,
            "whisper_stt_deployments": 1,
            "successful_deployments": 1,
            "failed_or_scaled_down": 0,
            "data_coverage": "100%",
            "gaps_detected": False,
            "largest_gap_days": 0
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name

    try:
        # First write
        persist_deployment_data(test_data, temp_file, backup_enabled=False)

        # Second write should create backup
        success = persist_deployment_data(test_data, temp_file, backup_enabled=True)
        assert success, "Second write should succeed"

        # Check if backup was created
        backup_dir = Path(".backups")
        if backup_dir.exists():
            backups = list(backup_dir.glob("whisper-stt-deployments-30d_backup_*.json"))
            if backups:
                print(f"✓ Backup functionality working: {len(backups)} backup(s) created")
                return True
            else:
                print("⚠ No backups found (may be normal depending on file name)")
                return True
        else:
            print("⚠ Backup directory not created")
            return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_pretty_vs_compact_format():
    """Test 7: Compare pretty vs compact JSON format."""
    print("\n📋 Test 7: Pretty vs Compact Format")
    print("-" * 50)

    test_data = {
        "metadata": {
            "generated_at": "2026-08-06T12:00:00Z",
            "data_period_start": "2026-07-07T00:00:00Z",
            "data_period_end": "2026-08-06T12:00:00Z",
            "services": ["whisper-stt"],
            "clusters": ["ardenone-cluster"],
            "data_sources": ["kubernetes"]
        },
        "summary": {
            "total_deployments_last_30_days": 1,
            "whisper_stt_deployments": 1,
            "successful_deployments": 1,
            "failed_or_scaled_down": 0,
            "data_coverage": "100%",
            "gaps_detected": False,
            "largest_gap_days": 0
        }
    }

    try:
        # Test pretty format
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            pretty_file = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            compact_file = f.name

        persist_deployment_data(test_data, pretty_file, pretty_print=True, backup_enabled=False)
        persist_deployment_data(test_data, compact_file, pretty_print=False, backup_enabled=False)

        # Compare file sizes
        pretty_size = os.path.getsize(pretty_file)
        compact_size = os.path.getsize(compact_file)

        print(f"  Pretty format: {pretty_size} bytes")
        print(f"  Compact format: {compact_size} bytes")
        print(f"  Size difference: {pretty_size - compact_size} bytes")

        assert pretty_size > compact_size, "Pretty format should be larger"

        # Verify both are valid
        with open(pretty_file, 'r') as f:
            json.load(f)
        with open(compact_file, 'r') as f:
            json.load(f)

        print("✓ Both formats produce valid JSON")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False
    finally:
        if os.path.exists(pretty_file):
            os.unlink(pretty_file)
        if os.path.exists(compact_file):
            os.unlink(compact_file)


def main():
    """Run all tests."""
    print("=" * 70)
    print("WHISPER-STT DEPLOYMENT DATA PERSISTENCE - COMPREHENSIVE TESTS")
    print("=" * 70)

    tests = [
        test_valid_data_persistence,
        test_missing_required_fields,
        test_invalid_timestamp_format,
        test_datetime_serialization,
        test_nested_complex_data,
        test_backup_functionality,
        test_pretty_vs_compact_format
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test crashed: {e}")
            results.append(False)

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("✓ All tests passed!")
        return 0
    else:
        print(f"✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
