#!/usr/bin/env python3
"""
Standalone function for validating deployment data files.

This module provides a simple validation function that checks if a deployment
data file is valid and returns validation results.
"""

from typing import Tuple, List, Dict, Any
from pathlib import Path
import json
from src.validation.validate_completeness import validate_completeness


def validate_deployment_file(file_path: str) -> Tuple[bool, List[str]]:
    """
    Validate a deployment data file.

    This function performs comprehensive validation on a deployment data file,
    checking for file existence, JSON structure, required fields, data types,
    and 30-day coverage completeness.

    Args:
        file_path: Path to the deployment data file to validate

    Returns:
        Tuple of (is_valid: bool, errors: List[str])
        - is_valid: True if the file passes all validation checks
        - errors: List of error messages describing validation failures

    Example:
        >>> is_valid, errors = validate_deployment_file("deployments.json")
        >>> if not is_valid:
        ...     for error in errors:
        ...         print(f"Error: {error}")
    """
    try:
        # Basic file existence check
        if not Path(file_path).exists():
            return False, [f"File not found: {file_path}"]

        # Read and parse JSON
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON: {e}"]

        # Validate structure and extract deployments data
        deployments = None
        errors = []

        if isinstance(data, list):
            # Direct list of deployments
            deployments = data
        elif isinstance(data, dict):
            # Check if it has a 'deployments' key
            if 'deployments' in data:
                deployments = data['deployments']

            # Validate required fields and types
            required_fields = ['service', 'namespace', 'cluster']
            for field in required_fields:
                if field not in data:
                    errors.append(f"Missing required field: {field}")
                elif not isinstance(data[field], str):
                    errors.append(f"Field '{field}' must be str, got {type(data[field]).__name__}")

            # If we have errors, return them
            if errors:
                return False, errors

            # If no deployments, valid for structure check
            if deployments is None:
                return True, []
        else:
            return False, ["Data must be a list or dictionary"]

        # Validate 30-day completeness
        if deployments is not None:
            is_valid, error_message = validate_completeness(deployments)
            if not is_valid:
                return False, [error_message]

        return True, []

    except Exception as e:
        return False, [f"Validation error: {e}"]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        is_valid, errors = validate_deployment_file(file_path)

        if is_valid:
            print(f"✅ Valid: {file_path}")
        else:
            print(f"❌ Invalid: {file_path}")
            for error in errors:
                print(f"  - {error}")
    else:
        print("Usage: python validate_deployment_file.py <file_path>")