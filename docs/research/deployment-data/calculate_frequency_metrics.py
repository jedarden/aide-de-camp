#!/usr/bin/env python3
"""
Calculate deployment frequency and timing metrics for pbx-web and whisper-stt services.
Uses validated deployment data from child bead adc-3m6ah.
"""

import json
from datetime import datetime
from typing import Dict, List, Any
import math

def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime object."""
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'
    return datetime.fromisoformat(ts)

def calculate_metrics(deployments: List[Dict[str, Any]], service_name: str) -> Dict[str, Any]:
    """Calculate deployment frequency and timing metrics."""

    if not deployments:
        return {
            "service": service_name,
            "error": "No deployments found",
            "total_deployments": 0
        }

    # Extract timestamps
    timestamps = []
    for deployment in deployments:
        ts_str = deployment.get("timestamp") or deployment.get("date")
        if ts_str:
            try:
                timestamps.append(parse_timestamp(ts_str))
            except Exception as e:
                print(f"Warning: Could not parse timestamp '{ts_str}': {e}")

    if not timestamps:
        return {
            "service": service_name,
            "error": "No valid timestamps found",
            "total_deployments": len(deployments)
        }

    # Sort by timestamp
    timestamps.sort()

    # Calculate metrics
    first_deployment = timestamps[0]
    last_deployment = timestamps[-1]
    total_deployments = len(timestamps)

    # Time range in days
    time_range_days = (last_deployment - first_deployment).total_seconds() / 86400

    # Deployment frequency (deployments per day)
    if time_range_days > 0:
        frequency_per_day = total_deployments / time_range_days
    else:
        frequency_per_day = float('inf')  # Infinite frequency if all on same day

    # Mean time between deployments
    if total_deployments > 1:
        # Calculate intervals between consecutive deployments
        intervals = []
        for i in range(1, len(timestamps)):
            interval_seconds = (timestamps[i] - timestamps[i-1]).total_seconds()
            intervals.append(interval_seconds)

        # Mean interval in seconds, hours, and days
        mean_interval_seconds = sum(intervals) / len(intervals)
        mean_interval_hours = mean_interval_seconds / 3600
        mean_interval_days = mean_interval_seconds / 86400

        # Min and max intervals for context
        min_interval_seconds = min(intervals)
        max_interval_seconds = max(intervals)
    else:
        mean_interval_seconds = None
        mean_interval_hours = None
        mean_interval_days = None
        min_interval_seconds = None
        max_interval_seconds = None

    return {
        "service": service_name,
        "total_deployments": total_deployments,
        "time_range": {
            "start": first_deployment.isoformat(),
            "end": last_deployment.isoformat(),
            "total_days": round(time_range_days, 2)
        },
        "deployment_frequency": {
            "deployments_per_day": round(frequency_per_day, 4),
            "days_per_deployment": round(1 / frequency_per_day, 2) if frequency_per_day > 0 else None
        },
        "mean_time_between_deployments": {
            "seconds": round(mean_interval_seconds, 2) if mean_interval_seconds else None,
            "hours": round(mean_interval_hours, 2) if mean_interval_hours else None,
            "days": round(mean_interval_days, 2) if mean_interval_days else None
        },
        "interval_range": {
            "min_seconds": round(min_interval_seconds, 2) if min_interval_seconds else None,
            "max_seconds": round(max_interval_seconds, 2) if max_interval_seconds else None
        } if total_deployments > 1 else None,
        "note": "Single deployment - mean time between deployments undefined" if total_deployments <= 1 else None
    }

def main():
    """Load deployment data and calculate metrics for both services."""

    print("Loading deployment data...")

    # Load pbx-web deployment data
    with open('/home/coding/aide-de-camp/docs/research/deployment-data/pbx-web-deployments.json', 'r') as f:
        pbx_data = json.load(f)

    # Load whisper-stt deployment data
    with open('/home/coding/aide-de-camp/docs/research/whisper-stt-deployment-data.json', 'r') as f:
        whisper_data = json.load(f)

    print("Calculating metrics for pbx-web...")

    # Calculate pbx-web metrics (using deployments array)
    pbx_deployments = pbx_data.get("deployments", [])
    pbx_metrics = calculate_metrics(pbx_deployments, "pbx-web")

    print("Calculating metrics for whisper-stt...")

    # Calculate whisper-stt metrics (using deployment_history array)
    whisper_deployments = whisper_data.get("deployment_history", [])
    whisper_metrics = calculate_metrics(whisper_deployments, "whisper-stt")

    # Compile results
    results = {
        "generated_at": datetime.now().isoformat(),
        "analysis_type": "deployment_frequency_and_timing_metrics",
        "services": {
            "pbx-web": pbx_metrics,
            "whisper-stt": whisper_metrics
        },
        "comparison": {
            "pbx-web": {
                "deployments_per_day": pbx_metrics.get("deployment_frequency", {}).get("deployments_per_day"),
                "mean_days_between_deployments": pbx_metrics.get("mean_time_between_deployments", {}).get("days")
            },
            "whisper-stt": {
                "deployments_per_day": whisper_metrics.get("deployment_frequency", {}).get("deployments_per_day"),
                "mean_days_between_deployments": whisper_metrics.get("mean_time_between_deployments", {}).get("days")
            }
        }
    }

    # Save results to file
    output_file = '/home/coding/aide-de-camp/docs/research/deployment-data/frequency-metrics.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {output_file}")

    # Print summary
    print("\n" + "="*60)
    print("DEPLOYMENT FREQUENCY AND TIMING METRICS")
    print("="*60)

    print("\n--- pbx-web ---")
    print(f"Total deployments: {pbx_metrics['total_deployments']}")
    print(f"Time range: {pbx_metrics['time_range']['start']} to {pbx_metrics['time_range']['end']}")
    print(f"Total days: {pbx_metrics['time_range']['total_days']}")
    print(f"Deployments per day: {pbx_metrics['deployment_frequency']['deployments_per_day']}")
    print(f"Days per deployment: {pbx_metrics['deployment_frequency']['days_per_deployment']}")
    if pbx_metrics['mean_time_between_deployments']['days']:
        print(f"Mean time between deployments: {pbx_metrics['mean_time_between_deployments']['days']} days")

    print("\n--- whisper-stt ---")
    print(f"Total deployments: {whisper_metrics['total_deployments']}")
    print(f"Time range: {whisper_metrics['time_range']['start']} to {whisper_metrics['time_range']['end']}")
    print(f"Total days: {whisper_metrics['time_range']['total_days']}")
    print(f"Deployments per day: {whisper_metrics['deployment_frequency']['deployments_per_day']}")
    print(f"Days per deployment: {whisper_metrics['deployment_frequency']['days_per_deployment']}")
    if whisper_metrics['mean_time_between_deployments']['days']:
        print(f"Mean time between deployments: {whisper_metrics['mean_time_between_deployments']['days']} days")

    print("\n" + "="*60)

    return results

if __name__ == "__main__":
    main()
