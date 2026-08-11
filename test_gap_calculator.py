#!/usr/bin/env python3
"""
Unit tests for gap calculator utilities.

Tests various gap scenarios including:
- Single isolated gaps
- Consecutive gaps
- Mixed consecutive and isolated gaps
- Edge cases (no gaps, single gap, etc.)
"""

import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, '/home/coding/aide-de-camp')

from src.utilities.gap_calculator import (
    GapPeriod,
    calculate_gap_periods,
    classify_gap_by_size,
    format_gap_period,
    format_gap_period_detailed,
    format_gap_error_message,
    format_multiple_gaps,
    format_gap_summary,
    format_consecutive_sequence_gaps,
    group_gaps_by_period,
    calculate_coverage_from_gaps,
    detect_anomalies,
    _find_consecutive_sequences,
    _calculate_summary,
    _empty_summary
)


def create_test_gaps(dates):
    """Helper to create test gap dictionaries."""
    return [{"date": date} for date in dates]


def test_single_isolated_gap():
    """Test a single isolated gap."""
    print("Testing single isolated gap...")

    gaps = create_test_gaps(["2026-07-15"])
    start_date = datetime.fromisoformat("2026-07-01")
    end_date = datetime.fromisoformat("2026-07-31")

    gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

    assert len(gap_periods) == 1, f"Expected 1 gap period, got {len(gap_periods)}"
    assert gap_periods[0].date == "2026-07-15"
    assert gap_periods[0].start_day == "2026-07-15"
    assert gap_periods[0].end_day == "2026-07-15"
    assert gap_periods[0].size_days == 1
    assert not gap_periods[0].is_consecutive, "Single gap should not be consecutive"
    assert gap_periods[0].sequence_id is None

    assert summary["total_gaps"] == 1
    assert summary["isolated_gaps"] == 1
    assert summary["consecutive_sequences"] == 0

    print("  ✓ Single isolated gap: PASSED")
    return True


def test_two_consecutive_gaps():
    """Test two consecutive gaps (1 day apart)."""
    print("Testing two consecutive gaps...")

    gaps = create_test_gaps(["2026-07-15", "2026-07-16"])
    start_date = datetime.fromisoformat("2026-07-01")
    end_date = datetime.fromisoformat("2026-07-31")

    gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

    assert len(gap_periods) == 2, f"Expected 2 gap periods, got {len(gap_periods)}"

    # Both gaps should be part of same consecutive sequence
    for gap in gap_periods:
        assert gap.is_consecutive, f"Gap {gap.date} should be consecutive"
        assert gap.start_day == "2026-07-15", f"Expected start 2026-07-15, got {gap.start_day}"
        assert gap.end_day == "2026-07-16", f"Expected end 2026-07-16, got {gap.end_day}"
        assert gap.size_days == 2, f"Expected size 2, got {gap.size_days}"

    assert summary["total_gaps"] == 2
    assert summary["isolated_gaps"] == 0
    assert summary["consecutive_sequences"] == 1
    assert summary["longest_gap_days"] == 2

    print("  ✓ Two consecutive gaps: PASSED")
    return True


def test_mixed_consecutive_and_isolated():
    """Test mixed consecutive and isolated gaps."""
    print("Testing mixed consecutive and isolated gaps...")

    gaps = create_test_gaps([
        "2026-07-05",  # Isolated (1)
        "2026-07-10", "2026-07-11",  # Consecutive pair (2)
        "2026-07-20",  # Isolated (1)
        "2026-07-25", "2026-07-26", "2026-07-27",  # Consecutive triple (3)
        # Total: 1 + 2 + 1 + 3 = 7 gaps
    ])
    start_date = datetime.fromisoformat("2026-07-01")
    end_date = datetime.fromisoformat("2026-07-31")

    gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

    # 7 input dates = 7 gap periods
    assert len(gap_periods) == 7, f"Expected 7 gap periods, got {len(gap_periods)}"

    # Check isolated gaps
    isolated = [gp for gp in gap_periods if not gp.is_consecutive]
    assert len(isolated) == 2, f"Expected 2 isolated gaps, got {len(isolated)}"

    # Check consecutive gaps
    consecutive = [gp for gp in gap_periods if gp.is_consecutive]
    assert len(consecutive) == 5, f"Expected 5 consecutive gaps, got {len(consecutive)}"

    # Verify first consecutive sequence (2 days)
    seq_1 = [gp for gp in consecutive if gp.date in ["2026-07-10", "2026-07-11"]]
    assert len(seq_1) == 2
    assert all(gp.start_day == "2026-07-10" for gp in seq_1)
    assert all(gp.end_day == "2026-07-11" for gp in seq_1)
    assert all(gp.size_days == 2 for gp in seq_1)

    # Verify second consecutive sequence (3 days)
    seq_2 = [gp for gp in consecutive if gp.date in ["2026-07-25", "2026-07-26", "2026-07-27"]]
    assert len(seq_2) == 3
    assert all(gp.start_day == "2026-07-25" for gp in seq_2)
    assert all(gp.end_day == "2026-07-27" for gp in seq_2)
    assert all(gp.size_days == 3 for gp in seq_2)

    assert summary["total_gaps"] == 7
    assert summary["isolated_gaps"] == 2
    assert summary["consecutive_sequences"] == 2
    assert summary["longest_gap_days"] == 3

    print("  ✓ Mixed consecutive and isolated gaps: PASSED")
    return True


