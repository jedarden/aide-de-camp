#!/usr/bin/env python3
"""
Tests for coverage gap validation with comprehensive error messages.

These tests verify that:
1. Gap detection correctly identifies missing periods
2. Gap severity classification follows thresholds
3. Error messages are clear, specific, and actionable
4. Validation covers all completeness section requirements
"""

import pytest
from datetime import datetime, timedelta
from src.validation.coverage_gap import (
    CoverageGapValidator,
    CoverageGapResult,
    GapDetail,
    GapSeverity,
    validate_completeness_section
)


class TestGapDetail:
    """Tests for GapDetail dataclass and error message generation."""

    def test_critical_gap_message_generation(self):
        """Test that critical gaps generate appropriate error messages."""
        gap = GapDetail(
            gap_start_days_ago=25,
            gap_end_days_ago=15,
            gap_duration_days=10,
            severity=GapSeverity.CRITICAL,
            gap_start_date=datetime(2026, 7, 12),
            gap_end_date=datetime(2026, 7, 21)
        )

        message = gap.actionable_message
        assert "CRITICAL GAP" in message
        assert "10-day gap" in message
        assert "prevents completeness validation" in message
        assert "exceeds 7-day threshold" in message

    def test_warning_gap_message_generation(self):
        """Test that warning gaps generate appropriate error messages."""
        gap = GapDetail(
            gap_start_days_ago=20,
            gap_end_days_ago=17,
            gap_duration_days=3,
            severity=GapSeverity.WARNING,
            gap_start_date=datetime(2026, 7, 17),
            gap_end_date=datetime(2026, 7, 19)
        )

        message = gap.actionable_message
        assert "WARNING: Gap detected" in message
        assert "3-day gap" in message
        assert "partial coverage" in message
        assert "investigate" in message.lower()

    def test_info_gap_message_generation(self):
        """Test that info gaps generate appropriate error messages."""
        gap = GapDetail(
            gap_start_days_ago=5,
            gap_end_days_ago=4,
            gap_duration_days=1,
            severity=GapSeverity.INFO,
            gap_start_date=datetime(2026, 8, 1),
            gap_end_date=datetime(2026, 8, 1)
        )

        message = gap.actionable_message
        assert "INFO: Minor gap" in message
        assert "1-day gap" in message
        assert "acceptable" in message

    def test_gap_to_dict_serialization(self):
        """Test that GapDetail serializes correctly to dictionary."""
        gap = GapDetail(
            gap_start_days_ago=10,
            gap_end_days_ago=5,
            gap_duration_days=5,
            severity=GapSeverity.CRITICAL,
            gap_start_date=datetime(2026, 7, 22),
            gap_end_date=datetime(2026, 7, 26),
            missing_data_types=["replicasets", "argo_cd_status"]
        )

        result = gap.to_dict()
        assert result["gap_start_days_ago"] == 10
        assert result["gap_end_days_ago"] == 5
        assert result["gap_duration_days"] == 5
        assert result["severity"] == "critical"
        assert result["gap_start_date"] == "2026-07-22T00:00:00"
        assert result["gap_end_date"] == "2026-07-26T00:00:00"
        assert result["missing_data_types"] == ["replicasets", "argo_cd_status"]
        assert "actionable_message" in result

    def test_single_day_vs_multi_day_formatting(self):
        """Test that single-day gaps use different formatting than multi-day gaps."""
        # Single-day gap should use "on YYYY-MM-DD" format
        single_day_gap = GapDetail(
            gap_duration_days=1,
            gap_start_days_ago=5,
            gap_end_days_ago=4,
            severity=GapSeverity.INFO,
            gap_start_date=datetime(2026, 8, 6),
            gap_end_date=datetime(2026, 8, 6)
        )

        message = single_day_gap.actionable_message
        assert "1-day gap on 2026-08-06" in message
        # Should NOT show redundant "from 2026-08-06 to 2026-08-06"
        assert "from 2026-08-06 to 2026-08-06" not in message

        # Multi-day gap should use "from YYYY-MM-DD to YYYY-MM-DD" format
        multi_day_gap = GapDetail(
            gap_duration_days=10,
            gap_start_days_ago=25,
            gap_end_days_ago=15,
            severity=GapSeverity.CRITICAL,
            gap_start_date=datetime(2026, 7, 12),
            gap_end_date=datetime(2026, 7, 21)
        )

        message = multi_day_gap.actionable_message
        assert "10-day gap from 2026-07-12 to 2026-07-21" in message


