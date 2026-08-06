#!/usr/bin/env python3
"""
Calculate deployment interval statistics and compare services.
Builds on MTBD calculation to add min, max, median, variance metrics.
"""

import json
import statistics
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from math import sqrt

def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp string to datetime object."""
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))

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

def calculate_interval_statistics(events: List[dict]) -> Dict:
    """Calculate comprehensive interval statistics for deployment events."""
    if len(events) == 0:
        return {
            "total_deployments": 0,
            "intervals_hours": [],
            "min_interval_hours": None,
            "max_interval_hours": None,
            "median_interval_hours": None,
            "mean_interval_hours": None,
            "stddev_interval_hours": None,
            "iqr_interval_hours": None,
            "coefficient_of_variation": None,
            "note": "No deployment events found"
        }

    if len(events) == 1:
        return {
            "total_deployments": 1,
            "intervals_hours": [],
            "min_interval_hours": None,
            "max_interval_hours": None,
            "median_interval_hours": None,
            "mean_interval_hours": None,
            "stddev_interval_hours": None,
            "iqr_interval_hours": None,
            "coefficient_of_variation": None,
            "note": "Only one deployment event - no intervals to calculate"
        }

    # Extract timestamps and calculate intervals
    timestamps = [event["timestamp"] for event in events]
    intervals_hours = []

    for i in range(1, len(timestamps)):
        diff_seconds = (timestamps[i] - timestamps[i-1]).total_seconds()
        intervals_hours.append(diff_seconds / 3600)  # Convert to hours

    if not intervals_hours:
        return {
            "total_deployments": len(events),
            "intervals_hours": [],
            "min_interval_hours": None,
            "max_interval_hours": None,
            "median_interval_hours": None,
            "mean_interval_hours": None,
            "stddev_interval_hours": None,
            "iqr_interval_hours": None,
            "coefficient_of_variation": None,
            "note": "No intervals calculated"
        }

    # Calculate statistics
    min_interval = min(intervals_hours)
    max_interval = max(intervals_hours)
    median_interval = statistics.median(intervals_hours)
    mean_interval = statistics.mean(intervals_hours)

    # Calculate standard deviation
    if len(intervals_hours) > 1:
        stddev_interval = statistics.stdev(intervals_hours)
        # Coefficient of variation (CV) = std/mean (lower = more consistent)
        cv = (stddev_interval / mean_interval) if mean_interval > 0 else None
    else:
        stddev_interval = None
        cv = None

    # Calculate Interquartile Range (IQR)
    if len(intervals_hours) >= 4:
        q1 = statistics.quantiles(intervals_hours, n=4)[0]  # 25th percentile
        q3 = statistics.quantiles(intervals_hours, n=4)[2]  # 75th percentile
        iqr = q3 - q1
    else:
        iqr = None

    return {
        "total_deployments": len(events),
        "intervals_hours": [round(interval, 2) for interval in intervals_hours],
        "min_interval_hours": round(min_interval, 2),
        "max_interval_hours": round(max_interval, 2),
        "median_interval_hours": round(median_interval, 2),
        "mean_interval_hours": round(mean_interval, 2),
        "stddev_interval_hours": round(stddev_interval, 2) if stddev_interval else None,
        "iqr_interval_hours": round(iqr, 2) if iqr else None,
        "coefficient_of_variation": round(cv, 2) if cv else None,
        "first_deployment": timestamps[0].isoformat(),
        "last_deployment": timestamps[-1].isoformat()
    }

def compare_services(pbx_web_stats: Dict, whisper_stt_stats: Dict) -> Dict:
    """Generate side-by-side comparison and insights."""
    comparison = {
        "interval_statistics_table": {
            "pbx_web": {
                "total_deployments": pbx_web_stats["total_deployments"],
                "min_interval_hours": pbx_web_stats["min_interval_hours"],
                "max_interval_hours": pbx_web_stats["max_interval_hours"],
                "median_interval_hours": pbx_web_stats["median_interval_hours"],
                "mean_interval_hours": pbx_web_stats["mean_interval_hours"],
                "stddev_interval_hours": pbx_web_stats["stddev_interval_hours"],
                "coefficient_of_variation": pbx_web_stats["coefficient_of_variation"]
            },
            "whisper_stt": {
                "total_deployments": whisper_stt_stats["total_deployments"],
                "min_interval_hours": whisper_stt_stats["min_interval_hours"],
                "max_interval_hours": whisper_stt_stats["max_interval_hours"],
                "median_interval_hours": whisper_stt_stats["median_interval_hours"],
                "mean_interval_hours": whisper_stt_stats["mean_interval_hours"],
                "stddev_interval_hours": whisper_stt_stats["stddev_interval_hours"],
                "coefficient_of_variation": whisper_stt_stats["coefficient_of_variation"]
            }
        },
        "consistency_analysis": {},
        "frequency_comparison": {},
        "insights": []
    }

    # Determine which service has more consistent deployment cadence
    # Lower coefficient of variation = more consistent
    pbx_cv = pbx_web_stats.get("coefficient_of_variation")
    whisper_cv = whisper_stt_stats.get("coefficient_of_variation")

    if pbx_cv is not None and whisper_cv is not None:
        if pbx_cv < whisper_cv:
            more_consistent = "pbx-web"
            consistency_reason = f"pbx-web has lower coefficient of variation ({pbx_cv} vs {whisper_cv})"
        elif whisper_cv < pbx_cv:
            more_consistent = "whisper-stt"
            consistency_reason = f"whisper-stt has lower coefficient of variation ({whisper_cv} vs {pbx_cv})"
        else:
            more_consistent = "equally consistent"
            consistency_reason = f"Both services have identical coefficient of variation ({pbx_cv})"

        comparison["consistency_analysis"] = {
            "more_consistent_service": more_consistent,
            "reason": consistency_reason,
            "pbx_web_cv": pbx_cv,
            "whisper_stt_cv": whisper_cv
        }
        comparison["insights"].append({
            "type": "consistency",
            "summary": f"{more_consistent.title()} has more consistent deployment cadence",
            "detail": consistency_reason
        })

    # Compare deployment frequencies
    pbx_mean = pbx_web_stats.get("mean_interval_hours")
    whisper_mean = whisper_stt_stats.get("mean_interval_hours")

    if pbx_mean is not None and whisper_mean is not None:
        if pbx_mean < whisper_mean:
            more_frequent = "pbx-web"
            frequency_diff = whisper_mean - pbx_mean
        else:
            more_frequent = "whisper-stt"
            frequency_diff = pbx_mean - whisper_mean

        comparison["frequency_comparison"] = {
            "more_frequent_service": more_frequent,
            "pbx_web_mean_hours": pbx_mean,
            "whisper_stt_mean_hours": whisper_mean,
            "difference_hours": round(frequency_diff, 2)
        }
        comparison["insights"].append({
            "type": "frequency",
            "summary": f"{more_frequent.title()} deploys more frequently on average",
            "detail": f"Mean interval: {pbx_mean}h (pbx-web) vs {whisper_mean}h (whisper-stt)"
        })

    # Variance analysis using standard deviation
    pbx_stddev = pbx_web_stats.get("stddev_interval_hours")
    whisper_stddev = whisper_stt_stats.get("stddev_interval_hours")

    if pbx_stddev is not None and whisper_stddev is not None:
        comparison["insights"].append({
            "type": "variance",
            "summary": f"Interval variance comparison",
            "detail": f"Standard deviation: {pbx_stddev}h (pbx-web) vs {whisper_stddev}h (whisper-stt)"
        })

    # Range analysis
    pbx_range = pbx_web_stats.get("max_interval_hours") - pbx_web_stats.get("min_interval_hours", 0)
    whisper_range = whisper_stt_stats.get("max_interval_hours") - whisper_stt_stats.get("min_interval_hours", 0)

    if pbx_range is not None and whisper_range is not None:
        comparison["insights"].append({
            "type": "range",
            "summary": f"Deployment interval ranges",
            "detail": f"Range (max-min): {pbx_range:.2f}h (pbx-web) vs {whisper_range:.2f}h (whisper-stt)"
        })

    return comparison

def format_comparison_table(comparison: Dict) -> str:
    """Generate a readable comparison table."""
    table = "\n" + "="*80 + "\n"
    table += "DEPLOYMENT INTERVAL STATISTICS - SIDE-BY-SIDE COMPARISON\n"
    table += "="*80 + "\n\n"

    table += f"{'Metric':<35} {'pbx-web':>20} {'whisper-stt':>20}\n"
    table += "-"*80 + "\n"

    pbx = comparison["interval_statistics_table"]["pbx_web"]
    whisper = comparison["interval_statistics_table"]["whisper_stt"]

    metrics = [
        ("Total Deployments (30 days)", "total_deployments"),
        ("Min Interval (hours)", "min_interval_hours"),
        ("Max Interval (hours)", "max_interval_hours"),
        ("Median Interval (hours)", "median_interval_hours"),
        ("Mean Interval (hours)", "mean_interval_hours"),
        ("Std Dev (hours)", "stddev_interval_hours"),
        ("Coefficient of Variation", "coefficient_of_variation")
    ]

    for label, key in metrics:
        pbx_val = pbx.get(key)
        whisper_val = whisper.get(key)

        pbx_str = f"{pbx_val:.2f}" if pbx_val is not None else "N/A"
        whisper_str = f"{whisper_val:.2f}" if whisper_val is not None else "N/A"

        table += f"{label:<35} {pbx_str:>20} {whisper_str:>20}\n"

    table += "-"*80 + "\n\n"

    # Add insights
    table += "INSIGHTS\n"
    table += "-"*80 + "\n"

    for insight in comparison.get("insights", []):
        table += f"• [{insight['type'].upper()}] {insight['summary']}\n"
        table += f"  {insight['detail']}\n\n"

    table += "="*80 + "\n"
    return table

def main():
    """Main function to calculate interval statistics and compare services."""

    # Load deployment data
    try:
        with open('/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json', 'r') as f:
            pbx_web_data = json.load(f)

        with open('/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json', 'r') as f:
            whisper_stt_data = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: Required deployment data file not found: {e}")
        print("Please ensure the following files exist:")
        print("  - pbx-web-deployment-data-30days.json")
        print("  - whisper-stt-deployment-data-30days.json")
        return

    # Extract deployment events
    pbx_web_events = extract_deployment_events(pbx_web_data, "pbx-web")
    whisper_stt_events = extract_deployment_events(whisper_stt_data, "whisper-stt")

    print(f"Loaded {len(pbx_web_events)} pbx-web deployment events")
    print(f"Loaded {len(whisper_stt_events)} whisper-stt deployment events")

    # Calculate interval statistics
    pbx_web_stats = calculate_interval_statistics(pbx_web_events)
    whisper_stt_stats = calculate_interval_statistics(whisper_stt_events)

    # Generate comparison
    comparison = compare_services(pbx_web_stats, whisper_stt_stats)

    # Create output structure
    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "task_id": "adc-1efr9",
            "description": "Deployment interval statistics and service comparison",
            "time_period_days": 30
        },
        "pbx_web": {
            "service_name": "pbx-web",
            "namespace": "pbx-web",
            "cluster": "ardenone-cluster",
            "interval_statistics": pbx_web_stats
        },
        "whisper_stt": {
            "service_name": "whisper-stt",
            "namespace": "whisper-stt",
            "cluster": "ardenone-cluster",
            "interval_statistics": whisper_stt_stats
        },
        "comparison": comparison
    }

    # Save to JSON
    output_file = '/home/coding/aide-de-camp/research/deployment-interval-statistics.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Interval statistics saved to {output_file}")

    # Print comparison table
    print(format_comparison_table(comparison))

    # Save readable table to text file
    table_file = '/home/coding/aide-de-camp/research/deployment-interval-comparison.txt'
    with open(table_file, 'w') as f:
        f.write(format_comparison_table(comparison))

    print(f"✓ Comparison table saved to {table_file}")

if __name__ == "__main__":
    main()