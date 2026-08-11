#!/usr/bin/env python3
"""
Validation runner for deployment data files.

This module provides a unified validation runner that checks:
1. JSON well-formedness (parseable JSON)
2. Required fields validation
3. Data type validation
4. Completeness validation (30 days, no gaps)

Usage:
    from src.validation.runner import validate_deployment_file

    is_valid, errors = validate_deployment_file("deployment-data.json")
    if not is_valid:
        for error in errors:
            print(f"ERROR: {error}")
"""

from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class ValidationResult:
    """
    Comprehensive validation result for deployment data files.

    Includes schema validation results and gap detection metrics.

    Gap Metrics:
        - gap_count: Total number of gap days detected
        - coverage_percentage: Percentage of days with deployment data
        - gap_severity: Overall severity level (none, low, medium, high, critical)
        - gap_type_breakdown: Distribution by gap type (isolated vs consecutive)
        - gap_size_distribution: Distribution by gap size classification
        - gap_periods: List of individual gap period descriptions
    """
    # Basic validation status
    is_valid: bool
    file_path: str

    # Individual validation checks
    is_wellformed_json: bool = False
    has_required_fields: bool = False
    has_valid_types: bool = False
    has_complete_coverage: bool = False

    # Error messages (legacy, for backward compatibility)
    errors: List[str] = field(default_factory=list)

    # Gap metrics (from gap detection)
    gap_detected: bool = False
    coverage_percentage: float = 0.0
    expected_days: int = 0
    actual_days: int = 0
    gap_count: int = 0
    gap_severity: str = "none"  # none, low, medium, high, critical

    # Gap type breakdown (isolated vs consecutive)
    isolated_gap_count: int = 0
    consecutive_gap_sequence_count: int = 0

    # Gap size distribution (classification by size)
    gap_size_distribution: Dict[str, int] = field(default_factory=dict)
    # Expected keys: tiny (1 day), small (2-3 days), medium (4-7 days), large (8-14 days), extended (>14 days)

    # Detailed gap information (optional, populated if gaps detected)
    gap_periods: List[str] = field(default_factory=list)  # String representations of gap periods
    actionable_guidance: List[str] = field(default_factory=list)
    anomaly_messages: List[str] = field(default_factory=list)

    # Deployment interval statistics (optional)
    deployment_intervals: Dict[str, Any] = field(default_factory=dict)

    # Validation timestamp
    validated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert validation result to dictionary for JSON serialization.

        Output Schema:
            {
                "is_valid": bool,
                "file_path": str,
                "is_wellformed_json": bool,
                "has_required_fields": bool,
                "has_valid_types": bool,
                "has_complete_coverage": bool,
                "errors": List[str],
                "gap_detected": bool,
                "coverage_percentage": float,
                "expected_days": int,
                "actual_days": int,
                "gap_count": int,
                "gap_severity": str,  # none, low, medium, high, critical
                "isolated_gap_count": int,
                "consecutive_gap_sequence_count": int,
                "gap_size_distribution": {
                    "tiny": int,      # 1 day gaps
                    "small": int,     # 2-3 day gaps
                    "medium": int,    # 4-7 day gaps
                    "large": int,     # 8-14 day gaps
                    "extended": int   # >14 day gaps
                },
                "gap_periods": List[str],
                "actionable_guidance": List[str],
                "anomaly_messages": List[str],
                "deployment_intervals": Dict[str, Any],
                "validated_at": str  # ISO 8601 timestamp
            }
        """
        return {
            "is_valid": self.is_valid,
            "file_path": self.file_path,
            "is_wellformed_json": self.is_wellformed_json,
            "has_required_fields": self.has_required_fields,
            "has_valid_types": self.has_valid_types,
            "has_complete_coverage": self.has_complete_coverage,
            "errors": self.errors,
            "gap_detected": self.gap_detected,
            "coverage_percentage": self.coverage_percentage,
            "expected_days": self.expected_days,
            "actual_days": self.actual_days,
            "gap_count": self.gap_count,
            "gap_severity": self.gap_severity,
            "isolated_gap_count": self.isolated_gap_count,
            "consecutive_gap_sequence_count": self.consecutive_gap_sequence_count,
            "gap_size_distribution": self.gap_size_distribution,
            "gap_periods": self.gap_periods,
            "actionable_guidance": self.actionable_guidance,
            "anomaly_messages": self.anomaly_messages,
            "deployment_intervals": self.deployment_intervals,
            "validated_at": self.validated_at
        }

    def get_legacy_tuple(self) -> Tuple[bool, List[str]]:
        """
        Return legacy format (is_valid, errors) for backward compatibility.

        Ensures existing code that expects validate_deployment_file to return
        a tuple continues to work without modification.
        """
        return self.is_valid, self.errors


def validate_deployment_file(
    file_path: str,
    return_type: str = "legacy"
) -> Tuple[bool, List[str]] | ValidationResult:
    """
    Validate a deployment data file with comprehensive checks.

    This function performs all validation checks in sequence:
    1. JSON well-formedness (file exists and is parseable)
    2. Required fields validation
    3. Data type validation
    4. Completeness validation (30-day coverage, no gaps)

    Args:
        file_path: Path to the deployment data JSON file
        return_type: "result" to return ValidationResult, "legacy" for tuple format

    Returns:
        ValidationResult (default): Comprehensive validation result with gap metrics
        Tuple (if return_type="legacy"): (is_valid: bool, error_messages: List[str])

    Examples:
        >>> # Legacy format (default, backward compatibility)
        >>> is_valid, errors = validate_deployment_file("deployment.json")
        >>> if not is_valid:
        ...     for error in errors:
        ...         print(f"ERROR: {error}")

        >>> # Enhanced result with gap metrics
        >>> result = validate_deployment_file("deployment.json", return_type="result")
        >>> print(f"Coverage: {result.coverage_percentage}%")
        >>> if result.gap_detected:
        ...     for guidance in result.actionable_guidance:
        ...         print(f"Guidance: {guidance}")
    """
    # Initialize comprehensive result
    result = ValidationResult(
        is_valid=True,
        file_path=file_path
    )

    # Convert to Path object
    path = Path(file_path)

    # Step 1: Check JSON well-formedness (file exists and is parseable)
    is_wellformed, wellformed_error, data = _validate_json_wellformedness(path)
    result.is_wellformed_json = is_wellformed

    if not is_wellformed:
        result.errors.append(f"JSON well-formedness: {wellformed_error}")
        result.is_valid = False
        if return_type == "legacy":
            return result.get_legacy_tuple()
        else:
            return result

    # Step 2: Required fields validation
    is_complete, complete_errors = _validate_required_fields(data)
    result.has_required_fields = is_complete

    if not is_complete:
        result.errors.extend([f"Required fields: {e}" for e in complete_errors])
        result.is_valid = False

    # Step 3: Data type validation
    is_types_valid, type_errors = _validate_data_types(data)
    result.has_valid_types = is_types_valid

    if not is_types_valid:
        result.errors.extend([f"Data types: {e}" for e in type_errors])
        result.is_valid = False

    # Step 4: Completeness validation (30 days, no gaps) - ENHANCED WITH GAP METRICS
    is_complete, gap_result = _validate_completeness_with_gap_metrics(data)
    result.has_complete_coverage = is_complete

    # Merge gap metrics into result with enhanced edge case handling
    if gap_result is not None:
        # Merge gap detection results
        result.gap_detected = not gap_result.is_valid
        result.coverage_percentage = gap_result.coverage_percentage
        result.expected_days = gap_result.expected_days
        result.actual_days = gap_result.actual_days
        result.gap_count = len(gap_result.gap_periods) if gap_result.gap_periods else 0

        # Convert severity enum to string, with fallback
        try:
            result.gap_severity = gap_result.severity.value if hasattr(gap_result.severity, 'value') else str(gap_result.severity)
        except (AttributeError, TypeError):
            result.gap_severity = "unknown"

        # Calculate gap type breakdown (isolated vs consecutive)
        try:
            from src.utilities.gap_calculator import classify_gap_by_size
            isolated_gaps = [gp for gp in gap_result.gap_periods if not gp.is_consecutive]
            consecutive_gaps = [gp for gp in gap_result.gap_periods if gp.is_consecutive]

            result.isolated_gap_count = len(isolated_gaps)

            # Count unique consecutive sequences (by start_day and end_day)
            unique_sequences = set((gp.start_day, gp.end_day) for gp in consecutive_gaps)
            result.consecutive_gap_sequence_count = len(unique_sequences)

            # Calculate gap size distribution
            size_distribution = {
                "tiny": 0,      # 1 day
                "small": 0,     # 2-3 days
                "medium": 0,    # 4-7 days
                "large": 0,     # 8-14 days
                "extended": 0   # >14 days
            }

            for gp in gap_result.gap_periods:
                size_class = classify_gap_by_size(gp)
                size_distribution[size_class] = size_distribution.get(size_class, 0) + 1

            result.gap_size_distribution = size_distribution
        except (AttributeError, TypeError, ImportError):
            # Default values if gap classification fails
            result.isolated_gap_count = 0
            result.consecutive_gap_sequence_count = 0
            result.gap_size_distribution = {}

        # Format gap periods with error handling
        try:
            result.gap_periods = [f"{gp.start_day} to {gp.end_day}" for gp in gap_result.gap_periods]
        except (AttributeError, TypeError):
            result.gap_periods = []

        # Merge actionable guidance and anomaly messages (preserve existing)
        if gap_result.actionable_guidance:
            result.actionable_guidance = gap_result.actionable_guidance
        if gap_result.anomaly_messages:
            result.anomaly_messages = gap_result.anomaly_messages
        if gap_result.deployment_intervals:
            result.deployment_intervals = gap_result.deployment_intervals

        # Add gap error message if validation failed
        if not is_complete and gap_result.error_message:
            # Import the formatter for detailed actionable guidance
            from src.validation.gap_integration import format_gap_validation_result
            # Add the full formatted guidance for better error messages
            formatted_guidance = format_gap_validation_result(gap_result)
            result.errors.append(formatted_guidance)
            result.is_valid = False
    else:
        # Handle gap detection failure - set defaults to preserve schema validation results
        result.gap_detected = False
        result.coverage_percentage = 100.0
        result.expected_days = data.get('period_days', 30)
        result.actual_days = result.expected_days
        result.gap_count = 0
        result.gap_severity = "none"
        result.isolated_gap_count = 0
        result.consecutive_gap_sequence_count = 0
        result.gap_size_distribution = {
            "tiny": 0,
            "small": 0,
            "medium": 0,
            "large": 0,
            "extended": 0
        }
        result.gap_periods = []
        result.actionable_guidance = ["Gap detection was unavailable - schema validation only"]
        result.anomaly_messages = []
        result.deployment_intervals = {}

    # Handle return type
    if return_type == "legacy":
        return result.get_legacy_tuple()
    else:
        return result


def _safe_extract_service_name(data: Dict[str, Any]) -> str:
    """
    Safely extract service name from deployment data with multiple fallbacks.

    Args:
        data: Parsed deployment data dictionary

    Returns:
        Service name string or "unknown" if not found
    """
    # Try direct service field
    if "service" in data and isinstance(data["service"], str):
        return data["service"]

    # Try metadata.service_name
    if "metadata" in data and isinstance(data["metadata"], dict):
        service = data["metadata"].get("service_name")
        if isinstance(service, str):
            return service

    # Try service_name at top level
    if "service_name" in data and isinstance(data["service_name"], str):
        return data["service_name"]

    # Default
    return "unknown"


def _validate_json_wellformedness(file_path: Path) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validate that a JSON file is well-formed and can be parsed.

    Args:
        file_path: Path to JSON file

    Returns:
        Tuple of (is_valid, error_message, parsed_data)
    """
    # Check file exists
    if not file_path.exists():
        return False, f"File does not exist: {file_path}", None

    # Try to parse JSON
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return True, None, data
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {str(e)}", None
    except Exception as e:
        return False, f"Error reading file: {str(e)}", None


