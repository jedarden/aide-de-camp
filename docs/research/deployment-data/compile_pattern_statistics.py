#!/usr/bin/env python3
"""
Compile comprehensive pattern statistics summary from all analysis results.
Merges frequency, temporal, and correlation data into a single comprehensive summary.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def load_json(filepath: Path) -> Dict[str, Any]:
    """Load JSON file with error handling."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {filepath} not found, skipping")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse {filepath}: {e}")
        return {}


def extract_time_distribution(temporal_data: Dict, pattern_name: str) -> Dict[str, Any]:
    """Extract time distribution for a specific pattern from temporal data."""
    time_dist = {
        "first_occurrence": None,
        "last_occurrence": None,
        "dates_with_occurrences": [],
        "peak_failure_day": None,
        "total_days_with_failures": 0
    }

    # Find days where this pattern occurred
    dates_with_failures = []
    for date, data in temporal_data.get("daily_bins", {}).items():
        pattern_count = data.get("by_pattern", {}).get(pattern_name, 0)
        if pattern_count > 0:
            dates_with_failures.append({
                "date": date,
                "count": pattern_count,
                "rate_percentage": temporal_data.get("daily_failure_rates", {}).get(date, {}).get("pattern_rates", {}).get(pattern_name, {}).get("rate_percentage", 0.0)
            })

    if dates_with_failures:
        time_dist["dates_with_occurrences"] = dates_with_failures
        time_dist["first_occurrence"] = dates_with_failures[0]["date"]
        time_dist["last_occurrence"] = dates_with_failures[-1]["date"]
        time_dist["total_days_with_failures"] = len(dates_with_failures)

        # Find peak day (highest count)
        peak_day = max(dates_with_failures, key=lambda x: x["count"])
        time_dist["peak_failure_day"] = peak_day["date"]

    return time_dist


def extract_deployment_correlations(temporal_data: Dict, pattern_name: str) -> list:
    """Extract deployment correlations for a specific pattern."""
    correlations = []

    for corr in temporal_data.get("deployment_correlations", []):
        pattern_in_corr = corr.get("pattern", {})
        if pattern_name in pattern_in_corr:
            # Build correlation entry
            correlation_entry = {
                "failure_date": corr.get("failure_date"),
                "failure_timestamp": corr.get("failure_timestamp"),
                "related_deployments": corr.get("related_deployments", []),
                "deployment_count": corr.get("deployment_count", 0)
            }
            correlations.append(correlation_entry)

    return correlations


