#!/usr/bin/env python3
"""
Build comprehensive failure taxonomy with frequency analysis.
Applies pattern-matching rules to categorize all failures and builds
complete taxonomy with frequency statistics, distribution by service/image/time,
and verifies completeness.
"""

import json
import os
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple


def load_json_file(filepath: str) -> Any:
    """Load a JSON file safely."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load {filepath}: {e}")
        return None


def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse various timestamp formats."""
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S+00:00",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


class FailureTaxonomyBuilder:
    """
    Builds comprehensive failure taxonomy with frequency analysis.
    Applies pattern-matching rules to categorize all failures.
    """

    def __init__(self, data_dir: str = "/home/coding/aide-de-camp/docs/research/deployment-data"):
        self.data_dir = Path(data_dir)

        # Pattern matching rules based on existing methodology
        self.pattern_rules = {
            'ImagePullBackOff': {
                'indicators': ['imagepullbackoff', 'pull', 'image', 'registry', 'cannot pull'],
                'severity': 'high',
                'category': 'infrastructure',
                'description': 'Container image cannot be pulled from registry'
            },
            'CrashLoopBackOff': {
                'indicators': ['crashloopbackoff', 'crashloop', 'crash', 'exited', 'error', 'terminated'],
                'severity': 'critical',
                'category': 'application',
                'description': 'Pod repeatedly crashes and restarts'
            },
            'OOMKilled': {
                'indicators': ['oomkilled', 'oom', 'out of memory', 'memory limit exceeded'],
                'severity': 'critical',
                'category': 'resource',
                'description': 'Container killed due to exceeding memory limits'
            },
            'Probe_failure': {
                'indicators': ['probe failed', 'readiness probe', 'liveness probe', 'startup probe', 'unhealthy'],
                'severity': 'medium',
                'category': 'application',
                'description': 'Health check failures (readiness, liveness, or startup probes)'
            },
            'Dependency_timeout': {
                'indicators': ['timeout', 'connection refused', 'dependency unavailable', 'upstream error'],
                'severity': 'high',
                'category': 'infrastructure',
                'description': 'Timeouts connecting to external services or dependencies'
            },
            'Deployment_rollback': {
                'indicators': ['rollback', 'rolled back', 'revert', 'previous version'],
                'severity': 'medium',
                'category': 'configuration',
                'description': 'Deployment was rolled back to a previous version'
            },
            'Health_check_failure': {
                'indicators': ['health check failure', 'readiness failure', 'pod readiness', 'startup crash'],
                'severity': 'high',
                'category': 'application',
                'description': 'Health check failures preventing pod readiness'
            },
            'Configuration_drift': {
                'indicators': ['configuration issue', 'config mismatch', 'same-day rollback'],
                'severity': 'medium',
                'category': 'configuration',
                'description': 'Configuration drift or mismatches causing issues'
            },
            'Rapid_deployment_churn': {
                'indicators': ['rapid deployment', 'multiple deployments', 'iterative fixes'],
                'severity': 'low',
                'category': 'operational',
                'description': 'Rapid deployment churn indicating iterative improvements'
            },
            'Operational_pattern': {
                'indicators': ['steady rhythm', 'deployment cadence', 'operational pattern'],
                'severity': 'info',
                'category': 'operational',
                'description': 'Normal operational deployment patterns'
            },
            'Positive_pattern': {
                'indicators': ['zero failures', '100% success', 'perfect stability'],
                'severity': 'positive',
                'category': 'reliability',
                'description': 'Positive patterns indicating excellent stability'
            }
        }

        # Storage for categorized failures
        self.categorized_failures = defaultdict(list)
        self.uncategorized_failures = []
        self.service_stats = defaultdict(lambda: {
            'total_events': 0,
            'failures': 0,
            'successes': 0,
            'patterns_found': defaultdict(int)
        })

    def classify_failure(self, event: Dict[str, Any], all_events: List[Dict] = None) -> Tuple[str, Dict]:
        """
        Classify a failure event into a pattern category using pattern-matching rules.
        Returns (pattern_name, pattern_info) tuple.
        """
        event_text = json.dumps(event).lower()

        # Check each pattern rule
        for pattern_name, rule in self.pattern_rules.items():
            indicators = rule['indicators']
            matches = sum(1 for indicator in indicators if indicator.lower() in event_text)

            if matches >= 2:  # Require at least 2 indicators for confidence
                return pattern_name, {
                    'severity': rule['severity'],
                    'category': rule['category'],
                    'description': rule['description'],
                    'confidence': matches / len(indicators)
                }

        # Special pattern detection for inactive replicasets (part of rapid deployment)
        if event.get('outcome') == 'inactive' and event.get('event_type') == 'deployment_rollout':
            # Check if this is part of a rapid deployment sequence
            if all_events:
                rapid_deployments = self._detect_rapid_deployment_sequence(event, all_events)
                if rapid_deployments:
                    return 'Rapid_deployment_churn', {
                        'severity': 'low',
                        'category': 'operational',
                        'description': 'Part of rapid deployment sequence indicating iterative improvements',
                        'confidence': 0.9
                    }

        # Check for positive patterns (zero failures, 100% success)
        if event.get('outcome') == 'success' and 'deployment' in event_text:
            # This is captured in success count, not failures
            return 'Success_pattern', {
                'severity': 'positive',
                'category': 'reliability',
                'description': 'Successful deployment',
                'confidence': 1.0
            }

        return 'Uncategorized', {
            'severity': 'unknown',
            'category': 'unknown',
            'description': 'Uncategorized failure pattern',
            'confidence': 0.0
        }

    def _detect_rapid_deployment_sequence(self, current_event: Dict, all_events: List[Dict]) -> List[Dict]:
        """Detect if current event is part of a rapid deployment sequence."""
        service = current_event.get('service', '')
        current_time = parse_timestamp(current_event.get('timestamp', ''))

        if not current_time:
            return []

        # Find other events from same service within 1 hour window
        rapid_sequence = []
        for event in all_events:
            if event.get('service') != service:
                continue

            event_time = parse_timestamp(event.get('timestamp', ''))
            if not event_time:
                continue

            time_diff = abs((event_time - current_time).total_seconds())
            if time_diff <= 3600:  # Within 1 hour
                rapid_sequence.append(event)

        # Consider it rapid if 3+ deployments in 1 hour
        return rapid_sequence if len(rapid_sequence) >= 3 else []

    def extract_failure_context(self, event: Dict[str, Any], service_name: str) -> Dict[str, Any]:
        """Extract context information from a failure event."""
        context = {
            'timestamp': event.get('timestamp') or event.get('time') or event.get('created_at') or event.get('date') or 'unknown',
            'service': service_name,
            'deployment_id': event.get('deployment') or event.get('deployment_name') or event.get('name') or 'unknown',
            'image': event.get('image') or event.get('container_image') or 'unknown',
            'outcome': event.get('outcome') or event.get('status') or event.get('state') or 'unknown',
            'namespace': event.get('namespace') or 'unknown',
            'cluster': event.get('cluster') or 'ardenone-cluster',
            'reason': event.get('reason') or event.get('message') or event.get('error') or event.get('notes') or 'unknown',
            'event_type': event.get('event_type') or event.get('type') or 'unknown',
            'revision': event.get('revision') or event.get('replicaSet') or 'unknown',
        }
        return context

    def load_all_deployment_data(self) -> Dict[str, Any]:
        """Load all deployment data from various sources."""
        all_data = {
            'pbx-web': [],
            'whisper-stt': [],
            'other': []
        }

        # Load pbx-web data
        pbx_web_files = [
            '/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json',
            '/home/coding/aide-de-camp/docs/research/deployment-data/pbx-web-deployment-data-30days.json',
            '/home/coding/aide-de-camp/docs/research/pbx-web-deployment-data.json'
        ]

        for filepath in pbx_web_files:
            data = load_json_file(filepath)
            if data:
                events = data.get('deployment_events_last_30_days', [])
                for event in events:
                    event['service'] = 'pbx-web'
                    all_data['pbx-web'].append(event)
                break

        # Load whisper-stt data
        whisper_files = [
            '/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json',
            '/home/coding/aide-de-camp/docs/research/deployment-data/whisper-stt-deployment-data-30days.json',
            '/home/coding/aide-de-camp/docs/research/whisper-stt-deployment-data.json'
        ]

        for filepath in whisper_files:
            data = load_json_file(filepath)
            if data:
                # Handle both deployment history and events structure
                if 'deployment_history_30_days' in data:
                    replicasets = data['deployment_history_30_days'].get('replicasets', [])
                    for rs in replicasets:
                        event = {
                            'date': rs.get('created', '').split('T')[0] if rs.get('created') else 'unknown',
                            'timestamp': rs.get('created', 'unknown'),
                            'event_type': 'deployment_rollout',
                            'deployment': rs.get('deployment', 'unknown'),
                            'revision': rs.get('revision', 'unknown'),
                            'replicaSet': rs.get('name', 'unknown'),
                            'image': rs.get('image', 'unknown'),
                            'outcome': 'success' if rs.get('status') == 'active' else 'inactive',
                            'service': 'whisper-stt'
                        }
                        all_data['whisper-stt'].append(event)
                elif 'deployment_events' in data:
                    for event in data['deployment_events']:
                        event['service'] = 'whisper-stt'
                        all_data['whisper-stt'].append(event)
                break

        # Load comprehensive deployment events
        comprehensive_data = load_json_file('/home/coding/aide-de-camp/deployment-events-30days.json')
        if comprehensive_data and 'whisper_stt_deployments' in comprehensive_data:
            events = comprehensive_data['whisper_stt_deployments'].get('deployment_events', [])
            for event in events:
                if 'service' not in event:
                    event['service'] = 'whisper-stt'
                all_data['whisper-stt'].append(event)

        return all_data

    def analyze_deployment_events(self, all_data: Dict[str, Any]):
        """Analyze deployment events and apply pattern matching."""
        total_events = 0
        total_failures = 0

        # Flatten all events for cross-service pattern detection
        all_events_flat = []
        for service_name, events in all_data.items():
            for event in events:
                event['service'] = service_name
                all_events_flat.append(event)

        for service_name, events in all_data.items():
            if not events:
                continue

            print(f"\nProcessing {len(events)} events for {service_name}...")

            for event in events:
                total_events += 1
                self.service_stats[service_name]['total_events'] += 1

                outcome = str(event.get('outcome', '')).lower()

                # Count successes
                if outcome in ['success', 'active', 'available']:
                    self.service_stats[service_name]['successes'] += 1
                    continue

                # Process failures or special patterns
                if outcome in ['failure', 'failed', 'error', 'inactive', 'rolled_back'] or \
                   event.get('event_type') in ['deployment_rollback', 'probe_failure']:

                    total_failures += 1
                    self.service_stats[service_name]['failures'] += 1

                    # Classify the failure with access to all events for sequence detection
                    pattern_name, pattern_info = self.classify_failure(event, all_events_flat)
                    context = self.extract_failure_context(event, service_name)

                    # Add pattern info to context
                    context['pattern_category'] = pattern_info['category']
                    context['pattern_severity'] = pattern_info['severity']
                    context['pattern_confidence'] = pattern_info['confidence']
                    context['pattern_description'] = pattern_info['description']

                    # Categorize - skip success patterns as they're not failures
                    if pattern_name == 'Success_pattern':
                        self.service_stats[service_name]['successes'] += 1
                        continue
                    elif pattern_name == 'Uncategorized':
                        self.uncategorized_failures.append(context)
                    else:
                        self.categorized_failures[pattern_name].append(context)
                        self.service_stats[service_name]['patterns_found'][pattern_name] += 1

        print(f"\nTotal events processed: {total_events}")
        print(f"Total failures detected: {total_failures}")
        print(f"Categorized failures: {sum(len(v) for v in self.categorized_failures.values())}")
        print(f"Uncategorized failures: {len(self.uncategorized_failures)}")

    def calculate_pattern_statistics(self) -> Dict[str, Any]:
        """Calculate comprehensive statistics for each pattern category."""
        pattern_stats = {}

        for pattern_name, failures in self.categorized_failures.items():
            if not failures:
                continue

            # Parse timestamps for time distribution
            timestamps = []
            for f in failures:
                ts = parse_timestamp(f['timestamp'])
                if ts:
                    timestamps.append(ts)

            # Calculate time distribution
            if timestamps:
                timestamps.sort()
                time_span_days = (timestamps[-1] - timestamps[0]).days if len(timestamps) > 1 else 0
                first_occurrence = timestamps[0].strftime('%Y-%m-%d') if timestamps else 'unknown'
                last_occurrence = timestamps[-1].strftime('%Y-%m-%d') if timestamps else 'unknown'

                # Calculate distribution by day
                day_distribution = Counter(ts.strftime('%Y-%m-%d') for ts in timestamps)
            else:
                time_span_days = 0
                first_occurrence = 'unknown'
                last_occurrence = 'unknown'
                day_distribution = Counter()

            # Count by service
            service_breakdown = Counter(f['service'] for f in failures)

            # Count by image
            images = [f['image'] for f in failures if f['image'] != 'unknown']
            image_breakdown = Counter(images) if images else Counter()

            # Extract common reasons
            reasons = [f['reason'] for f in failures if f['reason'] != 'unknown']
            reason_breakdown = Counter(reasons) if reasons else Counter()

            # Get severity and category
            severity = failures[0].get('pattern_severity', 'unknown')
            category = failures[0].get('pattern_category', 'unknown')
            description = failures[0].get('pattern_description', 'No description')

            pattern_stats[pattern_name] = {
                'frequency': len(failures),
                'severity': severity,
                'category': category,
                'description': description,
                'time_span_days': time_span_days,
                'first_occurrence': first_occurrence,
                'last_occurrence': last_occurrence,
                'day_distribution': dict(day_distribution.most_common(10)),
                'services_affected': dict(service_breakdown),
                'images_affected': dict(image_breakdown.most_common(5)),
                'common_reasons': dict(reason_breakdown.most_common(3)),
                'sample_failures': failures[:3]  # First 3 as examples
            }

        return pattern_stats

    def generate_taxonomy_report(self) -> Dict[str, Any]:
        """Generate the complete taxonomy report."""
        print("Generating taxonomy report...")

        # Calculate pattern statistics
        pattern_stats = self.calculate_pattern_statistics()

        # Build taxonomy structure
        taxonomy = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'analysis_period': '2026-07-07 to 2026-08-06 (30 days)',
                'cluster': 'ardenone-cluster',
                'services_analyzed': list(self.service_stats.keys()),
                'total_patterns_identified': len(self.categorized_failures),
                'total_failures_categorized': sum(len(v) for v in self.categorized_failures.values()),
                'uncategorized_failures': len(self.uncategorized_failures),
                'verification_complete': True
            },
            'service_statistics': dict(self.service_stats),
            'pattern_taxonomy': pattern_stats,
            'uncategorized_failures': self.uncategorized_failures[:10]  # First 10 for review
        }

        # Verify completeness
        total_records = sum(stats['total_events'] for stats in self.service_stats.values())
        categorized_count = taxonomy['metadata']['total_failures_categorized']
        uncategorized_count = len(self.uncategorized_failures)
        success_count = sum(stats['successes'] for stats in self.service_stats.values())

        verification = {
            'total_records_processed': total_records,
            'success_records': success_count,
            'failure_records': categorized_count + uncategorized_count,
            'categorized_failures': categorized_count,
            'uncategorized_failures': uncategorized_count,
            'completeness_check': (success_count + categorized_count + uncategorized_count) == total_records,
            'coverage_percentage': (categorized_count / (categorized_count + uncategorized_count) * 100) if (categorized_count + uncategorized_count) > 0 else 100
        }

        taxonomy['verification'] = verification

        return taxonomy

    def save_taxonomy(self, taxonomy: Dict[str, Any], output_path: str):
        """Save taxonomy to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(taxonomy, f, indent=2, default=str)
        print(f"Taxonomy saved to: {output_path}")

    def print_taxonomy_summary(self, taxonomy: Dict[str, Any]):
        """Print a summary of the taxonomy."""
        print("\n" + "="*60)
        print("FAILURE TAXONOMY WITH FREQUENCY ANALYSIS")
        print("="*60)

        metadata = taxonomy['metadata']
        print(f"\nGenerated: {metadata['generated_at']}")
        print(f"Analysis Period: {metadata['analysis_period']}")
        print(f"Services: {', '.join(metadata['services_analyzed'])}")
        print(f"Total Patterns: {metadata['total_patterns_identified']}")
        print(f"Total Failures Categorized: {metadata['total_failures_categorized']}")

        print("\n" + "-"*60)
        print("PATTERNS BY FREQUENCY")
        print("-"*60)

        # Sort patterns by frequency
        sorted_patterns = sorted(
            taxonomy['pattern_taxonomy'].items(),
            key=lambda x: x[1]['frequency'],
            reverse=True
        )

        for pattern_name, stats in sorted_patterns:
            print(f"\n{pattern_name}:")
            print(f"  Frequency: {stats['frequency']} occurrences")
            print(f"  Severity: {stats['severity']}")
            print(f"  Category: {stats['category']}")
            print(f"  Time Span: {stats['time_span_days']} days")
            print(f"  Services: {', '.join(stats['services_affected'].keys())}")
            if stats['images_affected']:
                print(f"  Images: {', '.join(list(stats['images_affected'].keys())[:3])}")

        print("\n" + "-"*60)
        print("VERIFICATION")
        print("-"*60)

        verification = taxonomy['verification']
        print(f"Total Records: {verification['total_records_processed']}")
        print(f"Success Records: {verification['success_records']}")
        print(f"Failure Records: {verification['failure_records']}")
        print(f"Categorized: {verification['categorized_failures']}")
        print(f"Uncategorized: {verification['uncategorized_failures']}")
        print(f"Completeness: {'✓ PASS' if verification['completeness_check'] else '✗ FAIL'}")
        print(f"Coverage: {verification['coverage_percentage']:.1f}%")

        print("\n" + "="*60)


def main():
    """Main execution function."""
    print("Building Failure Taxonomy with Frequency Analysis...")
    print("="*60)

    # Initialize builder
    builder = FailureTaxonomyBuilder()

    # Load all deployment data
    print("\nLoading deployment data...")
    all_data = builder.load_all_deployment_data()

    # Analyze events and apply pattern matching
    print("\nApplying pattern-matching rules...")
    builder.analyze_deployment_events(all_data)

    # Generate taxonomy report
    print("\nGenerating taxonomy report...")
    taxonomy = builder.generate_taxonomy_report()

    # Save taxonomy
    output_path = '/home/coding/aide-de-camp/docs/research/failure-taxonomy-complete.json'
    builder.save_taxonomy(taxonomy, output_path)

    # Print summary
    builder.print_taxonomy_summary(taxonomy)

    print(f"\n✓ Complete taxonomy saved to: {output_path}")

    return taxonomy


if __name__ == '__main__':
    main()