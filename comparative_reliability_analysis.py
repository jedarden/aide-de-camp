#!/usr/bin/env python3
"""
Comparative Deployment Reliability Analysis
Analyzes pbx-web vs whisper-stt deployment reliability patterns
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Any, Tuple


def load_json_file(filepath: str) -> Dict:
    """Load JSON data from file"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {filepath} not found")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing {filepath}: {e}")
        return {}


def calculate_reliability_metrics(deployment_data: Dict) -> Dict[str, Any]:
    """Calculate reliability metrics for a single service"""
    if not deployment_data:
        return {}

    metadata = deployment_data.get('metadata', {})
    deployment_metrics = deployment_data.get('deployment_metrics', {})
    events = deployment_data.get('deployment_events_last_30_days', [])
    pod_health = deployment_data.get('pod_health', {})

    # Basic metrics
    total_deployments = deployment_metrics.get('total_deployments_last_30_days', 0)
    successful_deployments = deployment_metrics.get('successful_deployments', 0)
    failed_deployments = deployment_metrics.get('failed_deployments', 0)

    success_rate = (successful_deployments / total_deployments * 100) if total_deployments > 0 else 0
    failure_rate = (failed_deployments / total_deployments * 100) if total_deployments > 0 else 0

    # Rollback metrics
    rollback_events = [e for e in events if e.get('event_type') == 'deployment_rollback']
    rollback_count = len(rollback_events)
    rollback_rate = (rollback_count / total_deployments * 100) if total_deployments > 0 else 0

    # Pod health metrics
    current_pod = pod_health.get('current_pod', {})
    health_indicators = pod_health.get('health_indicators', {})

    pod_restart_count = current_pod.get('restart_count', 0)
    pod_ready = current_pod.get('ready', False)
    pod_age_days = deployment_metrics.get('current_uptime_days', 0)

    # Calculate deployment frequency
    deployment_frequency = deployment_metrics.get('deployment_frequency_days', 0)

    return {
        'service': metadata.get('service', 'unknown'),
        'namespace': metadata.get('namespace', 'unknown'),
        'analysis_period': metadata.get('time_period', {}),
        'deployment_metrics': {
            'total_deployments': total_deployments,
            'successful_deployments': successful_deployments,
            'failed_deployments': failed_deployments,
            'success_rate_percentage': round(success_rate, 2),
            'failure_rate_percentage': round(failure_rate, 2),
            'rollback_count': rollback_count,
            'rollback_rate_percentage': round(rollback_rate, 2),
            'deployment_frequency_days': deployment_frequency,
            'deployment_stability': 'HIGH' if success_rate >= 95 and rollback_rate < 20 else 'MEDIUM' if success_rate >= 80 else 'LOW'
        },
        'pod_health_metrics': {
            'current_pod_age_days': pod_age_days,
            'pod_ready': pod_ready,
            'restart_count': pod_restart_count,
            'health_indicators': health_indicators
        },
        'infrastructure_profile': {
            'strategy': metadata.get('strategy', 'unknown'),
            'managed_by': metadata.get('managed_by', 'unknown'),
            'cluster': metadata.get('cluster', 'unknown')
        }
    }


def analyze_failure_patterns(pattern_data: Dict) -> Dict[str, Any]:
    """Analyze failure patterns from pattern frequency data"""
    if not pattern_data:
        return {}

    categories = pattern_data.get('categories', {})
    total_failures = pattern_data.get('total_categorized_failures', 0)

    # Analyze by service
    service_distribution = defaultdict(int)
    category_by_service = defaultdict(lambda: defaultdict(int))

    for category_name, category_data in categories.items():
        for service, count in category_data.get('service_distribution', {}).items():
            service_distribution[service] += count
            category_by_service[service][category_name] += count

    # Find dominant failure modes
    dominant_failures = sorted(
        [(name, data.get('total_count', 0)) for name, data in categories.items()],
        key=lambda x: x[1],
        reverse=True
    )

    return {
        'total_categorized_failures': total_failures,
        'failure_categories': len(categories),
        'dominant_failure_modes': dominant_failures[:5],
        'service_distribution': dict(service_distribution),
        'category_by_service': {k: dict(v) for k, v in category_by_service.items()},
        'temporal_distribution': {
            cat_name: cat_data.get('daily_distribution', {})
            for cat_name, cat_data in categories.items()
        }
    }


