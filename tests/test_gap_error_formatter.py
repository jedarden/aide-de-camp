#!/usr/bin/env python3
"""
Comprehensive tests for gap error message formatting.

Tests validate:
1. Error messages reference deployment intervals
2. Messages explain expected coverage patterns
3. Guidance suggests specific fixes (e.g., 'deploy to iad-options within 24 hours')
4. Messages formatted consistently with schema validation errors
5. Message content and formatting correctness
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from src.utilities.gap_calculator import GapPeriod
from src.utilities.gap_error_formatter import (
    format_gap_error,
    format_gap_errors_batch,
    generate_actionable_guidance,
    format_validation_summary,
    GapContext
)


class TestGapErrorFormatting:
    """Test basic gap error message formatting."""

    def test_format_single_gap_error(self):
        """Test formatting a single gap error."""
        gap = GapPeriod(
            date="2026-07-05",
            start_day="2026-07-05",
            end_day="2026-07-05",
            size_days=1,
            is_consecutive=False,
            sequence_id=None
        )

        context = GapContext(
            service_name="pbx-web",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0,
            analysis_period_start="2026-07-01",
            analysis_period_end="2026-07-30"
        )

        error = format_gap_error(gap, context)

        # Verify error contains all required sections
        assert "[pbx-web]" in error
        assert "1-day" in error
        assert "isolated gap" in error
        assert "2026-07-05" in error

        # Verify deployment interval reference
        assert "Deployment interval reference" in error
        assert "Expected deployments on days 1-30" in error

        # Verify expected coverage pattern
        assert "Expected coverage pattern" in error
        assert "95.0%" in error  # Code outputs float with decimal
        assert "30-day period" in error

        # Verify actionable guidance
        assert "Action:" in error
        assert "Deploy to pbx-web" in error

    def test_format_consecutive_gap_sequence(self):
        """Test formatting consecutive gap sequences."""
        gap = GapPeriod(
            date="2026-07-10",
            start_day="2026-07-08",
            end_day="2026-07-12",
            size_days=5,
            is_consecutive=True,
            sequence_id=0
        )

        context = GapContext(
            service_name="whisper-stt",
            cluster="iad-ci",
            expected_days=30,
            coverage_threshold=95.0
        )

        error = format_gap_error(gap, context)

        # Verify consecutive sequence formatting
        assert "consecutive sequence" in error
        assert "5-day" in error
        assert "2026-07-08 to 2026-07-12" in error

        # Verify severity classification
        assert "medium severity" in error

    def test_format_extended_gap(self):
        """Test formatting extended gaps (>14 days)."""
        gap = GapPeriod(
            date="2026-07-15",
            start_day="2026-07-10",
            end_day="2026-07-28",
            size_days=19,
            is_consecutive=True,
            sequence_id=0
        )

        context = GapContext(
            service_name="mta-my-way",
            cluster="apexalgo-iad",
            expected_days=30,
            coverage_threshold=95.0
        )

        error = format_gap_error(gap, context)

        # Verify extended gap formatting
        assert "19-day" in error
        assert "extended severity" in error
        assert "consecutive sequence" in error

        # Verify critical guidance
        assert "Critical" in error or "critical" in error.lower()
        assert "infrastructure logs" in error.lower()

    def test_format_with_unknown_cluster(self):
        """Test formatting when cluster is unknown."""
        gap = GapPeriod(
            date="2026-07-05",
            start_day="2026-07-05",
            end_day="2026-07-05",
            size_days=1,
            is_consecutive=False,
            sequence_id=None
        )

        context = GapContext(
            service_name="test-service",
            cluster="unknown",  # Default value
            expected_days=30,
            coverage_threshold=95.0
        )

        error = format_gap_error(gap, context)

        # Should handle unknown cluster gracefully
        assert "test-service" in error
        assert "Deploy to test-service" in error
        assert "target cluster" in error or "on cluster 'unknown'" not in error


class TestBatchFormatting:
    """Test batch formatting of multiple gaps."""

    def test_format_multiple_gaps_sorted_by_size(self):
        """Test that gaps are sorted by size (largest first)."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False),
            GapPeriod("2026-07-10", "2026-07-08", "2026-07-12", 5, True, 0),
            GapPeriod("2026-07-20", "2026-07-20", "2026-07-25", 6, True, 1),
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30
        )

        errors = format_gap_errors_batch(gaps, context, max_errors=10)

        # Verify all gaps are formatted
        assert len(errors) == 3

        # Verify sorting: 6-day gap should appear before 1-day gap
        first_error = errors[0]
        last_error = errors[-1]
        assert "6-day" in first_error
        assert "1-day" in last_error

    def test_batch_with_max_errors_limit(self):
        """Test batch formatting with max_errors limit."""
        gaps = [
            GapPeriod(f"2026-07-{i:02d}", f"2026-07-{i:02d}", f"2026-07-{i:02d}", 1, False)
            for i in range(1, 16)  # 15 gaps
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30
        )

        errors = format_gap_errors_batch(gaps, context, max_errors=5)

        # Should return 5 formatted errors plus summary
        assert len(errors) == 6
        assert "... and 10 additional gap(s)" in errors[-1]

    def test_batch_with_empty_gaps(self):
        """Test batch formatting with no gaps."""
        gaps = []

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30
        )

        errors = format_gap_errors_batch(gaps, context)

        # Should return empty list
        assert errors == []


