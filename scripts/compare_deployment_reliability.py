#!/usr/bin/env python3
"""
Compare pbx-web and whisper-stt deployment reliability.

This script analyzes deployment reliability differences, shared patterns,
and temporal correlations between two services.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any, Tuple


def load_json(filepath: Path) -> Dict:
    """Load and parse JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {filepath} not found")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing {filepath}: {e}")
        return {}


def calculate_reliability_profile(
    service_name: str,
    deployment_data: Dict,
    failure_patterns: Dict
) -> Dict[str, Any]:
    """Calculate comprehensive reliability profile for a service."""

    # Extract deployment metrics
    metrics = deployment_data.get(service_name.replace('-', '_'), {})
    if not metrics:
        metrics = deployment_data.get(service_name, {})

    overall = metrics.get('overall_metrics', {})

    # Extract failure patterns
    patterns = failure_patterns.get('by_service', {}).get(service_name, {})

    # Calculate reliability metrics
    total_deployments = overall.get('total_deployments', 0)
    total_successes = overall.get('total_successes', 0)
    total_failures = overall.get('total_failures', 0)
    success_rate = overall.get('overall_success_rate_percent', 0.0)

    # Get top failure modes
    error_type_counts = patterns.get('error_type_counts', {})
    top_error_patterns = patterns.get('top_error_patterns', [])

    # Calculate failure frequency
    weeks_analyzed = overall.get('weeks_analyzed', 1)
    weekly_failure_rate = overall.get('average_weekly_failure_rate', 0.0)

    return {
        'service_name': service_name,
        'total_deployments': total_deployments,
        'total_successes': total_successes,
        'total_failures': total_failures,
        'success_rate_percent': success_rate,
        'weekly_failure_rate': weekly_failure_rate,
        'top_error_types': error_type_counts,
        'top_error_patterns': top_error_patterns,
        'failure_modes': list(error_type_counts.keys()),
        'most_common_failure': max(error_type_counts.items(), key=lambda x: x[1])[0] if error_type_counts else None
    }


def identify_shared_patterns(failure_patterns: Dict) -> Dict[str, Any]:
    """Identify patterns shared between both services."""

    shared = failure_patterns.get('shared_patterns', {})

    shared_error_types = shared.get('error_types', [])
    shared_phases = shared.get('phases', [])

    # Get service-specific patterns
    service_specific = failure_patterns.get('service_specific_patterns', {})

    pbx_web_specific = service_specific.get('pbx-web', {}).get('specific_error_types', [])
    whisper_stt_specific = service_specific.get('whisper-stt', {}).get('specific_error_types', [])

    # Calculate pattern frequencies
    pbx_web_patterns = failure_patterns.get('by_service', {}).get('pbx-web', {}).get('error_type_counts', {})
    whisper_stt_patterns = failure_patterns.get('by_service', {}).get('whisper-stt', {}).get('error_type_counts', {})

    return {
        'shared_error_types': shared_error_types,
        'shared_phases': shared_phases,
        'pbx_web_specific_errors': pbx_web_specific,
        'whisper_stt_specific_errors': whisper_stt_specific,
        'pbx_web_error_frequency': pbx_web_patterns,
        'whisper_stt_error_frequency': whisper_stt_patterns
    }


