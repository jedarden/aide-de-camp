#!/usr/bin/env python3
"""
Load and validate deployment data from child bead 1.

This script loads the intermediate deployment metrics file and validates:
- Data structure completeness
- Required fields presence
- Timestamp parseability
- Status field validity
- Data consistency
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Required fields for validation
REQUIRED_TOP_LEVEL_FIELDS = [
    "generated_at", "analysis_period", "cluster", "services", "service_metrics"
]

REQUIRED_SERVICE_FIELDS = [
    "service_name", "analysis_period_days", "deployment_metrics",
    "timing_metrics", "pod_health_metrics"
]

REQUIRED_DEPLOYMENT_METRICS = [
    "total_deployments", "successful_rollouts", "failed_rollouts",
    "success_rate_percent", "failure_rate_percent"
]

REQUIRED_TIMING_METRICS = [
    "mean_time_between_deployments_hours", "median_time_between_deployments_hours",
    "deployment_timestamps", "sample_size"
]

REQUIRED_POD_HEALTH_METRICS = [
    "total_pods", "running_pods", "total_restarts", "crashloops", "oomkills"
]

def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO 8601 timestamp string."""
    try:
        # Handle various ISO formats
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        return datetime.fromisoformat(timestamp_str.replace('+00:00', ''))
    except Exception as e:
        raise ValueError(f"Failed to parse timestamp: {timestamp_str}") from e

