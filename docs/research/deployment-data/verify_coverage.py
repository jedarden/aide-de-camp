#!/usr/bin/env python3
"""
Verify deployment data completeness and coverage for 30-day analysis window.
Analyzes pbx-web-deployments.json and whisper-stt-deployments.json.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict


def load_json(filepath: Path) -> Dict[str, Any]:
    """Load JSON file safely."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"error": f"File not found: {filepath}"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp."""
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'
    return datetime.fromisoformat(ts)


def analyze_timestamp_range(data: Dict[str, Any], service_name: str) -> Dict[str, Any]:
    """Analyze timestamp coverage in deployment data."""
    analysis = {
        "service": service_name,
        "target_start": "2026-07-07T00:00:00Z",
        "target_end": "2026-08-06T23:59:59Z",
        "earliest_record": None,
        "latest_record": None,
        "coverage_days": 0,
        "gaps_detected": False
    }

    # Check for production deployment history (pbx-web specific)
    if "production_deployment_history" in data:
        history = data["production_deployment_history"]
        if "recent_deployments_in_window" in history:
            deployments = history["recent_deployments_in_window"]
            if deployments:
                timestamps = [d["timestamp"] for d in deployments]
                analysis["earliest_record"] = min(timestamps)
                analysis["latest_record"] = max(timestamps)

                # Calculate coverage
                earliest = parse_timestamp(analysis["earliest_record"])
                latest = parse_timestamp(analysis["latest_record"])
                analysis["coverage_days"] = (latest - earliest).days + 1

    # Check for workflow instances in deployments array
    if "deployments" in data and isinstance(data["deployments"], list):
        if data["deployments"]:
            timestamps = []
            for deployment in data["deployments"]:
                if "creationTimestamp" in deployment:
                    timestamps.append(deployment["creationTimestamp"])

            if timestamps:
                analysis["earliest_record"] = min(timestamps)
                analysis["latest_record"] = max(timestamps)
                earliest = parse_timestamp(analysis["earliest_record"])
                latest = parse_timestamp(analysis["latest_record"])
                analysis["coverage_days"] = (latest - earliest).days + 1

    return analysis


def check_required_fields(data: Dict[str, Any], service_name: str) -> Dict[str, Any]:
    """Check completeness of required fields."""
    completeness = {
        "service": service_name,
        "metadata_complete": False,
        "findings_complete": False,
        "extracted_data_complete": False,
        "missing_fields": []
    }

    # Check metadata fields
    required_metadata = ["query_metadata", "argo_workflows_query"]
    for field in required_metadata:
        if field in data:
            completeness["metadata_complete"] = True
            break
    else:
        completeness["missing_fields"].append("metadata (query_metadata or argo_workflows_query)")

    # Check findings
    if "findings" in data:
        findings = data["findings"]
        required_findings = ["workflows_found", "total_workflow_instances"]
        if any(k in findings for k in required_findings):
            completeness["findings_complete"] = True
    else:
        completeness["missing_fields"].append("findings")

    # Check extracted data
    if "extracted_data" in data or "deployments" in data:
        completeness["extracted_data_complete"] = True
    else:
        completeness["missing_fields"].append("extracted_data/deployments")

    return completeness


