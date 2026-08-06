#!/usr/bin/env python3
"""
Compute deployment frequency and timing metrics for pbx-web and whisper-stt services.

This script loads validated deployment data and calculates:
- Deployment frequency (deployments per day)
- Mean time between deployments
- Time range (first to last deployment)
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp string to datetime object."""
    # Handle Z suffix
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def calculate_deployment_metrics(deployments: List[Dict[str, Any]], analysis_period_days: int = 30) -> Dict[str, Any]:
    """
    Calculate deployment frequency and timing metrics.

    Args:
        deployments: List of deployment events with timestamps
        analysis_period_days: Analysis period in days (default 30)

    Returns:
        Dictionary containing calculated metrics
    """
    if not deployments:
        return {
            "total_deployments": 0,
            "deployment_frequency_per_day": 0.0,
            "deployment_frequency_days_per_deployment": None,
            "mean_time_between_deployments_hours": None,
            "time_range_days": 0.0,
            "first_deployment": None,
            "last_deployment": None,
            "deployment_intervals_hours": [],
            "analysis_period_days": analysis_period_days
        }

    # Sort deployments by timestamp
    sorted_deployments = sorted(deployments, key=lambda x: x["timestamp"])

    # Extract timestamps
    timestamps = [parse_timestamp(d["timestamp"]) for d in sorted_deployments]

    # Calculate basic metrics
    total_deployments = len(deployments)
    first_deployment = sorted_deployments[0]["timestamp"]
    last_deployment = sorted_deployments[-1]["timestamp"]

    # Calculate time range
    time_range_seconds = (timestamps[-1] - timestamps[0]).total_seconds()
    time_range_days = time_range_seconds / 86400.0

    # Calculate deployment intervals (time between consecutive deployments)
    deployment_intervals_hours = []
    for i in range(1, len(timestamps)):
        interval_seconds = (timestamps[i] - timestamps[i-1]).total_seconds()
        interval_hours = interval_seconds / 3600.0
        deployment_intervals_hours.append(interval_hours)

    # Calculate mean time between deployments
    if deployment_intervals_hours:
        mean_time_between_deployments_hours = sum(deployment_intervals_hours) / len(deployment_intervals_hours)
    else:
        mean_time_between_deployments_hours = None

    # Calculate deployment frequency
    if time_range_days > 0:
        deployment_frequency_per_day = total_deployments / time_range_days
        deployment_frequency_days_per_deployment = time_range_days / (total_deployments - 1) if total_deployments > 1 else None
    else:
        deployment_frequency_per_day = 0.0
        deployment_frequency_days_per_deployment = None

    return {
        "total_deployments": total_deployments,
        "deployment_frequency_per_day": round(deployment_frequency_per_day, 4),
        "deployment_frequency_days_per_deployment": round(deployment_frequency_days_per_deployment, 4) if deployment_frequency_days_per_deployment else None,
        "mean_time_between_deployments_hours": round(mean_time_between_deployments_hours, 4) if mean_time_between_deployments_hours else None,
        "time_range_days": round(time_range_days, 4),
        "first_deployment": first_deployment,
        "last_deployment": last_deployment,
        "deployment_intervals_hours": [round(h, 4) for h in deployment_intervals_hours],
        "analysis_period_days": analysis_period_days
    }


def load_pbx_web_deployments(data_file: Path) -> List[Dict[str, Any]]:
    """Load pbx-web deployment events from validated data."""
    with open(data_file, 'r') as f:
        data = json.load(f)

    deployments = []
    for event in data.get("deployment_events_last_30_days", []):
        deployments.append({
            "timestamp": event["timestamp"],
            "event_type": event.get("event_type"),
            "revision": event.get("revision"),
            "image": event.get("image")
        })

    return deployments


def load_whisper_stt_deployments(data_file: Path) -> List[Dict[str, Any]]:
    """Load whisper-stt deployment events from validated data."""
    with open(data_file, 'r') as f:
        data = json.load(f)

    deployments = []
    replicasets = data.get("deployment_history_30_days", {}).get("replicasets", [])

    # Filter to whisper-stt deployment only (exclude whisper-openai)
    for rs in replicasets:
        if rs.get("deployment") == "whisper-stt":
            deployments.append({
                "timestamp": rs["created"],
                "revision": rs.get("revision"),
                "image": rs.get("image"),
                "status": rs.get("status")
            })

    return deployments


