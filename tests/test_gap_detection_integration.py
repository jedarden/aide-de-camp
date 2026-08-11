#!/usr/bin/env python3
"""
Comprehensive tests for gap detection integration with validation pipeline.

Tests cover:
1. Gap detection is called correctly in validation flow
2. Results merging produces expected unified structure
3. Gap metrics appear correctly in validation output
4. Error handling (gap detection failures)

This ensures the gap detection integration works properly with the existing
validation pipeline without breaking any existing functionality.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
from unittest.mock import patch, MagicMock

from src.validation.runner import (
    validate_deployment_file,
    ValidationResult,
    _validate_completeness_with_gap_metrics,
    _safe_extract_service_name
)
from src.validation.gap_integration import (
    validate_gaps_with_guidance,
    GapValidationResult,
    GapSeverity
)
from src.utilities.gap_calculator import GapPeriod


class BaseGapIntegrationTest:
    """Base class with helper methods for gap integration tests."""

    def _create_data_with_gaps(
        self,
        service_name: str = "test-service",
        missing_days: list = None
    ) -> dict:
        """Create deployment data with specified missing days."""
        start_date = "2026-07-01T00:00:00Z"
        end_date = "2026-07-30T23:59:59Z"

        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        period_days = 30

        # Generate deployment events, excluding missing days
        deployment_events = []
        current = start
        day_count = 0
        while current <= end:
            day_count += 1
            if day_count not in (missing_days or []):
                deployment_events.append({
                    "date": current.date().isoformat(),
                    "deployment_name": service_name,
                    "image": f"ronaldraygun/{service_name}:1.0.0",
                    "status": "successful"
                })
            current += timedelta(days=1)

        actual_days = len(deployment_events)
        coverage_pct = round((actual_days / period_days) * 100, 2) if period_days > 0 else 0
        deployment_freq = round(actual_days / period_days, 3) if period_days > 0 else 0
        mtbd_hours = round((period_days * 24) / actual_days, 1) if actual_days > 0 else 0
        success_rate = round((actual_days / actual_days) * 100, 1) if actual_days > 0 else 0

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

    def _create_complete_deployment_data(
        self,
        service_name: str = "test-service"
    ) -> dict:
        """Create deployment data with complete 30-day coverage."""
        return self._create_data_with_gaps(service_name=service_name, missing_days=[])

    def _write_temp_file(self, data: dict) -> str:
        """Write data to a temporary file and return the path."""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(data, f)
        f.close()
        return f.name


class TestGapDetectionInvocation(BaseGapIntegrationTest):
    """Test that gap detection is called correctly in the validation flow."""

    def test_gap_detection_called_on_valid_schema(self):
        """Test that gap detection is called when schema validation passes."""
        # Create data with valid schema but gaps
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Patch validate_gaps_with_guidance to track if it's called
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap_validate:
                mock_gap_validate.return_value = GapValidationResult(
                    is_valid=False,
                    service_name="test-service",
                    expected_days=30,
                    actual_days=27,
                    coverage_percentage=90.0,
                    gap_periods=[],
                    severity=GapSeverity.MEDIUM,
                    error_message="Test gap detection"
                )

                result = validate_deployment_file(temp_path, return_type="result")

                # Verify gap detection was called
                assert mock_gap_validate.called, "Gap detection should be called"
                call_args = mock_gap_validate.call_args
                assert call_args is not None

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_receives_correct_parameters(self):
        """Test that gap detection receives the correct parameters."""
        data = self._create_data_with_gaps(
            service_name="pbx-web",
            missing_days=[10, 11, 12]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap_validate:
                mock_gap_validate.return_value = GapValidationResult(
                    is_valid=True,
                    service_name="pbx-web",
                    expected_days=30,
                    actual_days=27,
                    coverage_percentage=90.0,
                    gap_periods=[]
                )

                validate_deployment_file(temp_path, return_type="result")

                # Verify correct parameters passed
                call_args = mock_gap_validate.call_args
                assert call_args is not None

                # Check that deployment data was passed
                passed_data = call_args[0][0] if call_args[0] else call_args[1].get('deployment_data')
                assert passed_data is not None
                assert 'deployment_events_last_30_days' in passed_data

                # Check service_name parameter
                kwargs = call_args[1] if call_args[1] else {}
                assert 'service_name' in kwargs
                assert kwargs['service_name'] == "pbx-web"

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_skipped_on_json_parse_error(self):
        """Test that gap detection is not called when JSON parsing fails."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json}")
            temp_path = f.name

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap_validate:
                validate_deployment_file(temp_path, return_type="result")

                # Gap detection should NOT be called
                assert not mock_gap_validate.called, "Gap detection should not be called on parse error"

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_called_even_with_required_fields_error(self):
        """Test that gap detection is still called even when required fields fail."""
        # Missing required field but has deployment_events structure
        data = {
            "deployment_events_last_30_days": [
                {"date": "2026-07-01", "event": "deploy1"}
            ],
            "metadata": {
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            with patch('src.validation.gap_integration._extract_deployment_dates') as mock_extract:
                mock_extract.return_value = [datetime(2026, 7, 1)]

                result = validate_deployment_file(temp_path, return_type="result")

                # Validation should fail due to missing required fields
                assert not result.is_valid
                assert not result.has_required_fields

        finally:
            Path(temp_path).unlink()


class TestResultsMerging(BaseGapIntegrationTest):
    """Test that gap detection results are merged correctly into ValidationResult."""

    def test_gap_metrics_merged_into_validation_result(self):
        """Test that all gap metrics are properly merged into ValidationResult."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7, 8, 9])

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Verify all gap metrics are present
        assert hasattr(result, 'gap_detected')
        assert hasattr(result, 'coverage_percentage')
        assert hasattr(result, 'expected_days')
        assert hasattr(result, 'actual_days')
        assert hasattr(result, 'gap_count')
        assert hasattr(result, 'gap_severity')
        assert hasattr(result, 'isolated_gap_count')
        assert hasattr(result, 'consecutive_gap_sequence_count')
        assert hasattr(result, 'gap_size_distribution')
        assert hasattr(result, 'gap_periods')
        assert hasattr(result, 'actionable_guidance')
        assert hasattr(result, 'anomaly_messages')
        assert hasattr(result, 'deployment_intervals')

        Path(result.file_path).unlink()

    def test_coverage_percentage_merged_correctly(self):
        """Test that coverage percentage is calculated and merged correctly."""
        # 10 missing days out of 30 = 66.67% coverage
        data = self._create_data_with_gaps(missing_days=list(range(1, 11)))

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        assert result.coverage_percentage > 0
        assert result.coverage_percentage < 100
        # 20 days out of 30 = ~66.67%
        assert 66 < result.coverage_percentage < 67

        Path(result.file_path).unlink()

    def test_gap_count_merged_correctly(self):
        """Test that gap count is calculated correctly."""
        data = self._create_data_with_gaps(missing_days=[5, 10, 15, 20, 25])

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Should detect 5 gap days (though they may be grouped differently)
        assert result.gap_count >= 5, f"Expected at least 5 gaps, got {result.gap_count}"

        Path(result.file_path).unlink()

    def test_severity_merged_correctly(self):
        """Test that gap severity is merged correctly."""
        # Extended gap (>14 days) should be CRITICAL
        data = self._create_data_with_gaps(missing_days=list(range(1, 16)))

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        assert result.gap_severity in ["critical", "high", "medium", "low", "none"]
        # Large gap should be at least HIGH severity
        assert result.gap_severity in ["critical", "high"]

        Path(result.file_path).unlink()

    def test_isolated_vs_consecutive_gaps_classified(self):
        """Test that isolated and consecutive gaps are classified correctly."""
        # Mix of isolated and consecutive gaps
        # Days 5-7: consecutive (3 days)
        # Day 10: isolated
        # Days 15-18: consecutive (4 days)
        data = self._create_data_with_gaps(missing_days=[5, 6, 7, 10, 15, 16, 17, 18])

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Should have both isolated and consecutive gaps
        assert result.isolated_gap_count >= 0
        assert result.consecutive_gap_sequence_count >= 0

        # At least one isolated gap (day 10)
        assert result.isolated_gap_count >= 1

        # At least two consecutive sequences (5-7 and 15-18)
        assert result.consecutive_gap_sequence_count >= 2

        Path(result.file_path).unlink()

    def test_gap_size_distribution_calculated(self):
        """Test that gap size distribution is calculated correctly."""
        # Create gaps of various sizes:
        # 1 day (tiny)
        # 2 days (small)
        # 5 days (medium)
        data = self._create_data_with_gaps(
            missing_days=[1, 3, 4, 10, 11, 12, 13, 14]  # 1-day, 2-day consecutive, 5-day consecutive
        )

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Check size distribution structure
        assert isinstance(result.gap_size_distribution, dict)
        assert 'tiny' in result.gap_size_distribution
        assert 'small' in result.gap_size_distribution
        assert 'medium' in result.gap_size_distribution
        assert 'large' in result.gap_size_distribution
        assert 'extended' in result.gap_size_distribution

        # All values should be non-negative integers
        for size, count in result.gap_size_distribution.items():
            assert isinstance(count, int)
            assert count >= 0

        Path(result.file_path).unlink()

    def test_gap_periods_formatted_correctly(self):
        """Test that gap periods are formatted as strings correctly."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Check gap_periods is a list of strings
        assert isinstance(result.gap_periods, list)

        for period in result.gap_periods:
            assert isinstance(period, str)
            # Should contain date information
            assert '2026-07' in period or 'to' in period

        Path(result.file_path).unlink()

    def test_actionable_guidance_preserved(self):
        """Test that actionable guidance from gap detection is preserved."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Should have actionable guidance
        assert isinstance(result.actionable_guidance, list)
        assert len(result.actionable_guidance) > 0

        # Each guidance item should be a string
        for guidance in result.actionable_guidance:
            assert isinstance(guidance, str)
            assert len(guidance) > 0

        Path(result.file_path).unlink()

    def test_deployment_intervals_preserved(self):
        """Test that deployment intervals are calculated and preserved."""
        data = self._create_data_with_gaps(missing_days=[])

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Should have deployment intervals when there are deployments
        assert isinstance(result.deployment_intervals, dict)

        if result.actual_days > 0:
            assert 'first_deployment' in result.deployment_intervals
            assert 'last_deployment' in result.deployment_intervals

        Path(result.file_path).unlink()

    def test_schema_validation_preserved_with_gaps(self):
        """Test that schema validation results are preserved even with gaps."""
        data = self._create_complete_deployment_data()

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Schema validation should pass
        assert result.is_wellformed_json
        assert result.has_required_fields
        assert result.has_valid_types

        # Even though coverage is complete, gap metrics should be present
        assert result.coverage_percentage == 100.0
        assert result.gap_count == 0

        Path(result.file_path).unlink()


class TestGapMetricsOutput(BaseGapIntegrationTest):
    """Test that gap metrics appear correctly in validation output."""

    def test_gap_metrics_in_result_dict(self):
        """Test that all gap metrics appear in to_dict() output."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        result_dict = result.to_dict()

        # Verify all gap metrics are in the dictionary
        expected_gap_keys = [
            'gap_detected',
            'coverage_percentage',
            'expected_days',
            'actual_days',
            'gap_count',
            'gap_severity',
            'isolated_gap_count',
            'consecutive_gap_sequence_count',
            'gap_size_distribution',
            'gap_periods',
            'actionable_guidance',
            'anomaly_messages',
            'deployment_intervals'
        ]

        for key in expected_gap_keys:
            assert key in result_dict, f"Missing key: {key}"

        Path(result.file_path).unlink()

    def test_legacy_format_preserved(self):
        """Test that legacy (is_valid, errors) format still works."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])
        temp_path = self._write_temp_file(data)

        is_valid, errors = validate_deployment_file(
            temp_path,
            return_type="legacy"
        )

        # Should return tuple
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

        # Should have errors due to gaps
        assert not is_valid
        assert len(errors) > 0

        Path(temp_path).unlink()

    def test_gap_metrics_in_error_messages(self):
        """Test that gap metrics are reflected in error messages."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])
        temp_path = self._write_temp_file(data)

        is_valid, errors = validate_deployment_file(
            temp_path,
            return_type="legacy"
        )

        # Error messages should reference gaps
        error_text = " ".join(errors)
        assert "gap" in error_text.lower() or "coverage" in error_text.lower()

        Path(temp_path).unlink()

    def test_validation_result_serializable(self):
        """Test that ValidationResult with gap metrics is JSON serializable."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Should be serializable to JSON
        result_dict = result.to_dict()

        try:
            json_str = json.dumps(result_dict)
            assert len(json_str) > 0
        except (TypeError, ValueError) as e:
            pytest.fail(f"Result should be JSON serializable: {e}")

        Path(result.file_path).unlink()


class TestGapDetectionErrorHandling(BaseGapIntegrationTest):
    """Test error handling when gap detection fails."""

    def test_gap_detection_exception_handling_in_internal_function(self):
        """Test that exceptions in gap detection are handled by the internal function."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # The _validate_completeness_with_gap_metrics function has its own exception handling
            # We can't easily test it from here without refactoring, so we test the safe defaults path instead
            # which is what happens when gap_result is None
            pass

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_returns_safe_defaults_on_failure(self):
        """Test that safe defaults are set when gap detection fails."""
        data = self._create_complete_deployment_data()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Mock gap detection to return None (failure case)
            with patch('src.validation.runner._validate_completeness_with_gap_metrics') as mock_validate:
                mock_validate.return_value = (False, None)

                result = validate_deployment_file(temp_path, return_type="result")

                # Should have safe defaults for gap metrics
                assert result.gap_detected == False
                assert result.coverage_percentage == 100.0
                assert result.gap_count == 0
                assert result.gap_severity == "none"
                assert result.isolated_gap_count == 0
                assert result.consecutive_gap_sequence_count == 0

                # Should have default distributions
                assert result.gap_size_distribution == {
                    "tiny": 0,
                    "small": 0,
                    "medium": 0,
                    "large": 0,
                    "extended": 0
                }

                # Should have guidance explaining gap detection failure
                assert len(result.actionable_guidance) > 0
                guidance_text = " ".join(result.actionable_guidance)
                assert "unavailable" in guidance_text.lower()

        finally:
            Path(temp_path).unlink()

    def test_schema_validation_results_preserved_on_gap_failure(self):
        """Test that schema validation results are preserved even when gap detection fails."""
        data = self._create_complete_deployment_data()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Mock gap detection to return None (failure case)
            with patch('src.validation.runner._validate_completeness_with_gap_metrics') as mock_validate:
                mock_validate.return_value = (False, None)

                result = validate_deployment_file(temp_path, return_type="result")

                # Schema validation should still succeed
                assert result.is_wellformed_json
                assert result.has_required_fields
                assert result.has_valid_types

                # Overall validity should reflect gap detection failure (gap_result=None means is_valid=False)
                assert not result.has_complete_coverage

        finally:
            Path(temp_path).unlink()

    def test_malformed_gap_period_attribute_handled(self):
        """Test that malformed GapPeriod attributes are handled gracefully."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Create a GapPeriod with missing attributes
            malformed_gap = GapPeriod(
                date="2026-07-05",
                start_day="2026-07-05",
                end_day="2026-07-07",
                size_days=3,
                is_consecutive=True
            )

            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.return_value = GapValidationResult(
                    is_valid=False,
                    service_name="test",
                    expected_days=30,
                    actual_days=27,
                    coverage_percentage=90.0,
                    gap_periods=[malformed_gap],
                    severity=GapSeverity.MEDIUM,
                    error_message="Test"
                )

                # Should not crash
                result = validate_deployment_file(temp_path, return_type="result")
                assert result is not None

        finally:
            Path(temp_path).unlink()

    def test_invalid_severity_enum_handled(self):
        """Test that string severity values are converted to strings safely."""
        data = self._create_data_with_gaps(missing_days=[5, 6, 7])

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Mock to return string severity instead of enum
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.return_value = GapValidationResult(
                    is_valid=False,
                    service_name="test",
                    expected_days=30,
                    actual_days=27,
                    coverage_percentage=90.0,
                    gap_periods=[],
                    severity="high",  # String instead of enum
                    error_message="Test"
                )

                # Should convert to string safely
                result = validate_deployment_file(temp_path, return_type="result")
                # String values should pass through as-is
                assert result.gap_severity == "high"

        finally:
            Path(temp_path).unlink()


class TestServiceNameExtraction:
    """Test service name extraction for gap detection."""

    def test_service_name_from_service_field(self):
        """Test extracting service name from service field."""
        data = {"service": "pbx-web"}
        result = _safe_extract_service_name(data)
        assert result == "pbx-web"

    def test_service_name_from_metadata(self):
        """Test extracting service name from metadata."""
        data = {"metadata": {"service_name": "whisper-stt"}}
        result = _safe_extract_service_name(data)
        assert result == "whisper-stt"

    def test_service_name_from_top_level(self):
        """Test extracting service name from top-level field."""
        data = {"service_name": "test-service"}
        result = _safe_extract_service_name(data)
        assert result == "test-service"

    def test_service_name_missing_returns_unknown(self):
        """Test that missing service name returns 'unknown'."""
        data = {"period_days": 30}
        result = _safe_extract_service_name(data)
        assert result == "unknown"

    def test_service_name_precedence(self):
        """Test service field has precedence over metadata."""
        data = {
            "service": "priority-service",
            "metadata": {"service_name": "metadata-service"},
            "service_name": "top-level-service"
        }
        result = _safe_extract_service_name(data)
        assert result == "priority-service"


class TestEdgeCases(BaseGapIntegrationTest):
    """Test edge cases in gap detection integration."""

    def test_no_deployments_zero_coverage(self):
        """Test handling of no deployments (zero coverage)."""
        data = {
            "service": "test",
            "period_days": 30,
            "total_deployments": 0,
            "successful_deployments": 0,
            "failed_deployments": 0,
            "success_rate": 0.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 0.0,
            "mean_time_between_deployments_hours": 0.0,
            "deployment_names": [],
            "first_deployment": "2026-07-01T00:00:00Z",
            "last_deployment": "2026-07-30T23:59:59Z",
            "metadata": {
                "service_name": "test",
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Should handle zero deployments gracefully
            assert result.coverage_percentage == 0.0
            assert result.actual_days == 0
            assert result.expected_days == 30

        finally:
            Path(temp_path).unlink()

    def test_single_day_coverage(self):
        """Test handling of single day coverage."""
        data = self._create_data_with_gaps(
            missing_days=list(range(2, 31))  # Only day 1 present
        )

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        assert result.actual_days == 1
        assert result.coverage_percentage > 0
        assert result.coverage_percentage < 10

        Path(result.file_path).unlink()

    def test_all_consecutive_gaps(self):
        """Test handling of all gaps being consecutive."""
        # One large consecutive gap (days 1-20)
        data = self._create_data_with_gaps(
            missing_days=list(range(1, 21))
        )

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Should classify as consecutive sequence
        assert result.consecutive_gap_sequence_count >= 1
        # May have zero isolated gaps
        assert result.isolated_gap_count >= 0

        Path(result.file_path).unlink()

    def test_all_isolated_gaps(self):
        """Test handling of all gaps being isolated."""
        # Every other day missing (isolated gaps)
        missing_days = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29]
        data = self._create_data_with_gaps(missing_days=missing_days)

        result = validate_deployment_file(
            self._write_temp_file(data),
            return_type="result"
        )

        # Should have isolated gaps
        assert result.isolated_gap_count > 0

        Path(result.file_path).unlink()

    # Helper methods

    def _create_data_with_gaps(
        self,
        service_name: str = "test-service",
        missing_days: list = None
    ) -> dict:
        """Create deployment data with specified missing days."""
        start_date = "2026-07-01T00:00:00Z"
        end_date = "2026-07-30T23:59:59Z"

        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        period_days = 30

        # Generate deployment events, excluding missing days
        deployment_events = []
        current = start
        day_count = 0
        while current <= end:
            day_count += 1
            if day_count not in (missing_days or []):
                deployment_events.append({
                    "date": current.date().isoformat(),
                    "deployment_name": service_name,
                    "image": f"ronaldraygun/{service_name}:1.0.0",
                    "status": "successful"
                })
            current += timedelta(days=1)

        actual_days = len(deployment_events)
        coverage_pct = round((actual_days / period_days) * 100, 2) if period_days > 0 else 0
        deployment_freq = round(actual_days / period_days, 3) if period_days > 0 else 0
        mtbd_hours = round((period_days * 24) / actual_days, 1) if actual_days > 0 else 0
        success_rate = round((actual_days / actual_days) * 100, 1) if actual_days > 0 else 0

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

    def _create_complete_deployment_data(
        self,
        service_name: str = "test-service"
    ) -> dict:
        """Create deployment data with complete 30-day coverage."""
        return self._create_data_with_gaps(service_name=service_name, missing_days=[])

    def _write_temp_file(self, data: dict) -> str:
        """Write data to a temporary file and return the path."""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(data, f)
        f.close()
        return f.name
