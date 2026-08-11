#!/usr/bin/env python3
"""
Coverage gap validation with comprehensive error messages.

This module provides detailed validation for deployment data coverage gaps,
including gap detection, severity classification, and actionable error messages
that guide users in resolving coverage issues.

Usage:
    from src.validation.coverage_gap import CoverageGapValidator, GapDetail

    validator = CoverageGapValidator(
        period_start=datetime(2026, 7, 7),
        period_end=datetime(2026, 8, 6)
    )

    result = validator.validate_coverage(deployment_data)
    if result.has_gaps:
        for error in result.error_messages:
            print(error)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class GapSeverity(Enum):
    """Severity levels for coverage gaps."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class GapDetail:
    """
    Detailed information about a coverage gap.

    Attributes:
        gap_start_days_ago: Days ago when the gap started (relative to period end)
        gap_end_days_ago: Days ago when the gap ended (relative to period end)
        gap_duration_days: Duration of the gap in days
        severity: Severity level based on gap duration
        gap_start_date: Actual start date of the gap
        gap_end_date: Actual end date of the gap
        missing_data_types: Types of data missing during this gap
        actionable_message: Human-readable message explaining the gap and how to fix it
        is_consecutive: Whether this gap is part of a consecutive sequence
        consecutive_sequence_id: Identifier for the consecutive sequence (None if not consecutive)
        position_in_sequence: Position in consecutive sequence (0-indexed, None if not consecutive)
    """
    gap_start_days_ago: int
    gap_end_days_ago: int
    gap_duration_days: int
    severity: GapSeverity
    gap_start_date: Optional[datetime] = None
    gap_end_date: Optional[datetime] = None
    missing_data_types: List[str] = field(default_factory=list)
    actionable_message: str = ""
    is_consecutive: bool = False
    consecutive_sequence_id: Optional[int] = None
    position_in_sequence: Optional[int] = None

    def __post_init__(self):
        """Generate actionable message based on gap details."""
        if not self.actionable_message:
            self.actionable_message = self._generate_actionable_message()

    def _generate_actionable_message(self) -> str:
        """Generate a human-readable, actionable error message."""
        severity_prefix = {
            GapSeverity.CRITICAL: "CRITICAL GAP",
            GapSeverity.WARNING: "WARNING: Gap detected",
            GapSeverity.INFO: "INFO: Minor gap"
        }[self.severity]

        # Build gap description with proper date formatting
        gap_desc = self._format_gap_description()

        # Build severity-specific guidance
        guidance = self._get_severity_guidance()

        return f"{severity_prefix}: {gap_desc}. {guidance}"

    def _format_gap_description(self) -> str:
        """Format gap description, handling single-day vs multi-day gaps."""
        if self.gap_duration_days == 1:
            # Single-day gap format
            if self.gap_start_date:
                gap_desc = f"1-day gap on {self.gap_start_date.date()}"
            elif self.gap_start_days_ago:
                gap_desc = f"1-day gap on day {self.gap_start_days_ago} ago"
            else:
                gap_desc = "1-day gap"
        else:
            # Multi-day gap format
            gap_desc = f"{self.gap_duration_days}-day gap"
            if self.gap_start_date and self.gap_end_date:
                gap_desc += f" from {self.gap_start_date.date()} to {self.gap_end_date.date()}"
            elif self.gap_start_days_ago and self.gap_end_days_ago:
                gap_desc += f" from day {self.gap_start_days_ago} ago to day {self.gap_end_days_ago} ago"

        return gap_desc

    def _get_severity_guidance(self) -> str:
        """Get actionable guidance based on gap severity."""
        if self.severity == GapSeverity.CRITICAL:
            return (f"Gap of {self.gap_duration_days} days exceeds 7-day threshold and prevents "
                   "completeness validation. ACTION: Review data collection pipeline for failures "
                   "or service downtime during this period. Add missing deployment data from archives "
                   "or extend the analysis period to exclude this gap.")
        elif self.severity == GapSeverity.WARNING:
            return (f"Gap of {self.gap_duration_days} days indicates partial coverage. "
                   "ACTION: Investigate whether deployments occurred during this period. "
                   "If data exists, add it to the deployment history. If not, this may be expected "
                   "for low-frequency deployment services.")
        else:  # INFO
            return (f"Minor gap of {self.gap_duration_days} day(s) is acceptable for most use cases. "
                   "ACTION: Consider whether this gap affects analysis quality. For strict validation, "
                   "fill the missing data or adjust the completeness threshold.")

    def to_dict(self) -> Dict[str, Any]:
        """Convert gap detail to dictionary for JSON serialization."""
        return {
            "gap_start_days_ago": self.gap_start_days_ago,
            "gap_end_days_ago": self.gap_end_days_ago,
            "gap_duration_days": self.gap_duration_days,
            "severity": self.severity.value,
            "gap_start_date": self.gap_start_date.isoformat() if self.gap_start_date else None,
            "gap_end_date": self.gap_end_date.isoformat() if self.gap_end_date else None,
            "missing_data_types": self.missing_data_types,
            "actionable_message": self.actionable_message
        }


