#!/usr/bin/env python3
"""
Gap period calculation utilities for coverage analysis.

This module provides functions to calculate gap periods, including:
- Start and end days of each gap
- Gap size (number of days)
- Consecutive vs. non-consecutive gap classification
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass


@dataclass
class GapPeriod:
    """Represents a single gap period with calculated metadata."""
    date: str  # ISO format date string (YYYY-MM-DD)
    start_day: str  # Start date of this gap period
    end_day: str  # End date of this gap period
    size_days: int  # Size of the gap in days
    is_consecutive: bool  # Whether this gap is part of a consecutive sequence
    sequence_id: int = None  # ID of the consecutive sequence (None if isolated)


def calculate_gap_periods(
    gaps: List[Dict[str, Any]],
    start_date: datetime,
    end_date: datetime
) -> Tuple[List[GapPeriod], Dict[str, Any]]:
    """
    Calculate detailed gap periods including start, end, and size.

    Args:
        gaps: List of gap dictionaries with 'date' key (YYYY-MM-DD format)
        start_date: Analysis start date
        end_date: Analysis end date

    Returns:
        Tuple of (list of GapPeriod objects, summary statistics)
    """
    if not gaps:
        return [], _empty_summary()

    # Sort gaps by date
    sorted_gaps = sorted(gaps, key=lambda x: x["date"])

    # Find consecutive sequences
    sequences = _find_consecutive_sequences(sorted_gaps)

    # Create GapPeriod objects for each gap
    gap_periods = []
    for seq_id, sequence in enumerate(sequences):
        is_consecutive = len(sequence) > 1

        # Calculate sequence bounds
        seq_start_date = datetime.fromisoformat(sequence[0]["date"]).date()
        seq_end_date = datetime.fromisoformat(sequence[-1]["date"]).date()

        for gap in sequence:
            gap_date = datetime.fromisoformat(gap["date"]).date()

            # For isolated gaps, start = end = gap date
            # For consecutive gaps, use sequence bounds
            if is_consecutive:
                start_day = seq_start_date.isoformat()
                end_day = seq_end_date.isoformat()
                size_days = (seq_end_date - seq_start_date).days + 1
            else:
                start_day = gap_date.isoformat()
                end_day = gap_date.isoformat()
                size_days = 1

            gap_periods.append(GapPeriod(
                date=gap["date"],
                start_day=start_day,
                end_day=end_day,
                size_days=size_days,
                is_consecutive=is_consecutive,
                sequence_id=seq_id if is_consecutive else None
            ))

    # Calculate summary statistics
    summary = _calculate_summary(gap_periods, sequences, start_date, end_date)

    return gap_periods, summary


def _find_consecutive_sequences(sorted_gaps: List[Dict]) -> List[List[Dict]]:
    """
    Group gaps into consecutive sequences.

    A sequence is consecutive if each gap is exactly 1 day after the previous.
    Returns a list of sequences, where each sequence is a list of gap dicts.
    """
    if not sorted_gaps:
        return []

    sequences = []
    current_sequence = [sorted_gaps[0]]

    for i in range(1, len(sorted_gaps)):
        prev_date = datetime.fromisoformat(current_sequence[-1]["date"]).date()
        curr_date = datetime.fromisoformat(sorted_gaps[i]["date"]).date()

        # Check if consecutive (exactly 1 day apart)
        if (curr_date - prev_date).days == 1:
            current_sequence.append(sorted_gaps[i])
        else:
            # Start new sequence
            sequences.append(current_sequence)
            current_sequence = [sorted_gaps[i]]

    # Don't forget the last sequence
    sequences.append(current_sequence)

    return sequences


def _calculate_summary(
    gap_periods: List[GapPeriod],
    sequences: List[List[Dict]],
    start_date: datetime,
    end_date: datetime
) -> Dict[str, Any]:
    """Calculate summary statistics from gap periods."""
    total_gaps = len(gap_periods)
    isolated_gaps = [gp for gp in gap_periods if not gp.is_consecutive]
    consecutive_sequences = [seq for seq in sequences if len(seq) > 1]

    # Find longest gap period
    longest_gap = max(gap_periods, key=lambda gp: gp.size_days) if gap_periods else None

    # Calculate gap intensity (gaps per day)
    total_days = (end_date - start_date).days + 1
    gap_intensity = total_gaps / total_days if total_days > 0 else 0

    return {
        "total_gaps": total_gaps,
        "isolated_gaps": len(isolated_gaps),
        "consecutive_sequences": len(consecutive_sequences),
        "longest_gap_days": longest_gap.size_days if longest_gap else 0,
        "longest_gap_start": longest_gap.start_day if longest_gap else None,
        "longest_gap_end": longest_gap.end_day if longest_gap else None,
        "gap_intensity": round(gap_intensity, 4),
        "total_analysis_days": total_days
    }


def _empty_summary() -> Dict[str, Any]:
    """Return empty summary when no gaps exist."""
    return {
        "total_gaps": 0,
        "isolated_gaps": 0,
        "consecutive_sequences": 0,
        "longest_gap_days": 0,
        "longest_gap_start": None,
        "longest_gap_end": None,
        "gap_intensity": 0.0,
        "total_analysis_days": 0
    }


def classify_gap_by_size(gap: GapPeriod) -> str:
    """
    Classify a gap by its size.

    Returns:
        Classification: 'tiny', 'small', 'medium', 'large', 'extended'
    """
    if gap.size_days == 1:
        return "tiny"
    elif gap.size_days <= 3:
        return "small"
    elif gap.size_days <= 7:
        return "medium"
    elif gap.size_days <= 14:
        return "large"
    else:
        return "extended"


def format_gap_period(gap: GapPeriod) -> str:
    """
    Format a gap period for human-readable display.

    Returns:
        Formatted string showing gap size and date range:
        - Single day: "1-day gap on 2026-07-15"
        - Multi-day: "3-day gap from 2026-07-15 to 2026-07-17"
    """
    # Handle single-day gaps
    if gap.size_days == 1:
        return f"1-day gap on {gap.start_day}"
    # Handle multi-day gaps
    else:
        return f"{gap.size_days}-day gap from {gap.start_day} to {gap.end_day}"


def format_gap_period_detailed(gap: GapPeriod) -> str:
    """
    Format a gap period with detailed classification information.

    Returns:
        Formatted string with classification and severity:
        - "1-day gap on 2026-07-15 (isolated, tiny)"
        - "3-day gap from 2026-07-15 to 2026-07-17 (consecutive sequence, small)"
    """
    size_class = classify_gap_by_size(gap)
    type_label = "consecutive sequence" if gap.is_consecutive else "isolated"

    if gap.size_days == 1:
        return f"1-day gap on {gap.start_day} ({type_label}, {size_class})"
    else:
        return f"{gap.size_days}-day gap from {gap.start_day} to {gap.end_day} ({type_label}, {size_class})"


def format_gap_error_message(gap: GapPeriod, context: str = "") -> str:
    """
    Format a gap as an error message with optional context.

    Args:
        gap: The gap period to format
        context: Optional context string (e.g., service name, data type)

    Returns:
        Formatted error message ready for display
    """
    base_message = format_gap_period(gap)

    if context:
        return f"{context}: {base_message}"
    else:
        return base_message


def format_multiple_gaps(gap_periods: List[GapPeriod], context: str = "") -> List[str]:
    """
    Format multiple gap periods into individual error messages.

    Args:
        gap_periods: List of gap periods to format
        context: Optional context string to prefix each message

    Returns:
        List of formatted error messages
    """
    messages = []
    for gap in gap_periods:
        messages.append(format_gap_error_message(gap, context))
    return messages


def format_gap_summary(gap_periods: List[GapPeriod], summary: Dict[str, Any]) -> str:
    """
    Format a summary message for multiple gaps.

    Args:
        gap_periods: List of gap periods
        summary: Summary statistics from calculate_gap_periods

    Returns:
        Human-readable summary message
    """
    if not gap_periods:
        return "No gaps detected."

    total_gaps = summary.get("total_gaps", len(gap_periods))
    isolated = summary.get("isolated_gaps", 0)
    consecutive = summary.get("consecutive_sequences", 0)
    longest = summary.get("longest_gap_days", 0)

    parts = []
    parts.append(f"Found {total_gaps} gap(s)")

    if isolated > 0:
        parts.append(f"{isolated} isolated")

    if consecutive > 0:
        parts.append(f"{consecutive} consecutive sequence(s)")

    if longest > 0:
        parts.append(f"longest: {longest} days")

    return ". ".join(parts) + "."


def format_consecutive_sequence_gaps(gap_periods: List[GapPeriod]) -> List[str]:
    """
    Format consecutive gap sequences as consolidated messages.

    Instead of showing each day in a consecutive sequence separately,
    this function consolidates them into single messages.

    Args:
        gap_periods: List of gap periods

    Returns:
        List of formatted messages, one per unique consecutive sequence
    """
    # Group by unique consecutive sequences
    sequences = {}
    for gap in gap_periods:
        if gap.is_consecutive:
            # Use start_day as the key to identify unique sequences
            key = (gap.start_day, gap.end_day)
            if key not in sequences:
                sequences[key] = gap

    # Format each unique sequence
    messages = []
    for gap in sequences.values():
        messages.append(format_gap_period(gap))

    return messages


def group_gaps_by_period(gap_periods: List[GapPeriod]) -> Dict[str, List[GapPeriod]]:
    """
    Group gaps by their period (start_day).

    Gaps in the same consecutive sequence will have the same start_day and end_day,
    so this effectively groups consecutive gaps together.
    """
    groups = {}
    for gap in gap_periods:
        period_key = f"{gap.start_day}_to_{gap.end_day}"
        if period_key not in groups:
            groups[period_key] = []
        groups[period_key].append(gap)
    return groups


def calculate_coverage_from_gaps(
    expected_days: int,
    gap_count: int
) -> Dict[str, Any]:
    """
    Calculate coverage statistics from gap information.

    Args:
        expected_days: Total expected days in the analysis period
        gap_count: Number of days with gaps (missing data)

    Returns:
        Dictionary with coverage statistics
    """
    if expected_days == 0:
        return {
            "expected_days": 0,
            "days_with_data": 0,
            "days_with_gaps": 0,
            "coverage_percentage": 0.0,
            "gap_percentage": 0.0
        }

    days_with_data = expected_days - gap_count
    coverage_pct = (days_with_data / expected_days) * 100
    gap_pct = (gap_count / expected_days) * 100

    return {
        "expected_days": expected_days,
        "days_with_data": days_with_data,
        "days_with_gaps": gap_count,
        "coverage_percentage": round(coverage_pct, 2),
        "gap_percentage": round(gap_pct, 2)
    }


def detect_anomalies(
    gap_periods: List[GapPeriod],
    summary: Dict[str, Any]
) -> List[str]:
    """
    Detect anomalies in gap patterns with actionable guidance.

    Returns:
        List of anomaly descriptions with remediation steps
    """
    anomalies = []

    if not gap_periods:
        return anomalies

    # Check for extended gaps (> 14 days)
    extended_gaps = [gp for gp in gap_periods if gp.size_days > 14]
    if extended_gaps:
        impact_pct = round((summary['longest_gap_days'] / summary.get('total_analysis_days', 30)) * 100)
        anomalies.append(
            f"CRITICAL: Found {len(extended_gaps)} extended gap(s) (>14 days): "
            f"longest is {summary['longest_gap_days']} days ({impact_pct}% of analysis period). "
            f"ACTION: Review data collection infrastructure for failures. "
            f"Expected: continuous coverage across days 1-30. "
            f"Fill missing deployment data from backup sources or extend analysis period to exclude gap."
        )

    # Check for high gap intensity (> 0.5 = gap every other day)
    if summary['gap_intensity'] > 0.5:
        intensity_pct = summary['gap_intensity'] * 100
        anomalies.append(
            f"HIGH GAP INTENSITY: {summary['gap_intensity']:.2%} ({intensity_pct:.0f}%) of days have gaps. "
            f"Expected: <50% gap intensity for reliable analysis. "
            f"ACTION: Investigate systematic data collection issues. "
            f"Verify deployment pipeline is operational and logs are being captured consistently."
        )

    # Check if consecutive gaps dominate (> 70% of gaps are in consecutive sequences)
    if summary['total_gaps'] > 0:
        consecutive_gap_count = len([gp for gp in gap_periods if gp.is_consecutive])
        consecutive_ratio = consecutive_gap_count / summary['total_gaps']
        if consecutive_ratio > 0.7 and summary['total_gaps'] > 5:
            anomalies.append(
                f"CONSECUTIVE GAP DOMINANCE: {consecutive_gap_count}/{summary['total_gaps']} "
                f"gaps ({consecutive_ratio:.1%}) are in consecutive sequences. "
                f"Expected: isolated gaps rather than consecutive outages. "
                f"ACTION: Check for extended data collection failures or service downtime periods. "
                f"Review infrastructure logs during: {summary.get('longest_gap_start', 'unknown')} to {summary.get('longest_gap_end', 'unknown')}."
            )

    return anomalies
