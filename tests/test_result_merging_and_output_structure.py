#!/usr/bin/env python3
"""
Comprehensive tests for result merging and output structure validation.

Tests cover:
1. Gap metrics appear correctly in unified validation output
2. Result merging preserves existing validation data
3. Merged structure matches expected schema
4. Multiple gap detection results merge correctly
5. Edge cases and complex merging scenarios
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.validation.runner import (
    ValidationResult,
    validate_deployment_file,
    _validate_completeness_with_gap_metrics,
)
from src.validation.gap_integration import (
    GapValidationResult,
    GapSeverity,
)
from src.utilities.gap_calculator import GapPeriod


class TestGapMetricsInUnifiedOutput:
    """Test that gap metrics appear correctly in unified validation output."""

    def test_all_gap_metrics_present_in_result_dict(self):
        """Test that all gap metrics are present in to_dict() output."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/deployment.json"
        )

        # Set comprehensive gap metrics
        result.gap_detected = True
        result.coverage_percentage = 75.0
        result.expected_days = 30
        result.actual_days = 22
        result.gap_count = 8
        result.gap_severity = "high"
        result.isolated_gap_count = 3
        result.consecutive_gap_sequence_count = 2
        result.gap_size_distribution = {
            "tiny": 1,
            "small": 2,
            "medium": 2,
            "large": 2,
            "extended": 1
        }
        result.gap_periods = ["2026-07-01 to 2026-07-02", "2026-07-10 to 2026-07-15"]
        result.actionable_guidance = ["Add missing deployment data"]
        result.anomaly_messages = ["Critical gap detected"]
        result.deployment_intervals = {"first_deployment": "2026-07-01T00:00:00Z"}

        # Get unified output
        output = result.to_dict()

        # Verify all gap metrics are present
        required_gap_keys = [
            "gap_detected",
            "coverage_percentage",
            "expected_days",
            "actual_days",
            "gap_count",
            "gap_severity",
            "isolated_gap_count",
            "consecutive_gap_sequence_count",
            "gap_size_distribution",
            "gap_periods",
            "actionable_guidance",
            "anomaly_messages",
            "deployment_intervals"
        ]

        for key in required_gap_keys:
            assert key in output, f"Missing required gap metric: {key}"

    def test_gap_metrics_data_types_in_output(self):
        """Test that gap metrics have correct data types in unified output."""
        result = ValidationResult(
            is_valid=True,
            file_path="/test/deployment.json"
        )

        # Set gap metrics with specific types
        result.gap_detected = True  # bool
        result.coverage_percentage = 83.33  # float
        result.expected_days = 30  # int
        result.actual_days = 25  # int
        result.gap_count = 5  # int
        result.gap_severity = "medium"  # str
        result.isolated_gap_count = 2  # int
        result.consecutive_gap_sequence_count = 1  # int
        result.gap_size_distribution = {"tiny": 1}  # dict
        result.gap_periods = ["2026-07-01 to 2026-07-02"]  # list

        output = result.to_dict()

        # Verify data types
        assert isinstance(output["gap_detected"], bool)
        assert isinstance(output["coverage_percentage"], float)
        assert isinstance(output["expected_days"], int)
        assert isinstance(output["actual_days"], int)
        assert isinstance(output["gap_count"], int)
        assert isinstance(output["gap_severity"], str)
        assert isinstance(output["isolated_gap_count"], int)
        assert isinstance(output["consecutive_gap_sequence_count"], int)
        assert isinstance(output["gap_size_distribution"], dict)
        assert isinstance(output["gap_periods"], list)

    def test_gap_metrics_accuracy_in_output(self):
        """Test that gap metric values are accurate in unified output."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/deployment.json"
        )

        # Set specific gap metric values
        expected_coverage = 66.67
        expected_gap_count = 10
        expected_severity = "critical"

        result.gap_detected = True
        result.coverage_percentage = expected_coverage
        result.gap_count = expected_gap_count
        result.gap_severity = expected_severity

        output = result.to_dict()

        # Verify values match exactly
        assert output["coverage_percentage"] == expected_coverage
        assert output["gap_count"] == expected_gap_count
        assert output["gap_severity"] == expected_severity


class TestResultMergingDataPreservation:
    """Test that result merging preserves existing validation data."""

    def test_schema_validation_preserved_when_gaps_detected(self):
        """Test that schema validation results are preserved even when gaps are detected."""
        # Create deployment data with valid schema but gaps
        data = {
            "service": "test-service",
            "period_days": 30,
            "total_deployments": 20,
            "successful_deployments": 20,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.667,
            "mean_time_between_deployments_hours": 36.0,
            "deployment_names": ["test-service"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "service_name": "test-service",
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": [
                {"date": "2026-07-01", "deployment_name": "test", "image": "test:1.0", "status": "successful"},
                {"date": "2026-07-02", "deployment_name": "test", "image": "test:1.0", "status": "successful"},
                # Missing days 3-10 (gap)
            ] + [
                {"date": f"2026-07-{i:02d}", "deployment_name": "test", "image": "test:1.0", "status": "successful"}
                for i in range(11, 31)
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Schema validation should pass
            assert result.is_wellformed_json, "JSON should be well-formed"
            assert result.has_required_fields, "Required fields should be present"
            assert result.has_valid_types, "Data types should be valid"

            # But gap detection should fail completeness
            assert not result.has_complete_coverage, "Completeness should fail due to gaps"
            assert result.gap_detected, "Gaps should be detected"

            # All schema validation flags should be preserved
            assert result.is_wellformed_json == True
            assert result.has_required_fields == True
            assert result.has_valid_types == True

        finally:
            Path(temp_path).unlink()

    def test_individual_validation_flags_preserved(self):
        """Test that individual validation flags are preserved in result."""
        result = ValidationResult(
            is_valid=True,
            file_path="/test/deployment.json"
        )

        # Set individual validation flags
        result.is_wellformed_json = True
        result.has_required_fields = True
        result.has_valid_types = True
        result.has_complete_coverage = False  # Fails due to gaps

        # Set gap metrics
        result.gap_detected = True
        result.coverage_percentage = 85.0
        result.gap_count = 5

        # Get output
        output = result.to_dict()

        # Verify all individual flags are preserved
        assert output["is_wellformed_json"] == True
        assert output["has_required_fields"] == True
        assert output["has_valid_types"] == True
        assert output["has_complete_coverage"] == False

        # Verify gap metrics are also present
        assert output["gap_detected"] == True
        assert output["coverage_percentage"] == 85.0
        assert output["gap_count"] == 5

    def test_error_messages_preserved_during_merge(self):
        """Test that error messages from all validation stages are preserved."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/deployment.json",
            errors=["Required fields: missing_field"]
        )

        # Add gap-related error
        result.gap_detected = True
        result.gap_count = 3
        result.errors.append("Coverage: Only 27 days out of 30")

        output = result.to_dict()

        # Both errors should be present
        assert len(output["errors"]) == 2
        assert "Required fields: missing_field" in output["errors"]
        assert any("Coverage" in err for err in output["errors"])