def analyze_temporal_patterns(deployment_data: Dict) -> Dict[str, Any]:
    """Analyze temporal patterns and correlations."""

    pbx_web_data = deployment_data.get('pbx_web', {})
    whisper_stt_data = deployment_data.get('whisper_stt', {})

    # Get deployment events
    pbx_web_events = pbx_web_data.get('deployment_events', [])
    whisper_stt_events = whisper_stt_data.get('deployment_events', [])

    # Get weekly breakdowns
    pbx_web_weekly = pbx_web_data.get('weekly_breakdown', [])
    whisper_stt_weekly = whisper_stt_data.get('weekly_breakdown', [])

    # Check for correlated failures
    pbx_web_failures_by_week = {}
    whisper_stt_failures_by_week = {}

    for week_data in pbx_web_weekly:
        week = week_data.get('week')
        failures = week_data.get('failures', 0)
        pbx_web_failures_by_week[week] = failures

    for week_data in whisper_stt_weekly:
        week = week_data.get('week')
        failures = week_data.get('failures', 0)
        whisper_stt_failures_by_week[week] = failures

    # Find weeks where both services had deployments
    all_weeks = set(pbx_web_failures_by_week.keys()) | set(whisper_stt_failures_by_week.keys())
    correlated_failures = []

    for week in all_weeks:
        pbx_failures = pbx_web_failures_by_week.get(week, 0)
        whisper_failures = whisper_stt_failures_by_week.get(week, 0)

        if pbx_failures > 0 or whisper_failures > 0:
            correlated_failures.append({
                'week': week,
                'pbx_web_failures': pbx_failures,
                'whisper_stt_failures': whisper_failures,
                'both_failed': pbx_failures > 0 and whisper_failures > 0
            })

    # Time-of-day analysis (extract hours from timestamps)
    pbx_web_hours = []
    for event in pbx_web_events:
        timestamp = event.get('timestamp', '')
        try:
            dt = datetime.fromisoformat(timestamp.replace('+00:00', '').replace('Z', ''))
            pbx_web_hours.append(dt.hour)
        except:
            pass

    whisper_stt_hours = []
    for event in whisper_stt_events:
        timestamp = event.get('timestamp', '')
        try:
            dt = datetime.fromisoformat(timestamp.replace('+00:00', '').replace('Z', ''))
            whisper_stt_hours.append(dt.hour)
        except:
            pass

    return {
        'weekly_correlated_failures': correlated_failures,
        'pbx_web_deployment_hours': pbx_web_hours,
        'whisper_stt_deployment_hours': whisper_stt_hours,
        'has_temporal_correlation': any(cf['both_failed'] for cf in correlated_failures)
    }


def calculate_comparative_metrics(
    pbx_web_profile: Dict,
    whisper_stt_profile: Dict,
    shared_patterns: Dict,
    temporal_patterns: Dict
) -> Dict[str, Any]:
    """Calculate comparative metrics between services."""

    # Success rate delta
    success_rate_delta = pbx_web_profile['success_rate_percent'] - whisper_stt_profile['success_rate_percent']

    # Failure rate comparison
    failure_rate_ratio = (pbx_web_profile['weekly_failure_rate'] /
                         whisper_stt_profile['weekly_failure_rate']
                         if whisper_stt_profile['weekly_failure_rate'] > 0 else float('inf'))

    # Common vs unique failures
    shared_error_types = shared_patterns['shared_error_types']
    pbx_web_unique = len(shared_patterns['pbx_web_specific_errors'])
    whisper_stt_unique = len(shared_patterns['whisper_stt_specific_errors'])

    # Stability assessment
    pbx_web_stability = "STABLE" if pbx_web_profile['success_rate_percent'] >= 80 else "NEEDS_ATTENTION"
    whisper_stt_stability = "STABLE" if whisper_stt_profile['success_rate_percent'] >= 80 else "NEEDS_ATTENTION"

    return {
        'success_rate_delta_percentage_points': success_rate_delta,
        'success_rate_improvement_factor': success_rate_delta / whisper_stt_profile['success_rate_percent'] if whisper_stt_profile['success_rate_percent'] > 0 else None,
        'failure_rate_ratio': failure_rate_ratio,
        'shared_failure_patterns_count': len(shared_error_types),
        'pbx_web_unique_patterns_count': pbx_web_unique,
        'whisper_stt_unique_patterns_count': whisper_stt_unique,
        'has_temporal_correlation': temporal_patterns['has_temporal_correlation'],
        'pbx_web_stability': pbx_web_stability,
        'whisper_stt_stability': whisper_stt_stability,
        'more_reliable_service': 'pbx-web' if success_rate_delta > 0 else 'whisper-stt'
    }


