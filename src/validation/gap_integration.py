#!/usr/bin/env python3
"""
Integrated Gap Validation with Actionable Guidance

This module provides comprehensive gap validation that combines gap detection
from gap_calculator with detailed, actionable error messages. It integrates
with the schema validation pipeline to provide users with clear guidance on
how to fix coverage gaps.

Features:
- Gap detection using gap_calculator
- Actionable error messages with deployment interval references
- Coverage percentage calculations
- Integration with schema validation flow
- Detailed remediation steps

Usage:
    from src.validation.gap_integration import (
        validate_gaps_with_guidance,
        format_gap_validation_result,
        GapValidationResult
    )

    result = validate_gaps_with_guidance(
        deployment_data,
        start_date,
        end_date,
        service_name
    )

    if not result.is_valid:
        print(format_gap_validation_result(result))
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from src.utilities.gap_calculator import (
    calculate_gap_periods,
    GapPeriod,
    format_gap_period,
    format_gap_summary,
    detect_anomalies
)


class GapSeverity(Enum):
    """Severity levels for gap validation failures."""
    CRITICAL = "critical"  # > 14 days or coverage < 80%
    HIGH = "high"        # > 7 days or coverage < 90%
    MEDIUM = "medium"    # > 3 days or coverage < 95%
    LOW = "low"          # <= 3 days or coverage >= 95%
    NONE = "none"        # No gaps


@dataclass
class GapValidationResult:
    """Comprehensive result of gap validation with actionable guidance."""
    is_valid: bool
    service_name: str
    expected_days: int
    actual_days: int
    coverage_percentage: float
    gap_periods: List[GapPeriod] = field(default_factory=list)
    severity: GapSeverity = GapSeverity.NONE
    error_message: str = ""
    actionable_guidance: List[str] = field(default_factory=list)
    anomaly_messages: List[str] = field(default_factory=list)
    deployment_intervals: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "service_name": self.service_name,
            "expected_days": self.expected_days,
            "actual_days": self.actual_days,
            "coverage_percentage": self.coverage_percentage,
            "gap_count": len(self.gap_periods),
            "severity": self.severity.value,
            "error_message": self.error_message,
            "actionable_guidance": self.actionable_guidance,
            "anomaly_messages": self.anomaly_messages,
            "deployment_intervals": self.deployment_intervals
        }


def validate_gaps_with_guidance(
    deployment_data: Dict[str, Any],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    service_name: str = "unknown",
    expected_coverage_threshold: float = 95.0
) -> GapValidationResult:
    """
    Validate deployment data for gaps with actionable guidance.

    This function performs comprehensive gap validation:
    1. Extracts date range from metadata
    2. Detects gaps in coverage
    3. Calculates coverage statistics
    4. Generates actionable error messages
    5. Provides deployment interval context

    Args:
        deployment_data: Deployment data dictionary with metadata and events
        start_date: Expected start date (optional, inferred from data if not provided)
        end_date: Expected end date (optional, inferred from data if not provided)
        service_name: Name of the service for error messages
        expected_coverage_threshold: Minimum coverage percentage (default: 95.0)

    Returns:
        GapValidationResult with detailed validation information

    Examples:
        >>> data = {
        ...     "metadata": {
        ...         "time_period": {
        ...             "start": "2026-07-01T00:00:00Z",
        ...             "end": "2026-07-30T23:59:59Z"
        ...         }
        ...     },
        ...     "deployment_events_last_30_days": [...]
        ... }
        >>> result = validate_gaps_with_guidance(data, service_name="pbx-web")
        >>> if not result.is_valid:
        ...     print(format_gap_validation_result(result))
    """
    # Extract dates from metadata if not provided
    if start_date is None or end_date is None:
        start_date, end_date = _extract_date_range(deployment_data)

    if start_date is None or end_date is None:
        return GapValidationResult(
            is_valid=False,
            service_name=service_name,
            expected_days=0,
            actual_days=0,
            coverage_percentage=0.0,
            severity=GapSeverity.CRITICAL,
            error_message="Cannot determine date range from deployment data",
            actionable_guidance=[
                "Add metadata.time_period.start and metadata.time_period.end to deployment data",
                "Expected format: ISO 8601 timestamps (e.g., '2026-07-01T00:00:00Z')"
            ]
        )

    # Extract deployment dates from data
    deployment_dates = _extract_deployment_dates(deployment_data)

    # Calculate expected days
    expected_days = (end_date - start_date).days + 1
    actual_days = len(deployment_dates)

    # Calculate gaps
    gaps = _calculate_gaps_from_dates(deployment_dates, start_date, end_date)
    gap_periods, summary = calculate_gap_periods(gaps, start_date, end_date)

    # Calculate coverage percentage
    coverage_percentage = (actual_days / expected_days * 100) if expected_days > 0 else 0.0

    # Determine severity
    severity = _assess_gap_severity(gap_periods, coverage_percentage, expected_days)

    # Generate actionable guidance
    actionable_guidance = _generate_actionable_guidance(
        gap_periods,
        coverage_percentage,
        expected_coverage_threshold,
        expected_days,
        actual_days,
        service_name
    )

    # Detect anomalies
    anomaly_messages = detect_anomalies(gap_periods, summary)

    # Calculate deployment intervals for context
    deployment_intervals = _calculate_deployment_intervals(deployment_dates)

    # Generate error message
    error_message = _generate_error_message(
        gap_periods,
        coverage_percentage,
        expected_days,
        actual_days,
        service_name,
        deployment_intervals
    )

    # Determine if valid (meets threshold)
    is_valid = (
        len(gap_periods) == 0 and
        coverage_percentage >= expected_coverage_threshold
    )

    return GapValidationResult(
        is_valid=is_valid,
        service_name=service_name,
        expected_days=expected_days,
        actual_days=actual_days,
        coverage_percentage=round(coverage_percentage, 2),
        gap_periods=gap_periods,
        severity=severity,
        error_message=error_message,
        actionable_guidance=actionable_guidance,
        anomaly_messages=anomaly_messages,
        deployment_intervals=deployment_intervals
    )


def _is_valid_gap_object(gap: Any) -> bool:
    """
    Check if a gap object has the required attributes for formatting.

    Args:
        gap: Gap period object to validate

    Returns:
        True if gap has all required attributes, False otherwise
    """
    required_attrs = ['size_days', 'start_day', 'end_day', 'is_consecutive']
    return all(hasattr(gap, attr) for attr in required_attrs)


def format_gap_validation_result(result: GapValidationResult) -> str:
    """
    Format a gap validation result as a comprehensive, actionable error message.

    Args:
        result: GapValidationResult from validate_gaps_with_guidance

    Returns:
        Formatted error message with details and guidance
    """
    lines = []

    # Header
    lines.append(f"{'='*70}")
    lines.append(f"❌ Gap Validation Failed for {result.service_name}")
    lines.append(f"{'='*70}")

    # Summary
    lines.append(f"\n📊 Coverage Summary:")
    lines.append(f"   Expected days:        {result.expected_days} (deployment interval)")
    lines.append(f"   Actual days:          {result.actual_days}")
    lines.append(f"   Coverage:             {result.coverage_percentage}%")
    # Handle both enum and string severity
    severity_value = result.severity.value if hasattr(result.severity, 'value') else str(result.severity)
    lines.append(f"   Severity:             {severity_value.upper()}")

    # Deployment intervals context
    if result.deployment_intervals:
        lines.append(f"\n📅 Deployment Intervals:")
        di = result.deployment_intervals
        lines.append(f"   First deployment:    {di.get('first_deployment', 'N/A')}")
        lines.append(f"   Last deployment:     {di.get('last_deployment', 'N/A')}")
        lines.append(f"   Average interval:    {di.get('average_interval_days', 'N/A')} days")
        lines.append(f"   Longest interval:    {di.get('longest_interval_days', 'N/A')} days")

    # Gap details - only process valid gap objects
    if result.gap_periods:
        # Filter out malformed gap objects
        valid_gaps = [g for g in result.gap_periods if _is_valid_gap_object(g)]
        malformed_count = len(result.gap_periods) - len(valid_gaps)

        if valid_gaps:
            lines.append(f"\n🚫 Detected Gaps ({len(valid_gaps)}):")

            # Show unique consecutive sequences
            consecutive_gaps = [g for g in valid_gaps if g.is_consecutive]
            isolated_gaps = [g for g in valid_gaps if not g.is_consecutive]

            if consecutive_gaps:
                # Group by sequence
                sequences = {}
                for gap in consecutive_gaps:
                    key = (gap.start_day, gap.end_day)
                    if key not in sequences:
                        sequences[key] = gap

                lines.append(f"   Consecutive gap sequences:")
                for gap in sequences.values():
                    lines.append(f"     • {format_gap_period(gap)}")

            if isolated_gaps:
                lines.append(f"   Isolated gaps:")
                for gap in isolated_gaps[:5]:  # Show first 5
                    lines.append(f"     • {format_gap_period(gap)}")
                if len(isolated_gaps) > 5:
                    lines.append(f"     ... and {len(isolated_gaps) - 5} more")

        # Note about malformed gaps
        if malformed_count > 0:
            lines.append(f"\n⚠️  Warning: {malformed_count} gap(s) had missing attributes and were omitted from display")

    # Anomaly messages
    if result.anomaly_messages:
        lines.append(f"\n⚠️  Anomalies Detected:")
        for i, anomaly in enumerate(result.anomaly_messages, 1):
            lines.append(f"   {i}. {anomaly}")

    # Actionable guidance
    if result.actionable_guidance:
        lines.append(f"\n💡 Actionable Guidance:")
        for i, guidance in enumerate(result.actionable_guidance, 1):
            lines.append(f"   {i}. {guidance}")

    # Expected coverage reference
    lines.append(f"\n📐 Expected Coverage Requirements:")
    lines.append(f"   Deployment interval: Days 1-{result.expected_days} of analysis period")
    lines.append(f"   Minimum threshold: 95% coverage for reliable analysis")
    lines.append(f"   Acceptable gaps: Isolated gaps ≤3 days are generally acceptable")
    lines.append(f"   Critical gaps: Consecutive gaps >7 days require investigation")

    # Footer
    lines.append(f"\n{'='*70}")

    return "\n".join(lines)


def _extract_date_range(data: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Extract start and end dates from deployment data metadata."""
    start_date = None
    end_date = None

    # Try metadata.time_period
    if "metadata" in data and "time_period" in data["metadata"]:
        tp = data["metadata"]["time_period"]
        try:
            if "start" in tp:
                start_date = datetime.fromisoformat(tp["start"].replace('Z', '+00:00'))
            if "end" in tp:
                end_date = datetime.fromisoformat(tp["end"].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

    # Try report_metadata
    if start_date is None or end_date is None:
        if "report_metadata" in data:
            metadata = data["report_metadata"]
            try:
                if start_date is None and "time_range_start" in metadata:
                    start_date = datetime.fromisoformat(metadata["time_range_start"].replace('Z', '+00:00'))
                if end_date is None and "time_range_end" in metadata:
                    end_date = datetime.fromisoformat(metadata["time_range_end"].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

    # Try completeness section
    if start_date is None or end_date is None:
        if "completeness" in data:
            completeness = data["completeness"]
            if "data_period_start" in completeness and "data_period_end" in completeness:
                try:
                    start_date = datetime.fromisoformat(completeness["data_period_start"].replace('Z', '+00:00'))
                    end_date = datetime.fromisoformat(completeness["data_period_end"].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass

    return start_date, end_date


def _extract_deployment_dates(data: Dict[str, Any]) -> List[datetime]:
    """Extract unique deployment dates from deployment data."""
    dates = set()

    # Check deployment_events_last_30_days
    if "deployment_events_last_30_days" in data:
        events = data["deployment_events_last_30_days"]
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict) and "date" in event:
                    try:
                        date_str = event["date"]
                        if 'T' in date_str:
                            date_str = date_str.split('T')[0]
                        dates.add(datetime.fromisoformat(date_str))
                    except (ValueError, AttributeError):
                        continue

    # Check replica_history
    if "replica_history" in data:
        history = data["replica_history"]
        if isinstance(history, list):
            for rs in history:
                if isinstance(rs, dict) and "created_at" in rs:
                    try:
                        date_str = rs["created_at"]
                        if 'T' in date_str:
                            date_str = date_str.split('T')[0]
                        dates.add(datetime.fromisoformat(date_str))
                    except (ValueError, AttributeError):
                        continue

    return sorted(list(dates))


def _calculate_gaps_from_dates(
    deployment_dates: List[datetime],
    start_date: datetime,
    end_date: datetime
) -> List[Dict[str, Any]]:
    """Calculate gaps between deployment dates."""
    if not deployment_dates:
        # No deployments means entire range is a gap
        return [{"date": start_date.date().isoformat()}]

    gaps = []
    expected_dates = set()
    current = start_date
    while current <= end_date:
        expected_dates.add(current.date())
        current += timedelta(days=1)

    deployment_dates_set = {d.date() for d in deployment_dates}
    missing_dates = expected_dates - deployment_dates_set

    for missing_date in sorted(missing_dates):
        gaps.append({"date": missing_date.isoformat()})

    return gaps


def _assess_gap_severity(
    gap_periods: List[GapPeriod],
    coverage_percentage: float,
    expected_days: int
) -> GapSeverity:
    """Assess the severity of gap validation failures."""
    if not gap_periods and coverage_percentage >= 95.0:
        return GapSeverity.NONE

    # Check for critical conditions (coverage < 80% OR gaps > 14 days)
    max_gap_size = max([g.size_days for g in gap_periods]) if gap_periods else 0
    if coverage_percentage < 80.0 or max_gap_size > 14:
        return GapSeverity.CRITICAL

    # Check for high severity conditions (coverage < 90% OR gaps > 7 days)
    if coverage_percentage < 90.0 or max_gap_size > 7:
        return GapSeverity.HIGH

    # Check for medium severity conditions (coverage < 95% OR gaps > 3 days)
    if coverage_percentage < 95.0 or max_gap_size > 3:
        return GapSeverity.MEDIUM

    # Small gaps with good coverage
    return GapSeverity.LOW


def _generate_actionable_guidance(
    gap_periods: List[GapPeriod],
    coverage_percentage: float,
    expected_threshold: float,
    expected_days: int,
    actual_days: int,
    service_name: str
) -> List[str]:
    """Generate actionable guidance for fixing coverage gaps."""
    guidance = []

    # Coverage-based guidance
    if coverage_percentage < expected_threshold:
        shortfall = expected_threshold - coverage_percentage
        guidance.append(
            f"Increase coverage from {coverage_percentage:.1f}% to {expected_threshold:.1f}% "
            f"(shortfall: {shortfall:.1f}%). Add deployment data for {expected_days - actual_days} missing day(s)."
        )

    # Gap-specific guidance
    if gap_periods:
        # Group consecutive vs isolated
        consecutive_gaps = [g for g in gap_periods if g.is_consecutive]
        isolated_gaps = [g for g in gap_periods if not g.is_consecutive]

        if consecutive_gaps:
            max_consecutive = max([g.size_days for g in consecutive_gaps])
            guidance.append(
                f"Address {len(consecutive_gaps)} consecutive gap sequence(s). "
                f"Longest sequence: {max_consecutive} days. "
                f"Check for extended data collection failures or service downtime."
            )

        if isolated_gaps:
            guidance.append(
                f"Fill {len(isolated_gaps)} isolated gap day(s). "
                f"May indicate intermittent data collection issues or skipped deployments."
            )

    # Deployment interval guidance
    if actual_days < expected_days:
        missing_count = expected_days - actual_days
        guidance.append(
            f"Expected deployment interval: Days 1-{expected_days} of analysis period. "
            f"Current: {actual_days} day(s) with deployment data. "
            f"Add deployment data for {missing_count} missing day(s) in the 1-{expected_days} range."
        )

    # Data source guidance
    if coverage_percentage < 90.0:
        guidance.append(
            f"Verify data collection pipeline is operational. "
            f"Check: (1) Kubernetes ReplicaSet API is accessible, "
            f"(2) ArgoCD sync history is being captured, "
            f"(3) No retention policies are deleting deployment records."
        )

    # Service-specific guidance
    if service_name != "unknown":
        guidance.append(
            f"For service '{service_name}': Check deployment logs and ArgoCD history "
            f"for missing deployment events in the identified gap periods."
        )

    return guidance


def _calculate_deployment_intervals(deployment_dates: List[datetime]) -> Dict[str, Any]:
    """Calculate deployment interval statistics for context."""
    if not deployment_dates or len(deployment_dates) < 2:
        return {}

    intervals = []
    for i in range(1, len(deployment_dates)):
        interval_days = (deployment_dates[i] - deployment_dates[i - 1]).days
        intervals.append(interval_days)

    return {
        "first_deployment": deployment_dates[0].date().isoformat(),
        "last_deployment": deployment_dates[-1].date().isoformat(),
        "total_deployments": len(deployment_dates),
        "average_interval_days": round(sum(intervals) / len(intervals), 1) if intervals else 0,
        "longest_interval_days": max(intervals) if intervals else 0,
        "shortest_interval_days": min(intervals) if intervals else 0
    }


def _generate_error_message(
    gap_periods: List[GapPeriod],
    coverage_percentage: float,
    expected_days: int,
    actual_days: int,
    service_name: str,
    deployment_intervals: Dict[str, Any]
) -> str:
    """Generate a concise error message for the validation result."""
    if not gap_periods and coverage_percentage >= 95.0:
        return ""

    parts = []
    parts.append(f"{service_name}: {coverage_percentage:.1f}% coverage ({actual_days}/{expected_days} days)")

    if gap_periods:
        parts.append(f"{len(gap_periods)} gap(s) detected")

    return ". ".join(parts) + "."


__all__ = [
    "validate_gaps_with_guidance",
    "format_gap_validation_result",
    "GapValidationResult",
    "GapSeverity"
]