def main():
    """Main function to compute and save metrics."""
    # Define file paths
    base_dir = Path("/home/coding/aide-de-camp")
    pbx_web_data_file = base_dir / "pbx-web-deployment-data-30days.json"
    whisper_stt_data_file = base_dir / "whisper-stt-deployment-data-30days.json"
    output_file = base_dir / "research" / "deployment-frequency-metrics.json"

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Load deployment data
    print("Loading deployment data...")
    pbx_web_deployments = load_pbx_web_deployments(pbx_web_data_file)
    whisper_stt_deployments = load_whisper_stt_deployments(whisper_stt_data_file)

    print(f"Loaded {len(pbx_web_deployments)} pbx-web deployments")
    print(f"Loaded {len(whisper_stt_deployments)} whisper-stt deployments")

    # Calculate metrics for both services
    analysis_period_days = 30
    print(f"\nCalculating metrics for {analysis_period_days}-day period...")

    pbx_web_metrics = calculate_deployment_metrics(pbx_web_deployments, analysis_period_days)
    whisper_stt_metrics = calculate_deployment_metrics(whisper_stt_deployments, analysis_period_days)

    # Prepare comparative analysis
    comparative = {
        "pbx_web_frequency_per_day": pbx_web_metrics["deployment_frequency_per_day"],
        "whisper_stt_frequency_per_day": whisper_stt_metrics["deployment_frequency_per_day"],
        "pbx_web_mean_time_between_deployments_hours": pbx_web_metrics["mean_time_between_deployments_hours"],
        "whisper_stt_mean_time_between_deployments_hours": whisper_stt_metrics["mean_time_between_deployments_hours"],
        "pbx_web_time_range_days": pbx_web_metrics["time_range_days"],
        "whisper_stt_time_range_days": whisper_stt_metrics["time_range_days"],
    }

    # Add interpretation
    if pbx_web_metrics["deployment_frequency_per_day"] > 0 and whisper_stt_metrics["deployment_frequency_per_day"] > 0:
        freq_ratio = pbx_web_metrics["deployment_frequency_per_day"] / whisper_stt_metrics["deployment_frequency_per_day"]
        comparative["interpretation"] = {
            "frequency_comparison": f"pbx-web deploys {freq_ratio:.2f}x more frequently than whisper-stt",
            "time_between_deployments_comparison": "Comparison based on mean time between deployments",
            "overall_pattern": "Comparative metrics for both services"
        }
    else:
        comparative["interpretation"] = {
            "frequency_comparison": "Unable to compare - one or both services have zero deployments",
            "time_between_deployments_comparison": "Insufficient data",
            "overall_pattern": "Insufficient deployment data for comparison"
        }

    # Build final output
    output = {
        "analysis_metadata": {
            "generated_at": datetime.now().isoformat(),
            "analysis_period_days": analysis_period_days,
            "analysis_period": f"2026-07-07 to 2026-08-06",
            "services_analyzed": ["pbx-web", "whisper-stt"]
        },
        "deployment_frequency_metrics": {
            "pbx-web": pbx_web_metrics,
            "whisper-stt": whisper_stt_metrics
        },
        "comparative_analysis": comparative
    }

    # Save output
    print(f"\nSaving metrics to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print("\n=== Deployment Frequency Metrics ===")
    print(f"\npbx-web:")
    print(f"  Total deployments: {pbx_web_metrics['total_deployments']}")
    print(f"  Frequency: {pbx_web_metrics['deployment_frequency_per_day']} deployments/day")
    print(f"  Mean time between: {pbx_web_metrics['mean_time_between_deployments_hours']} hours")
    print(f"  Time range: {pbx_web_metrics['time_range_days']} days")
    print(f"  First deployment: {pbx_web_metrics['first_deployment']}")
    print(f"  Last deployment: {pbx_web_metrics['last_deployment']}")

    print(f"\nwhisper-stt:")
    print(f"  Total deployments: {whisper_stt_metrics['total_deployments']}")
    print(f"  Frequency: {whisper_stt_metrics['deployment_frequency_per_day']} deployments/day")
    print(f"  Mean time between: {whisper_stt_metrics['mean_time_between_deployments_hours']} hours")
    print(f"  Time range: {whisper_stt_metrics['time_range_days']} days")
    print(f"  First deployment: {whisper_stt_metrics['first_deployment']}")
    print(f"  Last deployment: {whisper_stt_metrics['last_deployment']}")

    print("\n✓ Metrics computed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
