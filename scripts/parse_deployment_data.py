#!/usr/bin/env python3
"""
Parse deployment JSON files from docs/research/deployment-data/.

Reads all .json files, loads them into Python data structures, and outputs
a summary of files processed and record counts.

Extended to include failure pattern detection and categorization.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List
from dataclasses import dataclass, field
from collections import Counter
from datetime import datetime, timezone


@dataclass
class PatternCategory:
    """Defines a failure pattern category with matching rules"""
    name: str
    description: str
    severity: str
    patterns: List[str]  # regex patterns
    keywords: List[str]  # simple keyword matches

    def matches(self, text: str) -> bool:
        """Check if this pattern matches the given text"""
        if not text:
            return False

        text_lower = text.lower()

        # Check regex patterns
        for pattern in self.patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    return True
            except re.error:
                continue

        # Check keyword matches
        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                return True

        return False


# Define the 6 pattern categories with regex patterns and keywords
PATTERN_CATEGORIES = [
    PatternCategory(
        name="ImagePullBackOff",
        description="Container image cannot be pulled (registry issues, authentication, missing image)",
        severity="high",
        patterns=[
            r'imagepullbackoff',
            r'pull.*error',
            r'failed.*pull.*image',
            r'image.*pull.*failed',
            r'errimage.*pull',
            r'back.*off.*pulling',
        ],
        keywords=[
            'imagepullbackoff',
            'image pull error',
            'failed to pull image',
            'registry error',
            'image not found',
            'authentication failed',
            'unauthorized',
        ]
    ),

    PatternCategory(
        name="CrashLoopBackOff",
        description="Pod repeatedly crashes and restarts (application errors, misconfiguration)",
        severity="critical",
        patterns=[
            r'crashloopbackoff',
            r'crash.*loop.*back',
            r'restart.*loop',
            r'container.*terminated.*exit.*code',
            r'back.*off.*restarting',
        ],
        keywords=[
            'crashloopbackoff',
            'crash loop',
            'restart loop',
            'container terminated',
            'exit code',
            'restarting',
            'back-off restarting',
        ]
    ),

    PatternCategory(
        name="OOMKilled",
        description="Container killed due to memory exhaustion (resource limits exceeded)",
        severity="high",
        patterns=[
            r'oomkilled',
            r'out.*of.*memory',
            r'memory.*exhausted',
            r'exceeded.*memory.*limit',
            r'kill.*memory',
        ],
        keywords=[
            'oomkilled',
            'out of memory',
            'memory exhausted',
            'oom',
            'memory limit exceeded',
            'killed due to memory',
        ]
    ),

    PatternCategory(
        name="Probe_failure",
        description="Readiness or liveness probe failures (health check issues)",
        severity="medium",
        patterns=[
            r'probe.*failed',
            r'readiness.*probe.*error',
            r'liveness.*probe.*error',
            r'health.*check.*failed',
            r'probe.*timeout',
            r'startup.*probe.*failed',
        ],
        keywords=[
            'readiness probe failed',
            'liveness probe failed',
            'health check failed',
            'probe timeout',
            'startup probe failed',
            'probe error',
        ]
    ),

    PatternCategory(
        name="Dependency_timeout",
        description="Deployment timeout due to dependency unavailability",
        severity="medium",
        patterns=[
            r'dependency.*timeout',
            r'service.*unavailable',
            r'connection.*timeout',
            r'depends.*not.*ready',
            r'waiting.*dependency',
            r'timeout.*waiting',
        ],
        keywords=[
            'dependency timeout',
            'service unavailable',
            'connection timeout',
            'dependency not ready',
            'waiting for dependency',
            'timeout waiting',
            'upstream timeout',
        ]
    ),

    PatternCategory(
        name="Other",
        description="Other failure patterns not matching standard categories",
        severity="unknown",
        patterns=[
            r'error',
            r'failed',
            r'failure',
            r'abnormal',
            r'terminated',
        ],
        keywords=[
            'error',
            'failed',
            'failure',
            'abnormal',
            'terminated',
            'warning',
        ]
    ),
]


def extract_failure_context(record: Dict[str, Any]) -> str:
    """
    Extract searchable text from a failure record for pattern matching.

    Args:
        record: A record that might contain failure information

    Returns:
        Combined searchable text string
    """
    searchable_texts = []

    # Common fields to search
    fields_to_search = [
        'outcome', 'reason', 'message', 'status', 'state',
        'event_type', 'notes', 'error', 'failure_type',
        'container_state', 'phase', 'failure_context',
        'pattern_type'
    ]

    for field in fields_to_search:
        if field in record and record[field]:
            searchable_texts.append(str(record[field]))

    # Also check nested structures
    if 'container_statuses' in record:
        for container in record['container_statuses']:
            if 'state' in container:
                searchable_texts.append(str(container['state']))
            if 'lastState' in container:
                searchable_texts.append(str(container['lastState']))
            if 'waiting' in container:
                searchable_texts.append(str(container['waiting']))
            if 'terminated' in container:
                searchable_texts.append(str(container['terminated']))

    return ' '.join(searchable_texts)


def categorize_failure(record: Dict[str, Any]) -> str:
    """
    Categorize a failure record into pattern types.

    Args:
        record: A record containing failure information

    Returns:
        Pattern category name (one of the 6 categories)
    """
    # Extract searchable text from the record
    combined_text = extract_failure_context(record)

    # Try to match against pattern categories (in order of specificity)
    for category in PATTERN_CATEGORIES:
        # Skip "Other" category - use it as fallback
        if category.name == "Other":
            continue

        if category.matches(combined_text):
            return category.name

    # If no specific pattern matched, use "Other"
    return "Other"


def detect_patterns_in_data(data: Any) -> Dict[str, int]:
    """
    Detect and count failure patterns in parsed JSON data.

    Args:
        data: Parsed JSON data

    Returns:
        Dictionary with pattern type counts
    """
    pattern_counts = {category.name: 0 for category in PATTERN_CATEGORIES}

    # Handle list of records
    if isinstance(data, list):
        for record in data:
            if isinstance(record, dict):
                pattern_type = categorize_failure(record)
                if pattern_type in pattern_counts:
                    pattern_counts[pattern_type] += 1

    # Handle dict with record containers
    elif isinstance(data, dict):
        # Check known record containers
        for key in ('records', 'items', 'results', 'workflows', 'deployments', 'failures', 'classified_failures', 'deployment_events'):
            if key in data and isinstance(data[key], list):
                for record in data[key]:
                    if isinstance(record, dict):
                        pattern_type = categorize_failure(record)
                        if pattern_type in pattern_counts:
                            pattern_counts[pattern_type] += 1

        # Also check for nested data structures
        for key, value in data.items():
            if isinstance(value, dict):
                # Recursively check nested dicts
                nested_counts = detect_patterns_in_data(value)
                for pattern_type, count in nested_counts.items():
                    pattern_counts[pattern_type] += count
            elif isinstance(value, list):
                # Recursively check nested lists
                for item in value:
                    if isinstance(item, (dict, list)):
                        nested_counts = detect_patterns_in_data(item)
                        for pattern_type, count in nested_counts.items():
                            pattern_counts[pattern_type] += count

    return pattern_counts


def parse_json_file(file_path: Path) -> Dict[str, Any] | None:
    """
    Parse a single JSON file.

    Args:
        file_path: Path to the JSON file

    Returns:
        Parsed JSON data as dict, or None if parsing fails
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"  ERROR: File not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"  ERROR: Invalid JSON in {file_path}: {e}")
        return None
    except Exception as e:
        print(f"  ERROR: Failed to read {file_path}: {e}")
        return None


