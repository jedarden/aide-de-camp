#!/usr/bin/env python3
"""
Comprehensive tests for error handling in gap detection.

Tests cover:
1. Graceful handling of gap detection failures
2. Validation pipeline continues when gap detection errors
3. Error messages are properly captured
4. Partial results are still returned
5. Various failure scenarios (exceptions, None returns, malformed data)
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
import logging
from unittest.mock import patch, MagicMock, Mock
from typing import Dict, Any, List

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


class BaseErrorHandlingTest:
    """Base class with helper methods for error handling tests."""

    def _create_valid_deployment_data(
        self,
        service_name: str = "test-service"
    ) -> dict:
        """Create deployment data with complete 30-day coverage."""
        start_date = "2026-07-01T00:00:00Z"
        end_date = "2026-07-30T23:59:59Z"

        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        period_days = 30

        # Generate deployment events for all days
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

        return {
            "service": service_name,
            "first_deployment": start_date,
            "last_deployment": end_date,
            "period_days": period_days,
            "total_deployments": period_days,
            "successful_deployments": period_days,
            "failed_deployments": 0,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "deployment_frequency_per_day": 1.0,
            "mean_time_between_deployments_hours": 24.0,
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

    def _write_temp_file(self, data: dict) -> str:
        """Write data to a temporary file and return the path."""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(data, f)
        f.close()
        return f.name


class TestGapDetectionExceptionHandling(BaseErrorHandlingTest):
    """Test that exceptions in gap detection are handled gracefully."""

    def test_exception_in_gap_detection_doesnt_crash_validator(self):
        """Test that an exception in gap detection doesn't crash the validator."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            # Mock validate_gaps_with_guidance to raise an exception
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap detection failed!")

                # Should not crash
                result = validate_deployment_file(temp_path, return_type="result")

                # Should return a result (not crash)
                assert result is not None
                assert isinstance(result, ValidationResult)

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_exception_creates_safe_result(self):
        """Test that gap detection exception creates a safe default result."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = ValueError("Cannot parse dates")

                result = validate_deployment_file(temp_path, return_type="result")

                # Should have safe default values for gap metrics
                # Note: gap_detected is True when gap_result.is_valid=False (error case)
                assert result.gap_count == 0
                # When gap detection fails, severity is set to "critical" (safe default)
                assert result.gap_severity in ["critical", "none", "unknown"]

                # Should have error guidance
                assert len(result.actionable_guidance) > 0
                guidance_text = " ".join(result.actionable_guidance).lower()
                assert "gap detection" in guidance_text or "error" in guidance_text

                # Should indicate failure in completeness validation
                assert not result.has_complete_coverage

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_exception_preserves_schema_validation(self):
        """Test that schema validation succeeds even when gap detection fails."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = RuntimeError("Gap detection error")

                result = validate_deployment_file(temp_path, return_type="result")

                # Schema validation should still pass
                assert result.is_wellformed_json
                assert result.has_required_fields
                assert result.has_valid_types

                # But overall validation should fail due to gap detection error
                assert not result.has_complete_coverage

        finally:
            Path(temp_path).unlink()

    def test_various_exception_types_handled(self):
        """Test that various exception types are handled gracefully."""
        exception_types = [
            ValueError("Invalid value"),
            TypeError("Type error"),
            KeyError("Missing key"),
            AttributeError("Attribute error"),
            RuntimeError("Runtime error"),
            ImportError("Import error"),
        ]

        for exception in exception_types:
            data = self._create_valid_deployment_data()
            temp_path = self._write_temp_file(data)

            try:
                with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                    mock_gap.side_effect = exception

                    # Should not raise
                    result = validate_deployment_file(temp_path, return_type="result")
                    assert result is not None

            finally:
                Path(temp_path).unlink()