class TestCoverageGapResult:
    """Tests for CoverageGapResult aggregation."""

    def test_result_summary_without_gaps(self):
        """Test summary generation when no gaps are present."""
        result = CoverageGapResult(
            has_gaps=False,
            total_gaps=0,
            critical_gaps=0,
            warning_gaps=0,
            info_gaps=0,
            coverage_percentage=100.0,
            meets_threshold=True
        )

        assert result.actionable_summary == "✅ No coverage gaps detected. Deployment data has complete temporal coverage."
        assert result.meets_threshold is True

    def test_result_summary_with_critical_gaps(self):
        """Test summary generation with critical gaps."""
        result = CoverageGapResult(
            has_gaps=True,
            total_gaps=2,
            critical_gaps=2,
            warning_gaps=0,
            info_gaps=0,
            coverage_percentage=65.0,
            meets_threshold=False
        )

        summary = result.actionable_summary
        assert "⚠️ COVERAGE GAPS DETECTED" in summary
        assert "2 gap(s) found" in summary
        assert "2 critical" in summary
        assert "🚨 CRITICAL" in summary
        assert "exceed 7-day threshold" in summary
        assert "RECOMMENDED ACTIONS" in summary

    def test_result_to_dict_serialization(self):
        """Test that result serializes correctly."""
        gap = GapDetail(
            gap_start_days_ago=10,
            gap_end_days_ago=5,
            gap_duration_days=5,
            severity=GapSeverity.CRITICAL
        )

        result = CoverageGapResult(
            has_gaps=True,
            total_gaps=1,
            critical_gaps=1,
            warning_gaps=0,
            info_gaps=0,
            gap_details=[gap],
            error_messages=[gap.actionable_message],
            coverage_percentage=85.0,
            meets_threshold=False
        )

        result_dict = result.to_dict()
        assert result_dict["has_gaps"] is True
        assert result_dict["total_gaps"] == 1
        assert result_dict["critical_gaps"] == 1
        assert len(result_dict["gap_details"]) == 1
        assert len(result_dict["error_messages"]) == 1
        assert result_dict["coverage_percentage"] == 85.0


