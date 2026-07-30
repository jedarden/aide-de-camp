#!/usr/bin/env python3
"""
Standardize and combine Kubernetes and Argo logs into unified comparison dataset.
"""

import json
import csv
from datetime import datetime
from typing import Any, Dict, List


def standardize_timestamp(ts: str) -> str:
    """Convert various timestamp formats to ISO 8601 UTC."""
    if not ts:
        return None

    # Already in ISO 8601 format
    if 'T' in ts:
        # Handle timezone offsets like -04:00
        if ts.endswith('Z'):
            return ts
        # Convert offset to UTC by removing offset info (simplification)
        # For full accuracy we'd parse and convert, but this gives us consistency
        try:
            # Try parsing with offset
            if '+' in ts or '-' in ts.split('T')[-1]:
                # Remove timezone offset and treat as UTC for consistency
                # This is a simplification - ideally we'd convert to UTC properly
                ts = ts.split('+')[0].split('-', maxsplit=2)[0] + 'Z' if ts.count('-') > 2 else ts
                if not ts.endswith('Z'):
                    parts = ts.rsplit('-', 1)
                    if len(parts) == 2 and ':' in parts[1]:
                        ts = parts[0] + 'Z'
            return ts
        except:
            return ts
    return ts


def normalize_error_code(exit_code: Any) -> str:
    """Normalize exit codes to consistent string format."""
    if exit_code is None:
        return None
    try:
        return f"EXIT_{int(exit_code)}"
    except (ValueError, TypeError):
        return str(exit_code).upper()


def normalize_event_type(event_type: str) -> str:
    """Normalize event types to consistent format."""
    if not event_type:
        return "UNKNOWN"
    return event_type.strip().lower()


def extract_k8s_events(data: Dict) -> List[Dict]:
    """Extract and normalize Kubernetes events."""
    records = []

    services = data.get('services', {})
    for service_name, service_data in services.items():
        # Extract events
        events = service_data.get('events', [])
        for event in events:
            record = {
                'source_type': 'k8s_event',
                'service': service_name,
                'namespace': service_data.get('namespace'),
                'timestamp': standardize_timestamp(event.get('first_timestamp')),
                'last_timestamp': standardize_timestamp(event.get('last_timestamp')),
                'event_type': normalize_event_type(event.get('event_type')),
                'reason': event.get('reason'),
                'message': event.get('message'),
                'reporting_component': event.get('reporting_component'),
                'count': event.get('count'),
                'involved_object': event.get('involved_object'),
                'cluster': data.get('collection_info', {}).get('cluster'),
            }
            records.append(record)

    return records


def extract_deployment_records(data: Dict) -> List[Dict]:
    """Extract and normalize deployment revision records."""
    records = []

    services = data.get('services', {})
    collection_info = data.get('collection_info', {})
    date_window = collection_info.get('date_window', {})

    for service_name, service_data in services.items():
        deployments = service_data.get('deployments', {})
        for deployment_name, deployment_data in deployments.items():
            revisions = deployment_data.get('revisions', [])
            for revision_info in revisions:
                # Use a generated timestamp since revisions don't have explicit timestamps
                # In a real scenario, these would come from deployment metadata
                record = {
                    'source_type': 'deployment',
                    'service': service_name,
                    'namespace': service_data.get('namespace'),
                    'deployment_name': deployment_name,
                    'revision': revision_info.get('revision'),
                    'change_cause': revision_info.get('change_cause'),
                    'timestamp': f"{date_window.get('start_date')}T00:00:00Z",
                    'cluster': collection_info.get('cluster'),
                    'event_type': 'deployment_rollout',
                    'reason': 'revision_update',
                    'message': f"Deployment {deployment_name} revision {revision_info.get('revision')}",
                }
                records.append(record)

    return records


def extract_pod_records(data: Dict) -> List[Dict]:
    """Extract and normalize pod status records."""
    records = []

    services = data.get('services', {})
    for service_name, service_data in services.items():
        pods = service_data.get('pods', [])
        for pod in pods:
            record = {
                'source_type': 'pod',
                'service': service_name,
                'namespace': service_data.get('namespace'),
                'pod_name': pod.get('name'),
                'status': pod.get('status'),
                'restarts': pod.get('restarts'),
                'failure_reason': pod.get('failure_reason'),
                'failure_message': pod.get('failure_message'),
                'exit_code': pod.get('exit_code'),
                'error_code': normalize_error_code(pod.get('exit_code')),
                'start_time': standardize_timestamp(pod.get('start_time')),
                'error_details': pod.get('error_details'),
                'cluster': data.get('collection_info', {}).get('cluster'),
                'event_type': 'pod_status_change',
                'reason': pod.get('status'),
                'message': f"Pod {pod.get('name')} is {pod.get('status')}",
            }
            records.append(record)

    return records


