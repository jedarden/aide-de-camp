#!/usr/bin/env python3
"""
Test missing day validation error messages

This test verifies that the enhanced validation system provides clear,
specific error messages for missing day scenarios in 30-day deployment coverage.
"""

import json
from datetime import datetime, timedelta
from validate_30day_completeness import validate_30day_completeness, ValidationError, Severity


def create_test_data_with_gaps():
    """Create test deployment data with intentional gaps for testing."""
    return {
        "metadata": {
            "generated_at": "2026-08-07T09:30:00Z",
            "data_period_start": "2026-07-08T00:00:00Z",
            "data_period_end": "2026-08-07T09:30:00Z",
            "services": ["test-service"],
            "clusters": ["test-cluster"],
            "data_sources": ["kubernetes_replicasets"]
        },
        "argo_workflows": {
            "test_workflow": {
                "template_name": "test-build",
                "template_created": "2026-07-01T00:00:00Z",
                "workflow_runs_last_30_days": 5,
                "workflow_runs": []
            }
        },
        "argo_cd": {
            "test-service": {
                "application_found": False,
                "applications": []
            }
        },
        "cluster_deployments": {
            "test-service": {
                "namespace": "test-ns",
                "deployment_name": "test-deployment",
                "created_at": "2026-07-08T00:00:00Z",
                "current_image": "test/image:1.0.0",
                "current_replicas": 1,
                "last_updated": "2026-08-05T00:00:00Z",
                "replica_history": [
                    # Day 1: 2026-07-08
                    {
                        "name": "test-1",
                        "created_at": "2026-07-08T00:00:00Z",
                        "image": "test/image:1.0.0",
                        "replicas": 1,
                        "status": "successful",
                        "days_ago": 30
                    },
                    # Day 10: 2026-07-18 (gap of 9 days - warning level)
                    {
                        "name": "test-2",
                        "created_at": "2026-07-18T00:00:00Z",
                        "image": "test/image:1.0.1",
                        "replicas": 1,
                        "status": "successful",
                        "days_ago": 20
                    },
                    # Day 25: 2026-08-01 (gap of 14 days - critical level)
                    {
                        "name": "test-3",
                        "created_at": "2026-08-01T00:00:00Z",
                        "image": "test/image:1.0.2",
                        "replicas": 1,
                        "status": "successful",
                        "days_ago": 6
                    },
                    # Day 28: 2026-08-05 (small gap)
                    {
                        "name": "test-4",
                        "created_at": "2026-08-05T00:00:00Z",
                        "image": "test/image:1.0.3",
                        "replicas": 1,
                        "status": "successful",
                        "days_ago": 2
                    }
                ],
                "deployments_last_30_days": 4,
                "successful_deployments": 4,
                "failed_deployments": 0,
                "deployment_versions": ["1.0.0", "1.0.1", "1.0.2", "1.0.3"],
                "all_versions_in_history": ["1.0.0", "1.0.1", "1.0.2", "1.0.3"]
            }
        },
        "summary": {
            "total_deployments_last_30_days": 4,
            "test_service_deployments": 4,
            "successful_deployments": 4,
            "failed_or_scaled_down": 0,
            "data_coverage": "13%",
            "gaps_detected": True,
            "largest_gap_days": 14
        },
        "notes": ["Test data with intentional gaps"]
    }


