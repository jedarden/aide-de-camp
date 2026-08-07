#!/usr/bin/env python3
"""
Build structured taxonomy data structure from pattern frequency statistics.

This script loads statistics output from Child 2 (adc-3hwmn) and constructs
a complete taxonomy with all pattern categories, frequency statistics,
service distribution, temporal data, and image context.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict


class TaxonomyBuilder:
    """Builds complete taxonomy data structure with frequency statistics."""

    def __init__(self, statistics_file: Path):
        self.statistics_file = statistics_file
        self.taxonomy = {
            "metadata": {},
            "pattern_categories": {},
            "service_distribution": {},
            "temporal_analysis": {},
            "image_context": {},
            "summary": {}
        }

    def load_statistics(self) -> Dict[str, Any]:
        """Load pattern frequency statistics from Child 2 output."""
        print(f"Loading statistics from {self.statistics_file}...")

        if not self.statistics_file.exists():
            raise FileNotFoundError(f"Statistics file not found: {self.statistics_file}")

        with open(self.statistics_file) as f:
            data = json.load(f)

        print(f"✓ Loaded statistics with {data.get('total_categorized_failures', 0)} categorized failures")
        return data

    def build_taxonomy_structure(self, stats_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build complete taxonomy structure from statistics."""

        # Build metadata
        metadata = {
            "generated_at": datetime.now().isoformat(),
            "source_analysis": "Child 2 (adc-3hwmn) - Pattern Frequency Statistics",
            "taxonomy_version": "1.0",
            "analysis_period": stats_data.get("generated_at", "unknown"),
            "total_categorized_failures": stats_data.get("total_categorized_failures", 0),
            "pattern_categories_count": len(stats_data.get("categories", {}))
        }

        # Build pattern categories with nested statistics
        pattern_categories = {}
        service_distribution = defaultdict(lambda: {
            "patterns": defaultdict(int),
            "total_failures": 0,
            "images": set()
        })

        temporal_data = {
            "daily_failures_by_pattern": defaultdict(lambda: defaultdict(int)),
            "time_spans": {},
            "active_days": set()
        }

        image_context = defaultdict(lambda: {
            "patterns": defaultdict(int),
            "services": set(),
            "total_failures": 0
        })

        categories = stats_data.get("categories", {})

        for category_name, category_data in categories.items():
            # Build pattern category entry
            pattern_categories[category_name] = {
                "description": self._get_category_description(category_name),
                "total_count": category_data.get("total_count", 0),
                "severity": self._get_category_severity(category_name),
                "service_distribution": dict(category_data.get("service_distribution", {})),
                "image_distribution": dict(category_data.get("image_distribution", {})),
                "version_distribution": dict(category_data.get("version_distribution", {})),
                "daily_distribution": dict(category_data.get("daily_distribution", {})),
                "time_span": category_data.get("time_span", {}),
                "examples": category_data.get("examples", [])[:3]  # Top 3 examples
            }

            # Aggregate service distribution
            for service, count in category_data.get("service_distribution", {}).items():
                service_distribution[service]["patterns"][category_name] += count
                service_distribution[service]["total_failures"] += count

            # Aggregate image distribution
            for image, count in category_data.get("image_distribution", {}).items():
                image_context[image]["patterns"][category_name] += count
                image_context[image]["total_failures"] += count
                for service in category_data.get("service_distribution", {}).keys():
                    image_context[image]["services"].add(service)

            # Aggregate temporal data
            time_span = category_data.get("time_span", {})
            if time_span.get("start") and time_span.get("end"):
                temporal_data["time_spans"][category_name] = time_span

            for day, count in category_data.get("daily_distribution", {}).items():
                temporal_data["daily_failures_by_pattern"][day][category_name] += count
                if day != "unknown":
                    temporal_data["active_days"].add(day)

            # Add images to service distribution
            for service in category_data.get("service_distribution", {}).keys():
                for image in category_data.get("image_distribution", {}).keys():
                    service_distribution[service]["images"].add(image)

        # Convert defaultdicts to regular dicts for JSON serialization
        service_dist_final = {}
        for service, data in service_distribution.items():
            service_dist_final[service] = {
                "total_failures": data["total_failures"],
                "patterns_by_type": dict(data["patterns"]),
                "images_involved": list(data["images"])
            }

        temporal_final = {
            "daily_failures_by_pattern": {
                day: dict(patterns)
                for day, patterns in temporal_data["daily_failures_by_pattern"].items()
            },
            "time_spans": temporal_data["time_spans"],
            "active_days": sorted(list(temporal_data["active_days"])),
            "total_active_days": len(temporal_data["active_days"])
        }

        image_ctx_final = {}
        for image, data in image_context.items():
            image_ctx_final[image] = {
                "total_failures": data["total_failures"],
                "patterns_by_type": dict(data["patterns"]),
                "services_affected": list(data["services"])
            }

        # Build summary
        summary = {
            "total_categorized_failures": stats_data.get("total_categorized_failures", 0),
            "total_pattern_categories": len(categories),
            "top_categories": self._get_top_categories(categories, 5),
            "services_analyzed": list(service_distribution.keys()),
            "total_services": len(service_distribution),
            "images_analyzed": list(image_context.keys()),
            "total_images": len(image_context),
            "active_days": temporal_final["active_days"],
            "analysis_duration_days": temporal_final["total_active_days"]
        }

        # Assemble final taxonomy
        taxonomy = {
            "metadata": metadata,
            "pattern_categories": pattern_categories,
            "service_distribution": service_dist_final,
            "temporal_analysis": temporal_final,
            "image_context": image_ctx_final,
            "summary": summary
        }

        return taxonomy

    def _get_category_description(self, category_name: str) -> str:
        """Get description for a pattern category."""
        descriptions = {
            "DependencyTimeout": "Timeouts connecting to external services or dependencies",
            "DeploymentRollback": "Deployment was rolled back to a previous version",
            "HTTPError": "HTTP error responses during deployment or operation",
            "NetworkIssue": "Network-related failures including connection issues",
            "RecordingFetchError": "Errors fetching recordings from storage"
        }
        return descriptions.get(category_name, "Pattern category from failure analysis")

    def _get_category_severity(self, category_name: str) -> str:
        """Get severity level for a pattern category."""
        severity_map = {
            "DependencyTimeout": "high",
            "DeploymentRollback": "medium",
            "HTTPError": "medium",
            "NetworkIssue": "medium",
            "RecordingFetchError": "low"
        }
        return severity_map.get(category_name, "variable")

    def _get_top_categories(self, categories: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """Get top categories by failure count."""
        sorted_categories = sorted(
            categories.items(),
            key=lambda x: x[1].get("total_count", 0),
            reverse=True
        )

        return [
            {
                "category": name,
                "count": data.get("total_count", 0),
                "severity": self._get_category_severity(name),
                "services": list(data.get("service_distribution", {}).keys()),
                "time_span_days": data.get("time_span", {}).get("days", 0)
            }
            for name, data in sorted_categories[:limit]
        ]

    def build(self) -> Dict[str, Any]:
        """Build complete taxonomy structure."""
        print("=" * 70)
        print("Building Taxonomy Data Structure")
        print("=" * 70)

        # Load statistics
        stats_data = self.load_statistics()

        # Build taxonomy
        print("Building taxonomy structure...")
        taxonomy = self.build_taxonomy_structure(stats_data)

        print("✓ Taxonomy structure built successfully")
        return taxonomy

    def save_taxonomy(self, output_file: Path):
        """Save taxonomy to JSON file."""
        taxonomy = self.build()

        print(f"\nSaving taxonomy to {output_file}...")
        with open(output_file, 'w') as f:
            json.dump(taxonomy, f, indent=2, default=str)

        print(f"✓ Taxonomy saved to {output_file}")
        return taxonomy

    def print_summary(self, taxonomy: Dict[str, Any]):
        """Print taxonomy summary."""
        summary = taxonomy.get("summary", {})

        print("\n" + "=" * 70)
        print("TAXONOMY SUMMARY")
        print("=" * 70)
        print(f"Total categorized failures: {summary.get('total_categorized_failures', 0)}")
        print(f"Pattern categories: {summary.get('total_pattern_categories', 0)}")
        print(f"Services analyzed: {summary.get('total_services', 0)}")
        print(f"Images analyzed: {summary.get('total_images', 0)}")
        print(f"Active days: {summary.get('analysis_duration_days', 0)}")

        print("\nTop Categories:")
        for i, cat in enumerate(summary.get('top_categories', []), 1):
            print(f"  {i}. {cat['category']}: {cat['count']} failures ({cat['severity']} severity)")


def main():
    """Main execution."""
    # Define paths
    statistics_file = Path("pattern-frequency-statistics.json")
    output_file = Path("taxonomy-structure-complete.json")

    print("=" * 70)
    print("Taxonomy Structure Builder")
    print("=" * 70)

    # Build and save taxonomy
    builder = TaxonomyBuilder(statistics_file)
    taxonomy = builder.save_taxonomy(output_file)

    # Print summary
    builder.print_summary(taxonomy)

    print("\n" + "=" * 70)
    print("TAXONOMY BUILD COMPLETE")
    print("=" * 70)
    print(f"\nOutput files:")
    print(f"  - {output_file} (complete taxonomy structure)")
    print(f"\nTaxonomy includes:")
    print(f"  ✓ Metadata (generation timestamp, source, version)")
    print(f"  ✓ Pattern categories ({taxonomy['summary']['total_pattern_categories']} categories)")
    print(f"  ✓ Service distribution ({taxonomy['summary']['total_services']} services)")
    print(f"  ✓ Temporal analysis ({taxonomy['summary']['analysis_duration_days']} days)")
    print(f"  ✓ Image context ({taxonomy['summary']['total_images']} images)")
    print(f"  ✓ Summary statistics")


if __name__ == "__main__":
    main()