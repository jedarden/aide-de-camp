"""
Deployment Data Validation Utilities

This module provides comprehensive validation functions for deployment data
against the comprehensive JSON schema defined in deployment-data-schema-comprehensive.json.

Schema Version: 1.0
Date: 2026-08-11
Bead ID: adc-3vohw

Usage:
    from src.utilities.deployment_validation import validate_deployment_data_file

    # Validate a deployment data file
    result = validate_deployment_data_file('whisper-stt-deployment-data.json')

    if result['valid']:
        print(f"✓ Validation passed: {result['summary']}")
    else:
        print(f"✗ Validation failed: {result['errors']}")
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field

try:
    import jsonschema
    from jsonschema import validate, ValidationError
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False


# ============================================================================
# Validation Result Data Structures
# ============================================================================

@dataclass
class ValidationIssue:
    """A single validation issue (error or warning)."""
    code: str
    message: str
    path: str = ""
    severity: str = "error"  # "error", "warning", "info"
    schema_rule: Optional[str] = None


@dataclass
class ValidationResult:
    """Comprehensive validation result for deployment data."""
    valid: bool
    file_path: str
    file_exists: bool
    well_formed_json: bool
    schema_valid: bool
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    info: List[ValidationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert validation result to dictionary."""
        return {
            "valid": self.valid,
            "file_path": self.file_path,
            "file_exists": self.file_exists,
            "well_formed_json": self.well_formed_json,
            "schema_valid": self.schema_valid,
            "errors": [
                {
                    "code": e.code,
                    "message": e.message,
                    "path": e.path,
                    "severity": e.severity,
                    "schema_rule": e.schema_rule
                }
                for e in self.errors
            ],
            "warnings": [
                {
                    "code": w.code,
                    "message": w.message,
                    "path": w.path,
                    "severity": w.severity,
                    "schema_rule": w.schema_rule
                }
                for w in self.warnings
            ],
            "info": [
                {
                    "code": i.code,
                    "message": i.message,
                    "path": i.path,
                    "severity": i.severity,
                    "schema_rule": i.schema_rule
                }
                for i in self.info
            ],
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }


# ============================================================================
# Schema Loading
# ============================================================================

