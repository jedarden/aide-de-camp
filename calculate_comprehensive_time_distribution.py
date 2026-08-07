#!/usr/bin/env python3
"""
Calculate comprehensive time distribution statistics for pattern categories.
This script parses the actual log files to extract ALL failures, not just samples.
"""

import json
import re
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any
import statistics

# Pattern categories and their error patterns
PATTERN_CATEGORIES = {
    "NetworkIssue": {
        "description": "Network allocation or connectivity problems",
        "patterns": [
            r"BrokenPipeError",
            r"\[Errno 32\] Broken pipe",
            r"\[Errno 104\] Connection reset by peer"
        ]
    },
    "RecordingFetchError": {
        "description": "Failed to fetch recordings from storage backend",
        "patterns": [
            r"recording fetch error",
            r"500.*recording"
        ]
    },
    "HTTPError": {
        "description": "HTTP error responses (4xx, 5xx)",
        "patterns": [
            r'http_(500|502|503|504)',  # Matches error_type field
            r'status (500|502|503|504)',  # Matches severity field
        ]
    },
    "DependencyTimeout": {
        "description": "Timeout connecting to dependent services",
        "patterns": [
            r"\[Errno 104\] Connection reset by peer",
            r"ConnectionResetError",
            r"timeout"
        ]
    },
    "DeploymentRollback": {
        "description": "Deployment was rolled back to previous version",
        "patterns": [
            r"rollback",
            r"rolled back"
        ]
    }
}

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
        "%Y-%m-%d %H:%M:%S",            # 2026-08-06 17:27:54
        "%Y-%m-%d",                     # 2026-08-06
    ]

    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except (ValueError, TypeError):
            continue

    return None

def extract_timestamp_from_log_entry(entry: Dict[str, Any]) -> datetime:
    """Extract timestamp from a log entry and normalize to UTC (naive datetime)."""
    # Try timestamp field first
    if 'timestamp' in entry and entry['timestamp']:
        ts = parse_timestamp(entry['timestamp'])
        if ts:
            # Convert to UTC and remove timezone info
            if ts.tzinfo is not None:
                ts = ts.astimezone(tz=None).replace(tzinfo=None)
            return ts

    # Try message field
    if 'message' in entry and entry['message']:
        # Extract ISO 8601 timestamps from message text
        patterns = [
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2})',
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})',
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)',
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)',
        ]
        for pattern in patterns:
            match = re.search(pattern, entry['message'])
            if match:
                ts_str = match.group(1)
                try:
                    if ts_str.endswith('Z'):
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    else:
                        ts = datetime.fromisoformat(ts_str)
                    # Convert to UTC and remove timezone info
                    if ts.tzinfo is not None:
                        ts = ts.astimezone(tz=None).replace(tzinfo=None)
                    return ts
                except ValueError:
                    ts = parse_timestamp(ts_str)
                    if ts:
                        # Convert to UTC and remove timezone info
                        if ts.tzinfo is not None:
                            ts = ts.astimezone(tz=None).replace(tzinfo=None)
                        return ts

    return None

def categorize_log_entry(entry: Dict[str, Any]) -> List[str]:
    """Categorize a log entry based on pattern matching and structured fields."""
    categories = []
    message = str(entry.get('message', ''))
    source = str(entry.get('source', ''))
    error_type = str(entry.get('error_type', ''))
    severity = str(entry.get('severity', ''))

    for category_name, category_info in PATTERN_CATEGORIES.items():
        for pattern in category_info['patterns']:
            # Check all relevant fields
            if (re.search(pattern, message, re.IGNORECASE) or
                re.search(pattern, source, re.IGNORECASE) or
                re.search(pattern, error_type, re.IGNORECASE) or
                re.search(pattern, severity, re.IGNORECASE)):
                categories.append(category_name)
                break

    return categories if categories else ['Uncategorized']