def test_extended_consecutive_sequence():
    """Test an extended consecutive sequence (> 7 days)."""
    print("Testing extended consecutive sequence...")

    gaps = create_test_gaps([
        "2026-07-10", "2026-07-11", "2026-07-12", "2026-07-13",
        "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17",
    ])
    start_date = datetime.fromisoformat("2026-07-01")
    end_date = datetime.fromisoformat("2026-07-31")

    gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

    assert len(gap_periods) == 8, f"Expected 8 gap periods, got {len(gap_periods)}"

    # All gaps should be in same consecutive sequence
    assert all(gp.is_consecutive for gp in gap_periods)
    assert all(gp.start_day == "2026-07-10" for gp in gap_periods)
    assert all(gp.end_day == "2026-07-17" for gp in gap_periods)
    assert all(gp.size_days == 8 for gp in gap_periods)

    assert summary["total_gaps"] == 8
    assert summary["consecutive_sequences"] == 1
    assert summary["longest_gap_days"] == 8
    assert summary["longest_gap_start"] == "2026-07-10"
    assert summary["longest_gap_end"] == "2026-07-17"

    print("  ✓ Extended consecutive sequence: PASSED")
    return True


def test_unordered_gaps():
    """Test that gaps are processed correctly regardless of input order."""
    print("Testing unordered gaps...")

    gaps = create_test_gaps([
        "2026-07-15", "2026-07-10", "2026-07-20",  # Unordered
    ])
    start_date = datetime.fromisoformat("2026-07-01")
    end_date = datetime.fromisoformat("2026-07-31")

    gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

    # Should still produce 3 isolated gaps
    assert len(gap_periods) == 3
    assert all(not gp.is_consecutive for gp in gap_periods)
    assert summary["isolated_gaps"] == 3

    # Dates should be in the original input, not sorted
    dates = [gp.date for gp in gap_periods]
    assert "2026-07-15" in dates
    assert "2026-07-10" in dates
    assert "2026-07-20" in dates

    print("  ✓ Unordered gaps: PASSED")
    return True


def test_no_gaps():
    """Test with no gaps (empty list)."""
    print("Testing no gaps...")

    gaps = []
    start_date = datetime.fromisoformat("2026-07-01")
    end_date = datetime.fromisoformat("2026-07-31")

    gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

    assert len(gap_periods) == 0
    assert summary["total_gaps"] == 0
    assert summary["isolated_gaps"] == 0
    assert summary["consecutive_sequences"] == 0
    assert summary["longest_gap_days"] == 0

    print("  ✓ No gaps: PASSED")
    return True


def test_gap_classification():
    """Test gap size classification."""
    print("Testing gap size classification...")

    test_cases = [
        (1, "tiny"),
        (2, "small"),
        (3, "small"),
        (5, "medium"),
        (7, "medium"),
        (10, "large"),
        (14, "large"),
        (15, "extended"),
        (30, "extended"),
    ]

    for size, expected_class in test_cases:
        gap = GapPeriod(
            date="2026-07-15",
            start_day="2026-07-15",
            end_day=f"2026-07-{15+size-1}",
            size_days=size,
            is_consecutive=False
        )
        result = classify_gap_by_size(gap)
        assert result == expected_class, f"Size {size} should be {expected_class}, got {result}"

    print("  ✓ Gap size classification: PASSED")
    return True


