#!/usr/bin/env python3
"""
End-to-End Tests for Gap Validation Pipeline

This test suite validates the complete gap validation flow:
1. Raw deployment data (JSON file) → schema validation → gap detection
2. Gap detection → integration with validation results
3. Integration → formatted error messages with actionable guidance

Test scenarios:
- Perfect coverage (no gaps)
- Isolated missing days
- Consecutive gap sequences
- Extended gaps (>14 days)
- Stale data scenarios
- Edge cases (zero deployments, single day coverage)

Acceptance criteria:
- Full pipeline validated from input to formatted output
- Error messages include actionable guidance
- Deployment interval references in guidance
- Coverage percentage calculations accurate
- Gap severity classification correct
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List

from src.validation.runner import validate_deployment_file
from src.validation.gap_integration import (
    validate_gaps_with_guidance,
    format_gap_validation_result,
    GapValidationResult,
    GapSeverity
)


class TestGapValidationE2E:
    """
    End-to-end tests for the complete gap validation pipeline.

    These tests validate the full flow:
    deployment_data.json → schema_validation → gap_detection → integration → formatted_output
    """

    # ==================== Test: Perfect Coverage ====================

    def test_perfect_coverage_passes_validation_e2e(self):
        """Test that deployment data with perfect 30-day coverage passes full validation."""
        # Create deployment data with complete coverage
        data = self._create_deployment_data(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            coverage_percentage=100.0
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Step 1: Validate file (full pipeline)
            is_valid, errors = validate_deployment_file(temp_path)

            # Step 2: Verify validation passes
            assert is_valid, f"Perfect coverage should pass validation, got errors: {errors}"
            assert len(errors) == 0, f"No errors expected for perfect coverage"

            # Step 3: Verify result object has correct gap metrics
            result = validate_deployment_file(temp_path, return_type="result")
            assert result.gap_detected is False
            assert result.coverage_percentage == 100.0
            assert result.gap_count == 0
            assert result.gap_severity == "none"
            assert result.has_complete_coverage is True

        finally:
            Path(temp_path).unlink()

    # ==================== Test: Isolated Missing Days ====================

    def test_isolated_missing_days_provides_guidance_e2e(self):
        """Test that isolated missing days generate proper guidance through full pipeline."""
        # Create data with isolated gaps (days 5, 10, 15 missing)
        data = self._create_deployment_data_with_missing_days(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 10, 15]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Step 1: Full pipeline validation
            is_valid, errors = validate_deployment_file(temp_path)

            # Step 2: Verify validation fails due to gaps
            assert not is_valid, "Validation should fail with gaps"
            assert len(errors) > 0, "Should have error messages"

            # Step 3: Verify error messages contain actionable guidance
            error_text = "\n".join(errors)
            assert "gap" in error_text.lower() or "coverage" in error_text.lower()

            # Step 4: Verify result object has correct metrics
            result = validate_deployment_file(temp_path, return_type="result")
            assert result.gap_detected is True
            assert result.coverage_percentage < 100.0
            assert result.gap_count >= 3
            assert result.actual_days == 27  # 30 - 3 missing days

            # Step 5: Verify actionable guidance is present and specific
            assert len(result.actionable_guidance) > 0
            guidance_text = "\n".join(result.actionable_guidance)
            assert "deployment" in guidance_text.lower() or "missing" in guidance_text.lower()

        finally:
            Path(temp_path).unlink()

    # ==================== Test: Consecutive Gap Sequences ====================

    def test_consecutive_gaps_provides_sequence_guidance_e2e(self):
        """Test that consecutive gap sequences get proper guidance through full pipeline."""
        # Create data with consecutive gap (days 10-15 missing)
        data = self._create_deployment_data_with_missing_days(
            service_name="whisper-stt",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[10, 11, 12, 13, 14, 15]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Full pipeline validation
            is_valid, errors = validate_deployment_file(temp_path)

            assert not is_valid, "Should fail with consecutive gaps"

            # Verify consecutive gap guidance
            result = validate_deployment_file(temp_path, return_type="result")
            assert result.consecutive_gap_sequence_count >= 1

            # Verify guidance mentions consecutive gaps or sequences
            guidance_text = "\n".join(result.actionable_guidance)
            has_consecutive_guidance = (
                "consecutive" in guidance_text.lower() or
                "sequence" in guidance_text.lower() or
                "extended" in guidance_text.lower()
            )
            assert has_consecutive_guidance, "Should mention consecutive gap sequence"

        finally:
            Path(temp_path).unlink()

    # ==================== Test: Extended Gaps (>14 days) ====================

    def test_extended_gap_critical_severity_e2e(self):
        """Test that extended gaps (>14 days) generate critical severity through full pipeline."""
        # Create data with extended gap (days 5-20 missing = 16 days)
        data = self._create_deployment_data_with_missing_days(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=list(range(5, 21))  # 16-day gap
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Full pipeline validation
            is_valid, errors = validate_deployment_file(temp_path)

            assert not is_valid, "Should fail with extended gap"

            # Verify critical severity
            result = validate_deployment_file(temp_path, return_type="result")
            assert result.gap_severity in ["critical", "high"], f"Expected critical/high severity, got {result.gap_severity}"

            # Verify coverage is very low
            assert result.coverage_percentage < 60.0, "Coverage should be below 60%"

            # Verify error messages indicate critical severity
            error_text = "\n".join(errors)
            has_critical_or_high = (
                "critical" in error_text.lower() or
                "high" in error_text.lower() or
                result.gap_severity in ["critical", "high"]
            )
            assert has_critical_or_high, "Should indicate critical/high severity"

        finally:
            Path(temp_path).unlink()

    # ==================== Test: Coverage Percentage Calculation ====================

    def test_coverage_percentage_accurate_e2e(self):
        """Test that coverage percentage is calculated accurately through full pipeline."""
        # Create data with known coverage (10 missing days = 66.67% coverage)
        data = self._create_deployment_data_with_missing_days(
            service_name="test-service",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=list(range(1, 11))  # 10 missing days
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Full pipeline validation
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify coverage percentage
            expected_coverage = (20 / 30) * 100  # 20 days out of 30
            assert abs(result.coverage_percentage - expected_coverage) < 1.0, \
                f"Expected coverage ~{expected_coverage}%, got {result.coverage_percentage}%"

            # Verify expected vs actual days
            assert result.expected_days == 30
            assert result.actual_days == 20

            # Verify gap count
            assert result.gap_count == 10

        finally:
            Path(temp_path).unlink()

    # ==================== Test: Deployment Interval References ====================

    def test_deployment_interval_references_in_guidance_e2e(self):
        """Test that guidance references deployment intervals through full pipeline."""
        data = self._create_deployment_data_with_missing_days(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[8, 9, 10]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Full pipeline validation
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify deployment intervals are calculated
            assert result.deployment_intervals is not None
            assert "first_deployment" in result.deployment_intervals
            assert "last_deployment" in result.deployment_intervals
            assert "average_interval_days" in result.deployment_intervals

            # Verify guidance references deployment intervals
            guidance_text = "\n".join(result.actionable_guidance)
            has_interval_reference = (
                "deployment interval" in guidance_text.lower() or
                "days 1-30" in guidance_text.lower() or
                "expected" in guidance_text.lower()
            )
            assert has_interval_reference, "Should reference deployment intervals"

        finally:
            Path(temp_path).unlink()

    # ==================== Test: Error Message Formatting ====================

    def test_formatted_error_message_quality_e2e(self):
        """Test that formatted error messages are high quality through full pipeline."""
        data = self._create_deployment_data_with_missing_days(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7, 8, 9]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Step 1: Validate and get result
            result = validate_deployment_file(temp_path, return_type="result")

            # Step 2: Format the result
            formatted_message = format_gap_validation_result(
                validate_gaps_with_guidance(
                    data,
                    service_name="pbx-web"
                )
            )

            # Step 3: Verify formatted message structure
            assert "Coverage Summary" in formatted_message or "coverage" in formatted_message.lower()
            assert "Deployment Intervals" in formatted_message or "deployment" in formatted_message.lower()
            assert "Actionable Guidance" in formatted_message or "guidance" in formatted_message.lower()
            assert "Expected Coverage" in formatted_message or "expected" in formatted_message.lower()

            # Step 4: Verify service name is included
            assert "pbx-web" in formatted_message

            # Step 5: Verify percentage is shown
            assert "%" in formatted_message or "percent" in formatted_message.lower()

        finally:
            Path(temp_path).unlink()

    # ==================== Test: Stale Data Scenario ====================

    def test_stale_data_scenario_old_last_deployment_e2e(self):
        """Test that stale data (old last deployment) is identified through full pipeline."""
        # Create data where last deployment is very old (simulation of stale data)
        data = self._create_deployment_data_with_missing_days(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=list(range(5, 31))  # Only first 4 days have data
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Full pipeline validation
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify very low coverage detected
            assert result.coverage_percentage < 20.0, "Should detect very low coverage"

            # Verify critical severity
            assert result.gap_severity == "critical", "Should be critical severity"

            # Verify guidance mentions data collection issues
            guidance_text = "\n".join(result.actionable_guidance)
            has_data_collection_guidance = (
                "data collection" in guidance_text.lower() or
                "pipeline" in guidance_text.lower() or
                "verify" in guidance_text.lower()
            )
            assert has_data_collection_guidance, "Should mention data collection issues"

        finally:
            Path(temp_path).unlink()

    # ==================== Test: Edge Cases ====================

    def test_zero_deployments_extreme_gap_e2e(self):
        """Test that zero deployments (extreme gap) is handled through full pipeline."""
        data = self._create_deployment_data_with_missing_days(
            service_name="new-service",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=list(range(1, 31))  # No deployments at all
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Full pipeline validation
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify zero coverage handled gracefully
            assert result.coverage_percentage == 0.0
            assert result.actual_days == 0
            assert result.expected_days == 30

            # Verify critical severity
            assert result.gap_severity == "critical"

            # Verify guidance is actionable despite extreme case
            assert len(result.actionable_guidance) > 0
            guidance_text = "\n".join(result.actionable_guidance)
            assert "deployment" in guidance_text.lower() or "data" in guidance_text.lower()

        finally:
            Path(temp_path).unlink()

    def test_single_day_coverage_minimum_e2e(self):
        """Test that single day coverage (minimum viable) is handled through full pipeline."""
        data = self._create_deployment_data_with_missing_days(
            service_name="test-service",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=list(range(2, 31))  # Only day 1 has data
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Full pipeline validation
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify single day handled
            assert result.actual_days == 1
            assert result.coverage_percentage > 0
            assert result.coverage_percentage < 10

            # Verify critical severity (very low coverage)
            assert result.gap_severity == "critical"

        finally:
            Path(temp_path).unlink()

    # ==================== Test: Gap Severity Classification ====================

    def test_gap_severity_classification_accuracy_e2e(self):
        """Test that gap severity is classified accurately through full pipeline."""
        test_cases = [
            # (missing_days, expected_severity_range)
            ([], "none"),                                    # No gaps
            ([5], "low"),                                    # 1 day gap, 96.67% coverage
            ([5, 6, 7], "medium"),                           # 3 day gap, 90% coverage
            (list(range(5, 12)), "critical"),                # 7 day gap, 76.67% coverage (< 80% = critical)
            (list(range(5, 20)), "critical"),                # 15 day gap, ~50% coverage
        ]

        for missing_days, expected_severity in test_cases:
            data = self._create_deployment_data_with_missing_days(
                service_name="test-service",
                start_date="2026-07-01T00:00:00Z",
                end_date="2026-07-30T23:59:59Z",
                missing_days=missing_days
            )

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(data, f)
                temp_path = f.name

            try:
                result = validate_deployment_file(temp_path, return_type="result")
                assert result.gap_severity == expected_severity, \
                    f"For missing days {len(missing_days)}, expected severity {expected_severity}, got {result.gap_severity}"

            finally:
                Path(temp_path).unlink()

    # ==================== Test: Integration with Validation Suite ====================

    def test_gap_validation_integrates_with_schema_validation_e2e(self):
        """Test that gap validation integrates properly with schema validation."""
        # Create data with both schema issues and gaps
        data = {
            "service": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster",
            # Missing some required fields intentionally
            "metadata": {
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": [
                {"date": "2026-07-01", "event": "deploy1"},
                {"date": "2026-07-02", "event": "deploy2"}
                # Only 2 days out of 30
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Full pipeline validation
            is_valid, errors = validate_deployment_file(temp_path)

            # Should fail due to both schema and gap issues
            assert not is_valid

            # Should have multiple error types
            result = validate_deployment_file(temp_path, return_type="result")

            # Schema validation should fail
            assert not result.has_required_fields or not result.has_valid_types

            # Gap validation should also fail
            assert not result.has_complete_coverage
            assert result.gap_detected is True

        finally:
            Path(temp_path).unlink()

    def test_guidance_quality_specific_actionable_steps_e2e(self):
        """Test that guidance includes specific actionable steps through full pipeline."""
        data = self._create_deployment_data_with_missing_days(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[8, 9, 10, 15, 16, 17]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Full pipeline validation
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify guidance includes actionable verbs
            actionable_verbs = ["add", "check", "verify", "fill", "extend", "review", "investigate"]
            guidance_text = "\n".join(result.actionable_guidance)

            has_actionable_verb = any(verb in guidance_text.lower() for verb in actionable_verbs)
            assert has_actionable_verb, "Guidance should include actionable verbs"

            # Verify guidance mentions specific days or deployment data
            has_specific_reference = (
                "deployment data" in guidance_text.lower() or
                "missing day" in guidance_text.lower() or
                "deployment interval" in guidance_text.lower()
            )
            assert has_specific_reference, "Guidance should reference specific issues"

            # Verify guidance is not generic - should be specific to the gaps
            assert len(result.actionable_guidance) >= 2, "Should have multiple guidance points"

        finally:
            Path(temp_path).unlink()

    # ==================== Helper Methods ====================

    def _create_deployment_data(
        self,
        service_name: str,
        start_date: str,
        end_date: str,
        coverage_percentage: float = 100.0
    ) -> Dict[str, Any]:
        """Create deployment data with specified coverage percentage."""
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        total_days = (end - start).days + 1

        # Calculate how many days to include
        days_to_include = int((coverage_percentage / 100.0) * total_days)

        # Generate deployment events
        deployment_events = []
        current = start
        for i in range(days_to_include):
            deployment_events.append({
                "date": current.date().isoformat(),
                "deployment_name": service_name,
                "image": f"ronaldraygun/{service_name}:1.0.0",
                "status": "successful"
            })
            current += timedelta(days=1)

        return {
            "service": service_name,
            "namespace": service_name,
            "cluster": "ardenone-cluster",
            "first_deployment": start_date,
            "last_deployment": end_date,
            "period_days": total_days,
            "total_deployments": days_to_include,
            "successful_deployments": days_to_include,
            "failed_deployments": 0,
            "success_rate": 100.0 if days_to_include > 0 else 0.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": round(days_to_include / total_days, 3) if total_days > 0 else 0.0,
            "mean_time_between_deployments_hours": round((total_days * 24) / days_to_include, 1) if days_to_include > 0 else 0.0,
            "deployment_names": [service_name],
            "metadata": {
                "service_name": service_name,
                "namespace": service_name,
                "cluster": "ardenone-cluster",
                "time_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            "deployment_events_last_30_days": deployment_events
        }

    def _create_deployment_data_with_missing_days(
        self,
        service_name: str,
        start_date: str,
        end_date: str,
        missing_days: List[int]
    ) -> Dict[str, Any]:
        """Create deployment data with specified missing days."""
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        total_days = (end - start).days + 1

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
        coverage_pct = round((actual_days / total_days) * 100, 2) if total_days > 0 else 0.0
        deployment_freq = round(actual_days / total_days, 3) if total_days > 0 else 0.0
        mtbd_hours = round((total_days * 24) / actual_days, 1) if actual_days > 0 else 0.0

        return {
            "service": service_name,
            "namespace": service_name,
            "cluster": "ardenone-cluster",
            "first_deployment": start_date,
            "last_deployment": end_date,
            "period_days": total_days,
            "total_deployments": actual_days,
            "successful_deployments": actual_days,
            "failed_deployments": 0,
            "success_rate": 100.0 if actual_days > 0 else 0.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": deployment_freq,
            "mean_time_between_deployments_hours": mtbd_hours,
            "deployment_names": [service_name],
            "metadata": {
                "service_name": service_name,
                "namespace": service_name,
                "cluster": "ardenone-cluster",
                "time_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            "deployment_events_last_30_days": deployment_events
        }


class TestGapValidationQualityMetrics:
    """
    Test quality metrics for gap validation error messages.

    Validates that error messages meet quality standards:
    - Clarity: easy to understand
    - Actionability: specific steps to fix
    - Context: explains what's wrong and why
    - Completeness: all necessary information
    """

    def test_error_message_includes_service_name(self):
        """Test that error messages include the service name for context."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7], service_name="pbx-web")

        result = validate_gaps_with_guidance(data, service_name="pbx-web")
        formatted = format_gap_validation_result(result)

        assert "pbx-web" in formatted, "Service name should be in error message"

    def test_error_message_includes_coverage_percentage(self):
        """Test that error messages include coverage percentage."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        result = validate_gaps_with_guidance(data, service_name="test")
        formatted = format_gap_validation_result(result)

        assert "%" in formatted or "percent" in formatted.lower()
        assert "Coverage" in formatted or "coverage" in formatted.lower()

    def test_error_message_includes_gap_count(self):
        """Test that error messages include gap count."""
        data = self._create_data_with_gaps(missing_days=[5, 10, 15, 20, 25])

        result = validate_gaps_with_guidance(data, service_name="test")
        formatted = format_gap_validation_result(result)

        assert "gap" in formatted.lower()

    def test_error_message_includes_severity_indicator(self):
        """Test that error messages include severity level."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7, 8, 9, 10, 11, 12])

        result = validate_gaps_with_guidance(data, service_name="test")
        formatted = format_gap_validation_result(result)

        assert "severity" in formatted.lower() or result.severity.value.lower() in formatted.lower()

    def test_guidance_includes_coverage_threshold(self):
        """Test that guidance includes the coverage threshold (95%)."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7, 8, 9, 10])

        result = validate_gaps_with_guidance(data, service_name="test")
        formatted = format_gap_validation_result(result)

        assert "95%" in formatted or "threshold" in formatted.lower()

    def test_guidance_includes_acceptable_gap_criteria(self):
        """Test that guidance includes acceptable gap criteria."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        result = validate_gaps_with_guidance(data, service_name="test")
        formatted = format_gap_validation_result(result)

        # Should mention acceptable gap sizes (e.g., "≤3 days")
        has_gap_criteria = (
            "3 day" in formatted.lower() or
            "acceptable" in formatted.lower() or
            "critical" in formatted.lower()
        )
        assert has_gap_criteria, "Should mention acceptable gap criteria"

    def _create_data_with_gaps(
        self,
        missing_days: List[int],
        service_name: str = "test"
    ) -> Dict[str, Any]:
        """Helper to create test data with gaps."""
        start_date = "2026-07-01T00:00:00Z"
        end_date = "2026-07-30T23:59:59Z"

        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        total_days = (end - start).days + 1

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

        return {
            "metadata": {
                "service_name": service_name,
                "time_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            "deployment_events_last_30_days": deployment_events
        }