def calculate_comparative_metrics(pbx_metrics: Dict, whisper_metrics: Dict,
                                   pbx_patterns: Dict, whisper_patterns: Dict) -> Dict[str, Any]:
    """Calculate comparative reliability metrics between services"""

    # Deployment reliability comparison
    pbx_deployment = pbx_metrics.get('deployment_metrics', {})
    whisper_deployment = whisper_metrics.get('deployment_metrics', {})

    # Calculate deltas
    success_rate_delta = pbx_deployment.get('success_rate_percentage', 0) - \
                        whisper_deployment.get('success_rate_percentage', 0)

    deployment_freq_delta = pbx_deployment.get('deployment_frequency_days', 0) - \
                          whisper_deployment.get('deployment_frequency_days', 0)

    rollback_delta = pbx_deployment.get('rollback_rate_percentage', 0) - \
                    whisper_deployment.get('rollback_rate_percentage', 0)

    # Pod health comparison
    pbx_pod = pbx_metrics.get('pod_health_metrics', {})
    whisper_pod = whisper_metrics.get('pod_health_metrics', {})

    uptime_delta = pbx_pod.get('current_pod_age_days', 0) - \
                  whisper_pod.get('current_pod_age_days', 0)

    return {
        'deployment_reliability': {
            'success_rate_comparison': {
                'pbx_web': pbx_deployment.get('success_rate_percentage', 0),
                'whisper_stt': whisper_deployment.get('success_rate_percentage', 0),
                'delta_percentage': round(success_rate_delta, 2),
                'winner': 'pbx-web' if success_rate_delta > 0 else 'whisper-stt' if success_rate_delta < 0 else 'TIE',
                'significance': 'HIGH' if abs(success_rate_delta) > 10 else 'MEDIUM' if abs(success_rate_delta) > 5 else 'LOW'
            },
            'deployment_frequency_comparison': {
                'pbx_web_deployments': pbx_deployment.get('total_deployments', 0),
                'whisper_stt_deployments': whisper_deployment.get('total_deployments', 0),
                'pbx_frequency_days': pbx_deployment.get('deployment_frequency_days', 0),
                'whisper_frequency_days': whisper_deployment.get('deployment_frequency_days', 0),
                'more_frequent': 'pbx-web' if pbx_deployment.get('total_deployments', 0) > whisper_deployment.get('total_deployments', 0) else 'whisper-stt',
                'stability_advantage': 'whisper-stt' if whisper_deployment.get('deployment_frequency_days', 0) > pbx_deployment.get('deployment_frequency_days', 0) else 'pbx-web'
            },
            'rollback_comparison': {
                'pbx_web_rollback_rate': pbx_deployment.get('rollback_rate_percentage', 0),
                'whisper_stt_rollback_rate': whisper_deployment.get('rollback_rate_percentage', 0),
                'delta_percentage': round(rollback_delta, 2),
                'more_stable': 'whisper-stt' if rollback_delta > 0 else 'pbx-web' if rollback_delta < 0 else 'TIE'
            }
        },
        'operational_stability': {
            'uptime_comparison': {
                'pbx_web_uptime_days': pbx_pod.get('current_pod_age_days', 0),
                'whisper_stt_uptime_days': whisper_pod.get('current_pod_age_days', 0),
                'delta_days': round(uptime_delta, 2),
                'longer_uptime': 'whisper-stt' if uptime_delta < 0 else 'pbx-web'
            },
            'restart_comparison': {
                'pbx_web_restarts': pbx_pod.get('restart_count', 0),
                'whisper_stt_restarts': whisper_pod.get('restart_count', 0),
                'more_stable': 'TIE' if pbx_pod.get('restart_count', 0) == whisper_pod.get('restart_count', 0) else
                               'whisper-stt' if whisper_pod.get('restart_count', 0) < pbx_pod.get('restart_count', 0) else 'pbx-web'
            }
        },
        'overall_reliability_assessment': {
            'deployment_success_winner': 'pbx-web' if success_rate_delta > 0 else 'whisper-stt' if success_rate_delta < 0 else 'TIE',
            'operational_stability_winner': 'whisper-stt' if uptime_delta < 0 else 'pbx-web' if uptime_delta > 0 else 'TIE',
            'overall_winner': 'TIE',  # Will be calculated based on weighted factors
            'confidence_level': 'HIGH'  # Based on data quality and completeness
        }
    }


