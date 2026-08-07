#!/usr/bin/env python3
"""
Parse and categorize failure patterns from deployment data.
Creates a comprehensive taxonomy of failure patterns with frequency, time distribution, and context.
"""

import json
import os
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pathlib import Path


def load_json_file(filepath):
    """Load a JSON file safely."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load {filepath}: {e}")
        return None


def parse_timestamp(timestamp_str):
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


class FailurePatternAnalyzer:
    """Analyzes failure patterns across deployment data."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.patterns = {
            'ImagePullBackOff': [],
            'CrashLoopBackOff': [],
            'OOMKilled': [],
            'Probe_failure': [],
            'Dependency_timeout': [],
            'Other': []
        }
        self.service_stats = defaultdict(lambda: {
            'total_events': 0,
            'failures': 0,
            'successes': 0
        })

    def classify_failure(self, event):
        """Classify a failure event into a pattern category."""
        event_text = json.dumps(event).lower()

        # ImagePullBackOff patterns
        if any(kw in event_text for kw in ['imagepullbackoff', 'pull', 'image', 'registry', 'cannot pull']):
            if 'imagepullbackoff' in event_text or 'pull' in event_text:
                return 'ImagePullBackOff'

        # CrashLoopBackOff patterns
        if any(kw in event_text for kw in ['crashloopbackoff', 'crash', 'exited', 'error', 'terminated']):
            if 'crashloopbackoff' in event_text or 'crashloop' in event_text:
                return 'CrashLoopBackOff'

        # OOMKilled patterns
        if any(kw in event_text for kw in ['oomkilled', 'oom', 'out of memory', 'memory limit']):
            if 'oomkilled' in event_text or 'oom' in event_text:
                return 'OOMKilled'

        # Probe failure patterns
        if any(kw in event_text for kw in ['probe', 'readiness', 'liveness', 'startup', 'healthcheck']):
            if 'probe' in event_text and ('failed' in event_text or 'timeout' in event_text):
                return 'Probe_failure'

        # Dependency timeout patterns
        if any(kw in event_text for kw in ['timeout', 'dependency', 'connection', 'database', 'network']):
            if 'timeout' in event_text or 'dependency' in event_text:
                return 'Dependency_timeout'

        return 'Other'

    def extract_failure_context(self, event, service_name):
        """Extract context information from a failure event."""
        context = {
            'timestamp': event.get('timestamp') or event.get('time') or event.get('created_at') or 'unknown',
            'service': service_name,
            'deployment_id': event.get('deployment_id') or event.get('deployment') or event.get('name') or 'unknown',
            'image': event.get('image') or event.get('container_image') or 'unknown',
            'outcome': event.get('outcome') or event.get('status') or event.get('state') or 'unknown',
            'namespace': event.get('namespace') or 'unknown',
            'cluster': event.get('cluster') or 'unknown',
            'reason': event.get('reason') or event.get('message') or event.get('error') or 'unknown',
            'event_type': event.get('event_type') or event.get('type') or 'unknown',
        }
        return context

    def parse_comprehensive_data(self):
        """Parse the comprehensive deployment events file."""
        filepath = self.data_dir / 'deployment-events-30days-comprehensive.json'
        data = load_json_file(filepath)
        if not data:
            return

        for service_name in ['pbx-web', 'whisper-stt']:
            if service_name not in data:
                continue

            service_data = data[service_name]
            events = service_data.get('deployment_events', [])
            self.service_stats[service_name]['total_events'] += len(events)

            for event in events:
                outcome = event.get('outcome', '').lower()
                if outcome == 'success':
                    self.service_stats[service_name]['successes'] += 1
                    continue

                if outcome in ['failure', 'failed', 'error', 'inactive']:
                    self.service_stats[service_name]['failures'] += 1
                    pattern = self.classify_failure(event)
                    context = self.extract_failure_context(event, service_name)
                    self.patterns[pattern].append(context)

    def parse_workflow_data(self):
        """Parse workflow failure data."""
        # Parse pbx-web workflows
        filepath = self.data_dir / 'pbx-web-raw-workflows.json'
        data = load_json_file(filepath)
        if data:
            self._parse_workflow_file(data, 'pbx-web')

        # Parse whisper-stt workflows
        filepath = self.data_dir / 'whisper-stt-raw-workflows.json'
        data = load_json_file(filepath)
        if data:
            self._parse_workflow_file(data, 'whisper-stt')

    def _parse_workflow_file(self, data, service_name):
        """Parse workflow data for a service."""
        workflows = data if isinstance(data, list) else data.get('workflows', [])
        self.service_stats[service_name]['total_events'] += len(workflows)

        for workflow in workflows:
            phase = workflow.get('status', {}).get('phase', '').lower()
            if phase in ['failed', 'error']:
                self.service_stats[service_name]['failures'] += 1
                pattern = self.classify_failure(workflow)
                context = self.extract_failure_context(workflow, service_name)
                self.patterns[pattern].append(context)
            elif phase == 'succeeded':
                self.service_stats[service_name]['successes'] += 1

    def parse_metrics_data(self):
        """Parse metrics files for additional failure context."""
        for service_name in ['pbx-web', 'whisper-stt']:
            filepath = self.data_dir / f'{service_name}-metrics.json'
            data = load_json_file(filepath)
            if not data:
                continue

            # Look for failure indicators in metrics
            for metric_name, metric_value in data.items():
                if isinstance(metric_value, dict) and 'errors' in metric_name.lower():
                    errors = metric_value.get('errors', [])
                    for error in errors:
                        self.service_stats[service_name]['failures'] += 1
                        pattern = self.classify_failure(error)
                        context = self.extract_failure_context(error, service_name)
                        self.patterns[pattern].append(context)

    def calculate_pattern_statistics(self):
        """Calculate statistics for each pattern category."""
        stats = {}

        for pattern_name, failures in self.patterns.items():
            if not failures:
                continue

            # Parse timestamps
            timestamps = []
            for f in failures:
                ts = parse_timestamp(f['timestamp'])
                if ts:
                    timestamps.append(ts)

            # Calculate time distribution
            if timestamps:
                timestamps.sort()
                time_span = (timestamps[-1] - timestamps[0]).days if len(timestamps) > 1 else 0
                first_occurrence = timestamps[0].isoformat() if timestamps else 'unknown'
                last_occurrence = timestamps[-1].isoformat() if timestamps else 'unknown'
            else:
                time_span = 0
                first_occurrence = 'unknown'
                last_occurrence = 'unknown'

            # Count by service
            service_breakdown = Counter(f['service'] for f in failures)

            # Count by image (if available)
            images = [f['image'] for f in failures if f['image'] != 'unknown']
            image_breakdown = Counter(images) if images else {}

            # Extract common reasons
            reasons = [f['reason'] for f in failures if f['reason'] != 'unknown']
            reason_breakdown = Counter(reasons) if reasons else {}

            stats[pattern_name] = {
                'frequency': len(failures),
                'time_span_days': time_span,
                'first_occurrence': first_occurrence,
                'last_occurrence': last_occurrence,
                'services_affected': dict(service_breakdown),
                'images_affected': dict(image_breakdown),
                'common_reasons': dict(reason_breakdown.most_common(5))
            }

        return stats

    def generate_taxonomy(self):
        """Generate the complete failure taxonomy."""
        # Parse all data sources
        print("Parsing comprehensive deployment data...")
        self.parse_comprehensive_data()

        print("Parsing workflow data...")
        self.parse_workflow_data()

        print("Parsing metrics data...")
        self.parse_metrics_data()

        print("Calculating pattern statistics...")
        pattern_stats = self.calculate_pattern_statistics()

        # Build taxonomy structure
        taxonomy = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'data_directory': str(self.data_dir),
                'total_patterns_identified': len(self.patterns),
                'total_failures_analyzed': sum(len(p) for p in self.patterns.values())
            },
            'service_statistics': dict(self.service_stats),
            'pattern_taxonomy': {}
        }

        for pattern_name in self.patterns.keys():
            taxonomy['pattern_taxonomy'][pattern_name] = {
                'description': self._get_pattern_description(pattern_name),
                'severity': self._get_pattern_severity(pattern_name),
                'statistics': pattern_stats.get(pattern_name, {
                    'frequency': 0,
                    'time_span_days': 0,
                    'services_affected': {},
                    'images_affected': {}
                }),
                'sample_failures': self.patterns[pattern_name][:5]  # First 5 as examples
            }

        return taxonomy

    def _get_pattern_description(self, pattern_name):
        """Get description for a pattern category."""
        descriptions = {
            'ImagePullBackOff': 'Container image cannot be pulled from registry (authentication issues, missing images, network problems)',
            'CrashLoopBackOff': 'Pod repeatedly crashes and restarts (application errors, misconfiguration, runtime exceptions)',
            'OOMKilled': 'Container killed due to exceeding memory limits (memory leaks, insufficient limits, high load)',
            'Probe_failure': 'Health check failures (readiness, liveness, or startup probes failing)',
            'Dependency_timeout': 'Timeouts connecting to external services (databases, APIs, network services)',
            'Other': 'Uncategorized or rare failure patterns not matching standard categories'
        }
        return descriptions.get(pattern_name, 'Unknown pattern')

    def _get_pattern_severity(self, pattern_name):
        """Get severity level for a pattern category."""
        severity = {
            'ImagePullBackOff': 'high',
            'CrashLoopBackOff': 'critical',
            'OOMKilled': 'critical',
            'Probe_failure': 'medium',
            'Dependency_timeout': 'high',
            'Other': 'variable'
        }
        return severity.get(pattern_name, 'unknown')


