#!/usr/bin/env python3
"""
Unit tests for gap period calculation utilities.

Tests the gap_calculator module from src.utilities.gap_calculator.
Covers various gap scenarios including consecutive, non-consecutive, and edge cases.
"""

import pytest
from datetime import datetime, timedelta
from src.utilities.gap_calculator import (
    GapPeriod,
    calculate_gap_periods,
    _find_consecutive_sequences,
    classify_gap_by_size,
    format_gap_period,
    group_gaps_by_period,
    calculate_coverage_from_gaps,
    detect_anomalies
)


class TestGapPeriod:
    """Test GapPeriod dataclass creation and properties."""

    def test_isolated_gap_period(self):
        """Test creation of an isolated (non-consecutive) gap period."""
        gap = GapPeriod(
            date="2026-08-01",
            start_day="2026-08-01",
            end_day="2026-08-01",
            size_days=1,
            is_consecutive=False,
            sequence_id=None
        )

        assert gap.date == "2026-08-01"
        assert gap.start_day == "2026-08-01"
        assert gap.end_day == "2026-08-01"
        assert gap.size_days == 1
        assert gap.is_consecutive is False
        assert gap.sequence_id is None

    def test_consecutive_gap_period(self):
        """Test creation of a consecutive gap period."""
        gap = GapPeriod(
            date="2026-08-02",
            start_day="2026-08-01",
            end_day="2026-08-05",
            size_days=5,
            is_consecutive=True,
            sequence_id=0
        )

        assert gap.date == "2026-08-02"
        assert gap.start_day == "2026-08-01"
        assert gap.end_day == "2026-08-05"
        assert gap.size_days == 5
        assert gap.is_consecutive is True
        assert gap.sequence_id == 0


class TestFindConsecutiveSequences:
    """Test consecutive sequence detection logic."""

    def test_empty_gaps_list(self):
        """Test with empty gaps list."""
        sequences = _find_consecutive_sequences([])
        assert sequences == []

    def test_single_gap(self):
        """Test with a single gap (forms one sequence)."""
        gaps = [{"date": "2026-08-01"}]
        sequences = _find_consecutive_sequences(gaps)
        assert len(sequences) == 1
        assert len(sequences[0]) == 1
        assert sequences[0][0]["date"] == "2026-08-01"

    def test_two_consecutive_gaps(self):
        """Test with two consecutive gaps (one day apart)."""
        gaps = [
            {"date": "2026-08-01"},
            {"date": "2026-08-02"}
        ]
        sequences = _find_consecutive_sequences(gaps)
        assert len(sequences) == 1
        assert len(sequences[0]) == 2

    def test_two_non_consecutive_gaps(self):
        """Test with two non-consecutive gaps (more than one day apart)."""
        gaps = [
            {"date": "2026-08-01"},
            {"date": "2026-08-05"}  # 4 day gap
        ]
        sequences = _find_consecutive_sequences(gaps)
        assert len(sequences) == 2
        assert len(sequences[0]) == 1
        assert len(sequences[1]) == 1

    def test_mixed_consecutive_and_isolated(self):
        """Test with both consecutive sequences and isolated gaps."""
        gaps = [
            {"date": "2026-08-01"},
            {"date": "2026-08-02"},  # Consecutive with previous
            {"date": "2026-08-05"},  # Isolated
            {"date": "2026-08-10"},
            {"date": "2026-08-11"},  # Consecutive with previous
            {"date": "2026-08-12"}   # Consecutive with previous
        ]
        sequences = _find_consecutive_sequences(gaps)
        assert len(sequences) == 3
        assert len(sequences[0]) == 2  # Aug 1-2
        assert len(sequences[1]) == 1  # Aug 5
        assert len(sequences[2]) == 3  # Aug 10-12

    def test_unsorted_gaps(self):
        """Test with unsorted gaps (should handle properly)."""
        gaps = [
            {"date": "2026-08-05"},
            {"date": "2026-08-01"},
            {"date": "2026-08-03"}
        ]
        # Note: calculate_gap_periods sorts before calling this function
        # This test verifies the function itself expects sorted input
        sequences = _find_consecutive_sequences(gaps)
        # With unsorted input, it won't detect consecutiveness correctly
        # This is expected behavior - sorting happens upstream
        assert len(sequences) == 3  # Treats all as isolated


