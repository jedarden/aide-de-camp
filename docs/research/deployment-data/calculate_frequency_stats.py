#!/usr/bin/env python3
"""
Calculate frequency statistics per failure pattern.

Groups failure data by pattern type and calculates:
- Total occurrence count per pattern
- List of affected services
- Count per service
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Any


def load_classified_failures(data_path: Path) -> Dict[str, Any]:
    """Load classified failure data."""
    with open(data_path, 'r') as f:
        return json.load(f)


def calculate_pattern_frequency(classified_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate frequency statistics per pattern type.

    Returns:
        Dictionary with pattern statistics:
        {
            "pattern_type": {
                "total_count": int,
                "services": {
                    "service_name": count
                },
                "severity_counts": {
                    "severity": count
                }
            }
        }
    """
    classified_failures = classified_data.get('classified_failures', [])

    # Initialize nested structure
    pattern_stats = defaultdict(lambda: {
        'total_count': 0,
        'services': Counter(),
        'severity_counts': Counter(),
        'severity_level': None,
        'description': None
    })

    # Load pattern definitions for metadata
    pattern_definitions = {}
    for definition in classified_data.get('pattern_definitions', []):
        pattern_definitions[definition['name']] = {
            'severity': definition['severity'],
            'description': definition['description']
        }

    # Process each failure record
    for failure in classified_failures:
        pattern_type = failure.get('pattern_type', 'Unknown')
        service = failure.get('service', 'unknown')
        severity = failure.get('pattern_severity', 'unknown')

        # Update counts
        pattern_stats[pattern_type]['total_count'] += 1
        pattern_stats[pattern_type]['services'][service] += 1
        pattern_stats[pattern_type]['severity_counts'][severity] += 1

        # Set metadata from pattern definitions
        if pattern_type in pattern_definitions:
            pattern_stats[pattern_type]['severity_level'] = pattern_definitions[pattern_type]['severity']
            pattern_stats[pattern_type]['description'] = pattern_definitions[pattern_type]['description']

    # Convert Counter objects to regular dicts for JSON serialization
    result = {}
    for pattern_type, stats in pattern_stats.items():
        result[pattern_type] = {
            'total_count': stats['total_count'],
            'services': dict(stats['services']),
            'severity_counts': dict(stats['severity_counts']),
            'severity_level': stats['severity_level'],
            'description': stats['description']
        }

    return result


def create_summary_table(pattern_stats: Dict[str, Any]) -> Dict[str, Any]:
    """Create a summary table for easy reading."""
    summary = {
        'total_patterns': len(pattern_stats),
        'total_failures': sum(p['total_count'] for p in pattern_stats.values()),
        'pattern_rankings': sorted(
            [(pattern, stats['total_count']) for pattern, stats in pattern_stats.items()],
            key=lambda x: x[1],
            reverse=True
        ),
        'services_affected': set(),
        'high_severity_patterns': [],
        'critical_severity_patterns': []
    }

    # Collect unique services across all patterns
    for stats in pattern_stats.values():
        summary['services_affected'].update(stats['services'].keys())

    summary['services_affected'] = list(summary['services_affected'])

    # Identify high/critical severity patterns
    for pattern, stats in pattern_stats.items():
        if stats['severity_level'] == 'high' and stats['total_count'] > 0:
            summary['high_severity_patterns'].append(pattern)
        elif stats['severity_level'] == 'critical' and stats['total_count'] > 0:
            summary['critical_severity_patterns'].append(pattern)

    return summary


def save_frequency_results(pattern_stats: Dict[str, Any], summary: Dict[str, Any], output_path: Path):
    """Save frequency analysis results."""
    output = {
        'metadata': {
            'analysis_type': 'frequency_by_pattern',
            'generated_at': '2026-08-06T23:00:00Z',
            'source_data': 'classified-failures.json'
        },
        'pattern_statistics': pattern_stats,
        'summary': summary
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✅ Saved frequency analysis to {output_path}")


def print_frequency_summary(pattern_stats: Dict[str, Any], summary: Dict[str, Any]):
    """Print a formatted summary table."""
    print("\n" + "="*80)
    print("FAILURE PATTERN FREQUENCY ANALYSIS")
    print("="*80)

    print(f"\nTotal Patterns Analyzed: {summary['total_patterns']}")
    print(f"Total Failures: {summary['total_failures']}")
    print(f"Services Affected: {', '.join(summary['services_affected']) if summary['services_affected'] else 'None'}")

    if summary['critical_severity_patterns']:
        print(f"\n⚠️  CRITICAL Severity Patterns: {', '.join(summary['critical_severity_patterns'])}")
    if summary['high_severity_patterns']:
        print(f"⚠️  HIGH Severity Patterns: {', '.join(summary['high_severity_patterns'])}")

    print("\n" + "-"*80)
    print(f"{'Pattern Type':<25} {'Count':>8} {'Severity':>12} {'Services':>20}")
    print("-"*80)

    for pattern, count in summary['pattern_rankings']:
        stats = pattern_stats[pattern]
        services = ', '.join(stats['services'].keys())
        severity = stats['severity_level'] or 'unknown'

        print(f"{pattern:<25} {count:>8} {severity:>12} {services:>20}")

    print("="*80 + "\n")


def main():
    """Main execution function."""
    base_path = Path('/home/coding/aide-de-camp/docs/research/deployment-data')
    input_file = base_path / 'classified-failures.json'
    output_file = base_path / 'frequency-by-pattern.json'

    print("Loading classified failure data...")
    classified_data = load_classified_failures(input_file)

    print("Calculating pattern frequencies...")
    pattern_stats = calculate_pattern_frequency(classified_data)

    print("Creating summary...")
    summary = create_summary_table(pattern_stats)

    print("Saving results...")
    save_frequency_results(pattern_stats, summary, output_file)

    print_frequency_summary(pattern_stats, summary)


if __name__ == '__main__':
    main()