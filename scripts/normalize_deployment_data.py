#!/usr/bin/env python3
"""
Normalize deployment data from pbx-web and whisper-stt 30-day analyses.
Extracts key metrics into a comparable format for synthesis.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def normalize_timestamp(ts_str: str | None) -> str | None:
    """Ensure timestamp is in ISO format."""
    if not ts_str:
        return None
    try:
        # Parse and re-format to ensure ISO 8601
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return dt.isoformat()
    except Exception:
        return ts_str


def determine_deployment_status(replica: Dict[str, Any]) -> str:
    """
    Determine deployment status from replica set data.
    Returns: 'success', 'failed', 'pending', 'unknown'
    """
    status = replica.get('status', 'unknown')

    # Check for explicit failure indicators
    if status == 'failed':
        return 'failed'

    # Check for success indicators
    ready = replica.get('readyReplicas', 0)
    available = replica.get('availableReplicas', 0)
    replicas = replica.get('replicas', 0)

    if status == 'active' and ready > 0 and available > 0:
        return 'success'
    elif status == 'inactive' and replicas == 0:
        # This is expected for old replicaSets - they were successful when deployed
        return 'success'
    elif status == 'pending' or (status == 'active' and ready == 0):
        return 'pending'

    return 'unknown'


def extract_failure_type(replica: Dict[str, Any]) -> str | None:
    """Extract or infer failure type from replica set data."""
    status = replica.get('status')

    if status == 'failed':
        return 'rollout_failed'
    if status == 'pending':
        return 'deployment_pending'

    # Check for crash loops or OOM from pod data if available
    # This would need to be cross-referenced with pod_status data

    return None


def normalize_deployment(data: Dict[str, Any], service_name: str) -> List[Dict[str, Any]]:
    """
    Normalize deployment data for a single service.

    Args:
        data: Raw deployment JSON data
        service_name: Name of the service (e.g., 'pbx-web', 'whisper-stt')

    Returns:
        List of normalized deployment records
    """
    normalized_records = []

    # Extract replicasets from deployment_history_30_days
    replicasets = data.get('deployment_history_30_days', {}).get('replicasets', [])

    for replica in replicasets:
        # Determine if this was a successful deployment
        deployment_status = determine_deployment_status(replica)
        failure_type = extract_failure_type(replica)

        record = {
            'service': service_name,
            'deployment_name': replica.get('deployment', 'unknown'),
            'replicaset_name': replica.get('name'),
            'timestamp': normalize_timestamp(replica.get('created')),
            'status': deployment_status,
            'failure_type': failure_type,
            'revision': replica.get('revision'),
            'replicas': replica.get('replicas', 0),
            'ready_replicas': replica.get('readyReplicas', 0),
            'available_replicas': replica.get('availableReplicas', 0),
            'image': replica.get('image'),
            'cluster': data.get('report_metadata', {}).get('cluster', 'unknown'),
            'namespace': data.get('report_metadata', {}).get('namespace', 'unknown'),
        }
        normalized_records.append(record)

    return normalized_records


def add_summary_metrics(normalized_data: List[Dict[str, Any]], source_data: Dict[str, Any], service_name: str) -> Dict[str, Any]:
    """Add summary metrics from the source data."""
    events_summary = source_data.get('deployment_history_30_days', {}).get('deployment_events_summary', {})
    health_assessment = source_data.get('deployment_health_assessment', {})
    pod_metrics = source_data.get('pod_status', {}).get('pod_metrics', {})
    error_incidents = source_data.get('error_incidents', {})
    log_analysis = source_data.get('log_analysis', {})

    return {
        'service': service_name,
        'total_deployments': events_summary.get('total_deployments', 0),
        'total_replicasets': events_summary.get('total_replicasets_in_30d', 0),
        'successful_updates': events_summary.get('successful_updates', 0),
        'failed_rollouts': events_summary.get('failed_rollouts', 0),
        'rollback_events': events_summary.get('rollback_events', 0),
        'last_deployment_update': normalize_timestamp(events_summary.get('last_deployment_update')),
        'overall_health': health_assessment.get('overall_health', 'unknown'),
        'deployment_stability': health_assessment.get('deployment_stability', 'unknown'),
        'uptime_percentage': health_assessment.get('uptime_percentage', 'unknown'),
        'zero_downtime_deployment': health_assessment.get('zero_downtime_deployment', False),
        'successful_deployment_rate': health_assessment.get('successful_deployment_rate', 'unknown'),
        'total_pods': pod_metrics.get('total_pods', 0),
        'running_pods': pod_metrics.get('running_pods', 0),
        'total_restarts': pod_metrics.get('total_restarts', 0),
        'crashloops': pod_metrics.get('crashloops', 0),
        'oomkills': pod_metrics.get('oomkills', 0),
        'total_incidents': error_incidents.get('total_incidents', 0),
        'critical_incidents': error_incidents.get('critical_incidents', 0),
        'warning_incidents': error_incidents.get('warning_incidents', 0),
        'log_errors': sum(
            log_data.get('errors_detected', 0)
            for log_data in log_analysis.values()
            if isinstance(log_data, dict)
        ),
    }


def main():
    """Main function to normalize both deployment datasets."""
    # Define paths
    base_dir = Path('/home/coding/aide-de-camp')
    research_dir = base_dir / 'docs' / 'research'

    pbx_web_file = research_dir / 'pbx-web-deployments-30d.json'
    whisper_stt_file = research_dir / 'whisper-stt-deployments-30d.json'
    output_file = research_dir / 'deployment-data-normalized.json'

    # Load source data
    print(f"Loading pbx-web data from {pbx_web_file}")
    with open(pbx_web_file) as f:
        pbx_web_data = json.load(f)

    print(f"Loading whisper-stt data from {whisper_stt_file}")
    with open(whisper_stt_file) as f:
        whisper_stt_data = json.load(f)

    # Normalize deployment records
    print("Normalizing deployment records...")
    pbx_web_records = normalize_deployment(pbx_web_data, 'pbx-web')
    whisper_stt_records = normalize_deployment(whisper_stt_data, 'whisper-stt')

    all_records = pbx_web_records + whisper_stt_records

    # Sort by timestamp
    all_records.sort(key=lambda x: x['timestamp'] or '')

    # Add summary metrics
    print("Adding summary metrics...")
    pbx_web_summary = add_summary_metrics(pbx_web_records, pbx_web_data, 'pbx-web')
    whisper_stt_summary = add_summary_metrics(whisper_stt_records, whisper_stt_data, 'whisper-stt')

    # Create output structure
    output_data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'source_files': [
                str(pbx_web_file.name),
                str(whisper_stt_file.name),
            ],
            'total_records': len(all_records),
        },
        'summaries': {
            'pbx-web': pbx_web_summary,
            'whisper-stt': whisper_stt_summary,
        },
        'deployment_records': all_records,
    }

    # Write output
    print(f"Writing normalized data to {output_file}")
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    # Data quality verification
    print("\n=== Data Quality Verification ===")

    missing_timestamps = [r for r in all_records if not r['timestamp']]
    if missing_timestamps:
        print(f"⚠️  WARNING: {len(missing_timestamps)} records missing timestamps")
    else:
        print("✓ All records have timestamps")

    missing_status = [r for r in all_records if not r['status'] or r['status'] == 'unknown']
    if missing_status:
        print(f"⚠️  WARNING: {len(missing_status)} records have unknown status")
    else:
        print("✓ All records have valid status")

    print(f"\n✓ Total deployment records: {len(all_records)}")
    print(f"✓ pbx-web records: {len(pbx_web_records)}")
    print(f"✓ whisper-stt records: {len(whisper_stt_records)}")

    # Print summary statistics
    print("\n=== Summary Statistics ===")
    for service, summary in output_data['summaries'].items():
        print(f"\n{service}:")
        print(f"  Total deployments: {summary['total_deployments']}")
        print(f"  Successful updates: {summary['successful_updates']}")
        print(f"  Failed rollouts: {summary['failed_rollouts']}")
        print(f"  Overall health: {summary['overall_health']}")
        print(f"  Uptime: {summary['uptime_percentage']}")

    print("\n✓ Normalization complete!")


if __name__ == '__main__':
    main()
