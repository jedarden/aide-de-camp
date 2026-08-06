#!/usr/bin/env python3
"""
Cross-service deployment correlation analysis for pbx-web and whisper-stt.
Analyzes temporal correlations between deployment events over a 30-day window.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
import statistics

# Define correlation windows (in minutes)
CORRELATION_WINDOWS = [5, 10, 15, 30, 60]

def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp."""
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))

def format_timedelta(td: timedelta) -> str:
    """Format timedelta for human reading."""
    total_seconds = abs(td.total_seconds())
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def load_pbx_events(data_file: Path) -> List[Dict[str, Any]]:
    """Load pbx-web deployment events."""
    with open(data_file) as f:
        data = json.load(f)

    events = []
    for event in data.get('deployment_events_last_30_days', []):
        events.append({
            'timestamp': parse_timestamp(event['timestamp']),
            'service': 'pbx-web',
            'event_type': event['event_type'],
            'revision': event.get('revision'),
            'outcome': event['outcome'],
            'details': event.get('notes', '')
        })

    return sorted(events, key=lambda x: x['timestamp'])

def load_whisper_events(data_file: Path) -> List[Dict[str, Any]]:
    """Load whisper-stt deployment events."""
    with open(data_file) as f:
        data = json.load(f)

    events = []
    for rs in data.get('deployment_history_30_days', {}).get('replicasets', []):
        # Skip inactive replicasets beyond the 30-day window
        if rs.get('status') == 'inactive' and 'created' in rs:
            ts = parse_timestamp(rs['created'])
            events.append({
                'timestamp': ts,
                'service': 'whisper-stt',
                'event_type': 'replica_created',
                'revision': rs.get('revision'),
                'outcome': rs.get('status'),
                'details': f"image: {rs.get('image', 'unknown')}"
            })

    return sorted(events, key=lambda x: x['timestamp'])

def find_correlations(pbx_events: List[Dict], whisper_events: List[Dict],
                     window_minutes: int) -> List[Dict[str, Any]]:
    """Find deployment event pairs within correlation window."""
    correlations = []
    window = timedelta(minutes=window_minutes)

    for pbx in pbx_events:
        for whisper in whisper_events:
            time_diff = whisper['timestamp'] - pbx['timestamp']

            if abs(time_diff) <= window:
                correlations.append({
                    'window_minutes': window_minutes,
                    'pbx_event': pbx,
                    'whisper_event': whisper,
                    'time_delta': time_diff,
                    'whisper_precedes_pbx': time_diff.total_seconds() < 0,
                    'absolute_delta': abs(time_diff)
                })

    return sorted(correlations, key=lambda x: x['absolute_delta'])

def calculate_lag_times(correlations: List[Dict]) -> Dict[str, Any]:
    """Calculate statistical lag time metrics."""
    if not correlations:
        return {'count': 0, 'mean_lag_minutes': None, 'median_lag_minutes': None}

    lags = [c['time_delta'].total_seconds() / 60 for c in correlations]
    abs_lags = [abs(lag) for lag in lags]

    return {
        'count': len(lags),
        'mean_lag_minutes': statistics.mean(abs_lags),
        'median_lag_minutes': statistics.median(abs_lags),
        'min_lag_minutes': min(abs_lags),
        'max_lag_minutes': max(abs_lags),
        'whisper_precedes_count': sum(1 for lag in lags if lag < 0),
        'pbx_precedes_count': sum(1 for lag in lags if lag > 0)
    }

def generate_timeline(pbx_events: List[Dict], whisper_events: List[Dict]) -> List[Dict]:
    """Generate unified timeline of all deployment events."""
    all_events = []

    for event in pbx_events:
        all_events.append({**event, 'source': 'pbx-web'})

    for event in whisper_events:
        all_events.append({**event, 'source': 'whisper-stt'})

    return sorted(all_events, key=lambda x: x['timestamp'])