def load_schema(schema_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load the comprehensive deployment data schema.

    Args:
        schema_path: Optional path to schema JSON file. If not provided,
                    uses the default schema at deployment-data-schema-comprehensive.json

    Returns:
        Dictionary containing the JSON schema

    Raises:
        FileNotFoundError: If schema file cannot be found
        ValueError: If schema is invalid
    """
    if schema_path is None:
        # Default to the comprehensive schema in project root
        script_dir = Path(__file__).parent.parent.parent
        schema_path = script_dir / "deployment-data-schema-comprehensive.json"

    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    try:
        with open(schema_file, 'r') as f:
            schema = json.load(f)

        # Basic schema structure validation
        if not isinstance(schema, dict):
            raise ValueError("Schema must be a dictionary")
        if "$schema" not in schema:
            raise ValueError("Schema missing $schema key")
        if "type" not in schema:
            raise ValueError("Schema missing type key")

        return schema

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in schema file: {e}")
    except Exception as e:
        raise ValueError(f"Error loading schema: {e}")


# ============================================================================
# JSON Validation Functions
# ============================================================================

def validate_json_structure(data: Any) -> tuple[bool, List[str]]:
    """
    Validate that data is a well-formed JSON object with expected top-level structure.

    Args:
        data: Parsed JSON data (dictionary, list, or primitive)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    if not isinstance(data, dict):
        errors.append(f"Data must be a JSON object, got {type(data).__name__}")
        return False, errors

    # Check for required top-level keys per schema SV-001
    required_keys = ["metadata", "cluster_deployments", "summary"]
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        errors.append(f"Missing required top-level keys: {', '.join(missing_keys)}")

    return len(errors) == 0, errors


def validate_metadata_structure(metadata: Dict[str, Any]) -> List[ValidationIssue]:
    """
    Validate metadata section structure per schema SV-002.

    Args:
        metadata: Metadata dictionary from deployment data

    Returns:
        List of validation issues found
    """
    issues = []

    required_fields = [
        "generated_at",
        "data_period_start",
        "data_period_end",
        "services",
        "clusters",
        "data_sources"
    ]

    # Check required fields
    for field in required_fields:
        if field not in metadata:
            issues.append(ValidationIssue(
                code="MISSING_REQUIRED_FIELD",
                message=f"Missing required metadata field: {field}",
                path="metadata",
                schema_rule="SV-002"
            ))

    if "services" in metadata:
        if not isinstance(metadata["services"], list):
            issues.append(ValidationIssue(
                code="INVALID_TYPE",
                message="metadata.services must be an array",
                path="metadata.services",
                schema_rule="SV-002"
            ))
        elif len(metadata["services"]) == 0:
            issues.append(ValidationIssue(
                code="EMPTY_ARRAY",
                message="metadata.services must contain at least one service",
                path="metadata.services",
                schema_rule="SV-002"
            ))

    if "clusters" in metadata:
        if not isinstance(metadata["clusters"], list):
            issues.append(ValidationIssue(
                code="INVALID_TYPE",
                message="metadata.clusters must be an array",
                path="metadata.clusters",
                schema_rule="SV-002"
            ))

    return issues


def validate_timestamps(data: Dict[str, Any]) -> List[ValidationIssue]:
    """
    Validate timestamp fields per schema TV-002 and TV-003.

    Args:
        data: Full deployment data dictionary

    Returns:
        List of validation issues found
    """
    issues = []

    def check_iso8601(timestamp_str: str, path: str) -> bool:
        """Check if timestamp string is valid ISO 8601."""
        if not isinstance(timestamp_str, str):
            issues.append(ValidationIssue(
                code="INVALID_TYPE",
                message=f"Timestamp must be a string, got {type(timestamp_str).__name__}",
                path=path,
                schema_rule="TV-002"
            ))
            return False

        try:
            # Try parsing ISO 8601
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            dt = datetime.fromisoformat(timestamp_str.replace('+00:00', ''))
            return True
        except ValueError:
            issues.append(ValidationIssue(
                code="INVALID_TIMESTAMP",
                message=f"Invalid ISO 8601 timestamp format: {timestamp_str}",
                path=path,
                schema_rule="TV-002"
            ))
            return False

    metadata = data.get("metadata", {})

    # Validate metadata timestamps
    for field in ["generated_at", "data_period_start", "data_period_end"]:
        if field in metadata:
            check_iso8601(metadata[field], f"metadata.{field}")

    # Check timestamp consistency (TV-003)
    if all(field in metadata for field in ["generated_at", "data_period_start", "data_period_end"]):
        try:
            start = datetime.fromisoformat(metadata["data_period_start"].replace('Z', '+00:00').replace('+00:00', ''))
            end = datetime.fromisoformat(metadata["data_period_end"].replace('Z', '+00:00').replace('+00:00', ''))
            generated = datetime.fromisoformat(metadata["generated_at"].replace('Z', '+00:00').replace('+00:00', ''))

            if start >= end:
                issues.append(ValidationIssue(
                    code="TIMESTAMP_ORDER",
                    message="data_period_start must be before data_period_end",
                    path="metadata",
                    schema_rule="TV-003"
                ))

            if end > generated:
                issues.append(ValidationIssue(
                    code="TIMESTAMP_ORDER",
                    message="data_period_end must be before or equal to generated_at",
                    path="metadata",
                    schema_rule="TV-003"
                ))
        except ValueError:
            # Timestamp parsing errors already captured above
            pass

    return issues


def validate_data_types(data: Dict[str, Any]) -> List[ValidationIssue]:
    """
    Validate data types match schema requirements per DQ-002.

    Args:
        data: Full deployment data dictionary

    Returns:
        List of validation issues found
    """
    issues = []

    # Validate summary numeric fields
    summary = data.get("summary", {})
    numeric_fields = {
        "total_deployments_last_30_days": int,
        "whisper_stt_deployments": int,
        "successful_deployments": int,
        "failed_or_scaled_down": int,
        "largest_gap_days": int
    }

    for field, expected_type in numeric_fields.items():
        if field in summary:
            if not isinstance(summary[field], expected_type):
                issues.append(ValidationIssue(
                    code="INVALID_TYPE",
                    message=f"summary.{field} must be {expected_type.__name__}, got {type(summary[field]).__name__}",
                    path=f"summary.{field}",
                    schema_rule="DQ-002"
                ))
            elif isinstance(summary[field], int) and summary[field] < 0:
                issues.append(ValidationIssue(
                    code="INVALID_RANGE",
                    message=f"summary.{field} must be non-negative",
                    path=f"summary.{field}",
                    schema_rule="DQ-002"
                ))

    # Validate data_coverage format
    if "data_coverage" in summary:
        if not isinstance(summary["data_coverage"], str):
            issues.append(ValidationIssue(
                code="INVALID_TYPE",
                message="summary.data_coverage must be a string",
                path="summary.data_coverage",
                schema_rule="DQ-002"
            ))
        elif not summary["data_coverage"].endswith('%'):
            issues.append(ValidationIssue(
                code="INVALID_FORMAT",
                message="summary.data_coverage must be a percentage (e.g., '100%')",
                path="summary.data_coverage",
                schema_rule="DQ-002"
            ))

    return issues


def validate_cluster_deployments(data: Dict[str, Any]) -> List[ValidationIssue]:
    """
    Validate cluster deployments section per SV-003 and DQ-001.

    Args:
        data: Full deployment data dictionary

    Returns:
        List of validation issues found
    """
    issues = []

    cluster_deployments = data.get("cluster_deployments", {})

    if not isinstance(cluster_deployments, dict):
        issues.append(ValidationIssue(
            code="INVALID_TYPE",
            message="cluster_deployments must be an object",
            path="cluster_deployments",
            schema_rule="SV-003"
        ))
        return issues

    # Check for whisper-stt deployment data
    if "whisper-stt" not in cluster_deployments:
        issues.append(ValidationIssue(
            code="MISSING_SERVICE_DATA",
            message="cluster_deployments missing 'whisper-stt' key",
            path="cluster_deployments",
            schema_rule="SV-003"
        ))
        return issues

    whisper_stt = cluster_deployments["whisper-stt"]

    # Validate required fields per DQ-001
    required_fields = [
        "namespace",
        "deployment_name",
        "created_at",
        "current_image",
        "current_replicas",
        "deployments_last_30_days",
        "successful_deployments",
        "failed_deployments",
        "deployment_versions"
    ]

    for field in required_fields:
        if field not in whisper_stt:
            issues.append(ValidationIssue(
                code="MISSING_REQUIRED_FIELD",
                message=f"Missing required cluster deployment field: {field}",
                path=f"cluster_deployments.whisper-stt.{field}",
                schema_rule="DQ-001"
            ))

    # Validate current_image format
    if "current_image" in whisper_stt:
        image = whisper_stt["current_image"]
        if isinstance(image, str) and not image.startswith(("ronaldraygun/", "ghcr.io/", "docker.io/")):
            issues.append(ValidationIssue(
                code="INVALID_FORMAT",
                message=f"current_image should match format registry/name:tag, got: {image}",
                path="cluster_deployments.whisper-stt.current_image",
                schema_rule="DQ-001",
                severity="warning"
            ))

    # Validate replica_history presence and minimum count (CV-003)
    if "replica_history" in whisper_stt:
        replica_history = whisper_stt["replica_history"]
        if not isinstance(replica_history, list):
            issues.append(ValidationIssue(
                code="INVALID_TYPE",
                message="replica_history must be an array",
                path="cluster_deployments.whisper-stt.replica_history",
                schema_rule="CV-003"
            ))
        elif len(replica_history) < 5:
            issues.append(ValidationIssue(
                code="INSUFFICIENT_DATA",
                message=f"replica_history must contain at least 5 entries for 30-day analysis, got {len(replica_history)}",
                path="cluster_deployments.whisper-stt.replica_history",
                schema_rule="CV-001"
            ))
    else:
        issues.append(ValidationIssue(
            code="MISSING_REQUIRED_FIELD",
            message="Missing replica_history data required for 30-day analysis",
            path="cluster_deployments.whisper-stt.replica_history",
            schema_rule="CV-003"
        ))

    return issues


# ============================================================================
# Main Validation Functions
# ============================================================================

def validate_deployment_data(
    data: Union[str, Dict[str, Any], Path],
    schema_path: Optional[str] = None
) -> ValidationResult:
    """
    Validate deployment data against the comprehensive schema.

    Args:
        data: Either a file path (str/Path), or a dictionary containing deployment data
        schema_path: Optional path to schema JSON file

    Returns:
        ValidationResult object with detailed validation results

    Raises:
        FileNotFoundError: If file path is provided but file doesn't exist
        ValueError: If schema file is invalid
    """
    # Initialize result
    result = ValidationResult(
        valid=False,
        file_path="",
        file_exists=True,
        well_formed_json=False,
        schema_valid=False
    )

    # Load schema
    try:
        schema = load_schema(schema_path)
        result.metadata["schema_version"] = schema.get("$id", "unknown")
        result.metadata["schema_title"] = schema.get("title", "Deployment Data Schema")
    except (FileNotFoundError, ValueError) as e:
        result.errors.append(ValidationIssue(
            code="SCHEMA_LOAD_ERROR",
            message=str(e),
            path="",
            severity="error"
        ))
        return result

    # Load data if path provided
    if isinstance(data, (str, Path)):
        result.file_path = str(data)
        file_path = Path(data)

        if not file_path.exists():
            result.file_exists = False
            result.errors.append(ValidationIssue(
                code="FILE_NOT_FOUND",
                message=f"File not found: {data}",
                path="",
                severity="error"
            ))
            return result

        try:
            with open(file_path, 'r') as f:
                raw_data = f.read()
                parsed_data = json.loads(raw_data)
                result.metadata["file_size"] = len(raw_data)
        except json.JSONDecodeError as e:
            result.errors.append(ValidationIssue(
                code="INVALID_JSON",
                message=f"Invalid JSON: {e}",
                path="",
                severity="error"
            ))
            return result
        except Exception as e:
            result.errors.append(ValidationIssue(
                code="FILE_READ_ERROR",
                message=f"Error reading file: {e}",
                path="",
                severity="error"
            ))
            return result
    else:
        parsed_data = data
        result.file_path = "<dict_input>"

    # JSON is well-formed
    result.well_formed_json = True

    # Run JSON Schema validation if jsonschema is available
    if JSONSCHEMA_AVAILABLE:
        try:
            validate(instance=parsed_data, schema=schema)
            result.schema_valid = True
        except ValidationError as e:
            result.schema_valid = False
            result.errors.append(ValidationIssue(
                code="SCHEMA_VALIDATION",
                message=f"Schema validation failed: {e.message}",
                path=" -> ".join(str(p) for p in e.path) if e.path else "",
                schema_rule=e.validator,
                severity="error"
            ))
            # Early return on schema validation failure
            return result
    else:
        result.info.append(ValidationIssue(
            code="JSONSCHEMA_NOT_AVAILABLE",
            message="jsonschema library not installed - using basic validation only",
            path="",
            severity="info"
        ))
        # Continue with basic validation

    # Run basic structural validation
    json_valid, json_errors = validate_json_structure(parsed_data)
    for error_msg in json_errors:
        result.errors.append(ValidationIssue(
            code="STRUCTURE_VALIDATION",
            message=error_msg,
            path="",
            schema_rule="SV-001",
            severity="error"
        ))

    if not json_valid:
        return result

    # Validate sections
    if "metadata" in parsed_data:
        metadata_issues = validate_metadata_structure(parsed_data["metadata"])
        for issue in metadata_issues:
            if issue.severity == "error":
                result.errors.append(issue)
            else:
                result.warnings.append(issue)

    # Validate timestamps
    timestamp_issues = validate_timestamps(parsed_data)
    for issue in timestamp_issues:
        if issue.severity == "error":
            result.errors.append(issue)
        else:
            result.warnings.append(issue)

    # Validate data types
    type_issues = validate_data_types(parsed_data)
    for issue in type_issues:
        if issue.severity == "error":
            result.errors.append(issue)
        else:
            result.warnings.append(issue)

    # Validate cluster deployments
    deployment_issues = validate_cluster_deployments(parsed_data)
    for issue in deployment_issues:
        if issue.severity == "error":
            result.errors.append(issue)
        else:
            result.warnings.append(issue)

    # Set overall validity
    result.valid = len(result.errors) == 0

    # Add summary metadata
    if "metadata" in parsed_data:
        result.metadata["data_period_start"] = parsed_data["metadata"].get("data_period_start")
        result.metadata["data_period_end"] = parsed_data["metadata"].get("data_period_end")
        result.metadata["services"] = parsed_data["metadata"].get("services", [])

    if "summary" in parsed_data:
        result.metadata["total_deployments"] = parsed_data["summary"].get("total_deployments_last_30_days", 0)
        result.metadata["data_coverage"] = parsed_data["summary"].get("data_coverage", "N/A")

    return result


def validate_deployment_data_file(
    file_path: Union[str, Path],
    schema_path: Optional[str] = None,
    output_format: str = "dict"
) -> Union[Dict[str, Any], ValidationResult]:
    """
    Validate a deployment data file against the comprehensive schema.

    This is the main entry point for deployment data validation. It accepts a file
    path, loads the JSON data, and validates it against the schema.

    Args:
        file_path: Path to the deployment data JSON file
        schema_path: Optional path to schema JSON file. If not provided, uses the
                    default schema at deployment-data-schema-comprehensive.json
        output_format: Either 'dict' or 'result'. If 'dict', returns a dictionary.
                      If 'result', returns a ValidationResult object.

    Returns:
        If output_format='dict': Dictionary with validation results
        If output_format='result': ValidationResult object

    Example:
        >>> result = validate_deployment_data_file('whisper-stt-deployments.json')
        >>> if result['valid']:
        ...     print(f"✓ Valid: {result['metadata']['total_deployments']} deployments")
        ... else:
        ...     print(f"✗ Invalid: {len(result['errors'])} errors")
    """
    result = validate_deployment_data(file_path, schema_path)

    if output_format == "result":
        return result
    else:
        return result.to_dict()


# ============================================================================
# Batch Validation
# ============================================================================

def validate_multiple_files(
    file_paths: List[Union[str, Path]],
    schema_path: Optional[str] = None
) -> Dict[str, ValidationResult]:
    """
    Validate multiple deployment data files against the schema.

    Args:
        file_paths: List of file paths to validate
        schema_path: Optional path to schema JSON file

    Returns:
        Dictionary mapping file paths to ValidationResult objects
    """
    results = {}
    for file_path in file_paths:
        results[str(file_path)] = validate_deployment_data(file_path, schema_path)
    return results


# ============================================================================
# Main and Testing
# ============================================================================

def main():
    """Main function for testing and demonstration."""
    print("=" * 80)
    print("DEPLOYMENT DATA VALIDATION")
    print("=" * 80)

    # Find sample deployment data files
    script_dir = Path(__file__).parent.parent.parent
    sample_files = [
        script_dir / "whisper-stt-deployment-data-30days.json",
        script_dir / "pbx-web-deployment-data-30days.json",
        script_dir / "deployment-data-schema-comprehensive.json"
    ]

    print(f"\nSearching for sample files...")
    available_files = [f for f in sample_files if f.exists()]

    if not available_files:
        print("No sample files found. Creating test validation with example data...")
        # Create minimal example for testing
        example_data = {
            "metadata": {
                "generated_at": "2026-08-11T00:00:00Z",
                "data_period_start": "2026-07-12T00:00:00Z",
                "data_period_end": "2026-08-11T00:00:00Z",
                "services": ["whisper-stt"],
                "clusters": ["ardenone-cluster"],
                "data_sources": ["kubernetes_replicasets"]
            },
            "cluster_deployments": {
                "whisper-stt": {
                    "namespace": "whisper-stt",
                    "deployment_name": "whisper-stt",
                    "created_at": "2026-05-01T17:26:49Z",
                    "current_image": "ronaldraygun/whisper-stt:1.8.6",
                    "current_replicas": 1,
                    "replica_history": [],
                    "deployments_last_30_days": 0,
                    "successful_deployments": 0,
                    "failed_deployments": 0,
                    "deployment_versions": []
                }
            },
            "summary": {
                "total_deployments_last_30_days": 0,
                "whisper_stt_deployments": 0,
                "successful_deployments": 0,
                "failed_or_scaled_down": 0,
                "data_coverage": "100%",
                "gaps_detected": True,
                "largest_gap_days": 30
            }
        }
        result = validate_deployment_data(example_data)
    else:
        print(f"Found {len(available_files)} sample file(s)")
        for file_path in available_files:
            print(f"\nValidating: {file_path.name}")
            print("-" * 80)

            result = validate_deployment_data(file_path)

            status = "✓ VALID" if result.valid else "✗ INVALID"
            print(f"Status: {status}")
            print(f"File exists: {result.file_exists}")
            print(f"JSON well-formed: {result.well_formed_json}")
            print(f"Schema valid: {result.schema_valid}")

            if result.errors:
                print(f"\n❌ Errors ({len(result.errors)}):")
                for error in result.errors:
                    print(f"  [{error.code}] {error.message}")
                    if error.path:
                        print(f"    Path: {error.path}")
                    if error.schema_rule:
                        print(f"    Rule: {error.schema_rule}")

            if result.warnings:
                print(f"\n⚠️  Warnings ({len(result.warnings)}):")
                for warning in result.warnings:
                    print(f"  [{warning.code}] {warning.message}")
                    if warning.path:
                        print(f"    Path: {warning.path}")

            if result.valid and result.metadata:
                print(f"\n📊 Metadata:")
                if "total_deployments" in result.metadata:
                    print(f"  Total deployments: {result.metadata['total_deployments']}")
                if "data_coverage" in result.metadata:
                    print(f"  Data coverage: {result.metadata['data_coverage']}")

    print("\n" + "=" * 80)
    print(f"JSONSchema library available: {JSONSCHEMA_AVAILABLE}")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