@dataclass
class PatternStatistics:
    """Aggregated statistics for a single failure pattern category"""
    pattern_name: str
    frequency: int = 0
    timestamps: List[datetime] = field(default_factory=list)
    service_context: Counter = field(default_factory=Counter)
    image_context: Counter = field(default_factory=Counter)

    @property
    def min_time(self) -> datetime | None:
        """Get the earliest timestamp"""
        return min(self.timestamps) if self.timestamps else None

    @property
    def max_time(self) -> datetime | None:
        """Get the latest timestamp"""
        return max(self.timestamps) if self.timestamps else None

    @property
    def avg_time(self) -> datetime | None:
        """Get the average timestamp (as midpoint)"""
        if not self.timestamps:
            return None
        # For datetime, average is the midpoint between min and max
        # This is more meaningful than arithmetic mean of datetimes
        return self.min_time + (self.max_time - self.min_time) / 2 if self.min_time and self.max_time else None

    @property
    def top_services(self) -> List[tuple]:
        """Get top 5 services by frequency"""
        return self.service_context.most_common(5)

    @property
    def top_images(self) -> List[tuple]:
        """Get top 5 images by frequency"""
        return self.image_context.most_common(5)

    def to_dict(self) -> Dict[str, Any]:
        """Convert statistics to dictionary for output"""
        return {
            'pattern_name': self.pattern_name,
            'frequency': self.frequency,
            'time_distribution': {
                'min_timestamp': self.min_time.isoformat() if self.min_time else None,
                'max_timestamp': self.max_time.isoformat() if self.max_time else None,
                'avg_timestamp': self.avg_time.isoformat() if self.avg_time else None,
                'time_span_hours': (self.max_time - self.min_time).total_seconds() / 3600 if self.min_time and self.max_time else 0
            },
            'service_context': dict(self.service_context),
            'image_context': dict(self.image_context),
            'top_services': self.top_services,
            'top_images': self.top_images
        }