class TestCalculateGapPeriods:
    """Test the main calculate_gap_periods function."""

    def test_empty_gaps_list(self):
        """Test with empty gaps list."""
        gaps = []
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 10)

        gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

        assert gap_periods == []
        assert summary["total_gaps"] == 0
        assert summary["isolated_gaps"] == 0
        assert summary["consecutive_sequences"] == 0

    def test_single_isolated_gap(self):
        """Test with a single isolated gap."""
        gaps = [{"date": "2026-08-05"}]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 10)

        gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

        assert len(gap_periods) == 1
        assert gap_periods[0].date == "2026-08-05"
        assert gap_periods[0].start_day == "2026-08-05"
        assert gap_periods[0].end_day == "2026-08-05"
        assert gap_periods[0].size_days == 1
        assert gap_periods[0].is_consecutive is False
        assert gap_periods[0].sequence_id is None
        assert summary["total_gaps"] == 1
        assert summary["isolated_gaps"] == 1
        assert summary["consecutive_sequences"] == 0

    def test_two_consecutive_gaps(self):
        """Test with two consecutive gaps (Aug 1 and Aug 2)."""
        gaps = [
            {"date": "2026-08-01"},
            {"date": "2026-08-02"}
        ]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 10)

        gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

        assert len(gap_periods) == 2
        # Both gaps should share the same sequence bounds
        assert gap_periods[0].start_day == "2026-08-01"
        assert gap_periods[0].end_day == "2026-08-02"
        assert gap_periods[0].size_days == 2
        assert gap_periods[0].is_consecutive is True
        assert gap_periods[0].sequence_id == 0

        assert gap_periods[1].start_day == "2026-08-01"
        assert gap_periods[1].end_day == "2026-08-02"
        assert gap_periods[1].size_days == 2
        assert gap_periods[1].is_consecutive is True
        assert gap_periods[1].sequence_id == 0

        assert summary["total_gaps"] == 2
        assert summary["isolated_gaps"] == 0
        assert summary["consecutive_sequences"] == 1

    def test_long_consecutive_sequence(self):
        """Test with a long consecutive sequence (5 consecutive days)."""
        gaps = [
            {"date": "2026-08-01"},
            {"date": "2026-08-02"},
            {"date": "2026-08-03"},
            {"date": "2026-08-04"},
            {"date": "2026-08-05"}
        ]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 10)

        gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

        assert len(gap_periods) == 5
        # All gaps should share the same sequence bounds
        for gap in gap_periods:
            assert gap.start_day == "2026-08-01"
            assert gap.end_day == "2026-08-05"
            assert gap.size_days == 5
            assert gap.is_consecutive is True
            assert gap.sequence_id == 0

        assert summary["total_gaps"] == 5
        assert summary["isolated_gaps"] == 0
        assert summary["consecutive_sequences"] == 1

    def test_multiple_consecutive_sequences(self):
        """Test with multiple separate consecutive sequences."""
        gaps = [
            {"date": "2026-08-01"},
            {"date": "2026-08-02"},  # Sequence 1: 2 days
            {"date": "2026-08-05"},
            {"date": "2026-08-06"},
            {"date": "2026-08-07"}   # Sequence 2: 3 days
        ]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 10)

        gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

        assert len(gap_periods) == 5
        assert summary["total_gaps"] == 5
        assert summary["isolated_gaps"] == 0
        assert summary["consecutive_sequences"] == 2

        # Verify first sequence
        for i in range(2):
            assert gap_periods[i].start_day == "2026-08-01"
            assert gap_periods[i].end_day == "2026-08-02"
            assert gap_periods[i].size_days == 2
            assert gap_periods[i].sequence_id == 0

        # Verify second sequence
        for i in range(2, 5):
            assert gap_periods[i].start_day == "2026-08-05"
            assert gap_periods[i].end_day == "2026-08-07"
            assert gap_periods[i].size_days == 3
            assert gap_periods[i].sequence_id == 1

    def test_mixed_consecutive_and_isolated_gaps(self):
        """Test with both consecutive sequences and isolated gaps."""
        gaps = [
            {"date": "2026-08-01"},
            {"date": "2026-08-02"},  # Consecutive: Aug 1-2
            {"date": "2026-08-05"},  # Isolated
            {"date": "2026-08-10"},
            {"date": "2026-08-11"},
            {"date": "2026-08-12"}   # Consecutive: Aug 10-12
        ]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 15)

        gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

        assert len(gap_periods) == 6
        assert summary["total_gaps"] == 6
        assert summary["isolated_gaps"] == 1
        assert summary["consecutive_sequences"] == 2

        # Verify isolated gap
        isolated_gap = [gp for gp in gap_periods if not gp.is_consecutive][0]
        assert isolated_gap.date == "2026-08-05"
        assert isolated_gap.size_days == 1

    def test_unsorted_input_gaps(self):
        """Test that unsorted input gaps are handled correctly."""
        gaps = [
            {"date": "2026-08-05"},
            {"date": "2026-08-01"},
            {"date": "2026-08-03"}
        ]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 10)

        gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

        # Should be sorted by date in output
        assert len(gap_periods) == 3
        assert gap_periods[0].date == "2026-08-01"
        assert gap_periods[1].date == "2026-08-03"
        assert gap_periods[2].date == "2026-08-05"

    def test_gap_size_calculation_accuracy(self):
        """Test that gap size calculation is accurate."""
        # Test 1-day sequence
        gaps = [{"date": "2026-08-01"}]
        gap_periods, _ = calculate_gap_periods(gaps, datetime(2026, 8, 1), datetime(2026, 8, 10))
        assert gap_periods[0].size_days == 1

        # Test 7-day sequence
        gaps = [{"date": f"2026-08-{i:02d}"} for i in range(1, 8)]
        gap_periods, _ = calculate_gap_periods(gaps, datetime(2026, 8, 1), datetime(2026, 8, 10))
        assert gap_periods[0].size_days == 7

        # Test 30-day sequence
        gaps = [{"date": f"2026-08-{i:02d}"} for i in range(1, 31)]
        gap_periods, _ = calculate_gap_periods(gaps, datetime(2026, 8, 1), datetime(2026, 8, 30))
        assert gap_periods[0].size_days == 30

    def test_summary_statistics_calculation(self):
        """Test that summary statistics are calculated correctly."""
        gaps = [
            {"date": "2026-08-01"},
            {"date": "2026-08-02"},  # Consecutive: 2 days
            {"date": "2026-08-05"},  # Isolated: 1 day
            {"date": "2026-08-10"},
            {"date": "2026-08-11"},
            {"date": "2026-08-12"},
            {"date": "2026-08-13"},
            {"date": "2026-08-14"},
            {"date": "2026-08-15"}   # Consecutive: 6 days
        ]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 31)

        gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

        assert summary["total_gaps"] == 9
        assert summary["isolated_gaps"] == 1
        assert summary["consecutive_sequences"] == 2
        assert summary["longest_gap_days"] == 6  # Longest sequence
        assert summary["longest_gap_start"] == "2026-08-10"
        assert summary["longest_gap_end"] == "2026-08-15"
        assert summary["total_analysis_days"] == 31  # Aug 1-31
        assert 0 < summary["gap_intensity"] < 1  # Should be between 0 and 1

    def test_boundary_gap_at_period_start(self):
        """Test gap at the very start of the analysis period."""
        gaps = [{"date": "2026-08-01"}]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 10)

        gap_periods, _ = calculate_gap_periods(gaps, start_date, end_date)

        assert gap_periods[0].date == "2026-08-01"
        assert gap_periods[0].start_day == "2026-08-01"

    def test_boundary_gap_at_period_end(self):
        """Test gap at the very end of the analysis period."""
        gaps = [{"date": "2026-08-31"}]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 31)

        gap_periods, _ = calculate_gap_periods(gaps, start_date, end_date)

        assert gap_periods[0].date == "2026-08-31"
        assert gap_periods[0].end_day == "2026-08-31"

    def test_thirty_day_analysis_period(self):
        """Test with a full 30-day analysis period."""
        # Create gaps on days 5, 6, 7 (consecutive) and day 15 (isolated)
        gaps = [
            {"date": "2026-08-05"},
            {"date": "2026-08-06"},
            {"date": "2026-08-07"},
            {"date": "2026-08-15"}
        ]
        start_date = datetime(2026, 8, 1)
        end_date = datetime(2026, 8, 30)

        gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

        assert summary["total_gaps"] == 4
        assert summary["total_analysis_days"] == 30
        assert summary["gap_intensity"] == round(4 / 30, 4)


