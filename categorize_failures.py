#!/usr/bin/env python3
"""
Apply pattern-matching rules to categorize failures.

This script loads parsed failure records from logs and applies
pattern-matching heuristics to assign each failure to a category.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional


# Pattern matching rules derived from parse_failure_patterns.py
PATTERN_RULES = {
    'ImagePullBackOff': {
        'description': 'Container image cannot be pulled from registry',
        'severity': 'high',
        'matchers': [
            lambda r: 'image' in r.get('reason', '').lower() and ('pull' in r.get('reason', '').lower() or 'backoff' in r.get('reason', '').lower()),
            lambda r: 'errimagepull' in r.get('reason', '').lower() or 'imagepull' in r.get('reason', '').lower(),
            lambda r: r.get('error_type', '') == 'image_pull_error',
        ]
    },
    'CrashLoopBackOff': {
        'description': 'Container repeatedly crashes and restarts',
        'severity': 'high',
        'matchers': [
            lambda r: 'crash' in r.get('reason', '').lower() and 'loop' in r.get('reason', '').lower(),
            lambda r: 'crashloopbackoff' in r.get('reason', '').lower(),
            lambda r: r.get('error_type', '') == 'crash_loop_back_off',
        ]
    },
    'OOMKilled': {
        'description': 'Container terminated due to excessive memory usage',
        'severity': 'critical',
        'matchers': [
            lambda r: 'oom' in r.get('reason', '').lower() or 'oomkilled' in r.get('reason', '').lower(),
            lambda r: r.get('error_type', '') == 'oom_killed',
            lambda r: 'exit code 137' in r.get('message', '').lower(),
        ]
    },
    'ProbeFailure': {
        'description': 'Liveness or readiness probe failures',
        'severity': 'medium',
        'matchers': [
            lambda r: 'probe' in r.get('reason', '').lower(),
            lambda r: 'liveness' in r.get('reason', '').lower() or 'readiness' in r.get('reason', '').lower(),
            lambda r: 'unhealthy' in r.get('reason', '').lower(),
            lambda r: r.get('error_type', '') in ['liveness_probe_failure', 'readiness_probe_failure'],
        ]
    },
    'DependencyTimeout': {
        'description': 'Timeout connecting to dependent services',
        'severity': 'medium',
        'matchers': [
            lambda r: 'timeout' in r.get('message', '').lower() or 'connection' in r.get('message', '').lower(),
            lambda r: 'network' in r.get('reason', '').lower() and 'timeout' in r.get('reason', '').lower(),
        ]
    },
    'NetworkIssue': {
        'description': 'Network allocation or connectivity problems',
        'severity': 'low',
        'matchers': [
            lambda r: 'clusterip' in r.get('reason', '').lower(),
            lambda r: 'network' in r.get('reason', '').lower() and not 'timeout' in r.get('reason', '').lower(),
            lambda r: 'clusteripnotallocated' in r.get('reason', '').lower(),
            lambda r: r.get('error_type', '') == 'broken_pipe',
            lambda r: r.get('error_pattern', '') and ('connection reset' in r.get('error_pattern', '').lower() or 'broken pipe' in r.get('error_pattern', '').lower()),
        ]
    },
    'ResourceIssue': {
        'description': 'Insufficient CPU or memory resources',
        'severity': 'medium',
        'matchers': [
            lambda r: 'insufficient' in r.get('reason', '').lower(),
            lambda r: 'cpu' in r.get('reason', '').lower() or 'memory' in r.get('reason', '').lower(),
            lambda r: r.get('error_type', '') in ['container_not_ready', 'pod_not_ready'],
        ]
    },
    'HTTPError': {
        'description': 'HTTP error responses (4xx, 5xx)',
        'severity': 'medium',
        'matchers': [
            lambda r: r.get('error_type', '') == 'http_500',
            lambda r: r.get('error_type', '') == 'http_503',
            lambda r: r.get('error_type', '') == 'http_404',
            lambda r: 'status 5' in r.get('severity', '') or 'status 4' in r.get('severity', ''),
        ]
    },
    'DeploymentRollback': {
        'description': 'Deployment was rolled back to previous version',
        'severity': 'high',
        'matchers': [
            lambda r: 'rollback' in r.get('event_type', '').lower(),
            lambda r: r.get('outcome', '') == 'rolled_back',
        ]
    },
    'DeploymentCluster': {
        'description': 'Multiple deployments occurring on the same day',
        'severity': 'info',
        'matchers': []  # Requires context analysis, not individual record matching
    },
    'DeploymentGap': {
        'description': 'Extended periods with no deployment activity',
        'severity': 'info',
        'matchers': []  # Requires temporal analysis
    },
    'DeprecationWarning': {
        'description': 'Use of deprecated features or annotations',
        'severity': 'info',
        'matchers': [
            lambda r: 'deprecated' in r.get('reason', '').lower() or 'deprecated' in r.get('message', '').lower(),
            lambda r: r.get('type', '').lower() == 'warning' and 'deprecated' in r.get('message', '').lower(),
        ]
    },
    'Operational': {
        'description': 'Operational events and warnings',
        'severity': 'info',
        'matchers': [
            lambda r: r.get('type', '').lower() == 'warning',
            lambda r: r.get('source', '') == 'kubernetes_events' and r.get('type', '').lower() == 'normal',
        ]
    },
    'ApplicationError': {
        'description': 'Application-level errors (exceptions, panics, etc.)',
        'severity': 'high',
        'matchers': [
            lambda r: 'traceback' in r.get('message', '').lower(),
            lambda r: 'exception' in r.get('message', '').lower(),
            lambda r: 'panic' in r.get('message', '').lower(),
            lambda r: 'fatal' in r.get('message', '').lower(),
        ]
    },
    'StartupFailure': {
        'description': 'Container failed to start properly',
        'severity': 'high',
        'matchers': [
            lambda r: 'containercreating' in r.get('reason', '').lower(),
            lambda r: 'error' in r.get('reason', '').lower() and 'start' in r.get('message', '').lower(),
        ]
    },
    'RecordingFetchError': {
        'description': 'Failed to fetch recordings from storage backend',
        'severity': 'medium',
        'matchers': [
            lambda r: r.get('error_type', '') == 'recording_fetch_errors',
            lambda r: 'recording fetch' in r.get('context', '').lower(),
        ]
    },
    'StorageBackendError': {
        'description': 'Storage backend connectivity or response issues',
        'severity': 'high',
        'matchers': [
            lambda r: 'storage backend' in r.get('context', '').lower(),
            lambda r: r.get('error_pattern', '') and 'connection reset' in r.get('error_pattern', '').lower(),
        ]
    },
}


def load_jsonl_logs(log_dir: Path) -> List[Dict[str, Any]]:
    """Load all parsed failure records from JSONL log files."""
    records = []
    for jsonl_file in log_dir.glob("*.jsonl"):
        try:
            with open(jsonl_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            record = json.loads(line)
                            record['_source_file'] = str(jsonl_file)
                            records.append(record)
                        except json.JSONDecodeError as e:
                            print(f"Warning: Failed to parse line in {jsonl_file}: {e}")
        except Exception as e:
            print(f"Warning: Failed to read {jsonl_file}: {e}")
    return records


def load_deployment_data(data_file: Path) -> List[Dict[str, Any]]:
    """Load deployment events from structured JSON data."""
    try:
        with open(data_file, 'r') as f:
            data = json.load(f)

        # Extract deployment events if structured as analysis report
        if 'pbx_web_analysis' in data or 'whisper_stt_analysis' in data:
            events = []
            for service_key in ['pbx_web_analysis', 'whisper_stt_analysis']:
                if service_key in data:
                    service_data = data[service_key]
                    failure_modes = service_data.get('failure_modes', {})
                    failure_details = failure_modes.get('failure_details', [])
                    for detail in failure_details:
                        detail['service'] = service_key.replace('_analysis', '')
                        detail['_source'] = 'deployment_analysis'
                        events.append(detail)
            return events
        return []
    except Exception as e:
        print(f"Warning: Failed to load {data_file}: {e}")
        return []


def categorize_failure(record: Dict[str, Any]) -> str:
    """Apply pattern-matching rules to categorize a single failure record."""

    for pattern_name, pattern_config in PATTERN_RULES.items():
        matchers = pattern_config.get('matchers', [])

        for matcher in matchers:
            try:
                if matcher(record):
                    return pattern_name
            except Exception as e:
                # Matcher failed to evaluate, skip it
                continue

    return 'uncategorized'


def categorize_all_failures(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Categorize all failure records and build summary."""

    categories = {}

    categorized = {
        'generated_at': datetime.now().isoformat(),
        'total_records': len(records),
        'categorized_count': 0,
        'uncategorized_count': 0,
        'categories': {},
        'failures': []
    }

    for record in records:
        category = categorize_failure(record)

        # Add category to record
        categorized_record = record.copy()
        categorized_record['pattern_category'] = category

        # Track in summary
        if category == 'uncategorized':
            categorized['uncategorized_count'] += 1
        else:
            categorized['categorized_count'] += 1

            # Initialize category if not exists
            if category not in categories:
                categories[category] = {
                    'count': 0,
                    'severity': PATTERN_RULES.get(category, {}).get('severity', 'unknown'),
                    'description': PATTERN_RULES.get(category, {}).get('description', 'Unknown pattern'),
                    'examples': []
                }

            categories[category]['count'] += 1

            # Keep up to 3 examples per category
            if len(categories[category]['examples']) < 3:
                categories[category]['examples'].append({
                    'source': record.get('source', 'unknown'),
                    'error_type': record.get('error_type', 'unknown'),
                    'reason': record.get('reason', 'N/A'),
                    'message': record.get('message', 'N/A')[:200] if record.get('message') else 'N/A'
                })

        categorized['failures'].append(categorized_record)

    categorized['categories'] = categories
    return categorized


