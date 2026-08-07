#!/usr/bin/env python3
"""
Calculate temporal distributions and deployment correlations.
Bins failures by day across 30-day window and correlates with deployment timestamps.
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any


def load_data(file_path: Path) -> Dict[str, Any]:
    """Load JSON data file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def bin_failures_by_day(classified_failures: List[Dict[str, Any]],
                        start_date: datetime,
                        end_date: datetime) -> Dict[str, Dict[str, Any]]:
    """Bin failures by day across the time window."""

    # Initialize bins for each day
    daily_bins = {}
    current_date = start_date
    while current_date <= end_date:
        day_key = current_date.strftime("%Y-%m-%d")
        daily_bins[day_key] = {
            "date": day_key,
            "total_failures": 0,
            "by_pattern": defaultdict(int),
            "by_service": defaultdict(int),
            "by_severity": defaultdict(int),
            "failure_timestamps": []
        }
        current_date += timedelta(days=1)

    # Populate bins with failures
    for failure in classified_failures:
        timestamp_str = failure.get("timestamp", failure.get("date", ""))
        try:
            if "T" in timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                timestamp = datetime.fromisoformat(timestamp_str)

            day_key = timestamp.strftime("%Y-%m-%d")
            if day_key in daily_bins:
                daily_bins[day_key]["total_failures"] += 1
                daily_bins[day_key]["by_pattern"][failure.get("pattern_type", "Unknown")] += 1
                daily_bins[day_key]["by_service"][failure.get("service", "Unknown")] += 1
                daily_bins[day_key]["by_severity"][failure.get("pattern_severity", "unknown")] += 1
                daily_bins[day_key]["failure_timestamps"].append(timestamp_str)
        except (ValueError, TypeError) as e:
            print(f"Warning: Could not parse timestamp '{timestamp_str}': {e}")

    # Convert defaultdicts to regular dicts for JSON serialization
    for day_data in daily_bins.values():
        day_data["by_pattern"] = dict(day_data["by_pattern"])
        day_data["by_service"] = dict(day_data["by_service"])
        day_data["by_severity"] = dict(day_data["by_severity"])

    return daily_bins


