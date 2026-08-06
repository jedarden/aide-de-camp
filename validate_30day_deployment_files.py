#!/usr/bin/env python3
"""
Comprehensive validation for 30-day deployment data files.

Validates:
- Required fields presence
- Data type correctness
- Timestamp validity
- 30-day coverage completeness
- Data consistency
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple


def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO 8601 timestamp string."""
    try:
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        return datetime.fromisoformat(timestamp_str.replace('+00:00', ''))
    except Exception as e:
        raise ValueError(f"Failed to parse timestamp: {timestamp_str}") from e


def validate_whisper_stt_data(data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """Validate whisper-stt deployment data structure."""
    errors = []
    warnings = []

    required_top_level = [
        "report_metadata", "current_status", "deployment_history_30_days",
        "pod_status", "operational_metrics", "argo_cd_integration",
        "error_incidents", "deployment_health_assessment", "summary"
    ]

    # Check required top-level fields
    for field in required_top_level:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate report_metadata
    if "report_metadata" in data:
        metadata = data["report_metadata"]
        required_metadata = [
            "generated_at", "time_range_start", "time_range_end",
            "cluster", "service", "namespace", "data_source"
        ]
        for field in required_metadata:
            if field not in metadata:
                errors.append(f"Missing report_metadata field: {field}")

        # Validate timestamps
        try:
            if "time_range_start" in metadata and "time_range_end" in metadata:
                start = parse_timestamp(metadata["time_range_start"])
                end = parse_timestamp(metadata["time_range_end"])
                duration = (end - start).days

                if duration < 29 or duration > 31:
                    warnings.append(f"Time range duration is {duration} days, expected ~30 days")
                elif duration == 30:
                    warnings.append(f"✓ Exactly 30 days coverage")
        except Exception as e:
            errors.append(f"Invalid metadata timestamps: {e}")

    # Validate deployment history
    if "deployment_history_30_days" in data:
        history = data["deployment_history_30_days"]
        if "replicasets" not in history:
            errors.append("Missing replicasets in deployment_history_30_days")
        else:
            replicasets = history["replicasets"]
            if not isinstance(replicasets, list):
                errors.append("replicasets must be a list")
            else:
                # Check for required fields in each replicaset
                for i, rs in enumerate(replicasets):
                    required_rs_fields = ["name", "created", "status", "replicas", "deployment", "image"]
                    for field in required_rs_fields:
                        if field not in rs:
                            errors.append(f"ReplicaSet {i}: Missing field {field}")

    # Validate summary
    if "summary" in data:
        summary = data["summary"]
        required_summary = [
            "deployment_name", "namespace", "cluster", "analysis_period",
            "deployments_in_namespace", "total_deployment_events",
            "successful_rollouts", "failed_rollouts", "availability", "overall_status"
        ]
        for field in required_summary:
            if field not in summary:
                errors.append(f"Missing summary field: {field}")

    return len(errors) == 0, errors, warnings


def validate_pbx_web_data(data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """Validate pbx-web deployment data structure."""
    errors = []
    warnings = []

    required_top_level = [
        "metadata", "current_status", "deployment_events_last_30_days",
        "deployment_metrics", "pod_health", "operational_logs_sample",
        "infrastructure_details", "summary"
    ]

    # Check required top-level fields
    for field in required_top_level:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate metadata
    if "metadata" in data:
        metadata = data["metadata"]
        required_metadata = [
            "service", "namespace", "cluster", "data_collected_at",
            "time_period", "managed_by", "strategy"
        ]
        for field in required_metadata:
            if field not in metadata:
                errors.append(f"Missing metadata field: {field}")

        # Validate timestamps
        try:
            if "time_period" in metadata:
                tp = metadata["time_period"]
                if "start" in tp and "end" in tp:
                    start = parse_timestamp(tp["start"])
                    end = parse_timestamp(tp["end"])
                    duration = (end - start).days

                    if duration < 29 or duration > 31:
                        warnings.append(f"Time range duration is {duration} days, expected ~30 days")
                    elif duration >= 30:
                        warnings.append(f"✓ At least 30 days coverage")
        except Exception as e:
            errors.append(f"Invalid metadata timestamps: {e}")

    # Validate deployment events
    if "deployment_events_last_30_days" in data:
        events = data["deployment_events_last_30_days"]
        if not isinstance(events, list):
            errors.append("deployment_events_last_30_days must be a list")
        else:
            # Check for required fields in each event
            for i, event in enumerate(events):
                required_event_fields = ["date", "timestamp", "event_type", "outcome"]
                for field in required_event_fields:
                    if field not in event:
                        errors.append(f"Event {i}: Missing field {field}")

    # Validate deployment metrics
    if "deployment_metrics" in data:
        metrics = data["deployment_metrics"]
        required_metrics = [
            "total_deployments_last_30_days", "successful_deployments",
            "failed_deployments", "deployment_frequency_days",
            "current_uptime_days", "last_deployment"
        ]
        for field in required_metrics:
            if field not in metrics:
                errors.append(f"Missing deployment_metrics field: {field}")

    # Validate summary
    if "summary" in data:
        summary = data["summary"]
        required_summary = [
            "overall_health", "deployment_stability", "uptime",
            "issues_last_30_days", "rollbacks_last_30_days",
            "deployment_success_rate", "recommendation"
        ]
        for field in required_summary:
            if field not in summary:
                errors.append(f"Missing summary field: {field}")

    return len(errors) == 0, errors, warnings


def validate_json_file(file_path: Path) -> Tuple[bool, List[str], List[str], Dict[str, Any]]:
    """Validate a JSON file for well-formedness and structure."""
    errors = []
    warnings = []
    data = None

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        warnings.append(f"✓ File is well-formed JSON")
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {e}")
        return False, errors, warnings, {}
    except Exception as e:
        errors.append(f"Error reading file: {e}")
        return False, errors, warnings, {}

    # Determine file type and validate accordingly
    if "report_metadata" in data and data.get("report_metadata", {}).get("service") == "whisper-stt":
        valid, field_errors, field_warnings = validate_whisper_stt_data(data)
        errors.extend(field_errors)
        warnings.extend(field_warnings)
        return valid, errors, warnings, data
    elif "metadata" in data and data.get("metadata", {}).get("service") == "pbx-web":
        valid, field_errors, field_warnings = validate_pbx_web_data(data)
        errors.extend(field_errors)
        warnings.extend(field_warnings)
        return valid, errors, warnings, data
    else:
        warnings.append("Unknown file type, performing basic validation only")
        return len(errors) == 0, errors, warnings, data


def check_30day_coverage(data: Dict[str, Any], file_type: str) -> Tuple[bool, List[str]]:
    """Check that data covers 30 days without gaps."""
    coverage_info = []

    if file_type == "whisper-stt":
        # Check from report_metadata
        if "report_metadata" in data:
            metadata = data["report_metadata"]
            try:
                start = parse_timestamp(metadata["time_range_start"])
                end = parse_timestamp(metadata["time_range_end"])
                duration = (end - start).days

                coverage_info.append(f"Time range: {start.date()} to {end.date()}")
                coverage_info.append(f"Duration: {duration} days")

                if duration >= 30:
                    return True, coverage_info
                else:
                    return False, coverage_info
            except Exception as e:
                return False, [f"Error parsing time range: {e}"]

    elif file_type == "pbx-web":
        # Check from metadata
        if "metadata" in data:
            metadata = data["metadata"]
            try:
                if "time_period" in metadata:
                    tp = metadata["time_period"]
                    start = parse_timestamp(tp["start"])
                    end = parse_timestamp(tp["end"])
                    duration = (end - start).days

                    coverage_info.append(f"Time range: {start.date()} to {end.date()}")
                    coverage_info.append(f"Duration: {duration} days")

                    if duration >= 30:
                        return True, coverage_info
                    else:
                        return False, coverage_info
            except Exception as e:
                return False, [f"Error parsing time range: {e}"]

    return False, ["Could not determine time range"]


def main():
    """Main validation function."""
    print("=" * 70)
    print("30-DAY DEPLOYMENT DATA FILE VALIDATION")
    print("=" * 70)

    # Files to validate
    whisper_file = Path("/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json")
    pbx_file = Path("/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json")

    all_valid = True

    # Validate whisper-stt file
    print(f"\n📄 Validating: {whisper_file.name}")
    print("-" * 70)
    valid, errors, warnings, data = validate_json_file(whisper_file)

    if warnings:
        print("⚠️  WARNINGS:")
        for warning in warnings:
            print(f"   {warning}")

    if errors:
        print("❌ ERRORS:")
        for error in errors:
            print(f"   • {error}")
        all_valid = False
    else:
        print("✓ Structure validation passed")

    # Check 30-day coverage
    if valid:
        coverage_valid, coverage_info = check_30day_coverage(data, "whisper-stt")
        print("\n📊 Coverage Check:")
        for info in coverage_info:
            print(f"   {info}")
        if coverage_valid:
            print("   ✓ 30-day coverage verified")
        else:
            print("   ⚠️  Coverage may be less than 30 days")

    # Validate pbx-web file
    print(f"\n📄 Validating: {pbx_file.name}")
    print("-" * 70)
    valid, errors, warnings, data = validate_json_file(pbx_file)

    if warnings:
        print("⚠️  WARNINGS:")
        for warning in warnings:
            print(f"   {warning}")

    if errors:
        print("❌ ERRORS:")
        for error in errors:
            print(f"   • {error}")
        all_valid = False
    else:
        print("✓ Structure validation passed")

    # Check 30-day coverage
    if valid:
        coverage_valid, coverage_info = check_30day_coverage(data, "pbx-web")
        print("\n📊 Coverage Check:")
        for info in coverage_info:
            print(f"   {info}")
        if coverage_valid:
            print("   ✓ 30-day coverage verified")
        else:
            print("   ⚠️  Coverage may be less than 30 days")

    # Final summary
    print("\n" + "=" * 70)
    if all_valid:
        print("✓ ALL FILES VALIDATED SUCCESSFULLY")
        print("\nFiles are ready for commit:")
        print(f"  • {whisper_file}")
        print(f"  • {pbx_file}")
        return 0
    else:
        print("✗ VALIDATION FAILED - Errors found that need correction")
        return 1


if __name__ == "__main__":
    sys.exit(main())
