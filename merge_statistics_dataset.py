#!/usr/bin/env python3
"""
Merge frequency statistics and time distribution into a structured dataset.
Combines outputs from adc-2082w (frequency) and adc-54lo8 (time distribution).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


def load_json_file(file_path: str) -> Dict[str, Any]:
    """Load JSON file with error handling."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        raise
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}")
        raise


def merge_category_stats(
    frequency_category: Dict[str, Any],
    time_category: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Merge frequency and time statistics for a single category."""

    if not time_category:
        # If no time data available, use frequency data only
        return {
            "description": frequency_category.get("description", "Unknown"),
            "severity": frequency_category.get("severity", "unknown"),
            "total_failures": frequency_category.get("occurrence_count", 0),
            "percentage_of_categorized": frequency_category.get("percentage_of_categorized", 0.0),
            "service_distribution": frequency_category.get("service_distribution", {}),
            "image_version_distribution": frequency_category.get("image_distribution", {}),
            "error_type_distribution": frequency_category.get("error_type_distribution", {}),
            "time_distribution": {
                "first_occurrence": None,
                "last_occurrence": None,
                "span_days": 0,
                "timestamps_analyzed": 0,
                "gap_statistics": None,
                "daily_weekly_counts": None,
                "time_clusters": None
            },
            "sample_failures": frequency_category.get("sample_failures", [])[:5]  # Limit samples
        }

    # Merge both datasets
    return {
        "description": frequency_category.get("description", time_category.get("category_info", {}).get("description", "Unknown")),
        "severity": frequency_category.get("severity", "unknown"),
        "total_failures": frequency_category.get("occurrence_count", 0),
        "percentage_of_categorized": frequency_category.get("percentage_of_categorized", 0.0),
        "service_distribution": frequency_category.get("service_distribution", {}),
        "image_version_distribution": frequency_category.get("image_distribution", {}),
        "error_type_distribution": frequency_category.get("error_type_distribution", {}),
        "time_distribution": {
            "first_occurrence": time_category.get("time_range", {}).get("first_occurrence"),
            "last_occurrence": time_category.get("time_range", {}).get("last_occurrence"),
            "span_days": time_category.get("time_range", {}).get("span_days", 0),
            "timestamps_analyzed": time_category.get("timestamps_analyzed", 0),
            "gap_statistics": {
                "average_gap_seconds": time_category.get("gap_statistics", {}).get("average_gap_seconds"),
                "median_gap_seconds": time_category.get("gap_statistics", {}).get("median_gap_seconds"),
                "min_gap_seconds": time_category.get("gap_statistics", {}).get("min_gap_seconds"),
                "max_gap_seconds": time_category.get("gap_statistics", {}).get("max_gap_seconds"),
                "stddev_gap_seconds": time_category.get("gap_statistics", {}).get("stddev_gap_seconds")
            },
            "daily_weekly_counts": {
                "daily_counts": time_category.get("daily_weekly_counts", {}).get("daily_counts", {}),
                "weekly_counts": time_category.get("daily_weekly_counts", {}).get("weekly_counts", {})
            },
            "time_clusters": {
                "clusters_found": time_category.get("time_clusters", {}).get("clusters_found", 0),
                "clusters": time_category.get("time_clusters", {}).get("clusters", [])
            }
        },
        "sample_failures": frequency_category.get("sample_failures", [])[:5]  # Limit samples
    }


def validate_completeness(merged_data: Dict[str, Any]) -> bool:
    """Validate that all categories have required fields."""
    required_fields = [
        "description", "severity", "total_failures",
        "service_distribution", "image_version_distribution",
        "error_type_distribution", "time_distribution", "sample_failures"
    ]

    missing_fields = []
    for category_name, category_data in merged_data["categories"].items():
        for field in required_fields:
            if field not in category_data:
                missing_fields.append(f"{category_name}.{field}")

    if missing_fields:
        print(f"Validation failed - missing fields: {missing_fields}")
        return False

    print(f"Validation passed - all {len(merged_data['categories'])} categories have required fields")
    return True


def create_merged_dataset(
    frequency_file: str,
    time_file: str,
    output_file: str
) -> Dict[str, Any]:
    """Create merged statistics dataset from frequency and time analysis."""

    print(f"Loading frequency statistics from: {frequency_file}")
    frequency_data = load_json_file(frequency_file)

    print(f"Loading time distribution from: {time_file}")
    time_data = load_json_file(time_file)

    print("Merging datasets...")
    merged_categories = {}

    # Get all unique categories from both datasets
    all_categories = set()
    all_categories.update(frequency_data.get("categories", {}).keys())
    all_categories.update(time_data.get("categories", {}).keys())

    for category in all_categories:
        freq_cat = frequency_data.get("categories", {}).get(category)
        time_cat = time_data.get("categories", {}).get(category)

        if freq_cat:
            merged_categories[category] = merge_category_stats(freq_cat, time_cat)
            print(f"  ✓ Merged {category}: {freq_cat.get('occurrence_count', 0)} occurrences")
        elif time_cat:
            # Category only in time data (e.g., Uncategorized)
            merged_categories[category] = {
                "description": time_cat.get("category_info", {}).get("description", "Unknown"),
                "severity": "unknown",
                "total_failures": time_cat.get("total_failures", 0),
                "percentage_of_categorized": 0.0,
                "service_distribution": {},
                "image_version_distribution": {},
                "error_type_distribution": {},
                "time_distribution": {
                    "first_occurrence": time_cat.get("time_range", {}).get("first_occurrence"),
                    "last_occurrence": time_cat.get("time_range", {}).get("last_occurrence"),
                    "span_days": time_cat.get("time_range", {}).get("span_days", 0),
                    "timestamps_analyzed": time_cat.get("timestamps_analyzed", 0),
                    "gap_statistics": time_cat.get("gap_statistics", {}),
                    "daily_weekly_counts": time_cat.get("daily_weekly_counts", {}),
                    "time_clusters": time_cat.get("time_clusters", {})
                },
                "sample_failures": []
            }
            print(f"  + Added {category} from time data: {time_cat.get('total_failures', 0)} failures")

    # Calculate summary statistics
    total_failures = sum(cat.get("total_failures", 0) for cat in merged_categories.values())
    categorized_failures = sum(
        cat.get("total_failures", 0)
        for cat in merged_categories.values()
        if cat.get("description") != "Uncategorized"
    )

    merged_dataset = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "generation_source": "adc-46mz4 - statistics aggregation",
            "source_files": {
                "frequency_statistics": frequency_file,
                "time_distribution": time_file
            },
            "frequency_analysis_timestamp": frequency_data.get("generated_at"),
            "time_analysis_timestamp": time_data.get("generated_at")
        },
        "summary": {
            "total_categories": len(merged_categories),
            "total_failures": total_failures,
            "categorized_failures": categorized_failures,
            "uncategorized_failures": total_failures - categorized_failures,
            "unique_services": len(set(
                svc
                for cat in merged_categories.values()
                for svc in cat.get("service_distribution", {}).keys()
            ))
        },
        "categories": merged_categories,
        "cross_category_analysis": {
            "services_with_multiple_categories": frequency_data.get("cross_category_analysis", {}).get("services_with_multiple_categories", {}),
            "most_affected_services": frequency_data.get("cross_category_analysis", {}).get("most_affected_services_overall", {})
        }
    }

    # Validate completeness
    if not validate_completeness(merged_dataset):
        raise ValueError("Merged dataset failed completeness validation")

    # Write output
    print(f"\nWriting merged dataset to: {output_file}")
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(merged_dataset, f, indent=2)

    # Print summary
    print("\n" + "="*60)
    print("STATISTICS DATASET AGGREGATION COMPLETE")
    print("="*60)
    print(f"Total categories: {merged_dataset['summary']['total_categories']}")
    print(f"Total failures: {merged_dataset['summary']['total_failures']}")
    print(f"Categorized failures: {merged_dataset['summary']['categorized_failures']}")
    print(f"Uncategorized failures: {merged_dataset['summary']['uncategorized_failures']}")
    print(f"Unique services affected: {merged_dataset['summary']['unique_services']}")
    print(f"Output file: {output_file}")
    print("="*60)

    return merged_dataset


if __name__ == "__main__":
    # Input files from child beads
    frequency_stats_file = "/home/coding/aide-de-camp/pattern-category-frequency-stats.json"
    time_stats_file = "/home/coding/aide-de-camp/comprehensive-time-distribution-statistics.json"

    # Output file (configurable via command line or default)
    import sys
    output_file = sys.argv[1] if len(sys.argv) > 1 else "/home/coding/aide-de-camp/aggregated-statistics-dataset.json"

    try:
        create_merged_dataset(frequency_stats_file, time_stats_file, output_file)
        print("\n✓ Statistics dataset aggregation completed successfully")
    except Exception as e:
        print(f"\n✗ Aggregation failed: {e}")
        sys.exit(1)
