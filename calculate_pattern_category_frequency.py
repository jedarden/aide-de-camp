#!/usr/bin/env python3
"""
Calculate comprehensive frequency statistics by pattern category.

This script analyzes categorized failures from adc-c2mam and generates:
- Total count of occurrences per pattern category
- Distribution by service (which services had which failures)
- Image/version context (what images/versions were involved)
- Time distribution (how failures spread across 30-day timeline)
"""

import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Any, Optional
import statistics


def load_categorized_failures(filepath: Path) -> Dict:
    """Load categorized failures JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return {}


def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse various timestamp formats to datetime object (always returns UTC-aware)."""
    if not ts_str:
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%f",  # Handle timestamps without timezone
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
        except (ValueError, AttributeError):
            continue

    return None


def extract_service_name(failure: Dict) -> str:
    """Extract service name from failure record using multiple possible fields."""
    # Try different fields that might contain service name
    for field in ['namespace', 'service', 'app', 'kubernetes.pod_namespace']:
        value = failure.get(field)
        if value and isinstance(value, str) and value not in ['N/A', '', 'unknown']:
            return value
    return 'unknown'


def extract_image_name(failure: Dict) -> str:
    """Extract image name from failure record."""
    # Try different fields that might contain image information
    for field in ['image', 'kubernetes.container_image', 'kubernetes.container_image_id']:
        value = failure.get(field)
        if value and isinstance(value, str) and value not in ['N/A', '', 'unknown']:
            # Clean up image name - remove long IDs and hashes
            if ':' in value and '@' in value:
                # Has both tag and digest - use tag only
                return value.split('@')[0]
            elif '@' in value:
                # Has digest - convert to short form
                parts = value.split(':')
                if len(parts) > 1:
                    digest = parts[1].split('@')[0][:12]  # First 12 chars of digest
                    return f"{parts[0]}:{digest}"
            return value
    return 'unknown'


def extract_timestamp(failure: Dict) -> Optional[datetime]:
    """Extract timestamp from failure record."""
    # Try different timestamp fields
    for field in ['timestamp', '_time', 'creation_timestamp', 'data_collection_timestamp']:
        value = failure.get(field)
        if value:
            parsed = parse_timestamp(str(value))
            if parsed:
                return parsed
    return None


def calculate_category_statistics(categorized_data: Dict) -> Dict[str, Any]:
    """Calculate comprehensive statistics for each pattern category."""

    failures = categorized_data.get('failures', [])
    category_metadata = categorized_data.get('categories', {})

    # Initialize statistics structure
    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_summary": {
            "total_records_processed": categorized_data.get('total_records', 0),
            "categorized_failures": categorized_data.get('categorized_count', 0),
            "uncategorized_failures": categorized_data.get('uncategorized_count', 0),
            "unique_pattern_categories": len(category_metadata)
        },
        "categories": {},
        "cross_category_analysis": {},
        "temporal_analysis": {}
    }

    # Group failures by pattern category
    category_failures = defaultdict(list)
    for failure in failures:
        category = failure.get('pattern_category', 'uncategorized')
        category_failures[category].append(failure)

    # Process each category
    for category_name, category_meta in category_metadata.items():
        if category_name == 'uncategorized':
            continue  # Skip uncategorized for detailed analysis

        failures_in_category = category_failures.get(category_name, [])

        # Calculate statistics for this category
        category_stats = calculate_single_category_stats(
            category_name,
            failures_in_category,
            category_meta
        )

        stats["categories"][category_name] = category_stats

    # Cross-category analysis
    stats["cross_category_analysis"] = analyze_cross_category_patterns(category_failures)

    # Temporal analysis
    stats["temporal_analysis"] = analyze_temporal_patterns(category_failures)

    return stats


