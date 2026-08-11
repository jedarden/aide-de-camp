#!/usr/bin/env python3
"""
Calculate deployment success rates, failure frequencies, and key reliability metrics
for pbx-web and whisper-stt services.
Computes metrics by week and overall statistics.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict

def parse_timestamp(ts: str) -> datetime:
    """Parse various timestamp formats to datetime object."""
    # Handle different timestamp formats
    ts = ts.replace('Z', '+00:00').replace(' -0400', '-04:00').replace(' -0500', '-05:00')

    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        # Try parsing with different formats
        for fmt in ['%Y-%m-%d %H:%M:%S %z', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ']:
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue
        raise ValueError(f"Cannot parse timestamp: {ts}")

def get_week_key(date: datetime) -> str:
    """Get week key in format YYYY-Www (ISO week)."""
    # Get ISO year and week number
    iso_year, iso_week, _ = date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"

def get_week_start_end(date: datetime) -> Tuple[datetime, datetime]:
    """Get start and end of week for a given date (Monday to Sunday)."""
    # Get Monday of the week (weekday() returns 0 for Monday)
    monday = date - timedelta(days=date.weekday())
    sunday = monday + timedelta(days=6)

    # Set time to midnight for start, 23:59:59 for end
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = sunday.replace(hour=23, minute=59, second=59, microsecond=999999)

    return monday, sunday

def extract_pbx_web_deployment_events(data: dict) -> List[dict]:
    """Extract deployment events from pbx-web data."""
    events = []

    # Extract from deployment_events_last_30_days array
    for event in data.get("deployment_events_last_30_days", []):
        timestamp = parse_timestamp(event["timestamp"])

        # Determine success/failure
        outcome = event.get("outcome", "unknown").lower()
        if outcome == "success":
            is_success = True
        elif outcome in ["failed", "rolled_back", "error"]:
            is_success = False
        else:
            is_success = True  # Default to success if unclear

        events.append({
            "timestamp": timestamp,
            "date": event["date"],
            "event_type": event.get("event_type", "deployment_rollout"),
            "outcome": outcome,
            "is_success": is_success,
            "revision": event.get("revision"),
            "image": event.get("image"),
            "service": "pbx-web"
        })

    return events

def extract_whisper_stt_deployment_events(data: dict) -> List[dict]:
    """Extract deployment events from whisper-stt data."""
    events = []

    # Extract from replicasets in deployment_history_30_days
    replicasets = data.get("deployment_history_30_days", {}).get("replicasets", [])

    for rs in replicasets:
        if rs.get("deployment") == "whisper-stt":
            timestamp = parse_timestamp(rs["created"])
            status = rs.get("status", "unknown").lower()

            # Determine success/failure based on status
            # Active means successful deployment, inactive could be rollback/failed
            is_success = status == "active"
            outcome = "success" if is_success else "inactive"

            events.append({
                "timestamp": timestamp,
                "event_type": "deployment_rollout",
                "outcome": outcome,
                "is_success": is_success,
                "revision": rs.get("revision"),
                "image": rs.get("image"),
                "status": status,
                "replicas": rs.get("replicas", 0),
                "service": "whisper-stt"
            })

    return events

def calculate_weekly_metrics(events: List[dict]) -> Dict:
    """Calculate deployment metrics grouped by week."""
    weekly_data = defaultdict(lambda: {
        "deployments": 0,
        "successes": 0,
        "failures": 0,
        "events": []
    })

    for event in events:
        week_key = get_week_key(event["timestamp"])
        week_start, week_end = get_week_start_end(event["timestamp"])

        weekly_data[week_key]["deployments"] += 1
        weekly_data[week_key]["events"].append({
            "timestamp": event["timestamp"].isoformat(),
            "outcome": event["outcome"],
            "is_success": event["is_success"]
        })

        if event["is_success"]:
            weekly_data[week_key]["successes"] += 1
        else:
            weekly_data[week_key]["failures"] += 1

    # Convert to list and calculate success rates
    weekly_metrics = []
    for week_key in sorted(weekly_data.keys()):
        data = weekly_data[week_key]
        deployments = data["deployments"]

        if deployments > 0:
            success_rate = (data["successes"] / deployments) * 100
        else:
            success_rate = 0.0

        # Calculate failures per week (normalized to weekly rate)
        failures_per_week = data["failures"]

        weekly_metrics.append({
            "week": week_key,
            "deployments": deployments,
            "successes": data["successes"],
            "failures": data["failures"],
            "success_rate_percent": round(success_rate, 2),
            "failures_per_week": failures_per_week,
            "events": data["events"]
        })

    return weekly_metrics

def calculate_overall_metrics(events: List[dict], weekly_metrics: List[dict]) -> Dict:
    """Calculate overall metrics from all events."""
    if not events:
        return {
            "total_deployments": 0,
            "total_successes": 0,
            "total_failures": 0,
            "overall_success_rate_percent": 0.0,
            "average_weekly_deployment_rate": 0.0,
            "average_weekly_failure_rate": 0.0,
            "weeks_with_deployments": 0,
            "weeks_analyzed": 0
        }

    total_deployments = len(events)
    total_successes = sum(1 for e in events if e["is_success"])
    total_failures = total_deployments - total_successes

    overall_success_rate = (total_successes / total_deployments * 100) if total_deployments > 0 else 0.0

    weeks_analyzed = len(weekly_metrics)
    weeks_with_deployments = sum(1 for w in weekly_metrics if w["deployments"] > 0)

    # Calculate average weekly rates
    if weeks_analyzed > 0:
        avg_weekly_deployment_rate = total_deployments / weeks_analyzed
        avg_weekly_failure_rate = total_failures / weeks_analyzed
    else:
        avg_weekly_deployment_rate = 0.0
        avg_weekly_failure_rate = 0.0

    return {
        "total_deployments": total_deployments,
        "total_successes": total_successes,
        "total_failures": total_failures,
        "overall_success_rate_percent": round(overall_success_rate, 2),
        "average_weekly_deployment_rate": round(avg_weekly_deployment_rate, 2),
        "average_weekly_failure_rate": round(avg_weekly_failure_rate, 2),
        "weeks_with_deployments": weeks_with_deployments,
        "weeks_analyzed": weeks_analyzed
    }

def main():
    """Main function to calculate deployment success metrics."""

    # Load deployment data
    try:
        with open('/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json', 'r') as f:
            pbx_web_data = json.load(f)
    except FileNotFoundError:
        print("Error: pbx-web deployment data file not found")
        return

    try:
        with open('/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json', 'r') as f:
            whisper_stt_data = json.load(f)
    except FileNotFoundError:
        print("Error: whisper-stt deployment data file not found")
        return

    # Extract deployment events
    pbx_web_events = extract_pbx_web_deployment_events(pbx_web_data)
    whisper_stt_events = extract_whisper_stt_deployment_events(whisper_stt_data)

    # Calculate weekly metrics
    pbx_web_weekly = calculate_weekly_metrics(pbx_web_events)
    whisper_stt_weekly = calculate_weekly_metrics(whisper_stt_events)

    # Calculate overall metrics
    pbx_web_overall = calculate_overall_metrics(pbx_web_events, pbx_web_weekly)
    whisper_stt_overall = calculate_overall_metrics(whisper_stt_events, whisper_stt_weekly)

    # Calculate comparison metrics
    success_rate_delta = pbx_web_overall["overall_success_rate_percent"] - whisper_stt_overall["overall_success_rate_percent"]

    # Get time period from metadata
    time_period = pbx_web_data.get("metadata", {}).get("time_period", {})
    start_date = time_period.get("start", "unknown")
    end_date = time_period.get("end", "unknown")

    # Create comprehensive output structure
    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "task_id": "adc-5b3x0h",
            "description": "Deployment success rates, failure frequencies, and reliability metrics",
            "time_period": {
                "start": start_date,
                "end": end_date,
                "description": time_period.get("description", "Last 30 days")
            },
            "services_analyzed": ["pbx-web", "whisper-stt"],
            "cluster": "ardenone-cluster"
        },
        "pbx_web": {
            "service_name": "pbx-web",
            "namespace": "pbx-web",
            "overall_metrics": pbx_web_overall,
            "weekly_breakdown": pbx_web_weekly,
            "deployment_events": [
                {
                    "timestamp": e["timestamp"].isoformat(),
                    "outcome": e["outcome"],
                    "is_success": e["is_success"],
                    "revision": e.get("revision"),
                    "image": e.get("image"),
                    "event_type": e.get("event_type")
                }
                for e in pbx_web_events
            ]
        },
        "whisper_stt": {
            "service_name": "whisper-stt",
            "namespace": "whisper-stt",
            "overall_metrics": whisper_stt_overall,
            "weekly_breakdown": whisper_stt_weekly,
            "deployment_events": [
                {
                    "timestamp": e["timestamp"].isoformat(),
                    "outcome": e["outcome"],
                    "is_success": e["is_success"],
                    "revision": e.get("revision"),
                    "image": e.get("image"),
                    "status": e.get("status")
                }
                for e in whisper_stt_events
            ]
        },
        "comparison": {
            "pbx_web_success_rate": pbx_web_overall["overall_success_rate_percent"],
            "whisper_stt_success_rate": whisper_stt_overall["overall_success_rate_percent"],
            "success_rate_delta": round(success_rate_delta, 2),
            "pbx_web_total_deployments": pbx_web_overall["total_deployments"],
            "whisper_stt_total_deployments": whisper_stt_overall["total_deployments"],
            "pbx_weekly_failure_rate": pbx_web_overall["average_weekly_failure_rate"],
            "whisper_weekly_failure_rate": whisper_stt_overall["average_weekly_failure_rate"],
            "pbx_weekly_deployment_rate": pbx_web_overall["average_weekly_deployment_rate"],
            "whisper_weekly_deployment_rate": whisper_stt_overall["average_weekly_deployment_rate"]
        },
        "summary": {
            "analysis_period": f"{start_date} to {end_date}",
            "pbx_web_deployment_health": "Excellent" if pbx_web_overall["overall_success_rate_percent"] >= 95 else "Needs attention",
            "whisper_stt_deployment_health": "Excellent" if whisper_stt_overall["overall_success_rate_percent"] >= 95 else "Needs attention",
            "total_deployment_events": pbx_web_overall["total_deployments"] + whisper_stt_overall["total_deployments"],
            "combined_success_rate": round(
                (pbx_web_overall["total_successes"] + whisper_stt_overall["total_successes"]) /
                (pbx_web_overall["total_deployments"] + whisper_stt_overall["total_deployments"]) * 100, 2
            ) if (pbx_web_overall["total_deployments"] + whisper_stt_overall["total_deployments"]) > 0 else 0.0,
            "analysis_complete": True
        }
    }

    # Save to file
    output_file = '/home/coding/aide-de-camp/data/deployment_success_rates.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ Deployment success metrics calculated and saved to {output_file}")
    print(f"\n=== OVERALL STATISTICS ===")
    print(f"\npbx-web:")
    print(f"  - Total deployments: {pbx_web_overall['total_deployments']}")
    print(f"  - Success rate: {pbx_web_overall['overall_success_rate_percent']}%")
    print(f"  - Failures: {pbx_web_overall['total_failures']}")
    print(f"  - Average weekly deployment rate: {pbx_web_overall['average_weekly_deployment_rate']}")
    print(f"  - Average weekly failure rate: {pbx_web_overall['average_weekly_failure_rate']}")

    print(f"\nwhisper-stt:")
    print(f"  - Total deployments: {whisper_stt_overall['total_deployments']}")
    print(f"  - Success rate: {whisper_stt_overall['overall_success_rate_percent']}%")
    print(f"  - Failures: {whisper_stt_overall['total_failures']}")
    print(f"  - Average weekly deployment rate: {whisper_stt_overall['average_weekly_deployment_rate']}")
    print(f"  - Average weekly failure rate: {whisper_stt_overall['average_weekly_failure_rate']}")

    print(f"\n=== COMPARISON ===")
    print(f"  - Success rate delta: {success_rate_delta:.2f}%")
    print(f"  - Combined success rate: {output['summary']['combined_success_rate']}%")
    print(f"  - Total events analyzed: {output['summary']['total_deployment_events']}")

if __name__ == "__main__":
    main()