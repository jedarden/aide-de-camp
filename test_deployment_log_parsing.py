#!/usr/bin/env python3
"""
Test suite for deployment log parsing functionality.

Tests the parsing functions with various edge cases and data quality scenarios.
"""

import json
import pandas as pd
import tempfile
import os
from datetime import datetime
from pathlib import Path

# Import functions to test
import sys
sys.path.insert(0, '/home/coding/aide-de-camp')
from parse_deployment_logs import (
    parse_pbx_web_deployments,
    parse_whisper_stt_deployments,
    validate_timestamp,
    load_deployment_logs,
    validate_deployment_data
)


def create_test_pbx_web_data():
    """Create test pbx-web deployment data."""
    return {
        "metadata": {
            "service": "pbx-web",
            "namespace": "pbx-web"
        },
        "deployment_events_last_30_days": [
            {"timestamp": "2026-07-13T18:07:55Z", "revision": 10},
            {"timestamp": "2026-07-15T03:24:40Z", "revision": 11},
            {"timestamp": "2026-07-28T17:26:12Z", "revision": 14},
        ]
    }


def create_test_whisper_stt_data():
    """Create test whisper-stt deployment data."""
    return {
        "report_metadata": {
            "service": "whisper-stt"
        },
        "deployment_history_30_days": {
            "replicasets": [
                {"created": "2026-06-14T04:11:57Z", "revision": 28},
                {"created": "2026-07-08T03:09:35Z", "revision": 29},
                {"created": "2026-07-12T16:53:42Z", "revision": 31},
            ]
        }
    }


def create_test_malformed_data():
    """Create test data with missing/invalid timestamps."""
    return {
        "deployment_events_last_30_days": [
            {"timestamp": "2026-07-13T18:07:55Z"},
            {"timestamp": None},  # Missing timestamp
            {"revision": 11},     # No timestamp field
            {"timestamp": "invalid-date"},  # Invalid format
        ]
    }


def test_parse_pbx_web_deployments():
    """Test pbx-web deployment parsing."""
    print("Testing parse_pbx_web_deployments...")

    # Create temporary test file
    test_data = create_test_pbx_web_data()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_file = f.name

    try:
        deployments = parse_pbx_web_deployments(temp_file)

        # Validate results
        assert len(deployments) == 3, f"Expected 3 deployments, got {len(deployments)}"
        assert all(d['service_name'] == 'pbx-web' for d in deployments), "All should be pbx-web"
        assert deployments[0]['deployment_time'] == '2026-07-13T18:07:55Z'

        print("  ✓ Parse pbx-web deployments: PASSED")
        return True
    finally:
        os.unlink(temp_file)


def test_parse_whisper_stt_deployments():
    """Test whisper-stt deployment parsing."""
    print("Testing parse_whisper_stt_deployments...")

    # Create temporary test file
    test_data = create_test_whisper_stt_data()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_file = f.name

    try:
        deployments = parse_whisper_stt_deployments(temp_file)

        # Validate results
        assert len(deployments) == 3, f"Expected 3 deployments, got {len(deployments)}"
        assert all(d['service_name'] == 'whisper-stt' for d in deployments), "All should be whisper-stt"
        assert deployments[0]['deployment_time'] == '2026-06-14T04:11:57Z'

        print("  ✓ Parse whisper-stt deployments: PASSED")
        return True
    finally:
        os.unlink(temp_file)


def test_validate_timestamp():
    """Test timestamp validation function."""
    print("Testing validate_timestamp...")

    # Valid timestamps
    valid_timestamps = [
        "2026-07-13T18:07:55Z",
        "2026-07-13T18:07:55+00:00",
        "2026-07-13T18:07:55.123Z",
        "2026-07-13T18:07:55-05:00",
    ]

    for ts in valid_timestamps:
        assert validate_timestamp(ts), f"Should validate: {ts}"

    # Invalid timestamps
    invalid_timestamps = [
        None,
        "",
        "invalid-date",
        "2026-13-40T25:61:61Z",  # Invalid date/time values
        12345,  # Not a string
    ]

    for ts in invalid_timestamps:
        assert not validate_timestamp(ts), f"Should reject: {ts}"

    print("  ✓ Timestamp validation: PASSED")
    return True


def test_load_deployment_logs():
    """Test loading both services."""
    print("Testing load_deployment_logs...")

    # Create temporary test files
    pbx_data = create_test_pbx_web_data()
    whisper_data = create_test_whisper_stt_data()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(pbx_data, f)
        pbx_file = f.name

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(whisper_data, f)
        whisper_file = f.name

    try:
        df = load_deployment_logs(pbx_file, whisper_file)

        # Validate DataFrame
        assert len(df) == 6, f"Expected 6 total deployments, got {len(df)}"
        assert 'service_name' in df.columns
        assert 'deployment_time' in df.columns
        assert df['service_name'].value_counts()['pbx-web'] == 3
        assert df['service_name'].value_counts()['whisper-stt'] == 3

        print("  ✓ Load deployment logs: PASSED")
        return True
    finally:
        os.unlink(pbx_file)
        os.unlink(whisper_file)


def test_validate_deployment_data():
    """Test data quality validation."""
    print("Testing validate_deployment_data...")

    # Create test DataFrame
    df = pd.DataFrame([
        {'service_name': 'pbx-web', 'deployment_time': pd.Timestamp('2026-07-13T18:07:55Z')},
        {'service_name': 'whisper-stt', 'deployment_time': pd.Timestamp('2026-07-14T04:11:57Z')},
    ])

    is_valid, message = validate_deployment_data(df)
    assert is_valid, f"Valid DataFrame should pass: {message}"

    # Test with null values
    df_invalid = pd.DataFrame([
        {'service_name': 'pbx-web', 'deployment_time': None},
    ])
    df_invalid['deployment_time'] = pd.to_datetime(df_invalid['deployment_time'])

    is_valid, message = validate_deployment_data(df_invalid)
    assert not is_valid, "DataFrame with null deployment_time should fail"

    print("  ✓ Data quality validation: PASSED")
    return True


def test_datetime_conversion():
    """Test datetime conversion and handling of invalid dates."""
    print("Testing datetime conversion...")

    # Test data with some invalid timestamps
    test_data = [
        {'service_name': 'pbx-web', 'deployment_time': '2026-07-13T18:07:55Z'},
        {'service_name': 'pbx-web', 'deployment_time': 'invalid-timestamp'},
        {'service_name': 'whisper-stt', 'deployment_time': '2026-07-14T04:11:57Z'},
    ]

    df = pd.DataFrame(test_data)
    df['deployment_time'] = pd.to_datetime(df['deployment_time'], errors='coerce')

    # Check that valid timestamps converted and invalid became NaT
    assert pd.isna(df.loc[1, 'deployment_time']), "Invalid timestamp should be NaT"
    assert not pd.isna(df.loc[0, 'deployment_time']), "Valid timestamp should convert"
    assert not pd.isna(df.loc[2, 'deployment_time']), "Valid timestamp should convert"

    print("  ✓ Datetime conversion: PASSED")
    return True


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Running Deployment Log Parsing Tests")
    print("=" * 60)
    print()

    tests = [
        test_validate_timestamp,
        test_parse_pbx_web_deployments,
        test_parse_whisper_stt_deployments,
        test_load_deployment_logs,
        test_validate_deployment_data,
        test_datetime_conversion,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"  ✗ {test.__name__}: FAILED - {e}")
            results.append((test.__name__, False))
        print()

    # Summary
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"Test Results: {passed}/{total} passed")
    print("=" * 60)

    return all(r for _, r in results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)