class TestCoverageGapValidator:
    """Tests for the CoverageGapValidator class."""

    def test_no_data_returns_critical_error(self):
        """Test validator with no deployment data."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        result = validator.validate_coverage([])

        assert result.has_gaps is True
        assert result.total_gaps == 1
        assert result.critical_gaps == 1
        assert result.coverage_percentage == 0.0
        assert result.meets_threshold is False
        assert len(result.error_messages) == 1
        assert "No deployment data found" in result.error_messages[0]

    def test_complete_coverage_no_gaps(self):
        """Test validator with complete daily coverage."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        # Create deployment data with daily coverage
        deployments = []
        current_date = datetime(2026, 7, 7)
        end_date = datetime(2026, 8, 6)

        while current_date <= end_date:
            deployments.append({"timestamp": current_date.isoformat() + "Z"})
            current_date += timedelta(days=1)

        result = validator.validate_coverage(deployments)

        assert result.has_gaps is False
        assert result.total_gaps == 0
        assert result.coverage_percentage >= 95.0
        assert result.meets_threshold is True

    def test_critical_gap_detection(self):
        """Test detection of gaps > 7 days."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        # Create deployments with a 10-day gap
        deployments = [
            {"timestamp": "2026-07-07T00:00:00Z"},
            {"timestamp": "2026-07-15T00:00:00Z"},  # 8-day gap from July 7
            {"timestamp": "2026-08-06T00:00:00Z"}
        ]

        result = validator.validate_coverage(deployments)

        assert result.has_gaps is True
        assert result.critical_gaps >= 1
        assert any(gap.gap_duration_days > 7 for gap in result.gap_details)

    def test_warning_gap_detection(self):
        """Test detection of gaps between 3-7 days."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        # Create deployments with a 5-day gap
        deployments = [
            {"timestamp": "2026-07-07T00:00:00Z"},
            {"timestamp": "2026-07-13T00:00:00Z"},  # 5-day gap
            {"timestamp": "2026-08-06T00:00:00Z"}
        ]

        result = validator.validate_coverage(deployments)

        assert result.has_gaps is True
        assert result.warning_gaps >= 1
        assert any(3 <= gap.gap_duration_days <= 7 for gap in result.gap_details)

    def test_info_gap_detection(self):
        """Test detection of gaps < 3 days."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        # Create deployments with a 2-day gap
        deployments = [
            {"timestamp": "2026-07-07T00:00:00Z"},
            {"timestamp": "2026-07-10T00:00:00Z"},  # 2-day gap
            {"timestamp": "2026-08-06T00:00:00Z"}
        ]

        result = validator.validate_coverage(deployments)

        assert result.has_gaps is True
        assert result.info_gaps >= 1
        assert any(gap.gap_duration_days < 3 for gap in result.gap_details)

    def test_multiple_gaps_detection(self):
        """Test detection of multiple gaps with different severities."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        # Create deployments with multiple gaps
        deployments = [
            {"timestamp": "2026-07-07T00:00:00Z"},
            {"timestamp": "2026-07-09T00:00:00Z"},  # 1-day gap (info)
            {"timestamp": "2026-07-15T00:00:00Z"},  # 5-day gap (warning)
            {"timestamp": "2026-07-29T00:00:00Z"},  # 13-day gap (critical)
            {"timestamp": "2026-08-06T00:00:00Z"}
        ]

        result = validator.validate_coverage(deployments)

        assert result.total_gaps == 4
        assert result.info_gaps >= 1
        assert result.warning_gaps >= 2  # 5-day and 7-day gaps
        assert result.critical_gaps >= 1

    def test_error_messages_are_actionable(self):
        """Test that error messages provide actionable guidance."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        # Create deployment with critical gap
        deployments = [
            {"timestamp": "2026-07-07T00:00:00Z"},
            {"timestamp": "2026-07-20T00:00:00Z"}  # 12-day gap
        ]

        result = validator.validate_coverage(deployments)

        # Verify error messages contain actionable content
        for error in result.error_messages:
            assert any(keyword in error for keyword in
                     ["ACTION", "Review", "Add", "Check", "Investigate", "Consider"])

    def test_custom_completeness_threshold(self):
        """Test validator with custom completeness threshold."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6),
            completeness_threshold=90.0  # Lower threshold
        )

        # Create deployments with 92% coverage
        deployments = []
        for i in range(28):  # 28 days out of 30
            deployments.append({"timestamp": (datetime(2026, 7, 7) + timedelta(days=i)).isoformat() + "Z"})

        result = validator.validate_coverage(deployments)

        # Should meet 90% threshold
        assert result.meets_threshold is True
        assert result.coverage_percentage >= 90.0

    def test_invalid_timestamp_handling(self):
        """Test that invalid timestamps are handled gracefully."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        deployments = [
            {"timestamp": "2026-07-07T00:00:00Z"},
            {"timestamp": "invalid-timestamp"},  # Invalid format
            {"timestamp": "2026-07-10T00:00:00Z"}
        ]

        result = validator.validate_coverage(deployments)

        # Should only count valid timestamps
        assert result.total_gaps >= 0  # May detect gaps from valid timestamps only


class TestCompletenessValidation:
    """Tests for completeness section validation."""

    def test_missing_completeness_section(self):
        """Test validation when completeness section is missing."""
        data = {
            "metadata": {"service": "test"},
            "deployment_info": {}
        }

        errors = validate_completeness_section(data)

        assert len(errors) == 1
        assert "COMPLETENESS SECTION MISSING" in errors[0]
        assert "ACTION" in errors[0]

    def test_missing_period_coverage_days(self):
        """Test validation when period_coverage_days is missing."""
        data = {
            "completeness": {
                "data_coverage_percent": "100%"
            }
        }

        errors = validate_completeness_section(data)

        assert any("period_coverage_days MISSING" in error for error in errors)

    def test_insufficient_period_coverage_days(self):
        """Test validation when period coverage is less than 30 days."""
        data = {
            "completeness": {
                "period_coverage_days": 25,
                "data_coverage_percent": "83%"
            }
        }

        errors = validate_completeness_section(data)

        assert any("MISSING DAYS IN 30-DAY COVERAGE" in error for error in errors)
        assert any("5 day(s)" in error for error in errors)  # 30 - 25 = 5 missing

    def test_invalid_coverage_percent_format(self):
        """Test validation when coverage_percent has invalid format."""
        data = {
            "completeness": {
                "period_coverage_days": 30,
                "data_coverage_percent": "95"  # Missing % symbol
            }
        }

        errors = validate_completeness_section(data)

        assert any("Invalid data coverage percentage format" in error for error in errors)
        assert any("% symbol" in error for error in errors)

    def test_gaps_detected_without_details(self):
        """Test validation when gaps_detected is true but gap_details is missing."""
        data = {
            "completeness": {
                "period_coverage_days": 30,
                "data_coverage_percent": "90%",
                "gaps_detected": True
            }
        }

        errors = validate_completeness_section(data)

        assert any("GAPS DETECTED WITHOUT DETAILS" in error for error in errors)

    def test_invalid_gap_detail_timing(self):
        """Test validation of gap detail with negative timing."""
        data = {
            "completeness": {
                "period_coverage_days": 30,
                "data_coverage_percent": "90%",
                "gaps_detected": True,
                "gap_details": [
                    {
                        "gap_start_days_ago": -5,  # Invalid: negative
                        "gap_end_days_ago": 10,
                        "gap_duration_days": 5
                    }
                ]
            }
        }

        errors = validate_completeness_section(data)

        assert any("INVALID GAP TIMING" in error for error in errors)
        assert any("cannot be negative" in error for error in errors)

    def test_invalid_gap_duration(self):
        """Test validation of gap detail with invalid duration."""
        data = {
            "completeness": {
                "period_coverage_days": 30,
                "data_coverage_percent": "90%",
                "gaps_detected": True,
                "gap_details": [
                    {
                        "gap_start_days_ago": 10,
                        "gap_end_days_ago": 5,
                        "gap_duration_days": 0  # Invalid: must be >= 1
                    }
                ]
            }
        }

        errors = validate_completeness_section(data)

        assert any("INVALID GAP DURATION" in error for error in errors)
        assert any("at least 1 day" in error for error in errors)

    def test_mismatched_severity_classification(self):
        """Test validation when severity doesn't match gap duration."""
        data = {
            "completeness": {
                "period_coverage_days": 30,
                "data_coverage_percent": "90%",
                "gaps_detected": True,
                "gap_details": [
                    {
                        "gap_start_days_ago": 25,
                        "gap_end_days_ago": 15,
                        "gap_duration_days": 10,  # 10 days = critical
                        "severity": "warning"  # Wrong: should be critical
                    }
                ]
            }
        }

        errors = validate_completeness_section(data)

        assert any("INVALID SEVERITY LEVEL" in error for error in errors)
        assert any("critical" in error for error in errors)  # Should suggest 'critical'

    def test_threshold_not_met_error_message(self):
        """Test error message when completeness threshold is not met."""
        data = {
            "completeness": {
                "period_coverage_days": 30,
                "data_coverage_percent": "85%",
                "gaps_detected": True,
                "meets_completeness_threshold": False,
                "completeness_threshold_percent": "95%"
            }
        }

        errors = validate_completeness_section(data)

        assert any("COMPLETENESS THRESHOLD NOT MET" in error for error in errors)
        assert any("85%" in error and "95%" in error for error in errors)

    def test_missing_deployment_days_error_message(self):
        """Test error message for missing deployment days."""
        data = {
            "completeness": {
                "period_coverage_days": 30,
                "data_coverage_percent": "100%",
                "gaps_detected": False,
                "meets_completeness_threshold": True,
                "minimum_deployment_days": 5,
                "actual_deployment_days": 2,
                "deployment_days_threshold_met": False
            }
        }

        errors = validate_completeness_section(data)

        # Should include error about missing deployment days
        assert any("MISSING DEPLOYMENT DAYS" in error for error in errors)

    def test_complete_valid_completeness_section(self):
        """Test validation with complete, valid completeness section."""
        data = {
            "completeness": {
                "period_coverage_days": 30,
                "data_coverage_percent": "100%",
                "gaps_detected": False,
                "gap_details": [],
                "meets_completeness_threshold": True,
                "completeness_threshold_percent": "95%",
                "minimum_deployment_days": 1,
                "actual_deployment_days": 15,
                "deployment_days_threshold_met": True
            }
        }

        errors = validate_completeness_section(data)

        # Should have no errors for valid data
        assert len(errors) == 0

    def test_error_messages_contain_guidance(self):
        """Test that all error messages contain actionable guidance."""
        data = {
            "completeness": {
                "period_coverage_days": 20,
                "data_coverage_percent": "67%",
                "gaps_detected": True,
                "gap_details": [
                    {
                        "gap_start_days_ago": 15,
                        "gap_end_days_ago": 10,
                        "gap_duration_days": 5,
                        "severity": "warning"
                    }
                ],
                "meets_completeness_threshold": False
            }
        }

        errors = validate_completeness_section(data)

        # All errors should contain actionable guidance
        for error in errors:
            assert any(keyword in error for keyword in
                     ["ACTION", "Add", "Check", "Review", "Verify", "Provide", "Consider"])


class TestGapSeverityClassification:
    """Tests for gap severity classification logic."""

    def test_critical_threshold_enforcement(self):
        """Test that gaps > 7 days are classified as critical."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        # 8-day gap should be critical
        assert validator._classify_gap(8) == GapSeverity.CRITICAL
        # 7-day gap should be warning (not critical)
        assert validator._classify_gap(7) == GapSeverity.WARNING

    def test_warning_threshold_enforcement(self):
        """Test that gaps 3-7 days are classified as warning."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        assert validator._classify_gap(3) == GapSeverity.WARNING
        assert validator._classify_gap(5) == GapSeverity.WARNING
        assert validator._classify_gap(7) == GapSeverity.WARNING

    def test_info_threshold_enforcement(self):
        """Test that gaps < 3 days are classified as info."""
        validator = CoverageGapValidator(
            period_start=datetime(2026, 7, 7),
            period_end=datetime(2026, 8, 6)
        )

        assert validator._classify_gap(1) == GapSeverity.INFO
        assert validator._classify_gap(2) == GapSeverity.INFO


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
