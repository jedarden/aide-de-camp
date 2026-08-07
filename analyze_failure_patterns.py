#!/usr/bin/env python3
"""
Failure Pattern Analyzer for Deployment Data

This script parses collected deployment data and categorizes failure patterns
across services. It creates a comprehensive taxonomy and documents findings.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Any


class FailurePatternAnalyzer:
    """Analyzes deployment events for failure patterns."""

    # Failure pattern taxonomy definitions
    PATTERN_TAXONOMY = {
        "ImagePullBackOff": {
            "description": "Container image cannot be pulled from registry",
            "severity": "high",
            "indicators": ["image pull error", "ErrImagePull", "ImagePullBackOff"],
            "causes": ["registry unavailable", "missing image", "authentication failure", "network issues"]
        },
        "CrashLoopBackOff": {
            "description": "Pod repeatedly crashes and restarts",
            "severity": "critical",
            "indicators": ["crash", "CrashLoopBackOff", "restart count", "terminated"],
            "causes": ["application errors", "misconfiguration", "runtime exceptions", "missing dependencies"]
        },
        "OOMKilled": {
            "description": "Container killed due to exceeding memory limits",
            "severity": "critical",
            "indicators": ["OOMKilled", "out of memory", "memory limit exceeded"],
            "causes": ["memory leaks", "insufficient limits", "high load", "memory-intensive operations"]
        },
        "Probe_failure": {
            "description": "Health check failures (readiness, liveness, or startup probes)",
            "severity": "medium",
            "indicators": ["probe failed", "readiness probe", "liveness probe", "unhealthy"],
            "causes": ["application not ready", "deadlock", "slow startup", "health check misconfiguration"]
        },
        "Dependency_timeout": {
            "description": "Timeouts connecting to external services or dependencies",
            "severity": "high",
            "indicators": ["timeout", "connection refused", "dependency unavailable", "upstream error"],
            "causes": ["database unavailable", "API timeout", "network issues", "service discovery failure"]
        },
        "Deployment_rollback": {
            "description": "Deployment was rolled back to a previous version",
            "severity": "medium",
            "indicators": ["rollback", "rolled back", "revert", "previous version"],
            "causes": ["deployment failure", "health check failures", "configuration errors", "errors detected post-deployment"]
        },
        "Other": {
            "description": "Other failure patterns not matching standard categories",
            "severity": "variable",
            "indicators": ["error", "failed", "failure", "issue"],
            "causes": ["various"]
        }
    }

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.patterns_found = defaultdict(list)
        self.analysis_results = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "data_directory": str(data_dir),
                "analysis_type": "failure_pattern_categorization"
            },
            "services": {},
            "pattern_statistics": {},
            "temporal_distribution": {},
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

    def analyze_service_events(self, service_name: str, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze deployment events for a single service."""
        events = service_data.get("deployment_events", [])
        current_status = service_data.get("current_status", {})
        pod_health = service_data.get("pod_health", {})

        service_analysis = {
            "service_name": service_name,
            "total_events": len(events),
            "current_image": current_status.get("image", "unknown"),
            "events_by_type": defaultdict(int),
            "failures_detected": [],
            "health_indicators": {},
            "deployment_outcomes": Counter()
        }

        # Extract health indicators if available
        if isinstance(pod_health, dict) and "health_indicators" in pod_health:
            service_analysis["health_indicators"] = pod_health["health_indicators"]

        # Analyze each event
        for event in events:
            event_type = event.get("event_type", "unknown")
            outcome = event.get("outcome", "unknown")

            service_analysis["events_by_type"][event_type] += 1
            service_analysis["deployment_outcomes"][outcome] += 1

            # Check for failure patterns
            if outcome == "rolled_back":
                failure = {
                    "timestamp": event.get("timestamp"),
                    "date": event.get("date"),
                    "pattern_type": "Deployment_rollback",
                    "severity": "medium",
                    "image": event.get("image"),
                    "context": {
                        "event_type": event_type,
                        "revision": event.get("revision"),
                        "notes": event.get("notes")
                    }
                }
                service_analysis["failures_detected"].append(failure)
                self.patterns_found["Deployment_rollback"].append(failure)

        # Check health indicators for common failure patterns
        if service_analysis["health_indicators"]:
            hi = service_analysis["health_indicators"]
            if not hi.get("no_image_pull_errors", True):
                failure = {
                    "pattern_type": "ImagePullBackOff",
                    "severity": "high",
                    "detected_via": "health_indicators",
                    "timestamp": datetime.now().isoformat()
                }
                service_analysis["failures_detected"].append(failure)
                self.patterns_found["ImagePullBackOff"].append(failure)

            if not hi.get("no_restart_loops", True):
                failure = {
                    "pattern_type": "CrashLoopBackOff",
                    "severity": "critical",
                    "detected_via": "health_indicators",
                    "timestamp": datetime.now().isoformat()
                }
                service_analysis["failures_detected"].append(failure)
                self.patterns_found["CrashLoopBackOff"].append(failure)

            if not hi.get("liveness_probes_passing", True):
                failure = {
                    "pattern_type": "Probe_failure",
                    "severity": "medium",
                    "detected_via": "health_indicators",
                    "probe_type": "liveness",
                    "timestamp": datetime.now().isoformat()
                }
                service_analysis["failures_detected"].append(failure)
                self.patterns_found["Probe_failure"].append(failure)

            if not hi.get("readiness_probes_passing", True):
                failure = {
                    "pattern_type": "Probe_failure",
                    "severity": "medium",
                    "detected_via": "health_indicators",
                    "probe_type": "readiness",
                    "timestamp": datetime.now().isoformat()
                }
                service_analysis["failures_detected"].append(failure)
                self.patterns_found["Probe_failure"].append(failure)

        return dict(service_analysis)

    def calculate_pattern_statistics(self) -> Dict[str, Any]:
        """Calculate statistics for each failure pattern category."""
        stats = {}

        for pattern_name, pattern_info in self.PATTERN_TAXONOMY.items():
            occurrences = self.patterns_found.get(pattern_name, [])

            # Calculate time span
            if occurrences:
                timestamps = [
                    occ.get("timestamp") or occ.get("date")
                    for occ in occurrences
                ]
                timestamps = [ts for ts in timestamps if ts]
                if timestamps:
                    # Convert to dates for span calculation
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
                    else:
                        time_span_days = 0
                else:
                    time_span_days = 0
            else:
                time_span_days = 0

            # Get affected services and images
            services_affected = set()
            images_affected = set()

            for occ in occurrences:
                if "service_name" in occ:
                    services_affected.add(occ["service_name"])
                if "image" in occ:
                    images_affected.add(occ["image"])
                if "context" in occ and "image" in occ["context"]:
                    images_affected.add(occ["context"]["image"])

            stats[pattern_name] = {
                "description": pattern_info["description"],
                "severity": pattern_info["severity"],
                "statistics": {
                    "frequency": len(occurrences),
                    "time_span_days": time_span_days,
                    "services_affected": list(services_affected),
                    "images_affected": list(images_affected),
                    "average_frequency_per_day": len(occurrences) / time_span_days if time_span_days > 0 else 0
                },
                "sample_failures": occurrences[:5],  # First 5 examples
                "indicators": pattern_info["indicators"],
                "common_causes": pattern_info["causes"]
            }

        return stats

    def generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        total_failures = sum(len(failures) for failures in self.patterns_found.values())

        # Count by severity
        severity_counts = defaultdict(int)
        for pattern_name, failures in self.patterns_found.items():
            severity = self.PATTERN_TAXONOMY[pattern_name]["severity"]
            severity_counts[severity] += len(failures)

        return {
            "total_patterns_identified": len(self.PATTERN_TAXONOMY),
            "total_failures_detected": total_failures,
            "patterns_with_occurrences": len([k for k, v in self.patterns_found.items() if v]),
            "failures_by_pattern": {
                pattern: len(failures)
                for pattern, failures in self.patterns_found.items()
            },
            "failures_by_severity": dict(severity_counts),
            "services_analyzed": list(self.analysis_results["services"].keys()),
            "analysis_period": "30 days (2026-07-07 to 2026-08-06)",
            "data_quality": "complete" if total_failures > 0 else "no_failures_found"
        }

    def analyze(self) -> Dict[str, Any]:
        """Run the complete analysis."""
        print("Loading deployment data...")
        deployment_data = self.load_deployment_data()

        print("Analyzing services...")
        for service_name, service_data in deployment_data.items():
            if service_name in ["metadata", "summary"]:
                continue

            print(f"  Analyzing {service_name}...")
            service_analysis = self.analyze_service_events(service_name, service_data)
            self.analysis_results["services"][service_name] = service_analysis

        print("Calculating pattern statistics...")
        self.analysis_results["pattern_statistics"] = self.calculate_pattern_statistics()

        print("Generating summary...")
        self.analysis_results["summary"] = self.generate_summary()

        return self.analysis_results

    def save_taxonomy(self, output_file: Path):
        """Save the failure taxonomy with analysis results."""
        taxonomy_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
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
            "analysis_results": {
                "patterns_found": {
                    pattern: len(failures)
                    for pattern, failures in self.patterns_found.items()
                },
                "total_failures_detected": sum(len(f) for f in self.patterns_found.values())
            }
        }

        with open(output_file, 'w') as f:
            json.dump(taxonomy_data, f, indent=2)

        print(f"Taxonomy saved to {output_file}")

    def save_full_analysis(self, output_file: Path):
        """Save the complete analysis results."""
        # Convert defaultdicts to regular dicts for JSON serialization
        results = dict(self.analysis_results)

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"Full analysis saved to {output_file}")