def parse_log_file(file_path: str) -> List[Dict[str, Any]]:
    """Parse a JSONL log file and extract entries with timestamps."""
    entries = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        timestamp = extract_timestamp_from_log_entry(entry)
                        if timestamp:
                            categories = categorize_log_entry(entry)
                            entries.append({
                                'timestamp': timestamp,
                                'categories': categories,
                                'raw_entry': entry
                            })
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        print(f"  File not found: {file_path}")

    return entries

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

    sorted_ts = sorted(timestamps)
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
    """Identify time clusters - periods with high failure density."""
    if not timestamps:
        return []

    # Ensure all timestamps are naive (no timezone info)
    normalized_ts = []
    for ts in timestamps:
        if ts.tzinfo is not None:
            # Convert to UTC and remove timezone info
            ts = ts.astimezone(tz=None).replace(tzinfo=None)
        normalized_ts.append(ts)

    sorted_ts = sorted(normalized_ts)

    # Sliding window approach
    clusters = []
    window_duration = timedelta(hours=window_hours)

    for i, current_ts in enumerate(sorted_ts):
        # Find end of window
        window_end = current_ts + window_duration

        # Count failures in window
        window_count = 0
        for ts in sorted_ts[i:]:
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
            for ts in sorted_ts[i:]:
                if ts <= window_end:
                    cluster_end = max(cluster_end, ts)
                else:
                    break

            # Only add if not overlapping with last cluster
            last_cluster_end = None
            if clusters:
                last_cluster_end_str = clusters[-1]['end'].replace('Z', '')
                last_cluster_end = datetime.strptime(last_cluster_end_str, "%Y-%m-%dT%H:%M:%S")

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
        "daily_counts": dict(sorted(daily_counts.items())),
        "weekly_counts": dict(sorted(weekly_counts.items())),
    }

def calculate_category_statistics(timestamps: List[datetime]) -> Dict[str, Any]:
    """Calculate comprehensive time distribution statistics for a category."""
    if not timestamps:
        return {
            "total_failures": 0,
            "timestamps_analyzed": 0,
            "error": "No timestamps to analyze"
        }

    # Sort timestamps
    timestamps.sort()

    # Calculate statistics
    daily_weekly = calculate_daily_weekly_counts(timestamps)
    gap_stats = calculate_gap_stats(timestamps)
    clusters = identify_time_clusters(timestamps)

    return {
        "total_failures": len(timestamps),
        "timestamps_analyzed": len(timestamps),
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

def main():
    """Main function to calculate comprehensive time distribution statistics."""

    # Parse log files
    print("Parsing log files to extract all failures with timestamps...")

    all_entries = []
    log_files = [
        'logs/pbx-web-parsed.jsonl',
        'logs/pbx-web-30day.jsonl'
    ]

    for log_file in log_files:
        print(f"  Processing {log_file}...")
        entries = parse_log_file(log_file)
        print(f"    Found {len(entries)} timestamped entries")
        all_entries.extend(entries)

    print(f"Total timestamped entries: {len(all_entries)}")

    # Group by category
    category_timestamps = defaultdict(list)
    for entry in all_entries:
        for category in entry['categories']:
            category_timestamps[category].append(entry['timestamp'])

    print(f"\nCategories found: {list(category_timestamps.keys())}")

    # Calculate statistics for each category
    results = {}

    for category_name, timestamps in category_timestamps.items():
        print(f"\nProcessing category: {category_name} ({len(timestamps)} failures)")

        category_stats = calculate_category_statistics(timestamps)

        # Add category metadata
        results[category_name] = {
            **category_stats,
            "category_info": PATTERN_CATEGORIES.get(category_name, {
                "description": "Uncategorized failures"
            }),
        }

    # Prepare output
    output = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "analysis_metadata": {
            "total_entries_parsed": len(all_entries),
            "log_files_processed": log_files,
            "categories_analyzed": len(results),
            "timezone_handling": "All timestamps normalized to UTC"
        },
        "categories": results,
    }

    # Write output
    output_file = 'comprehensive-time-distribution-statistics.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Comprehensive time distribution statistics written to {output_file}")

    # Print summary
    print("\n" + "="*60)
    print("COMPREHENSIVE TIME DISTRIBUTION SUMMARY")
    print("="*60)

    for category_name, stats in results.items():
        if stats.get('error'):
            print(f"\n{category_name}: ERROR - {stats['error']}")
            continue

        print(f"\n{category_name}:")
        print(f"  Total failures: {stats['total_failures']}")

        if 'time_range' in stats:
            tr = stats['time_range']
            print(f"  Time span: {tr['first_occurrence']} to {tr['last_occurrence']} ({tr['span_days']} days)")

        if 'daily_weekly_counts' in stats:
            dw = stats['daily_weekly_counts']
            if dw['daily_counts']:
                peak_day = max(dw['daily_counts'].items(), key=lambda x: x[1])
                print(f"  Peak day: {peak_day[0]} ({peak_day[1]} failures)")
                print(f"  Total unique days: {len(dw['daily_counts'])}")

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