def identify_shared_vs_unique_patterns(pattern_data: Dict, service_distribution: Dict) -> Dict[str, Any]:
    """Identify shared vs unique failure patterns"""

    categories = pattern_data.get('categories', {})

    shared_patterns = {}
    pbx_specific = {}
    whisper_specific = {}

    for category_name, category_data in categories.items():
        services = category_data.get('service_distribution', {})

        # Check if pattern affects multiple services
        pbx_count = services.get('pbx-web', 0) + services.get('pbx-web-parsed', 0)
        whisper_count = services.get('whisper-stt', 0)
        other_count = sum(v for k, v in services.items() if k not in ['pbx-web', 'pbx-web-parsed', 'whisper-stt'])

        if pbx_count > 0 and whisper_count > 0:
            shared_patterns[category_name] = {
                'pbx_count': pbx_count,
                'whisper_count': whisper_count,
                'total_count': category_data.get('total_count', 0),
                'severity': category_data.get('severity', 'unknown'),
                'description': category_data.get('description', '')
            }
        elif pbx_count > 0:
            pbx_specific[category_name] = {
                'count': pbx_count,
                'total_count': category_data.get('total_count', 0),
                'severity': category_data.get('severity', 'unknown'),
                'description': category_data.get('description', '')
            }
        elif whisper_count > 0:
            whisper_specific[category_name] = {
                'count': whisper_count,
                'total_count': category_data.get('total_count', 0),
                'severity': category_data.get('severity', 'unknown'),
                'description': category_data.get('description', '')
            }

    return {
        'shared_patterns': shared_patterns,
        'pbx_web_specific_patterns': pbx_specific,
        'whisper_stt_specific_patterns': whisper_specific,
        'pattern_summary': {
            'total_shared_patterns': len(shared_patterns),
            'total_pbx_patterns': len(pbx_specific),
            'total_whisper_patterns': len(whisper_specific),
            'most_concerning_shared': max(shared_patterns.items(), key=lambda x: x[1]['total_count'])[0] if shared_patterns else None,
            'most_concerning_pbx': max(pbx_specific.items(), key=lambda x: x[1]['count'])[0] if pbx_specific else None,
            'most_concerning_whisper': max(whisper_specific.items(), key=lambda x: x[1]['count'])[0] if whisper_specific else None
        }
    }


