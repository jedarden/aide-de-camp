#!/usr/bin/env python3
"""
Calculate deployment failure pattern statistics.
Analyzes frequency, time distribution, service context, and correlations.
"""

import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional
import statistics


def load_json_file(filepath: Path) -> Dict:
    """Load JSON file safely."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return {}


def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse various timestamp formats to datetime object (always returns UTC-aware)."""
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str, fmt)
            # If naive, treat as UTC
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            # If aware, convert to UTC
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue

    print(f"Warning: Could not parse timestamp: {ts_str}")
    return None


def calculate_pattern_statistics(parsed_data: Dict, classified_failures: Dict) -> Dict[str, Any]:
    """Calculate comprehensive statistics for each pattern type."""

    # Initialize statistics structure
    stats = {
        "generated_at": datetime.now().isoformat(),
        "analysis_period": {
            "start": None,
            "end": None,
            "days": 30
        },
        "patterns": {},
        "cross_pattern_analysis": {},
        "temporal_correlations": []
    }

    # Get all deployment events from parsed data
    all_events = []

    # Extract events from the parsed data files
    for filename, file_data in parsed_data.get("files", {}).items():
        if "timeline" in file_data:
            timeline = file_data["timeline"]
            all_events.extend(timeline)

    # Set analysis period
    if all_events:
        timestamps = []
        for event in all_events:
            ts = event.get("timestamp")
            if ts:
                parsed_ts = parse_timestamp(ts)
                if parsed_ts:
                    timestamps.append(parsed_ts)

        if timestamps:
            stats["analysis_period"]["start"] = min(timestamps).isoformat()
            stats["analysis_period"]["end"] = max(timestamps).isoformat()
            if len(timestamps) > 1:
                stats["analysis_period"]["days"] = (max(timestamps) - min(timestamps)).days

    # Process each pattern type from classified failures
    pattern_definitions = {p["name"]: p for p in classified_failures.get("pattern_definitions", [])}

    for pattern_def in classified_failures.get("pattern_definitions", []):
        pattern_name = pattern_def["name"]
        pattern_desc = pattern_def["description"]
        pattern_severity = pattern_def["severity"]

        # Find all failures for this pattern
        pattern_failures = [
            f for f in classified_failures.get("classified_failures", [])
            if f.get("pattern_type") == pattern_name
        ]

        # Calculate statistics
        occurrence_count = len(pattern_failures)

        if occurrence_count == 0:
            # Still include pattern with zero occurrences
            stats["patterns"][pattern_name] = {
                "description": pattern_desc,
                "severity": pattern_severity,
                "occurrence_count": 0,
                "frequency_per_day": 0,
                "services_affected": [],
                "images_affected": [],
                "time_distribution": {
                    "first_occurrence": None,
                    "last_occurrence": None,
                    "dates_with_occurrences": [],
                    "consecutive_days": 0
                },
                "temporal_clusters": []
            }
            continue

        # Service breakdown
        services = defaultdict(int)
        images = defaultdict(int)
        timestamps_parsed = []
        dates_seen = set()

        for failure in pattern_failures:
            service = failure.get("service", "unknown")
            image = failure.get("image", "unknown")
            timestamp_str = failure.get("timestamp") or failure.get("date")

            services[service] += 1
            images[image] += 1

            if timestamp_str:
                parsed_ts = parse_timestamp(timestamp_str)
                if parsed_ts:
                    timestamps_parsed.append(parsed_ts)
                    dates_seen.add(parsed_ts.date())

        # Time distribution analysis
        time_dist = {
            "first_occurrence": None,
            "last_occurrence": None,
            "dates_with_occurrences": sorted(list(dates_seen)),
            "consecutive_days": 0,
            "span_days": 0
        }

        if timestamps_parsed:
            timestamps_parsed.sort()
            time_dist["first_occurrence"] = timestamps_parsed[0].isoformat()
            time_dist["last_occurrence"] = timestamps_parsed[-1].isoformat()

            if len(timestamps_parsed) > 1:
                time_dist["span_days"] = (timestamps_parsed[-1] - timestamps_parsed[0]).days

            # Calculate consecutive days
            sorted_dates = sorted(list(dates_seen))
            consecutive = 1
            max_consecutive = 1
            for i in range(1, len(sorted_dates)):
                if (sorted_dates[i] - sorted_dates[i-1]).days == 1:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 1
            time_dist["consecutive_days"] = max_consecutive

        # Frequency metrics
        days_in_period = stats["analysis_period"]["days"]
        frequency_per_day = occurrence_count / days_in_period if days_in_period > 0 else 0

        # Find temporal clusters (group events within 1 hour)
        temporal_clusters = []
        if timestamps_parsed:
            timestamps_parsed.sort()
            current_cluster = [timestamps_parsed[0]]

            for ts in timestamps_parsed[1:]:
                if (ts - current_cluster[0]).total_seconds() <= 3600:  # Within 1 hour
                    current_cluster.append(ts)
                else:
                    if len(current_cluster) > 1:
                        temporal_clusters.append({
                            "start": current_cluster[0].isoformat(),
                            "end": current_cluster[-1].isoformat(),
                            "count": len(current_cluster),
                            "duration_seconds": (current_cluster[-1] - current_cluster[0]).total_seconds()
                        })
                    current_cluster = [ts]

            if len(current_cluster) > 1:
                temporal_clusters.append({
                    "start": current_cluster[0].isoformat(),
                    "end": current_cluster[-1].isoformat(),
                    "count": len(current_cluster),
                    "duration_seconds": (current_cluster[-1] - current_cluster[0]).total_seconds()
                })

        stats["patterns"][pattern_name] = {
            "description": pattern_desc,
            "severity": pattern_severity,
            "occurrence_count": occurrence_count,
            "frequency_per_day": round(frequency_per_day, 3),
            "services_affected": dict(services),
            "images_affected": dict(images),
            "time_distribution": time_dist,
            "temporal_clusters": temporal_clusters
        }

    # Cross-pattern analysis
    stats["cross_pattern_analysis"] = analyze_cross_patterns(classified_failures)

    # Temporal correlations between deployment and failure spikes
    stats["temporal_correlations"] = find_temporal_correlations(all_events, classified_failures)

    # Overall summary
    stats["summary"] = generate_summary(stats, classified_failures)

    return stats


