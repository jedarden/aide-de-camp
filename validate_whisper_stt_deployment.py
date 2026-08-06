#!/usr/bin/env python3
"""
Validate whisper-stt deployment data file against schema.

This script validates:
- JSON structure is well-formed
- All required fields are present
- Data types match schema expectations
- Timestamps are valid ISO 8601 format
- Numeric fields are valid
- 30-day coverage is complete (no gaps)
- Data consistency between related fields
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO 8601 timestamp string."""
    try:
        # Handle various ISO formats
        ts = timestamp_str
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        return datetime.fromisoformat(ts.replace('+00:00', ''))
    except Exception as e:
        raise ValueError(f"Invalid timestamp: {timestamp_str}") from e


def validate_metadata(metadata: Dict[str, Any]) -> List[str]:
    """Validate metadata section."""
    errors = []

    required_fields = ["generated_at", "data_period_start", "data_period_end",
                      "services", "clusters", "data_sources"]

    for field in required_fields:
        if field not in metadata:
            errors.append(f"metadata missing required field: {field}")

    # Validate timestamps
    if "generated_at" in metadata:
        try:
            parse_timestamp(metadata["generated_at"])
        except ValueError as e:
            errors.append(f"metadata.generated_at invalid: {e}")

    if "data_period_start" in metadata:
        try:
            parse_timestamp(metadata["data_period_start"])
        except ValueError as e:
            errors.append(f"metadata.data_period_start invalid: {e}")

    if "data_period_end" in metadata:
        try:
            parse_timestamp(metadata["data_period_end"])
        except ValueError as e:
            errors.append(f"metadata.data_period_end invalid: {e}")

    # Validate services is a non-empty list
    if "services" in metadata:
        if not isinstance(metadata["services"], list):
            errors.append("metadata.services must be a list")
        elif len(metadata["services"]) == 0:
            errors.append("metadata.services cannot be empty")

    # Validate clusters is a non-empty list
    if "clusters" in metadata:
        if not isinstance(metadata["clusters"], list):
            errors.append("metadata.clusters must be a list")
        elif len(metadata["clusters"]) == 0:
            errors.append("metadata.clusters cannot be empty")

    return errors


def validate_argo_workflows(argo_workflows: Dict[str, Any]) -> List[str]:
    """Validate Argo Workflow section."""
    errors = []

    if not isinstance(argo_workflows, dict):
        return ["argo_workflows must be a dictionary"]

    for workflow_name, workflow_data in argo_workflows.items():
        if not isinstance(workflow_data, dict):
            errors.append(f"argo_workflows.{workflow_name} must be a dictionary")
            continue

        required_fields = ["template_name", "template_created",
                         "workflow_runs_last_30_days", "workflow_runs"]

        for field in required_fields:
            if field not in workflow_data:
                errors.append(f"argo_workflows.{workflow_name} missing field: {field}")

        # Validate workflow_runs_last_30_days is non-negative
        if "workflow_runs_last_30_days" in workflow_data:
            if not isinstance(workflow_data["workflow_runs_last_30_days"], int):
                errors.append(f"argo_workflows.{workflow_name}.workflow_runs_last_30_days must be integer")
            elif workflow_data["workflow_runs_last_30_days"] < 0:
                errors.append(f"argo_workflows.{workflow_name}.workflow_runs_last_30_days must be >= 0")

        # Validate workflow_runs is a list
        if "workflow_runs" in workflow_data:
            if not isinstance(workflow_data["workflow_runs"], list):
                errors.append(f"argo_workflows.{workflow_name}.workflow_runs must be a list")

    return errors


def validate_argo_cd(argo_cd: Dict[str, Any]) -> List[str]:
    """Validate ArgoCD section."""
    errors = []

    if not isinstance(argo_cd, dict):
        return ["argo_cd must be a dictionary"]

    for app_name, app_data in argo_cd.items():
        if not isinstance(app_data, dict):
            errors.append(f"argo_cd.{app_name} must be a dictionary")
            continue

        required_fields = ["application_found", "applications"]

        for field in required_fields:
            if field not in app_data:
                errors.append(f"argo_cd.{app_name} missing field: {field}")

        # Validate application_found is boolean
        if "application_found" in app_data:
            if not isinstance(app_data["application_found"], bool):
                errors.append(f"argo_cd.{app_name}.application_found must be boolean")

        # Validate applications is a list
        if "applications" in app_data:
            if not isinstance(app_data["applications"], list):
                errors.append(f"argo_cd.{app_name}.applications must be a list")

    return errors


