#!/usr/bin/env python3
"""
Build comprehensive failure taxonomy with frequency analysis.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any


# Simplified pattern rules - avoiding complex nested lambdas
COMPREHENSIVE_PATTERN_RULES = {
    'HTTPError': {
        'description': 'HTTP error responses (4xx, 5xx)',
        'severity': 'medium',
        'matchers': [
            lambda r: r.get('error_type', '') in ['http_500', 'http_503', 'http_404', 'http_502'],
        ]
    },
    'DependencyTimeout': {
        'description': 'Timeout connecting to dependent services',
        'severity': 'medium', 
        'matchers': [
            lambda r: r.get('error_type', '') == 'connection_reset',
            lambda r: 'connection reset' in str(r.get('_msg', '')).lower() or 'timeout' in str(r.get('_msg', '')).lower(),
        ]
    },
    'NetworkIssue': {
        'description': 'Network allocation or connectivity problems',
        'severity': 'low',
        'matchers': [
            lambda r: r.get('error_type', '') == 'broken_pipe',
            lambda r: 'broken pipe' in str(r.get('_msg', '')).lower(),
        ]
    },
    'RecordingFetchError': {
        'description': 'Failed to fetch recordings from storage backend',
        'severity': 'medium',
        'matchers': [
            lambda r: r.get('error_type', '') == 'recording_fetch_errors',
            lambda r: 'recording fetch error' in str(r.get('_msg', '')).lower(),
        ]
    },
    'DeploymentRollback': {
        'description': 'Deployment was rolled back to previous version',
        'severity': 'high',
        'matchers': [
            lambda r: r.get('outcome', '') == 'rolled_back',
        ]
    },
    'ApplicationError': {
        'description': 'Application-level errors (exceptions, panics, etc.)',
        'severity': 'high',
        'matchers': [
            lambda r: 'traceback' in str(r.get('_msg', '')).lower() or 'exception' in str(r.get('_msg', '')).lower(),
        ]
    },
    'HTTPHealthCheck': {
        'description': 'HTTP health check requests (normal traffic)',
        'severity': 'info',
        'matchers': [
            lambda r: '"GET /health' in str(r.get('_msg', '')) or '"GET /api/health' in str(r.get('_msg', '')),
        ]
    },
    'HTTPNormalTraffic': {
        'description': 'Normal HTTP requests with 2xx/3xx responses',
        'severity': 'info',
        'matchers': [
            lambda r: any(code in str(r.get('_msg', '')) for code in ['200 OK', '201 Created', '202 Accepted']),
        ]
    },
    'InfoLogging': {
        'description': 'General informational logging messages',
        'severity': 'info',
        'matchers': [
            lambda r: r.get('log_level', '').lower() in ['info', 'debug'],
        ]
    },
}


def categorize_comprehensive(record: Dict[str, Any]) -> str:
    """Apply comprehensive pattern-matching rules to categorize any record type."""

    for pattern_name, pattern_config in COMPREHENSIVE_PATTERN_RULES.items():
        matchers = pattern_config.get('matchers', [])

        for matcher in matchers:
            try:
                if matcher(record):
                    return pattern_name
            except Exception:
                continue

    return 'uncategorized'


def build_service_distribution(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Build distribution of failures by service."""
    service_distribution = defaultdict(lambda: defaultdict(int))

    for record in records:
        category = record.get('pattern_category', 'uncategorized')

        service = 'unknown'
        if record.get('service'):
            service = record['service']
        elif record.get('app'):
            service = record['app']
        elif record.get('kubernetes', {}).get('namespace_name'):
            service = record['kubernetes']['namespace_name']

        service_distribution[service][category] += 1

    return dict(service_distribution)


