#!/usr/bin/env python3
"""
Transform ReplicaSet deployment data into structured workflow-style format.
Acceptance criteria: timestamp, image_tag, status (success/failed), duration_seconds
"""
import json
from datetime import datetime
from pathlib import Path


def load_replicaset_data(filepath):
    """Load existing ReplicaSet deployment data."""
    with open(filepath) as f:
        return json.load(f)


def transform_to_workflow_format(replicaset_records, service_name):
    """
    Transform ReplicaSet data to workflow-style format.
    Maps: timestamp, image -> image_tag, status
    Duration is set to null (ReplicaSets don't have workflow timing data)
    """
    deployments = []

    for record in replicaset_records:
        # Extract timestamp and image
        timestamp = record.get('timestamp', '')
        image = record.get('image', '')

        # Determine status: success if replicas > 0, otherwise unknown/failed
        replicas = record.get('replicas', 0)
        if replicas > 0:
            status = 'success'
        else:
            status = 'unknown'  # Could be scaled down, not necessarily failed

        deployments.append({
            'timestamp': timestamp,
            'image_tag': image,
            'status': status,
            'duration_seconds': None,  # No workflow timing data in ReplicaSets
            'source': 'replicaset',
            'replicaSet': record.get('replicaSet', ''),
            'revision': record.get('revision', '')
        })

    return deployments


def save_structured_deployments(deployments, filepath, service_name):
    """Save structured deployment data in workflow-style format."""
    data = {
        'service': service_name,
        'data_source': 'replicaset_transformed',
        'extracted_at': datetime.utcnow().isoformat() + 'Z',
        'total_deployments': len(deployments),
        'deployments': deployments
    }

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    return data


def main():
    input_dir = Path('docs/research/deployment-data')

    # Load existing ReplicaSet data
    pbx_data = load_replicaset_data(input_dir / 'pbx-web-deployments.json')
    whisper_data = load_replicaset_data(input_dir / 'whisper-stt-deployments.json')

    # Transform to workflow format
    pbx_deployments = transform_to_workflow_format(pbx_data, 'pbx-web')
    whisper_deployments = transform_to_workflow_format(whisper_data, 'whisper-stt')

    # Save structured files
    pbx_output = save_structured_deployments(
        pbx_deployments,
        input_dir / 'pbx-web-deployments-structured.json',
        'pbx-web'
    )

    whisper_output = save_structured_deployments(
        whisper_deployments,
        input_dir / 'whisper-stt-deployments-structured.json',
        'whisper-stt'
    )

    print(f"✓ Transformed {pbx_output['total_deployments']} pbx-web deployments")
    print(f"✓ Transformed {whisper_output['total_deployments']} whisper-stt deployments")
    print(f"\nOutput files:")
    print(f"  - {input_dir}/pbx-web-deployments-structured.json")
    print(f"  - {input_dir}/whisper-stt-deployments-structured.json")


if __name__ == '__main__':
    main()
