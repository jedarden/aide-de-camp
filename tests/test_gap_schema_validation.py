#!/usr/bin/env python3
"""
Unit tests for Gap Validation Schema

Tests the Pydantic models and data structures defined in gap_schema.py.
Validates gap detection logic, coverage calculations, and data integrity.
"""

import pytest
from datetime import datetime, date, timedelta
from typing import List
from src.validation.gap_schema import (
    GapSeverity,
    GapPeriod,
    DeploymentInterval,
    CoverageMetrics,
    GapDetail,
    GapValidationResult,
    CoverageGapResult,
    GapSummary,
    GapAnomaly,
    GapAnalysisReport,
)


class TestGapSeverity:
    """Test GapSeverity enum functionality"""

    def test_severity_values(self):
        """Test that all severity levels are defined"""
        assert GapSeverity.CRITICAL.value == "critical"
        assert GapSeverity.HIGH.value == "high"
        assert GapSeverity.WARNING.value == "warning"
        assert GapSeverity.INFO.value == "info"
        assert GapSeverity.NONE.value == "none"

    def test_severity_comparison(self):
        """Test severity enum comparison"""
        assert GapSeverity.CRITICAL != GapSeverity.WARNING
        assert GapSeverity.NONE == GapSeverity.NONE


class TestGapPeriod:
    """Test GapPeriod model validation and functionality"""

    def test_valid_gap_period(self):
        """Test creating a valid gap period"""
        gap = GapPeriod(
            date="2026-08-10",
            start_day="2026-08-10",
            end_day="2026-08-10",
            size_days=1,
            is_consecutive=False,
            sequence_id=None
        )
        assert gap.date == "2026-08-10"
        assert gap.size_days == 1
        assert gap.is_consecutive is False

    def test_consecutive_gap_period(self):
        """Test creating a consecutive gap period"""
        gap = GapPeriod(
            date="2026-08-11",
            start_day="2026-08-10",
            end_day="2026-08-12",
            size_days=3,
            is_consecutive=True,
            sequence_id=1
        )
        assert gap.size_days == 3
        assert gap.is_consecutive is True
        assert gap.sequence_id == 1

    def test_invalid_gap_size(self):
        """Test that gap size must be at least 1"""
        with pytest.raises(ValueError, match="Gap size must be at least 1 day"):
            GapPeriod(
                date="2026-08-10",
                start_day="2026-08-10",
                end_day="2026-08-10",
                size_days=0
            )

    def test_negative_gap_size(self):
        """Test that negative gap size is rejected"""
        with pytest.raises(ValueError, match="Gap size must be at least 1 day"):
            GapPeriod(
                date="2026-08-10",
                start_day="2026-08-10",
                end_day="2026-08-10",
                size_days=-1
            )


class TestDeploymentInterval:
    """Test DeploymentInterval model validation"""

    def test_valid_deployment_interval(self):
        """Test creating a valid deployment interval"""
        interval = DeploymentInterval(
            first_deployment="2026-07-01",
            last_deployment="2026-07-30",
            total_deployments=15,
            average_interval_days=2.1,
            longest_interval_days=7,
            shortest_interval_days=1
        )
        assert interval.total_deployments == 15
        assert interval.average_interval_days == 2.1

    def test_average_interval_rounding(self):
        """Test that average interval is rounded to 1 decimal place"""
        interval = DeploymentInterval(
            first_deployment="2026-07-01",
            last_deployment="2026-07-30",
            total_deployments=10,
            average_interval_days=2.8567,
            longest_interval_days=5,
            shortest_interval_days=1
        )
        assert interval.average_interval_days == 2.9

    def test_invalid_negative_deployments(self):
        """Test that negative deployment count is rejected"""
        with pytest.raises(ValueError):
            DeploymentInterval(
                first_deployment="2026-07-01",
                last_deployment="2026-07-30",
                total_deployments=-1,
                average_interval_days=2.0,
                longest_interval_days=5,
                shortest_interval_days=1
            )

    def test_invalid_negative_interval(self):
        """Test that negative interval is rejected"""
        with pytest.raises(ValueError, match="Average interval must be non-negative"):
            DeploymentInterval(
                first_deployment="2026-07-01",
                last_deployment="2026-07-30",
                total_deployments=10,
                average_interval_days=-1.0,
                longest_interval_days=5,
                shortest_interval_days=1
            )