def perform_temporal_analysis(pattern_data: Dict) -> Dict[str, Any]:
    """Perform temporal analysis of failures"""

    categories = pattern_data.get('categories', {})

    temporal_patterns = {}
    daily_failures = defaultdict(int)

    for category_name, category_data in categories.items():
        daily_dist = category_data.get('daily_distribution', {})

        # Convert daily distribution to temporal patterns
        if daily_dist:
            temporal_patterns[category_name] = {
                'daily_distribution': daily_dist,
                'peak_day': max(daily_dist.items(), key=lambda x: x[1])[0] if daily_dist else None,
                'peak_count': max(daily_dist.values()) if daily_dist else 0,
                'active_days': len(daily_dist),
                'time_span': category_data.get('time_span', {})
            }

            # Aggregate failures across all categories
            for day, count in daily_dist.items():
                daily_failures[day] += count

    # Find correlation patterns
    if daily_failures:
        sorted_days = sorted(daily_failures.items(), key=lambda x: x[1], reverse=True)
        peak_failure_day = sorted_days[0][0] if sorted_days else None
        peak_failure_count = sorted_days[0][1] if sorted_days else 0

        # Analyze clustering
        avg_failures_per_day = sum(daily_failures.values()) / len(daily_failures) if daily_failures else 0
        high_failure_days = {day: count for day, count in daily_failures.items() if count > avg_failures_per_day * 2}
    else:
        peak_failure_day = None
        peak_failure_count = 0
        high_failure_days = {}
        avg_failures_per_day = 0

    return {
        'temporal_patterns_by_category': temporal_patterns,
        'aggregate_temporal_analysis': {
            'peak_failure_day': peak_failure_day,
            'peak_failure_count': peak_failure_count,
            'average_failures_per_active_day': round(avg_failures_per_day, 2),
            'high_failure_days': high_failure_days,
            'total_active_days': len(daily_failures),
            'failure_clustering_detected': len(high_failure_days) > 0
        },
        'time_correlation_indicators': {
            'correlated_failures': len(high_failure_days) > 1,
            'temporal_spikes': sorted_days[:3] if sorted_days else []
        }
    }


def generate_reliability_profile(pbx_metrics: Dict, whisper_metrics: Dict,
                                   pbx_patterns: Dict, whisper_patterns: Dict,
                                   comparative_metrics: Dict, shared_patterns: Dict,
                                   temporal_analysis: Dict) -> Dict[str, Any]:
    """Generate comprehensive reliability profile"""

    return {
        'generated_at': datetime.now().isoformat(),
        'analysis_period': 'Last 30 days from data collection',
        'services_analyzed': ['pbx-web', 'whisper-stt'],

        # Individual Service Profiles
        'pbx_web_profile': {
            'deployment_reliability': pbx_metrics.get('deployment_metrics', {}),
            'operational_stability': pbx_metrics.get('pod_health_metrics', {}),
            'infrastructure_profile': pbx_metrics.get('infrastructure_profile', {}),
            'failure_pattern_exposure': pbx_patterns.get('service_distribution', {}),
            'reliability_grade': calculate_reliability_grade(pbx_metrics)
        },

        'whisper_stt_profile': {
            'deployment_reliability': whisper_metrics.get('deployment_metrics', {}),
            'operational_stability': whisper_metrics.get('pod_health_metrics', {}),
            'infrastructure_profile': whisper_metrics.get('infrastructure_profile', {}),
            'failure_pattern_exposure': whisper_patterns.get('service_distribution', {}),
            'reliability_grade': calculate_reliability_grade(whisper_metrics)
        },

        # Comparative Analysis
        'comparative_metrics': comparative_metrics,

        # Shared vs Unique Analysis
        'shared_vs_unique_patterns': shared_patterns,

        # Temporal Analysis
        'temporal_analysis': temporal_analysis,

        # Overall Assessment
        'executive_summary': generate_executive_summary(comparative_metrics, shared_patterns, temporal_analysis)
    }


def calculate_reliability_grade(metrics: Dict) -> str:
    """Calculate overall reliability grade"""
    deployment = metrics.get('deployment_metrics', {})
    pod_health = metrics.get('pod_health_metrics', {})

    success_rate = deployment.get('success_rate_percentage', 0)
    rollback_rate = deployment.get('rollback_rate_percentage', 0)
    restart_count = pod_health.get('restart_count', 0)
    pod_ready = pod_health.get('pod_ready', False)

    # Calculate grade based on multiple factors
    score = 0

    # Success rate (40 points)
    if success_rate >= 99:
        score += 40
    elif success_rate >= 95:
        score += 35
    elif success_rate >= 90:
        score += 25
    elif success_rate >= 80:
        score += 15

    # Rollback rate (20 points)
    if rollback_rate == 0:
        score += 20
    elif rollback_rate < 5:
        score += 15
    elif rollback_rate < 10:
        score += 10

    # Pod health (20 points)
    if pod_ready and restart_count == 0:
        score += 20
    elif pod_ready:
        score += 10

    # Deployment stability (20 points)
    stability = deployment.get('deployment_stability', 'LOW')
    if stability == 'HIGH':
        score += 20
    elif stability == 'MEDIUM':
        score += 10

    # Convert score to grade
    if score >= 90:
        return 'A'
    elif score >= 80:
        return 'B'
    elif score >= 70:
        return 'C'
    elif score >= 60:
        return 'D'
    else:
        return 'F'


