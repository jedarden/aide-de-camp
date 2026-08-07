#!/usr/bin/env python3
"""
Analyze deployment pattern statistics and metrics.
Calculates frequency, time distribution, and context for each failure pattern category.
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Any
import sys

def load_data():
    """Load deployment events and pattern analysis data."""
    with open('deployment-events-30days.json', 'r') as f:
        events_data = json.load(f)

    with open('deployment-patterns-analysis-report.json', 'r') as f:
        patterns_data = json.load(f)

    return events_data, patterns_data

def calculate_time_distribution(events: List[Dict]) -> Dict[str, Any]:
    """Calculate temporal distribution of deployment events."""
    if not events:
        return {"daily_distribution": {}, "hourly_distribution": {}, "day_of_week_distribution": {}}

    daily_counts = Counter()
    hourly_counts = Counter()
    day_of_week_counts = Counter()

    for event in events:
        timestamp_str = event.get('timestamp', '')
        if timestamp_str:
            try:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                date_key = dt.strftime('%Y-%m-%d')
                hour_key = dt.strftime('%H:00')
                day_key = dt.strftime('%A')

                daily_counts[date_key] += 1
                hourly_counts[hour_key] += 1
                day_of_week_counts[day_key] += 1
            except (ValueError, AttributeError):
                continue

    return {
        "daily_distribution": dict(sorted(daily_counts.items())),
        "hourly_distribution": dict(sorted(hourly_counts.items())),
        "day_of_week_distribution": dict(day_of_week_counts),
        "total_active_days": len(daily_counts),
        "peak_day": daily_counts.most_common(1)[0] if daily_counts else None,
        "peak_hour": hourly_counts.most_common(1)[0] if hourly_counts else None
    }

def analyze_rollback_pattern(events_data, patterns_data) -> Dict[str, Any]:
    """Analyze rollback pattern statistics."""
    rollback_events = []

    # Collect rollback events from both services
    for service_events in events_data.values():
        if isinstance(service_events, dict) and 'deployment_events' in service_events:
            for event in service_events['deployment_events']:
                if event.get('event_type') == 'deployment_rollback':
                    rollback_events.append(event)

    if not rollback_events:
        return {
            "pattern_type": "rollback",
            "occurrence_count": 0,
            "frequency": "0%",
            "time_distribution": {},
            "affected_services": [],
            "image_context": {},
            "notes": "No rollback events detected in 30-day period"
        }

    # Extract timing and context
    timestamps = []
    affected_services = set()
    image_versions = []

    for event in rollback_events:
        timestamps.append(event.get('timestamp', ''))
        affected_services.add(event.get('deployment', 'unknown'))
        image_versions.append(event.get('image', 'unknown'))

    time_dist = calculate_time_distribution(rollback_events)

    return {
        "pattern_type": "rollback",
        "occurrence_count": len(rollback_events),
        "frequency": f"{len(rollback_events)} events in 30 days",
        "time_distribution": {
            "timestamps": timestamps,
            "temporal_analysis": time_dist
        },
        "affected_services": list(affected_services),
        "image_context": {
            "images_involved": image_versions,
            "rollback_details": rollback_events
        },
        "severity": "LOW",
        "impact": "Service continuity maintained via automatic rollback"
    }

def analyze_rapid_deployment_pattern(events_data, patterns_data) -> Dict[str, Any]:
    """Analyze rapid deployment pattern statistics."""
    rapid_sequences = []

    # Extract rapid sequences from both services
    for service_name, service_data in patterns_data.items():
        if isinstance(service_data, dict) and 'rapid_patterns' in service_data:
            rapid_info = service_data['rapid_patterns']
            if 'rapid_sequences' in rapid_info:
                for seq in rapid_info['rapid_sequences']:
                    seq['service'] = service_name.replace('_analysis', '')
                    rapid_sequences.append(seq)

    if not rapid_sequences:
        return {
            "pattern_type": "rapid_deployment",
            "occurrence_count": 0,
            "frequency": "0%",
            "time_distribution": {},
            "affected_services": [],
            "image_context": {},
            "notes": "No rapid deployment sequences detected"
        }

    # Aggregate statistics
    total_deployments_in_sequences = sum(seq.get('deployment_count', 0) for seq in rapid_sequences)
    affected_services = set(seq.get('service', 'unknown') for seq in rapid_sequences)

    # Extract all events from rapid sequences
    all_rapid_events = []
    for seq in rapid_sequences:
        all_rapid_events.extend(seq.get('events', []))

    time_dist = calculate_time_distribution(all_rapid_events)

    # Image progression context
    image_progressions = []
    for seq in rapid_sequences:
        events = seq.get('events', [])
        if len(events) >= 2:
            progression = [e.get('image', 'unknown') for e in events]
            image_progressions.append({
                "service": seq.get('service', 'unknown'),
                "sequence": progression,
                "start_time": seq.get('start_time', ''),
                "duration_seconds": seq.get('duration_seconds', 0)
            })

    return {
        "pattern_type": "rapid_deployment",
        "occurrence_count": len(rapid_sequences),
        "frequency": f"{len(rapid_sequences)} rapid sequences involving {total_deployments_in_sequences} deployments",
        "time_distribution": {
            "sequences_detected": len(rapid_sequences),
            "temporal_analysis": time_dist,
            "total_deployments_in_rapid_sequences": total_deployments_in_sequences
        },
        "affected_services": list(affected_services),
        "image_context": {
            "rapid_image_progressions": image_progressions,
            "average_duration_seconds": sum(s.get('duration_seconds', 0) for s in rapid_sequences) / len(rapid_sequences)
        },
        "severity": "MEDIUM",
        "impact": "Rapid iterations may increase risk if not properly tested",
        "recommendations": [
            "Consider spreading rapid deployments to reduce risk",
            "Implement automated testing between rapid iterations"
        ]
    }

def analyze_version_revert_pattern(events_data, patterns_data) -> Dict[str, Any]:
    """Analyze version revert pattern statistics."""
    all_reverts = []

    for service_name, service_data in patterns_data.items():
        if isinstance(service_data, dict) and 'image_progression' in service_data:
            progression = service_data['image_progression']
            if 'version_reverts' in progression:
                for revert in progression['version_reverts']:
                    revert['service'] = service_name.replace('_analysis', '')
                    all_reverts.append(revert)

    if not all_reverts:
        return {
            "pattern_type": "version_revert",
            "occurrence_count": 0,
            "frequency": "0%",
            "time_distribution": {},
            "affected_services": [],
            "image_context": {},
            "notes": "No version reverts detected in 30-day period"
        }

    affected_services = set(revert.get('service', 'unknown') for revert in all_reverts)

    # Time distribution
    timestamps = [revert.get('timestamp', '') for revert in all_reverts]
    revert_events = [{'timestamp': ts} for ts in timestamps if ts]
    time_dist = calculate_time_distribution(revert_events)

    return {
        "pattern_type": "version_revert",
        "occurrence_count": len(all_reverts),
        "frequency": f"{len(all_reverts)} version reverts in 30 days",
        "time_distribution": {
            "timestamps": timestamps,
            "temporal_analysis": time_dist
        },
        "affected_services": list(affected_services),
        "image_context": {
            "revert_details": all_reverts,
            "from_images": [r.get('from', 'unknown') for r in all_reverts],
            "to_images": [r.get('to', 'unknown') for r in all_reverts]
        },
        "severity": "LOW",
        "impact": "Reverting to previous version indicates instability or issues with newer version"
    }

def analyze_infrastructure_deployment_pattern(events_data, patterns_data) -> Dict[str, Any]:
    """Analyze infrastructure/support deployment pattern."""
    infra_events = []

    for service_events in events_data.values():
        if isinstance(service_events, dict) and 'deployment_events' in service_events:
            for event in service_events['deployment_events']:
                deployment_name = event.get('deployment', '')
                # Infrastructure patterns based on deployment name
                if any(keyword in deployment_name.lower() for keyword in ['relay', 'infra', 'support', 'build']):
                    infra_events.append(event)

    if not infra_events:
        return {
            "pattern_type": "infrastructure_deployment",
            "occurrence_count": 0,
            "frequency": "0%",
            "time_distribution": {},
            "affected_services": [],
            "image_context": {},
            "notes": "No infrastructure-specific deployments detected"
        }

    affected_services = set(event.get('deployment', 'unknown') for event in infra_events)
    images = [event.get('image', 'unknown') for event in infra_events]

    time_dist = calculate_time_distribution(infra_events)

    return {
        "pattern_type": "infrastructure_deployment",
        "occurrence_count": len(infra_events),
        "frequency": f"{len(infra_events)} infrastructure deployments in 30 days",
        "time_distribution": {
            "temporal_analysis": time_dist
        },
        "affected_services": list(affected_services),
        "image_context": {
            "images_used": images,
            "deployment_types": list(set(event.get('notes', '') for event in infra_events))
        },
        "severity": "INFO",
        "impact": "Infrastructure deployments support main service operations"
    }

def analyze_deployment_failure_correlations(events_data, patterns_data) -> Dict[str, Any]:
    """Identify correlations between deployment timestamps and failure spikes."""

    correlations = []

    # Check for deployment clustering around failure events
    for service_name, service_data in patterns_data.items():
        if not isinstance(service_data, dict) or 'failure_modes' not in service_data:
            continue

        failures = service_data['failure_modes'].get('failure_details', [])

        if not failures:
            continue

        service = service_name.replace('_analysis', '')

        for failure in failures:
            failure_time = failure.get('timestamp', '')
            if not failure_time:
                continue

            # Look for deployments within 1 hour before the failure
            try:
                failure_dt = datetime.fromisoformat(failure_time.replace('Z', '+00:00'))

                nearby_deployments = []
                if service in events_data:
                    for event in events_data[service].get('deployment_events', []):
                        event_time_str = event.get('timestamp', '')
                        if event_time_str:
                            try:
                                event_dt = datetime.fromisoformat(event_time_str.replace('Z', '+00:00'))
                                time_diff = (failure_dt - event_dt).total_seconds()

                                if -3600 <= time_diff <= 3600:  # Within 1 hour
                                    nearby_deployments.append({
                                        "deployment": event.get('deployment', ''),
                                        "image": event.get('image', ''),
                                        "time_difference_seconds": time_diff,
                                        "timestamp": event_time_str
                                    })
                            except ValueError:
                                continue

                if nearby_deployments:
                    correlations.append({
                        "service": service,
                        "failure_event": failure,
                        "related_deployments": nearby_deployments,
                        "correlation_type": "temporal_proximity"
                    })
            except ValueError:
                continue

    return {
        "correlation_type": "deployment_failure_temporal",
        "correlations_found": len(correlations),
        "details": correlations,
        "interpretation": "Deployments occurring near failure events may indicate deployment-related issues"
    }

def generate_summary_statistics(pattern_analyses: List[Dict]) -> Dict[str, Any]:
    """Generate summary statistics across all pattern types."""

    total_patterns = len([p for p in pattern_analyses if p.get('occurrence_count', 0) > 0])
    total_events = sum(p.get('occurrence_count', 0) for p in pattern_analyses)

    affected_services = set()
    for p in pattern_analyses:
        affected_services.update(p.get('affected_services', []))

    severity_counts = Counter(p.get('severity', 'UNKNOWN') for p in pattern_analyses if p.get('occurrence_count', 0) > 0)

    return {
        "total_pattern_types_detected": total_patterns,
        "total_pattern_events": total_events,
        "services_affected": list(affected_services),
        "severity_distribution": dict(severity_counts),
        "pattern_categories": [
            p.get('pattern_type', 'unknown') for p in pattern_analyses
            if p.get('occurrence_count', 0) > 0
        ],
        "overall_assessment": "LOW_RISK" if severity_counts.get('LOW', 0) + severity_counts.get('INFO', 0) >= severity_counts.get('MEDIUM', 0) else "MEDIUM_RISK"
    }

def main():
    """Main analysis function."""
    print("Loading deployment data...")
    events_data, patterns_data = load_data()

    print("Analyzing pattern statistics...")

    # Analyze each pattern type
    rollback_analysis = analyze_rollback_pattern(events_data, patterns_data)
    rapid_deployment_analysis = analyze_rapid_deployment_pattern(events_data, patterns_data)
    version_revert_analysis = analyze_version_revert_pattern(events_data, patterns_data)
    infrastructure_analysis = analyze_infrastructure_deployment_pattern(events_data, patterns_data)

    # Analyze correlations
    correlations = analyze_deployment_failure_correlations(events_data, patterns_data)

    # Generate summary
    pattern_analyses = [
        rollback_analysis,
        rapid_deployment_analysis,
        version_revert_analysis,
        infrastructure_analysis
    ]

    summary_statistics = generate_summary_statistics(pattern_analyses)

    # Build final report
    report = {
        "metadata": {
            "analysis_type": "pattern_statistics_and_metrics",
            "generated_at": datetime.now().isoformat(),
            "time_period": "2026-07-07 to 2026-08-06 (30 days)",
            "data_sources": [
                "deployment-events-30days.json",
                "deployment-patterns-analysis-report.json"
            ]
        },
        "pattern_analyses": {
            "rollback_pattern": rollback_analysis,
            "rapid_deployment_pattern": rapid_deployment_analysis,
            "version_revert_pattern": version_revert_analysis,
            "infrastructure_deployment_pattern": infrastructure_analysis
        },
        "deployment_failure_correlations": correlations,
        "summary_statistics": summary_statistics,
        "key_findings": [
            f"Total pattern types detected: {summary_statistics['total_pattern_types_detected']}",
            f"Services affected by patterns: {', '.join(summary_statistics['services_affected'])}",
            f"Overall risk assessment: {summary_statistics['overall_assessment']}",
            f"Rapid deployment sequences: {rapid_deployment_analysis['occurrence_count']} detected",
            f"Rollback events: {rollback_analysis['occurrence_count']} detected",
            f"Version reverts: {version_revert_analysis['occurrence_count']} detected"
        ]
    }

    # Save to file
    output_path = '/home/coding/aide-de-camp/docs/research/deployment-data/pattern-statistics.json'
    print(f"Saving results to {output_path}...")

    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    print("✓ Pattern statistics analysis complete")
    print(f"✓ Results saved to {output_path}")

    # Print summary
    print("\n=== SUMMARY ===")
    for finding in report['key_findings']:
        print(f"  • {finding}")

if __name__ == '__main__':
    main()