@dataclass
class CoverageGapResult:
    """
    Result of coverage gap validation.

    Attributes:
        has_gaps: Whether any gaps were detected
        total_gaps: Total number of gaps detected
        critical_gaps: Number of critical gaps (>7 days)
        warning_gaps: Number of warning gaps (3-7 days)
        info_gaps: Number of info gaps (<3 days)
        gap_details: List of detailed gap information
        error_messages: List of human-readable error messages
        coverage_percentage: Overall coverage percentage
        meets_threshold: Whether coverage meets the minimum threshold
        actionable_summary: High-level summary with remediation steps
    """
    has_gaps: bool
    total_gaps: int
    critical_gaps: int
    warning_gaps: int
    info_gaps: int
    gap_details: List[GapDetail] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)
    coverage_percentage: float = 0.0
    meets_threshold: bool = False
    actionable_summary: str = ""

    def __post_init__(self):
        """Generate actionable summary if not provided."""
        if not self.actionable_summary:
            self.actionable_summary = self._generate_summary()

    def _generate_summary(self) -> str:
        """Generate a high-level summary with remediation guidance."""
        if not self.has_gaps:
            return "✅ No coverage gaps detected. Deployment data has complete temporal coverage."

        lines = [
            f"⚠️ COVERAGE GAPS DETECTED: {self.total_gaps} gap(s) found in deployment data.",
            f"Severity breakdown: {self.critical_gaps} critical, {self.warning_gaps} warning, {self.info_gaps} info.",
            f"Overall coverage: {self.coverage_percentage:.1f}% of expected period."
        ]

        if self.critical_gaps > 0:
            lines.append(
                f"🚨 CRITICAL: {self.critical_gaps} gap(s) exceed 7-day threshold. "
                "These prevent completeness validation and indicate significant data loss."
            )

        if self.warning_gaps > 0:
            lines.append(
                f"⚠️ WARNING: {self.warning_gaps} gap(s) between 3-7 days. "
                "Review these periods for partial coverage issues."
            )

        # Add remediation guidance
        lines.extend([
            "",
            "RECOMMENDED ACTIONS:",
            "1. Review gap_details below for specific missing periods",
            "2. Check data collection logs for failures during gap periods",
            "3. Add missing deployment data from backup sources if available",
            "4. For critical gaps, consider extending the analysis period to exclude affected days"
        ])

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            "has_gaps": self.has_gaps,
            "total_gaps": self.total_gaps,
            "critical_gaps": self.critical_gaps,
            "warning_gaps": self.warning_gaps,
            "info_gaps": self.info_gaps,
            "gap_details": [gap.to_dict() for gap in self.gap_details],
            "error_messages": self.error_messages,
            "coverage_percentage": self.coverage_percentage,
            "meets_threshold": self.meets_threshold,
            "actionable_summary": self.actionable_summary
        }