class TestClassifyGapBySize:
    """Test gap size classification."""

    def test_tiny_gap_classification(self):
        """Test that 1-day gaps are classified as 'tiny'."""
        gap = GapPeriod(
            date="2026-08-01",
            start_day="2026-08-01",
            end_day="2026-08-01",
            size_days=1,
            is_consecutive=False
        )
        assert classify_gap_by_size(gap) == "tiny"

    def test_small_gap_classification(self):
        """Test that 2-3 day gaps are classified as 'small'."""
        # 2-day gap
        gap = GapPeriod(
            date="2026-08-01",
            start_day="2026-08-01",
            end_day="2026-08-02",
            size_days=2,
            is_consecutive=True
        )
        assert classify_gap_by_size(gap) == "small"

        # 3-day gap
        gap.size_days = 3
        assert classify_gap_by_size(gap) == "small"

    def test_medium_gap_classification(self):
        """Test that 4-7 day gaps are classified as 'medium'."""
        gap = GapPeriod(
            date="2026-08-01",
            start_day="2026-08-01",
            end_day="2026-08-05",
            size_days=5,
            is_consecutive=True
        )
        assert classify_gap_by_size(gap) == "medium"

    def test_large_gap_classification(self):
        """Test that 8-14 day gaps are classified as 'large'."""
        gap = GapPeriod(
            date="2026-08-01",
            start_day="2026-08-01",
            end_day="2026-08-10",
            size_days=10,
            is_consecutive=True
        )
        assert classify_gap_by_size(gap) == "large"

    def test_extended_gap_classification(self):
        """Test that >14 day gaps are classified as 'extended'."""
        gap = GapPeriod(
            date="2026-08-01",
            start_day="2026-08-01",
            end_day="2026-08-20",
            size_days=20,
            is_consecutive=True
        )
        assert classify_gap_by_size(gap) == "extended"