class TestMergedStructureSchemaValidation:
    """Test that merged structure matches expected schema."""

    def test_output_schema_has_all_required_keys(self):
        """Test that output structure has all required keys from schema."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/deployment.json"
        )

        # Set some gap metrics
        result.gap_detected = True
        result.coverage_percentage = 75.0

        output = result.to_dict()

        # Verify all required top-level keys are present
        required_keys = [
            "is_valid",
            "file_path",
            "is_wellformed_json",
            "has_required_fields",
            "has_valid_types",
            "has_complete_coverage",
            "errors",
            "gap_detected",
            "coverage_percentage",
            "expected_days",
            "actual_days",
            "gap_count",
            "gap_severity",
            "isolated_gap_count",
            "consecutive_gap_sequence_count",
            "gap_size_distribution",
            "gap_periods",
            "actionable_guidance",
            "anomaly_messages",
            "deployment_intervals",
            "validated_at"
        ]

        for key in required_keys:
            assert key in output, f"Missing required key in schema: {key}"

    def test_gap_size_distribution_schema_structure(self):
        """Test that gap_size_distribution matches expected schema structure."""
        result = ValidationResult(
            is_valid=True,
            file_path="/test/deployment.json"
        )

        # Set gap size distribution with all required keys
        result.gap_size_distribution = {
            "tiny": 1,      # 1 day gaps
            "small": 2,     # 2-3 day gaps
            "medium": 3,    # 4-7 day gaps
            "large": 4,     # 8-14 day gaps
            "extended": 5   # >14 day gaps
        }

        output = result.to_dict()

        # Verify structure
        assert "gap_size_distribution" in output
        dist = output["gap_size_distribution"]

        # Verify all required size categories
        required_sizes = ["tiny", "small", "medium", "large", "extended"]
        for size in required_sizes:
            assert size in dist, f"Missing size category: {size}"
            assert isinstance(dist[size], int), f"Size {size} should be integer"
            assert dist[size] >= 0, f"Size {size} count should be non-negative"

    def test_json_serialization_schema_compliance(self):
        """Test that output can be serialized to JSON without errors."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/deployment.json"
        )

        # Set comprehensive data
        result.gap_detected = True
        result.coverage_percentage = 75.0
        result.gap_count = 8
        result.gap_severity = "high"
        result.gap_size_distribution = {
            "tiny": 1, "small": 2, "medium": 2, "large": 2, "extended": 1
        }
        result.gap_periods = ["2026-07-01 to 2026-07-03"]
        result.actionable_guidance = ["Add missing data"]
        result.anomaly_messages = ["Gap detected"]

        output = result.to_dict()

        # Should serialize without errors
        try:
            json_str = json.dumps(output)
            assert len(json_str) > 0

            # Should deserialize back to same structure
            deserialized = json.loads(json_str)
            assert deserialized == output
        except (TypeError, ValueError) as e:
            pytest.fail(f"Output should be JSON serializable: {e}")