def build_time_distribution(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Build temporal distribution of failures."""
    time_distribution = defaultdict(lambda: defaultdict(int))

    for record in records:
        category = record.get('pattern_category', 'uncategorized')

        timestamp = record.get('_time', record.get('timestamp', ''))
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                date_key = dt.strftime('%Y-%m-%d')
                time_distribution[category][date_key] += 1
            except:
                pass

    return dict(time_distribution)


def build_complete_taxonomy(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build complete taxonomy with comprehensive frequency analysis."""

    categorized_records = []
    category_stats = defaultdict(lambda: {
        'count': 0,
        'severity': 'unknown',
        'description': 'Unknown pattern',
        'examples': [],
        'first_seen': None,
        'last_seen': None
    })

    for record in records:
        category = categorize_comprehensive(record)
        record['pattern_category'] = category
        categorized_records.append(record)

        stats = category_stats[category]
        stats['count'] += 1

        if category in COMPREHENSIVE_PATTERN_RULES:
            stats['severity'] = COMPREHENSIVE_PATTERN_RULES[category]['severity']
            stats['description'] = COMPREHENSIVE_PATTERN_RULES[category]['description']

        timestamp = record.get('_time', record.get('timestamp', ''))
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                if stats['first_seen'] is None or dt < stats['first_seen']:
                    stats['first_seen'] = dt
                if stats['last_seen'] is None or dt > stats['last_seen']:
                    stats['last_seen'] = dt
            except:
                pass

        if len(stats['examples']) < 5:
            example = {
                'timestamp': timestamp,
                'source': record.get('_source_file', record.get('source', 'unknown')),
                'service': record.get('service', record.get('app', record.get('kubernetes', {}).get('namespace_name', 'unknown'))),
                'sample_data': str(record.get('_msg', record.get('message', record.get('reason', ''))))[:200]
            }
            stats['examples'].append(example)

    taxonomy = {
        'generated_at': datetime.now().isoformat(),
        'taxonomy_version': 'comprehensive_v1',
        'summary': {
            'total_records': len(records),
            'categories_found': len(category_stats),
            'categorized_count': sum(stats['count'] for cat, stats in category_stats.items() if cat != 'uncategorized'),
            'uncategorized_count': category_stats.get('uncategorized', {}).get('count', 0),
            'coverage_percentage': round((sum(stats['count'] for cat, stats in category_stats.items() if cat != 'uncategorized') / len(records)) * 100, 2) if records else 0
        },
        'service_distribution': build_service_distribution(categorized_records),
        'time_distribution': build_time_distribution(categorized_records),
        'categories': dict(category_stats)
    }

    return taxonomy


def main():
    """Main entry point for taxonomy building."""

    categorized_file = Path('categorized-failures-report.json')

    print("=" * 70)
    print("BUILDING COMPREHENSIVE FAILURE TAXONOMY")
    print("=" * 70)

    if not categorized_file.exists():
        print(f"ERROR: {categorized_file} not found. Run categorize_failures.py first.")
        return

    print(f"\n1. Loading categorized failures from {categorized_file}...")
    with open(categorized_file, 'r') as f:
        categorized_data = json.load(f)

    all_records = categorized_data['failures']
    print(f"   Loaded {len(all_records)} records")

    print(f"\n2. Building comprehensive taxonomy with {len(COMPREHENSIVE_PATTERN_RULES)} pattern categories...")
    taxonomy = build_complete_taxonomy(all_records)

    output_file = Path('comprehensive-failure-taxonomy.json')
    print(f"\n3. Writing comprehensive taxonomy to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(taxonomy, f, indent=2, default=str)

    print("\n" + "=" * 70)
    print("TAXONOMY SUMMARY")
    print("=" * 70)
    print(f"Total records processed: {taxonomy['summary']['total_records']}")
    print(f"Pattern categories defined: {len(COMPREHENSIVE_PATTERN_RULES)}")
    print(f"Categories found in data: {taxonomy['summary']['categories_found']}")
    print(f"Categorized records: {taxonomy['summary']['categorized_count']}")
    print(f"Uncategorized records: {taxonomy['summary']['uncategorized_count']}")
    print(f"Coverage: {taxonomy['summary']['coverage_percentage']}%")

    print(f"\nTop categories by frequency:")
    sorted_categories = sorted(
        taxonomy['categories'].items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )

    for i, (category, stats) in enumerate(sorted_categories[:10], 1):
        print(f"\n{i}. {category}:")
        print(f"   Count: {stats['count']:,} ({round(stats['count']/taxonomy['summary']['total_records']*100, 2)}%)")
        print(f"   Severity: {stats['severity']}")
        print(f"   Description: {stats['description']}")
        if stats['first_seen'] and stats['last_seen']:
            print(f"   Time range: {stats['first_seen'].strftime('%Y-%m-%d')} to {stats['last_seen'].strftime('%Y-%m-%d')}")

    print(f"\nService distribution:")
    for service, categories in list(taxonomy['service_distribution'].items())[:5]:
        total = sum(categories.values())
        print(f"   {service}: {total:,} records")
        top_cat = max(categories.items(), key=lambda x: x[1])
        print(f"      Top issue: {top_cat[0]} ({top_cat[1]:,} occurrences)")

    print("\n" + "=" * 70)
    print(f"Comprehensive taxonomy saved to: {output_file}")
    print("=" * 70)


if __name__ == '__main__':
    main()
