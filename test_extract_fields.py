#!/usr/bin/env python3
"""
Test script for extract_fields() function.

Tests field extraction and normalization with sample pbx-web log entries.
"""

import sys
sys.path.insert(0, '/home/coding/aide-de-camp')

from src.parse_log import extract_fields, normalize_timestamp


def test_normalize_timestamp():
    """Test timestamp normalization."""
    print("=" * 70)
    print("Testing timestamp normalization")
    print("=" * 70)

    test_cases = [
        # (input, expected_output)
        (1754768400, "2026-08-06T20:20:00Z"),
        ("1754768400", "2026-08-06T20:20:00Z"),
        ("2026-08-06T12:30:45Z", "2026-08-06T12:30:45Z"),
        ("2026-08-06T12:30:45+00:00", "2026-08-06T12:30:45Z"),
        (None, None),
        ("invalid", None),
    ]

    for input_val, expected in test_cases:
        result = normalize_timestamp(input_val)
        status = "✓" if result == expected else "✗"
        print(f"{status} normalize_timestamp({input_val!r}) = {result!r} (expected {expected!r})")


def test_extract_fields_pod_info():
    """Test extraction from pod_info entry."""
    print("\n" + "=" * 70)
    print("Testing pod_info entry extraction")
    print("=" * 70)

    raw_entry = {
        "pod_name": "pbx-web-5ff68464d-mkn8n",
        "age_days": 8,
        "restart_count": 0,
        "image": "ronaldraygun/pbx-web:1.0.9",
        "status": "running",
        "health_status": "All pods running with 0 restarts"
    }

    result = extract_fields(raw_entry)

    print(f"Input: {raw_entry}")
    print(f"\nOutput:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    # Verify expected values
    assert result['service'] == 'pbx-web', "Service should be pbx-web"
    assert result['event_type'] == 'pod_info', "Event type should be pod_info"
    assert result['status'] == 'success', "Status should be success for running pod"
    assert result['error_code'] is None, "Error code should be None for healthy pod"
    assert result['duration_ms'] == 8 * 24 * 60 * 60 * 1000, "Duration should be 8 days in ms"
    assert result['metadata']['raw_entry_type'] == 'pod_info'

    print("\n✓ pod_info extraction test passed")


def test_extract_fields_error():
    """Test extraction from error entry."""
    print("\n" + "=" * 70)
    print("Testing error entry extraction")
    print("=" * 70)

    raw_entry = {
        "error_type": "connection_refused",
        "error_pattern": "Error: connection refused",
        "severity": "intermittent",
        "context": "Database connection failure"
    }

    result = extract_fields(raw_entry)

    print(f"Input: {raw_entry}")
    print(f"\nOutput:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    # Verify expected values
    assert result['event_type'] == 'error', "Event type should be error"
    assert result['status'] == 'warning', "Status should be warning for intermittent error"
    assert result['error_code'] == 'connection_refused', "Error code should match error_type"

    print("\n✓ error entry extraction test passed")


def test_extract_fields_deployment():
    """Test extraction from deployment entry."""
    print("\n" + "=" * 70)
    print("Testing deployment entry extraction")
    print("=" * 70)

    raw_entry = {
        "metric_type": "deployment_history",
        "current_deployment_age_days": 15,
        "pbx_web_replica_sets": 3,
        "oldest_replica_set_age_days": 25
    }

    result = extract_fields(raw_entry)

    print(f"Input: {raw_entry}")
    print(f"\nOutput:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    # Verify expected values
    assert result['event_type'] == 'deployment', "Event type should be deployment"
    assert result['duration_ms'] == 15 * 24 * 60 * 60 * 1000, "Duration should be current_deployment_age_days"

    print("\n✓ deployment entry extraction test passed")


def test_extract_fields_metadata():
    """Test extraction from metadata entry."""
    print("\n" + "=" * 70)
    print("Testing metadata entry extraction")
    print("=" * 70)

    raw_entry = {
        "namespace": "pbx-web",
        "cluster": "ardenone-cluster",
        "data_collection_timestamp": "2026-08-06T12:30:45Z",
        "analysis_period": "30 days"
    }

    result = extract_fields(raw_entry)

    print(f"Input: {raw_entry}")
    print(f"\nOutput:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    # Verify expected values
    assert result['event_type'] == 'metadata', "Event type should be metadata"
    assert result['timestamp'] == "2026-08-06T12:30:45Z", "Timestamp should be normalized"
    assert result['namespace'] == 'pbx-web', "Namespace should match"

    print("\n✓ metadata entry extraction test passed")


def test_extract_fields_unknown():
    """Test extraction from unknown entry type."""
    print("\n" + "=" * 70)
    print("Testing unknown entry extraction")
    print("=" * 70)

    raw_entry = {
        "some_field": "some_value",
        "another_field": 123
    }

    result = extract_fields(raw_entry)

    print(f"Input: {raw_entry}")
    print(f"\nOutput:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    # Verify expected values
    assert result['event_type'] == 'unknown', "Event type should be unknown"
    assert result['status'] == 'unknown', "Status should be unknown for unknown entries"

    print("\n✓ unknown entry extraction test passed")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("EXTRACT_FIELDS() TEST SUITE")
    print("=" * 70)

    try:
        test_normalize_timestamp()
        test_extract_fields_pod_info()
        test_extract_fields_error()
        test_extract_fields_deployment()
        test_extract_fields_metadata()
        test_extract_fields_unknown()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        return 0

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
