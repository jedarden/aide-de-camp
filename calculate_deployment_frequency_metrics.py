#!/usr/bin/env python3
"""
Calculate deployment frequency and timing metrics for pbx-web and whisper-stt services.
Uses validated deployment data from child bead 1.
"""

import json
from datetime import datetime
from typing import Dict, List, Tuple

def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp string to datetime object."""
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))

def calculate_days_between(start: datetime, end: datetime) -> float:
    """Calculate days between two datetime objects."""
    return (end - start).total_seconds() / 86400

def calculate_hours_between(start: datetime, end: datetime) -> float:
    """Calculate hours between two datetime objects."""
    return (end - start).total_seconds() / 3600

def extract_deployment_events(data: dict, service_name: str) -> List[dict]:
    """Extract deployment events from validated data."""
    events = []

    if service_name == "pbx-web":
        # Extract from deployment_events_last_30_days array
        for event in data.get("deployment_events_last_30_days", []):
            events.append({
                "timestamp": parse_timestamp(event["timestamp"]),
                "date": event["date"],
                "event_type": event["event_type"],
                "outcome": event.get("outcome", "unknown")
            })
    elif service_name == "whisper-stt":
        # Extract from replicasets array
        for rs in data.get("deployment_history_30_days", {}).get("replicasets", []):
            if rs.get("deployment") == "whisper-stt":
                events.append({
                    "timestamp": parse_timestamp(rs["created"]),
                    "status": rs.get("status", "unknown"),
                    "revision": rs.get("revision"),
                    "image": rs.get("image")
                })

    # Sort by timestamp
    events.sort(key=lambda x: x["timestamp"])
    return events

def calculate_frequency_metrics(events: List[dict], time_period_days: int = 30) -> Dict:
    """Calculate deployment frequency and timing metrics."""
    if len(events) == 0:
        return {
            "total_deployments": 0,
            "deployment_frequency_per_day": 0.0,
            "mean_time_between_deployments_hours": None,
            "time_range_days": 0.0,
            "first_deployment": None,
            "last_deployment": None,
            "note": "No deployment events found"
        }

    # Extract timestamps
    timestamps = [event["timestamp"] for event in events]

    # First and last deployments
    first_deployment = min(timestamps)
    last_deployment = max(timestamps)

    # Time range
    time_range_days = calculate_days_between(first_deployment, last_deployment)

    # Total deployments
    total_deployments = len(events)

    # Deployment frequency (deployments per day)
    if time_period_days > 0:
        deployment_frequency_per_day = total_deployments / time_period_days
    else:
        deployment_frequency_per_day = 0.0

    # Mean time between deployments
    if total_deployments > 1:
        # Calculate time between consecutive deployments
        time_diffs = []
        for i in range(1, len(timestamps)):
            time_diffs.append((timestamps[i] - timestamps[i-1]).total_seconds() / 3600)  # hours

        mean_time_between_hours = sum(time_diffs) / len(time_diffs)
    else:
        mean_time_between_hours = None
        time_diffs = []

    return {
        "total_deployments": total_deployments,
        "deployment_frequency_per_day": round(deployment_frequency_per_day, 4),
        "mean_time_between_deployments_hours": round(mean_time_between_hours, 2) if mean_time_between_hours else None,
        "time_range_days": round(time_range_days, 2),
        "first_deployment": first_deployment.isoformat(),
        "last_deployment": last_deployment.isoformat(),
        "consecutive_gaps_hours": [round(gap, 2) for gap in time_diffs] if time_diffs else []
    }

def main():
    """Main function to calculate and save deployment frequency metrics."""

    # Load validated deployment data
    with open('/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json', 'r') as f:
        pbx_web_data = json.load(f)

    with open('/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json', 'r') as f:
        whisper_stt_data = json.load(f)

    # Extract deployment events
    pbx_web_events = extract_deployment_events(pbx_web_data, "pbx-web")
    whisper_stt_events = extract_deployment_events(whisper_stt_data, "whisper-stt")

    # Calculate metrics (using 30-day period from the data)
    time_period_days = 30

    pbx_web_metrics = calculate_frequency_metrics(pbx_web_events, time_period_days)
    whisper_stt_metrics = calculate_frequency_metrics(whisper_stt_events, time_period_days)

    # Create output structure
    metrics_output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "task_id": "adc-3m6ai",
            "description": "Deployment frequency and timing metrics",
            "time_period_days": time_period_days
        },
        "pbx_web": {
            "service_name": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster",
            "metrics": pbx_web_metrics,
            "deployment_events": [
                {
                    "timestamp": event["timestamp"].isoformat(),
                    "event_type": event.get("event_type", "deployment"),
                    "outcome": event.get("outcome", event.get("status", "unknown"))
                }
                for event in pbx_web_events
            ]
        },
        "whisper_stt": {
            "service_name": "whisper-stt",
            "namespace": "whisper-stt",
            "cluster": "ardenone-cluster",
            "metrics": whisper_stt_metrics,
            "deployment_events": [
                {
                    "timestamp": event["timestamp"].isoformat(),
                    "status": event.get("status", "unknown"),
                    "revision": event.get("revision"),
                    "image": event.get("image")
                }
                for event in whisper_stt_events
            ]
        },
        "comparison": {
            "pbx_web_deployments_per_day": pbx_web_metrics["deployment_frequency_per_day"],
            "whisper_stt_deployments_per_day": whisper_stt_metrics["deployment_frequency_per_day"],
            "frequency_ratio": round(pbx_web_metrics["deployment_frequency_per_day"] / whisper_stt_metrics["deployment_frequency_per_day"], 2) if whisper_stt_metrics["deployment_frequency_per_day"] > 0 else None,
            "pbx_web_mean_time_between_hours": pbx_web_metrics["mean_time_between_deployments_hours"],
            "whisper_stt_mean_time_between_hours": whisper_stt_metrics["mean_time_between_deployments_hours"]
        },
        "summary": {
            "pbx_web_total_deployments": pbx_web_metrics["total_deployments"],
            "whisper_stt_total_deployments": whisper_stt_metrics["total_deployments"],
            "pbx_web_time_range_days": pbx_web_metrics["time_range_days"],
            "whisper_stt_time_range_days": whisper_stt_metrics["time_range_days"],
            "analysis_complete": True
        }
    }

    # Save to file
    output_file = '/home/coding/aide-de-camp/research/deployment-frequency-metrics.json'
    with open(output_file, 'w') as f:
        json.dump(metrics_output, f, indent=2)

    print(f"✓ Deployment frequency metrics calculated and saved to {output_file}")
    print(f"\npbx-web:")
    print(f"  - Total deployments: {pbx_web_metrics['total_deployments']}")
    print(f"  - Deployments per day: {pbx_web_metrics['deployment_frequency_per_day']}")
    print(f"  - Mean time between deployments: {pbx_web_metrics['mean_time_between_deployments_hours']} hours")
    print(f"  - Time range: {pbx_web_metrics['time_range_days']} days")
    print(f"\nwhisper-stt:")
    print(f"  - Total deployments: {whisper_stt_metrics['total_deployments']}")
    print(f"  - Deployments per day: {whisper_stt_metrics['deployment_frequency_per_day']}")
    print(f"  - Mean time between deployments: {whisper_stt_metrics['mean_time_between_deployments_hours']} hours")
    print(f"  - Time range: {whisper_stt_metrics['time_range_days']} days")

if __name__ == "__main__":
    main()
