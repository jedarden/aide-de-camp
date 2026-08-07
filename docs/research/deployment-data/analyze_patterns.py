#!/usr/bin/env python3
"""
Analyze and categorize failure patterns from deployment data.

This script:
1. Loads parsed deployment data from Child 1
2. Creates a taxonomy of failure pattern categories
3. For each pattern, extracts frequency, time distribution, and context
4. Outputs intermediate results as console logs
5. Generates comprehensive failure pattern analysis
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class FailurePattern:
    """Represents a failure pattern with statistics."""
    pattern_id: str
    category: str
    severity: str
    description: str
    total_occurrences: int = 0
    distribution_by_service: Dict[str, int] = field(default_factory=dict)
    image_version_context: Dict[str, Any] = field(default_factory=dict)
    time_distribution: Dict[str, Any] = field(default_factory=dict)
    sample_occurrences: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pattern_id": self.pattern_id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "total_occurrences": self.total_occurrences,
            "distribution_by_service": self.distribution_by_service,
            "image_version_context": self.image_version_context,
            "time_distribution": self.time_distribution,
            "sample_occurrences": self.sample_occurrences
        }


class FailurePatternAnalyzer:
    """Analyze deployment failures and categorize them by pattern."""

    # Pattern matching rules for different failure types
    PATTERN_RULES = {
        "ImagePullBackOff": {
            "category": "Critical Infrastructure",
            "severity": "critical",
            "description": "Container image cannot be pulled from registry",
            "indicators": [
                r"ImagePullBackOff",
                r"ErrImagePull",
                r"Failed to pull image",
                r"pull access denied",
                r"manifest.*not found",
                r"unauthorized.*authentication",
                r"registry.*timeout"
            ]
        },
        "CrashLoopBackOff": {
            "category": "Runtime Failures",
            "severity": "critical",
            "description": "Pod repeatedly crashes and restarts",
            "indicators": [
                r"CrashLoopBackOff",
                r"back-off restarting",
                r"container.*crashed",
                r"exited.*code \d+",
                r"runtime error",
                r"uncaught exception"
            ]
        },
        "OOMKilled": {
            "category": "Runtime Failures",
            "severity": "high",
            "description": "Container killed due to memory exhaustion",
            "indicators": [
                r"OOMKilled",
                r"memory.*exceeded",
                r"killed.*memory",
                r"out of memory",
                r"memory.*limit"
            ]
        },
        "Probe_failure": {
            "category": "Health Check Failures",
            "severity": "medium",
            "description": "Readiness or liveness probe failures",
            "indicators": [
                r"readiness.*probe.*failed",
                r"liveness.*probe.*failed",
                r"startup.*probe.*failed",
                r"health.*check.*failed",
                r"probe.*timeout",
                r"unhealthy.*probe"
            ]
        },
        "Dependency_timeout": {
            "category": "Dependency Issues",
            "severity": "medium",
            "description": "Deployment timeout due to dependency unavailability",
            "indicators": [
                r"dependency.*timeout",
                r"service.*unavailable",
                r"connection.*refused",
                r"database.*connection.*failed",
                r"api.*unreachable",
                r"network.*policy.*blocked"
            ]
        },
        "ReplicaSet_failure": {
            "category": "Deployment Process Issues",
            "severity": "medium",
            "description": "ReplicaSet creation or scaling failures",
            "indicators": [
                r"replicaset.*failed",
                r"scaling.*failed",
                r"progress.*deadline.*exceeded",
                r"replica.*timeout"
            ]
        },
        "Volume_mount_failure": {
            "category": "Critical Infrastructure",
            "severity": "high",
            "description": "Volume mount or configuration failures",
            "indicators": [
                r"volume.*mount.*failed",
                r"configmap.*not found",
                r"secret.*not found",
                r"persistentvolume.*failed",
                r"mount.*timeout"
            ]
        },
        "Resource_exhaustion": {
            "category": "Runtime Failures",
            "severity": "high",
            "description": "CPU or resource limit exceeded",
            "indicators": [
                r"cpu.*limit.*exceeded",
                r"throttling.*cpu",
                r"resource.*quota.*exceeded",
                r"insufficient.*cpu",
                r"insufficient.*memory"
            ]
        },
        "Network_policy_blocked": {
            "category": "Dependency Issues",
            "severity": "medium",
            "description": "Network traffic blocked by network policies",
            "indicators": [
                r"network.*policy.*blocked",
                r"connection.*blocked",
                r"traffic.*denied",
                r"firewall.*rule"
            ]
        },
        "Deployment_rollback": {
            "category": "Deployment Process Issues",
            "severity": "medium",
            "description": "Deployment rolled back due to failures",
            "indicators": [
                r"rolled back",
                r"rollback.*triggered",
                r"deployment.*rollback",
                r"reverting.*previous"
            ]
        }
    }

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.patterns: Dict[str, FailurePattern] = {}
        self.raw_failures: List[Dict[str, Any]] = []
        self.processing_stats = defaultdict(int)

        # Initialize patterns from rules
        for pattern_id, rules in self.PATTERN_RULES.items():
            self.patterns[pattern_id] = FailurePattern(
                pattern_id=pattern_id,
                category=rules["category"],
                severity=rules["severity"],
                description=rules["description"]
            )

    def load_parsed_data(self) -> Dict[str, Any]:
        """Load the parsed data from Child 1."""
        parsed_data_path = self.data_dir / "parsed-data.json"

        if not parsed_data_path.exists():
            raise FileNotFoundError(f"Parsed data not found: {parsed_data_path}")

        print(f"Loading parsed data from {parsed_data_path}")
        with open(parsed_data_path, 'r') as f:
            data = json.load(f)

        print(f"✓ Loaded {len(data.get('raw_data', {}))} data files")
        return data

    def extract_failure_events(self, parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract failure events from parsed deployment data."""
        failures = []

        print("\nExtracting failure events from deployment data...")

        # Process deployment records
        for record in parsed_data.get('deployment_records', []):
            service_data = record.get('data', {})
            metadata = service_data.get('metadata', {})
            service_name = metadata.get('service', 'unknown')

            # Extract deployment events
            deployment_events = service_data.get('deployment_events_last_30_days', [])
            for event in deployment_events:
                if event.get('outcome') not in ['success', 'active', 'healthy', 'running']:
                    failures.append({
                        'timestamp': event.get('timestamp'),
                        'service': service_name,
                        'event_type': event.get('event_type'),
                        'outcome': event.get('outcome'),
                        'image': event.get('image'),
                        'notes': event.get('notes'),
                        'pod_name': event.get('pod_name'),
                        'restart_count': event.get('restart_count'),
                        'source': 'deployment_events'
                    })

        # Process comprehensive deployment events data
        comprehensive_events = parsed_data.get('raw_data', {}).get('deployment-events-30days-comprehensive.json', {})
        if comprehensive_events:
            print("  Processing comprehensive deployment events...")
            for service_name, service_data in comprehensive_events.items():
                if service_name == 'metadata' or service_name == 'summary':
                    continue
                if not isinstance(service_data, dict):
                    continue

                # Extract from various event types
                for event_type in ['deployment_events', 'pod_events', 'replicaset_events']:
                    events = service_data.get(event_type, [])
                    for event in events:
                        if isinstance(event, dict):
                            # Check for failure indicators
                            outcome = event.get('outcome', '')
                            status = event.get('status', '')
                            event_type_str = event.get('type', event.get('event_type', ''))

                            # Include events that indicate issues
                            if any(negative in str(outcome + status + event_type_str).lower()
                                   for negative in ['fail', 'error', 'timeout', 'rollback', 'crash', 'backoff']):
                                failures.append({
                                    'timestamp': event.get('timestamp') or event.get('created_at'),
                                    'service': service_name,
                                    'event_type': event_type_str,
                                    'outcome': outcome or status,
                                    'image': event.get('image') or event.get('container_image'),
                                    'notes': event.get('reason') or event.get('message'),
                                    'pod_name': event.get('pod_name'),
                                    'restart_count': event.get('restart_count', event.get('restarts')),
                                    'source': f'comprehensive_{event_type}'
                                })

        # Process raw data files for additional failure information
        for filename, content in parsed_data.get('raw_data', {}).items():
            if 'failure' in filename.lower() or 'taxonomy' in filename.lower():
                self._extract_from_failure_files(filename, content, failures)

        print(f"✓ Extracted {len(failures)} potential failure events")
        return failures

    def _extract_from_failure_files(self, filename: str, content: Any, failures: List[Dict[str, Any]]):
        """Extract failures from specialized failure analysis files."""
        if not isinstance(content, dict):
            return

        # Extract from failure taxonomy
        if 'pattern_categories' in content:
            for pattern_id, pattern_data in content['pattern_categories'].items():
                if pattern_data.get('total_occurrences', 0) > 0:
                    for occurrence in pattern_data.get('sample_occurrences', []):
                        failures.append({
                            'timestamp': occurrence.get('timestamp'),
                            'service': occurrence.get('service'),
                            'pattern_type': pattern_id,
                            'image': occurrence.get('image'),
                            'source': f'taxonomy_{filename}'
                        })

        # Extract from classified failures
        if 'failures' in content:
            for failure in content['failures']:
                failures.append({
                    **failure,
                    'source': f'classified_{filename}'
                })

    def classify_failure_pattern(self, failure: Dict[str, Any]) -> Optional[str]:
        """Classify a failure event into a pattern category."""
        # Combine relevant text for pattern matching
        text_parts = []

        for field in ['event_type', 'outcome', 'notes', 'reason', 'message']:
            value = failure.get(field)
            if value and isinstance(value, str):
                text_parts.append(value.lower())

        combined_text = ' '.join(text_parts)

        # Try to match against pattern rules
        for pattern_id, rules in self.PATTERN_RULES.items():
            for indicator_pattern in rules['indicators']:
                if re.search(indicator_pattern, combined_text, re.IGNORECASE):
                    return pattern_id

        return "Other"

    def analyze_pattern(self, failure: Dict[str, Any]) -> str:
        """Analyze a failure and return its pattern classification."""
        pattern_id = self.classify_failure_pattern(failure)

        if pattern_id and pattern_id in self.patterns:
            pattern = self.patterns[pattern_id]
            pattern.total_occurrences += 1

            # Extract service distribution
            service = failure.get('service', 'unknown')
            pattern.distribution_by_service[service] = pattern.distribution_by_service.get(service, 0) + 1

            # Extract image context
            image = failure.get('image')
            if image:
                if 'images_affected' not in pattern.image_version_context:
                    pattern.image_version_context['images_affected'] = []
                if image not in pattern.image_version_context['images_affected']:
                    pattern.image_version_context['images_affected'].append(image)

            # Store sample occurrence
            if len(pattern.sample_occurrences) < 5:  # Keep max 5 samples
                pattern.sample_occurrences.append({
                    'timestamp': failure.get('timestamp'),
                    'service': service,
                    'image': image,
                    'event_type': failure.get('event_type'),
                    'outcome': failure.get('outcome')
                })

        return pattern_id or "Other"

    def calculate_time_distribution(self, failures: List[Dict[str, Any]]):
        """Calculate time distribution for each pattern."""
        print("\nCalculating time distributions...")

        # Group failures by pattern
        failures_by_pattern = defaultdict(list)
        for failure in failures:
            pattern_id = self.classify_failure_pattern(failure)
            if failure.get('timestamp'):
                failures_by_pattern[pattern_id].append(failure['timestamp'])

        # Calculate statistics for each pattern
        for pattern_id, timestamps in failures_by_pattern.items():
            if timestamps and pattern_id in self.patterns:
                parsed_times = []
                for ts in timestamps:
                    try:
                        # Handle ISO 8601 timestamps
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        if dt.tzinfo is not None:
                            dt = dt.replace(tzinfo=None)
                        parsed_times.append(dt)
                    except (ValueError, AttributeError):
                        continue

                if parsed_times:
                    parsed_times.sort()
                    time_span = (parsed_times[-1] - parsed_times[0]).total_seconds() / 3600

                    self.patterns[pattern_id].time_distribution = {
                        'frequency': len(parsed_times),
                        'time_span_hours': round(time_span, 2),
                        'earliest_timestamp': parsed_times[0].isoformat(),
                        'latest_timestamp': parsed_times[-1].isoformat()
                    }

        print("✓ Time distribution calculated")

    def generate_taxonomy_report(self, correlations: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive taxonomy report."""
        print("\nGenerating taxonomy report...")

        # Calculate image statistics for each pattern
        for pattern in self.patterns.values():
            if pattern.image_version_context.get('images_affected'):
                pattern.image_version_context['total_unique_images'] = len(pattern.image_version_context['images_affected'])

        # Build frequency statistics
        frequency_stats = {
            'by_pattern': {pid: p.total_occurrences for pid, p in self.patterns.items()},
            'by_severity': defaultdict(int),
            'temporal_distribution': {}
        }

        for pattern in self.patterns.values():
            frequency_stats['by_severity'][pattern.severity] += pattern.total_occurrences

        return {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'analysis_type': 'failure_pattern_analysis_with_correlations',
                'time_period': 'deployment_data_analysis',
                'services_analyzed': list(set(
                    f.get('service', 'unknown')
                    for f in self.raw_failures
                )),
                'total_pattern_categories': len(self.patterns),
                'pattern_matching_rules_version': '1.0.0'
            },
            'pattern_categories': {
                pid: p.to_dict() for pid, p in self.patterns.items()
            },
            'frequency_statistics': frequency_stats,
            'temporal_correlations': correlations,
            'verification': {
                'total_records_processed': len(self.raw_failures),
                'total_patterns_detected': sum(p.total_occurrences for p in self.patterns.values()),
                'coverage_percentage': round(
                    (sum(p.total_occurrences for p in self.patterns.values()) / max(len(self.raw_failures), 1)) * 100, 2
                )
            },
            'summary': {
                'total_pattern_types_defined': len(self.patterns),
                'total_pattern_types_with_occurrences': sum(1 for p in self.patterns.values() if p.total_occurrences > 0),
                'total_failures_across_all_patterns': sum(p.total_occurrences for p in self.patterns.values()),
                'most_common_pattern': max(
                    [(pid, p.total_occurrences) for pid, p in self.patterns.items()],
                    key=lambda x: x[1]
                ) if self.patterns else (None, 0),
                'deployment_failure_clusters_found': len(correlations.get('deployment_failure_clusters', [])),
                'overall_assessment': 'ANALYSIS_COMPLETE'
            }
        }

    def analyze_temporal_correlations(self) -> Dict[str, Any]:
        """Analyze correlations between deployment timestamps and failure spikes."""
        print("\nAnalyzing temporal correlations between deployments and failures...")

        correlations = {
            'deployment_failure_clusters': [],
            'high_frequency_periods': [],
            'service_specific_patterns': {}
        }

        # Group failures by service and time window
        service_failures = defaultdict(list)
        for failure in self.raw_failures:
            if failure.get('timestamp') and failure.get('service'):
                try:
                    dt = datetime.fromisoformat(failure['timestamp'].replace('Z', '+00:00'))
                    if dt.tzinfo is not None:
                        dt = dt.replace(tzinfo=None)
                    service_failures[failure['service']].append((dt, failure))
                except (ValueError, AttributeError):
                    continue

        # Look for clusters within 24-hour windows
        for service, failures in service_failures.items():
            if len(failures) < 2:
                continue

            failures.sort(key=lambda x: x[0])

            # Find time clusters (failures within 24 hours)
            clusters = []
            current_cluster = [failures[0]]

            for dt, failure in failures[1:]:
                time_diff = (dt - current_cluster[0][0]).total_seconds() / 3600
                if time_diff <= 24:  # Within 24 hours
                    current_cluster.append((dt, failure))
                else:
                    if len(current_cluster) >= 2:
                        clusters.append(current_cluster)
                    current_cluster = [(dt, failure)]

            if len(current_cluster) >= 2:
                clusters.append(current_cluster)

            # Record significant clusters
            for cluster in clusters:
                if len(cluster) >= 2:
                    time_span = (cluster[-1][0] - cluster[0][0]).total_seconds() / 3600
                    correlations['deployment_failure_clusters'].append({
                        'service': service,
                        'failure_count': len(cluster),
                        'time_span_hours': round(time_span, 2),
                        'start_time': cluster[0][0].isoformat(),
                        'end_time': cluster[-1][0].isoformat(),
                        'patterns': list(set(f.get('pattern_type', 'Other') for _, f in cluster))
                    })

        print(f"✓ Found {len(correlations['deployment_failure_clusters'])} deployment-failure clusters")
        return correlations

    def print_pattern_summary(self):
        """Print summary of pattern analysis to console."""
        print("\n" + "=" * 80)
        print("FAILURE PATTERN ANALYSIS SUMMARY")
        print("=" * 80)

        print(f"\nTotal patterns analyzed: {len(self.patterns)}")
        print(f"Total failures processed: {len(self.raw_failures)}")

        # Sort patterns by occurrence count
        sorted_patterns = sorted(
            self.patterns.items(),
            key=lambda x: x[1].total_occurrences,
            reverse=True
        )

        print("\n" + "-" * 80)
        print("Pattern Distribution:")
        print("-" * 80)
        print(f"{'Pattern':<25} {'Severity':<10} {'Category':<25} {'Count':>8}")
        print("-" * 80)

        for pattern_id, pattern in sorted_patterns:
            if pattern.total_occurrences > 0:
                print(f"{pattern_id:<25} {pattern.severity:<10} {pattern.category:<25} {pattern.total_occurrences:>8}")

        # Time distribution analysis
        print("\n" + "-" * 80)
        print("Time Distribution Analysis:")
        print("-" * 80)

        for pattern_id, pattern in sorted_patterns:
            if pattern.total_occurrences > 0 and pattern.time_distribution:
                td = pattern.time_distribution
                print(f"\n{pattern_id}:")
                print(f"  Frequency: {td['frequency']} occurrences")
                print(f"  Time span: {td['time_span_hours']:.1f} hours")
                print(f"  Earliest: {td['earliest_timestamp']}")
                print(f"  Latest:   {td['latest_timestamp']}")

        # Service distribution
        print("\n" + "-" * 80)
        print("Service Impact Analysis:")
        print("-" * 80)

        service_impact = defaultdict(lambda: defaultdict(int))
        for pattern_id, pattern in self.patterns.items():
            for service, count in pattern.distribution_by_service.items():
                service_impact[service][pattern_id] += count

        for service, patterns in sorted(service_impact.items(), key=lambda x: sum(x[1].values()), reverse=True):
            total = sum(patterns.values())
            print(f"\n{service} (total failures: {total}):")
            for pattern_id, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True):
                print(f"  {pattern_id}: {count}")

        print("\n" + "=" * 80)

    def run_analysis(self) -> Dict[str, Any]:
        """Run complete failure pattern analysis."""
        print("Starting failure pattern analysis...")

        # Load parsed data
        parsed_data = self.load_parsed_data()

        # Extract failure events
        self.raw_failures = self.extract_failure_events(parsed_data)

        print(f"\nAnalyzing {len(self.raw_failures)} failure events...")

        # Classify each failure
        for i, failure in enumerate(self.raw_failures):
            pattern_id = self.analyze_pattern(failure)
            self.processing_stats[pattern_id] += 1

            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(self.raw_failures)} events...")

        # Calculate time distributions
        self.calculate_time_distribution(self.raw_failures)

        # Analyze temporal correlations
        correlations = self.analyze_temporal_correlations()

        # Generate taxonomy report
        taxonomy = self.generate_taxonomy_report(correlations)

        # Print console output
        self.print_pattern_summary()

        return taxonomy


def main():
    """Main entry point for pattern analysis."""
    # Setup paths
    script_dir = Path(__file__).parent
    data_dir = script_dir

    print("=" * 80)
    print("DEPLOYMENT FAILURE PATTERN ANALYZER")
    print("=" * 80)
    print(f"Data directory: {data_dir}")
    print()

    # Run analysis
    analyzer = FailurePatternAnalyzer(data_dir)

    try:
        taxonomy = analyzer.run_analysis()

        # Save results
        output_path = data_dir / "failure-pattern-analysis.json"
        print(f"\nSaving analysis results to {output_path}...")

        with open(output_path, 'w') as f:
            json.dump(taxonomy, f, indent=2, default=str)

        print(f"✓ Analysis complete!")
        print(f"✓ Results saved to {output_path.name}")

        return taxonomy

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("Please ensure parsed-data.json exists from Child 1 analysis")
        return None
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    main()