def calculate_daily_failure_rates(daily_bins: Dict[str, Dict[str, Any]],
                                   classified_failures: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Calculate daily failure rate per pattern type."""

    # Count total failures by pattern for rate calculation
    pattern_totals = defaultdict(int)
    for failure in classified_failures:
        pattern_totals[failure.get("pattern_type", "Unknown")] += 1

    daily_rates = {}
    for day_key, day_data in daily_bins.items():
        daily_rates[day_key] = {
            "date": day_key,
            "total_failures": day_data["total_failures"],
            "pattern_rates": {}
        }

        for pattern, count in day_data["by_pattern"].items():
            if pattern in pattern_totals and pattern_totals[pattern] > 0:
                # Rate as percentage of all failures of this pattern across all days
                rate = (count / pattern_totals[pattern]) * 100
            else:
                rate = 0
            daily_rates[day_key]["pattern_rates"][pattern] = {
                "count": count,
                "rate_percentage": round(rate, 2)
            }

    return daily_rates


def identify_temporal_clusters(daily_bins: Dict[str, Dict[str, Any]],
                               threshold_multiplier: float = 1.5) -> List[Dict[str, Any]]:
    """Identify temporal clusters of consecutive days with elevated failure rates."""

    if not daily_bins:
        return []

    # Calculate mean failure rate
    total_failures = sum(day["total_failures"] for day in daily_bins.values())
    days_with_failures = sum(1 for day in daily_bins.values() if day["total_failures"] > 0)
    mean_rate = total_failures / days_with_failures if days_with_failures > 0 else 0

    threshold = mean_rate * threshold_multiplier
    clusters = []
    current_cluster = None

    # Sort days chronologically
    sorted_days = sorted(daily_bins.keys())

    for day_key in sorted_days:
        day_data = daily_bins[day_key]

        if day_data["total_failures"] > threshold:
            if current_cluster is None:
                current_cluster = {
                    "start_date": day_key,
                    "end_date": day_key,
                    "days": [day_key],
                    "total_failures": day_data["total_failures"],
                    "peak_failures": day_data["total_failures"]
                }
            else:
                current_cluster["end_date"] = day_key
                current_cluster["days"].append(day_key)
                current_cluster["total_failures"] += day_data["total_failures"]
                current_cluster["peak_failures"] = max(
                    current_cluster["peak_failures"],
                    day_data["total_failures"]
                )
        else:
            if current_cluster is not None:
                clusters.append(current_cluster)
                current_cluster = None

    if current_cluster is not None:
        clusters.append(current_cluster)

    return clusters


def correlate_with_deployments(daily_bins: Dict[str, Dict[str, Any]],
                               deployments: List[Dict[str, Any]],
                               window_hours: int = 24) -> List[Dict[str, Any]]:
    """Correlate failure spikes with deployment timestamps."""

    correlations = []

    for day_key, day_data in daily_bins.items():
        if day_data["total_failures"] == 0:
            continue

        day_start = datetime.fromisoformat(day_key)
        day_end = day_start + timedelta(days=1)

        # Find deployments within the window before each failure
        for failure_ts in day_data["failure_timestamps"]:
            try:
                if "T" in failure_ts:
                    failure_time = datetime.fromisoformat(failure_ts.replace("Z", "+00:00"))
                else:
                    failure_time = datetime.fromisoformat(failure_ts)

                window_start = failure_time - timedelta(hours=window_hours)
                window_end = failure_time

                # Find deployments in the window
                related_deployments = []
                for deployment in deployments:
                    dep_ts_str = deployment.get("timestamp", "")
                    if dep_ts_str:
                        try:
                            if "T" in dep_ts_str:
                                dep_time = datetime.fromisoformat(dep_ts_str.replace("Z", "+00:00"))
                            else:
                                dep_time = datetime.fromisoformat(dep_ts_str)

                            if window_start <= dep_time <= window_end:
                                related_deployments.append({
                                    "deployment_id": deployment.get("deployment_id", "unknown"),
                                                                    "timestamp": dep_ts_str,
                                    "event_type": deployment.get("event_type", "unknown"),
                                    "image": deployment.get("image", "unknown"),
                                                                    "service": deployment.get("service", deployment.get("source", "unknown")),
                                    "hours_before_failure": (failure_time - dep_time).total_seconds() / 3600
                                })
                        except (ValueError, TypeError):
                            continue

                if related_deployments:
                    correlations.append({
                        "failure_date": day_key,
                        "failure_timestamp": failure_ts,
                        "related_deployments": related_deployments,
                        "deployment_count": len(related_deployments),
                        "pattern": day_data["by_pattern"],
                        "service": day_data["by_service"]
                    })
            except (ValueError, TypeError):
                continue

    return correlations


def main():
    """Main execution function."""
    base_dir = Path("/home/coding/aide-de-camp/docs/research/deployment-data")

    # Load classified failures
    classified_file = base_dir / "classified-failures.json"
    classified_data = load_data(classified_file)
    classified_failures = classified_data.get("classified_failures", [])

    # Load deployment events
    deployment_file = base_dir / "deployment-events-30days-comprehensive.json"
    deployment_data = load_data(deployment_file)

    # Combine all deployment events from both services
    all_deployments = []
    for service in ["pbx-web", "whisper-stt"]:
        if service in deployment_data:
            events = deployment_data[service].get("deployment_events", [])
            for event in events:
                event["service"] = service
                all_deployments.append(event)

    # Define 30-day window
    start_date = datetime(2026, 7, 7)
    end_date = datetime(2026, 8, 6)

    # 1. Bin failures by day
    daily_bins = bin_failures_by_day(classified_failures, start_date, end_date)

    # 2. Calculate daily failure rates per pattern
    daily_rates = calculate_daily_failure_rates(daily_bins, classified_failures)

    # 3. Identify temporal clusters
    clusters = identify_temporal_clusters(daily_bins, threshold_multiplier=1.0)

    # 4. Correlate with deployments
    correlations = correlate_with_deployments(daily_bins, all_deployments, window_hours=24)

    # Build output structure
    result = {
        "metadata": {
            "analysis_type": "temporal_distributions_and_deployment_correlations",
            "generated_at": datetime.now().isoformat(),
            "time_window": {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "total_days": (end_date - start_date).days + 1
            },
            "total_failures_analyzed": len(classified_failures),
            "total_deployments_analyzed": len(all_deployments)
        },
        "daily_bins": daily_bins,
        "daily_failure_rates": daily_rates,
        "temporal_clusters": clusters,
        "deployment_correlations": correlations,
        "summary": {
            "total_days_with_failures": sum(1 for day in daily_bins.values() if day["total_failures"] > 0),
            "peak_failure_day": max(daily_bins.items(), key=lambda x: x[1]["total_failures"])[0] if daily_bins else None,
            "total_clusters": len(clusters),
            "total_correlations": len(correlations)
        }
    }

    # Save output
    output_file = base_dir / "temporal-distributions.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"✓ Temporal analysis saved to {output_file}")
    print(f"  - Total failures: {len(classified_failures)}")
    print(f"  - Days with failures: {result['summary']['total_days_with_failures']}")
    print(f"  - Temporal clusters: {len(clusters)}")
    print(f"  - Deployment correlations: {len(correlations)}")


if __name__ == "__main__":
    main()