class TestCoverageMetrics:
    """Test CoverageMetrics model validation"""

    def test_valid_coverage_metrics(self):
        """Test creating valid coverage metrics"""
        metrics = CoverageMetrics(
            expected_days=30,
            actual_days=28,
            coverage_percentage=93.33,
            gap_count=2,
            meets_threshold=False,
            completeness_threshold=95.0
        )
        assert metrics.expected_days == 30
        assert metrics.actual_days == 28
        assert metrics.coverage_percentage == 93.33
        assert metrics.meets_threshold is False

    def test_coverage_percentage_rounding(self):
        """Test that coverage percentage is rounded to 2 decimal places"""
        metrics = CoverageMetrics(
            expected_days=30,
            actual_days=28,
            coverage_percentage=93.333333,
            gap_count=2,
            meets_threshold=False
        )
        assert metrics.coverage_percentage == 93.33

    def test_full_coverage(self):
        """Test 100% coverage scenario"""
        metrics = CoverageMetrics(
            expected_days=30,
            actual_days=30,
            coverage_percentage=100.0,
            gap_count=0,
            meets_threshold=True
        )
        assert metrics.coverage_percentage == 100.0
        assert metrics.meets_threshold is True

    def test_no_coverage(self):
        """Test 0% coverage scenario"""
        metrics = CoverageMetrics(
            expected_days=30,
            actual_days=0,
            coverage_percentage=0.0,
            gap_count=30,
            meets_threshold=False
        )
        assert metrics.coverage_percentage == 0.0
        assert metrics.actual_days == 0

    def test_invalid_coverage_percentage(self):
        """Test that coverage > 100% is rejected"""
        with pytest.raises(ValueError):
            CoverageMetrics(
                expected_days=30,
                actual_days=35,
                coverage_percentage=116.67,
                gap_count=0
            )

    def test_invalid_negative_coverage(self):
        """Test that negative coverage is rejected"""
        with pytest.raises(ValueError):
            CoverageMetrics(
                expected_days=30,
                actual_days=0,
                coverage_percentage=-5.0,
                gap_count=30
            )


class TestGapDetail:
    """Test GapDetail model validation"""

    def test_valid_gap_detail(self):
        """Test creating a valid gap detail"""
        gap = GapDetail(
            gap_start_days_ago=10,
            gap_end_days_ago=8,
            gap_duration_days=3,
            severity=GapSeverity.WARNING,
            gap_start_date="2026-08-01",
            gap_end_date="2026-08-03",
            actionable_message="3-day gap detected",
            is_consecutive=True
        )
        assert gap.gap_duration_days == 3
        assert gap.severity == GapSeverity.WARNING
        assert gap.is_consecutive is True

    def test_single_day_gap(self):
        """Test single day gap scenario"""
        gap = GapDetail(
            gap_start_days_ago=5,
            gap_end_days_ago=5,
            gap_duration_days=1,
            severity=GapSeverity.INFO,
            gap_start_date="2026-08-06",
            gap_end_date="2026-08-06"
        )
        assert gap.gap_duration_days == 1
        assert gap.gap_start_days_ago == 5
        assert gap.gap_end_days_ago == 5

    def test_critical_gap(self):
        """Test critical gap (>7 days)"""
        gap = GapDetail(
            gap_start_days_ago=20,
            gap_end_days_ago=10,
            gap_duration_days=11,
            severity=GapSeverity.CRITICAL,
            actionable_message="Critical gap detected"
        )
        assert gap.gap_duration_days == 11
        assert gap.severity == GapSeverity.CRITICAL

    def test_invalid_gap_duration(self):
        """Test that gap duration must be at least 1"""
        with pytest.raises(ValueError, match="Gap duration must be at least 1 day"):
            GapDetail(
                gap_start_days_ago=10,
                gap_end_days_ago=10,
                gap_duration_days=0,
                severity=GapSeverity.INFO
            )

    def test_gap_with_missing_data_types(self):
        """Test gap with missing data types"""
        gap = GapDetail(
            gap_start_days_ago=15,
            gap_end_days_ago=13,
            gap_duration_days=3,
            severity=GapSeverity.WARNING,
            missing_data_types=["replica_history", "deployment_events"],
            actionable_message="Missing deployment data"
        )
        assert "replica_history" in gap.missing_data_types
        assert "deployment_events" in gap.missing_data_types