def test_gap_formatting():
    """Test basic gap period formatting."""
    print("Testing gap period formatting...")

    # Single-day gap
    single_day = GapPeriod(
        date="2026-07-15",
        start_day="2026-07-15",
        end_day="2026-07-15",
        size_days=1,
        is_consecutive=False
    )
    formatted = format_gap_period(single_day)
    assert formatted == "1-day gap on 2026-07-15", f"Expected '1-day gap on 2026-07-15', got '{formatted}'"

    # Multi-day gap
    multi_day = GapPeriod(
        date="2026-07-16",
        start_day="2026-07-15",
        end_day="2026-07-17",
        size_days=3,
        is_consecutive=True
    )
    formatted = format_gap_period(multi_day)
    assert formatted == "3-day gap from 2026-07-15 to 2026-07-17", f"Expected '3-day gap from 2026-07-15 to 2026-07-17', got '{formatted}'"

    # Extended gap
    extended = GapPeriod(
        date="2026-07-20",
        start_day="2026-07-01",
        end_day="2026-07-20",
        size_days=20,
        is_consecutive=True
    )
    formatted = format_gap_period(extended)
    assert formatted == "20-day gap from 2026-07-01 to 2026-07-20", f"Expected '20-day gap from 2026-07-01 to 2026-07-20', got '{formatted}'"

    print("  ✓ Gap period formatting: PASSED")
    return True


def test_gap_formatting_detailed():
    """Test detailed gap period formatting with classification."""
    print("Testing detailed gap period formatting...")

    # Single-day isolated gap (tiny)
    single_day = GapPeriod(
        date="2026-07-15",
        start_day="2026-07-15",
        end_day="2026-07-15",
        size_days=1,
        is_consecutive=False
    )
    formatted = format_gap_period_detailed(single_day)
    assert "1-day gap on 2026-07-15" in formatted
    assert "isolated" in formatted
    assert "tiny" in formatted

    # Multi-day consecutive gap (small)
    multi_day = GapPeriod(
        date="2026-07-16",
        start_day="2026-07-15",
        end_day="2026-07-17",
        size_days=3,
        is_consecutive=True
    )
    formatted = format_gap_period_detailed(multi_day)
    assert "3-day gap from 2026-07-15 to 2026-07-17" in formatted
    assert "consecutive sequence" in formatted
    assert "small" in formatted

    # Medium consecutive gap
    medium = GapPeriod(
        date="2026-07-16",
        start_day="2026-07-12",
        end_day="2026-07-18",
        size_days=7,
        is_consecutive=True
    )
    formatted = format_gap_period_detailed(medium)
    assert "7-day gap from 2026-07-12 to 2026-07-18" in formatted
    assert "medium" in formatted

    print("  ✓ Detailed gap period formatting: PASSED")
    return True


def test_gap_error_message_formatting():
    """Test gap error message formatting with and without context."""
    print("Testing gap error message formatting...")

    gap = GapPeriod(
        date="2026-07-15",
        start_day="2026-07-15",
        end_day="2026-07-15",
        size_days=1,
        is_consecutive=False
    )

    # Without context
    message = format_gap_error_message(gap)
    assert message == "1-day gap on 2026-07-15"

    # With context
    message = format_gap_error_message(gap, "pbx-web workflow_data")
    assert message == "pbx-web workflow_data: 1-day gap on 2026-07-15"

    # Multi-day gap with context
    multi_gap = GapPeriod(
        date="2026-07-16",
        start_day="2026-07-15",
        end_day="2026-07-19",
        size_days=5,
        is_consecutive=True
    )
    message = format_gap_error_message(multi_gap, "whisper-stt deployment_data")
    assert message == "whisper-stt deployment_data: 5-day gap from 2026-07-15 to 2026-07-19"

    print("  ✓ Gap error message formatting: PASSED")
    return True


