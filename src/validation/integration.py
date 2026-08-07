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
    # Import the JSON well-formedness validator
    from src.validation.completeness import validate_json_wellformedness

    # Step 1: JSON well-formedness validation (EARLY TERMINATION)
    # This is called first to ensure data is well-formed JSON before proceeding.
    # On failure, we immediately return to prevent further validation attempts
    # on malformed data that could cause unexpected errors or false positives.
    is_valid, error = validate_json_wellformedness(data)
    if not is_valid:
        # Early termination: return immediately with JSON validation error
        # No further validation functions are called when JSON is invalid
        return (False, [f"JSON validation: {error}"])

    # TODO: Add remaining validation steps in future beads:
    # - Step 2: Required fields validation (validate_required_fields)
    # - Step 3: Data types validation (validate_data_types)
    # - Step 4: Completeness validation (validate_completeness)

    return (True, [])


__all__ = [
    "validate_all",
]