class TestGapValidationResult:
    """Test GapValidationResult model"""

    def test_valid_result(self):
        """Test creating a valid gap validation result"""
        result = GapValidationResult(
            is_valid=True,
            service_name="test-service",
            expected_days=30,
            actual_days=30,
            coverage_percentage=100.0,
            severity=GapSeverity.NONE
        )
        assert result.is_valid is True
        assert result.coverage_percentage == 100.0
        assert result.severity == GapSeverity.NONE

    def test_invalid_result_with_gaps(self):
        """Test validation result with gaps"""
        result = GapValidationResult(
            is_valid=False,
            service_name="test-service",
            expected_days=30,
            actual_days=25,
            coverage_percentage=83.33,
            severity=GapSeverity.HIGH,
            error_message="5 gaps detected",
            actionable_guidance=["Add missing deployment data", "Check pipeline"]
        )
        assert result.is_valid is False
        assert result.severity == GapSeverity.HIGH
        assert len(result.actionable_guidance) == 2

    def test_result_with_deployment_intervals(self):
        """Test result with deployment interval statistics"""
        intervals = DeploymentInterval(
            first_deployment="2026-07-01",
            last_deployment="2026-07-30",
            total_deployments=10,
            average_interval_days=3.2,
            longest_interval_days=8,
            shortest_interval_days=1
        )
        result = GapValidationResult(
            is_valid=True,
            service_name="test-service",
            expected_days=30,
            actual_days=30,
            coverage_percentage=100.0,
            deployment_intervals=intervals
        )
        assert result.deployment_intervals is not None
        assert result.deployment_intervals.total_deployments == 10


class TestCoverageGapResult:
    """Test CoverageGapResult model"""

    def test_result_no_gaps(self):
        """Test result with no gaps detected"""
        result = CoverageGapResult(
            has_gaps=False,
            total_gaps=0,
            critical_gaps=0,
            warning_gaps=0,
            info_gaps=0,
            coverage_percentage=100.0,
            meets_threshold=True
        )
        assert result.has_gaps is False
        assert result.total_gaps == 0
        assert result.meets_threshold is True

    def test_result_with_critical_gaps(self):
        """Test result with critical gaps"""
        result = CoverageGapResult(
            has_gaps=True,
            total_gaps=3,
            critical_gaps=1,
            warning_gaps=1,
            info_gaps=1,
            coverage_percentage=76.67,
            meets_threshold=False
        )
        assert result.critical_gaps == 1
        assert result.meets_threshold is False

    def test_result_with_gap_details(self):
        """Test result with detailed gap information"""
        gap1 = GapDetail(
            gap_start_days_ago=10,
            gap_end_days_ago=8,
            gap_duration_days=3,
            severity=GapSeverity.WARNING
        )
        gap2 = GapDetail(
            gap_start_days_ago=5,
            gap_end_days_ago=5,
            gap_duration_days=1,
            severity=GapSeverity.INFO
        )
        result = CoverageGapResult(
            has_gaps=True,
            total_gaps=2,
            critical_gaps=0,
            warning_gaps=1,
            info_gaps=1,
            gap_details=[gap1, gap2],
            coverage_percentage=86.67
        )
        assert len(result.gap_details) == 2
        assert result.warning_gaps == 1


