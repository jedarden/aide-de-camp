#!/usr/bin/env python3
"""
Calculate deployment success rates and metrics for pbx-web and whisper-stt services.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

from src.utils.atomic_write import atomic_write


def load_deployment_data(service: str) -> Dict[str, Any]:
    """Load deployment data for a given service."""
    if service == "pbx-web":
        data_path = Path("research/deployment-metadata-extraction/pbx-web-deployment-events.json")
    elif service == "whisper-stt":
        data_path = Path("research/whisper-stt-30days/deployments-30days.json")
    else:
        raise ValueError(f"Unknown service: {service}")

    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    with open(data_path) as f:
        return json.load(f)


def extract_deployment_events(data: Dict[str, Any], service: str) -> List[Dict[str, Any]]:
    """Extract deployment events from the loaded data."""
    if service == "pbx-web":
        return data.get("events", [])
    elif service == "whisper-stt":
        # whisper-stt has nested structure under deployments
        deployments = data.get("deployments", {})
        all_events = []
        for deployment_name, deployment_data in deployments.items():
            if "deployment_events" in deployment_data:
                events = deployment_data["deployment_events"]
                # Add deployment_name to each event for context
                for event in events:
                    event["deployment_name"] = deployment_name
                all_events.extend(events)
        return all_events
    return []


def calculate_metrics(deployment_events: List[Dict[str, Any]], service: str) -> Dict[str, Any]:
    """Calculate deployment metrics for a service."""
    if not deployment_events:
        return {
            "service": service,
            "error": "No deployment events found"
        }

    # Filter events to last 30 days (use UTC for consistent comparison)
    cutoff_date = datetime.now() - timedelta(days=30)
    filtered_events = []

    for event in deployment_events:
        timestamp_str = event.get("timestamp")
        if timestamp_str:
            try:
                # Parse timestamp and make it naive for comparison
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                # Convert to UTC and make naive
                timestamp = timestamp.replace(tzinfo=None)
                if timestamp >= cutoff_date:
                    filtered_events.append(event)
            except ValueError:
                # Skip events with invalid timestamps
                continue

    if not filtered_events:
        return {
            "service": service,
            "error": "No deployment events found in last 30 days"
        }

    # Sort by timestamp
    filtered_events.sort(key=lambda x: x.get("timestamp", ""))

    # Calculate success/failure counts
    total_deployments = len(filtered_events)
    successful_deployments = sum(1 for e in filtered_events if e.get("success") is True)
    failed_deployments = total_deployments - successful_deployments

    # Calculate success rate
    success_rate = (successful_deployments / total_deployments * 100) if total_deployments > 0 else 0
    failure_rate = (failed_deployments / total_deployments * 100) if total_deployments > 0 else 0

    # Calculate deployment frequency (deployments per day)
    if len(filtered_events) >= 2:
        first_timestamp = datetime.fromisoformat(filtered_events[0].get("timestamp", "").replace("Z", "+00:00")).replace(tzinfo=None)
        last_timestamp = datetime.fromisoformat(filtered_events[-1].get("timestamp", "").replace("Z", "+00:00")).replace(tzinfo=None)
        time_span_days = (last_timestamp - first_timestamp).days
        if time_span_days > 0:
            deploy_frequency = total_deployments / time_span_days
        else:
            deploy_frequency = 0
    else:
        deploy_frequency = 0

    # Calculate mean time between deployments (in hours)
    time_between_deployments = []
    for i in range(1, len(filtered_events)):
        current_time = datetime.fromisoformat(filtered_events[i].get("timestamp", "").replace("Z", "+00:00")).replace(tzinfo=None)
        prev_time = datetime.fromisoformat(filtered_events[i-1].get("timestamp", "").replace("Z", "+00:00")).replace(tzinfo=None)
        time_diff = current_time - prev_time
        time_between_deployments.append(time_diff.total_seconds() / 3600)  # Convert to hours

    mean_time_between_deployments = (
        sum(time_between_deployments) / len(time_between_deployments)
        if time_between_deployments else 0
    )

    # Get deployment names involved
    deployment_names = list(set(e.get("deployment_name", "unknown") for e in filtered_events))

    return {
        "service": service,
        "period_days": 30,
        "total_deployments": total_deployments,
        "successful_deployments": successful_deployments,
        "failed_deployments": failed_deployments,
        "success_rate": round(success_rate, 2),
        "failure_rate": round(failure_rate, 2),
        "deployment_frequency_per_day": round(deploy_frequency, 4),
        "mean_time_between_deployments_hours": round(mean_time_between_deployments, 2),
        "deployment_names": deployment_names,
        "first_deployment": filtered_events[0].get("timestamp") if filtered_events else None,
        "last_deployment": filtered_events[-1].get("timestamp") if filtered_events else None
    }


def main():
    """Calculate metrics for both services and save to intermediate file."""
    # Load data for both services
    pbx_web_data = load_deployment_data("pbx-web")
    whisper_stt_data = load_deployment_data("whisper-stt")

    # Extract deployment events
    pbx_web_events = extract_deployment_events(pbx_web_data, "pbx-web")
    whisper_stt_events = extract_deployment_events(whisper_stt_data, "whisper-stt")

    # Calculate metrics
    pbx_web_metrics = calculate_metrics(pbx_web_events, "pbx-web")
    whisper_stt_metrics = calculate_metrics(whisper_stt_events, "whisper-stt")

    # Create output directory if it doesn't exist
    output_dir = Path("docs/research")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save results to intermediate file
    results = {
        "generated_at": datetime.now().isoformat(),
        "period_days": 30,
        "services": {
            "pbx-web": pbx_web_metrics,
            "whisper-stt": whisper_stt_metrics
        },
        "summary": {
            "pbx-web": {
                "success_rate": pbx_web_metrics.get("success_rate", 0),
                "deploy_count": pbx_web_metrics.get("total_deployments", 0),
                "deploy_frequency": pbx_web_metrics.get("deployment_frequency_per_day", 0)
            },
            "whisper-stt": {
                "success_rate": whisper_stt_metrics.get("success_rate", 0),
                "deploy_count": whisper_stt_metrics.get("total_deployments", 0),
                "deploy_frequency": whisper_stt_metrics.get("deployment_frequency_per_day", 0)
            }
        }
    }

    output_path = output_dir / "deployment-metrics-intermediate.json"
    atomic_write(output_path, json.dumps(results, indent=2))

    print(f"Deployment metrics calculated and saved to {output_path}")
    print(f"\nSummary:")
    print(f"  pbx-web: {pbx_web_metrics.get('success_rate', 0)}% success rate ({pbx_web_metrics.get('total_deployments', 0)} deployments)")
    print(f"  whisper-stt: {whisper_stt_metrics.get('success_rate', 0)}% success rate ({whisper_stt_metrics.get('total_deployments', 0)} deployments)")


if __name__ == "__main__":
    main()