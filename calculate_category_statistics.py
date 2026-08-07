#!/usr/bin/env python3
"""
Calculate frequency statistics by pattern category.

For each pattern category from the categorization step, this script calculates:
- Total count of occurrences
- Distribution by service (which services had which failures)
- Image/version context (what images/versions were involved)
- Time distribution (how failures spread across 30-day timeline)

Acceptance Criteria:
1. For each pattern category, calculate total count, distribution by service,
   image/version context, and time distribution
2. Aggregate stats into structured format ready for taxonomy
3. Output per-category statistics dataset
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def extract_timestamp_from_message(message: str) -> datetime | None:
    """Extract ISO timestamp from log message."""
    if not message:
        return None

    # Look for ISO timestamp patterns like 2026-07-28T13:36:40.095001455-04:00
    # or 2026-07-13T18:07:55Z
    patterns = [
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[\d:.Z+-]+)',
        r'(\d{4}-\d{2}-\d{2})',
    ]

    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            ts_str = match.group(1)
            try:
                # Parse ISO timestamp
                if 'T' in ts_str:
                    return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                else:
                    return datetime.fromisoformat(ts_str)
            except ValueError:
                continue
    return None


def extract_service_from_failure(failure: Dict[str, Any]) -> str:
    """Extract service name from failure record."""
    # Direct service field
    if 'service' in failure:
        return failure['service']

    # From source file
    if '_source_file' in failure:
        source_file = failure['_source_file']
        if 'pbx-web' in source_file.lower():
            return 'pbx-web'
        elif 'whisper-stt' in source_file.lower():
            return 'whisper-stt'

    # From message
    if 'message' in failure:
        message = failure['message']
        if '[pbx-web]' in message:
            return 'pbx-web'
        elif '[whisper-stt]' in message:
            return 'whisper-stt'

    return 'unknown'


def extract_image_from_failure(failure: Dict[str, Any]) -> str:
    """Extract image tag from failure record."""
    # Direct image field
    if 'image' in failure and failure['image']:
        return failure['image']

    # From pod_name patterns
    if 'pod_name' in failure:
        pod_name = failure['pod_name']
        if 'pbx-web' in pod_name:
            return 'ronaldraygun/pbx-web:version-unknown'
        elif 'whisper-stt' in pod_name:
            return 'ronaldraygun/whisper-stt:version-unknown'

    return 'unknown'


def extract_namespace_from_failure(failure: Dict[str, Any]) -> str:
    """Extract namespace from failure record."""
    if 'namespace' in failure:
        return failure['namespace']

    # From source file
    if '_source_file' in failure:
        source_file = failure['_source_file']
        if 'pbx-web' in source_file.lower():
            return 'pbx-web'
        elif 'whisper-stt' in source_file.lower():
            return 'whisper-stt'

    return 'unknown'


def calculate_category_statistics(failures: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Calculate comprehensive statistics for each pattern category."""

    # Group by pattern category
    categorized_failures = defaultdict(list)
    for failure in failures:
        category = failure.get('pattern_category', 'uncategorized')
        categorized_failures[category].append(failure)

    # Calculate statistics for each category
    category_stats = {}

    for category, cat_failures in categorized_failures.items():
        if category == 'uncategorized':
            continue

        print(f"Calculating statistics for {category} ({len(cat_failures)} failures)...")

        stats = {
            'category': category,
            'total_count': len(cat_failures),
            'error_type_distribution': Counter(),
            'severity_distribution': Counter(),
            'service_distribution': Counter(),
            'namespace_distribution': Counter(),
            'source_distribution': Counter(),
            'image_distribution': Counter(),  # New: image/version context
            'temporal_distribution': defaultdict(int),  # by day
            'timestamps': [],
            'sample_failures': [],
        }

        # Process each failure in the category
        for failure in cat_failures:
            # Error type distribution
            error_type = failure.get('error_type', 'unknown')
            stats['error_type_distribution'][error_type] += 1

            # Severity distribution
            severity = failure.get('severity', 'unknown')
            stats['severity_distribution'][severity] += 1

            # Service distribution
            service = extract_service_from_failure(failure)
            stats['service_distribution'][service] += 1

            # Namespace distribution
            namespace = extract_namespace_from_failure(failure)
            stats['namespace_distribution'][namespace] += 1

            # Source distribution
            source = failure.get('source', 'unknown')
            stats['source_distribution'][source] += 1

            # Image/version distribution
            image = extract_image_from_failure(failure)
            stats['image_distribution'][image] += 1

            # Temporal distribution
            timestamp = None
            if 'timestamp' in failure:
                try:
                    timestamp = datetime.fromisoformat(failure['timestamp'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass

            if not timestamp and 'message' in failure:
                timestamp = extract_timestamp_from_message(failure['message'])

            if timestamp:
                stats['timestamps'].append(timestamp)
                day_key = timestamp.strftime('%Y-%m-%d')
                stats['temporal_distribution'][day_key] += 1

        # Convert Counters to regular dicts for JSON serialization
        stats['error_type_distribution'] = dict(sorted(
            stats['error_type_distribution'].items(),
            key=lambda x: x[1],
            reverse=True
        ))

        stats['severity_distribution'] = dict(sorted(
            stats['severity_distribution'].items(),
            key=lambda x: x[1],
            reverse=True
        ))

        stats['service_distribution'] = dict(sorted(
            stats['service_distribution'].items(),
            key=lambda x: x[1],
            reverse=True
        ))

        stats['namespace_distribution'] = dict(sorted(
            stats['namespace_distribution'].items(),
            key=lambda x: x[1],
            reverse=True
        ))

        stats['source_distribution'] = dict(sorted(
            stats['source_distribution'].items(),
            key=lambda x: x[1],
            reverse=True
        ))

        stats['image_distribution'] = dict(sorted(
            stats['image_distribution'].items(),
            key=lambda x: x[1],
            reverse=True
        ))

        stats['temporal_distribution'] = dict(sorted(
            stats['temporal_distribution'].items()
        ))

        # Add sample failures (up to 5)
        stats['sample_failures'] = cat_failures[:5]

        category_stats[category] = stats

    return category_stats


def add_percentages_to_distribution(distribution: Dict[str, int], total: int) -> Dict[str, Dict[str, Any]]:
    """Add percentages to a distribution dict."""
    result = {}
    for key, count in distribution.items():
        percentage = (count / total * 100) if total > 0 else 0
        result[key] = {
            'count': count,
            'percentage': round(percentage, 2)
        }
    return result


def enhance_statistics_with_percentages(category_stats: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Add percentage calculations to all category statistics."""
    enhanced_stats = {}

    for category, stats in category_stats.items():
        total_count = stats['total_count']

        enhanced = {
            'category': stats['category'],
            'total_count': total_count,
            'error_type_distribution': add_percentages_to_distribution(
                stats['error_type_distribution'], total_count
            ),
            'severity_distribution': add_percentages_to_distribution(
                stats['severity_distribution'], total_count
            ),
            'service_distribution': add_percentages_to_distribution(
                stats['service_distribution'], total_count
            ),
            'namespace_distribution': add_percentages_to_distribution(
                stats['namespace_distribution'], total_count
            ),
            'source_distribution': add_percentages_to_distribution(
                stats['source_distribution'], total_count
            ),
            'image_distribution': add_percentages_to_distribution(
                stats['image_distribution'], total_count
            ),
            'temporal_distribution': stats['temporal_distribution'],
            'timestamps': stats['timestamps'],
            'sample_failures': stats['sample_failures'],
        }

        enhanced_stats[category] = enhanced

    return enhanced_stats


def generate_summary_statistics(category_stats: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary statistics across all categories."""

    summary = {
        'total_categories': len(category_stats),
        'total_categorized_failures': sum(stats['total_count'] for stats in category_stats.values()),
        'category_counts': {cat: stats['total_count'] for cat, stats in category_stats.items()},
        'categories_by_frequency': sorted(
            category_stats.items(),
            key=lambda x: x[1]['total_count'],
            reverse=True
        ),
        'all_services': set(),
        'all_namespaces': set(),
        'all_images': set(),  # New: track all unique images
        'date_range': {'earliest': None, 'latest': None},
    }

    # Collect all services, namespaces, and images
    for stats in category_stats.values():
        summary['all_services'].update(stats['service_distribution'].keys())
        summary['all_namespaces'].update(stats['namespace_distribution'].keys())
        summary['all_images'].update(stats['image_distribution'].keys())

        # Track date range
        if stats['timestamps']:
            earliest = min(stats['timestamps'])
            latest = max(stats['timestamps'])

            current_earliest = summary['date_range']['earliest']
            if current_earliest is None:
                current_earliest = earliest
            else:
                try:
                    from datetime import datetime
                    if isinstance(current_earliest, str):
                        current_earliest = datetime.fromisoformat(current_earliest)
                    if earliest < current_earliest:
                        current_earliest = earliest
                except (ValueError, TypeError):
                    pass

            current_latest = summary['date_range']['latest']
            if current_latest is None:
                current_latest = latest
            else:
                try:
                    from datetime import datetime
                    if isinstance(current_latest, str):
                        current_latest = datetime.fromisoformat(current_latest)
                    if latest > current_latest:
                        current_latest = latest
                except (ValueError, TypeError):
                    pass

            summary['date_range']['earliest'] = current_earliest.isoformat() if hasattr(current_earliest, 'isoformat') else str(current_earliest)
            summary['date_range']['latest'] = current_latest.isoformat() if hasattr(current_latest, 'isoformat') else str(current_latest)

    # Convert sets to sorted lists for JSON serialization
    summary['all_services'] = sorted(summary['all_services'])
    summary['all_namespaces'] = sorted(summary['all_namespaces'])

    return summary


def main():
    """Main execution function."""

    # Load categorized failures report
    report_path = Path('categorized-failures-report.json')
    if not report_path.exists():
        print(f"ERROR: {report_path} not found!")
        return 1

    print(f"Loading categorized failures from {report_path}...")
    with open(report_path, 'r') as f:
        data = json.load(f)

    failures = data['failures']
    print(f"Total failures: {len(failures)}")

    # Calculate category statistics
    print("\nCalculating category statistics...")
    category_stats = calculate_category_statistics(failures)

    # Enhance with percentages and image context
    print("Adding percentages and image context...")
    enhanced_stats = enhance_statistics_with_percentages(category_stats)

    # Generate summary statistics
    print("Generating summary statistics...")
    summary = generate_summary_statistics(category_stats)

    # Prepare output
    output = {
        'generated_at': datetime.now().isoformat(),
        'source_report': str(report_path),
        'summary': summary,
        'category_statistics': enhanced_stats,
    }

    # Write output
    output_path = Path('category-frequency-statistics.json')
    print(f"\nWriting statistics to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n✅ Statistics calculated successfully!")
    print(f"   Categories analyzed: {summary['total_categories']}")
    print(f"   Total categorized failures: {summary['total_categorized_failures']}")
    print(f"   Services affected: {len(summary['all_services'])}")
    print(f"   Date range: {summary['date_range']['earliest']} to {summary['date_range']['latest']}")

    return 0


if __name__ == '__main__':
    exit(main())
