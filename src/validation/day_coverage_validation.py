#!/usr/bin/env python3
"""
Day Coverage Validation Error Messages

This module provides comprehensive error messages and validation for day coverage
in 30-day deployment data. It generates detailed, actionable error messages
that specify which days are missing, the expected range, and guidance for remediation.

Usage:
    from src.validation.day_coverage_validation import (
        validate_day_coverage,
        generate_coverage_error_message,
        DayCoverageValidator
    )

    # Validate coverage
    validator = DayCoverageValidator(start_date, end_date, "pbx-web")
    result = validator.validate(daily_counts)

    # Generate error message if needed
    if not result['is_complete']:
        error_msg = generate_coverage_error_message(result)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class CoverageSeverity(Enum):
    """Severity levels for coverage gaps."""
    CRITICAL = "critical"      # > 50% missing data
    HIGH = "high"              # 20-50% missing data
    MEDIUM = "medium"          # 5-20% missing data
    LOW = "low"                # < 5% missing data
    COMPLETE = "complete"      # 100% coverage


@dataclass
class DayCoverageResult:
    """Result of day coverage validation."""
    service_name: str
    expected_days: int
    actual_days: int
    missing_days: int
    coverage_percentage: float
    missing_day_list: List[str]
    sparse_days: List[str]
    severity: CoverageSeverity
    is_complete: bool
    actionable_guidance: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "service_name": self.service_name,
            "expected_days": self.expected_days,
            "actual_days": self.actual_days,
            "missing_days": self.missing_days,
            "coverage_percentage": self.coverage_percentage,
            "missing_day_list": self.missing_day_list,
            "sparse_days": self.sparse_days,
            "severity": self.severity.value,
            "is_complete": self.is_complete,
            "actionable_guidance": self.actionable_guidance
        }


class DayCoverageValidator:
    """Validate day coverage and generate detailed error messages."""

    def __init__(self, start_date: str, end_date: str, service_name: str):
        """
        Initialize the validator.

        Args:
            start_date: ISO format start date (e.g., "2026-07-08T00:00:00Z")
            end_date: ISO format end date (e.g., "2026-08-07T23:59:59Z")
            service_name: Name of the service being validated
        """
        self.start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        self.end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        self.service_name = service_name

    def validate(self, daily_counts: Dict[str, int],
                 sparse_threshold: int = 24) -> DayCoverageResult:
        """
        Validate day coverage from daily counts.

        Args:
            daily_counts: Dictionary mapping date strings to data point counts
            sparse_threshold: Minimum count for a day to be considered non-sparse

        Returns:
            DayCoverageResult with detailed validation information
        """
        expected_days = (self.end_date - self.start_date).days + 1
        actual_days = len(daily_counts)
        missing_days = expected_days - actual_days
        coverage_percentage = round((actual_days / expected_days) * 100, 2) if expected_days > 0 else 0

        # Find specific missing days
        all_days = []
        current = self.start_date
        while current <= self.end_date:
            all_days.append(current.date().isoformat())
            current += timedelta(days=1)

        missing_day_list = [day for day in all_days if day not in daily_counts]

        # Find sparse days
        sparse_days = [
            day for day, count in daily_counts.items()
            if count < sparse_threshold
        ]

        # Determine severity
        severity = self._assess_severity(coverage_percentage, missing_days, expected_days)
        is_complete = missing_days == 0

        # Generate actionable guidance
        guidance = self._generate_guidance(
            coverage_percentage, missing_day_list, sparse_days, expected_days
        )

        return DayCoverageResult(
            service_name=self.service_name,
            expected_days=expected_days,
            actual_days=actual_days,
            missing_days=missing_days,
            coverage_percentage=coverage_percentage,
            missing_day_list=missing_day_list,
            sparse_days=sparse_days,
            severity=severity,
            is_complete=is_complete,
            actionable_guidance=guidance
        )

    def _assess_severity(self, coverage_pct: float, missing_days: int,
                        expected_days: int) -> CoverageSeverity:
        """Assess the severity of coverage gaps."""
        if missing_days == 0:
            return CoverageSeverity.COMPLETE
        elif coverage_pct < 50:
            return CoverageSeverity.CRITICAL
        elif coverage_pct < 80:
            return CoverageSeverity.HIGH
        elif coverage_pct < 95:
            return CoverageSeverity.MEDIUM
        else:
            return CoverageSeverity.LOW

    def _generate_guidance(self, coverage_pct: float, missing_days: List[str],
                          sparse_days: List[str], expected_days: int) -> List[str]:
        """Generate actionable guidance for fixing coverage issues."""
        guidance = []

        if coverage_pct < 50:
            guidance.append(
                f"CRITICAL: Less than 50% coverage ({coverage_pct}%). "
                f"Extend data collection period or investigate data pipeline failures."
            )
        elif coverage_pct < 80:
            guidance.append(
                f"HIGH: Significant gaps in coverage ({coverage_pct}%). "
                f"Review data collection and retention policies."
            )
        elif coverage_pct < 95:
            guidance.append(
                f"MEDIUM: Minor gaps in coverage ({coverage_pct}%). "
                f"Check for intermittent data collection issues."
            )

        if missing_days:
            if len(missing_days) <= 5:
                guidance.append(
                    f"Add deployment data for {len(missing_days)} missing day(s): "
                    f"{', '.join(missing_days[:3])}{'...' if len(missing_days) > 3 else ''}"
                )
            else:
                guidance.append(
                    f"Add deployment data for {len(missing_days)} missing days. "
                    f"First few: {', '.join(missing_days[:3])}, ... "
                    f"Last few: {', '.join(missing_days[-3:])}"
                )

        if sparse_days:
            guidance.append(
                f"Investigate {len(sparse_days)} day(s) with sparse data "
                f"(less than {sparse_threshold} data points). "
                f"May indicate partial data collection."
            )

        if coverage_pct >= 95 and not sparse_days:
            guidance.append(
                "Coverage is excellent (>95%). Minor gaps are acceptable for most analysis."
            )

        return guidance


def generate_coverage_error_message(result: DayCoverageResult) -> str:
    """
    Generate a comprehensive error message for coverage validation.

    Args:
        result: DayCoverageResult from validation

    Returns:
        Formatted error message with details and guidance
    """
    lines = []

    # Header
    lines.append(f"❌ Day Coverage Validation Failed for {result.service_name}")
    lines.append("=" * 70)

    # Summary
    lines.append(f"\n📊 Coverage Summary:")
    lines.append(f"   Expected days: {result.expected_days}")
    lines.append(f"   Actual days:   {result.actual_days}")
    lines.append(f"   Coverage:      {result.coverage_percentage}%")
    lines.append(f"   Severity:      {result.severity.value.upper()}")

    # Missing days details
    if result.missing_day_list:
        lines.append(f"\n🚫 Missing Days ({len(result.missing_day_list)}):")

        if len(result.missing_day_list) <= 10:
            for day in result.missing_day_list:
                lines.append(f"   - {day}")
        else:
            # Show first 5 and last 5
            lines.append("   First 5 missing days:")
            for day in result.missing_day_list[:5]:
                lines.append(f"     - {day}")
            lines.append(f"   ... and {len(result.missing_day_list) - 10} more")
            lines.append("   Last 5 missing days:")
            for day in result.missing_day_list[-5:]:
                lines.append(f"     - {day}")

    # Sparse days
    if result.sparse_days:
        lines.append(f"\n⚠️  Sparse Data Days ({len(result.sparse_days)}):")
        for day in result.sparse_days[:5]:
            lines.append(f"   - {day} (partial data)")
        if len(result.sparse_days) > 5:
            lines.append(f"   ... and {len(result.sparse_days) - 5} more")

    # Actionable guidance
    if result.actionable_guidance:
        lines.append(f"\n💡 Actionable Guidance:")
        for i, guidance in enumerate(result.actionable_guidance, 1):
            lines.append(f"   {i}. {guidance}")

    # Footer
    lines.append("\n" + "=" * 70)

    return "\n".join(lines)


def validate_day_coverage(start_date: str, end_date: str, service_name: str,
                         daily_counts: Dict[str, int]) -> Dict[str, Any]:
    """
    Convenience function to validate day coverage and return dict result.

    Args:
        start_date: ISO format start date
        end_date: ISO format end date
        service_name: Name of the service
        daily_counts: Dictionary mapping date strings to counts

    Returns:
        Dictionary with validation results and error message if applicable
    """
    validator = DayCoverageValidator(start_date, end_date, service_name)
    result = validator.validate(daily_counts)

    response = {
        "validation": result.to_dict(),
        "has_errors": not result.is_complete,
        "error_message": None
    }

    if not result.is_complete:
        response["error_message"] = generate_coverage_error_message(result)

    return response


def main():
    """Example usage and testing."""
    # Example: 30-day window with some missing days
    start_date = "2026-07-08T00:00:00Z"
    end_date = "2026-08-06T23:59:59Z"
    service_name = "pbx-web"

    # Simulate daily counts with some gaps
    daily_counts = {
        "2026-07-08": 100,
        "2026-07-09": 95,
        "2026-07-10": 110,
        # Missing 2026-07-11, 2026-07-12
        "2026-07-13": 105,
        "2026-07-14": 90,
        # ... more days with gaps
    }

    print("=" * 70)
    print("DAY COVERAGE VALIDATION TEST")
    print("=" * 70)

    result = validate_day_coverage(start_date, end_date, service_name, daily_counts)

    if result["has_errors"]:
        print(result["error_message"])
    else:
        print("✅ Coverage validation passed!")

    return 0 if not result["has_errors"] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())