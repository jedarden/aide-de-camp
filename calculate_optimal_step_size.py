#!/usr/bin/env python3
"""
Calculate optimal time step size for 30-day aggregation.

Based on actual whisper-stt log data, this script analyzes different time bucket sizes
and recommends the optimal granularity for 30-day latency aggregation.
"""

import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path
import statistics


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp with timezone to UTC datetime."""
    # Remove microseconds and timezone for parsing
    try:
        # Parse the timestamp
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        # Convert to UTC
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception as e:
        print(f"Error parsing timestamp {ts_str}: {e}")
        return None


def extract_all_timestamps(log_file: Path) -> list:
    """Extract all valid timestamps from log file."""
    timestamps = []
    with open(log_file, 'r') as f:
        content = f.read()

    # Split by '}\n{' pattern to handle multi-line JSON objects
    # Each object starts with { and ends with }
    objects = content.split('}\n{')

    for obj_str in objects:
        try:
            # Add back the braces that were removed by split
            if not obj_str.startswith('{'):
                obj_str = '{' + obj_str
            if not obj_str.endswith('}'):
                obj_str = obj_str + '}'

            record = json.loads(obj_str)
            ts_str = record.get('timestamp')
            if ts_str:
                dt = parse_timestamp(ts_str)
                if dt:
                    timestamps.append(dt)
        except Exception as e:
            continue
    return timestamps


def calculate_step_size_analysis(timestamps: list, target_days: int = 30) -> dict:
    """Calculate optimal step size analysis for different bucket sizes."""

    if not timestamps:
        return {"error": "No timestamps found"}

    timestamps.sort()

    # Get time range
    start_time = timestamps[0]
    end_time = timestamps[-1]
    actual_duration_hours = (end_time - start_time).total_seconds() / 3600

    print(f"\nData Analysis:")
    print(f"  Start: {start_time.isoformat()}")
    print(f"  End: {end_time.isoformat()}")
    print(f"  Actual data span: {actual_duration_hours:.2f} hours")
    print(f"  Total events: {len(timestamps)}")
    print(f"  Events per hour: {len(timestamps) / actual_duration_hours:.2f}")

    # Calculate actual distribution by hour
    hourly_distribution = defaultdict(int)
    for ts in timestamps:
        hour_key = ts.replace(minute=0, second=0, microsecond=0)
        hourly_distribution[hour_key] += 1

    print(f"  Actual hours with data: {len(hourly_distribution)}")

    # Analyze different step sizes
    step_sizes = [
        {"name": "1-hour", "hours": 1},
        {"name": "6-hour", "hours": 6},
        {"name": "12-hour", "hours": 12},
        {"name": "24-hour", "hours": 24},
    ]

    analysis = {
        "data_summary": {
            "total_events": len(timestamps),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "actual_duration_hours": actual_duration_hours,
            "events_per_hour": len(timestamps) / actual_duration_hours,
            "actual_hours_with_data": len(hourly_distribution)
        },
        "step_size_analysis": [],
        "recommendation": None
    }

    print(f"\n{'=' * 60}")
    print("STEP SIZE ANALYSIS FOR {target_days}-DAY AGGREGATION")
    print(f"{'=' * 60}")

    for step_size in step_sizes:
        hours_per_step = step_size["hours"]

        # Calculate number of buckets for target duration
        target_duration_hours = target_days * 24
        num_buckets = int(target_duration_hours / hours_per_step)

        # Estimate events per bucket (based on current rate)
        events_per_bucket = len(timestamps) / (actual_duration_hours / hours_per_step)

        # Calculate manageability score
        manageability_score = "excellent" if num_buckets < 500 else "good" if num_buckets < 1000 else "acceptable" if num_buckets < 2000 else "poor"

        result = {
            "step_size": step_size["name"],
            "hours_per_bucket": hours_per_step,
            "estimated_buckets_for_{target_days}_days".format(target_days=target_days): num_buckets,
            "estimated_events_per_bucket": events_per_bucket,
            "manageability_score": manageability_score,
            "granularity": "high" if hours_per_step <= 1 else "medium" if hours_per_step <= 12 else "low",
            "within_target": num_buckets < 1000
        }

        analysis["step_size_analysis"].append(result)

        print(f"\n{step_size['name'].upper()} BUCKETS:")
        print(f"  Hours per bucket: {hours_per_step}")
        print(f"  Estimated buckets for {target_days} days: {num_buckets}")
        print(f"  Estimated events per bucket: {events_per_bucket:.1f}")
        print(f"  Manageability: {manageability_score}")
        print(f"  Granularity: {result['granularity']}")
        print(f"  Within target (<1000): {'✅' if num_buckets < 1000 else '❌'}")

    # Find optimal step size
    optimal = None
    for result in analysis["step_size_analysis"]:
        if result["within_target"]:
            if optimal is None or result["hours_per_bucket"] < optimal["hours_per_bucket"]:
                optimal = result

    if optimal:
        analysis["recommendation"] = {
            "step_size": optimal["step_size"],
            "justification": f"Provides {optimal['granularity']} granularity with {optimal['manageability_score']} manageability ({optimal['estimated_buckets_for_{target_days}_days'.format(target_days=target_days)]} buckets for {target_days} days)"
        }
        print(f"\n{'=' * 60}")
        print(f"RECOMMENDED STEP SIZE: {optimal['step_size'].upper()}")
        print(f"{'=' * 60}")
        print(f"Justification: {analysis['recommendation']['justification']}")
    else:
        print(f"\n⚠️ WARNING: No step size meets target (<1000 buckets for {target_days} days)")
        print(f"  Consider using 24-hour buckets or reducing time window")

    return analysis


def main():
    """Main execution."""

    log_file = Path("/home/coding/aide-de-camp/logs/whisper-stt-raw.jsonl")
    output_file = Path("/home/coding/aide-de-camp/optimal-step-size-analysis.json")

    print("Analyzing whisper-stt log data for optimal step size calculation...")
    print(f"Log file: {log_file}")

    # Extract timestamps
    timestamps = extract_all_timestamps(log_file)
    print(f"Extracted {len(timestamps)} valid timestamps")

    if not timestamps:
        print("ERROR: No valid timestamps found in log file")
        return

    # Perform analysis for 30-day target
    analysis = calculate_step_size_analysis(timestamps, target_days=30)

    # Save results
    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)

    print(f"\n✅ Analysis saved to {output_file}")

    # Print summary for documentation
    print(f"\n{'=' * 60}")
    print("CALCULATION METHODOLOGY")
    print(f"{'=' * 60}")
    print("1. Parse all timestamps from whisper-stt-raw.jsonl")
    print("2. Calculate actual event rate (events/hour) from existing data")
    print("3. Extrapolate to 30-day window using current event rate")
    print("4. For each step size (1h, 6h, 12h, 24h):")
    print("   - Calculate total buckets: (30 days * 24h) / hours_per_bucket")
    print("   - Estimate events per bucket using current event rate")
    print("   - Evaluate manageability score")
    print("5. Recommend step size with highest granularity that meets target (<1000 buckets)")


if __name__ == "__main__":
    main()