def analyze():
    """Main analysis function."""
    base_path = Path('docs/research/deployment-data')

    print("🔍 Loading deployment data...")
    pbx_events = load_pbx_events(base_path / 'pbx-web-deployment-data-30days.json')
    whisper_events = load_whisper_events(base_path / 'whisper-stt-deployment-data-30days.json')

    print(f"📊 pbx-web events: {len(pbx_events)}")
    print(f"📊 whisper-stt events: {len(whisper_events)}")

    # Generate unified timeline
    print("\n📅 UNIFIED TIMELINE (30 days)")
    print("=" * 80)
    timeline = generate_timeline(pbx_events, whisper_events)

    for i, event in enumerate(timeline):
        ts_str = event['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        source = event['source']
        event_type = event['event_type']
        outcome = event['outcome']
        details = event.get('details', '')

        print(f"{ts_str} | {source:15} | {event_type:20} | {outcome:12} | {details}")

    # Check for coincident deployment windows
    print(f"\n🔗 COINCIDENCE ANALYSIS (deployment events within N minutes)")
    print("=" * 80)

    all_correlations = []
    for window in CORRELATION_WINDOWS:
        correlations = find_correlations(pbx_events, whisper_events, window)
        lag_stats = calculate_lag_times(correlations)

        print(f"\nWindow: ±{window} minutes")
        print(f"  Correlated events: {lag_stats['count']}")

        if lag_stats['count'] > 0:
            print(f"  Mean lag: {lag_stats['mean_lag_minutes']:.1f} minutes")
            print(f"  Median lag: {lag_stats['median_lag_minutes']:.1f} minutes")
            print(f"  Range: {lag_stats['min_lag_minutes']:.1f} - {lag_stats['max_lag_minutes']:.1f} minutes")
            print(f"  whisper-stt precedes pbx-web: {lag_stats['whisper_precedes_count']}")
            print(f"  pbx-web precedes whisper-stt: {lag_stats['pbx_precedes_count']}")

            # Show closest correlations
            print(f"\n  Closest correlations:")
            for corr in correlations[:3]:
                delta = corr['time_delta'].total_seconds() / 60
                direction = "whisper→pbx" if delta > 0 else "pbx→whisper"
                print(f"    {corr['pbx_event']['timestamp'].strftime('%Y-%m-%d %H:%M')} → "
                      f"{corr['whisper_event']['timestamp'].strftime('%Y-%m-%d %H:%M')} "
                      f"({abs(delta):.1f}m, {direction})")

        all_correlations.extend(correlations)

    # Check if failures/issues correlate
    print(f"\n⚠️  FAILURE/ISSUE CORRELATION CHECK")
    print("=" * 80)

    pbx_issues = [e for e in pbx_events if e['outcome'] in ['rolled_back', 'failed', 'error']]
    whisper_issues = [e for e in whisper_events if e['outcome'] in ['failed', 'error', 'crash']]

    print(f"pbx-web issues: {len(pbx_issues)}")
    for issue in pbx_issues:
        print(f"  - {issue['timestamp'].strftime('%Y-%m-%d %H:%M')} | {issue['event_type']} | {issue['outcome']}")

    print(f"whisper-stt issues: {len(whisper_issues)}")
    for issue in whisper_issues:
        print(f"  - {issue['timestamp'].strftime('%Y-%m-%d %H:%M')} | {issue['event_type']} | {issue['outcome']}")

    # Check temporal clustering
    print(f"\n📊 TEMPORAL CLUSTERING ANALYSIS")
    print("=" * 80)

    if len(timeline) >= 2:
        intervals = []
        for i in range(1, len(timeline)):
            interval = (timeline[i]['timestamp'] - timeline[i-1]['timestamp']).total_seconds() / 3600  # hours
            intervals.append(interval)

        print(f"Mean interval between events: {statistics.mean(intervals):.1f} hours")
        print(f"Median interval: {statistics.median(intervals):.1f} hours")
        print(f"Min interval: {min(intervals):.1f} hours")
        print(f"Max interval: {max(intervals):.1f} hours")

        # Find clustered events (within 1 hour)
        clustered_events = []
        for i in range(1, len(timeline)):
            interval_hours = (timeline[i]['timestamp'] - timeline[i-1]['timestamp']).total_seconds() / 3600
            if interval_hours <= 1:
                clustered_events.append((timeline[i-1], timeline[i], interval_hours))

        print(f"\nEvents within 1 hour of each other: {len(clustered_events)}")
        for event1, event2, interval in clustered_events:
            print(f"  {event1['timestamp'].strftime('%Y-%m-%d %H:%M')} ({event1['source']}) → "
                  f"{event2['timestamp'].strftime('%Y-%m-%d %H:%M')} ({event2['source']}) "
                  f"({interval*60:.0f} minutes)")

    # Generate findings
    print(f"\n📋 FINDINGS SUMMARY")
    print("=" * 80)

    findings = {
        'analysis_date': datetime.now().isoformat(),
        'total_pbx_events': len(pbx_events),
        'total_whisper_events': len(whisper_events),
        'total_events': len(timeline),
        'pbx_issues': len(pbx_issues),
        'whisper_issues': len(whisper_issues),
        'correlations_found': len(all_correlations),
        'correlation_windows_analyzed': CORRELATION_WINDOWS,
        'key_findings': []
    }

    # Determine correlation level
    if len(all_correlations) == 0:
        correlation_level = "NO CORRELATION"
        findings['key_findings'].append(
            "No temporal correlation detected between pbx-web and whisper-stt deployments."
        )
    elif len(all_correlations) <= 2:
        correlation_level = "WEAK CORRELATION"
        findings['key_findings'].append(
            f"Weak correlation: {len(all_correlations)} coincident deployment windows found."
        )
    else:
        correlation_level = "MODERATE CORRELATION"
        findings['key_findings'].append(
            f"Moderate correlation: {len(all_correlations)} coincident deployment windows found."
        )

    print(f"Correlation Level: {correlation_level}")

    # Check temporal pattern
    if pbx_issues and whisper_issues:
        # Check if whisper issues precede pbx issues
        for whisper_issue in whisper_issues:
            for pbx_issue in pbx_issues:
                lag = (pbx_issue['timestamp'] - whisper_issue['timestamp']).total_seconds() / 3600
                if lag < 24:  # Within 24 hours
                    findings['key_findings'].append(
                        f"whisper-stt issue at {whisper_issue['timestamp'].strftime('%Y-%m-%d %H:%M')} "
                        f"preceded pbx-web issue at {pbx_issue['timestamp'].strftime('%Y-%m-%d %H:%M')} "
                        f"by {lag:.1f} hours"
                    )

    if not findings['key_findings']:
        findings['key_findings'].append(
            "Both services show stable deployment patterns with no failure correlations."
        )

    print("\nKey Findings:")
    for i, finding in enumerate(findings['key_findings'], 1):
        print(f"  {i}. {finding}")

    # Save intermediate results
    output_file = Path('docs/research/deployment-data/correlation-analysis-results.json')
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Prepare JSON-serializable data
    results = {
        'findings': findings,
        'timeline': [
            {
                'timestamp': e['timestamp'].isoformat(),
                'service': e['service'],
                'source': e['source'],
                'event_type': e['event_type'],
                'outcome': e['outcome'],
                'details': e.get('details', '')
            }
            for e in timeline
        ],
        'correlations': [
            {
                'window_minutes': c['window_minutes'],
                'pbx_timestamp': c['pbx_event']['timestamp'].isoformat(),
                'whisper_timestamp': c['whisper_event']['timestamp'].isoformat(),
                'lag_minutes': c['time_delta'].total_seconds() / 60,
                'whisper_precedes_pbx': c['whisper_precedes_pbx']
            }
            for c in all_correlations
        ]
    }

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to: {output_file}")
    print("\n🎯 CONCLUSION")
    print("=" * 80)

    if len(all_correlations) == 0:
        print("No temporal correlation found between pbx-web and whisper-stt deployments.")
        print("Deployment events are well-separated in time (hours to days apart).")
        print("Both services operate independently with no cascading deployment patterns.")
    elif len(all_correlations) <= 2:
        print("Weak correlation detected - very few coincident deployment windows.")
        print("Services largely operate on independent deployment schedules.")
    else:
        print("Moderate correlation detected - multiple coincident deployment windows.")
        print("Consider investigating deployment coordination and potential interdependencies.")

if __name__ == '__main__':
    analyze()