class TestGapSummary:
    """Test GapSummary model"""

    def test_valid_summary(self):
        """Test creating a valid gap summary"""
        summary = GapSummary(
            total_gaps=10,
            isolated_gaps=6,
            consecutive_sequences=2,
            longest_gap_days=7,
            longest_gap_start="2026-07-15",
            longest_gap_end="2026-07-21",
            gap_intensity=0.3333,
            total_analysis_days=30
        )
        assert summary.total_gaps == 10
        assert summary.gap_intensity == 0.3333

    def test_gap_intensity_rounding(self):
        """Test that gap intensity is rounded to 4 decimal places"""
        summary = GapSummary(
            total_gaps=10,
            isolated_gaps=6,
            consecutive_sequences=2,
            longest_gap_days=7,
            gap_intensity=0.33333333,
            total_analysis_days=30
        )
        assert summary.gap_intensity == 0.3333

    def test_empty_summary(self):
        """Test summary with no gaps"""
        summary = GapSummary(
            total_gaps=0,
            isolated_gaps=0,
            consecutive_sequences=0,
            longest_gap_days=0,
            gap_intensity=0.0,
            total_analysis_days=30
        )
        assert summary.total_gaps == 0
        assert summary.longest_gap_days == 0


class TestGapAnomaly:
    """Test GapAnomaly model"""

    def test_valid_anomaly(self):
        """Test creating a valid gap anomaly"""
        anomaly = GapAnomaly(
            severity="critical",
            category="extended_gap",
            description="Critical gap of 15 days detected",
            actionable_guidance="Review data collection infrastructure",
            affected_period="2026-07-10 to 2026-07-24",
            impact_assessment="50% of analysis period affected"
        )
        assert anomaly.severity == "critical"
        assert anomaly.category == "extended_gap"
        assert "data collection infrastructure" in anomaly.actionable_guidance


class TestGapAnalysisReport:
    """Test comprehensive GapAnalysisReport model"""

    def test_valid_report(self):
        """Test creating a comprehensive gap analysis report"""
        coverage_metrics = CoverageMetrics(
            expected_days=30,
            actual_days=25,
            coverage_percentage=83.33,
            gap_count=5,
            meets_threshold=False
        )

        gap_summary = GapSummary(
            total_gaps=5,
            isolated_gaps=3,
            consecutive_sequences=1,
            longest_gap_days=7,
            gap_intensity=0.1667,
            total_analysis_days=30
        )

        gap_detail = GapDetail(
            gap_start_days_ago=10,
            gap_end_days_ago=4,
            gap_duration_days=7,
            severity=GapSeverity.CRITICAL
        )

        report = GapAnalysisReport(
            service_name="test-service",
            analysis_period_start="2026-07-01",
            analysis_period_end="2026-07-30",
            coverage_metrics=coverage_metrics,
            gap_summary=gap_summary,
            gap_details=[gap_detail],
            is_valid=False,
            overall_severity=GapSeverity.CRITICAL
        )

        assert report.service_name == "test-service"
        assert report.is_valid is False
        assert report.overall_severity == GapSeverity.CRITICAL
        assert len(report.gap_details) == 1

    def test_report_with_anomalies(self):
        """Test report with detected anomalies"""
        coverage_metrics = CoverageMetrics(
            expected_days=30,
            actual_days=20,
            coverage_percentage=66.67,
            gap_count=10,
            meets_threshold=False
        )

        gap_summary = GapSummary(
            total_gaps=10,
            isolated_gaps=5,
            consecutive_sequences=2,
            longest_gap_days=8,
            gap_intensity=0.3333,
            total_analysis_days=30
        )

        anomaly = GapAnomaly(
            severity="critical",
            category="high_gap_intensity",
            description="Gap intensity exceeds 30%",
            actionable_guidance="Investigate data collection pipeline",
            impact_assessment="High impact on analysis reliability"
        )

        report = GapAnalysisReport(
            service_name="test-service",
            analysis_period_start="2026-07-01",
            analysis_period_end="2026-07-30",
            coverage_metrics=coverage_metrics,
            gap_summary=gap_summary,
            anomalies=[anomaly],
            is_valid=False,
            overall_severity=GapSeverity.CRITICAL
        )

        assert len(report.anomalies) == 1
        assert report.anomalies[0].category == "high_gap_intensity"

    def test_report_with_deployment_intervals(self):
        """Test report includes deployment interval analysis"""
        coverage_metrics = CoverageMetrics(
            expected_days=30,
            actual_days=30,
            coverage_percentage=100.0,
            gap_count=0,
            meets_threshold=True
        )

        gap_summary = GapSummary(
            total_gaps=0,
            isolated_gaps=0,
            consecutive_sequences=0,
            longest_gap_days=0,
            gap_intensity=0.0,
            total_analysis_days=30
        )

        deployment_intervals = DeploymentInterval(
            first_deployment="2026-07-01",
            last_deployment="2026-07-30",
            total_deployments=15,
            average_interval_days=2.1,
            longest_interval_days=7,
            shortest_interval_days=1
        )

        report = GapAnalysisReport(
            service_name="test-service",
            analysis_period_start="2026-07-01",
            analysis_period_end="2026-07-30",
            coverage_metrics=coverage_metrics,
            gap_summary=gap_summary,
            deployment_intervals=deployment_intervals,
            is_valid=True,
            overall_severity=GapSeverity.NONE
        )

        assert report.deployment_intervals is not None
        assert report.deployment_intervals.total_deployments == 15


