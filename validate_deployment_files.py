#!/usr/bin/env python3
"""
Comprehensive validation for deployment data files.

Validates:
- JSON structure and well-formedness
- Required fields presence
- Data type consistency
- 30-day coverage completeness
- Schema compliance
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Validation result container."""
    file_path: str
    is_valid_json: bool = False
    has_required_fields: bool = False
    has_valid_types: bool = False
    has_complete_coverage: bool = False
    errors: List[str] = None
    warnings: List[str] = None
    coverage_days: int = 0
    total_deployments: int = 0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class DeploymentDataValidator:
    """Validator for deployment data files."""

    def __init__(self, target_period_start: str = "2026-07-07", target_period_end: str = "2026-08-06"):
        self.target_start = datetime.fromisoformat(target_period_start)
        self.target_end = datetime.fromisoformat(target_period_end)
        self.target_days = (self.target_end - self.target_start).days + 1

    def validate_file(self, file_path: str) -> ValidationResult:
        """Validate a deployment data file comprehensively."""
        result = ValidationResult(file_path=file_path)

        try:
            # 1. Check if file exists and is valid JSON
            with open(file_path, 'r') as f:
                data = json.load(f)
            result.is_valid_json = True
            print(f"✅ {file_path}: Valid JSON structure")

            # 2. Validate required fields based on file type
            field_validation = self._validate_required_fields(data, file_path)
            result.has_required_fields = field_validation["valid"]
            result.errors.extend(field_validation.get("errors", []))
            result.warnings.extend(field_validation.get("warnings", []))

            # 3. Validate data types
            type_validation = self._validate_data_types(data, file_path)
            result.has_valid_types = type_validation["valid"]
            result.errors.extend(type_validation.get("errors", []))

            # 4. Validate 30-day coverage
            coverage_validation = self._validate_coverage(data, file_path)
            result.has_complete_coverage = coverage_validation["complete"]
            result.coverage_days = coverage_validation["days"]
            result.total_deployments = coverage_validation["deployments"]
            result.warnings.extend(coverage_validation.get("warnings", []))

            if coverage_validation.get("gaps"):
                result.warnings.append(f"Coverage gaps detected: {coverage_validation['gaps']}")

        except FileNotFoundError:
            result.errors.append(f"File not found: {file_path}")
        except json.JSONDecodeError as e:
            result.errors.append(f"Invalid JSON: {e}")
        except Exception as e:
            result.errors.append(f"Validation error: {e}")

        return result

    def _validate_required_fields(self, data: Dict, file_path: str) -> Dict[str, Any]:
        """Validate required fields for specific file types."""
        result = {"valid": True, "errors": [], "warnings": []}

        if "pbx-web" in file_path:
            # pbx-web specific required fields
            required_fields = ["argo_workflows_query", "findings", "production_deployment_history"]
            for field in required_fields:
                if field not in data:
                    result["errors"].append(f"Missing required field: {field}")
                    result["valid"] = False

        elif "whisper-stt" in file_path:
            # whisper-stt specific required fields
            required_fields = ["query_metadata", "findings", "deployments"]
            for field in required_fields:
                if field not in data:
                    result["errors"].append(f"Missing required field: {field}")
                    result["valid"] = False

        return result

    def _validate_data_types(self, data: Dict, file_path: str) -> Dict[str, Any]:
        """Validate data types for key fields."""
        result = {"valid": True, "errors": []}

        # Check metadata timestamp types
        for metadata_key in ["argo_workflows_query", "query_metadata"]:
            if metadata_key in data:
                metadata = data[metadata_key]
                for ts_field in ["generated_at", "time_range_start", "time_range_end", "query_date"]:
                    if ts_field in metadata:
                        try:
                            if isinstance(metadata[ts_field], str):
                                # Validate ISO format
                                ts = metadata[ts_field]
                                if ts.endswith('Z'):
                                    ts = ts[:-1] + '+00:00'
                                datetime.fromisoformat(ts.replace('+00:00', ''))
                        except (ValueError, TypeError) as e:
                            result["errors"].append(f"Invalid timestamp format for {metadata_key}.{ts_field}: {e}")
                            result["valid"] = False

        # Check numeric types in findings
        if "findings" in data:
            findings = data["findings"]
            numeric_fields = ["workflows_found", "total_workflow_instances"]
            for field in numeric_fields:
                if field in findings and not isinstance(findings[field], (int, type(None))):
                    result["errors"].append(f"Field findings.{field} should be numeric or null")
                    result["valid"] = False

        return result

    def _validate_coverage(self, data: Dict, file_path: str) -> Dict[str, Any]:
        """Validate 30-day coverage completeness."""
        result = {
            "complete": False,
            "days": 0,
            "deployments": 0,
            "gaps": [],
            "warnings": []
        }

        deployments = []

        # Extract deployments from different data structures
        if "production_deployment_history" in data:
            history = data["production_deployment_history"]
            if "recent_deployments_in_window" in history:
                deployments.extend(history["recent_deployments_in_window"])

        if "deployments" in data and isinstance(data["deployments"], list):
            deployments.extend(data["deployments"])

        result["deployments"] = len(deployments)

        if not deployments:
            result["warnings"].append("No deployment records found - coverage cannot be calculated")
            return result

        # Parse timestamps and find coverage range
        timestamps = []
        for deployment in deployments:
            ts_field = "timestamp" if "timestamp" in deployment else "creationTimestamp"
            if ts_field in deployment:
                try:
                    ts = deployment[ts_field]
                    if ts.endswith('Z'):
                        ts = ts[:-1] + '+00:00'
                    timestamps.append(datetime.fromisoformat(ts.replace('+00:00', '')))
                except (ValueError, TypeError) as e:
                    result["warnings"].append(f"Invalid deployment timestamp: {e}")

        if not timestamps:
            result["warnings"].append("No valid timestamps found in deployment records")
            return result

        # Calculate coverage
        earliest = min(timestamps)
        latest = max(timestamps)
        coverage_days = (latest - earliest).days + 1
        result["days"] = coverage_days

        # Check if coverage matches target period
        coverage_complete = coverage_days >= self.target_days
        result["complete"] = coverage_complete

        if not coverage_complete:
            gap_days = self.target_days - coverage_days
            result["gaps"].append(f"{gap_days} day gap in deployment records")

        # Check if records fall within target period
        if earliest > self.target_start:
            result["gaps"].append(f"Records start { (earliest - self.target_start).days } days after target start")
        if latest < self.target_end:
            result["gaps"].append(f"Records end { (self.target_end - latest).days } days before target end")

        return result


