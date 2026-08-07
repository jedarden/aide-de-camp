#!/usr/bin/env python3
"""
Unit tests for gap detection helper function.

Tests the detect_coverage_gaps function from src.validation.comparison module.
"""

import pytest
from datetime import datetime, timedelta
from src.validation.comparison import detect_coverage_gaps, _parse_timestamp


class TestParseTimestamp:
    """Test timestamp parsing utility function."""

    def test_parse_timestamp_z_suffix(self):
        """Test parsing timestamp with Z suffix."""
        result = _parse_timestamp("2026-08-01T12:00:00Z")
        assert result == datetime(2026, 8, 1, 12, 0, 0)

    def test_parse_timestamp_with_offset(self):
        """Test parsing timestamp with UTC offset."""
        result = _parse_timestamp("2026-08-01T12:00:00+00:00")
        assert result == datetime(2026, 8, 1, 12, 0, 0)

    def test_parse_timestamp_with_milliseconds(self):
        """Test parsing timestamp with milliseconds."""
        result = _parse_timestamp("2026-08-01T12:00:00.123Z")
        assert result == datetime(2026, 8, 1, 12, 0, 0, 123000)

    def test_parse_timestamp_empty_string(self):
        """Test parsing empty timestamp string."""
        with pytest.raises(ValueError, match="Timestamp string cannot be empty"):
            _parse_timestamp("")

    def test_parse_timestamp_invalid_format(self):
        """Test parsing invalid timestamp format."""
        with pytest.raises(ValueError, match="Invalid ISO 8601 timestamp"):
            _parse_timestamp("invalid-timestamp")


class TestDetectCoverageGaps:
    """Test gap detection functionality."""

    def test_empty_deployment_sequence(self):
        """Test with empty deployment list."""
        gaps = detect_coverage_gaps([])
        assert gaps == []

    def test_single_deployment(self):
        """Test with single deployment (cannot detect gaps)."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"}
        ]
        gaps = detect_coverage_gaps(deployments)
        assert gaps == []

    def test_no_gaps_continuous_deployment(self):
        """Test with continuous deployments (no gaps)."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            {"name": "deploy-2", "created_at": "2026-08-02T00:00:00Z"},
            {"name": "deploy-3", "created_at": "2026-08-03T00:00:00Z"},
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        assert len(gaps) == 0

    def test_single_gap_detected(self):
        """Test detection of a single gap."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            {"name": "deploy-2", "created_at": "2026-08-05T00:00:00Z"},  # 4 day gap
            {"name": "deploy-3", "created_at": "2026-08-06T00:00:00Z"},
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        assert len(gaps) == 1

        gap_start, gap_end = gaps[0]
        assert gap_start == datetime(2026, 8, 1, 0, 0, 1)
        assert gap_end == datetime(2026, 8, 4, 23, 59, 59)

    def test_multiple_gaps_detected(self):
        """Test detection of multiple gaps."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            {"name": "deploy-2", "created_at": "2026-08-05T00:00:00Z"},  # Gap 1: 4 days from Aug 1
            {"name": "deploy-3", "created_at": "2026-08-06T00:00:00Z"},
            {"name": "deploy-4", "created_at": "2026-08-15T00:00:00Z"},  # Gap 2: 9 days from Aug 6
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        assert len(gaps) == 2

        # First gap (between Aug 1 and Aug 5)
        gap_start, gap_end = gaps[0]
        assert gap_start == datetime(2026, 8, 1, 0, 0, 1)
        assert gap_end == datetime(2026, 8, 4, 23, 59, 59)

        # Second gap (between Aug 6 and Aug 15)
        gap_start, gap_end = gaps[1]
        assert gap_start == datetime(2026, 8, 6, 0, 0, 1)
        assert gap_end == datetime(2026, 8, 14, 23, 59, 59)

    def test_custom_gap_threshold(self):
        """Test with custom gap threshold."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            {"name": "deploy-2", "created_at": "2026-08-03T00:00:00Z"},  # 2 day gap
        ]

        # With threshold of 3 days, no gap detected
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=3)
        assert len(gaps) == 0

        # With threshold of 1 day, gap detected
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=1)
        assert len(gaps) == 1

    def test_unsorted_timestamps(self):
        """Test with unsorted deployment timestamps."""
        deployments = [
            {"name": "deploy-3", "created_at": "2026-08-06T00:00:00Z"},
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            {"name": "deploy-2", "created_at": "2026-08-05T00:00:00Z"},
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        assert len(gaps) == 1

    def test_missing_timestamp_field(self):
        """Test handling of deployments with missing timestamp field."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            {"name": "deploy-2"},  # Missing timestamp
            {"name": "deploy-3", "created_at": "2026-08-05T00:00:00Z"},
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        # Should detect gap between deploy-1 and deploy-3
        assert len(gaps) == 1

    def test_invalid_timestamp_values(self):
        """Test handling of invalid timestamp values."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            {"name": "deploy-2", "created_at": "invalid-timestamp"},
            {"name": "deploy-3", "created_at": "2026-08-05T00:00:00Z"},
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        # Should skip invalid timestamp and detect gap
        assert len(gaps) == 1

    def test_all_invalid_timestamps(self):
        """Test with all invalid timestamps."""
        deployments = [
            {"name": "deploy-1", "created_at": "invalid-timestamp"},
            {"name": "deploy-2", "created_at": "also-invalid"},
        ]
        gaps = detect_coverage_gaps(deployments)
        assert len(gaps) == 0

    def test_non_dict_deployment_objects(self):
        """Test with non-dict deployment objects."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            "not-a-dict",  # Invalid object
            {"name": "deploy-2", "created_at": "2026-08-05T00:00:00Z"},
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        # Should skip non-dict objects and detect gap
        assert len(gaps) == 1

    def test_custom_timestamp_field(self):
        """Test with custom timestamp field name."""
        deployments = [
            {"name": "deploy-1", "timestamp": "2026-08-01T00:00:00Z"},
            {"name": "deploy-2", "timestamp": "2026-08-05T00:00:00Z"},
        ]
        gaps = detect_coverage_gaps(deployments, timestamp_field="timestamp", gap_threshold_days=2)
        assert len(gaps) == 1

    def test_gap_precision_seconds(self):
        """Test gap detection with sub-day precision."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T12:00:00Z"},
            {"name": "deploy-2", "created_at": "2026-08-01T12:00:10Z"},  # 10 seconds gap
        ]
        # With gap_threshold_days=0, any gap > 0 is detected
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=0)
        assert len(gaps) == 1  # 10 seconds is still a gap with threshold=0

    def test_empty_dict_in_deployment_list(self):
        """Test with empty dict in deployment list."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            {},  # Empty dict
            {"name": "deploy-2", "created_at": "2026-08-05T00:00:00Z"},
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        # Should skip empty dict and detect gap
        assert len(gaps) == 1


