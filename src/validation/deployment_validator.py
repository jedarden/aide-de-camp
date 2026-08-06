#!/usr/bin/env python3
"""
Deployment Data Validation Module

This module provides validation functions for deployment data structures.
It checks field presence and data types against the expected schema.

Usage:
    from src.validation.deployment_validator import validate_deployment_data

    data = {...}
    is_valid, error_message = validate_deployment_data(data)
    if not is_valid:
        print(f"Validation failed: {error_message}")
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime


# Schema definitions based on whisper_stt_deployment_schema.py
REQUIRED_TOP_LEVEL_FIELDS = [
    "metadata",
    "argo_workflows",
    "argo_cd",
    "cluster_deployments",
    "summary"
]

REQUIRED_METADATA_FIELDS = [
    "generated_at",
    "data_period_start",
    "data_period_end",
    "services",
    "clusters",
    "data_sources"
]

REQUIRED_CLUSTER_DEPLOYMENT_FIELDS = [
    "namespace",
    "deployment_name",
    "created_at",
    "current_image",
    "current_replicas",
    "replica_history",
    "deployments_last_30_days",
    "successful_deployments",
    "failed_deployments",
    "deployment_versions",
    "all_versions_in_history"
]

REQUIRED_SUMMARY_FIELDS = [
    "total_deployments_last_30_days",
    "whisper_stt_deployments",
    "successful_deployments",
    "failed_or_scaled_down",
    "data_coverage",
    "gaps_detected",
    "largest_gap_days"
]

REQUIRED_REPLICA_HISTORY_FIELDS = [
    "name",
    "created_at",
    "image",
    "replicas",
    "status",
    "days_ago"
]

# Type definitions: field_name -> (expected_types, is_optional)
TYPE_DEFINITIONS = {
    # Metadata fields
    "metadata.generated_at": (str, False),
    "metadata.data_period_start": (str, False),
    "metadata.data_period_end": (str, False),
    "metadata.services": (list, False),
    "metadata.clusters": (list, False),
    "metadata.data_sources": (list, False),

    # Cluster deployment fields
    "cluster_deployments.namespace": (str, False),
    "cluster_deployments.deployment_name": (str, False),
    "cluster_deployments.created_at": (str, False),
    "cluster_deployments.current_image": (str, False),
    "cluster_deployments.current_replicas": (int, False),
    "cluster_deployments.replica_history": (list, False),
    "cluster_deployments.deployments_last_30_days": (int, False),
    "cluster_deployments.successful_deployments": (int, False),
    "cluster_deployments.failed_deployments": (int, False),
    "cluster_deployments.deployment_versions": (list, False),
    "cluster_deployments.all_versions_in_history": (list, False),
    "cluster_deployments.last_updated": (str, True),

    # Replica history fields
    "replica_history.name": (str, False),
    "replica_history.created_at": (str, False),
    "replica_history.image": (str, False),
    "replica_history.replicas": (int, False),
    "replica_history.status": (str, False),
    "replica_history.days_ago": (int, False),
    "replica_history.available_replicas": ((int, type(None)), True),
    "replica_history.ready_replicas": ((int, type(None)), True),

    # Argo workflows fields
    "argo_workflows.template_name": (str, False),
    "argo_workflows.template_created": (str, False),
    "argo_workflows.workflow_runs_last_30_days": (int, False),
    "argo_workflows.workflow_runs": (list, True),

    # ArgoCD fields
    "argo_cd.application_found": (bool, False),
    "argo_cd.applications": (list, True),

    # Summary fields
    "summary.total_deployments_last_30_days": (int, False),
    "summary.whisper_stt_deployments": (int, False),
    "summary.successful_deployments": (int, False),
    "summary.failed_or_scaled_down": (int, False),
    "summary.data_coverage": (str, False),
    "summary.gaps_detected": (bool, False),
    "summary.largest_gap_days": (int, False),
}


def validate_timestamp(timestamp_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate ISO 8601 timestamp string.

    Args:
        timestamp_str: String to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not timestamp_str:
        return False, "Timestamp cannot be empty"

    try:
        # Handle various ISO formats
        ts = timestamp_str
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        datetime.fromisoformat(ts.replace('+00:00', ''))
        return True, None
    except Exception as e:
        return False, f"Invalid ISO 8601 timestamp: {timestamp_str} - {e}"


def validate_field_type(value: Any, expected_types: tuple, field_name: str, is_optional: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate a field's value against expected types.

    Args:
        value: Value to validate
        expected_types: Tuple of expected types (or single type)
        field_name: Name of the field for error messages
        is_optional: Whether the field is optional

    Returns:
        Tuple of (is_valid, error_message)
    """
    if value is None:
        if is_optional:
            return True, None
        return False, f"Field '{field_name}' is required but is None"

    # Handle tuple of types
    if isinstance(expected_types, tuple):
        if not any(isinstance(value, t) for t in expected_types):
            type_names = [t.__name__ if hasattr(t, '__name__') else str(t) for t in expected_types]
            return False, f"Field '{field_name}' has incorrect type. Expected one of {type_names}, got {type(value).__name__}"
    else:
        if not isinstance(value, expected_types):
            expected_name = expected_types.__name__ if hasattr(expected_types, '__name__') else str(expected_types)
            return False, f"Field '{field_name}' has incorrect type. Expected {expected_name}, got {type(value).__name__}"

    return True, None


