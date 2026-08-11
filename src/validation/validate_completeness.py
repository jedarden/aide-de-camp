#!/usr/bin/env python3
"""
Completeness validation for 30-day deployment data.

Validates:
- Exactly 30 deployment entries present
- Chronological sequence with no date gaps
- No duplicate dates
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from src.utilities.gap_calculator import (
    GapPeriod,
    format_gap_error_message,
    format_gap_period_detailed,
    format_gap_summary,
    format_consecutive_sequence_gaps,
    detect_anomalies,
    calculate_gap_periods
)


def validate_completeness(data: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Validate completeness of 30-day deployment data.

    Args:
        data: List of deployment records with timestamp fields

    Returns:
        Tuple of (is_valid: bool, error_message: str)
        Returns (True, "") if valid, (False, error_message) if invalid
    """
    if not isinstance(data, list):
        return False, "Data must be a list"

    # Check exactly 30 entries
    if len(data) != 30:
        return False, f"Expected 30 deployment entries, found {len(data)}"

    # Extract and parse timestamps
    timestamps = []
    seen_dates = set()

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            return False, f"Entry {i} is not a dictionary"

        # Get timestamp field (support both "timestamp" and "creationTimestamp")
        ts_field = None
        if "timestamp" in entry:
            ts_field = "timestamp"
        elif "creationTimestamp" in entry:
            ts_field = "creationTimestamp"
        else:
            return False, f"Entry {i} missing timestamp field"

        ts_value = entry[ts_field]
        if not ts_value:
            return False, f"Entry {i} has empty timestamp"

        try:
            # Parse timestamp
            if isinstance(ts_value, str):
                if ts_value.endswith('Z'):
                    ts_value = ts_value[:-1] + '+00:00'
                dt = datetime.fromisoformat(ts_value.replace('+00:00', ''))
            else:
                return False, f"Entry {i} timestamp must be a string"

            timestamps.append(dt)
            date_only = dt.date()

            # Check for duplicate dates
            if date_only in seen_dates:
                return False, f"Duplicate date found: {date_only}"
            seen_dates.add(date_only)

        except (ValueError, AttributeError) as e:
            return False, f"Entry {i} has invalid timestamp: {e}"

    # Sort timestamps chronologically
    timestamps.sort()

    # Check for gaps in the date sequence
    gaps = []
    for i in range(len(timestamps) - 1):
        current_date = timestamps[i].date()
        next_date = timestamps[i + 1].date()
        expected_next_date = current_date + timedelta(days=1)

        if next_date != expected_next_date:
            days_diff = (next_date - current_date).days
            # Add each missing date individually
            for day_offset in range(1, days_diff):
                missing_date = (current_date + timedelta(days=day_offset)).isoformat()
                gaps.append({"date": missing_date})

    if gaps:
        # Use gap calculator to generate detailed error messages for ALL gaps
        start_analysis = timestamps[0]
        end_analysis = timestamps[-1]
        gap_periods, summary = calculate_gap_periods(gaps, start_analysis, end_analysis)

        if gap_periods:
            # Build comprehensive error message with all gaps
            gap_messages = []

            # Add summary line
            gap_messages.append(format_gap_summary(gap_periods, summary))

            # Add individual gap details (consolidate consecutive sequences)
            consolidated_gaps = format_consecutive_sequence_gaps(gap_periods)
            for gap_msg in consolidated_gaps:
                gap_messages.append(f"  - {gap_msg}")

            # Add actionable guidance based on gap size
            gap_messages.append("\nACTION:")
            longest_gap = max(gap_periods, key=lambda gp: gp.size_days)
            if longest_gap.size_days == 1:
                gap_messages.append("  Verify deployment occurred on this date. Check pipeline logs or re-run deployment for this day.")
            elif longest_gap.size_days <= 3:
                gap_messages.append(f"  Review deployment pipeline for {longest_gap.size_days}-day period. Check for service downtime or data collection failures.")
            elif longest_gap.size_days <= 7:
                gap_messages.append(f"  Investigate {longest_gap.size_days}-day outage. Verify infrastructure availability and data retention policies.")
            else:
                gap_messages.append(f"  Critical {longest_gap.size_days}-day gap detected. Review data collection infrastructure and consider extending analysis period to exclude this gap.")

            # Add anomaly-specific guidance if applicable
            anomalies = detect_anomalies(gap_periods, summary)
            if anomalies:
                gap_messages.append("\nADDITIONAL ANOMALIES:")
                for anomaly in anomalies:
                    gap_messages.append(f"  {anomaly}")

            return False, "\n".join(gap_messages)

    return True, ""