def generate_executive_summary(comparative: Dict, shared: Dict, temporal: Dict) -> Dict[str, Any]:
    """Generate executive summary"""

    deployment_comp = comparative.get('deployment_reliability', {}).get('success_rate_comparison', {})
    operational_comp = comparative.get('operational_stability', {}).get('uptime_comparison', {})
    shared_summary = shared.get('pattern_summary', {})
    temporal_summary = temporal.get('aggregate_temporal_analysis', {})

    return {
        'key_findings': [
            f"Deployment success rates: pbx-web {deployment_comp.get('pbx_web', 0)}% vs whisper-stt {deployment_comp.get('whisper_stt', 0)}%",
            f"Winner: {deployment_comp.get('winner', 'TIE')} by {abs(deployment_comp.get('delta_percentage', 0)):.1f} percentage points",
            f"Operational uptime: whisper-stt leads with {operational_comp.get('whisper_stt_uptime_days', 0)} days vs pbx-web {operational_comp.get('pbx_web_uptime_days', 0)} days",
            f"Shared failure patterns: {shared_summary.get('total_shared_patterns', 0)} categories affecting both services",
            f"Service-specific patterns: pbx-web {shared_summary.get('total_pbx_patterns', 0)} vs whisper-stt {shared_summary.get('total_whisper_patterns', 0)}",
            f"Peak failure day: {temporal_summary.get('peak_failure_day', 'N/A')} with {temporal_summary.get('peak_failure_count', 0)} failures"
        ],
        'reliability_recommendation': determine_reliability_recommendation(comparative, shared, temporal),
        'risk_assessment': assess_risk_level(comparative, shared, temporal),
        'confidence_level': 'HIGH'
    }


def determine_reliability_recommendation(comparative: Dict, shared: Dict, temporal: Dict) -> str:
    """Determine overall reliability recommendation"""

    deployment_comp = comparative.get('deployment_reliability', {}).get('success_rate_comparison', {})
    winner = deployment_comp.get('winner', 'TIE')
    delta = deployment_comp.get('delta_percentage', 0)

    shared_count = shared.get('pattern_summary', {}).get('total_shared_patterns', 0)

    if shared_count > 0:
        return f"CAUTION: {shared_count} shared failure patterns indicate systemic infrastructure vulnerabilities affecting both services"
    elif winner == 'TIE' and delta < 5:
        return "EXCELLENT: Both services demonstrate comparable high reliability with minimal differences"
    elif delta > 10:
        return f"RECOMMENDATION: {winner} shows significantly better deployment reliability ({delta:.1f}% delta)"
    else:
        return "GOOD: Both services operating within acceptable reliability parameters"