class TestActionableGuidance:
    """Test generation of actionable guidance."""

    def test_guidance_for_single_isolated_gap(self):
        """Test guidance for a single isolated gap."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="pbx-web",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0
        )

        guidance = generate_actionable_guidance(gaps, context)

        # Should provide guidance
        assert len(guidance) > 0

        # Should mention isolated gaps
        guidance_text = " ".join(guidance)
        assert "isolated" in guidance_text.lower()

        # Should include remediation steps
        assert any("Deploy to pbx-web" in g for g in guidance)

    def test_guidance_for_consecutive_gaps(self):
        """Test guidance for consecutive gap sequences."""
        gaps = [
            GapPeriod("2026-07-10", "2026-07-08", "2026-07-12", 5, True, 0),
            GapPeriod("2026-07-11", "2026-07-08", "2026-07-12", 5, True, 0),
            GapPeriod("2026-07-12", "2026-07-08", "2026-07-12", 5, True, 0),
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30
        )

        guidance = generate_actionable_guidance(gaps, context)

        # Should mention consecutive sequences
        guidance_text = " ".join(guidance)
        assert "consecutive" in guidance_text.lower()
        assert "sequence" in guidance_text.lower()

        # Should reference the specific date range
        assert "2026-07-08" in guidance_text
        assert "2026-07-12" in guidance_text

    def test_guidance_for_critical_gaps(self):
        """Test guidance for critical gaps (>14 days)."""
        gaps = [
            GapPeriod("2026-07-20", "2026-07-10", "2026-07-28", 19, True, 0)
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30
        )

        guidance = generate_actionable_guidance(gaps, context)

        # Should have CRITICAL priority message
        guidance_text = " ".join(guidance)
        assert "CRITICAL" in guidance_text
        assert "14 days" in guidance_text

        # Should suggest infrastructure review
        assert "infrastructure logs" in guidance_text.lower()

    def test_guidance_with_last_deployment_date(self):
        """Test guidance includes last deployment date context."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="pbx-web",
            cluster="iad-options",
            expected_days=30,
            last_deployment_date="2026-07-04"
        )

        guidance = generate_actionable_guidance(gaps, context)

        # Should include last deployment date
        guidance_text = " ".join(guidance)
        assert "2026-07-04" in guidance_text
        assert "Last deployment" in guidance_text

    def test_guidance_for_mixed_gap_types(self):
        """Test guidance for combination of consecutive and isolated gaps."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False),  # isolated
            GapPeriod("2026-07-10", "2026-07-08", "2026-07-12", 5, True, 0),  # consecutive
            GapPeriod("2026-07-20", "2026-07-18", "2026-07-25", 8, True, 1),  # large consecutive
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30
        )

        guidance = generate_actionable_guidance(gaps, context)

        # Should address both gap types
        guidance_text = " ".join(guidance)
        assert "isolated" in guidance_text.lower()
        assert "consecutive" in guidance_text.lower()

        # Should prioritize by severity (large gap gets priority)
        assert any("HIGH" in g or "large" in g.lower() for g in guidance)


class TestValidationSummaryFormatting:
    """Test validation summary formatting."""

    def test_summary_formatting_consistency(self):
        """Test that summary is formatted consistently with schema validation errors."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False),
            GapPeriod("2026-07-10", "2026-07-08", "2026-07-12", 5, True, 0),
        ]

        context = GapContext(
            service_name="pbx-web",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0,
            analysis_period_start="2026-07-01",
            analysis_period_end="2026-07-30",
            last_deployment_date="2026-07-28"
        )

        summary = format_validation_summary(gaps, coverage_percentage=90.0, context=context)

        # Should have consistent header format
        assert "❌ Coverage Validation Failed: pbx-web" in summary
        assert "==" in summary  # Separator lines

        # Should have coverage metrics section
        assert "📊 Coverage Metrics:" in summary
        assert "Service:              pbx-web" in summary
        assert "Cluster:              iad-options" in summary
        assert "Coverage:             90.0%" in summary

        # Should have deployment interval reference section
        assert "📅 Deployment Interval Reference:" in summary
        assert "Analysis period:" in summary
        assert "Expected coverage:" in summary

        # Should have gap breakdown section
        assert "🚫 Gap Breakdown:" in summary
        assert "Consecutive sequences:" in summary
        assert "Isolated gaps:" in summary

        # Should have actionable guidance section
        assert "💡 Actionable Guidance:" in summary

        # Should have expected coverage requirements section
        assert "📐 Expected Coverage Requirements:" in summary

    def test_summary_includes_all_required_sections(self):
        """Test that summary includes all required information."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0
        )

        summary = format_validation_summary(gaps, coverage_percentage=96.7, context=context)

        # Verify deployment interval reference
        assert "Days 1-30 of analysis period" in summary

        # Verify expected coverage pattern
        assert "At least one deployment every 24 hours" in summary

        # Verify specific threshold (accepts both 95% and 95.0%)
        assert "95% coverage" in summary or "95.0% coverage" in summary

        # Verify gap size distribution
        assert "Size distribution:" in summary
        assert "tiny: 1" in summary

    def test_summary_with_no_gaps(self):
        """Test summary formatting when there are no gaps."""
        gaps = []

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0
        )

        summary = format_validation_summary(gaps, coverage_percentage=100.0, context=context)

        # Should still format correctly
        assert "Coverage:             100.0%" in summary
        assert "Gaps detected:         0" in summary

        # Should not have gap breakdown section
        assert "Gap Breakdown:" not in summary


class TestSpecificFixGuidance:
    """Test that guidance suggests specific fixes."""

    def test_guidance_suggests_deploy_to_cluster_within_24h(self):
        """Test that guidance includes 'deploy to X within 24 hours' pattern."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="pbx-web",
            cluster="iad-options",
            expected_days=30
        )

        guidance = generate_actionable_guidance(gaps, context)

        # Should include specific deployment guidance
        guidance_text = " ".join(guidance)
        assert "Deploy to pbx-web" in guidance_text
        assert "within 24 hours" in guidance_text

    def test_guidance_includes_cluster_name(self):
        """Test that guidance references the specific cluster."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="pbx-web",
            cluster="iad-options",
            expected_days=30
        )

        error = format_gap_error(gaps[0], context)

        # Should reference cluster
        assert "on cluster 'iad-options'" in error

    def test_guidance_for_extended_gap_specific_steps(self):
        """Test that extended gaps get specific remediation steps."""
        gaps = [
            GapPeriod("2026-07-20", "2026-07-10", "2026-07-28", 19, True, 0)
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30
        )

        error = format_gap_error(gaps[0], context)

        # Extended gap should have specific guidance
        assert "Review infrastructure logs" in error
        assert "2026-07-10 to 2026-07-28" in error
        assert "root cause" in error.lower()

    def test_guidance_includes_verification_steps(self):
        """Test that guidance includes verification steps."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0
        )

        guidance = generate_actionable_guidance(gaps, context)

        # Should include verification step
        guidance_text = " ".join(guidance)
        assert "Verification:" in guidance_text or "verify" in guidance_text.lower()
        assert "re-run validation" in guidance_text.lower()