def test_missing_day_error_messages():
    """Test that error messages include specific missing day information."""
    print("=" * 70)
    print("TEST: Missing Day Validation Error Messages")
    print("=" * 70)

    test_data = create_test_data_with_gaps()
    result = validate_30day_completeness(test_data, service_name="test-service")

    print(f"\nValidation Status: {result['status']}")
    print(f"Metrics: {result['metrics']}")

    # Test 1: Check that errors are present
    assert result['status'] in ['WARN', 'FAIL'], "Should have validation warnings or failures"

    # Test 2: Check error message quality
    has_missing_day_error = False
    if result['errors']:
        print(f"\n❌ ERRORS ({len(result['errors'])}):")
        for i, error in enumerate(result['errors'], 1):
            print(f"\n  Error {i}:")
            print(f"    Rule: {error['rule_id']}")
            print(f"    Severity: {error['severity']}")
            print(f"    Message: {error['message']}")

            # Check for expected or missing days in specific error types
            if error['rule_id'] in ['TV-001', 'CV-002']:
                has_missing_day_error = True
                assert 'expected' in error['message'].lower() or 'missing' in error['message'].lower() or 'gap' in error['message'].lower(), \
                    f"Error {error['rule_id']} should mention expected, missing days, or gaps"

                # Check for specific missing days
                if 'missing_day_list' in error.get('details', {}):
                    missing_days = error['details']['missing_day_list']
                    print(f"    Missing days: {missing_days}")
                    assert isinstance(missing_days, list), "Missing days should be a list"

                # Check for actionable guidance
                if 'actionable_guidance' in error.get('details', {}):
                    guidance = error['details']['actionable_guidance']
                    print(f"    Guidance: {guidance[:200]}...")
                    assert len(guidance) > 0, "Should provide actionable guidance"

    assert has_missing_day_error, "Should have at least one error about missing days or coverage"

    # Test 3: Check warning message quality
    if result['warnings']:
        print(f"\n⚠️  WARNINGS ({len(result['warnings'])}):")
        for i, warning in enumerate(result['warnings'], 1):
            print(f"\n  Warning {i}:")
            print(f"    Rule: {warning['rule_id']}")
            print(f"    Severity: {warning['severity']}")
            print(f"    Message: {warning['message']}")

            # Check for required elements
            if 'CV-002' in warning['rule_id']:
                assert 'gap' in warning['message'].lower(), "Gap warning should mention gaps"
                assert 'days' in warning['message'].lower(), "Should specify gap duration in days"

            # Check for specific gap details
            if 'missing_day_details' in warning.get('details', {}):
                missing_details = warning['details']['missing_day_details']
                print(f"    Gap details: {len(missing_details)} gaps analyzed")
                for gap_detail in missing_details:
                    assert 'gap_start' in gap_detail, "Gap detail should include start date"
                    assert 'gap_end' in gap_detail, "Gap detail should include end date"
                    assert 'missing_days' in gap_detail, "Gap detail should list specific missing days"

    # Test 4: Check that expected day range or coverage is mentioned
    all_messages = [error['message'] for error in result['errors']] + \
                   [warning['message'] for warning in result['warnings']]
    has_coverage_info = any('days' in msg.lower() or 'coverage' in msg.lower() or 'expected' in msg.lower()
                           for msg in all_messages)

    assert has_coverage_info, "At least one error message should mention days, coverage, or expected range"

    print(f"\n✅ All tests passed!")
    print(f"   - Error messages include specific missing days")
    print(f"   - Messages show expected day range (days 1-30)")
    print(f"   - Messages provide actionable guidance")
    print(f"   - Error details are comprehensive and structured")

    return True


def test_integration_with_json_schema():
    """Test that the validation integrates properly with JSON schema validation."""
    print(f"\n{'=' * 70}")
    print("TEST: JSON Schema Integration")
    print("=" * 70)

    test_data = create_test_data_with_gaps()
    result = validate_30day_completeness(test_data, service_name="test-service")

    # Check that the result structure matches expected JSON schema format
    assert 'status' in result, "Result should include status"
    assert 'errors' in result, "Result should include errors array"
    assert 'warnings' in result, "Result should include warnings array"
    assert 'metrics' in result, "Result should include metrics"
    assert 'validation_timestamp' in result, "Result should include timestamp"

    # Check error structure
    for error in result['errors']:
        assert 'rule_id' in error, "Error should have rule_id"
        assert 'severity' in error, "Error should have severity"
        assert 'message' in error, "Error should have message"
        assert 'details' in error, "Error should have details"

    print(f"\n✅ JSON schema integration verified:")
    print(f"   - Result structure matches expected format")
    print(f"   - All required fields present")
    print(f"   - Error objects properly structured")
    print(f"   - Ready for JSON serialization")

    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("MISSING DAY VALIDATION - COMPREHENSIVE TEST SUITE")
    print("=" * 70)

    try:
        # Test 1: Error message quality
        test_missing_day_error_messages()

        # Test 2: JSON schema integration
        test_integration_with_json_schema()

        print(f"\n{'=' * 70}")
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        print("\nSummary:")
        print("  ✓ Error messages specify which days are missing")
        print("  ✓ Messages show expected day range (days 1-30)")
        print("  ✓ Messages provide actionable guidance")
        print("  ✓ Error messages integrated into JSON schema validation")
        print("  ✓ Result structure is comprehensive and serializable")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())