class TestFormatGapPeriod:
    """Test gap period formatting for human-readable output."""

    def test_format_isolated_gap(self):
        """Test formatting an isolated gap."""
        gap = GapPeriod(
            date="2026-08-05",
            start_day="2026-08-05",
            end_day="2026-08-05",
            size_days=1,
            is_consecutive=False
        )

        formatted = format_gap_period(gap)

        assert "2026-08-05" in formatted
        assert "1 day" in formatted
        assert "isolated" in formatted
        assert "tiny" in formatted

    def test_format_consecutive_gap(self):
        """Test formatting a consecutive gap."""
        gap = GapPeriod(
            date="2026-08-02",
            start_day="2026-08-01",
            end_day="2026-08-05",
            size_days=5,
            is_consecutive=True,
            sequence_id=0
        )

        formatted = format_gap_period(gap)

        assert "2026-08-02" in formatted
        assert "5-day consecutive sequence" in formatted
        assert "2026-08-01" in formatted
        assert "2026-08-05" in formatted
        assert "medium" in formatted  # 5 days = medium (4-7 days)

    def test_format_extended_gap(self):
        """Test formatting an extended gap."""
        gap = GapPeriod(
            date="2026-08-10",
            start_day="2026-08-01",
            end_day="2026-08-20",
            size_days=20,
            is_consecutive=True,
            sequence_id=0
        )

        formatted = format_gap_period(gap)

        assert "20-day consecutive sequence" in formatted
        assert "extended" in formatted