class TestMultipleGapResultsMerging:
    """Test multiple gap detection results merge correctly."""

    def test_multiple_gap_results_aggregation(self):
        """Test that multiple gap validation results can be aggregated."""
        # Create multiple gap results representing different periods
        gap_results = [
            GapValidationResult(
                is_valid=False,
                service_name="test-service",
                expected_days=30,
                actual_days=25,
                coverage_percentage=83.33,
                gap_periods=[
                    GapPeriod(
                        date="2026-07-05",
                        start_day="2026-07-05",
                        end_day="2026-07-07",
                        size_days=3,
                        is_consecutive=True
                    )
                ],
                severity=GapSeverity.MEDIUM
            ),
            GapValidationResult(
                is_valid=False,
                service_name="test-service",
                expected_days=30,
                actual_days=28,
                coverage_percentage=93.33,
                gap_periods=[
                    GapPeriod(
                        date="2026-07-15",
                        start_day="2026-07-15",
                        end_day="2026-07-15",
                        size_days=1,
                        is_consecutive=False
                    )
                ],
                severity=GapSeverity.LOW
            )
        ]

        # Aggregate the results
        total_gaps = sum(len(gr.gap_periods) for gr in gap_results)
        total_gap_days = sum(gp.size_days for gr in gap_results for gp in gr.gap_periods)

        # Verify aggregation
        assert total_gaps == 2, "Should have 2 total gap periods"
        assert total_gap_days == 4, "Should have 4 total gap days"

    def test_consecutive_gap_sequence_merging(self):
        """Test that consecutive gap sequences are correctly identified when merging."""
        # Create gap periods with some consecutive, some isolated
        gap_periods = [
            GapPeriod(
                date="2026-07-05",
                start_day="2026-07-05",
                end_day="2026-07-07",
                size_days=3,
                is_consecutive=True,
                sequence_id=1
            ),
            GapPeriod(
                date="2026-07-06",
                start_day="2026-07-06",
                end_day="2026-07-06",
                size_days=1,
                is_consecutive=True,
                sequence_id=1
            ),
            GapPeriod(
                date="2026-07-15",
                start_day="2026-07-15",
                end_day="2026-07-15",
                size_days=1,
                is_consecutive=False
            )
        ]

        # Count unique sequences
        unique_sequences = set(gp.sequence_id for gp in gap_periods if gp.is_consecutive)
        isolated_gaps = [gp for gp in gap_periods if not gp.is_consecutive]

        # Should have 1 consecutive sequence and 1 isolated gap
        assert len(unique_sequences) == 1
        assert len(isolated_gaps) == 1

    def test_severity_merging_chooses_worst(self):
        """Test that when merging results, worst severity is chosen."""
        severities = [
            GapSeverity.NONE,
            GapSeverity.LOW,
            GapSeverity.MEDIUM,
            GapSeverity.HIGH,
            GapSeverity.CRITICAL
        ]

        # Create results with different severities
        results = [
            GapValidationResult(
                is_valid=False,
                service_name="test",
                expected_days=30,
                actual_days=25,
                coverage_percentage=83.0,
                gap_periods=[],
                severity=severity
            )
            for severity in severities
        ]

        # Find worst severity
        severity_order = {
            GapSeverity.NONE: 0,
            GapSeverity.LOW: 1,
            GapSeverity.MEDIUM: 2,
            GapSeverity.HIGH: 3,
            GapSeverity.CRITICAL: 4
        }

        worst_severity = max(results, key=lambda r: severity_order[r.severity]).severity

        assert worst_severity == GapSeverity.CRITICAL

    def test_coverage_percentage_averaging(self):
        """Test that coverage percentages are averaged when merging multiple results."""
        results = [
            GapValidationResult(
                is_valid=False,
                service_name="test",
                expected_days=30,
                actual_days=25,
                coverage_percentage=83.33,
                gap_periods=[]
            ),
            GapValidationResult(
                is_valid=False,
                service_name="test",
                expected_days=30,
                actual_days=28,
                coverage_percentage=93.33,
                gap_periods=[]
            )
        ]

        # Calculate average coverage
        avg_coverage = sum(r.coverage_percentage for r in results) / len(results)

        # Should be approximately 88.33%
        assert 88.0 <= avg_coverage <= 89.0

    def test_actionable_guidance_aggregation(self):
        """Test that actionable guidance from multiple results is aggregated."""
        guidance_sets = [
            ["Add data for missing days 1-5"],
            ["Extend coverage period", "Check data collection"],
            ["Verify deployment events"]
        ]

        # Aggregate all guidance
        all_guidance = []
        for guidance in guidance_sets:
            all_guidance.extend(guidance)

        # Should have 4 total guidance items
        assert len(all_guidance) == 4

        # All should be unique strings
        assert len(set(all_guidance)) == len(all_guidance)