def validate_metadata(metadata: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate metadata section.

    Args:
        metadata: Metadata dictionary

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Check required fields
    for field in REQUIRED_METADATA_FIELDS:
        if field not in metadata:
            errors.append(f"Missing required metadata field: {field}")

    # Validate field types
    if "generated_at" in metadata:
        is_valid, error = validate_timestamp(metadata["generated_at"])
        if not is_valid:
            errors.append(error)

    if "data_period_start" in metadata:
        is_valid, error = validate_timestamp(metadata["data_period_start"])
        if not is_valid:
            errors.append(error)

    if "data_period_end" in metadata:
        is_valid, error = validate_timestamp(metadata["data_period_end"])
        if not is_valid:
            errors.append(error)

    # Validate list fields
    if "services" in metadata and not isinstance(metadata["services"], list):
        errors.append("metadata.services must be a list")

    if "clusters" in metadata and not isinstance(metadata["clusters"], list):
        errors.append("metadata.clusters must be a list")

    if "data_sources" in metadata and not isinstance(metadata["data_sources"], list):
        errors.append("metadata.data_sources must be a list")

    return len(errors) == 0, errors


def validate_cluster_deployments(cluster_deployments: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate cluster_deployments section.

    Args:
        cluster_deployments: Cluster deployments dictionary

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Check that we have at least one deployment
    if not cluster_deployments or len(cluster_deployments) == 0:
        errors.append("cluster_deployments cannot be empty")
        return False, errors

    for service_name, deployment_data in cluster_deployments.items():
        if not isinstance(deployment_data, dict):
            errors.append(f"cluster_deployments.{service_name} must be a dictionary")
            continue

        # Check required fields
        for field in REQUIRED_CLUSTER_DEPLOYMENT_FIELDS:
            if field not in deployment_data:
                errors.append(f"Missing required field in cluster_deployments.{service_name}: {field}")

        # Validate field types
        if "namespace" in deployment_data and not isinstance(deployment_data["namespace"], str):
            errors.append(f"cluster_deployments.{service_name}.namespace must be a string")

        if "deployment_name" in deployment_data and not isinstance(deployment_data["deployment_name"], str):
            errors.append(f"cluster_deployments.{service_name}.deployment_name must be a string")

        if "created_at" in deployment_data:
            is_valid, error = validate_timestamp(deployment_data["created_at"])
            if not is_valid:
                errors.append(f"cluster_deployments.{service_name}.created_at: {error}")

        if "current_replicas" in deployment_data and not isinstance(deployment_data["current_replicas"], int):
            errors.append(f"cluster_deployments.{service_name}.current_replicas must be an integer")

        if "replica_history" in deployment_data and isinstance(deployment_data["replica_history"], list):
            # Validate each replica history entry
            for i, entry in enumerate(deployment_data["replica_history"]):
                if not isinstance(entry, dict):
                    errors.append(f"cluster_deployments.{service_name}.replica_history[{i}] must be a dictionary")
                    continue

                for field in REQUIRED_REPLICA_HISTORY_FIELDS:
                    if field not in entry:
                        errors.append(f"Missing required field in cluster_deployments.{service_name}.replica_history[{i}]: {field}")

                # Validate replica history entry types
                if "name" in entry and not isinstance(entry["name"], str):
                    errors.append(f"cluster_deployments.{service_name}.replica_history[{i}].name must be a string")

                if "created_at" in entry:
                    is_valid, error = validate_timestamp(entry["created_at"])
                    if not is_valid:
                        errors.append(f"cluster_deployments.{service_name}.replica_history[{i}].created_at: {error}")

                if "replicas" in entry and not isinstance(entry["replicas"], int):
                    errors.append(f"cluster_deployments.{service_name}.replica_history[{i}].replicas must be an integer")

                if "days_ago" in entry and not isinstance(entry["days_ago"], int):
                    errors.append(f"cluster_deployments.{service_name}.replica_history[{i}].days_ago must be an integer")

    return len(errors) == 0, errors


def validate_summary(summary: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate summary section.

    Args:
        summary: Summary dictionary

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Check required fields
    for field in REQUIRED_SUMMARY_FIELDS:
        if field not in summary:
            errors.append(f"Missing required summary field: {field}")

    # Validate field types
    if "total_deployments_last_30_days" in summary and not isinstance(summary["total_deployments_last_30_days"], int):
        errors.append("summary.total_deployments_last_30_days must be an integer")

    if "whisper_stt_deployments" in summary and not isinstance(summary["whisper_stt_deployments"], int):
        errors.append("summary.whisper_stt_deployments must be an integer")

    if "successful_deployments" in summary and not isinstance(summary["successful_deployments"], int):
        errors.append("summary.successful_deployments must be an integer")

    if "failed_or_scaled_down" in summary and not isinstance(summary["failed_or_scaled_down"], int):
        errors.append("summary.failed_or_scaled_down must be an integer")

    if "data_coverage" in summary and not isinstance(summary["data_coverage"], str):
        errors.append("summary.data_coverage must be a string")

    if "gaps_detected" in summary and not isinstance(summary["gaps_detected"], bool):
        errors.append("summary.gaps_detected must be a boolean")

    if "largest_gap_days" in summary and not isinstance(summary["largest_gap_days"], int):
        errors.append("summary.largest_gap_days must be an integer")

    return len(errors) == 0, errors


def validate_deployment_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate deployment data against the schema.

    This function checks that all required fields are present and that
    data types match the expected schema.

    Args:
        data: Dictionary containing deployment data

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if validation passes, False otherwise
        - error_message: None if valid, error description if invalid
    """
    if not isinstance(data, dict):
        return False, f"Input data must be a dictionary, got {type(data).__name__}"

    all_errors = []

    # Check required top-level fields
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in data:
            all_errors.append(f"Missing required top-level field: {field}")

    # Validate metadata
    if "metadata" in data and isinstance(data["metadata"], dict):
        is_valid, errors = validate_metadata(data["metadata"])
        if not is_valid:
            all_errors.extend(errors)
    elif "metadata" in data:
        all_errors.append("metadata must be a dictionary")

    # Validate cluster_deployments
    if "cluster_deployments" in data and isinstance(data["cluster_deployments"], dict):
        is_valid, errors = validate_cluster_deployments(data["cluster_deployments"])
        if not is_valid:
            all_errors.extend(errors)
    elif "cluster_deployments" in data:
        all_errors.append("cluster_deployments must be a dictionary")

    # Validate summary
    if "summary" in data and isinstance(data["summary"], dict):
        is_valid, errors = validate_summary(data["summary"])
        if not is_valid:
            all_errors.extend(errors)
    elif "summary" in data:
        all_errors.append("summary must be a dictionary")

    # Check argo_workflows
    if "argo_workflows" in data and not isinstance(data["argo_workflows"], dict):
        all_errors.append("argo_workflows must be a dictionary")

    # Check argo_cd
    if "argo_cd" in data and not isinstance(data["argo_cd"], dict):
        all_errors.append("argo_cd must be a dictionary")

    if all_errors:
        error_message = "Validation failed:\n  - " + "\n  - ".join(all_errors)
        return False, error_message

    return True, None


def validate_deployment_data_list(data_list: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Validate a list of deployment data records.

    Args:
        data_list: List of deployment data dictionaries

    Returns:
        Tuple of (all_valid, error_messages)
        - all_valid: True if all records are valid, False otherwise
        - error_messages: List of error messages for invalid records
    """
    if not isinstance(data_list, list):
        return False, [f"Input must be a list, got {type(data_list).__name__}"]

    error_messages = []

    for i, data in enumerate(data_list):
        is_valid, error = validate_deployment_data(data)
        if not is_valid:
            error_messages.append(f"Record {i}: {error}")

    all_valid = len(error_messages) == 0
    return all_valid, error_messages


# Main function for command-line testing
def main():
    """Main function for testing validation."""
    import sys
    import json

    if len(sys.argv) > 1:
        # Load from file
        file_path = sys.argv[1]
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            print(f"Loaded data from: {file_path}")
        except FileNotFoundError:
            print(f"Error: File not found: {file_path}")
            return 1
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON: {e}")
            return 1
    else:
        print("Usage: python deployment_validator.py <deployment_data.json>")
        return 1

    is_valid, error = validate_deployment_data(data)

    print("\n" + "=" * 70)
    print("DEPLOYMENT DATA VALIDATION")
    print("=" * 70)

    if is_valid:
        print("✓ VALIDATION PASSED")
        return 0
    else:
        print("✗ VALIDATION FAILED")
        print(error)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
