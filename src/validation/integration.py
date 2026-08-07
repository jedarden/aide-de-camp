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


def validate_all(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Integration function that calls all validation functions in sequence.

    This function chains all validation steps and collects their errors:
    1. JSON well-formedness validation (validate_json)
    2. Required fields validation (validate_required_fields)
    3. Data types validation (validate_data_types)
    4. Completeness validation (validate_completeness)

    Args:
        data: Parsed data dictionary to validate

    Returns:
        Tuple of (is_valid: bool, errors: List[str])
        - (True, []) if all validations pass
        - (False, [all_errors]) if any validation fails

    Examples:
        >>> data = {"service": "pbx-web", "total_deployments": 10, ...}
        >>> is_valid, errors = validate_all(data=data)
        >>> is_valid
        True
    """
    # Import validators
    from src.validation.completeness import validate_json_wellformedness
    from src.validation.deployment_data import (
        validate_required_fields,
        validate_data_types,
        DEPLOYMENT_DATA_SCHEMA,
    )

    # Collect all validation errors
    errors = []

    # Step 1: JSON well-formedness validation
    is_valid_json, error_json = validate_json_wellformedness(data)
    if not is_valid_json:
        errors.append(f"JSON validation: {error_json}")

    # Step 2: Required fields validation
    # Run regardless of JSON validation result to collect all errors
    is_valid_fields, error_fields = validate_required_fields(data)
    if not is_valid_fields:
        errors.append(f"Required fields validation: {error_fields}")

    # Step 3: Data types validation
    # Run regardless of previous validation results to collect all errors
    is_valid_types, error_types = validate_data_types(data, DEPLOYMENT_DATA_SCHEMA)
    if not is_valid_types:
        errors.append(f"Data types validation: {error_types}")

    # TODO: Add Step 4 in future beads:
    # - Step 4: Completeness validation (validate_completeness)

    # Return result
    is_valid = len(errors) == 0
    return (is_valid, errors)


__all__ = [
    "validate_all",
]