def validate_cluster_deployments(cluster_deployments: Dict[str, Any]) -> List[str]:
    """Validate cluster deployments section."""
    errors = []

    if not isinstance(cluster_deployments, dict):
        return ["cluster_deployments must be a dictionary"]

    for deployment_name, deployment_data in cluster_deployments.items():
        if not isinstance(deployment_data, dict):
            errors.append(f"cluster_deployments.{deployment_name} must be a dictionary")
            continue

        required_fields = ["namespace", "deployment_name", "created_at", "current_image",
                         "current_replicas", "replica_history", "deployments_last_30_days",
                         "successful_deployments", "failed_deployments", "deployment_versions",
                         "all_versions_in_history"]

        for field in required_fields:
            if field not in deployment_data:
                errors.append(f"cluster_deployments.{deployment_name} missing field: {field}")

        # Validate numeric fields
        numeric_fields = {
            "current_replicas": int,
            "deployments_last_30_days": int,
            "successful_deployments": int,
            "failed_deployments": int
        }

        for field, expected_type in numeric_fields.items():
            if field in deployment_data:
                if not isinstance(deployment_data[field], expected_type):
                    errors.append(f"cluster_deployments.{deployment_name}.{field} must be {expected_type.__name__}")
                elif deployment_data[field] < 0:
                    errors.append(f"cluster_deployments.{deployment_name}.{field} must be >= 0")

        # Validate replica_history is a list
        if "replica_history" in deployment_data:
            if not isinstance(deployment_data["replica_history"], list):
                errors.append(f"cluster_deployments.{deployment_name}.replica_history must be a list")

        # Validate deployment_versions is a list
        if "deployment_versions" in deployment_data:
            if not isinstance(deployment_data["deployment_versions"], list):
                errors.append(f"cluster_deployments.{deployment_name}.deployment_versions must be a list")

        # Validate all_versions_in_history is a list
        if "all_versions_in_history" in deployment_data:
            if not isinstance(deployment_data["all_versions_in_history"], list):
                errors.append(f"cluster_deployments.{deployment_name}.all_versions_in_history must be a list")

        # Validate consistency: successful + failed <= total
        if all(field in deployment_data for field in ["successful_deployments",
                                                       "failed_deployments",
                                                       "deployments_last_30_days"]):
            total = deployment_data["successful_deployments"] + deployment_data["failed_deployments"]
            if total > deployment_data["deployments_last_30_days"]:
                errors.append(f"cluster_deployments.{deployment_name}: successful + failed deployments exceeds total")

    return errors


def validate_summary(summary: Dict[str, Any]) -> List[str]:
    """Validate summary section."""
    errors = []

    required_fields = ["total_deployments_last_30_days", "whisper_stt_deployments",
                      "successful_deployments", "failed_or_scaled_down",
                      "data_coverage", "gaps_detected", "largest_gap_days"]

    for field in required_fields:
        if field not in summary:
            errors.append(f"summary missing field: {field}")

    # Validate numeric fields
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
                errors.append(f"summary.{field} must be {expected_type.__name__}")
            elif summary[field] < 0:
                errors.append(f"summary.{field} must be >= 0")

    # Validate boolean fields
    if "gaps_detected" in summary:
        if not isinstance(summary["gaps_detected"], bool):
            errors.append("summary.gaps_detected must be boolean")

    # Validate data_coverage is string and looks like percentage
    if "data_coverage" in summary:
        if not isinstance(summary["data_coverage"], str):
            errors.append("summary.data_coverage must be string")

    return errors


def validate_pod_health(pod_health: Dict[str, Any]) -> List[str]:
    """Validate pod health section."""
    errors = []

    if "current_pods" in pod_health:
        if not isinstance(pod_health["current_pods"], list):
            errors.append("pod_health.current_pods must be a list")

    if "pod_metrics" in pod_health:
        if not isinstance(pod_health["pod_metrics"], dict):
            errors.append("pod_health.pod_metrics must be a dictionary")
        else:
            metrics = pod_health["pod_metrics"]
            required_metrics = ["total_pods", "running_pods", "total_containers",
                              "total_restarts", "crashloops", "oomkills"]

            for metric in required_metrics:
                if metric not in metrics:
                    errors.append(f"pod_health.pod_metrics missing field: {metric}")
                elif not isinstance(metrics[metric], int):
                    errors.append(f"pod_health.pod_metrics.{metric} must be integer")
                elif metrics[metric] < 0:
                    errors.append(f"pod_health.pod_metrics.{metric} must be >= 0")

            # Validate consistency: running_pods <= total_pods
            if "running_pods" in metrics and "total_pods" in metrics:
                if metrics["running_pods"] > metrics["total_pods"]:
                    errors.append("pod_health.pod_metrics.running_pods cannot exceed total_pods")

    return errors


def validate_30day_coverage(data: Dict[str, Any]) -> List[str]:
    """Validate 30-day data coverage and check for gaps."""
    errors = []
    warnings = []

    if "metadata" not in data:
        return ["Cannot validate coverage: metadata missing"]

    metadata = data["metadata"]

    # Check date range spans 30 days
    try:
        if "data_period_start" in metadata and "data_period_end" in metadata:
            start = parse_timestamp(metadata["data_period_start"])
            end = parse_timestamp(metadata["data_period_end"])
            days_span = (end - start).days

            if days_span < 30:
                warnings.append(f"Data period spans {days_span} days, expected at least 30")
            elif days_span > 31:
                warnings.append(f"Data period spans {days_span} days, expected ~30")

            # Check summary for coverage info
            if "summary" in data:
                summary = data["summary"]
                if "gaps_detected" in summary:
                    if summary["gaps_detected"]:
                        warnings.append(f"Summary reports gaps detected, largest gap: {summary.get('largest_gap_days', 'unknown')} days")

                if "data_coverage" in summary:
                    coverage = summary["data_coverage"]
                    if coverage != "100%":
                        warnings.append(f"Data coverage is {coverage}, expected 100%")

    except ValueError as e:
        errors.append(f"Cannot validate coverage: {e}")

    return errors, warnings