def detect_temporal_patterns(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Detect patterns that require temporal/contextual analysis."""

    deployment_events = [r for r in records if r.get('_source') == 'deployment_analysis']

    # Group by service and date
    deployments_by_date = defaultdict(lambda: defaultdict(int))
    for event in deployment_events:
        service = event.get('service', 'unknown')
        timestamp = event.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                date_key = dt.strftime('%Y-%m-%d')
                deployments_by_date[service][date_key] += 1
            except:
                pass

    # Detect deployment clusters (multiple deployments on same day)
    clusters = []
    for service, dates in deployments_by_date.items():
        for date, count in dates.items():
            if count > 2:
                clusters.append({
                    'service': service,
                    'date': date,
                    'count': count,
                    'pattern_type': 'DeploymentCluster'
                })

    return {
        'deployment_clusters': clusters,
        'temporal_patterns_detected': len(clusters)
    }


def main():
    """Main entry point."""

    # Define data sources
    logs_dir = Path('logs')
    data_file = Path('deployment-patterns-analysis-report.json')
    output_file = Path('categorized-failures-report.json')

    print("=" * 60)
    print("FAILURE PATTERN CATEGORIZATION")
    print("=" * 60)

    # Load failure records from multiple sources
    print("\n1. Loading parsed failure records...")
    log_records = load_jsonl_logs(logs_dir)
    print(f"   Loaded {len(log_records)} records from log files")

    print("\n2. Loading deployment analysis data...")
    deployment_records = load_deployment_data(data_file)
    print(f"   Loaded {len(deployment_records)} deployment events")

    all_records = log_records + deployment_records
    print(f"\n   Total records to categorize: {len(all_records)}")

    if len(all_records) == 0:
        print("\n   WARNING: No failure records found to categorize.")
        print("   Checking for data sources...")

        if not logs_dir.exists():
            print(f"   - logs/ directory not found")
        else:
            jsonl_files = list(logs_dir.glob("*.jsonl"))
            print(f"   - Found {len(jsonl_files)} JSONL files in logs/")

        if not data_file.exists():
            print(f"   - {data_file} not found")

        # Create empty report
        categorized = {
            'generated_at': datetime.now().isoformat(),
            'total_records': 0,
            'categorized_count': 0,
            'uncategorized_count': 0,
            'categories': {},
            'failures': [],
            'note': 'No failure records found in available data sources'
        }
    else:
        # Categorize failures
        print("\n3. Applying pattern-matching rules...")
        categorized = categorize_all_failures(all_records)

        # Detect temporal patterns
        print("\n4. Detecting temporal patterns...")
        temporal_patterns = detect_temporal_patterns(all_records)
        categorized['temporal_patterns'] = temporal_patterns

        # Write output
        print(f"\n5. Writing categorized report to {output_file}...")
        with open(output_file, 'w') as f:
            json.dump(categorized, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("CATEGORIZATION SUMMARY")
    print("=" * 60)
    print(f"Total records processed: {categorized['total_records']}")
    print(f"Categorized failures: {categorized['categorized_count']}")
    print(f"Uncategorized failures: {categorized['uncategorized_count']}")

    print(f"\nPattern categories found: {len(categorized['categories'])}")

    # Sort categories by count (descending)
    sorted_categories = sorted(
        categorized['categories'].items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )

    for category, data in sorted_categories:
        print(f"\n{category}:")
        print(f"  Count: {data['count']}")
        print(f"  Severity: {data['severity']}")
        print(f"  Description: {data['description']}")

    if categorized.get('temporal_patterns', {}).get('temporal_patterns_detected', 0) > 0:
        print(f"\nTemporal patterns detected:")
        for cluster in categorized['temporal_patterns']['deployment_clusters']:
            print(f"  - {cluster['service']}: {cluster['count']} deployments on {cluster['date']}")

    print("\n" + "=" * 60)
    print(f"Report saved to: {output_file}")
    print("=" * 60)

    return categorized


if __name__ == '__main__':
    main()