def _validate_required_fields(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that all required fields are present in deployment data.

    This function checks for both top-level required fields and
    nested structure requirements.

    Args:
        data: Parsed deployment data dictionary

    Returns:
        Tuple of (is_valid, error_messages)
    """
    from src.validation.deployment_data import validate_required_fields

    is_valid, error = validate_required_fields(data)
    if is_valid:
        return True, []
    else:
        return False, [error]


def _validate_data_types(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that all data types match the expected schema.

    Args:
        data: Parsed deployment data dictionary

    Returns:
        Tuple of (is_valid, error_messages)
    """
    from src.validation.deployment_data import validate_data_types, DEPLOYMENT_DATA_SCHEMA

    is_valid, error = validate_data_types(data, DEPLOYMENT_DATA_SCHEMA)
    if is_valid:
        return True, []
    else:
        return False, [error]


def _validate_completeness(data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate 30-day completeness (no gaps, no duplicates) with actionable guidance.

    This function now integrates gap validation with detailed error messages
    that reference deployment intervals and expected coverage.

    Args:
        data: Parsed deployment data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    from src.validation.completeness import validate_30day_completeness
    from src.validation.gap_integration import (
        validate_gaps_with_guidance,
        format_gap_validation_result
    )

    # First, run standard completeness validation
    is_valid, error = validate_30day_completeness(data)

    # If completeness check fails, run gap validation with guidance
    if not is_valid:
        # Extract service name from data if available
        service_name = data.get("service_name", "unknown")
        if "metadata" in data and "service_name" in data["metadata"]:
            service_name = data["metadata"]["service_name"]

        # Run comprehensive gap validation with actionable guidance
        gap_result = validate_gaps_with_guidance(data, service_name=service_name)

        # If gaps were detected, use the detailed formatted error message
        if gap_result.gap_periods or gap_result.coverage_percentage < 95.0:
            detailed_error = format_gap_validation_result(gap_result)
            return False, detailed_error

    return is_valid, error


def _validate_completeness_with_gap_metrics(data: Dict[str, Any]) -> Tuple[bool, Optional["GapValidationResult"]]:
    """
    Validate 30-day completeness with comprehensive gap metrics.

    This function performs gap detection and returns a detailed GapValidationResult
    with all gap metrics including coverage percentage, gap periods, severity,
    actionable guidance, and anomaly detection.

    Enhanced with edge case handling:
    - Returns a safe default GapValidationResult on gap detection failure
    - Preserves schema validation results even when gap detection fails
    - Handles missing data gracefully without breaking the validation pipeline

    Args:
        data: Parsed deployment data dictionary

    Returns:
        Tuple of (is_valid, gap_result) where:
            - is_valid: Boolean indicating if completeness validation passed
            - gap_result: GapValidationResult with detailed metrics, or safe default on failure
    """
    from src.validation.completeness import validate_30day_completeness
    from src.validation.gap_integration import validate_gaps_with_guidance, GapValidationResult, GapSeverity

    try:
        # First, run standard completeness validation
        is_valid, error = validate_30day_completeness(data)

        # Extract service name using safe helper
        service_name = _safe_extract_service_name(data)

        # Run comprehensive gap validation with actionable guidance
        gap_result = validate_gaps_with_guidance(data, service_name=service_name)

        # Determine overall validity: must pass completeness check AND meet coverage threshold
        is_complete_valid = is_valid and gap_result.is_valid

        return is_complete_valid, gap_result

    except Exception as e:
        # Handle any exceptions from gap detection gracefully
        import logging
        logging.error(f"Error in gap detection for service '{data.get('service', 'unknown')}': {str(e)}", exc_info=True)

        # Create a safe default GapValidationResult instead of returning None
        # This preserves schema validation results while indicating gap detection failure
        safe_result = GapValidationResult(
            is_valid=False,  # Mark as invalid since gap detection failed
            service_name=data.get("service", "unknown"),
            expected_days=30,
            actual_days=0,
            coverage_percentage=0.0,
            severity=GapSeverity.CRITICAL,  # Treat as critical since we can't validate
            error_message=f"Gap detection failed: {str(e)}. Schema validation passed, but completeness could not be verified.",
            actionable_guidance=[
                f"Gap detection encountered an error: {str(e)}",
                "Schema validation completed successfully, but gap detection is required for completeness validation.",
                "Check the deployment data structure and metadata.time_period fields.",
                "Ensure deployment_events_last_30_days or replica_history contains valid date entries.",
                "Review logs for detailed error information."
            ],
            anomaly_messages=[f"Gap detection failure: {str(e)}"],
            deployment_intervals={}
        )

        # Return failure with safe default result
        return False, safe_result


__all__ = [
    "validate_deployment_file",
]
