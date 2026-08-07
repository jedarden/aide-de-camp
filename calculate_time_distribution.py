#!/usr/bin/env python3
"""
Calculate time distribution statistics for pattern categories.

For each category, this script computes:
- Daily/weekly failure counts
- Time clusters (periods with high failure density)
- Temporal statistics: first occurrence, last occurrence, average gap between failures
"""

import json
import re
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any
import statistics

def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime object."""
    if not ts_str:
        return None

    # Handle various ISO 8601 formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",           # 2026-08-06T17:27:54Z
        "%Y-%m-%dT%H:%M:%S.%fZ",        # 2026-08-06T17:27:54.123Z
        "%Y-%m-%dT%H:%M:%S%z",          # 2026-08-06T17:27:54+00:00
        "%Y-%m-%dT%H:%M:%S.%f%z",       # 2026-08-06T17:27:54.123+00:00
        "%Y-%m-%dT%H:%M:%S.%f",         # 2026-07-28T20:23:24.872959658-04:00 (without timezone marker)
        "%Y-%m-%d %H:%M:%S",            # 2026-08-06 17:27:54
        "%Y-%m-%d",                     # 2026-08-06
    ]

    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except (ValueError, TypeError):
            continue

    return None

def calculate_gap_stats(timestamps: List[datetime]) -> Dict[str, Any]:
    """Calculate statistics about gaps between consecutive failures."""
    if len(timestamps) < 2:
        return {
            "average_gap_seconds": None,
            "median_gap_seconds": None,
            "min_gap_seconds": None,
            "max_gap_seconds": None,
            "stddev_gap_seconds": None,
        }

    # Sort timestamps
    sorted_ts = sorted(timestamps)

    # Calculate gaps
    gaps = [(sorted_ts[i+1] - sorted_ts[i]).total_seconds()
            for i in range(len(sorted_ts) - 1)]

    return {
        "average_gap_seconds": statistics.mean(gaps),
        "median_gap_seconds": statistics.median(gaps),
        "min_gap_seconds": min(gaps),
        "max_gap_seconds": max(gaps),
        "stddev_gap_seconds": statistics.stdev(gaps) if len(gaps) > 1 else 0,
    }

def identify_time_clusters(timestamps: List[datetime], window_hours: int = 6, threshold_density: float = 2.0) -> List[Dict[str, Any]]:
    """
    Identify time clusters - periods with high failure density.

    Args:
        timestamps: List of failure timestamps
        window_hours: Time window to consider for clustering (default: 6 hours)
        threshold_density: Failures per hour threshold (default: 2.0 per hour)

    Returns:
        List of cluster descriptions with start, end, duration, and count
    """
    if not timestamps:
        return []

    sorted_ts = sorted(timestamps)

    # Sliding window approach
    clusters = []
    window_start_idx = 0
    window_duration = timedelta(hours=window_hours)

    for i, current_ts in enumerate(sorted_ts):
        # Find end of window
        window_end = current_ts + window_duration

        # Count failures in window
        window_count = 0
        for ts in sorted_ts[window_start_idx:]:
            if ts <= window_end:
                window_count += 1
            else:
                break

        # Calculate density (failures per hour)
        density = window_count / window_hours if window_hours > 0 else 0

        # Check if this meets threshold
        if density >= threshold_density and window_count >= 2:  # At least 2 failures
            # Find cluster extent
            cluster_start = current_ts
            cluster_end = current_ts

            # Expand cluster to include all failures within threshold density
            for ts in sorted_ts[window_start_idx:]:
                if ts <= window_end:
                    cluster_end = max(cluster_end, ts)
                else:
                    break

            # Only add if not overlapping with last cluster
            last_cluster_end = None
            if clusters:
                last_cluster_end = datetime.strptime(clusters[-1]['end'], "%Y-%m-%dT%H:%M:%SZ")

            if not clusters or cluster_start > last_cluster_end:
                clusters.append({
                    'start': cluster_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    'end': cluster_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    'duration_hours': (cluster_end - cluster_start).total_seconds() / 3600,
                    'failure_count': window_count,
                    'density_per_hour': density,
                })

    return clusters

def calculate_daily_weekly_counts(timestamps: List[datetime]) -> Dict[str, Any]:
    """Calculate daily and weekly failure counts."""
    daily_counts = defaultdict(int)
    weekly_counts = defaultdict(int)

    for ts in timestamps:
        if not ts:
            continue

        # Daily count (by date)
        date_key = ts.date().isoformat()
        daily_counts[date_key] += 1

        # Weekly count (by ISO week)
        year, week, _ = ts.isocalendar()
        week_key = f"{year}-W{week:02d}"
        weekly_counts[week_key] += 1

    return {
        "daily_counts": dict(daily_counts),
        "weekly_counts": dict(weekly_counts),
    }

def calculate_category_statistics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate comprehensive time distribution statistics for a category."""
    if not records:
        return {
            "total_failures": 0,
            "timestamps_analyzed": 0,
            "error": "No records to analyze"
        }

    # Extract and parse timestamps
    timestamps = []
    parse_errors = 0

    for record in records:
        ts_str = record.get('timestamp')
        if ts_str:
            ts = parse_timestamp(ts_str)
            if ts:
                timestamps.append(ts)
            else:
                parse_errors += 1
        else:
            parse_errors += 1

    if not timestamps:
        return {
            "total_failures": len(records),
            "timestamps_analyzed": 0,
            "parse_errors": parse_errors,
            "error": "No valid timestamps found"
        }

    # Sort timestamps
    timestamps.sort()

    # Calculate statistics
    daily_weekly = calculate_daily_weekly_counts(timestamps)
    gap_stats = calculate_gap_stats(timestamps)
    clusters = identify_time_clusters(timestamps)

    return {
        "total_failures": len(records),
        "timestamps_analyzed": len(timestamps),
        "parse_errors": parse_errors,
        "time_range": {
            "first_occurrence": timestamps[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_occurrence": timestamps[-1].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "span_days": (timestamps[-1] - timestamps[0]).days,
        },
        "gap_statistics": gap_stats,
        "daily_weekly_counts": daily_weekly,
        "time_clusters": {
            "clusters_found": len(clusters),
            "clusters": clusters,
        },
    }

def extract_timestamp_from_record(record: Dict[str, Any]) -> datetime:
    """Extract timestamp from a failure record, checking multiple fields."""
    # Priority order: timestamp field > message field > other fields
    if 'timestamp' in record and record['timestamp']:
        ts = parse_timestamp(record['timestamp'])
        if ts:
            return ts

    if 'message' in record and record['message']:
        # Extract ISO 8601 timestamps from message text
        # Match ISO 8601 patterns in messages - improved pattern
        patterns = [
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2})',  # With microseconds and timezone
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})',         # With timezone
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)',                    # UTC with Z and microseconds
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)',                           # UTC with Z
        ]
        for pattern in patterns:
            match = re.search(pattern, record['message'])
            if match:
                ts_str = match.group(1)
                # Handle the timezone offset format specifically
                try:
                    # Try parsing with fromisoformat (handles timezone offsets better)
                    if ts_str.endswith('Z'):
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    else:
                        ts = datetime.fromisoformat(ts_str)
                    return ts
                except ValueError:
                    # Fall back to parse_timestamp
                    ts = parse_timestamp(ts_str)
                    if ts:
                        return ts

    return None