class CoverageGapValidator:
    """
    Validator for deployment data coverage gaps.

    Detects gaps in deployment data, classifies them by severity, and generates
    comprehensive error messages with actionable guidance for remediation.
    """

    # Thresholds for gap severity classification
    CRITICAL_GAP_DAYS = 7
    WARNING_GAP_DAYS = 3

    def __init__(self, period_start: datetime, period_end: datetime,
                 completeness_threshold: float = 95.0):
        """
        Initialize the validator.

        Args:
            period_start: Start of the analysis period
            period_end: End of the analysis period
            completeness_threshold: Minimum coverage percentage threshold (default 95%)
        """
        self.period_start = period_start
        self.period_end = period_end
        self.completeness_threshold = completeness_threshold
        self.expected_days = (period_end - period_start).days + 1

    def validate_coverage(self, deployment_data: List[Dict[str, Any]],
                         timestamp_field: str = "timestamp") -> CoverageGapResult:
        """
        Validate deployment data for coverage gaps.

        Args:
            deployment_data: List of deployment records
            timestamp_field: Field name containing timestamp (default "timestamp")

        Returns:
            CoverageGapResult with detailed gap information
        """
        # Parse timestamps and sort
        timestamps = self._extract_timestamps(deployment_data, timestamp_field)

        if not timestamps:
            return self._no_data_result()

        # Detect gaps
        gaps = self._detect_gaps(timestamps)

        # Calculate coverage percentage
        coverage_days = self._calculate_coverage_days(timestamps)
        coverage_percentage = (coverage_days / self.expected_days) * 100

        # Build result
        return self._build_result(gaps, coverage_percentage, coverage_days)

    def _extract_timestamps(self, deployment_data: List[Dict[str, Any]],
                           timestamp_field: str) -> List[datetime]:
        """Extract and sort timestamps from deployment data."""
        timestamps = []
        for record in deployment_data:
            if timestamp_field in record:
                try:
                    ts_str = record[timestamp_field]
                    if ts_str.endswith('Z'):
                        ts_str = ts_str[:-1] + '+00:00'
                    ts = datetime.fromisoformat(ts_str.replace('+00:00', ''))
                    timestamps.append(ts)
                except (ValueError, TypeError):
                    continue  # Skip invalid timestamps
        return sorted(timestamps)

    def _detect_gaps(self, timestamps: List[datetime]) -> List[GapDetail]:
        """Detect gaps between consecutive deployment timestamps."""
        gaps = []

        for i in range(1, len(timestamps)):
            prev_ts = timestamps[i - 1]
            curr_ts = timestamps[i]
            gap_days = (curr_ts - prev_ts).days - 1  # -1 because adjacent days have 0 gap

            if gap_days > 0:
                severity = self._classify_gap(gap_days)
                gap_start_date = prev_ts + timedelta(days=1)
                gap_end_date = curr_ts - timedelta(days=1)

                # Calculate days ago from period_end to gap dates
                gap_start_days_ago = (self.period_end - gap_start_date).days
                gap_end_days_ago = (self.period_end - gap_end_date).days

                gap = GapDetail(
                    gap_start_days_ago=gap_start_days_ago,
                    gap_end_days_ago=gap_end_days_ago,
                    gap_duration_days=gap_days,
                    severity=severity,
                    gap_start_date=gap_start_date,
                    gap_end_date=gap_end_date
                )
                gaps.append(gap)

        return gaps

    def _classify_gap(self, gap_days: int) -> GapSeverity:
        """Classify gap severity based on duration."""
        if gap_days > self.CRITICAL_GAP_DAYS:
            return GapSeverity.CRITICAL
        elif gap_days >= self.WARNING_GAP_DAYS:
            return GapSeverity.WARNING
        else:
            return GapSeverity.INFO

    def _calculate_coverage_days(self, timestamps: List[datetime]) -> int:
        """Calculate the number of days covered by deployment data."""
        if not timestamps:
            return 0

        coverage_days = set()
        for ts in timestamps:
            # Add this day and surrounding days (deployment typically covers a range)
            for offset in range(-1, 2):  # -1, 0, +1 days
                day = (ts + timedelta(days=offset)).date()
                coverage_days.add(day)

        return len(coverage_days)

    def _build_result(self, gaps: List[GapDetail], coverage_percentage: float,
                     coverage_days: int) -> CoverageGapResult:
        """Build the validation result from detected gaps."""
        has_gaps = len(gaps) > 0
        critical_count = sum(1 for g in gaps if g.severity == GapSeverity.CRITICAL)
        warning_count = sum(1 for g in gaps if g.severity == GapSeverity.WARNING)
        info_count = sum(1 for g in gaps if g.severity == GapSeverity.INFO)

        meets_threshold = coverage_percentage >= self.completeness_threshold

        error_messages = [gap.actionable_message for gap in gaps]

        return CoverageGapResult(
            has_gaps=has_gaps,
            total_gaps=len(gaps),
            critical_gaps=critical_count,
            warning_gaps=warning_count,
            info_gaps=info_count,
            gap_details=gaps,
            error_messages=error_messages,
            coverage_percentage=coverage_percentage,
            meets_threshold=meets_threshold
        )

    def _no_data_result(self) -> CoverageGapResult:
        """Return result for case with no deployment data."""
        return CoverageGapResult(
            has_gaps=True,
            total_gaps=1,
            critical_gaps=1,
            warning_gaps=0,
            info_gaps=0,
            gap_details=[],
            error_messages=[
                f"CRITICAL: No deployment data found for period {self.period_start.date()} "
                f"to {self.period_end.date()}. ACTION: Verify data collection pipeline is "
                f"functioning and deployment records exist for this service."
            ],
            coverage_percentage=0.0,
            meets_threshold=False,
            actionable_summary=(
                f"🚨 CRITICAL: No deployment data available for the {self.expected_days}-day "
                f"analysis period. This indicates a complete data collection failure or the service "
                f"may not have been deployed during this time. Review data collection logs and "
                f"service deployment history."
            )
        )


