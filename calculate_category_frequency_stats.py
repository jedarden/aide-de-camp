#!/usr/bin/env python3
"""
Calculate per-category frequency statistics for pattern categories.

For each pattern category, calculates:
- Total occurrence count
- Distribution by service (count and percentage per service)
- Image/version context (unique image tags with counts)

Acceptance Criteria:
1. For each pattern category: calculate total count, service distribution, image context
2. Structure output as nested dicts with counts and percentages
3. Handle edge cases: categories with no occurrences, missing fields
4. Output intermediate statistics dataset
"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any


def load_validated_dataset(filepath: Path) -> Dict:
    """Load validated failures dataset."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return {}


def extract_service_name(record: Dict) -> str:
    """Extract service name from record, handling missing fields."""
    # First try the direct service field
    if record.get('service') and isinstance(record['service'], str):
        return record['service']

    # Try namespace (direct field)
    if record.get('namespace') and isinstance(record['namespace'], str):
        return record['namespace']

    # Try to extract from _original data
    original = record.get('_original', {})

    # Try namespace in original
    if original.get('namespace'):
        return original['namespace']

    # Try pod_name pattern
    pod_name = original.get('pod_name', '') or record.get('pod_name', '')
    if pod_name:
        # Extract service from pod name (e.g., "pbx-web-5ff68464d-mkn8n" -> "pbx-web")
        parts = pod_name.split('-')
        if len(parts) >= 2:
            # Common pattern: service-name-hash-random
            # Take first two parts as service name
            return f"{parts[0]}-{parts[1]}"

    # Try source file
    source_file = original.get('_source_file', '') or record.get('_source_file', '')
    if 'pbx-web' in source_file:
        return 'pbx-web'
    elif 'whisper-stt' in source_file:
        return 'whisper-stt'

    return 'unknown'


def extract_image_tag(record: Dict) -> str:
    """Extract image tag from record, handling missing fields."""
    # First try the direct image_tag field
    if record.get('image_tag'):
        return str(record['image_tag'])

    # Try direct image field
    if record.get('image'):
        return str(record['image'])

    # Try container_image field
    if record.get('container_image'):
        return str(record['container_image'])

    # Try to extract from _original data
    original = record.get('_original', {})

    # Try image_tag in original
    if original.get('image_tag'):
        return str(original['image_tag'])

    # Try direct image field in original
    if original.get('image'):
        return str(original['image'])

    # Try container_image in original
    if original.get('container_image'):
        return str(original['container_image'])

    # Extract from source file name for log-based records
    source_file = record.get('_source_file', '') or original.get('_source_file', '')

    if source_file:
        # This is a log file record - infer service context from filename
        if 'pbx-web' in source_file:
            return 'pbx-web-logs'
        elif 'whisper-stt' in source_file:
            return 'whisper-stt-logs'
        elif 'whisper-openai' in source_file:
            return 'whisper-openai-logs'
        elif 'whisper' in source_file.lower():
            return 'whisper-logs'
        # Generic log source
        if 'logs' in source_file or '.jsonl' in source_file:
            return 'container-logs'

    # For describe/events sources, try to infer from pod name
    if record.get('pod'):
        pod_name = record['pod']
        if 'pbx-web' in pod_name:
            return 'pbx-web-pod'
        elif 'whisper' in pod_name.lower():
            return 'whisper-pod'
        return f'pod-{pod_name[:10]}'

    # Check data sources field if available
    data_sources = record.get('data_sources', []) or original.get('data_sources', [])
    if data_sources and ('kubectl logs' in data_sources or 'container_logs' in str(data_sources)):
        return 'container-logs'

    return 'unknown'