def extract_timestamp(record: Dict[str, Any]) -> datetime | None:
    """
    Extract timestamp from a record.

    Args:
        record: A record that might contain timestamp information

    Returns:
        datetime object or None if not found
    """
    timestamp_fields = [
        'timestamp', 'created_at', 'time', 'started_at', 'finished_at',
        'occurred_at', 'event_time', 'date', 'creationTimestamp', 'startTime'
    ]

    for field in timestamp_fields:
        if field in record and record[field]:
            value = record[field]
            try:
                # Handle ISO 8601 string
                if isinstance(value, str):
                    # Try parsing ISO 8601 format
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    # Ensure timezone-aware
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                # Handle Unix timestamp
                elif isinstance(value, (int, float)):
                    dt = datetime.fromtimestamp(value, tz=timezone.utc)
                    return dt
            except (ValueError, TypeError):
                continue

    return None


def extract_service_name(record: Dict[str, Any]) -> str | None:
    """
    Extract service name from a record.

    Args:
        record: A record that might contain service information

    Returns:
        Service name string or None if not found
    """
    service_fields = [
        'service', 'service_name', 'deployment', 'workload', 'job',
        'workflow', 'namespace', 'app', 'application', 'name'
    ]

    for field in service_fields:
        if field in record and record[field]:
            value = record[field]
            if isinstance(value, str):
                return value

    return None


def extract_image_info(record: Dict[str, Any]) -> str | None:
    """
    Extract image/version information from a record.

    Args:
        record: A record that might contain image information

    Returns:
        Image identifier string or None if not found
    """
    image_fields = ['image', 'container_image', 'image_name', 'version', 'tag']

    for field in image_fields:
        if field in record and record[field]:
            value = record[field]
            if isinstance(value, str):
                return value

    # Check nested structures
    if 'container_statuses' in record:
        for container in record['container_statuses']:
            if 'image' in container and container['image']:
                return container['image']
            if 'name' in container and 'imageID' in container:
                return f"{container['name']}@{container['imageID'][:12]}"

    if 'spec' in record and 'template' in record['spec']:
        if 'containers' in record['spec']['template']:
            for container in record['spec']['template']['containers']:
                if 'image' in container:
                    return container['image']

    return None


def collect_records_with_metadata(data: Any) -> List[Dict[str, Any]]:
    """
    Collect all records from parsed JSON data with pattern metadata.

    Args:
        data: Parsed JSON data

    Returns:
        List of records with pattern classification
    """
    records = []

    def process_record(record: Dict[str, Any]) -> None:
        """Process a single record and add to results"""
        timestamp = extract_timestamp(record)
        service = extract_service_name(record)
        image = extract_image_info(record)
        pattern_type = categorize_failure(record)

        records.append({
            'pattern_type': pattern_type,
            'timestamp': timestamp,
            'service': service,
            'image': image
        })

    # Handle list of records
    if isinstance(data, list):
        for record in data:
            if isinstance(record, dict):
                process_record(record)

    # Handle dict with record containers
    elif isinstance(data, dict):
        # Check known record containers
        for key in ('records', 'items', 'results', 'workflows', 'deployments',
                    'failures', 'classified_failures', 'deployment_events'):
            if key in data and isinstance(data[key], list):
                for record in data[key]:
                    if isinstance(record, dict):
                        process_record(record)

        # Also check for nested data structures
        for key, value in data.items():
            if isinstance(value, dict):
                # Recursively check nested dicts
                nested_records = collect_records_with_metadata(value)
                records.extend(nested_records)
            elif isinstance(value, list):
                # Recursively check nested lists
                for item in value:
                    if isinstance(item, (dict, list)):
                        nested_records = collect_records_with_metadata(item)
                        records.extend(nested_records)

    return records


