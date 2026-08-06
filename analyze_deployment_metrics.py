#!/usr/bin/env python3
"""
Calculate deployment success/failure metrics for pbx-web and whisper-stt services.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp string to datetime object."""
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'
    return datetime.fromisoformat(ts)

def calculate_pbx_web_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate metrics for pbx-web service."""
    events = data.get('deployment_events_last_30_days', [])

    # Count deployments by outcome
    successful = 0
    failed = 0
    total = len(events)

    for event in events:
        outcome = event.get('outcome', '').lower()
        if outcome == 'success':
            successful += 1
        elif outcome in ['failed', 'error', 'rolled_back']:
            failed += 1

    # Calculate success rate
    success_rate = (successful / total * 100) if total > 0 else 0
    failure_rate = (failed / total * 100) if total > 0 else 0

    # Calculate deployment frequency (deployments per day over 30 days)
    deploy_frequency = total / 30  # deployments per day

    # Calculate mean time between deployments
    timestamps = []
    for event in events:
        if 'timestamp' in event:
            timestamps.append(parse_timestamp(event['timestamp']))

    if len(timestamps) > 1:
        timestamps.sort(reverse=True)  # Most recent first
        time_diffs = []
        for i in range(len(timestamps) - 1):
            diff = timestamps[i] - timestamps[i + 1]
            time_diffs.append(diff.total_seconds() / 3600)  # Convert to hours

        if time_diffs:
            mean_time_between = sum(time_diffs) / len(time_diffs)
        else:
            mean_time_between = 0
    else:
        mean_time_between = 0

    return {
        'service': 'pbx-web',
        'total_deployments': total,
        'successful_deployments': successful,
        'failed_deployments': failed,
        'success_rate': round(success_rate, 2),
        'failure_rate': round(failure_rate, 2),
        'deployment_frequency_per_day': round(deploy_frequency, 3),
        'mean_time_between_deployments_hours': round(mean_time_between, 2),
        'deployment_events': events
    }

def calculate_whisper_stt_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate metrics for whisper-stt service."""
    deployment_history = data.get('deployment_history_30_days', {})
    replicasets = deployment_history.get('replicasets', [])

    # Count unique deployments from replicasets
    # Each replicaSet represents a deployment
    total = len(replicasets)

    # Determine success based on replicaSet status
    successful = 0
    failed = 0

    for rs in replicasets:
        # Check if replicaSet was able to become ready at some point
        status = rs.get('status', '').lower()
        ready_replicas = rs.get('readyReplicas', 0)

        # If it has readyReplicas > 0 or is currently active, consider it successful
        if ready_replicas > 0 or status == 'active':
            successful += 1
        else:
            failed += 1

    # Calculate success rate
    success_rate = (successful / total * 100) if total > 0 else 0
    failure_rate = (failed / total * 100) if total > 0 else 0

    # Calculate deployment frequency (deployments per day over 30 days)
    deploy_frequency = total / 30  # deployments per day

    # Calculate mean time between deployments using replicaSet creation timestamps
    timestamps = []
    for rs in replicasets:
        if 'created' in rs:
            timestamps.append(parse_timestamp(rs['created']))

    if len(timestamps) > 1:
        timestamps.sort(reverse=True)  # Most recent first
        time_diffs = []
        for i in range(len(timestamps) - 1):
            diff = timestamps[i] - timestamps[i + 1]
            time_diffs.append(diff.total_seconds() / 3600)  # Convert to hours

        if time_diffs:
            mean_time_between = sum(time_diffs) / len(time_diffs)
        else:
            mean_time_between = 0
    else:
        mean_time_between = 0

    return {
        'service': 'whisper-stt',
        'total_deployments': total,
        'successful_deployments': successful,
        'failed_deployments': failed,
        'success_rate': round(success_rate, 2),
        'failure_rate': round(failure_rate, 2),
        'deployment_frequency_per_day': round(deploy_frequency, 3),
        'mean_time_between_deployments_hours': round(mean_time_between, 2),
        'replicasets': replicasets
    }

def main():
    """Main function to load data and calculate metrics."""
    # Load pbx-web data
    with open('/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json', 'r') as f:
        pbx_web_data = json.load(f)

    # Load whisper-stt data
    with open('/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json', 'r') as f:
        whisper_stt_data = json.load(f)

    # Calculate metrics
    pbx_web_metrics = calculate_pbx_web_metrics(pbx_web_data)
    whisper_stt_metrics = calculate_whisper_stt_metrics(whisper_stt_data)

    # Prepare output
    output = {
        'generated_at': datetime.now().isoformat(),
        'analysis_period': '30 days',
        'services': {
            'pbx-web': pbx_web_metrics,
            'whisper-stt': whisper_stt_metrics
        },
        'summary': {
            'combined_success_rate': round(
                (pbx_web_metrics['success_rate'] + whisper_stt_metrics['success_rate']) / 2, 2
            ),
            'total_deployments_both_services': pbx_web_metrics['total_deployments'] + whisper_stt_metrics['total_deployments']
        }
    }

    # Save to intermediate file
    output_path = '/home/coding/aide-de-camp/docs/research/deployment-metrics-intermediate.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ Deployment metrics calculated and saved to {output_path}")
    print(f"\nSummary:")
    print(f"  pbx-web: {pbx_web_metrics['success_rate']}% success rate ({pbx_web_metrics['successful_deployments']}/{pbx_web_metrics['total_deployments']} deployments)")
    print(f"  whisper-stt: {whisper_stt_metrics['success_rate']}% success rate ({whisper_stt_metrics['successful_deployments']}/{whisper_stt_metrics['total_deployments']} deployments)")
    print(f"  Combined: {output['summary']['combined_success_rate']}% success rate")

if __name__ == '__main__':
    main()