def test_multiple_gaps_formatting():
    """Test formatting multiple gaps at once."""
    print("Testing multiple gaps formatting...")

    gaps = [
        GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False),
        GapPeriod("2026-07-15", "2026-07-15", "2026-07-17", 3, True),
        GapPeriod("2026-07-20", "2026-07-20", "2026-07-22", 3, True),
    ]

    # Format without context
    messages = format_multiple_gaps(gaps)
    assert len(messages) == 3
    assert messages[0] == "1-day gap on 2026-07-05"
    assert messages[1] == "3-day gap from 2026-07-15 to 2026-07-17"
    assert messages[2] == "3-day gap from 2026-07-20 to 2026-07-22"

    # Format with context
    messages = format_multiple_gaps(gaps, "service-name data_type")
    assert all("service-name data_type:" in msg for msg in messages)
    assert len(messages) == 3

    print("  ✓ Multiple gaps formatting: PASSED")
    return True


def test_gap_summary_formatting():
    """Test gap summary message formatting."""
    print("Testing gap summary formatting...")

    # Empty gaps
    summary = format_gap_summary([], {})
    assert summary == "No gaps detected."

    # Single isolated gap
    gaps = [GapPeriod("2026-07-15", "2026-07-15", "2026-07-15", 1, False)]
    summary_data = {
        "total_gaps": 1,
        "isolated_gaps": 1,
        "consecutive_sequences": 0,
        "longest_gap_days": 1
    }
    summary = format_gap_summary(gaps, summary_data)
    assert "1 gap" in summary
    assert "1 isolated" in summary
    assert "longest: 1 days" in summary

    # Mixed gaps
    gaps = [
        GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False),
        GapPeriod("2026-07-15", "2026-07-15", "2026-07-17", 3, True),
        GapPeriod("2026-07-20", "2026-07-20", "2026-07-22", 3, True),
    ]
    summary_data = {
        "total_gaps": 3,
        "isolated_gaps": 1,
        "consecutive_sequences": 1,
        "longest_gap_days": 3
    }
    summary = format_gap_summary(gaps, summary_data)
    assert "3 gap" in summary
    assert "1 isolated" in summary
    assert "1 consecutive sequence" in summary
    assert "longest: 3 days" in summary

    print("  ✓ Gap summary formatting: PASSED")
    return True


def test_consecutive_sequence_formatting():
    """Test formatting of consecutive sequences as consolidated messages."""
    print("Testing consecutive sequence formatting...")

    gaps = [
        # Isolated gap
        GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False),
        # Consecutive sequence (should be consolidated to 1 message)
        GapPeriod("2026-07-15", "2026-07-15", "2026-07-17", 3, True),
        GapPeriod("2026-07-16", "2026-07-15", "2026-07-17", 3, True),
        GapPeriod("2026-07-17", "2026-07-15", "2026-07-17", 3, True),
        # Another isolated gap
        GapPeriod("2026-07-25", "2026-07-25", "2026-07-25", 1, False),
    ]

    messages = format_consecutive_sequence_gaps(gaps)

    # Should have 1 message for the consecutive sequence (3 days consolidated)
    assert len(messages) == 1
    assert messages[0] == "3-day gap from 2026-07-15 to 2026-07-17"

    print("  ✓ Consecutive sequence formatting: PASSED")
    return True


def test_message_format_edge_cases():
    """Test edge cases in message formatting."""
    print("Testing message format edge cases...")

    # Very long gap
    long_gap = GapPeriod(
        date="2026-08-15",
        start_day="2026-07-01",
        end_day="2026-08-15",
        size_days=46,
        is_consecutive=True
    )
    formatted = format_gap_period(long_gap)
    assert "46-day gap from 2026-07-01 to 2026-08-15" == formatted

    # Empty context should not add extra colons
    gap = GapPeriod("2026-07-15", "2026-07-15", "2026-07-15", 1, False)
    formatted = format_gap_error_message(gap, "")
    assert formatted == "1-day gap on 2026-07-15"

    # Special characters in context
    formatted = format_gap_error_message(gap, "test-service:workflow-data")
    assert "test-service:workflow-data: 1-day gap on 2026-07-15" == formatted

    print("  ✓ Message format edge cases: PASSED")
    return True