def validate_completeness_with_details(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate completeness with detailed results.

    Args:
        data: List of deployment records with timestamp fields

    Returns:
        Dictionary with validation results:
        - is_valid: bool
        - error_message: str
        - entry_count: int
        - date_range: tuple of (earliest_date, latest_date)
        - coverage_days: int
    """
    result = {
        "is_valid": False,
        "error_message": "",
        "entry_count": len(data) if isinstance(data, list) else 0,
        "date_range": None,
        "coverage_days": 0
    }

    if not isinstance(data, list):
        result["error_message"] = "Data must be a list"
        return result

    if len(data) != 30:
        result["error_message"] = f"Expected 30 deployment entries, found {len(data)}"
        return result

    timestamps = []
    seen_dates = set()

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            result["error_message"] = f"Entry {i} is not a dictionary"
            return result

        ts_field = None
        if "timestamp" in entry:
            ts_field = "timestamp"
        elif "creationTimestamp" in entry:
            ts_field = "creationTimestamp"
        else:
            result["error_message"] = f"Entry {i} missing timestamp field"
            return result

        ts_value = entry[ts_field]
        if not ts_value:
            result["error_message"] = f"Entry {i} has empty timestamp"
            return result

        try:
            if isinstance(ts_value, str):
                if ts_value.endswith('Z'):
                    ts_value = ts_value[:-1] + '+00:00'
                dt = datetime.fromisoformat(ts_value.replace('+00:00', ''))
            else:
                result["error_message"] = f"Entry {i} timestamp must be a string"
                return result

            timestamps.append(dt)
            date_only = dt.date()

            if date_only in seen_dates:
                result["error_message"] = f"Duplicate date found: {date_only}"
                return result
            seen_dates.add(date_only)

        except (ValueError, AttributeError) as e:
            result["error_message"] = f"Entry {i} has invalid timestamp: {e}"
            return result

    timestamps.sort()
    earliest = timestamps[0].date()
    latest = timestamps[-1].date()
    result["date_range"] = (earliest.isoformat(), latest.isoformat())
    result["coverage_days"] = (latest - earliest).days + 1

    # Check for gaps and build gap list
    gaps = []
    for i in range(len(timestamps) - 1):
        current_date = timestamps[i].date()
        next_date = timestamps[i + 1].date()
        expected_next_date = current_date + timedelta(days=1)

        if next_date != expected_next_date:
            days_diff = (next_date - current_date).days
            # Add each missing date individually
            for day_offset in range(1, days_diff):
                missing_date = (current_date + timedelta(days=day_offset)).isoformat()
                gaps.append({"date": missing_date})

    if gaps:
        # Use gap calculator to generate detailed error messages for ALL gaps
        start_analysis = timestamps[0]
        end_analysis = timestamps[-1]
        gap_periods, summary = calculate_gap_periods(gaps, start_analysis, end_analysis)

        if gap_periods:
            # Build comprehensive error message with all gaps
            gap_messages = []

            # Add summary line
            gap_messages.append(format_gap_summary(gap_periods, summary))

            # Add individual gap details (consolidate consecutive sequences)
            consolidated_gaps = format_consecutive_sequence_gaps(gap_periods)
            for gap_msg in consolidated_gaps:
                gap_messages.append(f"  - {gap_msg}")

            # Add actionable guidance based on gap size
            gap_messages.append("\nACTION:")
            longest_gap = max(gap_periods, key=lambda gp: gp.size_days)
            if longest_gap.size_days == 1:
                gap_messages.append("  Verify deployment occurred on this date. Check pipeline logs or re-run deployment for this day.")
            elif longest_gap.size_days <= 3:
                gap_messages.append(f"  Review deployment pipeline for {longest_gap.size_days}-day period. Check for service downtime or data collection failures.")
            elif longest_gap.size_days <= 7:
                gap_messages.append(f"  Investigate {longest_gap.size_days}-day outage. Verify infrastructure availability and data retention policies.")
            else:
                gap_messages.append(f"  Critical {longest_gap.size_days}-day gap detected. Review data collection infrastructure and consider extending analysis period to exclude this gap.")

            # Add anomaly-specific guidance if applicable
            anomalies = detect_anomalies(gap_periods, summary)
            if anomalies:
                gap_messages.append("\nADDITIONAL ANOMALIES:")
                for anomaly in anomalies:
                    gap_messages.append(f"  {anomaly}")

            result["error_message"] = "\n".join(gap_messages)
            result["gaps_detected"] = len(gaps)
            result["gap_summary"] = summary
            return result

    result["is_valid"] = True
    return result