class TestGapDetectionScenarios:
    """Test realistic gap detection scenarios"""

    def test_no_gaps_scenario(self):
        """Test scenario with perfect coverage (no gaps)"""
        result = GapValidationResult(
            is_valid=True,
            service_name="pbx-web",
            expected_days=30,
            actual_days=30,
            coverage_percentage=100.0,
            severity=GapSeverity.NONE
        )
        assert result.is_valid
        assert result.coverage_percentage == 100.0

    def test_single_day_gap_scenario(self):
        """Test scenario with a single isolated gap"""
        gap = GapDetail(
            gap_start_days_ago=15,
            gap_end_days_ago=15,
            gap_duration_days=1,
            severity=GapSeverity.INFO,
            gap_start_date="2026-07-16",
            gap_end_date="2026-07-16"
        )
        result = CoverageGapResult(
            has_gaps=True,
            total_gaps=1,
            critical_gaps=0,
            warning_gaps=0,
            info_gaps=1,
            gap_details=[gap],
            coverage_percentage=96.67,
            meets_threshold=True
        )
        assert result.total_gaps == 1
        assert result.info_gaps == 1
        assert result.meets_threshold

    def test_consecutive_gaps_scenario(self):
        """Test scenario with consecutive gap sequence"""
        gap = GapDetail(
            gap_start_days_ago=12,
            gap_end_days_ago=8,
            gap_duration_days=5,
            severity=GapSeverity.WARNING,
            gap_start_date="2026-07-19",
            gap_end_date="2026-07-23",
            is_consecutive=True
        )
        result = CoverageGapResult(
            has_gaps=True,
            total_gaps=1,
            critical_gaps=0,
            warning_gaps=1,
            info_gaps=0,
            gap_details=[gap],
            coverage_percentage=83.33,
            meets_threshold=False
        )
        assert result.warning_gaps == 1
        assert result.meets_threshold is False

    def test_critical_gap_scenario(self):
        """Test scenario with critical gap (>7 days)"""
        gap = GapDetail(
            gap_start_days_ago=25,
            gap_end_days_ago=15,
            gap_duration_days=11,
            severity=GapSeverity.CRITICAL,
            gap_start_date="2026-07-06",
            gap_end_date="2026-07-16",
            actionable_message="Critical gap: 11-day gap from 2026-07-06 to 2026-07-16"
        )
        result = CoverageGapResult(
            has_gaps=True,
            total_gaps=1,
            critical_gaps=1,
            warning_gaps=0,
            info_gaps=0,
            gap_details=[gap],
            coverage_percentage=63.33,
            meets_threshold=False
        )
        assert result.critical_gaps == 1
        assert result.coverage_percentage < 80.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
