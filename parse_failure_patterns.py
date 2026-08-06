#!/usr/bin/env python3
"""
Parse and categorize failure patterns from deployment data.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any


def load_json_files(data_dir: Path) -> Dict[str, Any]:
    """Load all JSON files from the deployment data directory."""
    data = {}
    for json_file in data_dir.glob("*.json"):
        with open(json_file, 'r') as f:
            data[json_file.name] = json.load(f)
    return data


def extract_failure_modes(metrics: Dict[str, Any]) -> Dict[str, int]:
    """Extract failure modes from metrics data."""
    failure_modes = metrics.get('failure_modes', {})
    return {
        'crash_loop_back_off': failure_modes.get('crash_loop_back_off', 0),
        'oom_killed': failure_modes.get('oom_killed', 0),
        'image_pull_backoff': failure_modes.get('image_pull_backoff', 0),
        'image_pull_error': failure_modes.get('image_pull_error', 0),
        'liveness_probe_failure': failure_modes.get('liveness_probe_failure', 0),
        'readiness_probe_failure': failure_modes.get('readiness_probe_failure', 0),
        'container_not_ready': failure_modes.get('container_not_ready', 0),
        'pod_not_ready': failure_modes.get('pod_not_ready', 0),
    }


def extract_events(events: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract events with type, reason, and timestamp."""
    timeline = events.get('timeline', [])
    return [
        {
            'type': event.get('type'),
            'reason': event.get('reason'),
            'message': event.get('message'),
            'object': event.get('object'),
            'timestamp': event.get('timestamp')
        }
        for event in timeline
    ]


def extract_pod_restart_patterns(pods: Dict[str, Any]) -> Dict[str, Any]:
    """Extract restart patterns from pod data."""
    restart_stats = pods.get('restart_stats', {})
    waiting_reasons = pods.get('waiting_reasons', {})
    terminated_reasons = pods.get('terminated_reasons', {})

    return {
        'total_restarts': restart_stats.get('total_restarts', 0),
        'max_restarts': restart_stats.get('max_restarts', 0),
        'avg_restarts': restart_stats.get('avg_restarts', 0.0),
        'pods_with_restarts': restart_stats.get('pods_with_restarts', 0),
        'waiting_reasons': waiting_reasons,
        'terminated_reasons': terminated_reasons,
    }