def generate_markdown_summary(taxonomy, output_path):
    """Generate a markdown summary of the failure taxonomy."""
    lines = [
        '# Failure Pattern Taxonomy',
        '',
        '*Generated from deployment data analysis*',
        '',
        f"**Analysis Date:** {taxonomy['metadata']['generated_at']}",
        f"**Total Patterns:** {taxonomy['metadata']['total_patterns_identified']}",
        f"**Total Failures Analyzed:** {taxonomy['metadata']['total_failures_analyzed']}",
        '',
        '## Service Statistics',
        ''
    ]

    # Service statistics table
    lines.extend([
        '| Service | Total Events | Failures | Successes |',
        '|---------|--------------|----------|-----------|'
    ])

    for service, stats in taxonomy['service_statistics'].items():
        lines.append(
            f"| {service} | {stats['total_events']} | {stats['failures']} | {stats['successes']} |"
        )

    lines.extend(['', '## Pattern Categories', ''])

    # Pattern details
    for pattern_name, pattern_data in taxonomy['pattern_taxonomy'].items():
        stats = pattern_data['statistics']

        lines.extend([
            f"### {pattern_name}",
            '',
            f"**Description:** {pattern_data['description']}",
            f"**Severity:** {pattern_data['severity']}",
            '',
            '**Statistics:**',
            f"- Frequency: {stats.get('frequency', 0)} occurrences",
            f"- Time span: {stats.get('time_span_days', 0)} days",
            f"- First occurrence: {stats.get('first_occurrence', 'unknown')}",
            f"- Last occurrence: {stats.get('last_occurrence', 'unknown')}",
        ])

        if stats.get('services_affected'):
            lines.append('**Services affected:**')
            for service, count in stats['services_affected'].items():
                lines.append(f"  - {service}: {count} occurrences")
            lines.append('')

        if stats.get('images_affected'):
            lines.append('**Images affected:**')
            for image, count in list(stats['images_affected'].items())[:5]:
                lines.append(f"  - {image}: {count} occurrences")
            lines.append('')

        if stats.get('common_reasons'):
            lines.append('**Common reasons:**')
            for reason, count in stats['common_reasons'].items():
                lines.append(f"  - {reason}: {count} occurrences")
            lines.append('')

        lines.extend(['', '---', '', ''])

    # Write to file
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Markdown summary written to: {output_path}")


