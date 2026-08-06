#!/usr/bin/env python3
"""
Compute deployment frequency and timing metrics for pbx-web and whisper-stt.
"""

from datetime import datetime
from typing import List, Dict, Any
import json

def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp."""
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))

def calculate_metrics(deployments: List[Dict[str, Any]], service_name: str) -> Dict[str, Any]:
    """
    Calculate deployment frequency and timing metrics.

    Args:
        deployments: List of deployment events with timestamps
        service_name: Name of the service for reporting

    Returns:
        Dictionary containing calculated metrics
    """
    if not deployments:
        return {
            "service": service_name,
            "error": "No deployments found",
            "total_deployments": 0
        }

    # Sort deployments by timestamp
    sorted_deployments = sorted(deployments, key=lambda x: x["timestamp"])

    # Extract timestamps
    timestamps = [parse_timestamp(d["timestamp"]) for d in sorted_deployments]

    # Basic counts
    total_deployments = len(timestamps)

    # Time range
    first_deployment = timestamps[0]
    last_deployment = timestamps[-1]
    time_range_days = (last_deployment - first_deployment).total_seconds() / 86400

    # Frequency (deployments per day)
    if time_range_days > 0:
        frequency_per_day = total_deployments / time_range_days
    else:
        frequency_per_day = 0

    # Mean time between deployments
    if total_deployments > 1:
        time_diffs = [(timestamps[i] - timestamps[i-1]).total_seconds() / 3600
                      for i in range(1, len(timestamps))]
        mean_time_between_hours = sum(time_diffs) / len(time_diffs)
        mean_time_between_days = mean_time_between_hours / 24
    else:
        mean_time_between_hours = None
        mean_time_between_days = None

    # Compile metrics
    metrics = {
        "service": service_name,
        "total_deployments": total_deployments,
        "first_deployment": first_deployment.isoformat(),
        "last_deployment": last_deployment.isoformat(),
        "time_range_days": round(time_range_days, 2),
        "frequency_deployments_per_day": round(frequency_per_day, 4),
        "frequency_deployments_per_week": round(frequency_per_day * 7, 2),
        "frequency_deployments_per_month": round(frequency_per_day * 30, 2),
    }

    if mean_time_between_hours is not None:
        metrics["mean_time_between_deployments_hours"] = round(mean_time_between_hours, 2)
        metrics["mean_time_between_deployments_days"] = round(mean_time_between_days, 2)
    else:
        metrics["mean_time_between_deployments_hours"] = "N/A (single deployment)"
        metrics["mean_time_between_deployments_days"] = "N/A (single deployment)"

    return metrics

def main():
    """Main function to compute metrics for both services."""

    # whisper-stt deployments (from deployments-30days.json)
    whisper_stt_deployments = [
        {"timestamp": "2026-07-12T16:53:42Z", "revision": 32},
        {"timestamp": "2026-07-08T03:26:44Z", "revision": 31},
        {"timestamp": "2026-07-08T03:16:13Z", "revision": 30},
        {"timestamp": "2026-07-08T03:09:35Z", "revision": 29},
        {"timestamp": "2026-07-02T02:20:33Z", "revision": 28},
        {"timestamp": "2026-07-01T19:46:33Z", "revision": 27},
        {"timestamp": "2026-06-26T16:33:34Z", "revision": 26},
        {"timestamp": "2026-06-26T12:42:03Z", "revision": 25},
        {"timestamp": "2026-06-25T14:10:16Z", "revision": 24},
        {"timestamp": "2026-06-25T14:08:07Z", "revision": 23},
    ]

    # pbx-web deployments (from replicasets summary, filtered to pbx-web only)
    pbx_web_deployments = [
        {"timestamp": "2026-07-28T17:05:51Z", "revision": 13},
        {"timestamp": "2026-07-13T18:18:07Z", "revision": 14},
        {"timestamp": "2026-07-13T18:07:55Z", "revision": 11},
        {"timestamp": "2026-06-25T15:23:48Z", "revision": 10},
        {"timestamp": "2026-06-23T18:55:52Z", "revision": 9},
        {"timestamp": "2026-06-23T18:37:39Z", "revision": 8},
        {"timestamp": "2026-06-21T11:13:44Z", "revision": 7},
        {"timestamp": "2026-06-15T18:11:38Z", "revision": 6},
        {"timestamp": "2026-05-11T18:17:51Z", "revision": 5},
        {"timestamp": "2026-05-07T18:57:22Z", "revision": 4},
        {"timestamp": "2026-05-07T18:40:16Z", "revision": 3},
    ]

    # Calculate metrics
    whisper_metrics = calculate_metrics(whisper_stt_deployments, "whisper-stt")
    pbx_metrics = calculate_metrics(pbx_web_deployments, "pbx-web")

    # Create results
    results = {
        "analysis_date": "2026-08-06",
        "metrics": [whisper_metrics, pbx_metrics]
    }

    # Print results
    print("=" * 80)
    print("DEPLOYMENT FREQUENCY AND TIMING METRICS")
    print("=" * 80)
    print()

    for metrics in results["metrics"]:
        print(f"Service: {metrics['service']}")
        print("-" * 80)
        print(f"  Total deployments:           {metrics['total_deployments']}")
        print(f"  First deployment:            {metrics['first_deployment']}")
        print(f"  Last deployment:             {metrics['last_deployment']}")
        print(f"  Time range (days):           {metrics['time_range_days']}")
        print(f"  Frequency (deploys/day):    {metrics['frequency_deployments_per_day']}")
        print(f"  Frequency (deploys/week):   {metrics['frequency_deployments_per_week']}")
        print(f"  Frequency (deploys/month):  {metrics['frequency_deployments_per_month']}")

        if isinstance(metrics['mean_time_between_deployments_hours'], (int, float)):
            print(f"  Mean time between (hours):  {metrics['mean_time_between_deployments_hours']}")
            print(f"  Mean time between (days):   {metrics['mean_time_between_deployments_days']}")
        else:
            print(f"  Mean time between:           {metrics['mean_time_between_deployments_hours']}")
        print()

    # Save to file
    with open('/home/coding/aide-de-camp/research/adc-3m6ai-metrics.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("=" * 80)
    print("Results saved to: research/adc-3m6ai-metrics.json")
    print("=" * 80)

if __name__ == "__main__":
    main()