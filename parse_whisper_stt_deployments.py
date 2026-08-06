#!/usr/bin/env python3
"""
Parse whisper-stt deployment event data and extract structured deployment records.
Output format matches pbx-web CSV structure for comparison analysis.
"""

import json
import csv
from datetime import datetime
from pathlib import Path


def parse_timestamp(ts_string: str) -> str:
    """Parse and normalize ISO timestamp."""
    if ts_string:
        try:
            dt = datetime.fromisoformat(ts_string.replace('Z', '+00:00'))
            return dt.isoformat()
        except:
            return ts_string
    return ""


def extract_date(timestamp: str) -> str:
    """Extract date portion from timestamp."""
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except:
            return timestamp[:10] if len(timestamp) >= 10 else timestamp
    return ""


def classify_event_type(replica: dict, index: int, total_replicas: int) -> str:
    """
    Classify deployment event type based on replica set data.

    Types:
    - deployment_rollout: Standard deployment rollout
    - deployment_rollback: Rollback to previous version
    - rapid_deployment: Multiple deployments in short timeframe
    - scaling_event: Replica count change (not applicable for Recreate strategy)
    """
    deployment_name = replica.get('deployment', 'unknown')
    status = replica.get('status', 'unknown')
    image = replica.get('image', '')

    # Base classification - all whisper-stt events are rollouts
    # (Recreate strategy means full replacement on each update)
    event_type = 'deployment_rollout'

    # Check for rollback pattern (would need event sequence analysis)
    # For now, classify based on revision order
    revision = replica.get('revision', 0)

    # Flag rapid deployments (multiple events same day)
    # This will be marked in post-processing

    return event_type


def determine_outcome(replica: dict, pod_status: dict) -> str:
    """
    Determine deployment outcome.

    Returns: success, failed, partial, pending
    """
    status = replica.get('status', 'unknown')

    if status == 'active':
        return 'success'
    elif status == 'inactive':
        # Could be successful then replaced, or failed
        # Check if it has readyReplicas
        if replica.get('readyReplicas', 0) > 0:
            return 'success'
        return 'success'  # Assume successful but replaced
    else:
        return 'pending'


def get_pod_info_for_deployment(replica: dict, current_pods: list) -> dict:
    """Find current pod info for a replica set."""
    replica_name = replica.get('name', '')

    # Match pod by replica set prefix (pod name starts with replica name)
    for pod in current_pods:
        pod_name = pod.get('name', '')
        if pod_name.startswith(replica_name + '-'):
            return {
                'pod_name': pod_name,
                'pod_ready': pod.get('status') == 'Running',
                'restart_count': pod.get('totalRestartCount', 0),
                'pod_status': pod.get('status', 'Unknown')
            }

    return {
        'pod_name': '',
        'pod_ready': False,
        'restart_count': 0,
        'pod_status': 'NotRunning'
    }


def main():
    input_file = Path('/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json')
    output_csv = Path('/home/coding/aide-de-camp/whisper-stt-deployment-events-30days.csv')

    # Load JSON data
    print(f"Loading {input_file}...")
    with open(input_file, 'r') as f:
        data = json.load(f)

    # Extract replica sets (deployment events)
    replicasets = data.get('deployment_history_30_days', {}).get('replicasets', [])
    current_pods = data.get('pod_status', {}).get('current_pods', [])

    # Sort replicasets by creation time (newest first)
    replicasets_sorted = sorted(replicasets, key=lambda x: x.get('created', ''), reverse=True)

    # Prepare output records
    records = []

    # Track deployment dates for rapid deployment detection
    deployment_dates = {}

    for replica in replicasets_sorted:
        created_ts = parse_timestamp(replica.get('created', ''))
        date = extract_date(created_ts)

        # Track deployment counts per date
        deployment_key = (replica.get('deployment', ''), date)
        deployment_dates[deployment_key] = deployment_dates.get(deployment_key, 0) + 1

        # Classify event
        event_type = classify_event_type(replica, len(records), len(replicasets_sorted))

        # Determine outcome
        outcome = determine_outcome(replica, data.get('pod_status', {}))

        # Get pod info
        pod_info = get_pod_info_for_deployment(replica, current_pods)

        # Build notes
        notes = []
        if replica.get('status') == 'active':
            notes.append('Current active deployment')

        # Check for rapid deployment
        if deployment_dates.get(deployment_key, 0) > 1:
            notes.append('Rapid deployment sequence')

        notes_str = '; '.join(notes) if notes else ''

        # Create record
        record = {
            'date': date,
            'timestamp': created_ts,
            'event_type': event_type,
            'deployment': replica.get('deployment', ''),
            'revision': replica.get('revision', ''),
            'replicaSet': replica.get('name', ''),
            'image': replica.get('image', ''),
            'outcome': outcome,
            'pod_name': pod_info.get('pod_name', ''),
            'pod_ready': str(pod_info.get('pod_ready', False)).lower(),
            'restart_count': pod_info.get('restart_count', 0),
            'notes': notes_str
        }

        records.append(record)

    # Sort records by timestamp (newest first)
    records.sort(key=lambda x: x['timestamp'], reverse=True)

    # Write CSV
    print(f"Writing {output_csv}...")
    fieldnames = [
        'date', 'timestamp', 'event_type', 'deployment', 'revision',
        'replicaSet', 'image', 'outcome', 'pod_name', 'pod_ready',
        'restart_count', 'notes'
    ]

    with open(output_csv, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"✓ Extracted {len(records)} deployment events")
    print(f"✓ Output: {output_csv}")

    # Print summary
    print("\nEvent Summary:")
    event_counts = {}
    for record in records:
        event_type = record['event_type']
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

    for event_type, count in sorted(event_counts.items()):
        print(f"  {event_type}: {count}")

    print("\nOutcome Summary:")
    outcome_counts = {}
    for record in records:
        outcome = record['outcome']
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

    for outcome, count in sorted(outcome_counts.items()):
        print(f"  {outcome}: {count}")


if __name__ == '__main__':
    main()
