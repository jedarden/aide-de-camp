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
from dataclasses import dataclass


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

    for file_path in json_files:
        print(f"Parsing: {file_path.name}")
        data = parse_json_file(file_path)

        if data is not None:
            record_count = count_records(data)
            total_records += record_count

            # Detect patterns in this file
            pattern_counts = detect_patterns_in_data(data)

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

    print(f"{'='*60}")

    return 0


if __name__ == '__main__':
    exit(main())
