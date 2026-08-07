#!/usr/bin/env python3
"""
Analyze deployment patterns and compare service reliability.

Computes failure rates, success rates, mean time to failure, and identifies
common failure patterns between pbx-web and whisper-stt services.
"""

import csv
import json
from datetime import datetime
from collections import defaultdict, Counter
from statistics import mean, median
import sys

def parse_timestamp(ts_str):
    """Parse ISO timestamp string to datetime object."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None

def calculate_durations(timestamps):
    """Calculate durations between consecutive timestamps."""
    durations = []
    valid_timestamps = [t for t in timestamps if t is not None]
    valid_timestamps.sort()

    for i in range(1, len(valid_timestamps)):
        duration = (valid_timestamps[i] - valid_timestamps[i-1]).total_seconds()
        if duration > 0:  # Only positive durations make sense
            durations.append(duration)

    return durations

def analyze_csv(csv_path):
    """Analyze deployment patterns from CSV file."""

    # Initialize data structures
    services = defaultdict(lambda: {
        'total': 0,
        'success': 0,
        'failure': 0,
        'warning': 0,
        'error_codes': Counter(),
        'event_types': Counter(),
        'timestamps': [],
        'durations': [],
        'hourly_distribution': defaultdict(int),
        'daily_distribution': defaultdict(int),
        'weekday_distribution': defaultdict(int)
    })

    # Read and parse CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            service = row['service']
            if not service:
                continue

            event_type = row['event_type']
            status = row['status']
            error_code = row['error_code']
            timestamp_str = row['timestamp']
            duration_str = row['duration']

            # Parse timestamp
            timestamp = parse_timestamp(timestamp_str)

            # Parse duration
            duration = None
            if duration_str:
                try:
                    duration = float(duration_str)
                except (ValueError, TypeError):
                    pass

            # Update service stats
            services[service]['total'] += 1
            services[service]['event_types'][event_type] += 1

            if status == 'success':
                services[service]['success'] += 1
            elif status == 'failure':
                services[service]['failure'] += 1
            elif status == 'warning':
                services[service]['warning'] += 1

            if error_code:
                services[service]['error_codes'][error_code] += 1

            if timestamp:
                services[service]['timestamps'].append(timestamp)
                services[service]['hourly_distribution'][timestamp.hour] += 1
                services[service]['daily_distribution'][timestamp.day] += 1
                services[service]['weekday_distribution'][timestamp.weekday()] += 1

            if duration:
                services[service]['durations'].append(duration)

    # Calculate computed statistics
    results = {}

    for service, data in services.items():
        total = data['total']

        # Basic rates
        success_rate = (data['success'] / total * 100) if total > 0 else 0
        failure_rate = (data['failure'] / total * 100) if total > 0 else 0
        warning_rate = (data['warning'] / total * 100) if total > 0 else 0

        # Duration statistics
        duration_stats = {}
        if data['durations']:
            duration_stats = {
                'mean': mean(data['durations']),
                'median': median(data['durations']),
                'min': min(data['durations']),
                'max': max(data['durations']),
                'count': len(data['durations'])
            }

        # Time to failure (using timestamps)
        time_to_failure = calculate_durations(data['timestamps'])
        ttf_stats = {}
        if time_to_failure:
            ttf_stats = {
                'mean_seconds': mean(time_to_failure),
                'median_seconds': median(time_to_failure),
                'min_seconds': min(time_to_failure),
                'max_seconds': max(time_to_failure),
                'count': len(time_to_failure)
            }

        # Top error codes
        top_errors = [(code, count) for code, count in data['error_codes'].most_common(10)]

        # Top event types
        top_events = [(event, count) for event, count in data['event_types'].most_common(10)]

        results[service] = {
            'total_events': total,
            'success_count': data['success'],
            'failure_count': data['failure'],
            'warning_count': data['warning'],
            'success_rate': round(success_rate, 2),
            'failure_rate': round(failure_rate, 2),
            'warning_rate': round(warning_rate, 2),
            'top_error_codes': top_errors,
            'top_event_types': top_events,
            'duration_stats': duration_stats,
            'time_to_failure_stats': ttf_stats,
            'temporal_patterns': {
                'hourly_distribution': dict(data['hourly_distribution']),
                'weekday_distribution': {
                    'monday': data['weekday_distribution'][0],
                    'tuesday': data['weekday_distribution'][1],
                    'wednesday': data['weekday_distribution'][2],
                    'thursday': data['weekday_distribution'][3],
                    'friday': data['weekday_distribution'][4],
                    'saturday': data['weekday_distribution'][5],
                    'sunday': data['weekday_distribution'][6],
                }
            }
        }

    return results

def compare_services(results):
    """Compare services and identify patterns."""

    if len(results) < 2:
        return {'comparison': 'Need at least 2 services for comparison'}

    services = list(results.keys())

    comparison = {
        'services_analyzed': services,
        'failure_rate_comparison': {},
        'success_rate_comparison': {},
        'shared_error_codes': {},
        'unique_errors': {},
        'temporal_patterns': {}
    }

    # Compare failure and success rates
    for service in services:
        comparison['failure_rate_comparison'][service] = results[service]['failure_rate']
        comparison['success_rate_comparison'][service] = results[service]['success_rate']

    # Find shared and unique error codes
    all_errors = {}
    for service in services:
        all_errors[service] = set(code for code, _ in results[service]['top_error_codes'])

    if len(services) == 2:
        shared = all_errors[services[0]] & all_errors[services[1]]
        unique_to_first = all_errors[services[0]] - all_errors[services[1]]
        unique_to_second = all_errors[services[1]] - all_errors[services[0]]

        comparison['shared_error_codes'] = {
            'pbx-web': list(shared & all_errors['pbx-web']),
            'whisper-stt': list(shared & all_errors['whisper-stt']),
            'all_shared': list(shared)
        }

        comparison['unique_errors'] = {
            services[0]: list(unique_to_first),
            services[1]: list(unique_to_second)
        }

    return comparison

def generate_summary(results, comparison):
    """Generate human-readable summary."""

    summary = []
    summary.append("=" * 80)
    summary.append("DEPLOYMENT PATTERN ANALYSIS SUMMARY")
    summary.append("=" * 80)
    summary.append("")

    # Overall statistics
    summary.append("## OVERALL STATISTICS")
    summary.append("")

    for service, data in results.items():
        summary.append(f"### {service}")
        summary.append(f"  Total Events: {data['total_events']:,}")
        summary.append(f"  Success Rate: {data['success_rate']}% ({data['success_count']:,} events)")
        summary.append(f"  Failure Rate: {data['failure_rate']}% ({data['failure_count']:,} events)")
        summary.append(f"  Warning Rate: {data['warning_rate']}% ({data['warning_count']:,} events)")
        summary.append("")

        if data['duration_stats']:
            summary.append(f"  Duration Statistics (seconds):")
            summary.append(f"    Mean: {data['duration_stats']['mean']:.2f}")
            summary.append(f"    Median: {data['duration_stats']['median']:.2f}")
            summary.append(f"    Range: {data['duration_stats']['min']:.2f} - {data['duration_stats']['max']:.2f}")
            summary.append("")

        if data['time_to_failure_stats']:
            summary.append(f"  Time to Failure Statistics:")
            summary.append(f"    Mean: {data['time_to_failure_stats']['mean_seconds']:.2f} seconds")
            summary.append(f"    Median: {data['time_to_failure_stats']['median_seconds']:.2f} seconds")
            summary.append(f"    Range: {data['time_to_failure_stats']['min_seconds']:.2f} - {data['time_to_failure_stats']['max_seconds']:.2f} seconds")
            summary.append("")

    # Common failure patterns
    summary.append("## COMMON FAILURE PATTERNS")
    summary.append("")

    for service, data in results.items():
        summary.append(f"### {service} - Top Error Codes")
        if data['top_error_codes']:
            for error_code, count in data['top_error_codes'][:5]:
                pct = (count / data['total_events']) * 100
                summary.append(f"  {error_code}: {count:,} occurrences ({pct:.2f}%)")
        else:
            summary.append("  No error codes recorded")
        summary.append("")

    # Event type patterns
    summary.append("## EVENT TYPE PATTERNS")
    summary.append("")

    for service, data in results.items():
        summary.append(f"### {service} - Top Event Types")
        if data['top_event_types']:
            for event_type, count in data['top_event_types'][:5]:
                pct = (count / data['total_events']) * 100
                summary.append(f"  {event_type}: {count:,} occurrences ({pct:.2f}%)")
        else:
            summary.append("  No event types recorded")
        summary.append("")

    # Service comparison
    summary.append("## SERVICE COMPARISON")
    summary.append("")

    if 'failure_rate_comparison' in comparison:
        summary.append("### Failure Rates")
        for service, rate in comparison['failure_rate_comparison'].items():
            summary.append(f"  {service}: {rate}%")
        summary.append("")

    if 'shared_error_codes' in comparison and comparison['shared_error_codes']:
        summary.append("### Shared Error Codes")
        if 'all_shared' in comparison['shared_error_codes']:
            shared = comparison['shared_error_codes']['all_shared']
            if shared:
                summary.append(f"  Common to both: {', '.join(shared)}")
            else:
                summary.append("  No shared error codes found")
        summary.append("")

    if 'unique_errors' in comparison and comparison['unique_errors']:
        summary.append("### Unique Error Codes")
        for service, errors in comparison['unique_errors'].items():
            if errors:
                summary.append(f"  {service}: {', '.join(errors)}")
        summary.append("")

    # Temporal patterns
    summary.append("## TEMPORAL PATTERNS")
    summary.append("")

    for service, data in results.items():
        summary.append(f"### {service} - Weekly Distribution")
        weekday = data['temporal_patterns']['weekday_distribution']

        total_weekday = sum(weekday.values())
        if total_weekday > 0:
            weekday_pcts = {day: (count / total_weekday * 100) for day, count in weekday.items()}
            summary.append(f"  Monday: {weekday['monday']} events ({weekday_pcts['monday']:.1f}%)")
            summary.append(f"  Tuesday: {weekday['tuesday']} events ({weekday_pcts['tuesday']:.1f}%)")
            summary.append(f"  Wednesday: {weekday['wednesday']} events ({weekday_pcts['wednesday']:.1f}%)")
            summary.append(f"  Thursday: {weekday['thursday']} events ({weekday_pcts['thursday']:.1f}%)")
            summary.append(f"  Friday: {weekday['friday']} events ({weekday_pcts['friday']:.1f}%)")
            summary.append(f"  Saturday: {weekday['saturday']} events ({weekday_pcts['saturday']:.1f}%)")
            summary.append(f"  Sunday: {weekday['sunday']} events ({weekday_pcts['sunday']:.1f}%)")
        else:
            summary.append("  No weekday data available")
        summary.append("")

    # Key findings
    summary.append("## KEY FINDINGS")
    summary.append("")

    if len(results) >= 2:
        services = list(results.keys())
        failure_rates = {s: results[s]['failure_rate'] for s in services}
        worst_service = max(failure_rates, key=failure_rates.get)
        best_service = min(failure_rates, key=failure_rates.get)

        summary.append(f"• Highest failure rate: {worst_service} ({failure_rates[worst_service]}%)")
        summary.append(f"• Lowest failure rate: {best_service} ({failure_rates[best_service]}%)")

        if abs(failure_rates[worst_service] - failure_rates[best_service]) > 5:
            summary.append(f"⚠️  Significant reliability divergence ({failure_rates[worst_service] - failure_rates[best_service]:.1f}% difference)")

    summary.append("")

    # Recommendations
    summary.append("## RECOMMENDATIONS")
    summary.append("")

    for service, data in results.items():
        if data['failure_rate'] > 10:
            summary.append(f"⚠️  {service}: High failure rate ({data['failure_rate']}%) - investigate top error codes")

        if data['top_error_codes']:
            top_error, count = data['top_error_codes'][0]
            if (count / data['total_events']) > 0.05:  # More than 5%
                summary.append(f"🔍 {service}: Address '{top_error}' - {count} occurrences ({(count/data['total_events']*100):.1f}%)")

    summary.append("")
    summary.append("=" * 80)

    return "\n".join(summary)

def main():
    """Main analysis function."""

    csv_path = "/home/coding/aide-de-camp/data/parsed_deployments.csv"
    json_output_path = "/home/coding/aide-de-camp/data/analysis_results.json"
    summary_output_path = "/home/coding/aide-de-camp/data/pattern_summary.txt"

    print(f"Analyzing deployment patterns from {csv_path}...")

    try:
        # Run analysis
        results = analyze_csv(csv_path)

        # Generate comparison
        comparison = compare_services(results)

        # Combine results
        output_data = {
            'analysis_timestamp': datetime.utcnow().isoformat() + 'Z',
            'services': results,
            'comparison': comparison
        }

        # Write JSON output
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)

        print(f"✓ JSON results written to {json_output_path}")

        # Generate and write summary
        summary = generate_summary(results, comparison)
        with open(summary_output_path, 'w', encoding='utf-8') as f:
            f.write(summary)

        print(f"✓ Summary written to {summary_output_path}")

        # Print key stats to console
        print("\n" + "="*60)
        print("ANALYSIS COMPLETE - KEY STATISTICS")
        print("="*60)
        for service, data in results.items():
            print(f"\n{service}:")
            print(f"  Total: {data['total_events']:,} events")
            print(f"  Success: {data['success_rate']}%")
            print(f"  Failure: {data['failure_rate']}%")
            if data['top_error_codes']:
                print(f"  Top error: {data['top_error_codes'][0][0]} ({data['top_error_codes'][0][1]:,} occurrences)")

        return 0

    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