def test_group_gaps_by_period():
    """Test grouping gaps by period."""
    print("Testing grouping gaps by period...")

    gaps = [
        GapPeriod("2026-07-10", "2026-07-10", "2026-07-11", 2, True, 0),
        GapPeriod("2026-07-11", "2026-07-10", "2026-07-11", 2, True, 0),
        GapPeriod("2026-07-15", "2026-07-15", "2026-07-15", 1, False, None),
        GapPeriod("2026-07-20", "2026-07-20", "2026-07-22", 3, True, 1),
        GapPeriod("2026-07-21", "2026-07-20", "2026-07-22", 3, True, 1),
        GapPeriod("2026-07-22", "2026-07-20", "2026-07-22", 3, True, 1),
    ]

    grouped = group_gaps_by_period(gaps)

    assert len(grouped) == 3, f"Expected 3 groups, got {len(grouped)}"
    assert len(grouped["2026-07-10_to_2026-07-11"]) == 2
    assert len(grouped["2026-07-15_to_2026-07-15"]) == 1
    assert len(grouped["2026-07-20_to_2026-07-22"]) == 3

    print("  ✓ Grouping gaps by period: PASSED")
    return True


def test_coverage_calculation():
    """Test coverage calculation from gaps."""
    print("Testing coverage calculation...")

    # Normal case
    result = calculate_coverage_from_gaps(expected_days=30, gap_count=5)
    assert result["expected_days"] == 30
    assert result["days_with_data"] == 25
    assert result["days_with_gaps"] == 5
    assert result["coverage_percentage"] == 83.33
    assert result["gap_percentage"] == 16.67

    # Full coverage
    result = calculate_coverage_from_gaps(expected_days=30, gap_count=0)
    assert result["coverage_percentage"] == 100.0
    assert result["gap_percentage"] == 0.0

    # No coverage
    result = calculate_coverage_from_gaps(expected_days=30, gap_count=30)
    assert result["coverage_percentage"] == 0.0
    assert result["gap_percentage"] == 100.0

    # Edge case: zero days
    result = calculate_coverage_from_gaps(expected_days=0, gap_count=0)
    assert result["expected_days"] == 0
    assert result["coverage_percentage"] == 0.0

    print("  ✓ Coverage calculation: PASSED")
    return True


def test_anomaly_detection():
    """Test anomaly detection in gap patterns."""
    print("Testing anomaly detection...")

    # Normal gaps - no anomalies
    gaps = [
        GapPeriod("2026-07-05", "2026-07-05", "2026-07-05", 1, False),
        GapPeriod("2026-07-10", "2026-07-10", "2026-07-10", 1, False),
    ]
    summary = {
        "total_gaps": 2,
        "isolated_gaps": 2,
        "consecutive_sequences": 0,
        "longest_gap_days": 1,
        "gap_intensity": 0.06,
    }
    anomalies = detect_anomalies(gaps, summary)
    assert len(anomalies) == 0, "Normal gaps should not trigger anomalies"

    # Extended gap anomaly
    gaps = [
        GapPeriod("2026-07-01", "2026-07-01", "2026-07-20", 20, True, 0),
    ]
    summary = {
        "total_gaps": 20,
        "isolated_gaps": 0,
        "consecutive_sequences": 1,
        "longest_gap_days": 20,
        "gap_intensity": 0.65,
    }
    anomalies = detect_anomalies(gaps, summary)
    assert len(anomalies) >= 2, "Extended gap should trigger multiple anomalies"
    assert any("extended gap" in a for a in anomalies)
    assert any("High gap intensity" in a for a in anomalies)

    # Consecutive gap dominance
    gaps = [
        GapPeriod(f"2026-07-{i:02d}", "2026-07-01", "2026-07-10", 10, True, 0)
        for i in range(1, 11)
    ]
    summary = {
        "total_gaps": 10,
        "isolated_gaps": 0,
        "consecutive_sequences": 1,
        "longest_gap_days": 10,
        "gap_intensity": 0.33,
    }
    anomalies = detect_anomalies(gaps, summary)
    # Should have consecutive dominance warning
    assert len(anomalies) == 1
    assert "Consecutive gaps dominate" in anomalies[0]

    print("  ✓ Anomaly detection: PASSED")
    return True


