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

    # Detailed gap information (optional, populated if gaps detected)
    gap_periods: List[str] = field(default_factory=list)  # String representations of gap periods
    actionable_guidance: List[str] = field(default_factory=list)
    anomaly_messages: List[str] = field(default_factory=list)

    # Deployment interval statistics (optional)
    deployment_intervals: Dict[str, Any] = field(default_factory=dict)

    # Validation timestamp
    validated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        """Convert validation result to dictionary for JSON serialization."""
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

    # Merge gap metrics into result
    if gap_result:
        # Map fields from GapValidationResult to ValidationResult
        result.gap_detected = not gap_result.is_valid  # gaps detected if validation failed
        result.coverage_percentage = gap_result.coverage_percentage
        result.expected_days = gap_result.expected_days
        result.actual_days = gap_result.actual_days
        result.gap_count = len(gap_result.gap_periods)  # calculate from gap_periods list
        result.gap_severity = gap_result.severity.value  # convert enum to string
        result.gap_periods = [f"{gp.start_day} to {gp.end_day}" for gp in gap_result.gap_periods]
        result.actionable_guidance = gap_result.actionable_guidance
        result.anomaly_messages = gap_result.anomaly_messages
        result.deployment_intervals = gap_result.deployment_intervals

        if not is_complete:
            result.errors.append(gap_result.error_message)
            result.is_valid = False

    # Handle return type
    if return_type == "legacy":
        return result.get_legacy_tuple()
    else:
        return result


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

    Args:
        data: Parsed deployment data dictionary

    Returns:
        Tuple of (is_valid, gap_result) where:
            - is_valid: Boolean indicating if completeness validation passed
            - gap_result: GapValidationResult with detailed metrics, or None if validation failed
    """
    from src.validation.completeness import validate_30day_completeness
    from src.validation.gap_integration import validate_gaps_with_guidance, GapValidationResult

    try:
        # First, run standard completeness validation
        is_valid, error = validate_30day_completeness(data)

        # Extract service name from data if available
        service_name = data.get("service_name", "unknown")
        if "metadata" in data and "service_name" in data["metadata"]:
            service_name = data["metadata"]["service_name"]

        # Run comprehensive gap validation with actionable guidance
        gap_result = validate_gaps_with_guidance(data, service_name=service_name)

        # Determine overall validity: must pass completeness check AND meet coverage threshold
        is_complete_valid = is_valid and gap_result.is_valid

        return is_complete_valid, gap_result

    except Exception as e:
        # Handle any exceptions from gap detection gracefully
        import logging
        logging.error(f"Error in gap detection: {str(e)}")

        # Return a failure result with None for gap_result on exception
        return False, None


__all__ = [
    "validate_deployment_file",
]
