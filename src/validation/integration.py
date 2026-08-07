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
    schema: Optional[Dict[str, Any]] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None
) -> Tuple[bool, List[str]]:
    """
    Integration function that calls all validation functions in sequence.

    This function chains all validation steps and collects their errors:
    1. JSON well-formedness validation (validate_json_wellformedness)
    2. Required fields validation (validate_required_fields)
    3. Data types validation (validate_data_types)
    4. Completeness validation (validate_completeness)

    Args:
        file_path: Optional path to JSON file to validate. If provided, loads
                   and parses the file, taking precedence over `data` parameter.
        data: Optional parsed data dictionary to validate with expected fields:
              - service, period_days, total_deployments, etc.
              - deployment_events_last_30_days: list of event dicts with "date" field
        schema: Optional custom validation schema. If not provided, uses
                DEPLOYMENT_DATA_SCHEMA from deployment_data module.
        start_date: Optional custom start date for completeness validation.
                     If not provided, extracts from metadata.time_period.start.
        end_date: Optional custom end date for completeness validation.
                   If not provided, extracts from metadata.time_period.end.

    Returns:
        Tuple of (is_valid: bool, errors: List[str])
        - (True, []) if all validations pass
        - (False, [all_errors]) if any validation fails

    Examples:
        >>> # Validate from file
        >>> is_valid, errors = validate_all(file_path="deployment-data.json")

        >>> # Validate from data dictionary
        >>> data = {"service": "pbx-web", "total_deployments": 30,
        ...         "deployment_events_last_30_days": [...], ...}
        >>> is_valid, errors = validate_all(data=data)
        >>> is_valid
        True

        >>> # With custom schema
        >>> is_valid, errors = validate_all(data=data, schema=custom_schema)

        >>> # With custom date range
        >>> from datetime import datetime
        >>> is_valid, errors = validate_all(
        ...     data=data,
        ...     start_date=datetime(2026, 7, 1),
        ...     end_date=datetime(2026, 7, 30)
        ... )
    """
    # Import validators
    from src.validation.completeness import validate_json_wellformedness
    from src.validation.deployment_data import (
        validate_required_fields,
        validate_data_types,
        DEPLOYMENT_DATA_SCHEMA,
    )

    # Handle input: either file_path or data must be provided
    if file_path is None and data is None:
        return (False, ["Either file_path or data must be provided"])

    # Load from file if file_path is provided (takes precedence over data)
    if file_path is not None:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            return (False, [f"File not found: {file_path}"])
        except json.JSONDecodeError as e:
            return (False, [f"Invalid JSON in file {file_path}: {e}"])

    # Use default schema if none provided
    if schema is None:
        schema = DEPLOYMENT_DATA_SCHEMA

    # Ensure data is a dictionary
    if not isinstance(data, dict):
        return (False, [f"Data must be a dictionary, got {type(data).__name__}"])

    # Collect all validation errors
    errors = []

    # Step 1: JSON well-formedness validation
    # Early termination on JSON parse failure (cannot check further without valid JSON)
    is_valid_json, error_json = validate_json_wellformedness(data)
    if not is_valid_json:
        errors.append(f"JSON validation: {error_json}")
        return (False, errors)

    # Step 2: Required fields validation
    is_valid_fields, error_fields = validate_required_fields(data)
    if not is_valid_fields:
        errors.append(f"Required fields validation: {error_fields}")

    # Step 3: Data types validation
    is_valid_types, error_types = validate_data_types(data, schema)
    if not is_valid_types:
        errors.append(f"Data types validation: {error_types}")

    # Step 4: Completeness validation
    # Extract deployment events for completeness check
    deployment_events = data.get("deployment_events_last_30_days", [])

    # Transform events to have timestamp field for validate_completeness
    # The function expects "timestamp" or "creationTimestamp" field
    events_with_timestamps = []
    for event in deployment_events:
        if isinstance(event, dict) and "date" in event:
            # Convert "date" field to "timestamp" field
            events_with_timestamps.append({"timestamp": event["date"]})
        else:
            # Pass through as-is if it already has the right structure
            events_with_timestamps.append(event)

    # Import and call validate_completeness
    from src.validation.validate_completeness import validate_completeness
    is_valid_complete, error_complete = validate_completeness(events_with_timestamps)
    if not is_valid_complete:
        errors.append(f"Completeness validation: {error_complete}")

    # Return result
    is_valid = len(errors) == 0
    return (is_valid, errors)


__all__ = [
    "validate_all",
]