def test_find_consecutive_sequences():
    """Test the internal consecutive sequence detection."""
    print("Testing consecutive sequence detection...")

    # All isolated
    gaps = create_test_gaps(["2026-07-05", "2026-07-10", "2026-07-15"])
    sequences = _find_consecutive_sequences(gaps)
    assert len(sequences) == 3
    assert all(len(seq) == 1 for seq in sequences)

    # All consecutive
    gaps = create_test_gaps(["2026-07-05", "2026-07-06", "2026-07-07"])
    sequences = _find_consecutive_sequences(gaps)
    assert len(sequences) == 1
    assert len(sequences[0]) == 3

    # Mixed
    gaps = create_test_gaps([
        "2026-07-05",  # Isolated
        "2026-07-10", "2026-07-11",  # Consecutive
        "2026-07-15",  # Isolated
    ])
    sequences = _find_consecutive_sequences(gaps)
    assert len(sequences) == 3
    assert len(sequences[0]) == 1  # Isolated
    assert len(sequences[1]) == 2  # Consecutive
    assert len(sequences[2]) == 1  # Isolated

    print("  ✓ Consecutive sequence detection: PASSED")
    return True


def test_gap_intensity_calculation():
    """Test gap intensity calculation in summary."""
    print("Testing gap intensity calculation...")

    gaps = create_test_gaps(["2026-07-01", "2026-07-05", "2026-07-10"])
    start_date = datetime.fromisoformat("2026-07-01")
    end_date = datetime.fromisoformat("2026-07-31")  # 31 days

    _, summary = calculate_gap_periods(gaps, start_date, end_date)

    # 3 gaps in 31 days = 0.0967 intensity
    expected_intensity = 3 / 31
    assert abs(summary["gap_intensity"] - expected_intensity) < 0.001
    assert summary["total_analysis_days"] == 31

    print("  ✓ Gap intensity calculation: PASSED")
    return True


def test_boundary_conditions():
    """Test boundary conditions and edge cases."""
    print("Testing boundary conditions...")

    # Gap at start boundary
    gaps = create_test_gaps(["2026-07-01"])
    start_date = datetime.fromisoformat("2026-07-01")
    end_date = datetime.fromisoformat("2026-07-31")

    gap_periods, _ = calculate_gap_periods(gaps, start_date, end_date)
    assert len(gap_periods) == 1
    assert gap_periods[0].date == "2026-07-01"

    # Gap at end boundary
    gaps = create_test_gaps(["2026-07-31"])
    gap_periods, _ = calculate_gap_periods(gaps, start_date, end_date)
    assert len(gap_periods) == 1
    assert gap_periods[0].date == "2026-07-31"

    # Gaps on consecutive days spanning month boundary
    gaps = create_test_gaps(["2026-07-31", "2026-08-01"])
    start_date = datetime.fromisoformat("2026-07-01")
    end_date = datetime.fromisoformat("2026-08-31")

    gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)
    assert len(gap_periods) == 2
    assert all(gp.is_consecutive for gp in gap_periods)
    assert all(gp.size_days == 2 for gp in gap_periods)

    print("  ✓ Boundary conditions: PASSED")
    return True


def run_all_tests():
    """Run all tests."""
    print("=" * 70)
    print("GAP CALCULATOR UNIT TESTS")
    print("=" * 70)
    print()

    tests = [
        test_single_isolated_gap,
        test_two_consecutive_gaps,
        test_mixed_consecutive_and_isolated,
        test_extended_consecutive_sequence,
        test_unordered_gaps,
        test_no_gaps,
        test_gap_classification,
        test_gap_formatting,
        test_gap_formatting_detailed,
        test_gap_error_message_formatting,
        test_multiple_gaps_formatting,
        test_gap_summary_formatting,
        test_consecutive_sequence_formatting,
        test_message_format_edge_cases,
        test_group_gaps_by_period,
        test_coverage_calculation,
        test_anomaly_detection,
        test_find_consecutive_sequences,
        test_gap_intensity_calculation,
        test_boundary_conditions,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except AssertionError as e:
            print(f"  ✗ {test.__name__}: FAILED - {e}")
            results.append((test.__name__, False))
        except Exception as e:
            print(f"  ✗ {test.__name__}: ERROR - {e}")
            results.append((test.__name__, False))
        print()

    # Summary
    print("=" * 70)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"Test Results: {passed}/{total} passed")

    if passed < total:
        print("\nFailed tests:")
        for name, result in results:
            if not result:
                print(f"  - {name}")

    print("=" * 70)

    return all(r for _, r in results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