class TestGroupGapsByPeriod:
    """Test grouping gaps by their period."""

    def test_group_isolated_gaps(self):
        """Test grouping isolated gaps (each has its own period)."""
        gaps = [
            GapPeriod("2026-08-01", "2026-08-01", "2026-08-01", 1, False, None),
            GapPeriod("2026-08-05", "2026-08-05", "2026-08-05", 1, False, None),
            GapPeriod("2026-08-10", "2026-08-10", "2026-08-10", 1, False, None)
        ]

        groups = group_gaps_by_period(gaps)

        assert len(groups) == 3
        # Each gap should be in its own group
        for gap in gaps:
            key = f"{gap.start_day}_to_{gap.end_day}"
            assert key in groups
            assert len(groups[key]) == 1

    def test_group_consecutive_gaps(self):
        """Test grouping consecutive gaps (share same period)."""
        gaps = [
            GapPeriod("2026-08-01", "2026-08-01", "2026-08-03", 3, True, 0),
            GapPeriod("2026-08-02", "2026-08-01", "2026-08-03", 3, True, 0),
            GapPeriod("2026-08-03", "2026-08-01", "2026-08-03", 3, True, 0)
        ]

        groups = group_gaps_by_period(gaps)

        assert len(groups) == 1
        key = "2026-08-01_to_2026-08-03"
        assert key in groups
        assert len(groups[key]) == 3

    def test_group_mixed_gaps(self):
        """Test grouping mixed consecutive and isolated gaps."""
        gaps = [
            GapPeriod("2026-08-01", "2026-08-01", "2026-08-02", 2, True, 0),
            GapPeriod("2026-08-02", "2026-08-01", "2026-08-02", 2, True, 0),
            GapPeriod("2026-08-05", "2026-08-05", "2026-08-05", 1, False, None),
            GapPeriod("2026-08-10", "2026-08-10", "2026-08-12", 3, True, 1),
            GapPeriod("2026-08-11", "2026-08-10", "2026-08-12", 3, True, 1),
            GapPeriod("2026-08-12", "2026-08-10", "2026-08-12", 3, True, 1)
        ]

        groups = group_gaps_by_period(gaps)

        assert len(groups) == 3  # 2 consecutive sequences + 1 isolated
        assert len(groups["2026-08-01_to_2026-08-02"]) == 2
        assert len(groups["2026-08-05_to_2026-08-05"]) == 1
        assert len(groups["2026-08-10_to_2026-08-12"]) == 3