class TestDeploymentIntervalReferences:
    """Test that error messages reference deployment intervals."""

    def test_error_references_deployment_interval(self):
        """Test that error messages include deployment interval reference."""
        gap = GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30,
            analysis_period_start="2026-07-01",
            analysis_period_end="2026-07-30"
        )

        error = format_gap_error(gap, context)

        # Should explicitly reference deployment interval
        assert "Deployment interval reference" in error
        assert "days 1-30" in error

    def test_summary_references_deployment_interval(self):
        """Test that summary includes deployment interval section."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30,
            analysis_period_start="2026-07-01",
            analysis_period_end="2026-07-30"
        )

        summary = format_validation_summary(gaps, coverage_percentage=96.7, context=context)

        # Should have deployment interval section
        assert "Deployment Interval Reference" in summary
        assert "2026-07-01" in summary
        assert "2026-07-30" in summary


class TestExpectedCoveragePatterns:
    """Test that messages explain expected coverage patterns."""

    def test_error_explains_expected_pattern(self):
        """Test that error messages explain expected coverage pattern."""
        gap = GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0
        )

        error = format_gap_error(gap, context)

        # Should explain expected pattern
        assert "Expected coverage pattern" in error
        assert "30-day period" in error
        assert ("95%" in error or "95.0%" in error)  # Matches both formats

    def test_summary_includes_expected_pattern_section(self):
        """Test that summary includes expected pattern documentation."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0
        )

        summary = format_validation_summary(gaps, coverage_percentage=96.7, context=context)

        # Should have expected coverage requirements section
        assert "Expected Coverage Requirements" in summary
        assert "At least one deployment every 24 hours" in summary
        assert "maximum 24h interval" in summary