def main():
    # Load validated dataset
    print("Loading validated dataset...")
    with open('/home/coding/aide-de-camp/pattern-category-frequency-stats.json', 'r') as f:
        dataset = json.load(f)

    categories_data = dataset.get('categories', {})

    print(f"Analyzing {len(categories_data)} categories...")

    # Calculate statistics for each category
    results = {}

    for category_name, category_info in categories_data.items():
        print(f"Processing category: {category_name}")

        # Get sample failures from the category
        sample_failures = category_info.get('sample_failures', [])

        if not sample_failures:
            print(f"  No sample failures found for {category_name}")
            results[category_name] = {
                "total_failures": 0,
                "timestamps_analyzed": 0,
                "error": "No sample failures available"
            }
            continue

        # Extract timestamps from sample failures
        records_with_timestamps = []
        for failure in sample_failures:
            ts = extract_timestamp_from_record(failure)
            if ts:
                records_with_timestamps.append({
                    'timestamp': ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    'raw_record': failure
                })

        print(f"  Found {len(records_with_timestamps)} timestamps out of {len(sample_failures)} records")

        # Prepare records for statistics calculation
        records_for_stats = [{'timestamp': r['timestamp']} for r in records_with_timestamps]

        category_stats = calculate_category_statistics(records_for_stats)

        # Add category metadata
        results[category_name] = {
            **category_stats,
            "category_info": {
                "description": category_info.get('description', ''),
                "severity": category_info.get('severity', ''),
                "occurrence_count": category_info.get('occurrence_count', 0)
            },
        }

    # Prepare output
    output = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "analysis_type": "time_distribution_statistics",
        "total_categories_analyzed": len(results),
        "categories": results,
    }

    # Write output
    output_file = '/home/coding/aide-de-camp/time-distribution-statistics.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Time distribution statistics written to {output_file}")

    # Print summary
    print("\n" + "="*60)
    print("TIME DISTRIBUTION SUMMARY")
    print("="*60)

    for category_name, stats in results.items():
        if stats.get('error'):
            print(f"\n{category_name}: ERROR - {stats['error']}")
            continue

        print(f"\n{category_name}:")
        print(f"  Total failures: {stats['total_failures']}")
        print(f"  Timestamps analyzed: {stats['timestamps_analyzed']}")

        if 'time_range' in stats:
            tr = stats['time_range']
            print(f"  Time span: {tr['first_occurrence']} to {tr['last_occurrence']} ({tr['span_days']} days)")

        if 'time_clusters' in stats:
            tc = stats['time_clusters']
            print(f"  Time clusters found: {tc['clusters_found']}")
            for i, cluster in enumerate(tc['clusters'][:3], 1):  # Show top 3
                print(f"    Cluster {i}: {cluster['start']} to {cluster['end']}")
                print(f"      Duration: {cluster['duration_hours']:.1f}h, "
                      f"Failures: {cluster['failure_count']}, "
                      f"Density: {cluster['density_per_hour']:.2f}/h")

        if 'gap_statistics' in stats and stats['gap_statistics']['average_gap_seconds']:
            gs = stats['gap_statistics']
            print(f"  Average gap: {gs['average_gap_seconds']/3600:.2f} hours")
            print(f"  Median gap: {gs['median_gap_seconds']/3600:.2f} hours")

if __name__ == '__main__':
    main()
