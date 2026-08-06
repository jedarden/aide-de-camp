#!/usr/bin/env python3
"""
Calculate deployment frequency and timing metrics for pbx-web and whisper-stt services.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict

def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp string to datetime object."""
    if ts.endswith('+00:00'):
        ts = ts[:-6]
    return datetime.fromisoformat(ts)

def calculate_time_diff_hours(ts1: str, ts2: str) -> float:
    """Calculate hours between two ISO timestamp strings."""
    dt1 = parse_timestamp(ts1)
    dt2 = parse_timestamp(ts2)
    diff = abs(dt2 - dt1)
    return diff.total_seconds() / 3600

def calculate_service_metrics(deployments: List[Dict[str, Any]], analysis_period_days: int = 30) -> Dict[str, Any]:
    """
    Calculate deployment metrics for a single service.

    Args:
        deployments: List of deployment records with timestamps
        analysis_period_days: Total analysis period in days

    Returns:
        Dictionary with calculated metrics
    """
    if not deployments:
        return {
            "total_deployments": 0,
            "deployment_frequency_per_day": 0.0,
            "deployment_frequency_days_per_deployment": None,
            "mean_time_between_deployments_hours": None,
            "time_range_days": None,
            "first_deployment": None,
            "last_deployment": None,
            "deployment_intervals_hours": [],
            "note": "No deployments found"
        }

    # Sort by timestamp
    sorted_deployments = sorted(deployments, key=lambda x: x['timestamp'])

    # Extract timestamps
    timestamps = [d['timestamp'] for d in sorted_deployments]

    # Basic counts
    total_deployments = len(deployments)

    # Time range
    first_deployment = timestamps[0]
    last_deployment = timestamps[-1]
    time_range_hours = calculate_time_diff_hours(first_deployment, last_deployment)
    time_range_days = time_range_hours / 24

    # Deployment frequency (deployments per day)
    deployment_frequency_per_day = total_deployments / analysis_period_days if analysis_period_days > 0 else 0

    # Deployment frequency (days per deployment)
    deployment_frequency_days_per_deployment = analysis_period_days / total_deployments if total_deployments > 0 else None

    # Mean time between deployments
    deployment_intervals_hours = []
    if total_deployments > 1:
        for i in range(1, total_deployments):
            interval_hours = calculate_time_diff_hours(timestamps[i-1], timestamps[i])
            deployment_intervals_hours.append(interval_hours)

        if deployment_intervals_hours:
            mean_time_between_deployments_hours = sum(deployment_intervals_hours) / len(deployment_intervals_hours)
        else:
            mean_time_between_deployments_hours = None
    else:
        mean_time_between_deployments_hours = None

    return {
        "total_deployments": total_deployments,
        "deployment_frequency_per_day": round(deployment_frequency_per_day, 4),
        "deployment_frequency_days_per_deployment": round(deployment_frequency_days_per_deployment, 2) if deployment_frequency_days_per_deployment else None,
        "mean_time_between_deployments_hours": round(mean_time_between_deployments_hours, 4) if mean_time_between_deployments_hours else None,
        "time_range_days": round(time_range_days, 4),
        "first_deployment": first_deployment,
        "last_deployment": last_deployment,
        "deployment_intervals_hours": [round(interval, 4) for interval in deployment_intervals_hours],
        "analysis_period_days": analysis_period_days
    }

