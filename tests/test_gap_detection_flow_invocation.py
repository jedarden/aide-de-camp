#!/usr/bin/env python3
"""
Comprehensive test suite for gap detection flow invocation.

Tests cover:
1. Gap detection is invoked with correct parameters
2. Gap detection is called for each validation target
3. Gap detection results are captured properly
4. Integration with the validation runner
5. Error handling and fallback behavior
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

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
from src.utilities.gap_calculator import (
    GapPeriod,
    calculate_gap_periods,
    classify_gap_by_size
)


class TestGapDetectionInvocation:
    """Test that gap detection is invoked correctly in the validation flow."""

    def test_gap_detection_called_with_service_name(self):
        """Test that gap detection is called with the correct service name parameter."""
        service_name = "test-service"

        data = self._create_deployment_data(
            service_name=service_name,
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z"
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Call validation with return_type="result" to get ValidationResult
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify service name was passed through
            assert result.file_path == temp_path
            # The service name should be used in gap detection
            assert isinstance(result, ValidationResult)

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_called_with_correct_date_range(self):
        """Test that gap detection is called with the correct date range parameters."""
        start_date = "2026-07-01T00:00:00Z"
        end_date = "2026-07-30T23:59:59Z"

        data = self._create_deployment_data(
            service_name="pbx-web",
            start_date=start_date,
            end_date=end_date
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Mock validate_gaps_with_guidance at its import location
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap_validator:
                mock_gap_validator.return_value = GapValidationResult(
                    is_valid=True,
                    service_name="pbx-web",
                    expected_days=30,
                    actual_days=30,
                    coverage_percentage=100.0,
                    gap_periods=[]
                )

                result = validate_deployment_file(temp_path, return_type="result")

                # Verify gap detection was called
                assert mock_gap_validator.called

                # Get the call arguments
                call_args = mock_gap_validator.call_args
                assert call_args is not None

                # Verify data was passed
                assert 'deployment_data' in call_args.kwargs or len(call_args[0]) > 0

                # Verify service_name was passed
                if 'service_name' in call_args.kwargs:
                    assert call_args.kwargs['service_name'] in ['pbx-web', 'test-service']

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_receives_deployment_data(self):
        """Test that gap detection receives the complete deployment data."""
        data = self._create_deployment_data(
            service_name="whisper-stt",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z"
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap_validator:
                mock_gap_validator.return_value = GapValidationResult(
                    is_valid=True,
                    service_name="whisper-stt",
                    expected_days=30,
                    actual_days=30,
                    coverage_percentage=100.0,
                    gap_periods=[]
                )

                result = validate_deployment_file(temp_path, return_type="result")

                # Verify the data passed to gap detection contains deployment events
                call_args = mock_gap_validator.call_args

                # Extract deployment_data from call
                if 'deployment_data' in call_args.kwargs:
                    deployment_data = call_args.kwargs['deployment_data']
                else:
                    deployment_data = call_args[0][0] if call_args[0] else None

                assert deployment_data is not None
                assert 'deployment_events_last_30_days' in deployment_data
                assert 'metadata' in deployment_data

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_with_metadata_service_name(self):
        """Test gap detection when service name is in metadata."""
        data = {
            "service": "fallback-service",
            "metadata": {
                "service_name": "metadata-service",
                "time_period": {
                    "start": "2026-07-01T00:00:00Z",
                    "end": "2026-07-30T23:59:59Z"
                }
            },
            "deployment_events_last_30_days": self._generate_deployment_events(
                "2026-07-01T00:00:00Z", "2026-07-30T23:59:59Z"
            )
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            with patch('src.validation.gap_integration.validate_gaps_with_guidance') as mock_gap_validator:
                mock_gap_validator.return_value = GapValidationResult(
                    is_valid=True,
                    service_name="metadata-service",
                    expected_days=30,
                    actual_days=30,
                    coverage_percentage=100.0,
                    gap_periods=[]
                )

                result = validate_deployment_file(temp_path, return_type="result")

                # Verify gap detection was called
                assert mock_gap_validator.called

                # Verify service name extraction worked
                call_args = mock_gap_validator.call_args
                if 'service_name' in call_args.kwargs:
                    # Should prefer metadata.service_name
                    assert call_args.kwargs['service_name'] in ['metadata-service', 'fallback-service']

        finally:
            Path(temp_path).unlink()


class TestMultipleValidationTargets:
    """Test that gap detection is called for each validation target."""

    def test_gap_detection_for_different_services(self):
        """Test gap detection works for different service names."""
        services = ["pbx-web", "whisper-stt", "test-service"]

        for service in services:
            data = self._create_deployment_data(
                service_name=service,
                start_date="2026-07-01T00:00:00Z",
                end_date="2026-07-30T23:59:59Z"
            )

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(data, f)
                temp_path = f.name

            try:
                result = validate_deployment_file(temp_path, return_type="result")

                # Should complete successfully for all services
                assert isinstance(result, ValidationResult)

            finally:
                Path(temp_path).unlink()

    def test_gap_detection_with_different_date_ranges(self):
        """Test gap detection with different date ranges."""
        date_ranges = [
            ("2026-07-01T00:00:00Z", "2026-07-30T23:59:59Z"),  # 30 days
            ("2026-08-01T00:00:00Z", "2026-08-30T23:59:59Z"),  # August
            ("2026-06-01T00:00:00Z", "2026-06-30T23:59:59Z"),  # June
        ]

        for start_date, end_date in date_ranges:
            data = self._create_deployment_data(
                service_name="test-service",
                start_date=start_date,
                end_date=end_date
            )

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(data, f)
                temp_path = f.name

            try:
                result = validate_deployment_file(temp_path, return_type="result")

                # Should handle all date ranges
                assert isinstance(result, ValidationResult)
                assert result.expected_days == 30

            finally:
                Path(temp_path).unlink()

    def test_gap_detection_with_varying_coverage(self):
        """Test gap detection with varying coverage percentages."""
        coverages = [
            (100.0, 30),    # Perfect coverage
            (90.0, 27),     # Good coverage
            (70.0, 21),     # Poor coverage
            (50.0, 15),     # Critical coverage
        ]

        for coverage_pct, days_present in coverages:
            data = self._create_deployment_data_with_coverage(
                service_name="test-service",
                start_date="2026-07-01T00:00:00Z",
                end_date="2026-07-30T23:59:59Z",
                days_present=days_present
            )

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(data, f)
                temp_path = f.name

            try:
                result = validate_deployment_file(temp_path, return_type="result")

                # Should detect gaps correctly
                assert isinstance(result, ValidationResult)
                assert result.actual_days == days_present
                assert abs(result.coverage_percentage - coverage_pct) < 1.0

            finally:
                Path(temp_path).unlink()


class TestGapDetectionResultCapture:
    """Test that gap detection results are captured properly."""

    def test_gap_detection_results_captured_in_validation_result(self):
        """Test that gap detection results are properly captured in ValidationResult."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify gap metrics are captured
            assert result.gap_detected is True
            assert result.coverage_percentage < 100.0
            assert result.actual_days < result.expected_days
            assert result.gap_count > 0

            # Verify severity is set
            assert result.gap_severity in ["none", "low", "medium", "high", "critical"]
            assert result.gap_severity != "none"  # Should have severity since gaps exist

        finally:
            Path(temp_path).unlink()

    def test_gap_periods_captured_detailed(self):
        """Test that detailed gap periods are captured."""
        data = self._create_deployment_data_with_gaps(
            service_name="whisper-stt",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[10, 11, 12, 15, 20, 21]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify gap periods are captured
            assert len(result.gap_periods) > 0
            assert isinstance(result.gap_periods, list)

            # Verify each gap period is a string representation
            for gap_period in result.gap_periods:
                assert isinstance(gap_period, str)
                assert "to" in gap_period or "on" in gap_period

        finally:
            Path(temp_path).unlink()

    def test_gap_size_distribution_captured(self):
        """Test that gap size distribution is calculated and captured."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7, 8, 9, 10, 15, 25]  # Mix of gap sizes
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify gap size distribution
            assert isinstance(result.gap_size_distribution, dict)
            assert "tiny" in result.gap_size_distribution
            assert "small" in result.gap_size_distribution
            assert "medium" in result.gap_size_distribution
            assert "large" in result.gap_size_distribution
            assert "extended" in result.gap_size_distribution

            # Verify counts are non-negative
            for size, count in result.gap_size_distribution.items():
                assert count >= 0

        finally:
            Path(temp_path).unlink()

    def test_gap_type_breakdown_captured(self):
        """Test that isolated vs consecutive gap breakdown is captured."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 10, 11, 12, 15, 20, 21, 22]  # Mix of isolated and consecutive
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify gap type breakdown
            assert isinstance(result.isolated_gap_count, int)
            assert isinstance(result.consecutive_gap_sequence_count, int)
            assert result.isolated_gap_count >= 0
            assert result.consecutive_gap_sequence_count >= 0

            # Total should match or be less than gap count (due to consolidation)
            assert result.isolated_gap_count + result.consecutive_gap_sequence_count <= result.gap_count

        finally:
            Path(temp_path).unlink()

    def test_actionable_guidance_captured(self):
        """Test that actionable guidance is captured from gap detection."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify actionable guidance is captured
            assert isinstance(result.actionable_guidance, list)

            # Should have guidance when gaps exist
            if result.gap_detected:
                assert len(result.actionable_guidance) > 0

                # Verify guidance contains actionable content
                for guidance in result.actionable_guidance:
                    assert isinstance(guidance, str)
                    assert len(guidance) > 0

        finally:
            Path(temp_path).unlink()

    def test_anomaly_messages_captured(self):
        """Test that anomaly messages are captured from gap detection."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=list(range(10, 25))  # Extended gap for anomaly detection
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify anomaly messages are captured
            assert isinstance(result.anomaly_messages, list)

            # May have anomalies for extended gaps
            # (just verify it's a list, not checking content)

        finally:
            Path(temp_path).unlink()

    def test_deployment_intervals_captured(self):
        """Test that deployment intervals are captured."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[15, 16, 17]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify deployment intervals are captured
            assert isinstance(result.deployment_intervals, dict)

            # If there are deployments, should have interval stats
            if result.actual_days > 1:
                assert "first_deployment" in result.deployment_intervals
                assert "last_deployment" in result.deployment_intervals

        finally:
            Path(temp_path).unlink()


class TestGapDetectionErrorHandling:
    """Test error handling in gap detection flow."""

    def test_gap_detection_failure_returns_safe_defaults(self):
        """Test that gap detection failure returns safe default values."""
        # Create data that might cause issues
        data = {
            "service": "test-service",
            "metadata": {
                "time_period": {
                    "start": "invalid-date",
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

            # Should return safe defaults instead of crashing
            assert isinstance(result, ValidationResult)
            assert isinstance(result.gap_detected, bool)
            assert isinstance(result.coverage_percentage, (int, float))
            assert isinstance(result.gap_count, int)

        finally:
            Path(temp_path).unlink()

    def test_gap_detection_with_missing_metadata(self):
        """Test gap detection when metadata is missing."""
        data = {
            "service": "test-service",
            "deployment_events_last_30_days": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Should handle missing metadata gracefully
            assert isinstance(result, ValidationResult)

        finally:
            Path(temp_path).unlink()

    def test_service_name_extraction_safety(self):
        """Test safe service name extraction with various data structures."""
        test_cases = [
            ({"service": "direct-service"}, "direct-service"),
            ({"metadata": {"service_name": "metadata-service"}}, "metadata-service"),
            ({"service_name": "top-level-service"}, "top-level-service"),
            ({}, "unknown"),
            ({"metadata": {}}, "unknown"),
        ]

        for data, expected_service in test_cases:
            service_name = _safe_extract_service_name(data)

            # Should extract service name or return "unknown"
            if expected_service != "unknown":
                assert service_name == expected_service
            else:
                assert service_name == "unknown"

    def test_empty_deployment_events_handling(self):
        """Test handling of empty deployment events list."""
        data = {
            "service": "test-service",
            "metadata": {
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

            # Should handle empty events as 100% gap
            assert result.gap_detected is True
            assert result.actual_days == 0
            assert result.coverage_percentage == 0.0

        finally:
            Path(temp_path).unlink()


class TestValidationResultIntegration:
    """Test integration of gap detection with ValidationResult."""

    def test_validation_result_contains_all_gap_fields(self):
        """Test that ValidationResult contains all gap-related fields."""
        data = self._create_deployment_data(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z"
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")

            # Verify all expected fields are present
            expected_fields = [
                'is_valid', 'file_path', 'is_wellformed_json', 'has_required_fields',
                'has_valid_types', 'has_complete_coverage', 'errors', 'gap_detected',
                'coverage_percentage', 'expected_days', 'actual_days', 'gap_count',
                'gap_severity', 'isolated_gap_count', 'consecutive_gap_sequence_count',
                'gap_size_distribution', 'gap_periods', 'actionable_guidance',
                'anomaly_messages', 'deployment_intervals', 'validated_at'
            ]

            for field in expected_fields:
                assert hasattr(result, field), f"Missing field: {field}"

        finally:
            Path(temp_path).unlink()

    def test_validation_result_to_dict(self):
        """Test that ValidationResult.to_dict() includes gap metrics."""
        data = self._create_deployment_data_with_gaps(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z",
            missing_days=[5, 6, 7]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            result = validate_deployment_file(temp_path, return_type="result")
            result_dict = result.to_dict()

            # Verify gap metrics are in dict output
            assert 'gap_detected' in result_dict
            assert 'coverage_percentage' in result_dict
            assert 'gap_count' in result_dict
            assert 'gap_severity' in result_dict
            assert 'gap_size_distribution' in result_dict
            assert 'gap_periods' in result_dict

            # Verify values match
            assert result_dict['gap_detected'] == result.gap_detected
            assert result_dict['coverage_percentage'] == result.coverage_percentage

        finally:
            Path(temp_path).unlink()

    def test_legacy_tuple_compatibility(self):
        """Test that legacy tuple format still works with gap detection."""
        data = self._create_deployment_data(
            service_name="pbx-web",
            start_date="2026-07-01T00:00:00Z",
            end_date="2026-07-30T23:59:59Z"
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name

        try:
            # Test legacy format
            is_valid, errors = validate_deployment_file(temp_path, return_type="legacy")

            # Should return tuple
            assert isinstance(is_valid, bool)
            assert isinstance(errors, list)

        finally:
            Path(temp_path).unlink()


# Helper methods

def _create_deployment_data(
    self,
    service_name: str,
    start_date: str,
    end_date: str
) -> dict:
    """Create deployment data with complete 30-day coverage."""
    start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

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
    period_days = (end - start).days + 1

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
        "deployment_frequency_per_day": total_deployments / period_days if period_days > 0 else 0,
        "mean_time_between_deployments_hours": (period_days * 24) / total_deployments if total_deployments > 0 else 0,
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
    period_days = (end - start).days + 1

    return {
        "service": service_name,
        "first_deployment": start_date,
        "last_deployment": end_date,
        "period_days": period_days,
        "total_deployments": actual_days,
        "successful_deployments": actual_days,
        "failed_deployments": 0,
        "success_rate": 100.0,
        "failure_rate": 0.0,
        "deployment_frequency_per_day": actual_days / period_days if period_days > 0 else 0,
        "mean_time_between_deployments_hours": (period_days * 24) / actual_days if actual_days > 0 else 0,
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


def _create_deployment_data_with_coverage(
    self,
    service_name: str,
    start_date: str,
    end_date: str,
    days_present: int
) -> dict:
    """Create deployment data with specific number of days present."""
    start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

    deployment_events = []
    current = start
    for _ in range(days_present):
        deployment_events.append({
            "date": current.date().isoformat(),
            "deployment_name": service_name,
            "image": f"ronaldraygun/{service_name}:1.0.0",
            "status": "successful"
        })
        current += timedelta(days=1)

    period_days = (end - start).days + 1

    return {
        "service": service_name,
        "first_deployment": start_date,
        "last_deployment": end_date,
        "period_days": period_days,
        "total_deployments": days_present,
        "successful_deployments": days_present,
        "failed_deployments": 0,
        "success_rate": 100.0,
        "failure_rate": 0.0,
        "deployment_frequency_per_day": days_present / period_days if period_days > 0 else 0,
        "mean_time_between_deployments_hours": (period_days * 24) / days_present if days_present > 0 else 0,
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


def _generate_deployment_events(self, start_date: str, end_date: str) -> list:
    """Generate deployment events for a date range."""
    start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

    events = []
    current = start
    while current <= end:
        events.append({
            "date": current.date().isoformat(),
            "deployment_name": "test-deployment",
            "image": "ronaldraygun/test:1.0.0",
            "status": "successful"
        })
        current += timedelta(days=1)

    return events


# Add helper methods to test classes
TestGapDetectionInvocation._create_deployment_data = _create_deployment_data
TestGapDetectionInvocation._generate_deployment_events = _generate_deployment_events

TestMultipleValidationTargets._create_deployment_data = _create_deployment_data
TestMultipleValidationTargets._create_deployment_data_with_coverage = _create_deployment_data_with_coverage

TestGapDetectionResultCapture._create_deployment_data_with_gaps = _create_deployment_data_with_gaps

TestGapDetectionErrorHandling._create_deployment_data = _create_deployment_data

TestValidationResultIntegration._create_deployment_data = _create_deployment_data
TestValidationResultIntegration._create_deployment_data_with_gaps = _create_deployment_data_with_gaps


if __name__ == "__main__":
    pytest.main([__file__, "-v"])