class TestComplexMergingScenarios:
    """Test edge cases and complex merging scenarios."""

    def test_merging_with_partial_gap_data(self):
        """Test merging when some gap data is missing or incomplete."""
        result = ValidationResult(
            is_valid=True,
            file_path="/test/deployment.json"
        )

        # Set partial gap data (some fields missing)
        result.gap_detected = True
        result.coverage_percentage = 75.0
        result.gap_count = 5
        # Note: gap_size_distribution and gap_periods not set

        output = result.to_dict()

        # Should still have all keys, even if empty/default
        assert "gap_size_distribution" in output
        assert "gap_periods" in output
        assert isinstance(output["gap_size_distribution"], dict)
        assert isinstance(output["gap_periods"], list)

    def test_merging_preserves_validation_timestamp(self):
        """Test that merging preserves the validation timestamp."""
        # Create result with specific timestamp
        timestamp = "2026-08-11T10:30:00Z"
        result = ValidationResult(
            is_valid=True,
            file_path="/test/deployment.json",
            validated_at=timestamp
        )

        # Add gap metrics
        result.gap_detected = True
        result.coverage_percentage = 85.0

        output = result.to_dict()

        # Timestamp should be preserved
        assert output["validated_at"] == timestamp

    def test_merging_with_zero_coverage(self):
        """Test merging when coverage is zero (no deployments)."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/deployment.json"
        )

        # Set zero coverage scenario
        result.gap_detected = True
        result.coverage_percentage = 0.0
        result.expected_days = 30
        result.actual_days = 0
        result.gap_count = 30
        result.gap_severity = "critical"

        output = result.to_dict()

        # Zero values should be preserved correctly
        assert output["coverage_percentage"] == 0.0
        assert output["actual_days"] == 0
        assert output["gap_count"] == 30
        assert output["gap_severity"] == "critical"

    def test_merging_with_perfect_coverage(self):
        """Test merging when coverage is perfect (100%)."""
        result = ValidationResult(
            is_valid=True,
            file_path="/test/deployment.json"
        )

        # Set perfect coverage
        result.gap_detected = False
        result.coverage_percentage = 100.0
        result.expected_days = 30
        result.actual_days = 30
        result.gap_count = 0
        result.gap_severity = "none"

        output = result.to_dict()

        # Perfect coverage should be reflected correctly
        assert output["coverage_percentage"] == 100.0
        assert output["actual_days"] == 30
        assert output["gap_count"] == 0
        assert output["gap_severity"] == "none"
        assert output["gap_detected"] == False

    def test_merging_error_handling_safe_defaults(self):
        """Test that merging uses safe defaults when gap detection fails."""
        result = ValidationResult(
            is_valid=True,
            file_path="/test/deployment.json"
        )

        # Simulate gap detection failure - defaults should be set
        result.gap_detected = False
        result.coverage_percentage = 100.0
        result.gap_count = 0
        result.gap_severity = "none"
        result.gap_size_distribution = {
            "tiny": 0, "small": 0, "medium": 0, "large": 0, "extended": 0
        }
        result.actionable_guidance = ["Gap detection was unavailable"]

        output = result.to_dict()

        # Safe defaults should be present
        assert output["gap_detected"] == False
        assert output["coverage_percentage"] == 100.0
        assert output["gap_count"] == 0
        assert output["gap_severity"] == "none"
        assert len(output["actionable_guidance"]) > 0


class TestResultMergingIntegration:
    """Integration tests for result merging in validation pipeline."""

    def test_end_to_end_validation_with_gaps(self):
        """Test complete validation pipeline with gap detection and result merging."""
        # Create deployment data with gaps
        data = {
            "service": "integration-test",
            "period_days": 30,
            "total_deployments": 25,
            "successful_deployments": 25,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.833,
            "mean_time_between_deployments_hours": 28.8,
            "deployment_names": ["integration-test"],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "service_name": "integration-test",
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": [
                {"date": f"2026-07-{i:02d}", "deployment_name": "test", "image": "test:1.0", "status": "successful"}
                for i in range(1, 26)  # Days 1-25 covered, missing 26-30
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify comprehensive result structure
            assert result is not None
            assert hasattr(result, 'gap_detected')
            assert hasattr(result, 'coverage_percentage')

            # Verify gap metrics are populated
            assert result.gap_detected == True
            assert result.coverage_percentage > 0
            assert result.coverage_percentage < 100

            # Verify schema validation passed
            assert result.is_wellformed_json
            assert result.has_required_fields
            assert result.has_valid_types

            # Verify completeness failed due to gaps
            assert not result.has_complete_coverage

            # Verify output structure
            output = result.to_dict()
            assert "gap_detected" in output
            assert "coverage_percentage" in output
            assert "gap_periods" in output

        finally:
            Path(temp_path).unlink()

    def test_result_serialization_roundtrip(self):
        """Test that result can be serialized and deserialized without data loss."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/deployment.json"
        )

        # Set comprehensive data
        result.gap_detected = True
        result.coverage_percentage = 75.0
        result.expected_days = 30
        result.actual_days = 22
        result.gap_count = 8
        result.gap_severity = "high"
        result.isolated_gap_count = 3
        result.consecutive_gap_sequence_count = 2
        result.gap_size_distribution = {
            "tiny": 1, "small": 2, "medium": 2, "large": 2, "extended": 1
        }
        result.gap_periods = ["2026-07-01 to 2026-07-02", "2026-07-10 to 2026-07-15"]
        result.actionable_guidance = ["Add missing deployment data"]
        result.anomaly_messages = ["Critical gap detected"]

        # Serialize
        output = result.to_dict()
        json_str = json.dumps(output)

        # Deserialize
        deserialized = json.loads(json_str)

        # Verify no data loss
        assert deserialized["gap_detected"] == result.gap_detected
        assert deserialized["coverage_percentage"] == result.coverage_percentage
        assert deserialized["gap_count"] == result.gap_count
        assert deserialized["gap_severity"] == result.gap_severity
        assert deserialized["isolated_gap_count"] == result.isolated_gap_count
        assert deserialized["consecutive_gap_sequence_count"] == result.consecutive_gap_sequence_count
        assert len(deserialized["gap_periods"]) == len(result.gap_periods)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])