class TestConsistencyWithSchemaValidation:
    """Test that messages are formatted consistently with schema validation errors."""

    def test_header_format_consistency(self):
        """Test that error headers match schema validation format."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="pbx-web",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0
        )

        summary = format_validation_summary(gaps, coverage_percentage=96.7, context=context)

        # Should use consistent header format with emoji and separators
        assert "❌" in summary  # Error icon
        assert "Coverage Validation Failed:" in summary
        assert "=" in summary  # Separator lines

    def test_section_structure_consistency(self):
        """Test that error messages use consistent section structure."""
        gaps = [
            GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)
        ]

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30,
            coverage_threshold=95.0
        )

        summary = format_validation_summary(gaps, coverage_percentage=96.7, context=context)

        # Should have consistent section structure with emoji headers
        sections = [
            "📊 Coverage Metrics:",
            "📅 Deployment Interval Reference:",
            "🚫 Gap Breakdown:",
            "💡 Actionable Guidance:",
            "📐 Expected Coverage Requirements:"
        ]

        for section in sections:
            assert section in summary

    def test_indentation_consistency(self):
        """Test that formatted messages use consistent indentation."""
        gap = GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False)

        context = GapContext(
            service_name="test-service",
            cluster="iad-options",
            expected_days=30
        )

        error = format_gap_error(gap, context)

        # Lines should be consistently indented
        lines = error.split("\n")
        for line in lines[1:]:  # Skip header line
            if line.strip():  # Non-empty lines
                assert line.startswith("  ")  # Should have 2-space indent


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
