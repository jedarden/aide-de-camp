#!/usr/bin/env python3
"""
Calculate daily deployment counts per service for pbx-web and whisper-stt.
Groups deployments by date (not datetime) and counts deployments per day.
"""

import json
from collections import defaultdict
from datetime import datetime

def load_deployment_data():
    """Load deployment data from various sources."""

    # Load pbx-web deployment data
    with open('/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json', 'r') as f:
        pbx_data = json.load(f)

    # Load whisper-stt deployment data
    with open('/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json', 'r') as f:
        whisper_data = json.load(f)

    return pbx_data, whisper_data

def extract_deployment_events(data, service_name):
    """Extract deployment events with timestamps."""
    events = []

    # Check for deployment_events_last_30_days key (pbx-web format)
    if 'deployment_events_last_30_days' in data:
        for event in data['deployment_events_last_30_days']:
            if 'timestamp' in event:
                timestamp = event['timestamp']
                # Extract date from timestamp
                date = timestamp.split('T')[0] if 'T' in timestamp else timestamp
                events.append({
                    'timestamp': timestamp,
                    'event_type': event.get('event_type', 'unknown'),
                    'revision': event.get('revision'),
                    'date': date
                })

    # Check for deployment_history_30_days key (whisper-stt format)
    elif 'deployment_history_30_days' in data:
        history = data['deployment_history_30_days']
        if 'replicasets' in history:
            for rs in history['replicasets']:
                # Only count replicasets for the specific service
                if rs.get('deployment') == service_name:
                    timestamp = rs.get('created')
                    if timestamp:
                        date = timestamp.split('T')[0] if 'T' in timestamp else timestamp
                        events.append({
                            'timestamp': timestamp,
                            'event_type': 'replica_set_created',
                            'revision': rs.get('revision'),
                            'date': date,
                            'image': rs.get('image')
                        })

    # Check for deployment_events key (alternative format)
    elif 'deployment_events' in data:
        for event in data['deployment_events']:
            if 'timestamp' in event:
                timestamp = event['timestamp']
                date = timestamp.split('T')[0] if 'T' in timestamp else timestamp
                events.append({
                    'timestamp': timestamp,
                    'event_type': event.get('event_type', 'unknown'),
                    'revision': event.get('revision'),
                    'date': date
                })

    return events

def group_by_date(events):
    """Group deployment events by date."""
    daily_counts = defaultdict(int)

    for event in events:
        date = event.get('date')
        if date:
            daily_counts[date] += 1

    return dict(daily_counts)

def calculate_metrics(daily_counts, service_name):
    """Calculate deployment frequency metrics."""
    total_deployments = sum(daily_counts.values())
    days_with_deployments = len(daily_counts)

    # Handle edge case of single deployment
    if days_with_deployments == 1:
        avg_deployments_per_day = 1.0
    elif days_with_deployments > 1:
        # Get date range
        dates = sorted(daily_counts.keys())
        date_range_days = (datetime.strptime(dates[-1], '%Y-%m-%d') -
                          datetime.strptime(dates[0], '%Y-%m-%d')).days + 1
        avg_deployments_per_day = total_deployments / date_range_days if date_range_days > 0 else total_deployments
    else:
        avg_deployments_per_day = 0.0

    return {
        'total_deployments': total_deployments,
        'days_with_deployments': days_with_deployments,
        'avg_deployments_per_day': round(avg_deployments_per_day, 3),
        'daily_breakdown': daily_counts
    }

def main():
    """Main function to calculate daily deployment counts."""

    print("Loading deployment data...")
    pbx_data, whisper_data = load_deployment_data()

    print("Extracting deployment events...")
    pbx_events = extract_deployment_events(pbx_data, 'pbx-web')
    whisper_events = extract_deployment_events(whisper_data, 'whisper-stt')

    print(f"pbx-web: {len(pbx_events)} deployment events")
    print(f"whisper-stt: {len(whisper_events)} deployment events")

    print("\nGrouping by date...")
    pbx_daily = group_by_date(pbx_events)
    whisper_daily = group_by_date(whisper_events)

    print("\nCalculating metrics...")
    pbx_metrics = calculate_metrics(pbx_daily, 'pbx-web')
    whisper_metrics = calculate_metrics(whisper_daily, 'whisper-stt')

    # Prepare results
    results = {
        'analysis_metadata': {
            'generated_at': datetime.now().isoformat(),
            'analysis_period': 'Last 30 days',
            'services_analyzed': ['pbx-web', 'whisper-stt']
        },
        'pbx_web_metrics': pbx_metrics,
        'whisper_stt_metrics': whisper_metrics,
        'comparative_analysis': {
            'pbx_web_daily_count': pbx_metrics['days_with_deployments'],
            'pbx_web_avg_per_day': pbx_metrics['avg_deployments_per_day'],
            'whisper_stt_daily_count': whisper_metrics['days_with_deployments'],
            'whisper_stt_avg_per_day': whisper_metrics['avg_deployments_per_day'],
            'more_frequent_service': 'pbx-web' if pbx_metrics['avg_deployments_per_day'] > whisper_metrics['avg_deployments_per_day'] else 'whisper-stt'
        }
    }

    # Save results
    output_file = '/home/coding/aide-de-camp/notes/adc-4h468-daily-deployment-counts.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print("DAILY DEPLOYMENT COUNT RESULTS")
    print(f"{'='*60}")

    print(f"\npbx-web:")
    print(f"  Total deployments: {pbx_metrics['total_deployments']}")
    print(f"  Days with deployments: {pbx_metrics['days_with_deployments']}")
    print(f"  Average deployments per day: {pbx_metrics['avg_deployments_per_day']}")
    print(f"  Daily breakdown:")
    for date, count in sorted(pbx_daily.items()):
        print(f"    {date}: {count} deployment(s)")

    print(f"\nwhisper-stt:")
    print(f"  Total deployments: {whisper_metrics['total_deployments']}")
    print(f"  Days with deployments: {whisper_metrics['days_with_deployments']}")
    print(f"  Average deployments per day: {whisper_metrics['avg_deployments_per_day']}")
    if whisper_daily:
        print(f"  Daily breakdown:")
        for date, count in sorted(whisper_daily.items()):
            print(f"    {date}: {count} deployment(s)")

    print(f"\n{'='*60}")
    print("COMPARISON")
    print(f"{'='*60}")
    print(f"More frequent service: {results['comparative_analysis']['more_frequent_service']}")
    print(f"pbx-web: {pbx_metrics['avg_deployments_per_day']} deployments/day over {pbx_metrics['days_with_deployments']} days")
    print(f"whisper-stt: {whisper_metrics['avg_deployments_per_day']} deployments/day over {whisper_metrics['days_with_deployments']} days")

    print(f"\nResults saved to: {output_file}")

    return results

if __name__ == '__main__':
    main()