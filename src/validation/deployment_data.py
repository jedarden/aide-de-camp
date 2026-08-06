#!/usr/bin/env python3
"""
Deployment data validation functions.

This module provides validation functions for deployment data structures,
checking field presence, data types, and basic constraints.

Usage:
    from src.validation.deployment_data import validate_deployment_data

    data = {"service": "pbx-web", "total_deployments": 10, ...}
    is_valid, error = validate_deployment_data(data)
    if not is_valid:
        print(f"Validation failed: {error}")
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime


# Expected field types for deployment data
DEPLOYMENT_DATA_SCHEMA = {
    # Required string fields
    "service": str,
    "first_deployment": str,
    "last_deployment": str,

    # Required integer fields
    "period_days": int,
    "total_deployments": int,
    "successful_deployments": int,
    "failed_deployments": int,

    # Required float fields
    "success_rate": float,
    "failure_rate": float,
    "deployment_frequency_per_day": float,
    "mean_time_between_deployments_hours": float,

    # Required list fields
    "deployment_names": list,
}


def validate_timestamp(timestamp_str: str) -> bool:
    """
    Validate ISO 8601 timestamp string.

    Args:
        timestamp_str: String to validate as ISO 8601 timestamp

    Returns:
        True if valid timestamp, False otherwise
    """
    if not timestamp_str:
        return False

    try:
        # Handle various ISO formats
        ts = timestamp_str
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        datetime.fromisoformat(ts.replace('+00:00', ''))
        return True
    except (ValueError, AttributeError):
        return False


def validate_deployment_record(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate a single deployment record against the expected schema.

    Args:
        data: Dictionary containing deployment data

    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])
    """
    if not isinstance(data, dict):
        return False, f"Data must be a dictionary, got {type(data).__name__}"

    # Check all required fields are present
    missing_fields = []
    for field_name in DEPLOYMENT_DATA_SCHEMA:
        if field_name not in data:
            missing_fields.append(field_name)

    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"

    # Validate data types
    type_errors = []
    for field_name, expected_type in DEPLOYMENT_DATA_SCHEMA.items():
        value = data[field_name]

        # For float fields, also accept int
        if expected_type is float:
            if not isinstance(value, (int, float)):
                type_errors.append(f"{field_name} must be numeric, got {type(value).__name__}")
        elif expected_type is list:
            if not isinstance(value, list):
                type_errors.append(f"{field_name} must be a list, got {type(value).__name__}")
        else:
            if not isinstance(value, expected_type):
                type_errors.append(f"{field_name} must be {expected_type.__name__}, got {type(value).__name__}")

    if type_errors:
        return False, "; ".join(type_errors)

    # Numeric fields should be non-negative where appropriate (check BEFORE business constraints)
    non_negative_fields = [
        "period_days", "total_deployments", "successful_deployments",
        "failed_deployments", "deployment_frequency_per_day",
        "mean_time_between_deployments_hours"
    ]

    for field in non_negative_fields:
        if field in data and data[field] < 0:
            return False, f"{field} must be non-negative, got {data[field]}"

    # Validate timestamp fields (empty strings are invalid)
    timestamp_fields = ["first_deployment", "last_deployment"]
    for field in timestamp_fields:
        if field in data:
            if not data[field] or not validate_timestamp(data[field]):
                return False, f"{field} contains invalid timestamp: {data[field]}"

    # Validate business constraints
    # total_deployments should equal successful + failed
    total = data.get("total_deployments", 0)
    successful = data.get("successful_deployments", 0)
    failed = data.get("failed_deployments", 0)

    if successful + failed != total:
        return False, f"successful_deployments ({successful}) + failed_deployments ({failed}) must equal total_deployments ({total})"

    # success_rate and failure_rate should sum to 100 (approximately)
    # Exception: when total_deployments is 0, both rates should be 0
    success_rate = data.get("success_rate", 0)
    failure_rate = data.get("failure_rate", 0)

    if total == 0:
        # When no deployments, both rates should be 0
        if success_rate != 0.0 or failure_rate != 0.0:
            return False, f"When total_deployments is 0, success_rate and failure_rate must both be 0.0, got {success_rate} and {failure_rate}"
    elif abs(success_rate + failure_rate - 100.0) > 0.1:  # Allow small floating point errors
        return False, f"success_rate ({success_rate}) + failure_rate ({failure_rate}) should equal 100.0"

    return True, None