def calculate_single_category_stats(
    category_name: str,
    failures: List[Dict],
    category_metadata: Dict
) -> Dict[str, Any]:
    """Calculate detailed statistics for a single pattern category."""

    occurrence_count = len(failures)

    # Initialize result structure
    stats = {
        "description": category_metadata.get('description', ''),
        "severity": category_metadata.get('severity', ''),
        "occurrence_count": occurrence_count,
        "percentage_of_categorized": 0.0,  # Will be calculated at higher level
        "service_distribution": {},
        "image_distribution": {},
        "time_distribution": {
            "first_occurrence": None,
            "last_occurrence": None,
            "dates_with_occurrences": [],
            "occurrences_by_date": {},
            "consecutive_days": 0,
            "span_days": 0,
            "average_occurrences_per_day": 0.0
        },
        "error_type_distribution": {},
        "sample_failures": []
    }

    if occurrence_count == 0:
        return stats

    # Service distribution
    service_counts = defaultdict(int)
    image_counts = defaultdict(int)
    error_type_counts = defaultdict(int)

    # Parse timestamps and collect dates
    timestamps_parsed = []
    dates_seen = set()
    occurrences_by_date = defaultdict(int)

    for failure in failures:
        # Extract service
        service = extract_service_name(failure)
        service_counts[service] += 1

        # Extract image
        image = extract_image_name(failure)
        image_counts[image] += 1

        # Extract error type
        error_type = failure.get('error_type', 'unknown')
        error_type_counts[error_type] += 1

        # Extract and parse timestamp
        ts = extract_timestamp(failure)
        if ts:
            timestamps_parsed.append(ts)
            date_str = ts.date().isoformat()
            dates_seen.add(ts.date())
            occurrences_by_date[date_str] += 1

    # Build service distribution
    stats["service_distribution"] = dict(sorted(
        service_counts.items(),
        key=lambda x: x[1],
        reverse=True
    ))

    # Build image distribution (top 10)
    sorted_images = sorted(image_counts.items(), key=lambda x: x[1], reverse=True)
    stats["image_distribution"] = dict(sorted_images[:10])

    # Build error type distribution
    stats["error_type_distribution"] = dict(sorted(
        error_type_counts.items(),
        key=lambda x: x[1],
        reverse=True
    ))

    # Time distribution analysis
    if timestamps_parsed:
        timestamps_parsed.sort()
        stats["time_distribution"]["first_occurrence"] = timestamps_parsed[0].isoformat()
        stats["time_distribution"]["last_occurrence"] = timestamps_parsed[-1].isoformat()

        # Calculate span
        if len(timestamps_parsed) > 1:
            stats["time_distribution"]["span_days"] = (
                timestamps_parsed[-1] - timestamps_parsed[0]
            ).days

        # Dates with occurrences
        sorted_dates = sorted(dates_seen)
        stats["time_distribution"]["dates_with_occurrences"] = [
            d.isoformat() for d in sorted_dates
        ]

        # Occurrences by date
        stats["time_distribution"]["occurrences_by_date"] = dict(
            sorted(occurrences_by_date.items())
        )

        # Calculate consecutive days
        max_consecutive = 1
        current_consecutive = 1
        for i in range(1, len(sorted_dates)):
            if (sorted_dates[i] - sorted_dates[i-1]).days == 1:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1
        stats["time_distribution"]["consecutive_days"] = max_consecutive

        # Average occurrences per day
        days_with_failures = len(dates_seen)
        if days_with_failures > 0:
            stats["time_distribution"]["average_occurrences_per_day"] = round(
                occurrence_count / days_with_failures, 2
            )

    # Sample failures (first 5)
    stats["sample_failures"] = failures[:5]

    return stats


def analyze_cross_category_patterns(category_failures: Dict[str, List[Dict]]) -> Dict:
    """Analyze patterns across categories."""

    # Service-category matrix
    service_category_matrix = defaultdict(lambda: defaultdict(int))

    for category, failures in category_failures.items():
        if category == 'uncategorized':
            continue
        for failure in failures:
            service = extract_service_name(failure)
            service_category_matrix[service][category] += 1

    # Find services with multiple failure categories
    multi_category_services = {
        service: dict(categories)
        for service, categories in service_category_matrix.items()
        if len(categories) > 1
    }

    # Most affected services across all categories
    all_service_counts = defaultdict(int)
    for service, categories in service_category_matrix.items():
        all_service_counts[service] = sum(categories.values())

    return {
        "services_with_multiple_categories": multi_category_services,
        "most_affected_services_overall": dict(sorted(
            all_service_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10])
    }