def compile_pattern_statistics() -> Dict[str, Any]:
    """Compile comprehensive pattern statistics from all analysis files."""

    # Paths to input files
    base_dir = Path("/home/coding/aide-de-camp/docs/research/deployment-data")

    # Load all analysis data
    frequency_data = load_json(base_dir / "frequency-by-pattern.json")
    temporal_data = load_json(base_dir / "temporal-distributions.json")
    classified_data = load_json(base_dir / "classified-failures.json")
    taxonomy_data = load_json(base_dir / "failure-taxonomy.json")

    # Extract metadata
    metadata = {
        "analysis_date": datetime.utcnow().isoformat() + "Z",
        "data_window_days": temporal_data.get("metadata", {}).get("time_window", {}).get("total_days", 0),
        "total_failures_analyzed": temporal_data.get("metadata", {}).get("total_failures_analyzed", 0),
        "total_deployments_analyzed": temporal_data.get("metadata", {}).get("total_deployments_analyzed", 0),
        "services_analyzed": taxonomy_data.get("services_analyzed", []),
        "analysis_period": {
            "start_date": temporal_data.get("metadata", {}).get("time_window", {}).get("start_date"),
            "end_date": temporal_data.get("metadata", {}).get("time_window", {}).get("end_date")
        }
    }

    # Get frequency summary
    frequency_summary = frequency_data.get("pattern_statistics", {})

    # Build pattern definitions from classified data's pattern_definitions
    pattern_definitions = {}
    for pd in classified_data.get("pattern_definitions", []):
        pattern_name = pd["name"]
        pattern_definitions[pattern_name] = pd

    # Also include any patterns from frequency data that might not be in definitions
    for pattern_name in frequency_summary.keys():
        if pattern_name not in pattern_definitions:
            # Create minimal definition
            pattern_definitions[pattern_name] = {
                "name": pattern_name,
                "description": f"Pattern: {pattern_name}",
                "severity": "unknown",
                "patterns_count": 0,
                "keywords_count": 0
            }

    # Compile statistics for each pattern
    pattern_stats = {}

    for pattern_name, pattern_def in pattern_definitions.items():
        freq_data = frequency_summary.get(pattern_name, {})
        taxonomy_cat = taxonomy_data.get("pattern_categories", {}).get(pattern_name, {})

        # Extract services affected
        services_affected = freq_data.get("services", {})

        # Extract image versions from classified failures
        image_versions = {}
        for failure in classified_data.get("classified_failures", []):
            if failure.get("pattern_type") == pattern_name:
                image = failure.get("image")
                if image:
                    image_versions[image] = image_versions.get(image, 0) + 1

        # Extract time distribution
        time_dist = extract_time_distribution(temporal_data, pattern_name)

        # Extract deployment correlations
        deployment_correlations = extract_deployment_correlations(temporal_data, pattern_name)

        pattern_stats[pattern_name] = {
            "pattern_type": pattern_name,
            "description": pattern_def.get("description"),
            "severity": pattern_def.get("severity"),
            "occurrence_count": freq_data.get("total_count", 0),
            "frequency_per_day": round(freq_data.get("total_count", 0) / metadata["data_window_days"], 4) if metadata["data_window_days"] > 0 else 0,
            "affected_services": services_affected,
            "image_versions": image_versions,
            "time_distribution": time_dist,
            "deployment_correlations": deployment_correlations
        }

    # Build summary statistics
    summary = {
        "total_patterns_identified": len(pattern_stats),
        "patterns_with_occurrences": sum(1 for p in pattern_stats.values() if p["occurrence_count"] > 0),
        "total_failures": metadata["total_failures_analyzed"],
        "services_with_failures": len([s for s in metadata["services_analyzed"] if any(p["affected_services"].get(s, 0) > 0 for p in pattern_stats.values())]),
        "pattern_rankings": sorted(
            [(name, data["occurrence_count"]) for name, data in pattern_stats.items()],
            key=lambda x: x[1],
            reverse=True
        ),
        "high_severity_patterns": [name for name, data in pattern_stats.items() if data.get("severity") == "high" and data["occurrence_count"] > 0],
        "critical_severity_patterns": [name for name, data in pattern_stats.items() if data.get("severity") == "critical" and data["occurrence_count"] > 0],
        "peak_failure_day": temporal_data.get("summary", {}).get("peak_failure_day"),
        "total_days_with_failures": temporal_data.get("summary", {}).get("total_days_with_failures", 0),
        "total_correlations": temporal_data.get("summary", {}).get("total_correlations", 0)
    }

    return {
        "metadata": metadata,
        "summary": summary,
        "pattern_statistics": pattern_stats
    }


def main():
    """Main entry point."""
    print("Compiling comprehensive pattern statistics...")

    # Compile statistics
    stats = compile_pattern_statistics()

    # Write output
    output_path = Path("/home/coding/aide-de-camp/docs/research/deployment-data/pattern-statistics.json")
    with open(output_path, 'w') as f:
        json.dump(stats, f, indent=2)

    print(f"✓ Comprehensive pattern statistics saved to {output_path}")

    # Print summary
    print(f"\nSummary:")
    print(f"  Analysis period: {stats['metadata']['analysis_period']['start_date']} to {stats['metadata']['analysis_period']['end_date']}")
    print(f"  Data window: {stats['metadata']['data_window_days']} days")
    print(f"  Total failures analyzed: {stats['metadata']['total_failures_analyzed']}")
    print(f"  Total deployments analyzed: {stats['metadata']['total_deployments_analyzed']}")
    print(f"  Patterns identified: {stats['summary']['total_patterns_identified']}")
    print(f"  Patterns with occurrences: {stats['summary']['patterns_with_occurrences']}")
    print(f"  Services analyzed: {', '.join(stats['metadata']['services_analyzed'])}")

    print(f"\nPattern rankings:")
    for pattern, count in stats['summary']['pattern_rankings']:
        print(f"  - {pattern}: {count} occurrences")

    # Validate output
    try:
        with open(output_path, 'r') as f:
            json.load(f)
        print("\n✓ JSON validation successful")
    except json.JSONDecodeError as e:
        print(f"\n✗ JSON validation failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