def validate_deployment_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate deployment data for field presence and data types.

    This is the main validation function that checks deployment data
    against the expected schema. It can handle both single deployment
    records and collections of deployment data.

    Args:
        data: Dictionary containing deployment data. Can be either:
              - A single deployment record with service/metrics fields
              - A collection with nested structure (e.g., {"services": {...}})

    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])
        Returns True, None if data is valid
        Returns False, error_message if data is invalid

    Examples:
        >>> data = {
        ...     "service": "pbx-web",
        ...     "total_deployments": 10,
        ...     "successful_deployments": 8,
        ...     "failed_deployments": 2,
        ...     "success_rate": 80.0,
        ...     "failure_rate": 20.0,
        ...     "deployment_frequency_per_day": 0.33,
        ...     "mean_time_between_deployments_hours": 72.0,
        ...     "period_days": 30,
        ...     "deployment_names": ["pbx-web"],
        ...     "first_deployment": "2026-07-01T00:00:00Z",
        ...     "last_deployment": "2026-07-30T23:59:59Z"
        ... }
        >>> is_valid, error = validate_deployment_data(data)
        >>> is_valid
        True
    """
    if not isinstance(data, dict):
        return False, f"Data must be a dictionary, got {type(data).__name__}"

    # Check if this is a single deployment record (has 'service' field)
    if "service" in data:
        return validate_deployment_record(data)

    # Check if this is a collection (has 'services' field)
    if "services" in data:
        services = data["services"]
        if not isinstance(services, dict):
            return False, f"'services' must be a dictionary, got {type(services).__name__}"

        # Validate each service's deployment data
        for service_name, service_data in services.items():
            if not isinstance(service_data, dict):
                return False, f"Service '{service_name}' data must be a dictionary, got {type(service_data).__name__}"

            is_valid, error = validate_deployment_record(service_data)
            if not is_valid:
                return False, f"Service '{service_name}': {error}"

        return True, None

    # If neither structure, check if it matches the base schema anyway
    return validate_deployment_record(data)


def validate_deployment_data_simple(data: dict) -> bool:
    """
    Simple validation wrapper that returns only boolean.

    This function provides the exact signature requested in the task:
    validate_deployment_data(data: dict) -> bool

    Args:
        data: Dictionary containing deployment data

    Returns:
        True if data is valid, False if invalid

    Examples:
        >>> good_data = {"service": "test", "total_deployments": 1, ...}
        >>> validate_deployment_data_simple(good_data)
        True
        >>> bad_data = {"service": "test"}  # Missing fields
        >>> validate_deployment_data_simple(bad_data)
        False
    """
    is_valid, _ = validate_deployment_data(data)
    return is_valid


def validate_required_fields(data: dict) -> Tuple[bool, str]:
    """
    Validate that all required fields are present in deployment data.

    This function focuses solely on field presence validation, without checking
    data types or business constraints. It provides a lightweight validation
    to ensure all expected fields exist in the data structure.

    Args:
        data: Dictionary containing deployment data. Can be either:
              - A single deployment record with service/metrics fields
              - A collection with nested structure (e.g., {"services": {...}})

    Returns:
        Tuple of (is_valid: bool, error_message: str)
        Returns (True, "") if all required fields are present
        Returns (False, error_message) if any required fields are missing

    Examples:
        >>> # Valid single deployment record
        >>> data = {
        ...     "service": "pbx-web",
        ...     "period_days": 30,
        ...     "total_deployments": 10,
        ...     "successful_deployments": 8,
        ...     "failed_deployments": 2,
        ...     "success_rate": 80.0,
        ...     "failure_rate": 20.0,
        ...     "deployment_frequency_per_day": 0.33,
        ...     "mean_time_between_deployments_hours": 72.0,
        ...     "deployment_names": ["pbx-web"],
        ...     "first_deployment": "2026-07-01T00:00:00Z",
        ...     "last_deployment": "2026-07-30T23:59:59Z"
        ... }
        >>> is_valid, error = validate_required_fields(data)
        >>> is_valid
        True
        >>> error
        ''

        >>> # Missing required field
        >>> data = {"service": "pbx-web"}
        >>> is_valid, error = validate_required_fields(data)
        >>> is_valid
        False
        >>> "Missing required fields" in error
        True
    """
    if not isinstance(data, dict):
        return False, f"Data must be a dictionary, got {type(data).__name__}"

    # Check if this is a collection (has 'services' field)
    if "services" in data:
        services = data["services"]
        if not isinstance(services, dict):
            return False, f"'services' must be a dictionary, got {type(services).__name__}"

        # Validate each service's deployment data
        for service_name, service_data in services.items():
            if not isinstance(service_data, dict):
                return False, f"Service '{service_name}' data must be a dictionary, got {type(service_data).__name__}"

            is_valid, error = _validate_fields_in_record(service_data)
            if not is_valid:
                # Enhance error message with service context
                enhanced_error = error if error else ""
                if "Missing required fields" in enhanced_error:
                    enhanced_error = f"Service '{service_name}': {enhanced_error}"
                return False, enhanced_error

        return True, ""

    # For single deployment records, check field presence directly
    return _validate_fields_in_record(data)


def _validate_fields_in_record(data: dict) -> Tuple[bool, str]:
    """
    Internal helper to validate field presence in a single deployment record.

    Args:
        data: Dictionary containing deployment record data

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    if not isinstance(data, dict):
        return False, f"Data must be a dictionary, got {type(data).__name__}"

    # Check all required fields are present
    missing_fields = []
    for field_name in DEPLOYMENT_DATA_SCHEMA:
        if field_name not in data:
            missing_fields.append(field_name)

    if missing_fields:
        # Create clear, actionable error message
        if len(missing_fields) == 1:
            error = f"Missing required field: {missing_fields[0]}"
        else:
            # Group related fields for better readability
            error = f"Missing required fields: {', '.join(missing_fields)}"
        return False, error

    return True, ""