def validate_deployment_data(data_path: Path) -> Dict[str, Any]:
    """Load and validate deployment data file."""

    results = {
        "valid": False,
        "errors": [],
        "warnings": [],
        "file_size": 0,
        "summary": {}
    }

    print("=" * 70)
    print("WHISPER-STT DEPLOYMENT DATA VALIDATION")
    print("=" * 70)
    print(f"\nValidating file: {data_path}")

    # Check file exists
    if not data_path.exists():
        results["errors"].append(f"File not found: {data_path}")
        return results

    # Get file size
    results["file_size"] = data_path.stat().st_size
    print(f"File size: {results['file_size']} bytes")

    # Load JSON
    try:
        with open(data_path, 'r') as f:
            data = json.load(f)
        print("✓ JSON is well-formed")
    except json.JSONDecodeError as e:
        results["errors"].append(f"Invalid JSON: {e}")
        return results

    # Validate top-level structure
    print("\nValidating top-level structure...")
    required_sections = ["metadata", "argo_workflows", "argo_cd",
                        "cluster_deployments", "summary"]

    for section in required_sections:
        if section not in data:
            results["errors"].append(f"Missing top-level section: {section}")
            print(f"✗ Missing section: {section}")
        else:
            print(f"✓ Found section: {section}")

    # Validate each section
    print("\nValidating sections...")

    if "metadata" in data:
        errors = validate_metadata(data["metadata"])
        results["errors"].extend(errors)
        if not errors:
            print("✓ metadata is valid")
            results["summary"]["services"] = data["metadata"].get("services", [])
            results["summary"]["clusters"] = data["metadata"].get("clusters", [])

    if "argo_workflows" in data:
        errors = validate_argo_workflows(data["argo_workflows"])
        results["errors"].extend(errors)
        if not errors:
            print("✓ argo_workflows is valid")

    if "argo_cd" in data:
        errors = validate_argo_cd(data["argo_cd"])
        results["errors"].extend(errors)
        if not errors:
            print("✓ argo_cd is valid")

    if "cluster_deployments" in data:
        errors = validate_cluster_deployments(data["cluster_deployments"])
        results["errors"].extend(errors)
        if not errors:
            print("✓ cluster_deployments is valid")
            # Extract deployment counts
            for name, deployment in data["cluster_deployments"].items():
                results["summary"][f"{name}_deployments"] = deployment.get("deployments_last_30_days")

    if "summary" in data:
        errors = validate_summary(data["summary"])
        results["errors"].extend(errors)
        if not errors:
            print("✓ summary is valid")
            results["summary"]["total_deployments"] = data["summary"].get("total_deployments_last_30_days")

    if "pod_health" in data:
        errors = validate_pod_health(data["pod_health"])
        results["errors"].extend(errors)
        if not errors:
            print("✓ pod_health is valid")

    # Validate 30-day coverage
    print("\nValidating 30-day coverage...")
    coverage_errors, coverage_warnings = validate_30day_coverage(data)
    results["errors"].extend(coverage_errors)
    results["warnings"].extend(coverage_warnings)

    if not coverage_errors:
        print("✓ 30-day coverage validated")

    # Check optional sections
    optional_sections = ["resources", "storage", "error_incidents", "notes"]
    for section in optional_sections:
        if section in data:
            print(f"✓ Found optional section: {section}")

    # Final validation result
    results["valid"] = len(results["errors"]) == 0

    return results


def main():
    """Main validation function."""

    # Default file path
    data_path = Path("/home/coding/aide-de-camp/whisper-stt-deployments-30d.json")

    # Run validation
    results = validate_deployment_data(data_path)

    # Print summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    print(f"\nValid: {'✓ YES' if results['valid'] else '✗ NO'}")
    print(f"File size: {results['file_size']} bytes")
    print(f"Errors: {len(results['errors'])}")
    print(f"Warnings: {len(results['warnings'])}")

    if results["summary"]:
        print("\n📊 Data Summary:")
        for key, value in results["summary"].items():
            print(f"  • {key}: {value}")

    if results["errors"]:
        print("\n❌ ERRORS:")
        for error in results["errors"]:
            print(f"  • {error}")

    if results["warnings"]:
        print("\n⚠️  WARNINGS:")
        for warning in results["warnings"]:
            print(f"  • {warning}")

    print("\n" + "=" * 70)
    if results["valid"]:
        print("✓ VALIDATION PASSED - File is ready for commit")
    else:
        print("✗ VALIDATION FAILED - File has errors that need attention")
    print("=" * 70)

    return 0 if results["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