def calculate_summary_stats(data: Dict[str, Any], service_name: str) -> Dict[str, Any]:
    """Calculate deployment summary statistics."""
    stats = {
        "service": service_name,
        "total_deployments": 0,
        "successful_deployments": 0,
        "failed_deployments": 0,
        "error_deployments": 0,
        "data_source": "unknown"
    }

    # Check data source
    if "argo_workflows_query" in data:
        stats["data_source"] = "argo_workflows_ci"
    elif "query_metadata" in data:
        stats["data_source"] = "argo_workflows_ci"

    # Count deployments from extracted_data or deployments array
    deployments = []
    if "extracted_data" in data and isinstance(data["extracted_data"], list):
        deployments = data["extracted_data"]
    elif "deployments" in data and isinstance(data["deployments"], list):
        deployments = data["deployments"]

    stats["total_deployments"] = len(deployments)

    # Count by phase
    for deployment in deployments:
        phase = deployment.get("phase", "Unknown")
        if phase == "Succeeded":
            stats["successful_deployments"] += 1
        elif phase == "Failed":
            stats["failed_deployments"] += 1
        elif phase == "Error":
            stats["error_deployments"] += 1

    # Add production deployment stats if available
    if "production_deployment_history" in data:
        history = data["production_deployment_history"]
        if "recent_deployments_in_window" in history:
            prod_deployments = history["recent_deployments_in_window"]
            stats["production_deployments_in_window"] = len(prod_deployments)
            stats["data_source"] += " + production_cluster"

    # Add findings context
    if "findings" in data:
        stats["workflows_found_in_ci"] = data["findings"].get("workflows_found",
                                                          data["findings"].get("total_workflow_instances", 0))

    return stats


def generate_coverage_report() -> Dict[str, Any]:
    """Generate comprehensive coverage report."""
    base_dir = Path("/home/coding/aide-de-camp/docs/research/deployment-data")

    services = {
        "pbx-web": base_dir / "pbx-web-deployments.json",
        "whisper-stt": base_dir / "whisper-stt-deployments.json"
    }

    report = {
        "generated_at": datetime.now().isoformat(),
        "target_period": {
            "start": "2026-07-07",
            "end": "2026-08-06",
            "total_days": 30
        },
        "services": {}
    }

    for service_name, filepath in services.items():
        print(f"\n{'='*60}")
        print(f"Analyzing {service_name}")
        print(f"{'='*60}")

        data = load_json(filepath)

        if "error" in data:
            print(f"❌ Error: {data['error']}")
            report["services"][service_name] = {"error": data["error"]}
            continue

        # Timestamp analysis
        timestamp_analysis = analyze_timestamp_range(data, service_name)
        print(f"\n📅 Timestamp Coverage:")
        print(f"   Target range: 2026-07-07 to 2026-08-06 (30 days)")
        if timestamp_analysis["earliest_record"]:
            print(f"   Earliest record: {timestamp_analysis['earliest_record']}")
            print(f"   Latest record: {timestamp_analysis['latest_record']}")
            print(f"   Coverage days: {timestamp_analysis['coverage_days']}")
        else:
            print(f"   ⚠️  No deployment records found in CI")

        # Field completeness
        completeness = check_required_fields(data, service_name)
        print(f"\n✅ Field Completeness:")
        print(f"   Metadata complete: {completeness['metadata_complete']}")
        print(f"   Findings complete: {completeness['findings_complete']}")
        print(f"   Data array complete: {completeness['extracted_data_complete']}")
        if completeness["missing_fields"]:
            print(f"   ⚠️  Missing: {', '.join(completeness['missing_fields'])}")

        # Summary statistics
        stats = calculate_summary_stats(data, service_name)
        print(f"\n📊 Summary Statistics:")
        print(f"   Data source: {stats['data_source']}")
        print(f"   CI workflows found: {stats.get('workflows_found_in_ci', 'N/A')}")
        print(f"   Total deployments: {stats['total_deployments']}")
        if stats.get("production_deployments_in_window"):
            print(f"   Production deployments: {stats['production_deployments_in_window']}")
        print(f"   Success/Failed/Error: {stats['successful_deployments']}/{stats['failed_deployments']}/{stats['error_deployments']}")

        report["services"][service_name] = {
            "timestamp_analysis": timestamp_analysis,
            "completeness": completeness,
            "statistics": stats
        }

    return report


if __name__ == "__main__":
    report = generate_coverage_report()

    # Save report
    output_path = Path("/home/coding/aide-de-camp/docs/research/deployment-data/coverage-report.json")
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Coverage report saved to: {output_path}")
    print(f"{'='*60}")
