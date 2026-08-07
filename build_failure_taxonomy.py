#!/usr/bin/env python3
"""
Failure Taxonomy Builder with Frequency Analysis

This script applies pattern-matching rules to categorize all deployment failures
and builds a complete taxonomy with frequency statistics for the 30-day analysis period.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Tuple


class FailureTaxonomyBuilder:
    """Builds comprehensive failure taxonomy with frequency analysis."""

    # Pattern-matching rules (from previous step)
    PATTERN_TAXONOMY = {
        "ImagePullBackOff": {
            "description": "Container image cannot be pulled from registry",
            "severity": "high",
            "indicators": ["image pull error", "ErrImagePull", "ImagePullBackOff", "pull back off"],
            "causes": ["registry unavailable", "missing image", "authentication failure", "network issues"]
        },
        "CrashLoopBackOff": {
            "description": "Pod repeatedly crashes and restarts",
            "severity": "critical",
            "indicators": ["crash", "CrashLoopBackOff", "restart count", "terminated", "back off"],
            "causes": ["application errors", "misconfiguration", "runtime exceptions", "missing dependencies"]
        },
        "OOMKilled": {
            "description": "Container killed due to exceeding memory limits",
            "severity": "critical",
            "indicators": ["OOMKilled", "out of memory", "memory limit exceeded", "oom"],
            "causes": ["memory leaks", "insufficient limits", "high load", "memory-intensive operations"]
        },
        "Probe_failure": {
            "description": "Health check failures (readiness, liveness, or startup probes)",
            "severity": "medium",
            "indicators": ["probe failed", "readiness probe", "liveness probe", "startup probe", "unhealthy"],
            "causes": ["application not ready", "deadlock", "slow startup", "health check misconfiguration"]
        },
        "Dependency_timeout": {
            "description": "Timeouts connecting to external services or dependencies",
            "severity": "high",
            "indicators": ["timeout", "connection refused", "dependency unavailable", "upstream error", "connection timeout"],
            "causes": ["database unavailable", "API timeout", "network issues", "service discovery failure"]
        },
        "Deployment_rollback": {
            "description": "Deployment was rolled back to a previous version",
            "severity": "medium",
            "indicators": ["rollback", "rolled back", "revert", "previous version", "undo deployment"],
            "causes": ["deployment failure", "health check failures", "configuration errors", "errors detected post-deployment"]
        },
        "Rapid_deployment_sequence": {
            "description": "Multiple deployments occurring in rapid succession",
            "severity": "info",
            "indicators": ["rapid deployment", "quick succession", "multiple deployments", "deployment burst"],
            "causes": ["quick bug fixes", "configuration refinement", "image build corrections", "deployment validation"]
        },
        "Other": {
            "description": "Other failure patterns not matching standard categories",
            "severity": "variable",
            "indicators": ["error", "failed", "failure", "issue", "problem"],
            "causes": ["various"]
        }
    }

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.categorized_failures = defaultdict(list)
        self.uncategorized_failures = []
        self.taxonomy = {
            "metadata": {},
            "pattern_definitions": {},
            "frequency_analysis": {},
            "service_distribution": {},
            "temporal_distribution": {},
            "image_context": {},
            "summary": {}
        }

    def load_deployment_data(self) -> Dict[str, Any]:
        """Load the comprehensive deployment events file."""
        comprehensive_file = self.data_dir / "deployment-events-30days-comprehensive.json"
        if not comprehensive_file.exists():
            print(f"Error: {comprehensive_file} not found")
            sys.exit(1)

        with open(comprehensive_file) as f:
            return json.load(f)

    def match_pattern(self, failure_text: str, event_data: Dict[str, Any]) -> Optional[str]:
        """Match failure text against pattern taxonomy indicators."""
        failure_text_lower = failure_text.lower()

        # Check each pattern's indicators
        for pattern_name, pattern_info in self.PATTERN_TAXONOMY.items():
            if pattern_name == "Other":
                continue  # Keep Other as fallback

            for indicator in pattern_info["indicators"]:
                if indicator.lower() in failure_text_lower:
                    return pattern_name

        # Check for rapid deployment sequence pattern (special case)
        if self.is_rapid_deployment_sequence(event_data):
            return "Rapid_deployment_sequence"

        # Default to Other if no match
        return "Other"

    def is_rapid_deployment_sequence(self, event_data: Dict[str, Any]) -> bool:
        """Check if this is part of a rapid deployment sequence."""
        # This would be determined by temporal analysis across events
        # For individual event matching, we look for keywords
        notes = event_data.get("notes", "").lower()
        return any(keyword in notes for keyword in ["rapid", "quick succession", "burst"])

    def categorize_failure(self, event: Dict[str, Any], service_name: str) -> str:
        """Categorize a failure event using pattern matching."""
        # Build failure context string
        failure_context = self.build_failure_context(event)

        # Match against patterns
        pattern_type = self.match_pattern(failure_context, event)

        # Extract metadata
        failure_record = {
            "timestamp": event.get("timestamp"),
            "date": event.get("date"),
            "service": service_name,
            "deployment": event.get("deployment", event.get("deployment_id", "unknown")),
            "image": event.get("image", "unknown"),
            "event_type": event.get("event_type", "unknown"),
            "outcome": event.get("outcome", "unknown"),
            "revision": event.get("revision", "unknown"),
            "notes": event.get("notes", ""),
            "context": failure_context
        }

        # Store in categorized bucket
        self.categorized_failures[pattern_type].append(failure_record)

        return pattern_type

    def build_failure_context(self, event: Dict[str, Any]) -> str:
        """Build a comprehensive failure context string for pattern matching."""
        context_parts = []

        # Add various fields for pattern matching
        for field in ["event_type", "outcome", "notes", "message", "reason", "error"]:
            value = event.get(field, "")
            if value and isinstance(value, str):
                context_parts.append(value)

        # Add image context
        image = event.get("image", "")
        if image:
            context_parts.append(f"image: {image}")

        return " ".join(context_parts)

    def analyze_service(self, service_name: str, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single service for failure patterns."""
        events = service_data.get("deployment_events", [])
        service_failures = []
        total_events = len(events)

        for event in events:
            # Check if this is a failure event
            if self.is_failure_event(event):
                pattern_type = self.categorize_failure(event, service_name)
                service_failures.append({
                    "event": event,
                    "pattern_type": pattern_type
                })

        return {
            "service_name": service_name,
            "total_events_analyzed": total_events,
            "failures_detected": len(service_failures),
            "failure_patterns": [f["pattern_type"] for f in service_failures],
            "failure_details": service_failures
        }

    def is_failure_event(self, event: Dict[str, Any]) -> bool:
        """Determine if an event represents a failure."""
        outcome = event.get("outcome", "").lower()
        event_type = event.get("event_type", "").lower()
        notes = event.get("notes", "").lower()

        # Check for failure indicators
        failure_indicators = [
            "failure", "failed", "error", "rollback", "crash", "timeout",
            "back off", "terminated", "oomkilled", "pull back off", "unhealthy"
        ]

        for indicator in failure_indicators:
            if (indicator in outcome or
                indicator in event_type or
                indicator in notes):
                return True

        return False

    def calculate_frequency_statistics(self) -> Dict[str, Any]:
        """Calculate frequency statistics for each pattern category."""
        frequency_stats = {}

        for pattern_name, failures in self.categorized_failures.items():
            pattern_info = self.PATTERN_TAXONOMY.get(pattern_name, {})

            # Calculate time span
            timestamps = [f.get("timestamp") or f.get("date") for f in failures if f.get("timestamp") or f.get("date")]
            time_span_days = 0
            if timestamps:
                dates = []
                for ts in timestamps:
                    try:
                        if "T" in ts:
                            dates.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                        else:
                            dates.append(datetime.fromisoformat(ts))
                    except:
                        pass
                if dates:
                    time_span_days = (max(dates) - min(dates)).days + 1

            # Extract unique services and images
            services_affected = list(set(f.get("service") for f in failures))
            images_affected = list(set(f.get("image") for f in failures if f.get("image") and f.get("image") != "unknown"))

            # Calculate per-day average
            avg_per_day = len(failures) / time_span_days if time_span_days > 0 else 0

            frequency_stats[pattern_name] = {
                "pattern_name": pattern_name,
                "description": pattern_info.get("description", ""),
                "severity": pattern_info.get("severity", "variable"),
                "total_occurrences": len(failures),
                "time_span_days": time_span_days,
                "services_affected": services_affected,
                "images_affected": images_affected,
                "frequency_per_day": round(avg_per_day, 2),
                "percentage_of_total": 0.0,  # Will be calculated after
                "sample_failures": failures[:3]  # First 3 examples
            }

        return frequency_stats

    def calculate_service_distribution(self) -> Dict[str, Any]:
        """Calculate failure distribution by service."""
        service_dist = defaultdict(lambda: {
            "total_failures": 0,
            "patterns": defaultdict(int),
            "images": set(),
            "timeline": []
        })

        for pattern_name, failures in self.categorized_failures.items():
            for failure in failures:
                service = failure.get("service", "unknown")
                service_dist[service]["total_failures"] += 1
                service_dist[service]["patterns"][pattern_name] += 1

                if failure.get("image") and failure.get("image") != "unknown":
                    service_dist[service]["images"].add(failure.get("image"))

                if failure.get("timestamp"):
                    service_dist[service]["timeline"].append({
                        "timestamp": failure.get("timestamp"),
                        "pattern": pattern_name,
                        "image": failure.get("image")
                    })

        # Convert to JSON-serializable format
        return {
            service: {
                "total_failures": data["total_failures"],
                "patterns_by_type": dict(data["patterns"]),
                "images_involved": list(data["images"]),
                "failure_timeline": sorted(data["timeline"], key=lambda x: x.get("timestamp", ""))
            }
            for service, data in service_dist.items()
        }

    def calculate_temporal_distribution(self) -> Dict[str, Any]:
        """Calculate temporal distribution of failures."""
        all_failures = []
        for failures in self.categorized_failures.values():
            all_failures.extend(failures)

        daily_counts = Counter()
        hourly_counts = Counter()
        day_of_week_counts = Counter()

        for failure in all_failures:
            timestamp_str = failure.get("timestamp") or failure.get("date")
            if timestamp_str:
                try:
                    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    date_key = dt.strftime('%Y-%m-%d')
                    hour_key = dt.strftime('%H:00')
                    day_key = dt.strftime('%A')

                    daily_counts[date_key] += 1
                    hourly_counts[hour_key] += 1
                    day_of_week_counts[day_key] += 1
                except:
                    pass

        return {
            "daily_distribution": dict(sorted(daily_counts.items())),
            "hourly_distribution": dict(sorted(hourly_counts.items())),
            "day_of_week_distribution": dict(day_of_week_counts),
            "total_active_days": len(daily_counts),
            "peak_day": daily_counts.most_common(1)[0] if daily_counts else None,
            "peak_hour": hourly_counts.most_common(1)[0] if hourly_counts else None,
            "most_common_day_of_week": day_of_week_counts.most_common(1)[0] if day_of_week_counts else None
        }

    def calculate_image_context(self) -> Dict[str, Any]:
        """Analyze failures in the context of images involved."""
        image_failures = defaultdict(lambda: {
            "total_failures": 0,
            "patterns": defaultdict(int),
            "services": set(),
            "first_seen": None,
            "last_seen": None
        })

        for pattern_name, failures in self.categorized_failures.items():
            for failure in failures:
                image = failure.get("image", "unknown")
                if image == "unknown":
                    continue

                image_failures[image]["total_failures"] += 1
                image_failures[image]["patterns"][pattern_name] += 1
                image_failures[image]["services"].add(failure.get("service", "unknown"))

                timestamp = failure.get("timestamp")
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        if image_failures[image]["first_seen"] is None or dt < image_failures[image]["first_seen"]:
                            image_failures[image]["first_seen"] = dt
                        if image_failures[image]["last_seen"] is None or dt > image_failures[image]["last_seen"]:
                            image_failures[image]["last_seen"] = dt
                    except:
                        pass

        # Convert to JSON-serializable format
        result = {}
        for image, data in image_failures.items():
            result[image] = {
                "total_failures": data["total_failures"],
                "patterns_by_type": dict(data["patterns"]),
                "services_affected": list(data["services"]),
                "first_seen": data["first_seen"].isoformat() if data["first_seen"] else None,
                "last_seen": data["last_seen"].isoformat() if data["last_seen"] else None
            }

        return result

    def generate_summary(self, frequency_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics."""
        total_failures = sum(len(failures) for failures in self.categorized_failures.values())

        # Calculate percentages
        for pattern_name, stats in frequency_stats.items():
            if total_failures > 0:
                stats["percentage_of_total"] = round((stats["total_occurrences"] / total_failures) * 100, 1)

        # Severity distribution
        severity_counts = Counter()
        for pattern_name, failures in self.categorized_failures.items():
            severity = self.PATTERN_TAXONOMY.get(pattern_name, {}).get("severity", "variable")
            severity_counts[severity] += len(failures)

        return {
            "total_failures_categorized": total_failures,
            "total_pattern_types_detected": len(self.categorized_failures),
            "uncategorized_failures": len(self.uncategorized_failures),
            "verification": {
                "total_records_processed": total_failures + len(self.uncategorized_failures),
                "categorized_records": total_failures,
                "uncategorized_records": len(self.uncategorized_failures),
                "all_categorized": len(self.uncategorized_failures) == 0
            },
            "failures_by_pattern": {
                pattern: len(failures)
                for pattern, failures in self.categorized_failures.items()
            },
            "failures_by_severity": dict(severity_counts),
            "most_common_patterns": sorted(
                [(p, len(f)) for p, f in self.categorized_failures.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }

    def build_taxonomy(self) -> Dict[str, Any]:
        """Build the complete failure taxonomy."""
        print("Loading deployment data...")
        deployment_data = self.load_deployment_data()

        print("Analyzing services for failure patterns...")
        services_analyzed = {}
        for service_name, service_data in deployment_data.items():
            if service_name in ["metadata", "summary"]:
                continue

            print(f"  Analyzing {service_name}...")
            service_analysis = self.analyze_service(service_name, service_data)
            services_analyzed[service_name] = service_analysis

        print("Calculating frequency statistics...")
        frequency_stats = self.calculate_frequency_statistics()

        print("Calculating service distribution...")
        service_dist = self.calculate_service_distribution()

        print("Calculating temporal distribution...")
        temporal_dist = self.calculate_temporal_distribution()

        print("Calculating image context...")
        image_ctx = self.calculate_image_context()

        print("Generating summary...")
        summary = self.generate_summary(frequency_stats)

        # Build final taxonomy structure
        self.taxonomy = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "analysis_type": "failure_taxonomy_with_frequency_analysis",
                "time_period": "30 days (2026-07-07 to 2026-08-06)",
                "pattern_categories": list(self.PATTERN_TAXONOMY.keys()),
                "total_patterns_defined": len(self.PATTERN_TAXONOMY)
            },
            "pattern_definitions": [
                {
                    "name": name,
                    "description": info["description"],
                    "severity": info["severity"],
                    "indicators": info["indicators"],
                    "common_causes": info["causes"]
                }
                for name, info in self.PATTERN_TAXONOMY.items()
            ],
            "frequency_analysis": frequency_stats,
            "service_distribution": service_dist,
            "temporal_distribution": temporal_dist,
            "image_context": image_ctx,
            "services_analyzed": services_analyzed,
            "summary": summary
        }

        return self.taxonomy

    def save_taxonomy(self, output_file: Path):
        """Save the complete taxonomy to file."""
        with open(output_file, 'w') as f:
            json.dump(self.taxonomy, f, indent=2, default=str)

        print(f"Taxonomy saved to {output_file}")

    def verify_taxonomy(self) -> bool:
        """Verify that all failures were categorized."""
        total_categorized = sum(len(failures) for failures in self.categorized_failures.values())
        total_uncategorized = len(self.uncategorized_failures)
        total_records = total_categorized + total_uncategorized

        print("\n" + "=" * 60)
        print("TAXONOMY VERIFICATION")
        print("=" * 60)
        print(f"Total records processed: {total_records}")
        print(f"Categorized failures: {total_categorized}")
        print(f"Uncategorized failures: {total_uncategorized}")

        if total_uncategorized == 0:
            print("✓ All failures successfully categorized")
            return True
        else:
            print(f"⚠ {total_uncategorized} failures remain uncategorized")
            for failure in self.uncategorized_failures:
                print(f"  - {failure.get('timestamp', 'unknown')}: {failure.get('notes', 'no notes')}")
            return False


def main():
    """Main execution."""
    data_dir = Path("docs/research/deployment-data")

    if not data_dir.exists():
        print(f"Error: {data_dir} not found")
        sys.exit(1)

    print("=" * 60)
    print("Failure Taxonomy Builder with Frequency Analysis")
    print("=" * 60)

    builder = FailureTaxonomyBuilder(data_dir)
    taxonomy = builder.build_taxonomy()

    # Save outputs
    output_file = data_dir / "failure-taxonomy-complete.json"
    print(f"\nSaving taxonomy to {output_file}...")
    builder.save_taxonomy(output_file)

    # Verify
    builder.verify_taxonomy()

    print("\n" + "=" * 60)
    print("TAXONOMY BUILD COMPLETE")
    print("=" * 60)

    # Print summary
    summary = taxonomy["summary"]
    print(f"\nSUMMARY:")
    print(f"  Total failures categorized: {summary['total_failures_categorized']}")
    print(f"  Pattern types detected: {summary['total_pattern_types_detected']}")
    print(f"  Most common patterns:")
    for pattern, count in summary['most_common_patterns']:
        print(f"    - {pattern}: {count} occurrences")


if __name__ == "__main__":
    main()