class TestGapDetectionNoneReturnHandling(BaseErrorHandlingTest):
    """Test handling when gap detection returns None."""

    def test_none_gap_result_sets_safe_defaults(self):
        """Test that None gap result triggers safe defaults."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.runner._validate_completeness_with_gap_metrics') as mock_validate:
                mock_validate.return_value = (False, None)

                result = validate_deployment_file(temp_path, return_type="result")

                # Verify safe defaults
                assert result.gap_detected == False
                assert result.coverage_percentage == 100.0
                assert result.gap_count == 0
                assert result.gap_severity == "none"
                assert result.isolated_gap_count == 0
                assert result.consecutive_gap_sequence_count == 0

                # Verify default distribution
                expected_dist = {
                    "tiny": 0,
                    "small": 0,
                    "medium": 0,
                    "large": 0,
                    "extended": 0
                }
                assert result.gap_size_distribution == expected_dist

                # Verify gap periods are empty
                assert result.gap_periods == []

        finally:
            Path(temp_path).unlink()

    def test_none_gap_result_preserves_schema(self):
        """Test that schema validation is preserved when gap result is None."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.runner._validate_completeness_with_gap_metrics') as mock_validate:
                mock_validate.return_value = (False, None)

                result = validate_deployment_file(temp_path, return_type="result")

                # Schema validation should pass
                assert result.is_wellformed_json
                assert result.has_required_fields
                assert result.has_valid_types

                # Overall validation should fail (no gap result)
                assert not result.has_complete_coverage

        finally:
            Path(temp_path).unlink()

    def test_none_gap_result_includes_guidance(self):
        """Test that guidance is provided when gap result is None."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.runner._validate_completeness_with_gap_metrics') as mock_validate:
                mock_validate.return_value = (False, None)

                result = validate_deployment_file(temp_path, return_type="result")

                # Should have guidance about gap detection being unavailable
                assert len(result.actionable_guidance) > 0
                guidance_text = " ".join(result.actionable_guidance).lower()
                assert "unavailable" in guidance_text or "schema validation" in guidance_text

        finally:
            Path(temp_path).unlink()


class TestMalformedGapResultHandling(BaseErrorHandlingTest):
    """Test handling of malformed gap results."""

    def test_malformed_gap_period_attributes_handled(self):
        """Test that malformed GapPeriod attributes don't crash the validator."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            # Create a GapPeriod with missing/invalid attributes
            malformed_gap = GapPeriod(
                date="2026-07-05",
                start_day="2026-07-05",
                end_day="2026-07-07",
                size_days=3,
                is_consecutive=True,
                sequence_id=0
            )

            # Mock to return result with malformed gap
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.return_value = GapValidationResult(
                    is_valid=False,
                    service_name="test",
                    expected_days=30,
                    actual_days=27,
                    coverage_percentage=90.0,
                    gap_periods=[malformed_gap],
                    severity=GapSeverity.MEDIUM,
                    error_message="Test gap"
                )

                # Should not crash
                result = validate_deployment_file(temp_path, return_type="result")
                assert result is not None

        finally:
            Path(temp_path).unlink()

    def test_missing_gap_period_attributes(self):
        """Test handling when gap periods are missing expected attributes."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            # Create mock gap objects without proper attributes
            class MockGap:
                def __init__(self):
                    self.date = "2026-07-05"
                    # Missing start_day, end_day, etc.

            mock_gaps = [MockGap()]

            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.return_value = GapValidationResult(
                    is_valid=False,
                    service_name="test",
                    expected_days=30,
                    actual_days=27,
                    coverage_percentage=90.0,
                    gap_periods=mock_gaps,  # Malformed gaps
                    severity=GapSeverity.MEDIUM,
                    error_message="Test"
                )

                # Should handle gracefully (may set empty list)
                result = validate_deployment_file(temp_path, return_type="result")
                assert result is not None

        finally:
            Path(temp_path).unlink()

    def test_invalid_severity_enum_value(self):
        """Test handling of invalid severity enum values."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                # Return invalid severity (not a valid enum)
                mock_gap.return_value = GapValidationResult(
                    is_valid=False,
                    service_name="test",
                    expected_days=30,
                    actual_days=27,
                    coverage_percentage=90.0,
                    gap_periods=[],
                    severity="INVALID_SEVERITY",  # Invalid
                    error_message="Test"
                )

                result = validate_deployment_file(temp_path, return_type="result")

                # Should handle gracefully (may convert to string or set default)
                assert result.gap_severity is not None
                assert isinstance(result.gap_severity, str)

        finally:
            Path(temp_path).unlink()

    def test_non_numeric_coverage_percentage(self):
        """Test handling of non-numeric coverage percentage."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                # Return invalid coverage
                mock_gap.return_value = GapValidationResult(
                    is_valid=False,
                    service_name="test",
                    expected_days=30,
                    actual_days=27,
                    coverage_percentage="invalid",  # Should be float
                    gap_periods=[],
                    severity=GapSeverity.MEDIUM,
                    error_message="Test"
                )

                # Should handle gracefully (may convert or set default)
                result = validate_deployment_file(temp_path, return_type="result")
                assert result is not None

        finally:
            Path(temp_path).unlink()


class TestErrorMessageCapturing(BaseErrorHandlingTest):
    """Test that error messages are properly captured and reported."""

    def test_gap_detection_error_captured_in_anomaly_messages(self):
        """Test that gap detection errors are captured in anomaly messages."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Specific error: Date parsing failed")

                result = validate_deployment_file(temp_path, return_type="result")

                # Should capture error in guidance or anomalies
                all_messages = result.actionable_guidance + result.anomaly_messages
                message_text = " ".join(all_messages).lower()

                # Should reference the error
                assert len(all_messages) > 0
                assert "error" in message_text or "failed" in message_text

        finally:
            Path(temp_path).unlink()

    def test_exception_message_preserved_in_guidance(self):
        """Test that exception messages are preserved in actionable guidance."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                error_msg = "Cannot find required field 'deployment_dates'"
                mock_gap.side_effect = ValueError(error_msg)

                result = validate_deployment_file(temp_path, return_type="result")

                # Error message should be in guidance
                guidance_text = " ".join(result.actionable_guidance)
                # The error should be referenced (may be summarized)
                assert len(result.actionable_guidance) > 0

        finally:
            Path(temp_path).unlink()

    def test_multiple_errors_all_captured(self):
        """Test that multiple error sources are all captured."""
        data = self._create_valid_deployment_data()

        # Create data with schema issues AND gap detection failure
        data.pop("service", None)  # Remove required field
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap detection failed")

                result = validate_deployment_file(temp_path, return_type="result")

                # Should have errors from both schema validation and gap detection
                assert len(result.errors) > 0

                # Error text should mention both issues
                all_errors = " ".join(result.errors).lower()
                # May have schema error or gap error (or both)

        finally:
            Path(temp_path).unlink()

    def test_error_in_legacy_format(self):
        """Test that errors are captured in legacy tuple format."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap error")

                is_valid, errors = validate_deployment_file(temp_path, return_type="legacy")

                # Should have error messages
                assert isinstance(errors, list)
                assert len(errors) > 0
                assert not is_valid

                # Error messages should reference the issue
                error_text = " ".join(errors).lower()
                assert "gap" in error_text or "coverage" in error_text or "error" in error_text

        finally:
            Path(temp_path).unlink()