def analyze_temporal_patterns(category_failures: Dict[str, List[Dict]]) -> Dict:
    """Analyze temporal patterns across categories."""

    # Daily failure counts by category
    daily_counts = defaultdict(lambda: defaultdict(int))

    for category, failures in category_failures.items():
        if category == 'uncategorized':
            continue
        for failure in failures:
            ts = extract_timestamp(failure)
            if ts:
                date_str = ts.date().isoformat()
                daily_counts[date_str][category] += 1

    # Sort by date
    sorted_daily_counts = dict(sorted(daily_counts.items()))

    # Find peak failure days
    daily_totals = {
        date: sum(categories.values())
        for date, categories in sorted_daily_counts.items()
    }

    peak_days = sorted(
        daily_totals.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    return {
        "daily_breakdown": sorted_daily_counts,
        "peak_failure_days": [
            {"date": date, "total_count": count}
            for date, count in peak_days
        ]
    }


def main():
    """Main execution."""

    # Define paths
    base_dir = Path("/home/coding/aide-de-camp")
    categorized_failures_path = base_dir / "categorized-failures-report.json"
    output_path = base_dir / "pattern-category-frequency-stats.json"

    print("Loading categorized failures...")
    categorized_data = load_categorized_failures(categorized_failures_path)

    if not categorized_data:
        print(f"Error: Could not load categorized failures from {categorized_failures_path}")
        return

    print("Calculating pattern category frequency statistics...")
    stats = calculate_category_statistics(categorized_data)

    # Calculate percentages
    total_categorized = categorized_data.get('categorized_count', 0)
    if total_categorized > 0:
        for category, cat_stats in stats.get("categories", {}).items():
            cat_stats["percentage_of_categorized"] = round(
                (cat_stats["occurrence_count"] / total_categorized) * 100, 2
            )

    print(f"Writing statistics to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(stats, f, indent=2)

    print("\n" + "=" * 60)
    print("PATTERN CATEGORY FREQUENCY STATISTICS SUMMARY")
    print("=" * 60)

    summary = stats.get("analysis_summary", {})
    print(f"\nTotal records processed: {summary.get('total_records_processed', 0)}")
    print(f"Categorized failures: {summary.get('categorized_failures', 0)}")
    print(f"Uncategorized failures: {summary.get('uncategorized_failures', 0)}")
    print(f"Unique pattern categories: {summary.get('unique_pattern_categories', 0)}")

    print("\n" + "-" * 60)
    print("PER-CATEGORY BREAKDOWN")
    print("-" * 60)

    for category_name, cat_stats in stats.get("categories", {}).items():
        print(f"\n{category_name} ({cat_stats['severity']}):")
        print(f"  Description: {cat_stats['description']}")
        print(f"  Occurrences: {cat_stats['occurrence_count']}")
        print(f"  % of categorized: {cat_stats['percentage_of_categorized']}%")

        if cat_stats['service_distribution']:
            print(f"  Services affected: {list(cat_stats['service_distribution'].keys())[:5]}")

        if cat_stats['image_distribution']:
            top_images = list(cat_stats['image_distribution'].keys())[:3]
            print(f"  Top images: {top_images}")

        time_dist = cat_stats.get('time_distribution', {})
        if time_dist.get('first_occurrence'):
            print(f"  Time span: {time_dist.get('first_occurrence', 'N/A')} to {time_dist.get('last_occurrence', 'N/A')}")
            print(f"  Days spanned: {time_dist.get('span_days', 0)}")

    print("\n" + "-" * 60)
    print("CROSS-CATEGORY ANALYSIS")
    print("-" * 60)

    cross_analysis = stats.get("cross_category_analysis", {})
    multi_cat_services = cross_analysis.get("services_with_multiple_categories", {})

    if multi_cat_services:
        print(f"\nServices with multiple failure categories:")
        for service, categories in multi_cat_services.items():
            print(f"  {service}: {categories}")
    else:
        print("\nNo services with multiple failure categories found.")

    top_services = cross_analysis.get("most_affected_services_overall", {})
    print(f"\nTop affected services overall:")
    for service, count in list(top_services.items())[:5]:
        print(f"  {service}: {count} failures")

    print("\n" + "-" * 60)
    print("TEMPORAL ANALYSIS")
    print("-" * 60)

    temporal = stats.get("temporal_analysis", {})
    peak_days = temporal.get("peak_failure_days", [])

    print(f"\nPeak failure days:")
    for day_info in peak_days:
        print(f"  {day_info['date']}: {day_info['total_count']} failures")

    print(f"\n✅ Statistics saved to {output_path}")


if __name__ == "__main__":
    main()