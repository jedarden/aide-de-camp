#!/usr/bin/env python3
"""
Combined 30-Day Completeness Validator for Deployment Data

This module provides comprehensive validation for deployment data files against
both JSON Schema structure and 30-day completeness requirements.

Validation includes:
1. JSON Schema structure validation (core-deployment-schema-30day-completeness.json)
2. 30-day period coverage validation
3. Gap detection and analysis
4. Minimum deployment days validation
5. Completeness threshold validation

Usage:
    python validate_30day_completeness_combined.py <deployment-data.json>

    With custom schema:
    python validate_30day_completeness_combined.py <deployment-data.json> <schema.json>
"""

import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path


class ValidationError:
    """Represents a validation error with clear messaging and context."""

    CATEGORIES = {
        "schema": "JSON Schema Validation",
        "period": "Period Coverage",
        "gap": "Data Gaps",
        "deployment": "Deployment Activity",
        "completeness": "Completeness Threshold",
        "timestamp": "Timestamp Format"
    }

    def __init__(
        self,
        category: str,
        message: str,
        field_path: str = "",
        details: Dict[str, Any] = None
    ):
        self.category = category
        self.message = message
        self.field_path = field_path
        self.details = details or {}

    def __str__(self):
        category_label = self.CATEGORIES.get(self.category, self.category.upper())
        path_str = f" [{self.field_path}]" if self.field_path else ""
        return f"[{category_label}]{path_str} {self.message}"

    def to_dict(self):
        return {
            "category": self.category,
            "category_label": self.CATEGORIES.get(self.category, self.category.upper()),
            "message": self.message,
            "field_path": self.field_path,
            "details": self.details
        }


