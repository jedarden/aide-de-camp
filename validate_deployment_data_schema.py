#!/usr/bin/env python3
"""
Deployment Data Schema Validation

Validates whisper-stt deployment data files against the JSON schema definition.
Ensures structural compliance, type correctness, and 30-day completeness requirements.

Usage:
    python validate_deployment_data_schema.py <deployment_data_file.json>
    python validate_deployment_data_schema.py --check-30-day <deployment_data_file.json>
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Tuple, List
from datetime import datetime, timedelta

try:
    import jsonschema
    from jsonschema import validate, ValidationError, Draft7Validator
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    print("Warning: jsonschema not installed. Install with: pip install jsonschema")
    print("Falling to basic structural validation only.")


# Load the JSON schema
SCHEMA_PATH = Path(__file__).parent / "whisper-stt-deployment-data-schema.json"


def load_schema(schema_path: Path = SCHEMA_PATH) -> Dict[str, Any]:
    """
    Load the deployment data JSON schema.

    Args:
        schema_path: Path to the schema JSON file

    Returns:
        Dict containing the loaded schema

    Raises:
        FileNotFoundError: If schema file doesn't exist
        json.JSONDecodeError: If schema file is invalid JSON
    """
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_deployment_data(filepath: Path) -> Dict[str, Any]:
    """
    Load deployment data JSON file.

    Args:
        filepath: Path to deployment data JSON file

    Returns:
        Dict containing the deployment data

    Raises:
        FileNotFoundError: If data file doesn't exist
        json.JSONDecodeError: If data file is invalid JSON
    """
    if not filepath.exists():
        raise FileNotFoundError(f"Data file not found: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_with_jsonschema(
    data: Dict[str, Any],
    schema: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """
    Validate deployment data against JSON schema using jsonschema library.

    Args:
        data: Deployment data to validate
        schema: JSON schema definition

    Returns:
        Tuple of (is_valid, error_messages)
    """
    if not JSONSCHEMA_AVAILABLE:
        return False, ["jsonschema library not available"]

    errors = []
    validator = Draft7Validator(schema)

    for error in validator.iter_errors(data):
        # Format error message for clarity
        path = " -> ".join(str(p) for p in error.path) if error.path else "root"
        error_msg = f"Path: {path} | Error: {error.message}"
        errors.append(error_msg)

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_basic_structure(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Perform basic structural validation without jsonschema library.

    Args:
        data: Deployment data to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Check if data is a dict
    if not isinstance(data, dict):
        return False, ["Root data must be a JSON object"]

    # Required top-level fields
    required_fields = [
        "metadata",
        "current_status",
        "deployment_events_last_30_days",
        "deployment_metrics",
        "pod_health",
        "infrastructure_details",
        "summary"
    ]

    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate metadata structure
    if "metadata" in data:
        metadata = data["metadata"]
        if not isinstance(metadata, dict):
            errors.append("'metadata' must be an object")
        else:
            required_metadata_fields = [
                "service", "namespace", "cluster",
                "data_collected_at", "time_period"
            ]
            for field in required_metadata_fields:
                if field not in metadata:
                    errors.append(f"metadata.{field} is required")

    # Validate deployment_events_last_30_days is an array
    if "deployment_events_last_30_days" in data:
        events = data["deployment_events_last_30_days"]
        if not isinstance(events, list):
            errors.append("'deployment_events_last_30_days' must be an array")
        elif len(events) == 0:
            errors.append("'deployment_events_last_30_days' must contain at least one event for 30-day completeness")

    # Validate deployment_metrics
    if "deployment_metrics" in data:
        metrics = data["deployment_metrics"]
        if not isinstance(metrics, dict):
            errors.append("'deployment_metrics' must be an object")
        else:
            required_metrics_fields = [
                "total_deployments_last_30_days",
                "successful_deployments",
                "deployment_success_rate"
            ]
            for field in required_metrics_fields:
                if field not in metrics:
                    errors.append(f"deployment_metrics.{field} is required")

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_30_day_completeness(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate 30-day completeness requirements.

    Ensures:
    1. Time period is defined and spans approximately 30 days
    2. At least one deployment event exists in the period
    3. Deployment metrics reflect 30-day window

    Args:
        data: Deployment data to validate

    Returns:
        Tuple of (is_complete, completeness_errors)
    """
    errors = []
    warnings = []

    # Check time period fields exist
    if "metadata" not in data or "data_period_start" not in data["metadata"] or "data_period_end" not in data["metadata"]:
        errors.append("metadata.data_period_start and metadata.data_period_end are required for 30-day completeness validation")
        return False, errors

    metadata = data["metadata"]

    # Check start and end timestamps
    try:
        start_str = metadata["data_period_start"]
        end_str = metadata["data_period_end"]

        start = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))

        # Calculate period length
        period_days = (end - start).days

        # Check if period is approximately 30 days (allow 28-32 days for flexibility)
        if not (28 <= period_days <= 32):
            errors.append(
                f"Analysis period is {period_days} days, expected approximately 30 days "
                f"(acceptable range: 28-32 days)"
            )

    except (ValueError, AttributeError) as e:
        errors.append(f"Invalid timestamp format in time_period: {e}")
        return False, errors

    # Check cluster_deployments exists and has deployment metrics
    if "cluster_deployments" not in data:
        errors.append("cluster_deployments is required for 30-day completeness")
        return False, errors

    cluster_deployments = data["cluster_deployments"]
    if not isinstance(cluster_deployments, dict):
        errors.append("cluster_deployments must be an object")
        return False, errors

    if "whisper-stt" not in cluster_deployments:
        errors.append("cluster_deployments.whisper-stt is required for 30-day completeness")
        return False, errors

    whisper_stt = cluster_deployments["whisper-stt"]
    if not isinstance(whisper_stt, dict):
        errors.append("cluster_deployments.whisper-stt must be an object")
        return False, errors

    if "deployments_last_30_days" not in whisper_stt:
        errors.append("cluster_deployments.whisper-stt.deployments_last_30_days is required")
        return False, errors

    deployments_last_30_days = whisper_stt["deployments_last_30_days"]

    # Check replica_history for deployment events
    events = whisper_stt.get("replica_history", [])
    if not isinstance(events, list):
        errors.append("cluster_deployments.whisper-stt.replica_history must be an array")
        return False, errors

    if len(events) == 0:
        warnings.append(
            "No deployment events found in 30-day period. "
            "This may indicate data collection issues or a period with no deployments."
        )
    else:
        # Check if events fall within the time period
        events_outside_period = 0
        for event in events:
            if not isinstance(event, dict) or "timestamp" not in event:
                continue

            try:
                event_time = datetime.fromisoformat(
                    event["timestamp"].replace('Z', '+00:00')
                )

                if event_time < start or event_time > end:
                    events_outside_period += 1

            except (ValueError, AttributeError):
                # Skip events with invalid timestamps
                continue

        if events_outside_period > 0:
            warnings.append(
                f"{events_outside_period} deployment events fall outside the "
                f"specified time period. Check timestamp alignment."
            )

    # Check summary exists and has 30-day fields
    if "summary" not in data:
        errors.append("summary is required for 30-day completeness")
        return False, errors

    summary = data["summary"]
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
        return False, errors

    if "total_deployments_last_30_days" not in summary:
        errors.append("summary.total_deployments_last_30_days is required")
    else:
        total_deployments = summary["total_deployments_last_30_days"]

        if not isinstance(total_deployments, int):
            errors.append("summary.total_deployments_last_30_days must be an integer")
        elif total_deployments < 0:
            errors.append("summary.total_deployments_last_30_days cannot be negative")
        elif total_deployments == 0 and len(events) > 0:
            warnings.append(
                "summary.total_deployments_last_30_days is 0, "
                "but replica_history contains events. "
                "Verify metrics calculation."
            )
        elif total_deployments != deployments_last_30_days:
            warnings.append(
                f"summary.total_deployments_last_30_days ({total_deployments}) "
                f"does not match cluster_deployments.whisper-stt.deployments_last_30_days ({deployments_last_30_days}). "
                "Verify deployment counting."
            )

    is_complete = len(errors) == 0
    all_messages = errors + warnings

    return is_complete, all_messages