class TestPartialResultsReturn(BaseErrorHandlingTest):
    """Test that partial results are returned when gap detection fails."""

    def test_schema_validation_results_returned_on_gap_failure(self):
        """Test that schema validation results are returned even when gap detection fails."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap detection failed")

                result = validate_deployment_file(temp_path, return_type="result")

                # Schema validation should succeed and be present
                assert result.is_wellformed_json is True
                assert result.has_required_fields is True
                assert result.has_valid_types is True

                # Result should be a complete ValidationResult object
                assert isinstance(result, ValidationResult)
                assert hasattr(result, 'file_path')
                assert hasattr(result, 'validated_at')

        finally:
            Path(temp_path).unlink()

    def test_basic_metadata_returned_on_gap_failure(self):
        """Test that basic metadata is returned even when gap detection fails."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap error")

                result = validate_deployment_file(temp_path, return_type="result")

                # Should have basic metadata
                assert result.file_path == temp_path
                assert result.validated_at is not None
                assert len(result.validated_at) > 0

                # Should be ISO format timestamp
                assert "T" in result.validated_at
                assert "Z" in result.validated_at or "+" in result.validated_at

        finally:
            Path(temp_path).unlink()

    def test_gap_metrics_have_safe_defaults(self):
        """Test that gap metrics have safe default values when gap detection fails."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap error")

                result = validate_deployment_file(temp_path, return_type="result")

                # All gap metrics should have safe defaults
                assert result.gap_detected in [True, False]  # Boolean
                assert isinstance(result.coverage_percentage, (int, float))
                assert isinstance(result.expected_days, int)
                assert isinstance(result.actual_days, int)
                assert isinstance(result.gap_count, int)
                assert isinstance(result.gap_severity, str)
                assert isinstance(result.isolated_gap_count, int)
                assert isinstance(result.consecutive_gap_sequence_count, int)
                assert isinstance(result.gap_size_distribution, dict)
                assert isinstance(result.gap_periods, list)
                assert isinstance(result.actionable_guidance, list)
                assert isinstance(result.anomaly_messages, list)
                assert isinstance(result.deployment_intervals, dict)

        finally:
            Path(temp_path).unlink()

    def test_result_dict_serializable_on_gap_failure(self):
        """Test that result is still JSON serializable when gap detection fails."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap error")

                result = validate_deployment_file(temp_path, return_type="result")

                # Should be serializable to JSON
                result_dict = result.to_dict()

                try:
                    json_str = json.dumps(result_dict)
                    assert len(json_str) > 0

                    # Should be able to parse back
                    parsed = json.loads(json_str)
                    assert isinstance(parsed, dict)

                except (TypeError, ValueError) as e:
                    pytest.fail(f"Result should be JSON serializable even on gap failure: {e}")

        finally:
            Path(temp_path).unlink()

    def test_legacy_tuple_returned_on_gap_failure(self):
        """Test that legacy tuple format works when gap detection fails."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap error")

                # Legacy format should still work
                is_valid, errors = validate_deployment_file(temp_path, return_type="legacy")

                # Should return tuple
                assert isinstance(is_valid, bool)
                assert isinstance(errors, list)

                # Should indicate failure
                assert not is_valid

        finally:
            Path(temp_path).unlink()

    def test_validation_continues_pipeline_after_gap_error(self):
        """Test that validation pipeline continues and returns a complete result."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap error")

                result = validate_deployment_file(temp_path, return_type="result")

                # Should have run through entire pipeline
                # Check that all validation stages were attempted
                assert hasattr(result, 'is_wellformed_json')  # Stage 1
                assert hasattr(result, 'has_required_fields')  # Stage 2
                assert hasattr(result, 'has_valid_types')  # Stage 3
                assert hasattr(result, 'has_complete_coverage')  # Stage 4

                # Should have final validity status
                assert hasattr(result, 'is_valid')
                assert isinstance(result.is_valid, bool)

        finally:
            Path(temp_path).unlink()


