#!/usr/bin/env python3
"""
Core Deployment Schema Validation Script

Validates deployment data files against core-deployment-schema.json
"""

import json
import sys
from pathlib import Path
from typing import Optional

try:
    from jsonschema import validate, Draft202012Validator, ValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    Draft202012Validator = None


def load_schema(schema_path: Optional[str] = None) -> dict:
    """Load the core deployment schema"""
    if schema_path is None:
        script_dir = Path(__file__).parent
        schema_path = script_dir / "core-deployment-schema.json"

    with open(schema_path, 'r') as f:
        return json.load(f)


def load_data(data_file: str) -> dict:
    """Load deployment data from file"""
    with open(data_file, 'r') as f:
        return json.load(f)


def validate_with_jsonschema(data: dict, schema: dict) -> list:
    """Validate data against schema using jsonschema library"""
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    return errors


def validate_structure(data: dict, schema: dict) -> list:
    """Basic structural validation without jsonschema library"""
    errors = []

    # Check required top-level fields
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            errors.append({"path": f"root.{field}", "message": f"Missing required field: {field}"})

    # Check metadata
    if "metadata" in data:
        metadata = data["metadata"]
        metadata_required = ["generated_at", "data_period_start", "data_period_end",
                            "service_name", "namespace", "cluster"]
        for field in metadata_required:
            if field not in metadata:
                errors.append({"path": f"metadata.{field}",
                             "message": f"Missing required metadata field: {field}"})

    # Check deployment_info
    if "deployment_info" in data:
        deployment = data["deployment_info"]
        deployment_required = ["deployment_name", "created_at", "current_image", "current_replicas"]
        for field in deployment_required:
            if field not in deployment:
                errors.append({"path": f"deployment_info.{field}",
                             "message": f"Missing required deployment field: {field}"})

    # Check current_status
    if "current_status" in data:
        status = data["current_status"]
        status_required = ["sync_status", "health_status", "ready_replicas",
                          "available_replicas", "updated_replicas"]
        for field in status_required:
            if field not in status:
                errors.append({"path": f"current_status.{field}",
                             "message": f"Missing required status field: {field}"})

    # Check metrics
    if "metrics" in data:
        metrics = data["metrics"]
        metrics_required = ["total_deployments", "successful_deployments",
                          "failed_deployments", "deployment_success_rate",
                          "last_deployment_timestamp", "days_since_last_deployment"]
        for field in metrics_required:
            if field not in metrics:
                errors.append({"path": f"metrics.{field}",
                             "message": f"Missing required metrics field: {field}"})

    return errors


def format_errors(errors: list) -> str:
    """Format validation errors for display"""
    if not errors:
        return ""

    output = []
    for error in errors:
        if isinstance(error, ValidationError):
            path = '.'.join(str(p) for p in error.path) if error.path else 'root'
            output.append(f"✗ Path: {path} | Error: {error.message}")
        else:
            path = error.get('path', 'unknown')
            message = error.get('message', 'unknown error')
            output.append(f"✗ Path: {path} | Error: {message}")

    return '\n'.join(output)


def validate_file(data_file: str, schema_path: Optional[str] = None) -> bool:
    """Validate a deployment data file against the core schema"""
    try:
        schema = load_schema(schema_path)
        data = load_data(data_file)
    except FileNotFoundError as e:
        print(f"✗ Error: File not found: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON: {e}")
        return False

    if HAS_JSONSCHEMA:
        errors = validate_with_jsonschema(data, schema)
    else:
        print("⚠ Warning: jsonschema library not installed, using basic structural validation")
        print("  Install with: pip install jsonschema")
        errors = validate_structure(data, schema)

    if errors:
        print(f"✗ Schema validation failed for {data_file}")
        print(format_errors(errors))
        return False
    else:
        print(f"✓ Schema validation passed for {data_file}")
        return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_core_schema.py <data-file.json> [schema-file.json]")
        print("\nExample:")
        print("  python validate_core_schema.py deployment-data.json")
        print("  python validate_core_schema.py deployment-data.json custom-schema.json")
        sys.exit(1)

    data_file = sys.argv[1]
    schema_path = sys.argv[2] if len(sys.argv) > 2 else None

    success = validate_file(data_file, schema_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