def validate_completeness_section(data: Dict[str, Any]) -> List[str]:
    """
    Validate the completeness section of deployment data.

    Args:
        data: Deployment data dictionary with completeness section

    Returns:
        List of error messages for completeness validation failures
    """
    errors = []

    if "completeness" not in data:
        errors.append(
            "COMPLETENESS SECTION MISSING: Required 'completeness' object is not present. "
            "ACTION: Add a 'completeness' object with period_coverage_days, data_coverage_percent, "
            "gaps_detected, and meets_completeness_threshold fields to enable 30-day completeness validation."
        )
        return errors

    completeness = data["completeness"]

    # Validate period_coverage_days
    period_coverage = completeness.get("period_coverage_days")
    if period_coverage is None:
        errors.append(
            "period_coverage_days MISSING: Required field not provided. ACTION: Add "
            "'period_coverage_days' integer field indicating the total days covered by deployment data. "
            "For 30-day completeness validation, this should be >= 30."
        )
    elif not isinstance(period_coverage, int) or period_coverage < 30:
        actual = period_coverage if isinstance(period_coverage, int) else "invalid type"
        missing = 30 - period_coverage if isinstance(period_coverage, int) else "unknown"
        errors.append(
            f"MISSING DAYS IN 30-DAY COVERAGE: Period has only {actual} days instead of required 30 days. "
            f"EXPECTED RANGE: Days 1-30 of analysis period. MISSING: {missing} day(s) from the 30-day window. "
            f"ACTION REQUIRED: 1) Add deployment data for the missing {missing} day(s) in the 1-30 day range, "
            f"2) Verify replica_history has entries for all days 1-30, 3) Check if data collection skipped days "
            f"in the period, 4) Extend data collection if days are genuinely missing from the timeframe."
        )

    # Validate data_coverage_percent
    coverage_percent = completeness.get("data_coverage_percent")
    if coverage_percent is None:
        errors.append(
            "data_coverage_percent MISSING: Required field not provided. ACTION: Add "
            "'data_coverage_percent' string field (e.g., '95%', '100%') indicating the percentage "
            "of the 30-day period with deployment data coverage."
        )
    elif not isinstance(coverage_percent, str) or not coverage_percent.endswith('%'):
        errors.append(
            f"Invalid data coverage percentage format: '{coverage_percent}'. REQUIRED FORMAT: 'XX%' "
            f"with % symbol (e.g., '95%', '100%', '87%'). CURRENT VALUE: '{coverage_percent}' does not "
            f"match pattern. ACTION: Provide coverage as a percentage string from '0%' to '100%' ending with % symbol."
        )

    # Validate gaps_detected
    gaps_detected = completeness.get("gaps_detected")
    if gaps_detected is None:
        errors.append(
            "gaps_detected MISSING: Required boolean field not provided. ACTION: Add "
            "'gaps_detected' boolean field (true/false) indicating whether data gaps exist in the 30-day period."
        )
    elif gaps_detected and isinstance(gaps_detected, bool):
        # Check for gap_details when gaps are detected
        gap_details = completeness.get("gap_details")
        if not gap_details or not isinstance(gap_details, list):
            errors.append(
                "GAPS DETECTED WITHOUT DETAILS: gaps_detected=true but gap_details array is missing or empty. "
                "ACTION: Provide gap_details array with entries for each gap, including gap_start_days_ago, "
                "gap_end_days_ago, gap_duration_days, severity, and missing_data_types for each gap."
            )
        elif len(gap_details) > 0:
            # Validate individual gap details
            for i, gap in enumerate(gap_details):
                gap_errors = _validate_gap_detail(gap, i)
                errors.extend(gap_errors)

    # Validate meets_completeness_threshold
    meets_threshold = completeness.get("meets_completeness_threshold")
    if meets_threshold is None:
        errors.append(
            "meets_completeness_threshold MISSING: Required boolean field not provided. ACTION: Add "
            "'meets_completeness_threshold' boolean field (true/false) indicating whether coverage meets "
            "the minimum threshold (default 95%)."
        )
    elif meets_threshold is False and isinstance(meets_threshold, bool):
        threshold = completeness.get("completeness_threshold_percent", "95%")
        coverage = completeness.get("data_coverage_percent", "unknown")
        errors.append(
            f"COMPLETENESS THRESHOLD NOT MET: Deployment data fails minimum coverage requirements. "
            f"COVERAGE: {coverage} actual vs {threshold} required. "
            f"ACTION: 1) Extend data collection period to cover full 30-day window, 2) Fill missing "
            f"deployment data from gap_details periods, 3) Verify replica_history has no gaps >7 days, "
            f"4) Consider adjusting completeness_threshold_percent if current threshold is too strict."
        )

    # Validate deployment_days_threshold_met
    deployment_threshold_met = completeness.get("deployment_days_threshold_met")
    if deployment_threshold_met is False and isinstance(deployment_threshold_met, bool):
        minimum_days = completeness.get("minimum_deployment_days", 1)
        actual_days = completeness.get("actual_deployment_days", 0)
        shortfall = minimum_days - actual_days

        errors.append(
            f"MISSING DEPLOYMENT DAYS IN 30-DAY PERIOD: Insufficient deployment activity detected. "
            f"EXPECTED RANGE: Days 1-30 of analysis period. "
            f"ACTUAL: {actual_days} distinct days with deployments vs REQUIRED: {minimum_days} minimum deployment days. "
            f"SHORTFALL: {shortfall} deployment day(s) missing from the 30-day window. "
            f"IDENTIFY MISSING DAYS: Review which specific days in the 1-30 range lack deployment events. "
            f"CHECK REPLICA_HISTORY: Verify replica_history captures deployment events for all active days. "
            f"ROOT CAUSES: 1) New deployment with limited history in the 30-day window, "
            f"2) Deployment paused or inactive during specific days in 1-30 range, "
            f"3) Insufficient replica_history coverage for some days. "
            f"ACTION REQUIRED: 1) Add deployment data for the {shortfall} missing deployment day(s) in the 1-30 range, "
            f"2) Check if deployment occurred on days not captured in replica_history, "
            f"3) Extend analysis period to capture more deployment activity, "
            f"4) Adjust minimum_deployment_days if deployment frequency is lower than expected for this service type."
        )

    return errors