def validate_deployment_data(data_path: Path) -> Dict[str, Any]:
    """Load and validate deployment metrics data."""

    print(f"Loading deployment data from: {data_path}")
    validation_results = {
        "loaded": False,
        "errors": [],
        "warnings": [],
        "summary": {}
    }

    try:
        # Load the data
        with open(data_path, 'r') as f:
            data = json.load(f)
        validation_results["loaded"] = True
        print("✓ Data loaded successfully")

        # Validate top-level structure
        print("\nValidating top-level structure...")
        for field in REQUIRED_TOP_LEVEL_FIELDS:
            if field not in data:
                error = f"Missing required top-level field: {field}"
                validation_results["errors"].append(error)
                print(f"✗ {error}")
            else:
                print(f"✓ Found required field: {field}")

        # Validate generated_at timestamp
        if "generated_at" in data:
            try:
                generated_at = parse_timestamp(data["generated_at"])
                print(f"✓ Generated timestamp valid: {generated_at}")
                validation_results["summary"]["generated_at"] = generated_at.isoformat()
            except Exception as e:
                error = f"Invalid generated_at timestamp: {e}"
                validation_results["errors"].append(error)
                print(f"✗ {error}")

        # Validate services list
        if "services" in data:
            services = data["services"]
            print(f"\n✓ Services defined: {services}")
            validation_results["summary"]["services"] = services

            if not isinstance(services, list) or len(services) == 0:
                error = "Services must be a non-empty list"
                validation_results["errors"].append(error)
                print(f"✗ {error}")

        # Validate each service's metrics
        if "service_metrics" in data:
            print("\nValidating service metrics...")
            for service_key, service_data in data["service_metrics"].items():
                print(f"\nValidating service: {service_key}")

                # Check required service fields
                for field in REQUIRED_SERVICE_FIELDS:
                    if field not in service_data:
                        error = f"Service {service_key}: Missing required field: {field}"
                        validation_results["errors"].append(error)
                        print(f"✗ {error}")
                    else:
                        print(f"✓ {service_key}: Found {field}")

                # Validate deployment_metrics
                if "deployment_metrics" in service_data:
                    deployment_metrics = service_data["deployment_metrics"]
                    for field in REQUIRED_DEPLOYMENT_METRICS:
                        if field not in deployment_metrics:
                            error = f"Service {service_key}: Missing deployment_metric: {field}"
                            validation_results["errors"].append(error)
                            print(f"✗ {error}")
                        else:
                            print(f"✓ {service_key}: Found {field} = {deployment_metrics[field]}")

                    # Validate numeric fields
                    numeric_fields = ["total_deployments", "successful_rollouts",
                                    "failed_rollouts", "success_rate_percent",
                                    "failure_rate_percent"]
                    for field in numeric_fields:
                        if field in deployment_metrics:
                            if not isinstance(deployment_metrics[field], (int, float)):
                                error = f"Service {service_key}: {field} should be numeric"
                                validation_results["errors"].append(error)
                                print(f"✗ {error}")

                # Validate timing_metrics
                if "timing_metrics" in service_data:
                    timing_metrics = service_data["timing_metrics"]

                    # Check required timing fields
                    for field in REQUIRED_TIMING_METRICS:
                        if field not in timing_metrics:
                            error = f"Service {service_key}: Missing timing_metric: {field}"
                            validation_results["errors"].append(error)
                            print(f"✗ {error}")

                    # Validate timestamps array
                    if "deployment_timestamps" in timing_metrics:
                        timestamps = timing_metrics["deployment_timestamps"]
                        if not isinstance(timestamps, list):
                            error = f"Service {service_key}: deployment_timestamps must be a list"
                            validation_results["errors"].append(error)
                            print(f"✗ {error}")
                        else:
                            print(f"✓ {service_key}: Found {len(timestamps)} deployment timestamps")
                            valid_timestamps = []
                            for i, ts in enumerate(timestamps):
                                try:
                                    parsed = parse_timestamp(ts)
                                    valid_timestamps.append(parsed.isoformat())
                                except Exception as e:
                                    error = f"Service {service_key}: Invalid timestamp at index {i}: {ts}"
                                    validation_results["errors"].append(error)
                                    print(f"✗ {error}")

                            validation_results["summary"][f"{service_key}_valid_timestamps"] = len(valid_timestamps)
                            validation_results["summary"][f"{service_key}_total_timestamps"] = len(timestamps)

                # Validate pod_health_metrics
                if "pod_health_metrics" in service_data:
                    pod_metrics = service_data["pod_health_metrics"]

                    for field in REQUIRED_POD_HEALTH_METRICS:
                        if field not in pod_metrics:
                            error = f"Service {service_key}: Missing pod_health_metric: {field}"
                            validation_results["errors"].append(error)
                            print(f"✗ {error}")
                        else:
                            value = pod_metrics[field]
                            if not isinstance(value, (int, float)):
                                error = f"Service {service_key}: {field} should be numeric"
                                validation_results["errors"].append(error)
                                print(f"✗ {error}")
                            else:
                                print(f"✓ {service_key}: {field} = {value}")

                    # Validate consistency: running_pods <= total_pods
                    if "running_pods" in pod_metrics and "total_pods" in pod_metrics:
                        if pod_metrics["running_pods"] > pod_metrics["total_pods"]:
                            warning = f"Service {service_key}: running_pods ({pod_metrics['running_pods']}) > total_pods ({pod_metrics['total_pods']})"
                            validation_results["warnings"].append(warning)
                            print(f"⚠ {warning}")

        # Validate comparison data if present
        if "comparison" in data:
            print("\nValidating comparison metrics...")
            comparison = data["comparison"]

            comparison_fields = [
                "total_deployments_both_services", "pbx_web_deployment_percentage",
                "whisper_stt_deployment_percentage", "combined_success_rate_percent",
                "joint_deployment_stability"
            ]

            for field in comparison_fields:
                if field not in comparison:
                    warning = f"Missing comparison field: {field}"
                    validation_results["warnings"].append(warning)
                    print(f"⚠ {warning}")
                else:
                    print(f"✓ Found comparison field: {field}")

    except FileNotFoundError:
        error = f"Data file not found: {data_path}"
        validation_results["errors"].append(error)
        print(f"✗ {error}")
    except json.JSONDecodeError as e:
        error = f"Invalid JSON in data file: {e}"
        validation_results["errors"].append(error)
        print(f"✗ {error}")
    except Exception as e:
        error = f"Unexpected error during validation: {e}"
        validation_results["errors"].append(error)
        print(f"✗ {error}")

    return validation_results

def main():
    """Main validation function."""

    # Path to intermediate data file
    data_path = Path("/home/coding/aide-de-camp/docs/research/deployment-metrics-intermediate.json")

    print("=" * 70)
    print("DEPLOYMENT DATA VALIDATION")
    print("=" * 70)

    # Run validation
    results = validate_deployment_data(data_path)

    # Print summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    print(f"\nData Loaded: {'✓ YES' if results['loaded'] else '✗ NO'}")
    print(f"Errors: {len(results['errors'])}")
    print(f"Warnings: {len(results['warnings'])}")

    if results["errors"]:
        print("\n❌ ERRORS:")
        for error in results["errors"]:
            print(f"  • {error}")

    if results["warnings"]:
        print("\n⚠️  WARNINGS:")
        for warning in results["warnings"]:
            print(f"  • {warning}")

    print("\n📊 SUMMARY:")
    for key, value in results["summary"].items():
        print(f"  • {key}: {value}")

    # Overall validation result
    print("\n" + "=" * 70)
    if results["loaded"] and len(results["errors"]) == 0:
        print("✓ VALIDATION PASSED - Data is ready for processing")
    else:
        print("✗ VALIDATION FAILED - Data has errors that need attention")
    print("=" * 70)

    # Return validation results
    return results

if __name__ == "__main__":
    main()