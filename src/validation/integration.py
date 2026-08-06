#!/usr/bin/env python3
"""
Validation integration function that chains all validation steps.

This module provides the validate_all function that calls all validation
functions in sequence and collects their errors.

Usage:
    from src.validation.integration import validate_all

    # For file-based validation
    is_valid, errors = validate_all(file_path="deployment-data.json")

    # For data-based validation
    data = {"service": "pbx-web", ...}
    is_valid, errors = validate_all(data=data)
"""

from typing import Tuple, List, Dict, Any, Optional, Union
from pathlib import Path
import json


def validate_all(
    file_path: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    schema: Optional[Dict[str, type]] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None
) -> Tuple[bool, List[str]]:
    """
    Integration function that calls all validation functions in sequence.

    This function chains all validation steps and collects their errors:
    1. JSON well-formedness validation (validate_json)
    2. Required fields validation (validate_required_fields)
    3. Data types validation (validate_data_types)
    4. Completeness validation (validate_completeness)

    Args:
        file_path: Path to JSON file to validate (optional if data is provided)
        data: Parsed data dictionary to validate (optional if file_path is provided)
        schema: Schema dict for data type validation (optional, uses default if not provided)
        start_date: Start date for completeness validation (optional)
        end_date: End date for completeness validation (optional)

    Returns:
        Tuple of (is_valid: bool, errors: List[str])
        - (True, []) if all validations pass
        - (False, [all_errors]) if any validation fails

    Note:
        Early termination on JSON parse failure - cannot check further without valid data.

    Examples:
        >>> # Validate from file
        >>> is_valid, errors = validate_all(file_path="deployment-data.json")
        >>> if not is_valid:
        ...     for error in errors:
        ...         print(f"ERROR: {error}")

        >>> # Validate from data
        >>> data = {"service": "pbx-web", "total_deployments": 10, ...}
        >>> is_valid, errors = validate_all(data=data)
        >>> is_valid
        True
    """
    from src.validation.completeness import validate_json_wellformedness, validate_30day_completeness
    from src.validation.deployment_data import validate_required_fields, validate_data_types, DEPLOYMENT_DATA_SCHEMA

    errors: List[str] = []
    parsed_data: Optional[Dict[str, Any]] = None

    # Step 1: Validate JSON well-formedness
    if file_path:
        # Load and validate JSON file
        path = Path(file_path)

        # Check file exists
        if not path.exists():
            return False, [f"File not found: {file_path}"]

        # Try to parse JSON file
        try:
            with open(path, 'r') as f:
                parsed_data = json.load(f)
        except json.JSONDecodeError as e:
            error = f"Invalid JSON in file: {e}"
            return False, [error]  # Early termination - cannot check further
        except Exception as e:
            error = f"Error reading file: {e}"
            return False, [error]  # Early termination - cannot check further

        # Validate JSON structure
        is_valid, json_error = validate_json_wellformedness(parsed_data)
        if not is_valid:
            errors.append(f"JSON validation: {json_error}")
            return False, errors  # Early termination - cannot check further

    elif data:
        # Validate provided data structure
        parsed_data = data
        is_valid, json_error = validate_json_wellformedness(parsed_data)
        if not is_valid:
            errors.append(f"JSON validation: {json_error}")
            return False, errors  # Early termination - cannot check further
    else:
        return False, ["Either file_path or data must be provided"]

    # At this point, we have valid parsed_data
    assert parsed_data is not None, "parsed_data should be set after JSON validation"

    # Step 2: Validate required fields
    is_valid, fields_error = validate_required_fields(parsed_data)
    if not is_valid:
        errors.append(f"Required fields: {fields_error}")
        # Don't return early - continue to collect all errors

    # Step 3: Validate data types
    validation_schema = schema if schema is not None else DEPLOYMENT_DATA_SCHEMA
    is_valid, types_error = validate_data_types(parsed_data, validation_schema)
    if not is_valid:
        errors.append(f"Data types: {types_error}")
        # Don't return early - continue to collect all errors

    # Step 4: Validate completeness (30-day coverage)
    is_valid, completeness_error = validate_30day_completeness(
        parsed_data, start_date, end_date
    )
    if not is_valid:
        errors.append(f"Completeness: {completeness_error}")
        # Don't return early - this is the last validation

    # Return results
    is_valid = len(errors) == 0
    return is_valid, errors


__all__ = [
    "validate_all",
]