def extract_argo_workflows(data: Dict) -> List[Dict]:
    """Extract and normalize Argo workflow records."""
    records = []

    templates = data.get('available_workflow_templates', [])

    for template in templates:
        service = template.get('target_service')
        record = {
            'source_type': 'argo_workflow_template',
            'service': service,
            'workflow_name': template.get('name'),
            'git_repo': template.get('git_repo'),
            'container_path': template.get('container_path'),
            'docker_image': template.get('docker_image'),
            'age_days': template.get('age_days'),
            'timestamp': data.get('generated_at'),
            'cluster': data.get('cluster_info', {}).get('cluster'),
            'namespace': data.get('cluster_info', {}).get('namespace'),
            'event_type': 'workflow_template_registered',
            'reason': 'template_available',
            'message': f"Workflow template {template.get('name')} for {service}",
        }
        records.append(record)

    # Add workflow execution records if available
    for service_key in ['pbx_web_build_workflows', 'whisper_stt_build_workflows']:
        workflow_data = data.get(service_key, {})
        runs = workflow_data.get('workflow_runs', [])

        for run in runs:
            service = service_key.replace('_build_workflows', '').replace('_', '-')
            record = {
                'source_type': 'argo_workflow_execution',
                'service': service,
                'workflow_name': run.get('name'),
                'status': run.get('status'),
                'timestamp': standardize_timestamp(run.get('started_at')),
                'cluster': data.get('cluster_info', {}).get('cluster'),
                'namespace': data.get('cluster_info', {}).get('namespace'),
                'event_type': 'workflow_execution',
                'reason': run.get('status'),
                'message': run.get('message'),
            }
            records.append(record)

    # Add a note about data limitations as a record
    limitations = data.get('data_limitations', {})
    record = {
        'source_type': 'argo_data_limitation',
        'service': 'pbx-web',  # Applies to both services
        'event_type': 'data_retention_limitation',
        'reason': 'limited_historical_data',
        'message': limitations.get('missing_data_reason'),
        'timestamp': limitations.get('oldest_workflow_found'),
        'oldest_workflow': limitations.get('oldest_workflow_found'),
        'total_workflows': limitations.get('total_workflows_in_namespace'),
        'cluster': data.get('cluster_info', {}).get('cluster'),
    }
    records.append(record)

    return records


def merge_and_deduplicate(records: List[Dict]) -> List[Dict]:
    """Remove duplicate records while preserving all unique data."""
    seen = set()
    unique_records = []

    for record in records:
        # Create a hash key for deduplication
        key_parts = []
        for field in ['source_type', 'service', 'timestamp', 'reason', 'message']:
            value = record.get(field)
            if value is not None:
                key_parts.append(f"{field}:{value}")

        key = '|'.join(sorted(key_parts))

        if key not in seen:
            seen.add(key)
            unique_records.append(record)

    return unique_records


def sort_records(records: List[Dict]) -> List[Dict]:
    """Sort records by timestamp and service."""
    def sort_key(record):
        timestamp = record.get('timestamp') or ''
        service = record.get('service') or ''
        source_type = record.get('source_type') or ''
        return (timestamp, service, source_type)

    return sorted(records, key=sort_key)


def main():
    # Load input data
    print("Loading input files...")
    with open('/tmp/k8s-logs.json', 'r') as f:
        k8s_data = json.load(f)

    with open('/tmp/argo-logs.json', 'r') as f:
        argo_data = json.load(f)

    print("Extracting records from Kubernetes logs...")
    k8s_events = extract_k8s_events(k8s_data)
    deployments = extract_deployment_records(k8s_data)
    pods = extract_pod_records(k8s_data)

    print("Extracting records from Argo logs...")
    argo_workflows = extract_argo_workflows(argo_data)

    print(f"Records extracted:")
    print(f"  - K8s events: {len(k8s_events)}")
    print(f"  - Deployments: {len(deployments)}")
    print(f"  - Pods: {len(pods)}")
    print(f"  - Argo workflows: {len(argo_workflows)}")

    # Combine all records
    all_records = k8s_events + deployments + pods + argo_workflows

    print(f"Total records before deduplication: {len(all_records)}")

    # Deduplicate
    combined_records = merge_and_deduplicate(all_records)
    print(f"Total records after deduplication: {len(combined_records)}")

    # Sort
    combined_records = sort_records(combined_records)

    # Export JSON
    output_json = '/tmp/combined-logs.json'
    with open(output_json, 'w') as f:
        json.dump(combined_records, f, indent=2, default=str)
    print(f"JSON output written to {output_json}")

    # Export CSV
    output_csv = '/tmp/combined-logs.csv'

    # Get all unique field names
    fieldnames = set()
    for record in combined_records:
        fieldnames.update(record.keys())
    fieldnames = sorted(fieldnames)

    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(combined_records)
    print(f"CSV output written to {output_csv}")

    # Print summary statistics
    print("\nSummary Statistics:")
    services = set(r.get('service') for r in combined_records if r.get('service'))
    source_types = set(r.get('source_type') for r in combined_records if r.get('source_type'))

    print(f"  Services: {sorted(services)}")
    print(f"  Source types: {sorted(source_types)}")
    print(f"  Total records: {len(combined_records)}")

    # Count by service and source type
    by_service = {}
    by_source_type = {}

    for record in combined_records:
        service = record.get('service', 'unknown')
        source_type = record.get('source_type', 'unknown')

        by_service[service] = by_service.get(service, 0) + 1
        by_source_type[source_type] = by_source_type.get(source_type, 0) + 1

    print(f"\nRecords by service:")
    for service, count in sorted(by_service.items()):
        print(f"  {service}: {count}")

    print(f"\nRecords by source type:")
    for source, count in sorted(by_source_type.items()):
        print(f"  {source}: {count}")

    print("\nTransformation complete!")
    return combined_records


if __name__ == '__main__':
    main()