class TestGapDetectionIntegration:
    """Integration tests for realistic deployment scenarios."""

    def test_weekly_deployments_no_gaps(self):
        """Test weekly deployment pattern (no gaps)."""
        deployments = [
            {"name": f"deploy-{i}", "created_at": f"2026-08-{i:02d}T00:00:00Z"}
            for i in range(1, 8)  # Aug 1-7
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=2)
        assert len(gaps) == 0

    def test_sparse_deployments_many_gaps(self):
        """Test sparse deployment pattern with many gaps."""
        deployments = [
            {"name": "deploy-1", "created_at": "2026-08-01T00:00:00Z"},
            {"name": "deploy-2", "created_at": "2026-08-15T00:00:00Z"},
            {"name": "deploy-3", "created_at": "2026-08-25T00:00:00Z"},
        ]
        gaps = detect_coverage_gaps(deployments, gap_threshold_days=3)
        assert len(gaps) == 2

        # Check first gap duration (approx 14 days)
        gap_start, gap_end = gaps[0]
        gap_duration = (gap_end - gap_start).days
        assert gap_duration >= 13  # At least 13 days

    def test_30_day_coverage_sample(self):
        """Test realistic 30-day deployment sample."""
        # Simulate deployments every 2-3 days with some breaks
        base_date = datetime(2026, 8, 1)
        deployments = []

        # Add deployments every 2 days (no gaps)
        for i in range(0, 10):
            ts = base_date + timedelta(days=i*2)
            deployments.append({
                "name": f"deploy-{i}",
                "created_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            })

        # Add a 10-day break (gap)
        # Last deployment was day 18, next is day 28
        deployments.append({
            "name": "deploy-final",
            "created_at": (base_date + timedelta(days=28)).strftime("%Y-%m-%dT%H:%M:%SZ")
        })

        gaps = detect_coverage_gaps(deployments, gap_threshold_days=3)
        assert len(gaps) == 1  # One 10-day gap

        gap_start, gap_end = gaps[0]
        gap_duration = (gap_end - gap_start).days
        assert gap_duration >= 9  # At least 9 days gap


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