def analyze_cross_patterns(classified_failures: Dict) -> Dict:
    """Analyze relationships between different pattern types."""

    failures = classified_failures.get("classified_failures", [])

    # Service-pattern matrix
    service_pattern_matrix = defaultdict(lambda: defaultdict(int))

    for failure in failures:
        service = failure.get("service", "unknown")
        pattern = failure.get("pattern_type", "unknown")
        service_pattern_matrix[service][pattern] += 1

    # Find services with multiple pattern types
    multi_pattern_services = {
        service: dict(patterns)
        for service, patterns in service_pattern_matrix.items()
        if len(patterns) > 1
    }

    return {
        "services_with_multiple_patterns": multi_pattern_services,
        "pattern_co_occurrences": analyze_pattern_co_occurrences(failures)
    }


def analyze_pattern_co_occurrences(failures: List[Dict]) -> List[Dict]:
    """Find patterns that occur together on same day/service."""

    co_occurrences = []

    # Group by service and date
    service_date_groups = defaultdict(list)
    for failure in failures:
        service = failure.get("service", "unknown")
        date = failure.get("date")
        if date:
            service_date_groups[(service, date)].append(failure)

    # Find groups with multiple patterns
    for (service, date), group_failures in service_date_groups.items():
        patterns_in_group = set(f.get("pattern_type") for f in group_failures)
        if len(patterns_in_group) > 1:
            co_occurrences.append({
                "service": service,
                "date": date,
                "patterns": list(patterns_in_group),
                "count": len(group_failures)
            })

    return co_occurrences


def find_temporal_correlations(all_events: List[Dict], classified_failures: Dict) -> List[Dict]:
    """Find correlations between deployment activity and failure spikes."""

    correlations = []

    # Get deployment events
    deployment_events = [
        e for e in all_events
        if e.get("event_type") in ["deployment_rollout", "deployment_rollback", "image_bump"]
    ]

    # Get failure events
    failure_events = classified_failures.get("classified_failures", [])

    # Look for failures within time windows of deployments
    for deployment in deployment_events:
        deploy_ts = parse_timestamp(deployment.get("timestamp"))
        if not deploy_ts:
            continue

        # Check for failures within 24 hours after deployment
        nearby_failures = []
        for failure in failure_events:
            fail_ts = parse_timestamp(failure.get("timestamp") or failure.get("date"))
            if not fail_ts:
                continue

            time_diff = (fail_ts - deploy_ts).total_seconds()

            # Within 24 hours, and failure is after deployment
            if 0 <= time_diff <= 86400:  # 24 hours = 86400 seconds
                nearby_failures.append({
                    "failure": failure,
                    "time_diff_hours": round(time_diff / 3600, 2),
                    "pattern_type": failure.get("pattern_type")
                })

        if nearby_failures:
            correlations.append({
                "deployment_timestamp": deployment.get("timestamp"),
                "service": deployment.get("service"),
                "deployment_event_type": deployment.get("event_type"),
                "nearby_failures": nearby_failures,
                "failure_count": len(nearby_failures),
                "patterns_seen": list(set(f["pattern_type"] for f in nearby_failures))
            })

    return correlations