class CompletenessValidator:
    """
    Validates deployment data for 30-day completeness requirements.

    This validator checks:
    - 30-day minimum period coverage
    - Gaps in deployment data (>3 days warning, >7 days critical)
    - Minimum deployment days (configurable)
    - Completeness threshold (default 95%)
    """

    def __init__(
        self,
        min_coverage_percent: float = 95.0,
        min_deployment_days: int = 1,
        critical_gap_threshold: int = 7,
        warning_gap_threshold: int = 3
    ):
        """
        Initialize the completeness validator.

        Args:
            min_coverage_percent: Minimum coverage percentage (default 95.0)
            min_deployment_days: Minimum deployment days required (default 1)
            critical_gap_threshold: Days gap considered critical (default 7)
            warning_gap_threshold: Days gap considered warning (default 3)
        """
        self.min_coverage_percent = min_coverage_percent
        self.min_deployment_days = min_deployment_days
        self.critical_gap_threshold = critical_gap_threshold
        self.warning_gap_threshold = warning_gap_threshold

    def validate(self, data: Dict) -> Tuple[bool, List[ValidationError]]:
        """
        Validate deployment data for 30-day completeness.

        Args:
            data: Deployment data dictionary

        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []

        # Phase 1: Check required top-level fields
        errors.extend(self._validate_required_fields(data))

        # If critical fields missing, skip further validation
        if any(e.category == "schema" for e in errors):
            return False, errors

        # Parse period dates
        metadata = data.get("metadata", {})
        try:
            period_start = self._parse_timestamp(metadata.get("data_period_start", ""))
            period_end = self._parse_timestamp(metadata.get("data_period_end", ""))
        except ValueError as e:
            errors.append(ValidationError(
                "timestamp",
                f"Invalid timestamp format: {e}",
                "metadata.data_period_start/data_period_end"
            ))
            return False, errors

        # Phase 2: Validate period length
        errors.extend(self._validate_period_length(period_start, period_end))

        # Phase 3: Check replica_history for gaps
        replica_history = data.get("replica_history", [])
        errors.extend(self._validate_replica_coverage(
            replica_history,
            period_start,
            period_end
        ))

        # Phase 4: Validate deployment activity
        metrics = data.get("metrics", {})
        errors.extend(self._validate_deployment_activity(metrics))

        # Phase 5: Validate completeness section if present
        completeness = data.get("completeness", {})
        if completeness:
            errors.extend(self._validate_completeness_section(completeness))

        is_valid = len(errors) == 0
        return is_valid, errors

    def _validate_required_fields(self, data: Dict) -> List[ValidationError]:
        """Validate required top-level fields."""
        errors = []

        required_fields = ["metadata", "deployment_info", "current_status", "metrics"]
        for field in required_fields:
            if field not in data:
                errors.append(ValidationError(
                    "schema",
                    f"Missing required field: {field}",
                    field
                ))

        # Check metadata sub-fields
        if "metadata" in data:
            metadata = data["metadata"]
            required_metadata = ["data_period_start", "data_period_end", "service_name"]
            for field in required_metadata:
                if field not in metadata:
                    errors.append(ValidationError(
                        "schema",
                        f"Missing required metadata field: {field}",
                        f"metadata.{field}"
                    ))

        return errors

    def _validate_period_length(
        self,
        period_start: datetime,
        period_end: datetime
    ) -> List[ValidationError]:
        """Validate that the period meets minimum length requirements."""
        errors = []

        period_length = (period_end - period_start).days

        if period_length < 30:
            errors.append(ValidationError(
                "period",
                f"Analysis period is only {period_length} days. "
                f"Minimum required: 30 days for completeness validation.",
                "metadata",
                details={
                    "period_length_days": period_length,
                    "minimum_required": 30,
                    "shortfall_days": 30 - period_length
                }
            ))

        return errors

    def _validate_replica_coverage(
        self,
        replica_history: List[Dict],
        period_start: datetime,
        period_end: datetime
    ) -> List[ValidationError]:
        """Validate replica history coverage and detect gaps."""
        errors = []

        if not replica_history:
            errors.append(ValidationError(
                "gap",
                "No replica history data found. Cannot validate completeness.",
                "replica_history",
                details={"expected": "at least one entry"}
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
            errors.append(ValidationError(
                "timestamp",
                "No valid timestamps found in replica_history",
                "replica_history[].created_at"
            ))
            return errors

        # Sort dates (most recent first)
        replica_dates.sort(reverse=True)

        # Check period boundaries
        earliest_replica = replica_dates[-1]
        latest_replica = replica_dates[0]

        # Gap at start of period
        if earliest_replica > period_start:
            gap_days = (earliest_replica - period_start).days
            if gap_days > self.warning_gap_threshold:
                severity = "critical" if gap_days > self.critical_gap_threshold else "warning"
                errors.append(ValidationError(
                    "gap",
                    f"Gap of {gap_days} days detected at start of period. "
                    f"Earliest replica: {earliest_replica.strftime('%Y-%m-%d')}, "
                    f"Period start: {period_start.strftime('%Y-%m-%d')}.",
                    "replica_history",
                    details={
                        "gap_start_days_ago": (period_end - period_start).days,
                        "gap_end_days_ago": (period_end - earliest_replica).days,
                        "gap_duration_days": gap_days,
                        "severity": severity
                    }
                ))

        # Gap at end of period
        if latest_replica < period_end:
            gap_days = (period_end - latest_replica).days
            if gap_days > self.warning_gap_threshold:
                severity = "critical" if gap_days > self.critical_gap_threshold else "warning"
                errors.append(ValidationError(
                    "gap",
                    f"Gap of {gap_days} days detected at end of period. "
                    f"Latest replica: {latest_replica.strftime('%Y-%m-%d')}, "
                    f"Period end: {period_end.strftime('%Y-%m-%d')}.",
                    "replica_history",
                    details={
                        "gap_start_days_ago": (period_end - latest_replica).days,
                        "gap_end_days_ago": 0,
                        "gap_duration_days": gap_days,
                        "severity": severity
                    }
                ))

        # Check for gaps between replicas
        for i in range(len(replica_dates) - 1):
            current = replica_dates[i]
            next_replica = replica_dates[i + 1]
            gap = (current - next_replica).days

            if gap > self.warning_gap_threshold:
                severity = "critical" if gap > self.critical_gap_threshold else "warning"
                days_ago = (period_end - next_replica).days
                errors.append(ValidationError(
                    "gap",
                    f"Gap of {gap} days between replicas "
                    f"({days_ago + gap} to {days_ago} days ago).",
                    "replica_history",
                    details={
                        "gap_start_days_ago": days_ago + gap,
                        "gap_end_days_ago": days_ago,
                        "gap_duration_days": gap,
                        "severity": severity
                    }
                ))

        return errors

    def _validate_deployment_activity(self, metrics: Dict) -> List[ValidationError]:
        """Validate deployment activity in metrics."""
        errors = []

        if not metrics:
            errors.append(ValidationError(
                "deployment",
                "Missing metrics data. Cannot validate deployment activity.",
                "metrics"
            ))
            return errors

        # Check for deployment counts
        total_deployments = metrics.get("total_deployments", 0)

        if total_deployments == 0:
            errors.append(ValidationError(
                "deployment",
                f"No deployments recorded in the analysis period. "
                f"Minimum required: {self.min_deployment_days} deployment(s).",
                "metrics.total_deployments",
                details={
                    "minimum_deployment_days": self.min_deployment_days,
                    "actual_deployments": 0
                }
            ))

        # Check analysis period length in metrics
        analysis_period_days = metrics.get("analysis_period_days")
        if analysis_period_days and analysis_period_days < 30:
            errors.append(ValidationError(
                "period",
                f"Metrics analysis period is only {analysis_period_days} days. "
                f"Minimum required: 30 days.",
                "metrics.analysis_period_days",
                details={
                    "analysis_period_days": analysis_period_days,
                    "minimum_required": 30
                }
            ))

        return errors

    def _validate_completeness_section(self, completeness: Dict) -> List[ValidationError]:
        """Validate the completeness field for consistency and threshold compliance."""
        errors = []

        # Check coverage percent
        coverage_percent_str = completeness.get("data_coverage_percent", "")
        if coverage_percent_str:
            try:
                coverage = float(coverage_percent_str.rstrip("%"))
                if coverage < self.min_coverage_percent:
                    errors.append(ValidationError(
                        "completeness",
                        f"Data coverage ({coverage}%) is below minimum threshold "
                        f"({self.min_coverage_percent}%).",
                        "completeness.data_coverage_percent",
                        details={
                            "actual_coverage_percent": coverage,
                            "minimum_coverage_percent": self.min_coverage_percent,
                            "shortfall_percent": self.min_coverage_percent - coverage
                        }
                    ))
            except ValueError:
                errors.append(ValidationError(
                    "completeness",
                    f"Invalid coverage percentage format: '{coverage_percent_str}'",
                    "completeness.data_coverage_percent",
                    details={"expected_format": "e.g., '95%', '100%'"}
                ))

        # Check if gaps are reported
        gaps_detected = completeness.get("gaps_detected", False)
        if gaps_detected:
            gap_details = completeness.get("gap_details", [])
            errors.append(ValidationError(
                "completeness",
                f"Data gaps detected in completeness report. {len(gap_details)} gap(s) found. "
                f"Completeness validation requires gaps_detected=false.",
                "completeness.gaps_detected",
                details={"gap_count": len(gap_details), "gaps": gap_details}
            ))

        # Check completeness threshold
        meets_threshold = completeness.get("meets_completeness_threshold", True)
        if not meets_threshold:
            errors.append(ValidationError(
                "completeness",
                "Deployment data does not meet completeness threshold. "
                "See gap_details for specific issues.",
                "completeness.meets_completeness_threshold",
                details={
                    "meets_threshold": False,
                    "minimum_coverage_percent": self.min_coverage_percent
                }
            ))

        # Check deployment days threshold
        deployment_days_met = completeness.get("deployment_days_threshold_met", True)
        if not deployment_days_met:
            actual_days = completeness.get("actual_deployment_days", 0)
            min_days = completeness.get("minimum_deployment_days", self.min_deployment_days)
            errors.append(ValidationError(
                "deployment",
                f"Deployment days threshold not met. "
                f"Actual: {actual_days} days, Required: {min_days} days.",
                "completeness.deployment_days_threshold_met",
                details={
                    "actual_deployment_days": actual_days,
                    "minimum_deployment_days": min_days,
                    "shortfall_days": min_days - actual_days
                }
            ))

        return errors

    def _parse_timestamp(self, timestamp: str) -> datetime:
        """Parse ISO 8601 timestamp string."""
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


def validate_with_jsonschema(
    data: Dict,
    schema_path: Optional[str] = None
) -> Tuple[bool, List[ValidationError]]:
    """
    Validate data against JSON Schema using jsonschema library.

    Returns:
        Tuple of (is_valid, errors)
    """
    try:
        from jsonschema import validate, Draft202012Validator, ValidationError as JSONSchemaValidationError
    except ImportError:
        return True, [ValidationError(
            "schema",
            "jsonschema library not installed. Install with: pip install jsonschema",
            ""
        )]

    if schema_path is None:
        script_dir = Path(__file__).parent
        schema_path = script_dir / "core-deployment-schema-30day-completeness.json"

    try:
        with open(schema_path, 'r') as f:
            schema = json.load(f)
    except FileNotFoundError:
        return False, [ValidationError(
            "schema",
            f"Schema file not found: {schema_path}",
            ""
        )]

    errors = []
    validator = Draft202012Validator(schema)

    for error in validator.iter_errors(data):
        path = '.'.join(str(p) for p in error.path) if error.path else 'root'
        errors.append(ValidationError(
            "schema",
            error.message,
            path,
            details={"validator": error.validator, "schema_path": list(error.schema_path)}
        ))

    return len(errors) == 0, errors


def main():
    """CLI entry point for combined completeness validation."""
    if len(sys.argv) < 2:
        print("Usage: python validate_30day_completeness_combined.py <deployment-data.json> [schema.json]", file=sys.stderr)
        print("\nValidates deployment data for 30-day completeness requirements:")
        print("  1. JSON Schema structure validation")
        print("  2. 30-day period coverage")
        print("  3. Gap detection (>3 days warning, >7 days critical)")
        print("  4. Minimum deployment days")
        print("  5. Completeness threshold validation")
        sys.exit(1)

    data_file = Path(sys.argv[1])
    if not data_file.exists():
        print(f"✗ Error: File not found: {data_file}", file=sys.stderr)
        sys.exit(1)

    schema_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Load deployment data
    try:
        with open(data_file, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON file: {e}", file=sys.stderr)
        sys.exit(1)

    # Phase 1: JSON Schema validation
    print("Phase 1: JSON Schema structure validation...")
    schema_valid, schema_errors = validate_with_jsonschema(data, schema_path)

    # Phase 2: 30-day completeness validation
    print("Phase 2: 30-day completeness validation...")
    validator = CompletenessValidator(
        min_coverage_percent=95.0,
        min_deployment_days=1,
        critical_gap_threshold=7,
        warning_gap_threshold=3
    )
    completeness_valid, completeness_errors = validator.validate(data)

    all_errors = schema_errors + completeness_errors

    # Print results
    if not all_errors:
        print("✓ 30-day completeness validation passed")
        print("  ✓ JSON Schema structure valid")
        print("  ✓ Period covers 30+ days")
        print("  ✓ No significant gaps detected")
        print("  ✓ Minimum deployment requirements met")
        print("  ✓ Completeness threshold met")
        sys.exit(0)
    else:
        print(f"✗ Validation failed ({len(all_errors)} error(s))", file=sys.stderr)
        print("", file=sys.stderr)

        # Group errors by category
        errors_by_category = {}
        for error in all_errors:
            if error.category not in errors_by_category:
                errors_by_category[error.category] = []
            errors_by_category[error.category].append(error)

        for category, errors in errors_by_category.items():
            category_label = ValidationError.CATEGORIES.get(category, category.upper())
            print(f"  {category_label} ({len(errors)} error(s))", file=sys.stderr)
            for error in errors:
                print(f"    ✗ {error}", file=sys.stderr)
                if error.details:
                    for key, value in error.details.items():
                        print(f"      {key}: {value}", file=sys.stderr)

        sys.exit(1)


if __name__ == "__main__":
    main()
