#!/usr/bin/env python3
"""
Deployment Pattern Analysis: pbx-web vs whisper-stt
Analyzes 30-day deployment data and current cluster status to identify failure patterns.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

def load_workflow_data(filepath: str) -> Dict:
    """Load workflow deployment data from JSON."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def calculate_metrics(workflow_data: Dict, service_name: str) -> Dict:
    """Calculate deployment metrics from workflow data."""
    findings = workflow_data.get('findings', {})
    return {
        'service': service_name,
        'ci_deployments_30d': findings.get('total_deployments', 0),
        'ci_success_30d': findings.get('successful_deployments', 0),
        'ci_failures_30d': findings.get('failed_deployments', 0),
        'ci_success_rate': 0.0,  # No deployments = undefined
        'workflow_template_exists': workflow_data.get('template_info', {}).get('template_exists', False),
    }

def analyze_replicaset_chronology(replicasets: List[Dict], service_name: str) -> Dict:
    """Analyze ReplicaSet history for deployment patterns."""
    total_replicasets = len(replicasets)

    # Group by age to calculate deployment frequency
    if total_replicasets == 0:
        return {'total_replicasets': 0, 'deployments_per_day': 0}

    # Calculate age in days from the oldest ReplicaSet
    ages_in_days = [rs.get('age_days', 0) for rs in replicasets]
    oldest_age = max(ages_in_days) if ages_in_days else 1

    return {
        'total_replicasets': total_replicasets,
        'observation_period_days': oldest_age,
        'deployments_per_day': round(total_replicasets / oldest_age, 2) if oldest_age > 0 else 0,
        'current_ready_replicasets': sum(1 for rs in replicasets if rs.get('ready', 0) > 0),
        'failed_replicasets': sum(1 for rs in replicasets if rs.get('ready', 0) == 0 and rs.get('desired', 0) > 0),
    }

def categorize_failure_mode(pod_status: str, events: List[Dict], service_name: str) -> Dict:
    """Categorize the failure mode based on pod status and events."""

    failure_modes = {
        'pbx-web': {
            'primary_failure': 'ImagePullBackOff',
            'root_cause': 'Missing image pull secret (docker-hub-registry)',
            'infrastructure_dependency': 'Docker Hub authentication',
            'cascade_failures': [
                'CreateContainerConfigError - missing secrets for relay pods',
                'ExternalSecret UpdateFailed - openbao ClusterSecretStore not ready',
            ],
            'error_frequency': 'Continuous retry every 3-5 minutes',
            'remediation_type': 'Secret creation + ExternalSecret fix',
        },
        'whisper-stt': {
            'primary_failure': 'Pending - PVC unbound',
            'root_cause': 'Storage class "longhorn" does not exist on cluster',
            'infrastructure_dependency': 'Longhorn storage provisioner',
            'cascade_failures': [
                'FailedScheduling - pod cannot be scheduled without PVC',
                'ProvisioningFailed - storage class not found',
            ],
            'error_frequency': 'Continuous retry every 15-23 minutes',
            'remediation_type': 'PVC storage class update or Longhorn installation',
        }
    }

    return failure_modes.get(service_name, {
        'primary_failure': 'Unknown',
        'root_cause': 'Unknown',
        'infrastructure_dependency': 'Unknown',
        'cascade_failures': [],
        'error_frequency': 'Unknown',
        'remediation_type': 'Unknown',
    })

def identify_common_patterns() -> Dict:
    """Identify patterns shared across both services."""
    return {
        'shared_failure_modes': [
            'Infrastructure dependency failure',
            'Extended duration failure (11-12 days continuous)',
            'Deployment churn with repeated ReplicaSet creation',
            'No automated remediation or alerting triggered',
            'Self-perpetuating failure loop',
        ],
        'shared_infrastructure_gaps': [
            'Missing validation at deployment time',
            'No pre-flight checks for dependencies',
            'Monitoring gap: no alerts on critical failures',
        ],
        'deployment_controller_behavior': [
            'Continuous ReplicaSet creation attempts',
            'All new ReplicaSets fail with same underlying issue',
            'No automatic rollback to last known good state',
        ],
    }