def generate_summary(stats: Dict, classified_failures: Dict) -> Dict:
    """Generate overall summary statistics."""

    patterns = stats.get("patterns", {})

    total_occurrences = sum(p["occurrence_count"] for p in patterns.values())

    # Severity breakdown
    severity_counts = defaultdict(int)
    for pattern in patterns.values():
        severity_counts[pattern["severity"]] += pattern["occurrence_count"]

    # Most affected services
    all_services = defaultdict(int)
    for pattern in patterns.values():
        services_affected = pattern.get("services_affected", {})
        # Handle both dict and list formats
        if isinstance(services_affected, dict):
            for service, count in services_affected.items():
                all_services[service] += count
        elif isinstance(services_affected, list):
            for service in services_affected:
                all_services[service] += 1

    # Most common images in failures
    all_images = defaultdict(int)
    for pattern in patterns.values():
        images_affected = pattern.get("images_affected", {})
        # Handle both dict and list formats
        if isinstance(images_affected, dict):
            for image, count in images_affected.items():
                all_images[image] += count
        elif isinstance(images_affected, list):
            for image in images_affected:
                all_images[image] += 1

    # Temporal analysis
    patterns_with_time_distribution = [
        name for name, p in patterns.items()
        if p.get("time_distribution", {}).get("dates_with_occurrences")
    ]

    return {
        "total_pattern_occurrences": total_occurrences,
        "patterns_with_occurrences": len([p for p in patterns.values() if p["occurrence_count"] > 0]),
        "total_patterns_tracked": len(patterns),
        "severity_distribution": dict(severity_counts),
        "top_affected_services": dict(sorted(all_services.items(), key=lambda x: x[1], reverse=True)[:5]),
        "top_affected_images": dict(sorted(all_images.items(), key=lambda x: x[1], reverse=True)[:5]),
        "patterns_with_time_data": len(patterns_with_time_distribution),
        "temporal_correlation_count": len(stats.get("temporal_correlations", []))
    }


def main():
    """Main execution."""

    # Define paths
    base_dir = Path("/home/coding/aide-de-camp/docs/research/deployment-data")
    parsed_data_path = base_dir / "parsed-data.json"
    classified_failures_path = base_dir / "classified-failures.json"
    output_path = base_dir / "pattern-statistics.json"

    print("Loading data files...")
    parsed_data = load_json_file(parsed_data_path)
    classified_failures = load_json_file(classified_failures_path)

    if not parsed_data:
        print(f"Error: Could not load parsed data from {parsed_data_path}")
        return

    if not classified_failures:
        print(f"Error: Could not load classified failures from {classified_failures_path}")
        return

    print("Calculating pattern statistics...")
    stats = calculate_pattern_statistics(parsed_data, classified_failures)

    print(f"Writing statistics to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(stats, f, indent=2)

    print("\nPattern Statistics Summary:")
    print("=" * 50)
    summary = stats.get("summary", {})
    print(f"Total pattern occurrences: {summary.get('total_pattern_occurrences', 0)}")
    print(f"Patterns with occurrences: {summary.get('patterns_with_occurrences', 0)}")
    print(f"Total patterns tracked: {summary.get('total_patterns_tracked', 0)}")
    print(f"Severity distribution: {summary.get('severity_distribution', {})}")
    print(f"Top affected services: {summary.get('top_affected_services', {})}")
    print(f"Temporal correlations found: {summary.get('temporal_correlation_count', 0)}")

    print("\nPer-Pattern Breakdown:")
    print("=" * 50)
    for pattern_name, pattern_stats in stats.get("patterns", {}).items():
        if pattern_stats["occurrence_count"] > 0:
            print(f"\n{pattern_name} ({pattern_stats['severity']}):")
            print(f"  Occurrences: {pattern_stats['occurrence_count']}")
            print(f"  Frequency: {pattern_stats['frequency_per_day']}/day")
            print(f"  Services: {pattern_stats['services_affected']}")
            if pattern_stats.get('temporal_clusters'):
                print(f"  Temporal clusters: {len(pattern_stats['temporal_clusters'])}")

    print(f"\n✅ Statistics saved to {output_path}")


if __name__ == "__main__":
    main()