def _validate_gap_detail(gap: Dict[str, Any], index: int) -> List[str]:
    """Validate a single gap detail entry."""
    errors = []
    prefix = f"gap_details[{index}]"

    # Check required fields
    required_fields = ["gap_start_days_ago", "gap_end_days_ago", "gap_duration_days"]
    for field in required_fields:
        if field not in gap:
            errors.append(
                f"{prefix}.{field} MISSING: Required field not provided. ACTION: Add '{field}' "
                f"integer field to identify the gap timing and duration."
            )

    # Validate gap_start_days_ago
    if "gap_start_days_ago" in gap:
        start = gap["gap_start_days_ago"]
        if not isinstance(start, int) or start < 0:
            errors.append(
                f"INVALID GAP TIMING: {prefix}.gap_start_days_ago cannot be negative. CURRENT VALUE: "
                f"'{start}' days ago. REQUIRED: 0 or more days ago (relative to data_period_end). "
                f"ACTION: Check gap calculation logic - ensure gap_start_days_ago = "
                f"(data_period_end - gap_start_date).days is always non-negative."
            )

    # Validate gap_end_days_ago
    if "gap_end_days_ago" in gap:
        end = gap["gap_end_days_ago"]
        if not isinstance(end, int) or end < 0:
            errors.append(
                f"INVALID GAP TIMING: {prefix}.gap_end_days_ago cannot be negative. CURRENT VALUE: "
                f"'{end}' days ago. REQUIRED: 0 or more days ago (relative to data_period_end). "
                f"ACTION: Verify gap_end_days_ago = (data_period_end - gap_end_date).days calculation "
                f"produces non-negative result."
            )

    # Validate gap_duration_days
    if "gap_duration_days" in gap:
        duration = gap["gap_duration_days"]
        if not isinstance(duration, int) or duration < 1:
            errors.append(
                f"INVALID GAP DURATION: {prefix}.gap_duration_days must be at least 1 day. CURRENT "
                f"VALUE: '{duration}' days. REQUIRED: Minimum 1 day (gaps of 0 days should not be recorded). "
                f"ACTION: Either remove this gap entry (if no actual gap exists) or verify gap calculation: "
                f"gap_duration_days = (gap_end_date - gap_start_date).days must be >= 1."
            )

        # Check severity classification
        severity = gap.get("severity")
        if severity:
            expected_severity = "critical" if duration > 7 else "warning" if duration >= 3 else "info"
            if severity != expected_severity:
                errors.append(
                    f"INVALID SEVERITY LEVEL: {prefix}.severity is '{severity}' but gap_duration_days is "
                    f"{duration} days. EXPECTED: '{expected_severity}' based on duration. "
                    f"SEVERITY CLASSIFICATION: 'critical' = gap >7 days, 'warning' = gap 3-7 days, "
                    f"'info' = gap <3 days. ACTION: Update severity field to match gap duration."
                )

    return errors


__all__ = [
    "CoverageGapValidator",
    "CoverageGapResult",
    "GapDetail",
    "GapSeverity",
    "validate_completeness_section"
]