def calculate_category_frequency_stats(categorized_data: Dict) -> Dict[str, Any]:
    """Calculate frequency statistics for each pattern category."""

    failures = categorized_data.get('failures', [])
    categories_metadata = categorized_data.get('categories', {})

    # Initialize output structure
    stats_output = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_dataset': 'categorized-failures-report.json',
        'total_categories_analyzed': 0,
        'categories': {}
    }

    # Group failures by pattern_category using defaultdict for efficiency
    from collections import defaultdict
    category_failures = defaultdict(list)

    for failure in failures:
        category = failure.get('pattern_category', 'uncategorized')
        category_failures[category].append(failure)

    # Process each category
    for category_name, category_meta in categories_metadata.items():
        if category_name == 'uncategorized':
            continue  # Skip uncategorized as per task requirements

        failures_in_category = category_failures.get(category_name, [])

        # Handle edge case: category with no occurrences
        if not failures_in_category:
            stats_output['categories'][category_name] = {
                'total_occurrences': 0,
                'service_distribution': {},
                'image_distribution': {},
                'description': category_meta.get('description', ''),
                'note': 'No failures found for this category'
            }
            continue

        # Calculate statistics using Counter for efficiency
        service_counter = Counter()
        image_counter = Counter()

        for failure in failures_in_category:
            # Extract and count service
            service = extract_service_name(failure)
            service_counter[service] += 1

            # Extract and count image tag
            image_tag = extract_image_tag(failure)
            image_counter[image_tag] += 1

        # Calculate totals
        total_occurrences = len(failures_in_category)

        # Build service distribution with percentages
        service_distribution = {}
        for service, count in service_counter.most_common():
            percentage = (count / total_occurrences * 100) if total_occurrences > 0 else 0
            service_distribution[service] = {
                'count': count,
                'percentage': round(percentage, 2)
            }

        # Build image distribution with percentages
        image_distribution = {}
        for image_tag, count in image_counter.most_common():
            percentage = (count / total_occurrences * 100) if total_occurrences > 0 else 0
            image_distribution[image_tag] = {
                'count': count,
                'percentage': round(percentage, 2)
            }

        # Store category statistics
        stats_output['categories'][category_name] = {
            'description': category_meta.get('description', ''),
            'severity': category_meta.get('severity', ''),
            'total_occurrences': total_occurrences,
            'service_distribution': service_distribution,
            'image_distribution': image_distribution
        }

        stats_output['total_categories_analyzed'] += 1

    # Add summary statistics
    total_all_occurrences = sum(
        cat_stats['total_occurrences']
        for cat_stats in stats_output['categories'].values()
    )

    stats_output['summary'] = {
        'total_occurrences_all_categories': total_all_occurrences,
        'categories_analyzed': list(stats_output['categories'].keys())
    }

    return stats_output


def main():
    """Main execution."""

    # Define paths
    base_dir = Path("/home/coding/aide-de-camp")
    input_path = base_dir / "categorized-failures-report.json"
    output_path = base_dir / "category-frequency-statistics.json"

    print("Loading categorized failures report...")
    categorized_data = load_validated_dataset(input_path)

    if not categorized_data:
        print(f"Error: Could not load categorized failures from {input_path}")
        return 1

    total_failures = len(categorized_data.get('failures', []))
    print(f"  Total failures in dataset: {total_failures}")
    print(f"  Pattern categories: {list(categorized_data.get('categories', {}).keys())}")

    print("\nCalculating per-category frequency statistics...")
    stats = calculate_category_frequency_stats(categorized_data)

    print(f"Writing statistics to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(stats, f, indent=2)

    print("\n" + "=" * 60)
    print("PER-CATEGORY FREQUENCY STATISTICS SUMMARY")
    print("=" * 60)

    print(f"\nCategories analyzed: {stats['total_categories_analyzed']}")
    print(f"Total occurrences across all categories: {stats['summary']['total_occurrences_all_categories']}")

    print("\n" + "-" * 60)
    print("CATEGORY BREAKDOWN")
    print("-" * 60)

    for category_name, cat_stats in sorted(
        stats['categories'].items(),
        key=lambda x: x[1]['total_occurrences'],
        reverse=True
    ):
        print(f"\n{category_name}:")
        print(f"  Total occurrences: {cat_stats['total_occurrences']}")

        if cat_stats['service_distribution']:
            print(f"  Service distribution:")
            for service, svc_stats in list(cat_stats['service_distribution'].items())[:5]:
                print(f"    {service}: {svc_stats['count']} ({svc_stats['percentage']}%)")

        if cat_stats['image_distribution']:
            print(f"  Image distribution (top 5):")
            for image, img_stats in list(cat_stats['image_distribution'].items())[:5]:
                print(f"    {image}: {img_stats['count']} ({img_stats['percentage']}%)")

    print(f"\n✅ Statistics saved to {output_path}")
    return 0


if __name__ == "__main__":
    exit(main())