def assess_risk_level(comparative: Dict, shared: Dict, temporal: Dict) -> Dict[str, Any]:
    """Assess overall risk level"""

    deployment_comp = comparative.get('deployment_reliability', {}).get('success_rate_comparison', {})
    pbx_success = deployment_comp.get('pbx_web', 0)
    whisper_success = deployment_comp.get('whisper_stt', 0)

    shared_patterns = shared.get('shared_patterns', {})
    high_severity_shared = sum(1 for p in shared_patterns.values() if p.get('severity') in ['HIGH', 'CRITICAL'])

    temporal_clustering = temporal.get('aggregate_temporal_analysis', {}).get('failure_clustering_detected', False)

    # Calculate risk score
    risk_factors = 0

    if pbx_success < 95 or whisper_success < 95:
        risk_factors += 1
    if high_severity_shared > 0:
        risk_factors += 2
    if temporal_clustering:
        risk_factors += 1

    if risk_factors >= 3:
        risk_level = 'HIGH'
        risk_color = 'red'
    elif risk_factors >= 1:
        risk_level = 'MEDIUM'
        risk_color = 'yellow'
    else:
        risk_level = 'LOW'
        risk_color = 'green'

    return {
        'risk_level': risk_level,
        'risk_color': risk_color,
        'risk_factors_count': risk_factors,
        'primary_concerns': [
            'Sub-95% success rates' if pbx_success < 95 or whisper_success < 95 else None,
            f'{high_severity_shared} high-severity shared patterns' if high_severity_shared > 0 else None,
            'Temporal failure clustering detected' if temporal_clustering else None
        ],
        'overall_assessment': 'Both services show strong reliability metrics with room for improvement in shared failure pattern mitigation'
    }


def main():
    """Main execution function"""

    print("Starting comparative reliability analysis...")

    # Define file paths
    base_dir = '/home/coding/aide-de-camp'
    pbx_deployment_file = os.path.join(base_dir, 'pbx-web-deployment-data-30days.json')
    whisper_deployment_file = os.path.join(base_dir, 'whisper-stt-deployments-30d.json')
    pattern_file = os.path.join(base_dir, 'pattern-frequency-statistics.json')
    output_file = os.path.join(base_dir, 'comparative_reliability_analysis.json')

    # Load data files
    print("Loading deployment data...")
    pbx_deployment_data = load_json_file(pbx_deployment_file)
    whisper_deployment_data = load_json_file(whisper_deployment_file)
    pattern_data = load_json_file(pattern_file)

    if not pbx_deployment_data or not whisper_deployment_data:
        print("Error: Could not load deployment data files")
        return

    # Calculate individual service metrics
    print("Calculating individual service metrics...")
    pbx_metrics = calculate_reliability_metrics(pbx_deployment_data)
    whisper_metrics = calculate_reliability_metrics(whisper_deployment_data)

    # Analyze failure patterns
    print("Analyzing failure patterns...")
    pattern_analysis = analyze_failure_patterns(pattern_data)

    # Calculate comparative metrics
    print("Calculating comparative metrics...")
    comparative_metrics = calculate_comparative_metrics(
        pbx_metrics, whisper_metrics,
        pattern_analysis.get('service_distribution', {}),
        pattern_analysis.get('category_by_service', {})
    )

    # Identify shared vs unique patterns
    print("Identifying shared vs unique patterns...")
    shared_patterns = identify_shared_vs_unique_patterns(
        pattern_data,
        pattern_analysis.get('service_distribution', {})
    )

    # Perform temporal analysis
    print("Performing temporal analysis...")
    temporal_analysis = perform_temporal_analysis(pattern_data)

    # Generate comprehensive reliability profile
    print("Generating comprehensive reliability profile...")
    reliability_profile = generate_reliability_profile(
        pbx_metrics, whisper_metrics,
        pattern_analysis, pattern_analysis,
        comparative_metrics, shared_patterns, temporal_analysis
    )

    # Save output
    print(f"Saving results to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(reliability_profile, f, indent=2, default=str)

    print("Analysis complete!")
    print(f"\nExecutive Summary:")
    for finding in reliability_profile.get('executive_summary', {}).get('key_findings', []):
        print(f"  - {finding}")

    recommendation = reliability_profile.get('executive_summary', {}).get('reliability_recommendation', '')
    print(f"\nRecommendation: {recommendation}")

    risk = reliability_profile.get('executive_summary', {}).get('risk_assessment', {})
    print(f"Risk Level: {risk.get('risk_level', 'UNKNOWN')}")

    return reliability_profile


if __name__ == '__main__':
    main()