def validate_file(
    filepath: str,
    check_30_day_completeness: bool = True,
    schema_path: Path = SCHEMA_PATH
) -> int:
    """
    Validate a deployment data file.

    Args:
        filepath: Path to deployment data JSON file
        check_30_day_completeness: Whether to check 30-day completeness
        schema_path: Path to JSON schema file

    Returns:
        Exit code (0 for success, 1 for validation failure)
    """
    data_file = Path(filepath)

    print(f"Validating: {data_file}")
    print("-" * 60)

    try:
        # Load data
        data = load_deployment_data(data_file)
        print(f"✓ Loaded deployment data ({len(data)} top-level fields)")

    except FileNotFoundError as e:
        print(f"✗ Error: {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in data file: {e}")
        return 1

    try:
        # Load schema
        schema = load_schema(schema_path)
        print(f"✓ Loaded schema from {schema_path}")

    except FileNotFoundError as e:
        print(f"✗ Error: {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in schema file: {e}")
        return 1

    # Validate against schema
    print("\nSchema validation:")
    print("-" * 60)

    if JSONSCHEMA_AVAILABLE:
        is_valid, errors = validate_with_jsonschema(data, schema)
    else:
        print("  (Using basic structural validation - jsonschema not available)")
        is_valid, errors = validate_basic_structure(data)

    if is_valid:
        print("✓ Schema validation passed")
    else:
        print(f"✗ Schema validation failed with {len(errors)} error(s):")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")

    # Validate 30-day completeness
    if check_30_day_completeness:
        print("\n30-Day completeness validation:")
        print("-" * 60)

        is_complete, messages = validate_30_day_completeness(data)

        if is_complete:
            print("✓ 30-day completeness requirements met")
            if messages:
                print(f"  ({len(messages)} warning(s):")
                for msg in messages:
                    print(f"    - {msg})")
        else:
            print(f"✗ 30-day completeness validation failed:")
            for msg in messages:
                if "Error:" in msg or "must" in msg or "required" in msg:
                    print(f"  ✗ {msg}")
                else:
                    print(f"  ⚠ {msg}")

    # Final result
    print("\n" + "=" * 60)
    if is_valid and (not check_30_day_completeness or is_complete):
        print("✓ Validation successful")
        return 0
    else:
        print("✗ Validation failed")
        return 1


def main():
    """Main entry point for CLI validation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate whisper-stt deployment data against JSON schema"
    )
    parser.add_argument(
        "file",
        help="Path to deployment data JSON file"
    )
    parser.add_argument(
        "--no-30-day-check",
        action="store_true",
        help="Skip 30-day completeness validation"
    )
    parser.add_argument(
        "--schema",
        type=str,
        default=str(SCHEMA_PATH),
        help=f"Path to JSON schema file (default: {SCHEMA_PATH})"
    )

    args = parser.parse_args()

    check_30_day = not args.no_30_day_check
    schema_path = Path(args.schema)

    return validate_file(
        args.file,
        check_30_day_completeness=check_30_day,
        schema_path=schema_path
    )


if __name__ == "__main__":
    sys.exit(main())