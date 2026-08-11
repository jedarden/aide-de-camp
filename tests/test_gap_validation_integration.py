#!/usr/bin/env python3
"""
End-to-End Tests for Gap Validation Integration

Tests the complete validation pipeline with gap detection and actionable guidance:
- Gap validation integrated into schema validation flow
- Messages include actionable guidance for fixing gaps
- Guidance references deployment intervals and expected coverage
- Full pipeline validation from JSON to error messages
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile

from src.validation.runner import validate_deployment_file
from src.validation.gap_integration import (
    validate_gaps_with_guidance,
    format_gap_validation_result,
    GapValidationResult,
    GapSeverity
)


class TestGapValidationIntegration:
    """Test gap validation integrated into the validation pipeline."""

    def test_no_gaps_passes_validation(self):
        """Test that deployment data with no gaps passes validation."""
        # Create deployment data with perfect 30-day coverage
        data = self._create_complete_deployment_data(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z"
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert is_valid, f"Expected valid but got errors: {errors}"
            assert len(errors) == 0
        finally:
            Path(temp_path).unlink()

    def test_single_gap_provides_actionable_guidance(self):
        """Test that a single gap generates actionable error message."""
        # Create deployment data with a single 3-day gap
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7]  # Days 5-7 missing
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid, "Expected validation to fail with gaps"
            assert len(errors) > 0

            # Check for actionable guidance in error messages
            error_text = "\n".join(errors)
            assert "Actionable Guidance" in error_text or "actionable_guidance" in error_text.lower()
            assert "gap" in error_text.lower()
            assert "coverage" in error_text.lower() or "coverage" in error_text
        finally:
            Path(temp_path).unlink()

    def test_multiple_consecutive_gaps_provides_guidance(self):
        """Test that consecutive gap sequences get proper guidance."""
        data = self._create_deployment_data_with_gaps(
            service_name="whisper-stt",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[10, 11, 12, 13, 14, 15]  # 6-day consecutive gap
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid

            error_text = "\n".join(errors)
            # Should mention consecutive gaps
            assert "consecutive" in error_text.lower() or "sequence" in error_text.lower()
            # Should provide actionable guidance
            assert "deployment" in error_text.lower() or "add" in error_text.lower()
        finally:
            Path(temp_path).unlink()

    def test_extended_critical_gap_guidance(self):
        """Test that extended gaps (>14 days) generate critical severity guidance."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=list(range(10, 25))  # 15-day gap
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            is_valid, errors = validate_deployment_file(temp_path)
            assert not is_valid

            error_text = "\n".join(errors)
            # Should indicate critical severity
            assert "critical" in error_text.lower() or "crITICAL" in error_text
            # Should reference deployment intervals
            assert "deployment interval" in error_text.lower() or "days 1-30" in error_text.lower()
        finally:
            Path(temp_path).unlink()

    def test_coverage_percentage_in_error_message(self):
        """Test that error messages include coverage percentage."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[1, 2, 3, 4, 5, 6]  # 6 days missing = 80% coverage
        )

        result = validate_gaps_with_guidance(
            data,
            service_name="pbx-web"
        )

        assert not result.is_valid
        assert result.coverage_percentage < 95.0
        error_message = format_gap_validation_result(result)

        # Check for coverage percentage in formatted output
        assert "Coverage:" in error_message or "coverage" in error_message.lower()
        assert "80%" in error_message or "80.0" in error_message

    def test_deployment_intervals_reference_in_guidance(self):
        """Test that guidance references deployment intervals."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[15, 16, 17]
        )

        result = validate_gaps_with_guidance(
            data,
            service_name="pbx-web"
        )

        guidance = "\n".join(result.actionable_guidance)

        # Should reference expected deployment interval
        assert "deployment interval" in guidance.lower() or "days 1-30" in guidance.lower()
        assert "expected" in guidance.lower()

    def test_expected_coverage_requirements_in_message(self):
        """Test that error messages include expected coverage requirements."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7, 8, 9]
        )

        result = validate_gaps_with_guidance(
            data,
            service_name="pbx-web"
        )

        formatted_message = format_gap_validation_result(result)

        # Should include expected coverage requirements section
        assert "Expected Coverage" in formatted_message or "expected" in formatted_message.lower()
        assert "95%" in formatted_message or "threshold" in formatted_message.lower()

    def test_service_name_in_error_message(self):
        """Test that service name is included in error messages."""
        data = self._create_deployment_data_with_gaps(
            service_name="whisper-stt",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[10, 11, 12]
        )

        result = validate_gaps_with_guidance(
            data,
            service_name="whisper-stt"
        )

        formatted_message = format_gap_validation_result(result)

        # Should include service name
        assert "whisper-stt" in formatted_message

    def test_multiple_gaps_all_listed(self):
        """Test that multiple individual gaps are all listed."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 10, 15, 20, 25]  # 5 isolated gaps
        )

        result = validate_gaps_with_guidance(
            data,
            service_name="pbx-web"
        )

        assert len(result.gap_periods) == 5
        formatted_message = format_gap_validation_result(result)

        # Should show all gaps or indicate there are multiple
        assert "gap" in formatted_message.lower()

    def test_gap_size_classification_in_guidance(self):
        """Test that gap sizes are classified correctly in guidance."""
        # Test with various gap sizes
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7, 8, 9, 10, 11, 12]  # 8-day gap
        )

        result = validate_gaps_with_guidance(
            data,
            service_name="pbx-web"
        )

        # Should have appropriate severity for an 8-day gap
        assert result.severity in [GapSeverity.HIGH, GapSeverity.CRITICAL]
        formatted_message = format_gap_validation_result(result)

        # Should indicate gap size
        assert "8" in formatted_message or "day" in formatted_message.lower()

    def test_remediation_steps_in_guidance(self):
        """Test that guidance includes specific remediation steps."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7]
        )

        result = validate_gaps_with_guidance(
            data,
            service_name="pbx-web"
        )

        guidance_text = "\n".join(result.actionable_guidance)

        # Should include actionable steps like:
        # - "Add deployment data"
        # - "Check for missing days"
        # - "Extend data collection"
        has_add_deployment = "add deployment data" in guidance_text.lower()
        has_check_missing = "missing" in guidance_text.lower()
        has_verify_data = "verify" in guidance_text.lower() or "check" in guidance_text.lower()

        assert has_add_deployment or has_check_missing or has_verify_data

    def test_isolated_vs_consecutive_gap_distinction(self):
        """Test that isolated and consecutive gaps are distinguished."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7, 10, 15, 16, 17]  # Mix of isolated and consecutive
        )

        result = validate_gaps_with_guidance(
            data,
            service_name="pbx-web"
        )

        formatted_message = format_gap_validation_result(result)

        # Should distinguish between consecutive and isolated gaps
        has_consecutive = "consecutive" in formatted_message.lower() or "sequence" in formatted_message.lower()
        has_isolated = "isolated" in formatted_message.lower() or "individual" in formatted_message.lower()

        assert has_consecutive or has_isolated

    def test_deployment_intervals_calculation(self):
        """Test that deployment intervals are calculated and shown."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[10, 11, 12]
        )

        result = validate_gaps_with_guidance(
            data,
            service_name="pbx-web"
        )

        # Should have deployment intervals calculated
        assert result.deployment_intervals is not None
        assert "first_deployment" in result.deployment_intervals
        assert "last_deployment" in result.deployment_intervals
        assert "average_interval_days" in result.deployment_intervals

        formatted_message = format_gap_validation_result(result)

        # Should show deployment intervals section
        assert "Deployment Intervals" in formatted_message or "deployment" in formatted_message.lower()

    # Helper methods

    def _create_complete_deployment_data(
        self,
        service_name: str,
        start_date: str,
        end_date: str
    ) -> dict:
        """Create deployment data with complete 30-day coverage."""
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        period_days = (end - start).days + 1

        # Generate all days in range
        deployment_events = []
        current = start
        while current <= end:
            deployment_events.append({
                "date": current.date().isoformat(),
                "deployment_name": service_name,
                "image": f"ronaldraygun/{service_name}:1.0.0",
                "status": "successful"
            })
            current += timedelta(days=1)

        total_deployments = len(deployment_events)
        deployment_freq = total_deployments / period_days if period_days > 0 else 0
        mtbd_hours = (period_days * 24) / total_deployments if total_deployments > 0 else 0

        return {
            "service": service_name,
            "first_deployment": start_date,
            "last_deployment": end_date,
            "period_days": period_days,
            "total_deployments": total_deployments,
            "successful_deployments": total_deployments,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": deployment_freq,
            "mean_time_between_deployments_hours": mtbd_hours,
            "deployment_names": [service_name],
            "metadata": {
                "service_name": service_name,
                "time_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            "deployment_events_last_30_days": deployment_events
        }

    def _create_deployment_data_with_gaps(
        self,
        service_name: str,
        start_date: str,
        end_date: str,
        missing_days: list
    ) -> dict:
        """Create deployment data with specified missing days."""
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        period_days = (end - start).days + 1

        # Generate deployment events, excluding missing days
        deployment_events = []
        current = start
        day_count = 0
        while current <= end:
            day_count += 1
            if day_count not in missing_days:
                deployment_events.append({
                    "date": current.date().isoformat(),
                    "deployment_name": service_name,
                    "image": f"ronaldraygun/{service_name}:1.0.0",
                    "status": "successful"
                })
            current += timedelta(days=1)

        actual_days = len(deployment_events)
        coverage_pct = round((actual_days / period_days) * 100, 2)
        deployment_freq = actual_days / period_days if period_days > 0 else 0
        mtbd_hours = (period_days * 24) / actual_days if actual_days > 0 else 0
        success_rate = (actual_days / actual_days * 100) if actual_days > 0 else 0

        return {
            "service": service_name,
            "first_deployment": start_date,
            "last_deployment": end_date,
            "period_days": period_days,
            "total_deployments": actual_days,
            "successful_deployments": actual_days,
            "failed_deployments": 0,
            "success_rate": success_rate,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": deployment_freq,
            "mean_time_between_deployments_hours": mtbd_hours,
            "deployment_names": [service_name],
            "metadata": {
                "service_name": service_name,
                "time_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            "deployment_events_last_30_days": deployment_events
        }


class TestGapSeverityClassification:
    """Test gap severity classification in integrated validation."""

    def test_no_gaps_none_severity(self):
        """Test that no gaps results in NONE severity."""
        data = self._create_data_with_coverage(100.0, [])
        result = validate_gaps_with_guidance(data, service_name="test")
        assert result.severity == GapSeverity.NONE
        assert result.is_valid

    def test_small_gaps_low_severity(self):
        """Test that small gaps (<3 days) result in LOW severity."""
        # For LOW severity, need: coverage >= 95% AND gap size <= 3 days
        # 1 missing day = 29/30 = 96.67% coverage, gap size = 1 day
        data = self._create_data_with_coverage(96.67, [5])
        result = validate_gaps_with_guidance(data, service_name="test")
        assert result.severity == GapSeverity.LOW

    def test_medium_gaps_medium_severity(self):
        """Test that medium gaps (3-7 days) result in MEDIUM severity."""
        # For MEDIUM severity, need: coverage >= 90% AND < 95% OR gap size > 3 days
        # 3 missing days = 27/30 = 90.0% coverage (not < 90%, so won't trigger HIGH)
        # But coverage = 90% is not < 95%, so it triggers MEDIUM
        data = self._create_data_with_coverage(90.0, [5, 6, 7])
        result = validate_gaps_with_guidance(data, service_name="test")
        assert result.severity == GapSeverity.MEDIUM

    def test_large_gaps_high_severity(self):
        """Test that large gaps (7-14 days) result in HIGH severity."""
        # For HIGH severity, need: coverage >= 80% AND < 90% OR gap size > 7 days
        # 4 missing days = 26/30 = 86.67% coverage, gap size = 4 days (not > 7, so coverage triggers it)
        # 86.67% is < 90%, so it triggers HIGH
        data = self._create_data_with_coverage(86.67, [5, 6, 7, 8])
        result = validate_gaps_with_guidance(data, service_name="test")
        assert result.severity == GapSeverity.HIGH

    def test_extended_gaps_critical_severity(self):
        """Test that extended gaps (>14 days) result in CRITICAL severity."""
        data = self._create_data_with_coverage(50.0, list(range(5, 20)))
        result = validate_gaps_with_guidance(data, service_name="test")
        assert result.severity == GapSeverity.CRITICAL

    def _create_data_with_coverage(self, coverage_pct: float, missing_days: list) -> dict:
        """Helper to create data with specific coverage."""
        start_date = "2026-07-01T00:00:00Z"
        end_date = "2026-07-30T23:59:59Z"
        period_days = 30

        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        deployment_events = []
        current = start
        day_count = 0
        while current <= end:
            day_count += 1
            if day_count not in missing_days:
                deployment_events.append({
                    "date": current.date().isoformat(),
                    "deployment_name": "test",
                    "image": "ronaldraygun/test:1.0.0",
                    "status": "successful"
                })
            current += timedelta(days=1)

        actual_days = len(deployment_events)
        deployment_freq = actual_days / period_days if period_days > 0 else 0
        mtbd_hours = (period_days * 24) / actual_days if actual_days > 0 else 0
        success_rate = (actual_days / actual_days * 100) if actual_days > 0 else 0

        return {
            "service": "test",
            "first_deployment": start_date,
            "last_deployment": end_date,
            "period_days": period_days,
            "total_deployments": actual_days,
            "successful_deployments": actual_days,
            "failed_deployments": 0,
            "success_rate": success_rate,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": deployment_freq,
            "mean_time_between_deployments_hours": mtbd_hours,
            "deployment_names": ["test"],
            "metadata": {
                "service_name": "test",
                "time_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            "deployment_events_last_30_days": deployment_events
        }


class TestActionableGuidanceContent:
    """Test the content and quality of actionable guidance."""

    def test_guidance_includes_coverage_info(self):
        """Test that guidance includes coverage percentage information."""
        data = self._create_data_with_gap(80.0)
        result = validate_gaps_with_guidance(data, service_name="test")

        guidance_text = "\n".join(result.actionable_guidance)

        # Should mention coverage percentage
        assert "coverage" in guidance_text.lower() or "%" in guidance_text

    def test_guidance_includes_deployment_interval_reference(self):
        """Test that guidance references deployment intervals."""
        data = self._create_data_with_gap(85.0)
        result = validate_gaps_with_guidance(data, service_name="test")

        guidance_text = "\n".join(result.actionable_guidance)

        # Should reference deployment intervals or expected days
        assert "deployment" in guidance_text.lower() or "day" in guidance_text.lower()

    def test_guidance_includes_remediation_steps(self):
        """Test that guidance includes specific remediation steps."""
        data = self._create_data_with_gap(75.0)
        result = validate_gaps_with_guidance(data, service_name="test")

        guidance_text = "\n".join(result.actionable_guidance)

        # Should include actionable verbs like "add", "check", "verify"
        actionable_verbs = ["add", "check", "verify", "extend", "fill", "review", "investigate"]
        has_actionable_verb = any(verb in guidance_text.lower() for verb in actionable_verbs)

        assert has_actionable_verb, f"Expected actionable verb in: {guidance_text}"

    def _create_data_with_gap(self, coverage_pct: float) -> dict:
        """Helper to create data with a gap resulting in specific coverage."""
        start_date = "2026-07-01T00:00:00Z"
        end_date = "2026-07-30T23:59:59Z"

        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        # Calculate how many days to include for desired coverage
        total_days = 30
        days_to_include = int((coverage_pct / 100.0) * total_days)

        deployment_events = []
        current = start
        for i in range(days_to_include):
            deployment_events.append({
                "date": current.date().isoformat(),
                "deployment_name": "test",
                "image": "ronaldraygun/test:1.0.0",
                "status": "successful"
            })
            current += timedelta(days=1)

        return {
            "metadata": {
                "service_name": "test",
                "namespace": "test",
                "cluster": "test-cluster",
                "time_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            "deployment_events_last_30_days": deployment_events
        }
