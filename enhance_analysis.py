#!/usr/bin/env python3
"""
Enhanced deployment pattern analysis with deeper insights.
"""

import json
from datetime import datetime
from pathlib import Path

def enhance_analysis():
    """Add deeper insights to the existing analysis."""
    
    # Load existing analysis
    with open('/home/coding/scratch/deployment-patterns-analysis.json', 'r') as f:
        analysis = json.load(f)
    
    # Add detailed deployment behavior analysis
    analysis['deployment_behaviors'] = {
        'pbx_web': {
            'strategy': 'Frequent deployment pattern',
            'frequency_description': '11 deployments in 30 days (~2.7 day intervals)',
            'stability_factors': [
                '0 pod restarts indicates stable container runtime',
                '6625 health checks all passing',
                'Recording fetch errors are application-level, not infrastructure'
            ],
            'risk_factors': [
                'High deployment frequency increases surface area for errors',
                'Connectivity errors suggest upstream storage dependencies'
            ]
        },
        'whisper_stt': {
            'strategy': 'Long-running stable deployments',
            'frequency_description': '2 deployments (whisper-openai: revision 24, whisper-stt: revision 32)',
            'stability_factors': [
                '100% pod stability over 28 days',
                '0 HTTP errors across 97,658 requests',
                'Simple health-check only traffic pattern'
            ],
            'risk_factors': [
                'Lower deployment frequency may mask deployment process issues',
                'Health-check only traffic may not represent real-world load'
            ]
        }
    }
    
    # Add failure mode taxonomy
    analysis['failure_taxonomy'] = {
        'connectivity_failures': {
            'description': 'Network-related connection issues',
            'affected_service': 'pbx-web',
            'patterns': [
                'Connection reset by peer (errno 104)',
                'Broken pipe (errno 32)'
            ],
            'likely_causes': [
                'Upstream storage backend connectivity issues',
                'Network-level interruptions',
                'Storage service restarts or maintenance'
            ],
            'mitigation_strategies': [
                'Implement retry logic with exponential backoff',
                'Add circuit breakers for storage backend calls',
                'Consider adding persistent connection pooling'
            ]
        },
        'http_server_errors': {
            'description': 'HTTP 5xx errors generated during application processing',
            'affected_service': 'pbx-web',
            'patterns': [
                'HTTP 500 errors during recording fetch failures'
            ],
            'likely_causes': [
                'Unhandled exceptions in recording fetch code',
                'Cascading failures from connectivity issues'
            ],
            'mitigation_strategies': [
                'Add graceful error handling for recording fetch failures',
                'Implement fallback mechanisms for recording access',
                'Add monitoring and alerting for recording fetch success rates'
            ]
        }
    }
    
    # Add infrastructure dependency analysis
    analysis['infrastructure_analysis'] = {
        'shared_dependencies': {
            'cluster_infrastructure': {
                'dependency': 'ardenone-cluster',
                'impact': 'Both services share cluster-level risks (API server, networking, DNS)',
                'failure_impact': 'HIGH - Cluster-wide issues would affect both services'
            },
            'container_runtime': {
                'dependency': 'Container runtime (containerd/docker)',
                'impact': 'Pod stability and restart behavior',
                'failure_impact': 'MEDIUM - Both show 0 restarts, indicating stable runtime'
            },
            'resource_constraints': {
                'dependency': 'CPU (8 cores), Memory (8Gi)',
                'impact': 'Resource limits affect performance and stability',
                'failure_impact': 'LOW - Both services have adequate headroom (requests: 1 CPU, 4Gi memory)'
            }
        },
        'service_specific_dependencies': {
            'pbx_web': [
                'Storage backend (recording fetch errors indicate external dependency)',
                'Site-generator container',
                'Nginx reverse proxy'
            ],
            'whisper_stt': [
                'PVC storage for model caches (3 PVCs)',
                'Whisper models (large-v3-turbo, distil-large-v3)',
                'Single traffic pattern (health checks only)'
            ]
        }
    }
    
    # Add operational insights
    analysis['operational_insights'] = {
        'deployment_maturity': {
            'pbx_web': {
                'maturity_level': 'HIGH - Continuous deployment pattern',
                'indicators': ['Frequent deployments', 'Active monitoring', 'Error tracking'],
                'recommendations': ['Focus on upstream storage reliability', 'Improve error handling for recording fetches']
            },
            'whisper_stt': {
                'maturity_level': 'MEDIUM - Stable but infrequent deployments',
                'indicators': ['Long-running pods', 'Simple architecture', 'High stability'],
                'recommendations': ['Increase deployment frequency to test deployment process', 'Add load testing beyond health checks']
            }
        },
        'monitoring_gaps': {
            'common_gaps': [
                'No latency data available for either service',
                'Limited pod event history coverage',
                'No rollback frequency tracking in current data'
            ],
            'service_specific': {
                'pbx_web': ['Victorialogs retention < 7 hours limits historical analysis'],
                'whisper_stt': ['Health-check only traffic may not reflect production load patterns']
            }
        }
    }
    
    # Add correlation analysis
    analysis['correlation_analysis'] = {
        'temporal_correlation': {
            'finding': 'No temporal correlation in failures detected',
            'reasoning': 'whisper-stt shows 0 errors, pbx-web shows intermittent connectivity issues',
            'conclusion': 'Failures are service-specific, not infrastructure-wide'
        },
        'infrastructure_correlation': {
            'finding': 'Both services show excellent pod stability (0 restarts)',
            'reasoning': 'Shared container runtime and cluster infrastructure are healthy',
            'conclusion': 'Infrastructure stability is high, issues are application-level'
        },
        'deployment_pattern_correlation': {
            'finding': 'Different deployment frequencies',
            'reasoning': 'pbx-web: 11 deployments vs whisper-stt: 2 deployments',
            'conclusion': 'Different deployment strategies - pbx-web is CD-focused, whisper-stt is stability-focused'
        }
    }
    
    # Save enhanced analysis
    output_file = Path('/home/coding/scratch/deployment-patterns-analysis.json')
    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)
    
    print(f"Enhanced analysis saved to {output_file}")
    print(f"Added sections:")
    print(f"  - deployment_behaviors")
    print(f"  - failure_taxonomy")
    print(f"  - infrastructure_analysis")
    print(f"  - operational_insights")
    print(f"  - correlation_analysis")

if __name__ == '__main__':
    enhance_analysis()