def validate_data_types(data: dict, schema: dict) -> Tuple[bool, str]:
    """
    Validate that all data types match the expected schema.

    This function checks that each field in the data matches the expected type
    defined in the schema. It supports strings, integers, floats, lists, and
    date/timestamp validation.

    Args:
        data: Dictionary containing deployment data to validate
        schema: Dictionary mapping field names to their expected types

    Returns:
        Tuple of (is_valid: bool, error_message: str)
        Returns (True, "") if all types are valid
        Returns (False, error_message) if any type mismatches are found

    Examples:
        >>> schema = {"service": str, "total_deployments": int}
        >>> data = {"service": "pbx-web", "total_deployments": 10}
        >>> is_valid, error = validate_data_types(data, schema)
        >>> is_valid
        True
        >>> error
        ''

        >>> # Invalid type
        >>> data = {"service": "pbx-web", "total_deployments": "10"}
        >>> is_valid, error = validate_data_types(data, schema)
        >>> is_valid
        False
        >>> "must be int" in error
        True
    """
    if not isinstance(data, dict):
        return False, f"Data must be a dictionary, got {type(data).__name__}"

    if not isinstance(schema, dict):
        return False, f"Schema must be a dictionary, got {type(schema).__name__}"

    type_errors = []

    for field_name, expected_type in schema.items():
        # Skip validation if field is not present in data
        if field_name not in data:
            continue

        value = data[field_name]

        # Handle float fields - accept both int and float
        if expected_type is float:
            if not isinstance(value, (int, float)):
                type_errors.append(f"{field_name} must be numeric, got {type(value).__name__}")

        # Handle list fields
        elif expected_type is list:
            if not isinstance(value, list):
                type_errors.append(f"{field_name} must be a list, got {type(value).__name__}")

        # Handle string fields
        elif expected_type is str:
            if not isinstance(value, str):
                type_errors.append(f"{field_name} must be str, got {type(value).__name__}")
            else:
                # Additional validation for timestamp fields
                if field_name in ["first_deployment", "last_deployment", "created_at", "updated_at"]:
                    if value and not validate_timestamp(value):
                        type_errors.append(f"{field_name} contains invalid date string: {value}")

        # Handle integer fields
        elif expected_type is int:
            if not isinstance(value, int):
                type_errors.append(f"{field_name} must be int, got {type(value).__name__}")

        # Handle any other expected type
        else:
            if not isinstance(value, expected_type):
                type_errors.append(f"{field_name} must be {expected_type.__name__}, got {type(value).__name__}")

    if type_errors:
        error_message = "; ".join(type_errors)
        return False, error_message

    return True, ""


# Export the simple version as the main function for the task requirement
__all__ = [
    "validate_deployment_data",
    "validate_deployment_data_simple",
    "validate_deployment_record",
    "validate_timestamp",
    "validate_required_fields",
    "validate_data_types",
]