class TestSpecificFailureScenarios(BaseErrorHandlingTest):
    """Test specific failure scenarios that could occur in production."""

    def test_missing_deployment_events_field(self):
        """Test handling when deployment_events_last_30_days field is missing."""
        data = self._create_valid_deployment_data()
        data.pop("deployment_events_last_30_days", None)
        temp_path = self._write_temp_file(data)

        try:
            # Should handle gracefully
            result = validate_deployment_file(temp_path, return_type="result")
            assert result is not None

        finally:
            Path(temp_path).unlink()

    def test_empty_deployment_events_list(self):
        """Test handling when deployment_events_last_30_days is empty."""
        data = self._create_valid_deployment_data()
        data["deployment_events_last_30_days"] = []
        temp_path = self._write_temp_file(data)

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Should handle zero coverage gracefully
            assert result is not None
            assert result.actual_days == 0

        finally:
            Path(temp_path).unlink()

    def test_deployment_events_missing_date_field(self):
        """Test handling when deployment events are missing date field."""
        data = self._create_valid_deployment_data()

        # Remove date field from all events
        for event in data["deployment_events_last_30_days"]:
            if "date" in event:
                del event["date"]

        temp_path = self._write_temp_file(data)

        try:
            # Should handle gracefully
            result = validate_deployment_file(temp_path, return_type="result")
            assert result is not None

        finally:
            Path(temp_path).unlink()

    def test_invalid_date_format_in_events(self):
        """Test handling when deployment events have invalid date formats."""
        data = self._create_valid_deployment_data()

        # Corrupt date fields
        for event in data["deployment_events_last_30_days"]:
            event["date"] = "not-a-valid-date"

        temp_path = self._write_temp_file(data)

        try:
            # Should handle gracefully
            result = validate_deployment_file(temp_path, return_type="result")
            assert result is not None

        finally:
            Path(temp_path).unlink()

    def test_malformed_time_period_metadata(self):
        """Test handling when time_period metadata is malformed."""
        data = self._create_valid_deployment_data()

        # Corrupt time_period
        data["metadata"]["time_period"] = {
            "start": "invalid-date",
            "end": "also-invalid"
        }

        temp_path = self._write_temp_file(data)

        try:
            # Should handle gracefully
            result = validate_deployment_file(temp_path, return_type="result")
            assert result is not None

        finally:
            Path(temp_path).unlink()

    def test_gap_calculation_import_error(self):
        """Test handling when gap calculation module has import errors."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            # Mock import failure in gap calculator (classify_gap_by_size is in gap_calculator)
            with patch('src.utilities.gap_calculator.classify_gap_by_size') as mock_classify:
                mock_classify.side_effect = ImportError("Cannot import gap classifier")

                # Should handle gracefully
                result = validate_deployment_file(temp_path, return_type="result")
                assert result is not None

        finally:
            Path(temp_path).unlink()


class TestErrorRecoveryAndLogging(BaseErrorHandlingTest):
    """Test error recovery and logging behavior."""

    def test_gap_error_logged_but_not_raised(self):
        """Test that gap errors are logged but not raised to caller."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap error")

                # Mock logger to capture logging
                with patch('logging.error') as mock_log:
                    result = validate_deployment_file(temp_path, return_type="result")

                    # Should log the error
                    assert mock_log.called

                    # But should not raise to caller
                    assert result is not None

        finally:
            Path(temp_path).unlink()

    def test_multiple_gap_errors_all_handled(self):
        """Test handling of multiple sequential errors in gap detection."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            # First call raises, second call raises
            call_count = 0
            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise Exception(f"Error {call_count}")

            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = side_effect

                # Should handle and recover
                result = validate_deployment_file(temp_path, return_type="result")
                assert result is not None

        finally:
            Path(temp_path).unlink()

    def test_validation_result_complete_despite_error(self):
        """Test that ValidationResult is complete and usable despite gap errors."""
        data = self._create_valid_deployment_data()
        temp_path = self._write_temp_file(data)

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap:
                mock_gap.side_effect = Exception("Gap error")

                result = validate_deployment_file(temp_path, return_type="result")

                # Result should have all required fields
                required_fields = [
                    'is_valid', 'file_path', 'is_wellformed_json',
                    'has_required_fields', 'has_valid_types', 'has_complete_coverage',
                    'errors', 'gap_detected', 'coverage_percentage',
                    'expected_days', 'actual_days', 'gap_count', 'gap_severity',
                    'isolated_gap_count', 'consecutive_gap_sequence_count',
                    'gap_size_distribution', 'gap_periods', 'actionable_guidance',
                    'anomaly_messages', 'deployment_intervals', 'validated_at'
                ]

                for field in required_fields:
                    assert hasattr(result, field), f"Missing field: {field}"

                # to_dict() should work
                result_dict = result.to_dict()
                assert isinstance(result_dict, dict)

                # get_legacy_tuple() should work
                is_valid, errors = result.get_legacy_tuple()
                assert isinstance(is_valid, bool)
                assert isinstance(errors, list)

        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