def main():
    """Main execution function."""
    data_dir = Path('/home/coding/aide-de-camp/docs/research/deployment-data')

    print("Starting failure pattern analysis...")
    print(f"Data directory: {data_dir}")
    print()

    # Initialize analyzer
    analyzer = FailurePatternAnalyzer(data_dir)

    # Generate taxonomy
    taxonomy = analyzer.generate_taxonomy()

    # Save taxonomy JSON
    taxonomy_path = data_dir / 'failure-taxonomy.json'
    with open(taxonomy_path, 'w') as f:
        json.dump(taxonomy, f, indent=2, default=str)
    print(f"Taxonomy saved to: {taxonomy_path}")
    print()

    # Generate markdown summary
    markdown_path = Path('/home/coding/aide-de-camp/docs/research/failure-patterns.md')
    generate_markdown_summary(taxonomy, markdown_path)
    print()

    # Print summary
    print("=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Total patterns identified: {taxonomy['metadata']['total_patterns_identified']}")
    print(f"Total failures analyzed: {taxonomy['metadata']['total_failures_analyzed']}")
    print()

    for pattern_name, pattern_data in taxonomy['pattern_taxonomy'].items():
        freq = pattern_data['statistics']['frequency']
        if freq > 0:
            print(f"  {pattern_name}: {freq} occurrences")
    print()
    print("Files generated:")
    print(f"  1. {taxonomy_path}")
    print(f"  2. {markdown_path}")


if __name__ == '__main__':
    main()