def extract_deployment_patterns(deployments: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract deployment patterns from deployment history."""
    deployment_list = deployments.get('deployments', [])
    patterns = []

    for deployment in deployment_list:
        patterns.append({
            'timestamp': deployment.get('timestamp'),
            'image_tag': deployment.get('image_tag'),
            'status': deployment.get('status'),
            'replicaSet': deployment.get('replicaSet'),
            'revision': deployment.get('revision'),
        })

    return patterns


def categorize_event_type(event: Dict[str, Any]) -> str:
    """Categorize events into pattern types."""
    reason = event.get('reason', '').lower()
    event_type = event.get('type', '').lower()
    message = event.get('message', '').lower()

    # Image pull issues
    if 'image' in reason and ('pull' in reason or 'backoff' in reason):
        return 'ImagePullBackOff'
    if 'errimagepull' in reason or 'imagepull' in reason:
        return 'ImagePullBackOff'

    # OOM killed
    if 'oom' in reason or 'oomkilled' in reason:
        return 'OOMKilled'

    # Crash loop
    if 'crash' in reason or 'loop' in reason:
        return 'CrashLoopBackOff'

    # Probe failures
    if 'probe' in reason or 'liveness' in reason or 'readiness' in reason:
        return 'ProbeFailure'
    if 'unhealthy' in reason:
        return 'ProbeFailure'

    # Network/dependency issues
    if 'network' in reason or 'timeout' in reason or 'connection' in reason:
        return 'DependencyTimeout'
    if 'clusterip' in reason:
        return 'NetworkIssue'

    # Resource issues
    if 'insufficient' in reason or 'cpu' in reason or 'memory' in reason:
        return 'ResourceIssue'

    # Warnings that might indicate issues
    if event_type == 'warning':
        if 'deprecated' in reason or 'deprecated' in message:
            return 'DeprecationWarning'
        if 'clusteripnotallocated' in reason:
            return 'NetworkIssue'
        return 'Warning'

    return event_type.title() if event_type else 'Unknown'


def analyze_deployment_outcomes(deployments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze deployment outcomes for patterns."""
    outcomes = defaultdict(int)
    status_by_image = defaultdict(lambda: defaultdict(int))

    for deployment in deployments:
        status = deployment.get('status', 'unknown')
        image = deployment.get('image_tag', 'unknown')
        outcomes[status] += 1
        status_by_image[image][status] += 1

    return {
        'outcomes': dict(outcomes),
        'by_image': dict(status_by_image),
        'total': len(deployments)
    }


def calculate_time_distribution(items: List[Dict[str, Any]], timestamp_key: str = 'timestamp') -> Dict[str, int]:
    """Calculate distribution of events over time (by date)."""
    distribution = defaultdict(int)

    for item in items:
        timestamp = item.get(timestamp_key, '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                date_key = dt.strftime('%Y-%m-%d')
                distribution[date_key] += 1
            except:
                pass

    return dict(sorted(distribution.items()))


def build_taxonomy(data_dir: Path) -> Dict[str, Any]:
    """Build complete failure taxonomy from all data files."""
    all_data = load_json_files(data_dir)

    taxonomy = {
        'generated_at': datetime.now().isoformat(),
        'data_directory': str(data_dir),
        'services': {},
        'pattern_categories': {},
        'summary': {}
    }

    # Process metrics files
    for service in ['pbx-web', 'whisper-stt']:
        metrics_file = f"{service}-metrics.json"
        if metrics_file in all_data:
            metrics = all_data[metrics_file]

            # Extract failure modes
            failure_modes = extract_failure_modes(metrics)
            events = extract_events(metrics)
            pod_patterns = extract_pod_restart_patterns(metrics.get('pods', {}))

            # Categorize events
            categorized_events = defaultdict(list)
            for event in events:
                category = categorize_event_type(event)
                categorized_events[category].append(event)

            # Count by category
            event_counts = {cat: len(evts) for cat, evts in categorized_events.items()}

            taxonomy['services'][service] = {
                'failure_modes': failure_modes,
                'pod_patterns': pod_patterns,
                'event_categories': event_counts,
                'event_details': {cat: evts for cat, evts in categorized_events.items()},
            }

    # Process deployment data
    for service in ['pbx-web', 'whisper-stt']:
        structured_file = f"{service}-deployments-structured.json"
        if structured_file in all_data:
            deployments = all_data[structured_file]
            deployment_patterns = extract_deployment_patterns(deployments)
            outcomes = analyze_deployment_outcomes(deployment_patterns)
            time_dist = calculate_time_distribution(deployment_patterns)

            if service not in taxonomy['services']:
                taxonomy['services'][service] = {}

            taxonomy['services'][service]['deployment_patterns'] = outcomes
            taxonomy['services'][service]['deployment_timeline'] = time_dist

    # Aggregate pattern categories across all services
    pattern_categories = {
        'ImagePullBackOff': {
            'description': 'Container image cannot be pulled from registry',
            'severity': 'high',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'CrashLoopBackOff': {
            'description': 'Container repeatedly crashes and restarts',
            'severity': 'high',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'OOMKilled': {
            'description': 'Container terminated due to excessive memory usage',
            'severity': 'critical',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'ProbeFailure': {
            'description': 'Liveness or readiness probe failures',
            'severity': 'medium',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'DependencyTimeout': {
            'description': 'Timeout connecting to dependent services',
            'severity': 'medium',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'NetworkIssue': {
            'description': 'Network allocation or connectivity problems',
            'severity': 'low',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'ResourceIssue': {
            'description': 'Insufficient CPU or memory resources',
            'severity': 'medium',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'DeploymentCluster': {
            'description': 'Multiple deployments occurring on the same day',
            'severity': 'info',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'DeploymentGap': {
            'description': 'Extended periods with no deployment activity',
            'severity': 'info',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'UnknownDeploymentStatus': {
            'description': 'Deployments with unknown/undetermined status',
            'severity': 'low',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'DeprecationWarning': {
            'description': 'Use of deprecated features or annotations',
            'severity': 'info',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
        'Operational': {
            'description': 'Operational events and warnings',
            'severity': 'info',
            'occurrences': 0,
            'by_service': {},
            'examples': []
        },
    }

    # Aggregate counts from failure modes and events
    for service, service_data in taxonomy['services'].items():
        failure_modes = service_data.get('failure_modes', {})
        event_categories = service_data.get('event_categories', {})

        # Add failure mode counts
        pattern_categories['CrashLoopBackOff']['by_service'][service] = failure_modes.get('crash_loop_back_off', 0)
        pattern_categories['OOMKilled']['by_service'][service] = failure_modes.get('oom_killed', 0)
        pattern_categories['ImagePullBackOff']['by_service'][service] = failure_modes.get('image_pull_backoff', 0)
        pattern_categories['ProbeFailure']['by_service'][service] = (
            failure_modes.get('liveness_probe_failure', 0) +
            failure_modes.get('readiness_probe_failure', 0)
        )
        pattern_categories['ResourceIssue']['by_service'][service] = (
            failure_modes.get('container_not_ready', 0) +
            failure_modes.get('pod_not_ready', 0)
        )

        # Add event category counts
        for category, count in event_categories.items():
            if category not in pattern_categories:
                pattern_categories[category] = {
                    'description': f'Event type: {category}',
                    'severity': 'unknown',
                    'occurrences': 0,
                    'by_service': {},
                    'examples': []
                }
            if service not in pattern_categories[category]['by_service']:
                pattern_categories[category]['by_service'][service] = 0
            pattern_categories[category]['by_service'][service] += count

        # Track unknown deployment statuses
        deployment_patterns = service_data.get('deployment_patterns', {})
        unknown_count = deployment_patterns.get('outcomes', {}).get('unknown', 0)
        if unknown_count > 0:
            pattern_categories['UnknownDeploymentStatus']['by_service'][service] = unknown_count
            # Track which images have unknown status
            by_image = deployment_patterns.get('by_image', {})
            unknown_images = [
                {'image': img, 'count': counts.get('unknown', 0)}
                for img, counts in by_image.items()
                if counts.get('unknown', 0) > 0
            ]
            pattern_categories['UnknownDeploymentStatus']['examples'].extend([
                {'service': service, 'details': unknown_images}
            ])

        # Detect deployment clusters (multiple deployments on same day)
        deployment_timeline = service_data.get('deployment_timeline', {})
        for date, count in deployment_timeline.items():
            if count > 2:  # More than 2 deployments in a day is a cluster
                pattern_categories['DeploymentCluster']['occurrences'] += 1
                if service not in pattern_categories['DeploymentCluster']['by_service']:
                    pattern_categories['DeploymentCluster']['by_service'][service] = 0
                pattern_categories['DeploymentCluster']['by_service'][service] += count
                pattern_categories['DeploymentCluster']['examples'].append({
                    'service': service,
                    'date': date,
                    'count': count
                })

    # Calculate deployment gaps
    for service, service_data in taxonomy['services'].items():
        deployment_timeline = service_data.get('deployment_timeline', {})
        if len(deployment_timeline) > 1:
            dates = sorted(deployment_timeline.keys())
            for i in range(1, len(dates)):
                gap_days = (datetime.strptime(dates[i], '%Y-%m-%d') -
                          datetime.strptime(dates[i-1], '%Y-%m-%d')).days
                if gap_days > 7:  # More than a week is a significant gap
                    pattern_categories['DeploymentGap']['occurrences'] += 1
                    if service not in pattern_categories['DeploymentGap']['by_service']:
                        pattern_categories['DeploymentGap']['by_service'][service] = 0
                    pattern_categories['DeploymentGap']['by_service'][service] += 1
                    pattern_categories['DeploymentGap']['examples'].append({
                        'service': service,
                        'gap_start': dates[i-1],
                        'gap_end': dates[i],
                        'gap_days': gap_days
                    })

    # Calculate totals
    for category, data in pattern_categories.items():
        if 'examples' not in data:
            data['examples'] = []
        total = sum(data['by_service'].values())
        pattern_categories[category]['occurrences'] = total

    # Remove categories with zero occurrences
    pattern_categories = {k: v for k, v in pattern_categories.items() if v['occurrences'] > 0}

    taxonomy['pattern_categories'] = pattern_categories

    # Add summary
    taxonomy['summary'] = {
        'total_pattern_categories': len(pattern_categories),
        'services_analyzed': list(taxonomy['services'].keys()),
        'total_deployment_events': sum(
            s.get('deployment_patterns', {}).get('total', 0)
            for s in taxonomy['services'].values()
        ),
        'total_failures': sum(
            sum(m.get('failure_modes', {}).values())
            for s in taxonomy['services'].values()
            for m in [s.get('failure_modes', {})]
        )
    }

    return taxonomy


def main():
    """Main entry point."""
    data_dir = Path('docs/research/deployment-data')
    output_file = data_dir / 'failure-taxonomy.json'

    print("Parsing deployment data files...")
    taxonomy = build_taxonomy(data_dir)

    print(f"Writing taxonomy to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(taxonomy, f, indent=2)

    print("\n=== SUMMARY ===")
    print(f"Services analyzed: {taxonomy['summary']['services_analyzed']}")
    print(f"Pattern categories found: {taxonomy['summary']['total_pattern_categories']}")
    print(f"Total deployment events: {taxonomy['summary']['total_deployment_events']}")
    print(f"Total failures: {taxonomy['summary']['total_failures']}")

    print("\n=== PATTERN CATEGORIES ===")
    for category, data in taxonomy['pattern_categories'].items():
        print(f"\n{category}:")
        print(f"  Severity: {data['severity']}")
        print(f"  Occurrences: {data['occurrences']}")
        print(f"  Description: {data['description']}")
        if data['by_service']:
            print(f"  By service: {dict(data['by_service'])}")

    return taxonomy


if __name__ == '__main__':
    main()
