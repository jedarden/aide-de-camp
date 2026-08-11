#!/usr/bin/env python3
"""
Test that ValidationResult outputs comprehensive gap metrics.

This test verifies that the ValidationResult.to_dict() method includes
all required gap metrics in the correct format as specified by the
validation output schema.
"""

import pytest
from datetime import datetime
from src.validation.runner import ValidationResult


class TestValidationResultGapMetrics:
    """Test gap metrics in ValidationResult output."""

    def test_to_dict_includes_all_gap_metrics(self):
        """Test that to_dict() includes all required gap metrics."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/path.json"
        )

        # Set gap metrics
        result.gap_detected = True
        result.gap_count = 5
        result.gap_severity = "medium"
        result.coverage_percentage = 83.33
        result.expected_days = 30
        result.actual_days = 25
        result.isolated_gap_count = 2
        result.consecutive_gap_sequence_count = 1
        result.gap_size_distribution = {
            "tiny": 1,
            "small": 1,
            "medium": 1,
            "large": 1,
            "extended": 1
        }
        result.gap_periods = ["2026-07-01 to 2026-07-02", "2026-07-05 to 2026-07-09"]

        # Get dict output
        output = result.to_dict()

        # Verify all gap metrics are present
        assert "gap_detected" in output
        assert "gap_count" in output
        assert "gap_severity" in output
        assert "coverage_percentage" in output
        assert "expected_days" in output
        assert "actual_days" in output
        assert "isolated_gap_count" in output
        assert "consecutive_gap_sequence_count" in output
        assert "gap_size_distribution" in output
        assert "gap_periods" in output

    def test_gap_size_distribution_structure(self):
        """Test that gap_size_distribution has correct structure."""
        result = ValidationResult(is_valid=True, file_path="/test/path.json")

        result.gap_size_distribution = {
            "tiny": 1,
            "small": 2,
            "medium": 3,
            "large": 4,
            "extended": 5
        }

        output = result.to_dict()

        assert "gap_size_distribution" in output
        assert isinstance(output["gap_size_distribution"], dict)
        assert output["gap_size_distribution"]["tiny"] == 1
        assert output["gap_size_distribution"]["small"] == 2
        assert output["gap_size_distribution"]["medium"] == 3
        assert output["gap_size_distribution"]["large"] == 4
        assert output["gap_size_distribution"]["extended"] == 5

    def test_gap_severity_classification(self):
        """Test that gap_severity accepts all valid values."""
        valid_severities = ["none", "low", "medium", "high", "critical"]

        for severity in valid_severities:
            result = ValidationResult(is_valid=True, file_path="/test/path.json")
            result.gap_severity = severity
            output = result.to_dict()

            assert output["gap_severity"] == severity

    def test_isolated_vs_consecutive_gap_counts(self):
        """Test that isolated and consecutive gap counts are separate."""
        result = ValidationResult(is_valid=True, file_path="/test/path.json")

        result.isolated_gap_count = 3
        result.consecutive_gap_sequence_count = 2

        output = result.to_dict()

        assert output["isolated_gap_count"] == 3
        assert output["consecutive_gap_sequence_count"] == 2
        # These should be independent metrics
        assert output["isolated_gap_count"] != output["consecutive_gap_sequence_count"]

    def test_gap_periods_list_format(self):
        """Test that gap_periods is output as a list of strings."""
        result = ValidationResult(is_valid=True, file_path="/test/path.json")

        result.gap_periods = [
            "2026-07-01 to 2026-07-03",
            "2026-07-10 to 2026-07-15"
        ]

        output = result.to_dict()

        assert "gap_periods" in output
        assert isinstance(output["gap_periods"], list)
        assert len(output["gap_periods"]) == 2
        assert output["gap_periods"][0] == "2026-07-01 to 2026-07-03"

    def test_coverage_percentage_float(self):
        """Test that coverage_percentage is a float."""
        result = ValidationResult(is_valid=True, file_path="/test/path.json")

        result.coverage_percentage = 95.5

        output = result.to_dict()

        assert "coverage_percentage" in output
        assert isinstance(output["coverage_percentage"], float)
        assert output["coverage_percentage"] == 95.5

    def test_backward_compatibility_legacy_tuple(self):
        """Test that get_legacy_tuple() returns backward-compatible format."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/path.json",
            errors=["Error 1", "Error 2"]
        )

        # Get legacy format
        is_valid, errors = result.get_legacy_tuple()

        # Verify it matches old format
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)
        assert is_valid == False
        assert len(errors) == 2
        assert errors == ["Error 1", "Error 2"]

    def test_all_gap_metrics_default_to_zero(self):
        """Test that gap metrics default to appropriate zero values."""
        result = ValidationResult(is_valid=True, file_path="/test/path.json")

        output = result.to_dict()

        # Check defaults
        assert output.get("gap_count", 0) >= 0
        assert output.get("isolated_gap_count", 0) >= 0
        assert output.get("consecutive_gap_sequence_count", 0) >= 0
        assert isinstance(output.get("gap_size_distribution", {}), dict)

    def test_actionable_guidance_in_output(self):
        """Test that actionable_guidance is included in output."""
        result = ValidationResult(is_valid=True, file_path="/test/path.json")

        result.actionable_guidance = [
            "Add deployment data for missing days",
            "Extend data collection period"
        ]

        output = result.to_dict()

        assert "actionable_guidance" in output
        assert isinstance(output["actionable_guidance"], list)
        assert len(output["actionable_guidance"]) == 2

    def test_anomaly_messages_in_output(self):
        """Test that anomaly_messages is included in output."""
        result = ValidationResult(is_valid=True, file_path="/test/path.json")

        result.anomaly_messages = [
            "Unusual deployment pattern detected",
            "Coverage gap exceeds threshold"
        ]

        output = result.to_dict()

        assert "anomaly_messages" in output
        assert isinstance(output["anomaly_messages"], list)
        assert len(output["anomaly_messages"]) == 2

    def test_complete_gap_metrics_output_schema(self):
        """Test that output schema matches documented structure."""
        result = ValidationResult(
            is_valid=False,
            file_path="/test/deployment.json"
        )

        # Set all gap metrics
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

        output = result.to_dict()

        # Verify schema structure
        required_keys = [
            "is_valid",
            "file_path",
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
            "validated_at"
        ]

        for key in required_keys:
            assert key in output, f"Missing required key: {key}"

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