def compute_pattern_statistics(records: List[Dict[str, Any]]) -> Dict[str, PatternStatistics]:
    """
    Compute statistics for each pattern category.

    Args:
        records: List of records with pattern metadata

    Returns:
        Dictionary mapping pattern names to statistics
    """
    # Initialize statistics for each pattern category
    stats = {
        category.name: PatternStatistics(pattern_name=category.name)
        for category in PATTERN_CATEGORIES
    }

    # Aggregate statistics
    for record in records:
        pattern_type = record['pattern_type']

        if pattern_type in stats:
            stats[pattern_type].frequency += 1

            if record['timestamp']:
                stats[pattern_type].timestamps.append(record['timestamp'])

            if record['service']:
                stats[pattern_type].service_context[record['service']] += 1

            if record['image']:
                stats[pattern_type].image_context[record['image']] += 1

    return stats


def print_statistics_summary(stats: Dict[str, PatternStatistics], total_records: int) -> None:
    """
    Print statistics summary to stdout.

    Args:
        stats: Dictionary mapping pattern names to statistics
        total_records: Total number of records processed
    """
    print(f"\n{'='*60}")
    print("DETAILED PATTERN STATISTICS")
    print(f"{'='*60}")

    for category in PATTERN_CATEGORIES:
        pattern_stats = stats.get(category.name)

        if not pattern_stats or pattern_stats.frequency == 0:
            continue

        print(f"\n{category.name} ({category.severity})")
        print(f"  Description: {category.description}")
        print(f"  Frequency: {pattern_stats.frequency} occurrences "
              f"({pattern_stats.frequency / total_records * 100:.1f}% of total)")

        if pattern_stats.timestamps:
            print(f"  Time Distribution:")
            print(f"    Earliest: {pattern_stats.min_time.isoformat()}")
            print(f"    Latest:   {pattern_stats.max_time.isoformat()}")
            if pattern_stats.avg_time:
                print(f"    Midpoint: {pattern_stats.avg_time.isoformat()}")

            time_span_hours = (pattern_stats.max_time - pattern_stats.min_time).total_seconds() / 3600
            print(f"    Time span: {time_span_hours:.1f} hours")

        if pattern_stats.top_services:
            print(f"  Top Services:")
            for service, count in pattern_stats.top_services:
                pct = (count / pattern_stats.frequency) * 100
                print(f"    {service}: {count} ({pct:.1f}%)")

        if pattern_stats.top_images:
            print(f"  Top Images:")
            for image, count in pattern_stats.top_images[:3]:  # Top 3 images
                pct = (count / pattern_stats.frequency) * 100
                print(f"    {image}: {count} ({pct:.1f}%)")

    print(f"\n{'='*60}")


def count_records(data: Any) -> int:
    """
    Count records in parsed JSON data.

    Args:
        data: Parsed JSON data (dict, list, or other)

    Returns:
        Number of records (0 for non-iterable top-level data)
    """
    if isinstance(data, list):
        return len(data)
    elif isinstance(data, dict):
        # If it's a dict with known record containers, count those
        for key in ('records', 'items', 'results', 'workflows', 'deployments', 'failures'):
            if key in data and isinstance(data[key], list):
                return len(data[key])
        # Otherwise count the dict itself as one record
        return 1
    else:
        return 0