class TestCalculateCoverageFromGaps:
    """Test coverage calculation from gap information."""

    def test_full_coverage_no_gaps(self):
        """Test coverage calculation with no gaps."""
        coverage = calculate_coverage_from_gaps(expected_days=30, gap_count=0)

        assert coverage["expected_days"] == 30
        assert coverage["days_with_data"] == 30
        assert coverage["days_with_gaps"] == 0
        assert coverage["coverage_percentage"] == 100.0
        assert coverage["gap_percentage"] == 0.0

    def test_partial_coverage_with_gaps(self):
        """Test coverage calculation with some gaps."""
        coverage = calculate_coverage_from_gaps(expected_days=30, gap_count=5)

        assert coverage["expected_days"] == 30
        assert coverage["days_with_data"] == 25
        assert coverage["days_with_gaps"] == 5
        assert coverage["coverage_percentage"] == 83.33
        assert coverage["gap_percentage"] == 16.67

    def test_zero_expected_days(self):
        """Test coverage calculation with zero expected days."""
        coverage = calculate_coverage_from_gaps(expected_days=0, gap_count=0)

        assert coverage["expected_days"] == 0
        assert coverage["days_with_data"] == 0
        assert coverage["coverage_percentage"] == 0.0
        assert coverage["gap_percentage"] == 0.0

    def test_complete_coverage_loss(self):
        """Test coverage calculation when all days are gaps."""
        coverage = calculate_coverage_from_gaps(expected_days=30, gap_count=30)

        assert coverage["expected_days"] == 30
        assert coverage["days_with_data"] == 0
        assert coverage["days_with_gaps"] == 30
        assert coverage["coverage_percentage"] == 0.0
        assert coverage["gap_percentage"] == 100.0