def validate_deployment_files() -> Dict[str, ValidationResult]:
    """Validate all deployment data files."""
    validator = DeploymentDataValidator()

    files_to_validate = [
        "/home/coding/aide-de-camp/docs/research/deployment-data/pbx-web-deployments.json",
        "/home/coding/aide-de-camp/docs/research/deployment-data/whisper-stt-deployments.json",
        "/home/coding/aide-de-camp/docs/research/deployment-data/coverage-report.json"
    ]

    results = {}
    print("=" * 70)
    print("DEPLOYMENT DATA VALIDATION")
    print("=" * 70)
    print(f"\nTarget Period: {validator.target_start.date()} to {validator.target_end.date()} ({validator.target_days} days)")

    for file_path in files_to_validate:
        if Path(file_path).exists():
            print(f"\n{'='*70}")
            result = validator.validate_file(file_path)
            results[file_path] = result

            # Print results
            status = "✅ VALID" if (result.is_valid_json and result.has_required_fields and
                                   result.has_valid_types) else "❌ INVALID"
            print(f"{status}: {Path(file_path).name}")

            if result.is_valid_json:
                print(f"  • JSON Structure: ✓ Valid")
                print(f"  • Required Fields: {'✓' if result.has_required_fields else '✗'}")
                print(f"  • Data Types: {'✓' if result.has_valid_types else '✗'}")
                print(f"  • Coverage: {result.coverage_days}/{validator.target_days} days ({result.total_deployments} deployments)")
                print(f"  • Complete Coverage: {'✓' if result.has_complete_coverage else '✗'}")

            if result.errors:
                print(f"  • Errors ({len(result.errors)}):")
                for error in result.errors:
                    print(f"    - {error}")

            if result.warnings:
                print(f"  • Warnings ({len(result.warnings)}):")
                for warning in result.warnings:
                    print(f"    - {warning}")
        else:
            print(f"\n⚠️  File not found: {file_path}")

    return results


def main():
    """Main validation function."""
    results = validate_deployment_files()

    print(f"\n{'='*70}")
    print("VALIDATION SUMMARY")
    print(f"{'='*70}")

    valid_count = sum(1 for r in results.values()
                     if r.is_valid_json and r.has_required_fields and r.has_valid_types)
    total_count = len(results)

    print(f"\nFiles validated: {total_count}")
    print(f"Files passed: {valid_count}")
    print(f"Files failed: {total_count - valid_count}")

    # Document validated files for git commit
    print(f"\n📝 Files ready for commit:")
    for file_path, result in results.items():
        if result.is_valid_json and result.has_required_fields and result.has_valid_types:
            print(f"  • {file_path}")

    return 0 if valid_count == total_count else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())