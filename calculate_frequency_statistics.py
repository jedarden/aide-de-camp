#!/usr/bin/env python3
"""
Calculate frequency statistics by pattern category for categorized failures.
Extracts service distribution, image/version context, and temporal patterns.
"""

import json
from datetime import datetime
from collections import defaultdict, Counter
import re


def extract_service_from_failure(failure):
    """Extract service name from failure record."""
    # Try multiple fields that might contain service info
    if 'namespace' in failure:
        return failure['namespace']
    if 'pod_name' in failure:
        # Extract service from pod name (e.g., pbx-web-5ff68464d-mkn8n -> pbx-web)
        pod_name = failure['pod_name']
        if '-' in pod_name:
            parts = pod_name.split('-')
            # Pod names are typically {service}-{replicaset}-{random}
            # Try to find the service part
            if len(parts) >= 2:
                return '-'.join(parts[:-2]) if len(parts) > 2 else parts[0]
        return pod_name
    if '_source_file' in failure:
        # Extract from source file path
        source_file = failure['_source_file']
        if '/' in source_file:
            return source_file.split('/')[-1].replace('.jsonl', '').replace('-30day', '')
    return 'unknown'


def extract_image_version(failure):
    """Extract image and version from failure record."""
    if 'image' in failure:
        image = failure['image']
        # Parse version from image tag
        if ':' in image:
            image_name, version = image.rsplit(':', 1)
            return {'image': image_name, 'version': version}
        return {'image': image, 'version': 'unknown'}
    return None


def extract_timestamp(failure):
    """Extract timestamp from failure record."""
    # Try various timestamp fields
    for field in ['timestamp', 'data_collection_timestamp', 'occurred_at', 'created_at']:
        if field in failure and failure[field]:
            try:
                timestamp_str = failure[field]
                # Handle various timestamp formats
                if isinstance(timestamp_str, str):
                    # Try ISO 8601 format
                    if 'T' in timestamp_str:
                        return timestamp_str
                    # Try other formats
                    return timestamp_str
            except Exception:
                pass

    # Try to extract from message field
    if 'message' in failure:
        message = failure['message']
        # Look for ISO timestamp at start of message
        timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2}T[\d:\.]+[+-]?\d{2}:\d{2})', message)
        if timestamp_match:
            return timestamp_match.group(1)

    return 'unknown'


def categorize_by_day(timestamp_str):
    """Categorize timestamp into day bucket."""
    if timestamp_str == 'unknown':
        return 'unknown'

    try:
        # Parse ISO 8601 timestamp
        # Handle formats like: 2026-07-28T13:36:40.095001455-04:00
        if 'T' in timestamp_str:
            # Extract date part
            date_part = timestamp_str.split('T')[0]
            return date_part
    except Exception:
        pass

    return 'unknown'


def calculate_statistics(categorized_failures):
    """Calculate comprehensive statistics by pattern category."""

    # Initialize data structures
    category_stats = defaultdict(lambda: {
        'total_count': 0,
        'services': Counter(),
        'images': Counter(),
        'versions': Counter(),
        'daily_distribution': defaultdict(int),
        'severity': None,
        'description': None,
        'examples': []
    })

    # Process each failure
    for failure in categorized_failures:
        category = failure.get('pattern_category', 'uncategorized')

        # Skip uncategorized for detailed analysis
        if category == 'uncategorized':
            continue

        # Extract service
        service = extract_service_from_failure(failure)
        category_stats[category]['services'][service] += 1

        # Extract image/version
        image_info = extract_image_version(failure)
        if image_info:
            category_stats[category]['images'][image_info['image']] += 1
            category_stats[category]['versions'][image_info['version']] += 1

        # Extract and categorize timestamp
        timestamp = extract_timestamp(failure)
        day = categorize_by_day(timestamp)
        category_stats[category]['daily_distribution'][day] += 1

        # Increment total count
        category_stats[category]['total_count'] += 1

        # Store a few examples
        if len(category_stats[category]['examples']) < 5:
            category_stats[category]['examples'].append({
                'service': service,
                'image': image_info['image'] if image_info else 'unknown',
                'version': image_info['version'] if image_info else 'unknown',
                'timestamp': timestamp,
                'day': day,
                'error_type': failure.get('error_type', 'unknown'),
                'message': failure.get('message', 'N/A')[:200]  # Truncate long messages
            })

    # Convert to final output format
    result = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'total_categorized_failures': sum(cat['total_count'] for cat in category_stats.values()),
        'categories': {}
    }

    # Convert defaultdicts to regular dicts and sort
    for category, stats in sorted(category_stats.items()):
        # Sort distributions by count (descending)
        top_services = dict(stats['services'].most_common(10))
        top_images = dict(stats['images'].most_common(10))
        top_versions = dict(stats['versions'].most_common(10))

        # Sort daily distribution by date
        sorted_days = dict(sorted(stats['daily_distribution'].items()))

        result['categories'][category] = {
            'total_count': stats['total_count'],
            'service_distribution': top_services,
            'image_distribution': top_images,
            'version_distribution': top_versions,
            'daily_distribution': sorted_days,
            'time_span': calculate_time_span(sorted_days),
            'examples': stats['examples']
        }

    return result


def calculate_time_span(daily_distribution):
    """Calculate time span from daily distribution."""
    valid_days = [day for day in daily_distribution.keys() if day != 'unknown']
    if not valid_days:
        return {'start': 'unknown', 'end': 'unknown', 'days': 0}

    return {
        'start': min(valid_days),
        'end': max(valid_days),
        'days': (len(set(valid_days)))
    }


def main():
    """Main function to calculate and output statistics."""
    print("Loading categorized failures data...")

    # Load the categorized failures report
    with open('categorized-failures-report.json', 'r') as f:
        data = json.load(f)

    failures = data.get('failures', [])
    print(f"Loaded {len(failures)} failure records")

    print("Calculating frequency statistics by pattern category...")
    stats = calculate_statistics(failures)

    # Output results
    output_file = 'pattern-frequency-statistics.json'
    with open(output_file, 'w') as f:
        json.dump(stats, f, indent=2)

    print(f"✓ Statistics written to {output_file}")

    # Print summary
    print("\n" + "="*60)
    print("FREQUENCY STATISTICS SUMMARY")
    print("="*60)
    print(f"Total categorized failures analyzed: {stats['total_categorized_failures']}")
    print(f"Pattern categories found: {len(stats['categories'])}")
    print()

    for category, cat_stats in sorted(stats['categories'].items(),
                                     key=lambda x: x[1]['total_count'],
                                     reverse=True):
        print(f"\n{category}:")
        print(f"  Total count: {cat_stats['total_count']}")
        print(f"  Time span: {cat_stats['time_span']['start']} to {cat_stats['time_span']['end']} ({cat_stats['time_span']['days']} days)")
        print(f"  Top services: {list(cat_stats['service_distribution'].keys())[:5]}")
        print(f"  Top images: {list(cat_stats['image_distribution'].keys())[:3]}")
        print(f"  Top versions: {list(cat_stats['version_distribution'].keys())[:3]}")

    print("\n" + "="*60)


if __name__ == '__main__':
    main()