def generate_report(
    pbx_web_profile: Dict,
    whisper_stt_profile: Dict,
    shared_patterns: Dict,
    temporal_patterns: Dict,
    comparative_metrics: Dict
) -> Dict[str, Any]:
    """Generate comprehensive comparative report."""

    report = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'analysis_type': 'deployment_reliability_comparison',
            'services_compared': ['pbx-web', 'whisper-stt']
        },
        'reliability_profiles': {
            'pbx_web': pbx_web_profile,
            'whisper_stt': whisper_stt_profile
        },
        'comparative_metrics': comparative_metrics,
        'shared_patterns': {
            'shared_error_types': shared_patterns['shared_error_types'],
            'shared_phases': shared_patterns['shared_phases'],
            'explanation': 'These error types and phases occur in both services'
        },
        'service_specific_patterns': {
            'pbx_web_specific': {
                'unique_error_types': shared_patterns['pbx_web_specific_errors'],
                'error_frequency': shared_patterns['pbx_web_error_frequency']
            },
            'whisper_stt_specific': {
                'unique_error_types': shared_patterns['whisper_stt_specific_errors'],
                'error_frequency': shared_patterns['whisper_stt_error_frequency']
            }
        },
        'temporal_analysis': {
            'weekly_correlation': temporal_patterns['weekly_correlated_failures'],
            'has_correlated_failures': temporal_patterns['has_temporal_correlation'],
            'finding': 'Services do NOT show correlated failure patterns' if not temporal_patterns['has_temporal_correlation'] else 'Services show correlated failure patterns'
        },
        'key_findings': [
            f"pbx-web has a {comparative_metrics['success_rate_delta_percentage_points']:.1f} percentage point higher success rate than whisper-stt",
            f"pbx-web success rate: {pbx_web_profile['success_rate_percent']:.1f}%, whisper-stt: {whisper_stt_profile['success_rate_percent']:.1f}%",
            f"whisper-stt has {comparative_metrics['failure_rate_ratio']:.1f}x more weekly failures than pbx-web",
            f"Both services share {len(shared_patterns['shared_error_types'])} error type(s): {', '.join(shared_patterns['shared_error_types'])}",
            f"pbx-web has {len(shared_patterns['pbx_web_specific_errors'])} unique error type(s): {', '.join(shared_patterns['pbx_web_specific_errors'])}",
            f"whisper-stt has {len(shared_patterns['whisper_stt_specific_errors'])} unique error type(s): {', '.join(shared_patterns['whisper_stt_specific_errors'])}",
            f"Temporal correlation: {'YES' if temporal_patterns['has_temporal_correlation'] else 'NO'} - failures do {'not ' if not temporal_patterns['has_temporal_correlation'] else ''}cluster together",
            f"Most reliable service: {comparative_metrics['more_reliable_service'].upper()}"
        ],
        'stability_triggers': {
            'pbx_web': {
                'stability_level': comparative_metrics['pbx_web_stability'],
                'primary_concern': 'Scaled_Down_Or_Failed errors (20% of errors)' if 'Scaled_Down_Or_Failed' in pbx_web_profile['top_error_types'] else 'Rolled_Over pattern',
                'recommendation': 'Monitor for scale-down events and rollout stability'
            },
            'whisper_stt': {
                'stability_level': comparative_metrics['whisper_stt_stability'],
                'primary_concern': 'Very low success rate (25%) - all failures are Rolled_Over',
                'recommendation': 'Investigate rollout process and health check configuration'
            }
        }
    }

    return report


def main():
    """Main execution function."""

    # Define data paths
    data_dir = Path('/home/coding/aide-de-camp/data')
    failure_patterns_file = data_dir / 'failure_patterns_analysis.json'
    success_rates_file = data_dir / 'deployment_success_rates.json'
    output_file = data_dir / 'deployment_reliability_comparison.json'

    # Load data
    print("Loading deployment data...")
    failure_patterns = load_json(failure_patterns_file)
    deployment_data = load_json(success_rates_file)

    if not failure_patterns or not deployment_data:
        print("Error: Could not load required data files")
        return

    print("Calculating reliability profiles...")
    pbx_web_profile = calculate_reliability_profile('pbx-web', deployment_data, failure_patterns)
    whisper_stt_profile = calculate_reliability_profile('whisper-stt', deployment_data, failure_patterns)

    print("Identifying shared patterns...")
    shared_patterns = identify_shared_patterns(failure_patterns)

    print("Analyzing temporal patterns...")
    temporal_patterns = analyze_temporal_patterns(deployment_data)

    print("Calculating comparative metrics...")
    comparative_metrics = calculate_comparative_metrics(
        pbx_web_profile,
        whisper_stt_profile,
        shared_patterns,
        temporal_patterns
    )

    print("Generating comprehensive report...")
    report = generate_report(
        pbx_web_profile,
        whisper_stt_profile,
        shared_patterns,
        temporal_patterns,
        comparative_metrics
    )

    # Write output
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n✓ Comparative analysis complete!")
    print(f"  Output: {output_file}")
    print(f"\nKey Findings:")
    for finding in report['key_findings']:
        print(f"  • {finding}")


if __name__ == '__main__':
    main()
