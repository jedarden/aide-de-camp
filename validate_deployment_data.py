#!/usr/bin/env python3
"""
Deployment data validation script.

Validates both deployment JSON files and their structure:
- pbx-web-deployments.json: ArgoCD deployment records
- whisper-stt-deployments-30d.json: Comprehensive deployment event data

Checks for required fields:
- timestamp
- success/failure status (outcome)
- error_type (if failed)
- phase (if failed)
- error_message (if failed)
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple

def load_json_file(file_path: Path) -> Tuple[bool, Any, List[str]]:
    """Load and parse a JSON file.

    Returns:
        (success, data, errors)
    """
    errors = []

    if not file_path.exists():
        return False, None, [f"File not found: {file_path}"]

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return True, data, errors
    except json.JSONDecodeError as e:
        return False, None, [f"Malformed JSON: {e}"]
    except Exception as e:
        return False, None, [f"Error reading file: {e}"]


def validate_pbx_web_structure(data: Any) -> Tuple[bool, List[str], List[str], Dict]:
    """Validate pbx-web-deployments.json structure.

    Expected structure:
    {
      "query_date": "...",
      "deployments": [
        {
          "commit_hash": "...",
          "timestamp": "...",
          "author": "...",
          "message": "...",
          "image_tag": "...",
          "deployment_type": "..."
        }
      ]
    }
    """
    errors = []
    warnings = []
    stats = {
        "total_records": 0,
        "has_timestamp": 0,
        "has_commit_hash": 0,
        "deployment_types": set(),
    }

    if not isinstance(data, dict):
        return False, ["Root element is not a dictionary"], [], stats

    # Check for deployments array
    if "deployments" not in data:
        return False, ["Missing 'deployments' array"], [], stats

    if not isinstance(data["deployments"], list):
        return False, ["'deployments' is not a list"], [], stats

    deployments = data["deployments"]
    stats["total_records"] = len(deployments)

    if len(deployments) == 0:
        warnings.append("No deployment records found")

    # Validate each deployment record
    for i, deployment in enumerate(deployments):
        if not isinstance(deployment, dict):
            errors.append(f"Record {i}: Not a dictionary")
            continue

        # Check timestamp
        if "timestamp" in deployment:
            stats["has_timestamp"] += 1
        else:
            errors.append(f"Record {i}: Missing required field 'timestamp'")

        # Check commit_hash
        if "commit_hash" in deployment:
            stats["has_commit_hash"] += 1
        else:
            errors.append(f"Record {i}: Missing required field 'commit_hash'")

        # Track deployment types
        if "deployment_type" in deployment:
            stats["deployment_types"].add(deployment["deployment_type"])

    # Convert set to list for JSON serialization
    stats["deployment_types"] = list(stats["deployment_types"])

    return len(errors) == 0, errors, warnings, stats


def validate_whisper_stt_structure(data: Any) -> Tuple[bool, List[str], List[str], Dict]:
    """Validate whisper-stt-deployments-30d.json structure.

    Expected structure:
    {
      "metadata": { ... },
      "current_status": { ... },
      "deployment_events_last_30_days": [
        {
          "date": "...",
          "timestamp": "...",
          "event_type": "...",
          "outcome": "...",  // success/failure
          "revision": ...,
          // error details if outcome == failure
        }
      ],
      "deployment_metrics": { ... }
    }
    """
    errors = []
    warnings = []
    stats = {
        "total_records": 0,
        "has_timestamp": 0,
        "has_event_type": 0,
        "has_outcome": 0,
        "successful_deployments": 0,
        "failed_deployments": 0,
        "outcome_types": set(),
    }

    if not isinstance(data, dict):
        return False, ["Root element is not a dictionary"], [], stats

    # Check for deployment_events_last_30_days array
    if "deployment_events_last_30_days" not in data:
        return False, ["Missing 'deployment_events_last_30_days' array"], [], stats

    if not isinstance(data["deployment_events_last_30_days"], list):
        return False, ["'deployment_events_last_30_days' is not a list"], [], stats

    events = data["deployment_events_last_30_days"]
    stats["total_records"] = len(events)

    if len(events) == 0:
        warnings.append("No deployment events found")

    # Validate each event record
    for i, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"Record {i}: Not a dictionary")
            continue

        # Check timestamp
        if "timestamp" in event:
            stats["has_timestamp"] += 1
        else:
            errors.append(f"Record {i}: Missing required field 'timestamp'")

        # Check event_type
        if "event_type" in event:
            stats["has_event_type"] += 1
        else:
            errors.append(f"Record {i}: Missing required field 'event_type'")

        # Check outcome (success/failure)
        if "outcome" in event:
            stats["has_outcome"] += 1
            outcome = event["outcome"]
            stats["outcome_types"].add(outcome)

            if outcome == "success":
                stats["successful_deployments"] += 1
            elif outcome == "failure":
                stats["failed_deployments"] += 1

                # For failures, check error detail fields
                if "error_type" not in event:
                    warnings.append(f"Record {i}: Failed deployment missing 'error_type'")
                if "phase" not in event:
                    warnings.append(f"Record {i}: Failed deployment missing 'phase'")
                if "error_message" not in event:
                    warnings.append(f"Record {i}: Failed deployment missing 'error_message'")
            else:
                warnings.append(f"Record {i}: Unknown outcome type '{outcome}'")
        else:
            errors.append(f"Record {i}: Missing required field 'outcome'")

    # Convert set to list for JSON serialization
    stats["outcome_types"] = list(stats["outcome_types"])

    return len(errors) == 0, errors, warnings, stats


def validate_file(file_path: Path, file_type: str) -> Dict:
    """Validate a single deployment data file."""

    # Load the file
    success, data, errors = load_json_file(file_path)

    if not success:
        return {
            "file": str(file_path),
            "exists": file_path.exists(),
            "valid_json": False,
            "structure_valid": False,
            "record_count": 0,
            "errors": errors,
            "warnings": [],
            "stats": {}
        }

    # Validate structure based on file type
    if file_type == "pbx-web":
        valid, structure_errors, warnings, stats = validate_pbx_web_structure(data)
    elif file_type == "whisper-stt":
        valid, structure_errors, warnings, stats = validate_whisper_stt_structure(data)
    else:
        return {
            "file": str(file_path),
            "exists": True,
            "valid_json": True,
            "structure_valid": False,
            "record_count": 0,
            "errors": ["Unknown file type"],
            "warnings": [],
            "stats": {}
        }

    return {
        "file": str(file_path),
        "exists": True,
        "valid_json": True,
        "structure_valid": valid,
        "record_count": stats.get("total_records", 0),
        "errors": structure_errors,
        "warnings": warnings,
        "stats": stats
    }


def main():
    """Main validation function."""

    print("=" * 70)
    print("Deployment Data Validation")
    print("=" * 70)
    print()

    # Define files to validate
    workspace = Path("/home/coding/aide-de-camp")
    files_to_validate = [
        (workspace / "pbx-web-deployments.json", "pbx-web"),
        (workspace / "whisper-stt-deployments-30d.json", "whisper-stt"),
    ]

    results = []
    total_errors = 0
    total_warnings = 0

    for file_path, file_type in files_to_validate:
        print(f"Validating: {file_path.name}")
        print("-" * 70)

        result = validate_file(file_path, file_type)
        results.append(result)

        total_errors += len(result["errors"])
        total_warnings += len(result["warnings"])

        # Print results
        if not result["exists"]:
            print(f"  ❌ File not found")
        elif not result["valid_json"]:
            print(f"  ❌ Invalid JSON: {result['errors'][0]}")
        elif not result["structure_valid"]:
            print(f"  ❌ Structure invalid: {len(result['errors'])} errors, {len(result['warnings'])} warnings")
        else:
            print(f"  ✅ Valid: {result['record_count']} records")

        print(f"  Errors: {len(result['errors'])}")
        print(f"  Warnings: {len(result['warnings'])}")

        if result.get("stats"):
            stats = result["stats"]
            print(f"  Statistics:")
            print(f"    - Total records: {stats.get('total_records', 0)}")
            print(f"    - Records with timestamp: {stats.get('has_timestamp', 0)}")

            if file_type == "pbx-web":
                print(f"    - Records with commit_hash: {stats.get('has_commit_hash', 0)}")
                print(f"    - Deployment types: {', '.join(stats.get('deployment_types', []))}")
            elif file_type == "whisper-stt":
                print(f"    - Successful deployments: {stats.get('successful_deployments', 0)}")
                print(f"    - Failed deployments: {stats.get('failed_deployments', 0)}")
                print(f"    - Outcome types: {', '.join(stats.get('outcome_types', []))}")

        print()

    # Summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Total files validated: {len(results)}")
    print(f"Valid files: {sum(1 for r in results if r['valid_json'] and r['structure_valid'])}")
    print(f"Total errors: {total_errors}")
    print(f"Total warnings: {total_warnings}")
    print()

    # Save results to file
    output_file = workspace / "data" / "deployment_validation_results.json"
    validation_report = {
        "validation_date": datetime.now().isoformat(),
        "results": results,
        "summary": {
            "total_files": len(results),
            "valid_files": sum(1 for r in results if r['valid_json'] and r['structure_valid']),
            "total_errors": total_errors,
            "total_warnings": total_warnings
        }
    }

    with open(output_file, 'w') as f:
        json.dump(validation_report, f, indent=2)

    print(f"Validation results saved to: {output_file}")

    # Exit with error code if validation failed
    if total_errors > 0:
        print("\n❌ Validation failed with errors")
        sys.exit(1)
    elif total_warnings > 0:
        print("\n⚠️  Validation completed with warnings")
        sys.exit(0)
    else:
        print("\n✅ All files validated successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()