def generate_markdown_report(analysis_results: Dict[str, Any], taxonomy_file: Path, output_file: Path):
    """Generate a markdown summary report."""
    lines = [
        "# Failure Pattern Analysis Report",
        "",
        f"**Generated:** {analysis_results['metadata']['generated_at']}",
        f"**Analysis Period:** {analysis_results['summary']['analysis_period']}",
        "",
        "## Executive Summary",
        "",
    ]

    summary = analysis_results["summary"]
    lines.extend([
        f"- **Total patterns identified:** {summary['total_patterns_identified']}",
        f"- **Total failures detected:** {summary['total_failures_detected']}",
        f"- **Patterns with occurrences:** {summary['patterns_with_occurrences']}",
        f"- **Services analyzed:** {', '.join(summary['services_analyzed'])}",
        f"- **Data quality:** {summary['data_quality']}",
        "",
        "## Failure Pattern Taxonomy",
        ""
    ])

    for pattern_name, pattern_data in analysis_results["pattern_statistics"].items():
        lines.append(f"### {pattern_name}")
        lines.append("")
        lines.append(f"**Description:** {pattern_data['description']}")
        lines.append(f"**Severity:** {pattern_data['severity']}")

        stats = pattern_data["statistics"]
        lines.append(f"**Frequency:** {stats['frequency']} occurrences")
        lines.append(f"**Time span:** {stats['time_span_days']} days")

        if stats['services_affected']:
            lines.append(f"**Services affected:** {', '.join(stats['services_affected'])}")
        if stats['images_affected']:
            lines.append(f"**Images affected:** {', '.join(stats['images_affected'])}")

        if pattern_data['sample_failures']:
            lines.append("")
            lines.append("**Sample occurrences:**")
            for i, failure in enumerate(pattern_data['sample_failures'][:3], 1):
                lines.append(f"  {i}. {failure.get('timestamp', failure.get('date', 'unknown'))}")
                if 'image' in failure:
                    lines.append(f"     Image: {failure['image']}")
                if 'context' in failure and 'notes' in failure['context']:
                    lines.append(f"     Notes: {failure['context']['notes']}")

        lines.append("")
        lines.append("**Indicators:**")
        for indicator in pattern_data['indicators']:
            lines.append(f"  - `{indicator}`")

        lines.append("")
        lines.append("**Common causes:**")
        for cause in pattern_data['common_causes']:
            lines.append(f"  - {cause}")

        lines.append("")

    # Add service-specific analysis
    lines.append("## Service-Specific Analysis")
    lines.append("")

    for service_name, service_data in analysis_results["services"].items():
        lines.append(f"### {service_name}")
        lines.append("")
        lines.append(f"**Total events:** {service_data['total_events']}")
        lines.append(f"**Current image:** {service_data['current_image']}")
        lines.append("")

        if service_data['events_by_type']:
            lines.append("**Event types:**")
            for event_type, count in service_data['events_by_type'].items():
                lines.append(f"  - {event_type}: {count}")
            lines.append("")

        if service_data['deployment_outcomes']:
            lines.append("**Deployment outcomes:**")
            for outcome, count in service_data['deployment_outcomes'].items():
                lines.append(f"  - {outcome}: {count}")
            lines.append("")

        if service_data['failures_detected']:
            lines.append("**Failures detected:**")
            for failure in service_data['failures_detected']:
                lines.append(f"  - {failure['pattern_type']}: {failure.get('timestamp', failure.get('date', 'unknown'))}")
            lines.append("")
        else:
            lines.append("**No failures detected** ✅")
            lines.append("")

    # Add methodology
    lines.extend([
        "## Methodology",
        "",
        "This analysis examined:",
        "1. Deployment events from the last 30 days",
        "2. Pod health indicators for failure signals",
        "3. Deployment outcomes (success, rollback, failure)",
        "4. Image version changes and patterns",
        "",
        "Failures are categorized using the taxonomy defined above, with severity",
        "ratings ranging from 'info' to 'critical'.",
        "",
        "## Recommendations",
        "",
        "### Monitoring",
        "- Continue monitoring for the failure patterns defined in the taxonomy",
        "- Set up alerts for critical patterns (CrashLoopBackOff, OOMKilled)",
        "- Track deployment success rates over time",
        "",
        "### Data Collection",
        "- Collect pod status and event data for deeper failure analysis",
        "- Track CI/CD workflow execution and failures",
        "- Monitor image pull success rates and timing",
        "",
        "---",
        "",
        f"*Analysis based on data from: {taxonomy_file.parent.name}/"
    ])

    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Markdown report saved to {output_file}")


def main():
    """Main execution."""
    data_dir = Path("docs/research/deployment-data")

    if not data_dir.exists():
        print(f"Error: {data_dir} not found")
        sys.exit(1)

    print("=" * 60)
    print("Failure Pattern Analysis")
    print("=" * 60)

    analyzer = FailurePatternAnalyzer(data_dir)
    results = analyzer.analyze()

    # Save outputs
    taxonomy_file = data_dir / "failure-taxonomy.json"
    full_analysis_file = data_dir / "failure-pattern-analysis.json"
    report_file = Path("docs/research/failure-patterns.md")

    print("\nSaving results...")
    analyzer.save_taxonomy(taxonomy_file)
    analyzer.save_full_analysis(full_analysis_file)
    generate_markdown_report(results, taxonomy_file, report_file)

    print("\n" + "=" * 60)
    print("Analysis complete!")
    print("=" * 60)
    print(f"\nResults:")
    print(f"  - {taxonomy_file}")
    print(f"  - {full_analysis_file}")
    print(f"  - {report_file}")
    print(f"\nSummary:")
    print(f"  - Total failures: {results['summary']['total_failures_detected']}")
    print(f"  - Patterns found: {results['summary']['patterns_with_occurrences']}")


if __name__ == "__main__":
    main()