def main():
    """Main entry point for parsing deployment JSON files."""
    # Directory containing deployment JSON files
    data_dir = Path('docs/research/deployment-data/')

    # Verify directory exists
    if not data_dir.exists():
        print(f"ERROR: Directory not found: {data_dir.absolute()}")
        return 1

    # Find all JSON files
    json_files = sorted(data_dir.glob('*.json'))

    if not json_files:
        print(f"No JSON files found in {data_dir.absolute()}")
        return 0

    print(f"Found {len(json_files)} JSON file(s) in {data_dir.absolute()}\n")

    # Parse each file
    results = []
    total_records = 0
    errors = 0

    # Initialize pattern counts across all files
    total_pattern_counts = {category.name: 0 for category in PATTERN_CATEGORIES}

    # Collect all records with metadata for statistical analysis
    all_records_with_metadata = []

    for file_path in json_files:
        print(f"Parsing: {file_path.name}")
        data = parse_json_file(file_path)

        if data is not None:
            record_count = count_records(data)
            total_records += record_count

            # Detect patterns in this file
            pattern_counts = detect_patterns_in_data(data)

            # Collect records with metadata for statistics
            records_with_metadata = collect_records_with_metadata(data)
            all_records_with_metadata.extend(records_with_metadata)

            # Aggregate pattern counts
            for pattern_type, count in pattern_counts.items():
                total_pattern_counts[pattern_type] += count

            results.append({
                'file': file_path.name,
                'records': record_count,
                'size_kb': file_path.stat().st_size / 1024,
                'status': 'ok',
                'pattern_counts': pattern_counts
            })

            # Show file-level pattern counts if any patterns detected
            total_patterns = sum(pattern_counts.values())
            if total_patterns > 0:
                print(f"  ✓ {record_count} record(s), {file_path.stat().st_size / 1024:.1f} KB")
                print(f"  Patterns detected: {total_patterns}")
                for pattern_type, count in pattern_counts.items():
                    if count > 0:
                        print(f"    - {pattern_type}: {count}")
            else:
                print(f"  ✓ {record_count} record(s), {file_path.stat().st_size / 1024:.1f} KB (no patterns detected)")
        else:
            errors += 1
            results.append({
                'file': file_path.name,
                'records': 0,
                'size_kb': file_path.stat().st_size / 1024,
                'status': 'error',
                'pattern_counts': {category.name: 0 for category in PATTERN_CATEGORIES}
            })

    # Compute pattern statistics
    pattern_statistics = compute_pattern_statistics(all_records_with_metadata)

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Files processed: {len(json_files)}")
    print(f"Successful: {len(json_files) - errors}")
    print(f"Errors: {errors}")
    print(f"Total records: {total_records}")
    print(f"Total data size: {sum(r['size_kb'] for r in results):.1f} KB")

    # Print pattern detection summary
    total_patterns_detected = sum(total_pattern_counts.values())
    print(f"\n{'='*60}")
    print("FAILURE PATTERN DETECTION")
    print(f"{'='*60}")
    print(f"Total patterns detected: {total_patterns_detected}")
    print(f"\nPattern Type Counts:")

    # Print pattern categories in order
    for category in PATTERN_CATEGORIES:
        count = total_pattern_counts[category.name]
        percentage = (count / total_patterns_detected * 100) if total_patterns_detected > 0 else 0
        print(f"  {category.name:20s}: {count:4d} ({percentage:5.1f}%)")
        print(f"    Severity: {category.severity}")
        print(f"    Description: {category.description}")

    # Print detailed statistics
    print_statistics_summary(pattern_statistics, total_patterns_detected)

    # Output structured aggregation data as Python dict
    aggregation_output = {
        'summary': {
            'files_processed': len(json_files),
            'successful': len(json_files) - errors,
            'errors': errors,
            'total_records': total_records,
            'total_patterns_detected': total_patterns_detected
        },
        'pattern_statistics': {
            pattern_name: stats.to_dict()
            for pattern_name, stats in pattern_statistics.items()
        }
    }

    # Optionally write to JSON file for further analysis
    output_file = Path('docs/research/pattern_aggregations.json')
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            # Convert datetime objects to ISO format for JSON serialization
            json.dump(aggregation_output, f, indent=2, default=str)
        print(f"\nStructured aggregations written to: {output_file}")
    except Exception as e:
        print(f"\nWarning: Could not write aggregations to file: {e}")

    print(f"{'='*60}")

    return 0


if __name__ == '__main__':
    exit(main())