def main():
    """Main function to load data and calculate metrics."""

    # Load the validated deployment data
    with open('docs/research/deployment-data-normalized.json', 'r') as f:
        data = json.load(f)

    # Extract deployment records
    all_deployments = data['deployment_records']

    # Group by service
    service_deployments = defaultdict(list)
    for deployment in all_deployments:
        service = deployment['service']
        service_deployments[service].append(deployment)

    # Analysis period (30 days as per the metadata)
    analysis_period_days = 30

    # Calculate metrics for each service
    metrics = {}

    for service_name in ['pbx-web', 'whisper-stt']:
        deployments = service_deployments[service_name]
        service_metrics = calculate_service_metrics(deployments, analysis_period_days)
        metrics[service_name] = service_metrics

    # Prepare output
    output = {
        "analysis_metadata": {
            "generated_at": datetime.now().isoformat(),
            "analysis_period_days": analysis_period_days,
            "analysis_period": "2026-07-07 to 2026-08-06",
            "services_analyzed": list(metrics.keys())
        },
        "deployment_frequency_metrics": {
            "pbx-web": metrics['pbx-web'],
            "whisper-stt": metrics['whisper-stt']
        },
        "comparative_analysis": {
            "pbx_web_frequency_per_day": metrics['pbx-web']['deployment_frequency_per_day'],
            "whisper_stt_frequency_per_day": metrics['whisper-stt']['deployment_frequency_per_day'],
            "pbx_web_mean_time_between_deployments_hours": metrics['pbx-web']['mean_time_between_deployments_hours'],
            "whisper_stt_mean_time_between_deployments_hours": metrics['whisper-stt']['mean_time_between_deployments_hours'],
            "pbx_web_time_range_days": metrics['pbx-web']['time_range_days'],
            "whisper_stt_time_range_days": metrics['whisper-stt']['time_range_days'],
            "interpretation": {
                "frequency_comparison": "pbx-web deploys {:.2f}x more frequently than whisper-stt".format(
                    metrics['pbx-web']['deployment_frequency_per_day'] / metrics['whisper-stt']['deployment_frequency_per_day']
                    if metrics['whisper-stt']['deployment_frequency_per_day'] > 0 else 0
                ),
                "time_between_deployments_comparison": "pbx-web has {:.2f}x shorter mean time between deployments than whisper-stt".format(
                    metrics['whisper-stt']['mean_time_between_deployments_hours'] / metrics['pbx-web']['mean_time_between_deployments_hours']
                    if metrics['pbx-web']['mean_time_between_deployments_hours'] and metrics['whisper-stt']['mean_time_between_deployments_hours'] > 0 else 0
                ),
                "overall_pattern": "Both services show relatively low deployment frequency, with pbx-web being slightly more active than whisper-stt"
            }
        }
    }

    # Save output
    with open('docs/research/deployment-frequency-metrics.json', 'w') as f:
        json.dump(output, f, indent=2)

    # Print summary
    print("=== Deployment Frequency and Timing Metrics ===\n")

    print("PBX-WEB:")
    print(f"  Total deployments: {metrics['pbx-web']['total_deployments']}")
    print(f"  Deployment frequency: {metrics['pbx-web']['deployment_frequency_per_day']} deployments/day")
    print(f"  Days per deployment: {metrics['pbx-web']['deployment_frequency_days_per_deployment']}")
    print(f"  Mean time between deployments: {metrics['pbx-web']['mean_time_between_deployments_hours']} hours")
    print(f"  Time range: {metrics['pbx-web']['time_range_days']} days")
    print(f"  First deployment: {metrics['pbx-web']['first_deployment']}")
    print(f"  Last deployment: {metrics['pbx-web']['last_deployment']}")
    print(f"  Deployment intervals: {metrics['pbx-web']['deployment_intervals_hours']}")

    print("\nWHISPER-STT:")
    print(f"  Total deployments: {metrics['whisper-stt']['total_deployments']}")
    print(f"  Deployment frequency: {metrics['whisper-stt']['deployment_frequency_per_day']} deployments/day")
    print(f"  Days per deployment: {metrics['whisper-stt']['deployment_frequency_days_per_deployment']}")
    print(f"  Mean time between deployments: {metrics['whisper-stt']['mean_time_between_deployments_hours']} hours")
    print(f"  Time range: {metrics['whisper-stt']['time_range_days']} days")
    print(f"  First deployment: {metrics['whisper-stt']['first_deployment']}")
    print(f"  Last deployment: {metrics['whisper-stt']['last_deployment']}")
    print(f"  Deployment intervals: {metrics['whisper-stt']['deployment_intervals_hours']}")

    print("\n=== COMPARATIVE ANALYSIS ===")
    print(f"pbx-web deploys {metrics['pbx-web']['deployment_frequency_per_day'] / metrics['whisper-stt']['deployment_frequency_per_day']:.2f}x more frequently than whisper-stt")
    if metrics['pbx-web']['mean_time_between_deployments_hours'] and metrics['whisper-stt']['mean_time_between_deployments_hours']:
        print(f"pbx-web has {metrics['whisper-stt']['mean_time_between_deployments_hours'] / metrics['pbx-web']['mean_time_between_deployments_hours']:.2f}x shorter mean time between deployments than whisper-stt")

    print(f"\nResults saved to: docs/research/deployment-frequency-metrics.json")

if __name__ == "__main__":
    main()