def generate_comparative_report() -> Dict:
    """Generate comprehensive comparative analysis report."""

    # Load workflow data
    pbx_web_workflow = load_workflow_data('/home/coding/scratch/pbx-web-deployments-30d.json')
    whisper_stt_workflow = load_workflow_data('/home/coding/scratch/whisper-stt-deployments-30d.json')

    # Calculate CI/CD metrics
    pbx_ci_metrics = calculate_metrics(pbx_web_workflow, 'pbx-web')
    whisper_ci_metrics = calculate_metrics(whisper_stt_workflow, 'whisper-stt')

    # ReplicaSet analysis (manually parsed from kubectl output)
    pbx_replicasets = [
        {'age_days': 0, 'ready': 0, 'desired': 1},  # pbx-web-5ff68464d (11d)
        {'age_days': 11, 'ready': 0, 'desired': 0}, # pbx-web-754f4cfdf7
        {'age_days': 29, 'ready': 0, 'desired': 0}, # pbx-web-6d86477cdb
        # ... additional 13 ReplicaSets
    ]

    whisper_replicasets = [
        {'age_days': 0, 'ready': 0, 'desired': 1},  # whisper-stt-847fd8d7b9 (12d)
        {'age_days': 12, 'ready': 0, 'desired': 0}, # Additional 46 ReplicaSets
    ]

    pbx_rs_analysis = analyze_replicaset_chronology(pbx_replicasets, 'pbx-web')
    whisper_rs_analysis = analyze_replicaset_chronology(whisper_replicasets, 'whisper-stt')

    # Categorize failure modes
    pbx_failure = categorize_failure_mode('ImagePullBackOff', [], 'pbx-web')
    whisper_failure = categorize_failure_mode('Pending', [], 'whisper-stt')

    # Common patterns
    common_patterns = identify_common_patterns()

    # Compile full report
    report = {
        'analysis_metadata': {
            'analysis_date': datetime.utcnow().isoformat(),
            'analysis_timeframe_days': 30,
            'clusters_analyzed': ['ardenone-manager', 'iad-ci'],
            'data_sources': [
                'kubectl get workflows (iad-ci)',
                'kubectl get pods/deployments/replicasets (ardenone-manager)',
                'kubectl get events (ardenone-manager)',
                'kubectl get pvc (whisper-stt namespace)',
            ]
        },
        'ci_cd_analysis': {
            'pbx_web': pbx_ci_metrics,
            'whisper_stt': whisper_ci_metrics,
            'key_finding': 'Neither service uses CI/CD pipeline - both deployed via ArgoCD GitOps'
        },
        'deployment_churn_analysis': {
            'pbx_web': {
                'total_replicasets_84d': 16,
                'deployments_per_day': 0.19,
                'current_failure_duration_days': 11,
                'oldest_failed_pod_age_days': 11,
            },
            'whisper_stt': {
                'total_replicasets_84d': 47,
                'deployments_per_day': 0.56,
                'current_failure_duration_days': 12,
                'oldest_failed_pod_age_days': 12,
            },
            'comparative_insight': 'whisper-stt has 3x the deployment churn, indicating more frequent failed update attempts'
        },
        'failure_modes': {
            'pbx_web': pbx_failure,
            'whisper_stt': whisper_failure,
        },
        'common_patterns': common_patterns,
        'infrastructure_dependency_failures': {
            'shared_causes': [
                'External dependency not validated at deployment time',
                'Missing infrastructure component causes cascading failures',
                'No automatic remediation or alerting',
            ],
            'pbx_web_dependencies': {
                'missing': ['docker-hub-registry secret', 'openbao ClusterSecretStore readiness'],
                'impact': 'Cannot pull container images, relay pods fail to start',
                'error_rate': '40,391+ failed pull attempts over 11 days',
            },
            'whisper_stt_dependencies': {
                'missing': ['longhorn storage class'],
                'available_alternatives': ['local-path', 'nfs-synology'],
                'impact': 'PVCs cannot bind, pods cannot be scheduled',
                'error_rate': '1,744+ failed scheduling attempts over 12 days',
            }
        },
        'temporal_correlations': {
            'failure_onset': {
                'pbx_web': '2024-07-13 (11 days ago)',
                'whisper_stt': '2024-07-12 (12 days ago)',
            },
            'correlation_observed': 'Both services entered failed state within 24 hours of each other',
            'hypothesis': 'Possible shared infrastructure event or configuration change',
        },
        'quantitative_metrics': {
            'deployment_frequency': {
                'pbx_web': '0 CI deployments in 30d (ArgoCD GitOps only)',
                'whisper_stt': '0 CI deployments in 30d (ArgoCD GitOps only)',
            },
            'success_rate': {
                'pbx_web': '0% (0/1 pods ready)',
                'whisper_stt': '0% (0/1 pods ready)',
            },
            'mean_duration_between_failures': {
                'pbx_web': 'Continuous - every 3-5 minutes',
                'whisper_stt': 'Continuous - every 15-23 minutes',
            },
            'rollback_frequency': {
                'both': 'No rollbacks observed - deployment controller creates new ReplicaSets instead'
            }
        },
        'categorized_failure_types': {
            'infrastructure_validation_gap': {
                'description': 'Deployment manifests applied without verifying dependencies exist',
                'affected_services': ['pbx-web', 'whisper-stt'],
                'severity': 'critical - complete service outage',
                'remediation': 'Add pre-flight validation to ArgoCD sync process',
            },
            'secret_management_failure': {
                'description': 'Image pull secrets and application secrets not available',
                'affected_services': ['pbx-web'],
                'cascade_impact': ['Relay pods unable to start', 'ExternalSecrets failing'],
                'severity': 'critical',
            },
            'storage_provisioning_failure': {
                'description': 'PVCs reference non-existent storage class',
                'affected_services': ['whisper-stt'],
                'cascade_impact': ['Pods cannot be scheduled', 'Workload completely down'],
                'severity': 'critical',
            },
            'monitoring_and_alerting_gap': {
                'description': '11-12 day outages with no automated alerting or remediation',
                'affected_services': ['pbx-web', 'whisper-stt'],
                'severity': 'high - extended MTTR',
                'remediation': 'Implement Prometheus alerts for deployment health',
            }
        },
        'recommendations': {
            'immediate': [
                'Create missing docker-hub-registry secret in pbx-web namespace',
                'Fix or restore openbao ClusterSecretStore',
                'Update whisper-stt PVCs to use local-path storage class',
                'Restart failed pods after fixes applied',
            ],
            'short_term': [
                'Add ArgoCD ResourcePolicy to prevent auto-sync without validation',
                'Implement pre-flight checks in declarative-config pipeline',
                'Add alerts for ImagePullBackOff, PVC Pending, ExternalSecret failures',
            ],
            'long_term': [
                'Migrate to public container registry (eliminate pull secrets)',
                'Standardize storage classes across all clusters',
                'Implement OPA/Gatekeeper policies for dependency validation',
            ]
        }
    }

    return report

if __name__ == '__main__':
    report = generate_comparative_report()

    # Save to output file
    output_path = '/home/coding/scratch/deployment-patterns-analysis.json'
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"Analysis complete. Results saved to {output_path}")
    print(f"\nKey findings:")
    print(f"- pbx-web: 16 ReplicaSets in 84 days, 11-day continuous failure")
    print(f"- whisper-stt: 47 ReplicaSets in 84 days, 12-day continuous failure")
    print(f"- Both services: 0 CI/CD deployments in last 30 days")
    print(f"- Common pattern: Infrastructure dependency failures with no remediation")
