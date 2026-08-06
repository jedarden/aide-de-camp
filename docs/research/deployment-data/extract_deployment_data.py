#!/usr/bin/env python3
"""
Extract deployment history for pbx-web and whisper-stt services.
These services are deployed via ArgoCD, not CI/CD pipelines.
Deployment history is tracked via Kubernetes ReplicaSets.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def run_kubectl(cmd):
    """Run kubectl command and return JSON output."""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"kubectl failed: {result.stderr}")
    return json.loads(result.stdout)


def get_replicaset_history(namespace, app_label):
    """Get ReplicaSet history for a deployment."""
    cmd = (f'kubectl --server=http://traefik-ardenone-cluster:8001 '
           f'get replicaset -n {namespace} -l app={app_label} '
           f'--sort-by=.metadata.creationTimestamp -o json')
    data = run_kubectl(cmd)
    return data.get('items', [])


def extract_deployment_records(replicasets, days=30):
    """Extract deployment records from ReplicaSets."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records = []

    for rs in replicasets:
        name = rs.get('metadata', {}).get('name', '')
        created = rs.get('metadata', {}).get('creationTimestamp', '')
        revision = rs.get('metadata', {}).get('annotations', {}).get(
            'deployment.kubernetes.io/revision', ''
        )

        # Parse timestamp
        created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))

        # Extract images
        images = []
        for c in rs.get('spec', {}).get('template', {}).get('spec', {}).get('containers', []):
            images.append(c.get('image', ''))

        # Get status
        available = rs.get('status', {}).get('availableReplicas', 0)
        replicas = rs.get('status', {}).get('replicas', 0)

        # Determine status (success if replicas == available and both > 0)
        status = 'success' if (replicas > 0 and replicas == available) else 'unknown'

        records.append({
            'replicaset_name': name,
            'revision': revision,
            'created_at': created,
            'images': images,
            'available_replicas': available,
            'replicas': replicas,
            'status': status,
            'in_window': created_dt >= cutoff
        })

    return records


def save_deployment_data(records, filepath):
    """Save deployment records to JSON file."""
    # Save only records in the time window
    in_window = [r for r in records if r['in_window']]

    data = {
        'service': filepath.stem.replace('-deployments', ''),
        'extracted_at': datetime.now(timezone.utc).isoformat(),
        'time_window_days': 30,
        'total_replicasets': len(records),
        'replicasets_in_window': len(in_window),
        'deployments': in_window
    }

    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)

    return data


def main():
    output_dir = Path('docs/research/deployment-data')
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Extracting deployment history for pbx-web and whisper-stt...")
    print()

    # pbx-web
    print("Fetching pbx-web ReplicaSets...")
    pbx_replicasets = get_replicaset_history('pbx-web', 'pbx-web')
    pbx_records = extract_deployment_records(pbx_replicasets, days=30)
    pbx_data = save_deployment_data(
        pbx_records,
        output_dir / 'pbx-web-deployments.json'
    )
    print(f"  pbx-web: {pbx_data['replicasets_in_window']} deployments in last 30 days")
    print(f"    Date range: {pbx_data['deployments'][0]['created_at'] if pbx_data['deployments'] else 'N/A'} to "
          f"{pbx_data['deployments'][-1]['created_at'] if pbx_data['deployments'] else 'N/A'}")

    # whisper-stt
    print()
    print("Fetching whisper-stt ReplicaSets...")
    whisper_replicasets = get_replicaset_history('whisper-stt', 'whisper-stt')
    whisper_records = extract_deployment_records(whisper_replicasets, days=30)
    whisper_data = save_deployment_data(
        whisper_records,
        output_dir / 'whisper-stt-deployments.json'
    )
    print(f"  whisper-stt: {whisper_data['replicasets_in_window']} deployments in last 30 days")
    print(f"    Date range: {whisper_data['deployments'][0]['created_at'] if whisper_data['deployments'] else 'N/A'} to "
          f"{whisper_data['deployments'][-1]['created_at'] if whisper_data['deployments'] else 'N/A'}")

    print()
    print(f"Deployment data saved to {output_dir}/")
    print("  - pbx-web-deployments.json")
    print("  - whisper-stt-deployments.json")


if __name__ == '__main__':
    main()
