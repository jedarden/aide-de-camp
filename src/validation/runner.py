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
from typing import Tuple, List, Dict, Any
import json


def validate_deployment_file(file_path: str) -> Tuple[bool, List[str]]:
    """
    Validate a deployment data file with comprehensive checks.

    This function performs all validation checks in sequence:
    1. JSON well-formedness (file exists and is parseable)
    2. Required fields validation
    3. Data type validation
    4. Completeness validation (30-day coverage, no gaps)

    Args:
        file_path: Path to the deployment data JSON file

    Returns:
        Tuple of (is_valid: bool, error_messages: List[str])
        - (True, []) if all validations pass
        - (False, [error_messages]) if any validation fails

    Examples:
        >>> is_valid, errors = validate_deployment_file("deployment.json")
        >>> if not is_valid:
        ...     for error in errors:
        ...         print(f"ERROR: {error}")
    """
    errors = []

    # Convert to Path object
    path = Path(file_path)

    # Step 1: Check JSON well-formedness (file exists and is parseable)
    is_wellformed, wellformed_error, data = _validate_json_wellformedness(path)
    if not is_wellformed:
        errors.append(f"JSON well-formedness: {wellformed_error}")
        return False, errors

    # Step 2: Required fields validation
    is_complete, complete_errors = _validate_required_fields(data)
    if not is_complete:
        errors.extend([f"Required fields: {e}" for e in complete_errors])
        # Don't return early - continue to collect all errors

    # Step 3: Data type validation
    is_types_valid, type_errors = _validate_data_types(data)
    if not is_types_valid:
        errors.extend([f"Data types: {e}" for e in type_errors])
        # Don't return early - continue to collect all errors

    # Step 4: Completeness validation (30 days, no gaps)
    is_complete, complete_error = _validate_completeness(data)
    if not is_complete:
        errors.append(f"Completeness: {complete_error}")

    # Return results
    is_valid = len(errors) == 0
    return is_valid, errors


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
    Validate 30-day completeness (no gaps, no duplicates).

    Args:
        data: Parsed deployment data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    from src.validation.completeness import validate_30day_completeness

    is_valid, error = validate_30day_completeness(data)
    return is_valid, error


__all__ = [
    "validate_deployment_file",
]