class TestDetectAnomalies:
    """Test anomaly detection in gap patterns."""

    def test_no_anomalies_with_healthy_gaps(self):
        """Test that healthy gap patterns produce no anomalies."""
        gap_periods = [
            GapPeriod("2026-08-05", "2026-08-05", "2026-08-05", 1, False),
            GapPeriod("2026-08-10", "2026-08-10", "2026-08-10", 1, False)
        ]
        summary = {
            "total_gaps": 2,
            "gap_intensity": 0.1,
            "longest_gap_days": 1
        }

        anomalies = detect_anomalies(gap_periods, summary)
        assert len(anomalies) == 0

    def test_detect_extended_gaps(self):
        """Test detection of extended gaps (>14 days)."""
        gap_periods = [
            GapPeriod("2026-08-01", "2026-08-01", "2026-08-20", 20, True)
        ]
        summary = {
            "total_gaps": 1,
            "gap_intensity": 0.5,
            "longest_gap_days": 20
        }

        anomalies = detect_anomalies(gap_periods, summary)
        assert len(anomalies) == 1
        assert "extended gap" in anomalies[0].lower()
        assert "20 days" in anomalies[0]

    def test_detect_high_gap_intensity(self):
        """Test detection of high gap intensity (>0.5)."""
        gap_periods = [
            GapPeriod(f"2026-08-{i}", f"2026-08-{i}", f"2026-08-{i}", 1, False)
            for i in range(1, 16)  # 15 gaps out of 30 days = 0.5 intensity
        ]
        summary = {
            "total_gaps": 15,
            "gap_intensity": 0.6,  # > 0.5 threshold
            "longest_gap_days": 1
        }

        anomalies = detect_anomalies(gap_periods, summary)
        assert len(anomalies) == 1
        assert "high gap intensity" in anomalies[0].lower()
        assert "60.00%" in anomalies[0]

    def test_detect_consecutive_gap_dominance(self):
        """Test detection when consecutive gaps dominate (>70%)."""
        # Create 10 total gaps: 8 consecutive, 2 isolated
        # 8/10 = 80% > 70% threshold
        gap_periods = [
            # Consecutive sequence 1: 3 gaps
            GapPeriod("2026-08-01", "2026-08-01", "2026-08-03", 3, True, 0),
            GapPeriod("2026-08-02", "2026-08-01", "2026-08-03", 3, True, 0),
            GapPeriod("2026-08-03", "2026-08-01", "2026-08-03", 3, True, 0),
            # Isolated gaps
            GapPeriod("2026-08-05", "2026-08-05", "2026-08-05", 1, False),
            GapPeriod("2026-08-08", "2026-08-08", "2026-08-08", 1, False),
            # Consecutive sequence 2: 5 gaps
            GapPeriod("2026-08-10", "2026-08-10", "2026-08-14", 5, True, 1),
            GapPeriod("2026-08-11", "2026-08-10", "2026-08-14", 5, True, 1),
            GapPeriod("2026-08-12", "2026-08-10", "2026-08-14", 5, True, 1),
            GapPeriod("2026-08-13", "2026-08-10", "2026-08-14", 5, True, 1),
            GapPeriod("2026-08-14", "2026-08-10", "2026-08-14", 5, True, 1)
        ]
        summary = {
            "total_gaps": 10,
            "gap_intensity": 0.33,
            "longest_gap_days": 5
        }

        anomalies = detect_anomalies(gap_periods, summary)
        assert len(anomalies) == 1
        assert "consecutive gaps dominate" in anomalies[0].lower()
        assert "8/10" in anomalies[0]

    def test_multiple_anomalies_detected(self):
        """Test detection of multiple simultaneous anomalies."""
        # Create gap periods where consecutive gaps dominate (>70%)
        # 15 consecutive gaps out of 20 total = 75% consecutive
        gap_periods = [
            # Extended consecutive gap (15 gaps)
            GapPeriod(f"2026-08-{i}", "2026-08-01", "2026-08-15", 15, True, 0)
            for i in range(1, 16)  # Days 1-15
        ] + [
            # 5 isolated gaps to reach 20 total
            GapPeriod(f"2026-08-{i}", f"2026-08-{i}", f"2026-08-{i}", 1, False)
            for i in range(20, 25)  # Days 20-24
        ]

        summary = {
            "total_gaps": 20,  # High intensity
            "gap_intensity": 0.8,  # High intensity
            "longest_gap_days": 15  # Extended consecutive gap
        }

        anomalies = detect_anomalies(gap_periods, summary)
        # Should detect: extended gaps + high intensity + consecutive dominance
        assert len(anomalies) == 3


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_gap_february_28_to_march_1(self):
        """Test gap spanning February 28 to March 1 (non-leap year)."""
        gaps = [
            {"date": "2026-02-28"},
            {"date": "2026-03-01"}
        ]
        start_date = datetime(2026, 2, 1)
        end_date = datetime(2026, 3, 31)

        gap_periods, _ = calculate_gap_periods(gaps, start_date, end_date)

        # Should detect these as consecutive
        assert len(gap_periods) == 2
        assert gap_periods[0].is_consecutive is True
        assert gap_periods[0].size_days == 2

    def test_gap_leap_year_february_29(self):
        """Test gap including February 29 in a leap year."""
        gaps = [
            {"date": "2024-02-28"},
            {"date": "2024-02-29"},
            {"date": "2024-03-01"}
        ]
        start_date = datetime(2024, 2, 1)
        end_date = datetime(2024, 3, 31)

        gap_periods, _ = calculate_gap_periods(gaps, start_date, end_date)

        # Should detect all three as consecutive
        assert len(gap_periods) == 3
        for gap in gap_periods:
            assert gap.is_consecutive is True
        assert gap_periods[0].size_days == 3

    def test_year_boundary_gap(self):
        """Test gap spanning year boundary."""
        gaps = [
            {"date": "2025-12-31"},
            {"date": "2026-01-01"}
        ]
        start_date = datetime(2025, 12, 1)
        end_date = datetime(2026, 1, 31)

        gap_periods, _ = calculate_gap_periods(gaps, start_date, end_date)

        # Should detect these as consecutive
        assert len(gap_periods) == 2
        assert gap_periods[0].is_consecutive is True
        assert gap_periods[0].size_days == 2

    def test_month_end_to_month_start_gap(self):
        """Test gap from month end to next month start."""
        gaps = [
            {"date": "2026-07-31"},
            {"date": "2026-08-01"}
        ]
        start_date = datetime(2026, 7, 1)
        end_date = datetime(2026, 8, 31)

        gap_periods, _ = calculate_gap_periods(gaps, start_date, end_date)

        # Should detect these as consecutive
        assert len(gap_periods) == 2
        assert gap_periods[0].is_consecutive is True
        assert gap_periods[0].size_days == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
