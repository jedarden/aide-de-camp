#!/usr/bin/env python3
"""
30-Day Completeness Validator for Deployment Data

This module validates deployment data files for 30-day completeness requirements.
Checks for:
- 30-day period coverage
- Gaps in deployment data
- Minimum deployment days
- Clear error messages for completeness failures
"""

import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
from pathlib import Path


class CompletenessError:
    """Represents a completeness validation error with clear messaging."""

    def __init__(self, category: str, message: str, details: Dict[str, Any] = None):
        self.category = category
        self.message = message
        self.details = details or {}

    def __str__(self):
        return f"[{self.category}] {self.message}"

    def to_dict(self):
        return {
            "category": self.category,
            "message": self.message,
            "details": self.details
        }


class CompletenessValidator:
    """Validates 30-day completeness requirements for deployment data."""

    def __init__(self, min_coverage_percent: float = 95.0, min_deployment_days: int = 1):
        """
        Initialize the validator.

        Args:
            min_coverage_percent: Minimum coverage percentage (default 95%)
            min_deployment_days: Minimum deployment days required (default 1)
        """
        self.min_coverage_percent = min_coverage_percent
        self.min_deployment_days = min_deployment_days

    def validate(self, data: Dict) -> Tuple[bool, List[CompletenessError]]:
        """
        Validate deployment data for 30-day completeness.

        Args:
            data: Deployment data dictionary

        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []

        # Check required fields
        if "metadata" not in data:
            errors.append(CompletenessError(
                "missing_field",
                "Missing required field: metadata"
            ))
            return False, errors

        metadata = data["metadata"]
        if "data_period_start" not in metadata or "data_period_end" not in metadata:
            errors.append(CompletenessError(
                "missing_field",
                "Missing required metadata fields: data_period_start or data_period_end"
            ))
            return False, errors

        # Parse period dates
        try:
            period_start = self._parse_timestamp(metadata["data_period_start"])
            period_end = self._parse_timestamp(metadata["data_period_end"])
        except ValueError as e:
            errors.append(CompletenessError(
                "invalid_timestamp",
                f"Invalid timestamp format: {e}"
            ))
            return False, errors

        # Check period length
        period_length = (period_end - period_start).days
        if period_length < 30:
            errors.append(CompletenessError(
                "period_too_short",
                f"Analysis period is only {period_length} days. Minimum required: 30 days.",
                details={"period_length_days": period_length, "minimum_required": 30}
            ))

        # Check replica_history for gaps
        replica_history = data.get("replica_history", [])
        gap_errors = self._check_replica_gaps(
            replica_history,
            period_start,
            period_end
        )
        errors.extend(gap_errors)

        # Check metrics for deployment activity
        metrics = data.get("metrics", {})
        deployment_errors = self._check_deployment_activity(metrics)
        errors.extend(deployment_errors)

        # Check completeness field if present
        completeness = data.get("completeness", {})
        if completeness:
            completeness_errors = self._check_completeness_field(completeness)
            errors.extend(completeness_errors)

        is_valid = len(errors) == 0
        return is_valid, errors

    def _parse_timestamp(self, timestamp: str) -> datetime:
        """Parse ISO 8601 timestamp string."""
        # Handle various ISO 8601 formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(timestamp, fmt)
            except ValueError:
                continue
        raise ValueError(f"Unable to parse timestamp: {timestamp}")

    def _check_replica_gaps(
        self,
        replica_history: List[Dict],
        period_start: datetime,
        period_end: datetime
    ) -> List[CompletenessError]:
        """Check for gaps in replica history coverage."""
        errors = []

        if not replica_history:
            errors.append(CompletenessError(
                "missing_data",
                "No replica history data found. Cannot validate completeness.",
                details={"field": "replica_history", "expected": "at least one entry"}
            ))
            return errors

        # Parse replica timestamps
        replica_dates = []
        for replica in replica_history:
            try:
                created_at = replica.get("created_at")
                if created_at:
                    replica_dates.append(self._parse_timestamp(created_at))
            except ValueError:
                continue

        if not replica_dates:
            errors.append(CompletenessError(
                "invalid_data",
                "No valid timestamps found in replica_history",
                details={"field": "replica_history"}
            ))
            return errors

        # Check for gaps
        replica_dates.sort(reverse=True)  # Most recent first

        # Check if replicas cover the period
        earliest_replica = replica_dates[-1]
        latest_replica = replica_dates[0]

        if earliest_replica > period_start:
            gap_days = (earliest_replica - period_start).days
            if gap_days > 7:  # More than a week gap
                errors.append(CompletenessError(
                    "data_gap",
                    f"Gap of {gap_days} days detected at start of period. "
                    f"Earliest replica is from {earliest_replica.strftime('%Y-%m-%d')}, "
                    f"but period starts on {period_start.strftime('%Y-%m-%d')}.",
                    details={
                        "gap_start_days_ago": (period_end - period_start).days,
                        "gap_end_days_ago": (period_end - earliest_replica).days,
                        "gap_duration_days": gap_days,
                        "severity": "critical" if gap_days > 14 else "warning"
                    }
                ))

        if latest_replica < period_end:
            gap_days = (period_end - latest_replica).days
            if gap_days > 7:
                errors.append(CompletenessError(
                    "data_gap",
                    f"Gap of {gap_days} days detected at end of period. "
                    f"Latest replica is from {latest_replica.strftime('%Y-%m-%d')}, "
                    f"but period ends on {period_end.strftime('%Y-%m-%d')}.",
                    details={
                        "gap_start_days_ago": (period_end - latest_replica).days,
                        "gap_end_days_ago": 0,
                        "gap_duration_days": gap_days,
                        "severity": "critical" if gap_days > 14 else "warning"
                    }
                ))

        # Check for gaps between replicas
        for i in range(len(replica_dates) - 1):
            current = replica_dates[i]
            next_replica = replica_dates[i + 1]
            gap = (current - next_replica).days

            if gap > 7:  # More than a week between replicas
                days_ago = (period_end - next_replica).days
                errors.append(CompletenessError(
                    "data_gap",
                    f"Gap of {gap} days detected between replicas. "
                    f"Gap starts {days_ago} days ago and ends {days_ago + gap} days ago.",
                    details={
                        "gap_start_days_ago": days_ago + gap,
                        "gap_end_days_ago": days_ago,
                        "gap_duration_days": gap,
                        "severity": "critical" if gap > 14 else "warning"
                    }
                ))

        return errors

    def _check_deployment_activity(self, metrics: Dict) -> List[CompletenessError]:
        """Check for deployment activity in metrics."""
        errors = []

        if not metrics:
            errors.append(CompletenessError(
                "missing_field",
                "Missing metrics data. Cannot validate deployment activity.",
                details={"field": "metrics"}
            ))
            return errors

        # Check for deployment counts
        total_deployments = metrics.get("total_deployments", 0)
        successful_deployments = metrics.get("successful_deployments", 0)

        if total_deployments == 0:
            errors.append(CompletenessError(
                "no_deployments",
                "No deployments recorded in the 30-day period. "
                f"Minimum required: {self.min_deployment_days} deployment(s).",
                details={
                    "minimum_deployment_days": self.min_deployment_days,
                    "actual_deployments": 0
                }
            ))

        # Check for analysis period
        analysis_period_days = metrics.get("analysis_period_days")
        if analysis_period_days and analysis_period_days < 30:
            errors.append(CompletenessError(
                "period_too_short",
                f"Metrics analysis period is only {analysis_period_days} days. "
                f"Minimum required: 30 days.",
                details={
                    "analysis_period_days": analysis_period_days,
                    "minimum_required": 30
                }
            ))

        return errors

    def _check_completeness_field(self, completeness: Dict) -> List[CompletenessError]:
        """Check the completeness field for consistency."""
        errors = []

        # Check coverage percent
        coverage_percent = completeness.get("data_coverage_percent", "")
        if coverage_percent:
            try:
                coverage = float(coverage_percent.rstrip("%"))
                if coverage < self.min_coverage_percent:
                    errors.append(CompletenessError(
                        "coverage_below_threshold",
                        f"Data coverage ({coverage}%) is below the minimum threshold "
                        f"({self.min_coverage_percent}%).",
                        details={
                            "actual_coverage_percent": coverage,
                            "minimum_coverage_percent": self.min_coverage_percent
                        }
                    ))
            except ValueError:
                errors.append(CompletenessError(
                    "invalid_coverage_format",
                    f"Invalid coverage percentage format: {coverage_percent}",
                    details={"expected_format": "e.g., '95%', '100%'"}
                ))

        # Check if gaps are reported
        gaps_detected = completeness.get("gaps_detected", False)
        if gaps_detected:
            gap_details = completeness.get("gap_details", [])
            errors.append(CompletenessError(
                "gaps_reported",
                f"Data gaps detected in the completeness report. {len(gap_details)} gap(s) found.",
                details={"gap_count": len(gap_details), "gaps": gap_details}
            ))

        # Check completeness threshold
        meets_threshold = completeness.get("meets_completeness_threshold", True)
        if not meets_threshold:
            errors.append(CompletenessError(
                "completeness_threshold_not_met",
                "Deployment data does not meet the completeness threshold.",
                details={
                    "meets_threshold": False,
                    "minimum_coverage_percent": self.min_coverage_percent
                }
            ))

        return errors


def main():
    """CLI entry point for completeness validation."""
    if len(sys.argv) != 2:
        print("Usage: python validate_30day_completeness.py <deployment-data.json>", file=sys.stderr)
        sys.exit(1)

    data_file = Path(sys.argv[1])
    if not data_file.exists():
        print(f"Error: File not found: {data_file}", file=sys.stderr)
        sys.exit(1)

    # Load deployment data
    try:
        with open(data_file, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate completeness
    validator = CompletenessValidator(min_coverage_percent=95.0, min_deployment_days=1)
    is_valid, errors = validator.validate(data)

    # Print results
    if is_valid:
        print("✓ 30-day completeness validation passed")
        print("  - Period covers 30+ days")
        print("  - No significant gaps detected")
        print("  - Minimum deployment requirements met")
        sys.exit(0)
    else:
        print(f"✗ 30-day completeness validation failed ({len(errors)} error(s))", file=sys.stderr)
        print("", file=sys.stderr)

        # Group errors by category
        errors_by_category = {}
        for error in errors:
            if error.category not in errors_by_category:
                errors_by_category[error.category] = []
            errors_by_category[error.category].append(error)

        for category, category_errors in errors_by_category.items():
            print(f"  [{category.upper()}]", file=sys.stderr)
            for error in category_errors:
                print(f"    - {error.message}", file=sys.stderr)
                if error.details:
                    for key, value in error.details.items():
                        print(f"      {key}: {value}", file=sys.stderr)

        sys.exit(1)


if __name__ == "__main__":
    main()
