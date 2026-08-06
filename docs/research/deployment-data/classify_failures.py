#!/usr/bin/env python3
"""
Failure Pattern Classification System

Categorizes deployment failures into pattern types:
- ImagePullBackOff
- CrashLoopBackOff
- OOMKilled
- Probe failure
- Dependency timeout
- Other
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict


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


def classify_failure(failure_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify a single failure record into pattern types.

    Args:
        failure_record: A record containing failure information

    Returns:
        The same record with pattern_type field added
    """
    # Extract searchable text from the failure record
    searchable_texts = []

    # Common fields to search
    fields_to_search = [
        'outcome', 'reason', 'message', 'status', 'state',
        'event_type', 'notes', 'error', 'failure_type',
        'container_state', 'phase', 'reason'
    ]

    for field in fields_to_search:
        if field in failure_record and failure_record[field]:
            searchable_texts.append(str(failure_record[field]))

    # Also check nested structures
    if 'container_statuses' in failure_record:
        for container in failure_record['container_statuses']:
            if 'state' in container:
                searchable_texts.append(str(container['state']))
            if 'lastState' in container:
                searchable_texts.append(str(container['lastState']))
            if 'waiting' in container:
                searchable_texts.append(str(container['waiting']))
            if 'terminated' in container:
                searchable_texts.append(str(container['terminated']))

    # Combine all searchable text
    combined_text = ' '.join(searchable_texts)

    # Try to match against pattern categories (in order of specificity)
    pattern_type = None
    matched_pattern = None

    for i, category in enumerate(PATTERN_CATEGORIES):
        # Skip "Other" category for now - use it as fallback
        if category.name == "Other":
            continue

        if category.matches(combined_text):
            pattern_type = category.name
            matched_pattern = category
            break

    # If no specific pattern matched, use "Other"
    if pattern_type is None:
        pattern_type = "Other"
        matched_pattern = PATTERN_CATEGORIES[-1]  # Last one is "Other"

    # Create the classified record
    classified = failure_record.copy()
    classified['pattern_type'] = pattern_type
    classified['pattern_severity'] = matched_pattern.severity
    classified['pattern_description'] = matched_pattern.description

    return classified


def extract_failure_records(data: Dict) -> List[Dict[str, Any]]:
    """
    Extract failure records from the parsed deployment data.

    Args:
        data: The parsed-data.json content

    Returns:
        List of failure records with contextual information
    """
    failure_records = []

    # Process deployment records
    if 'deployment_records' in data:
        for deployment_group in data['deployment_records']:
            source = deployment_group.get('source', 'unknown')
            deployment_data = deployment_group.get('data', {})

            # Check deployment events
            if 'deployment_events_last_30_days' in deployment_data:
                for event in deployment_data['deployment_events_last_30_days']:
                    outcome = event.get('outcome', '')
                    if outcome not in ['success', 'success', 'rolled_back']:
                        record = event.copy()
                        record['source_file'] = source
                        record['service'] = deployment_data.get('metadata', {}).get('service', 'unknown')
                        record['failure_context'] = f"deployment_event: {outcome}"
                        failure_records.append(record)
                    elif outcome == 'rolled_back':
                        # Rollbacks are also interesting failures
                        record = event.copy()
                        record['source_file'] = source
                        record['service'] = deployment_data.get('metadata', {}).get('service', 'unknown')
                        record['failure_context'] = "deployment_rollback"
                        failure_records.append(record)

    # Process raw data metrics for failure modes
    if 'raw_data' in data:
        for service_name, metrics_file in {
            'pbx-web': 'pbx-web-metrics.json',
            'whisper-stt': 'whisper-stt-metrics.json'
        }.items():
            if metrics_file in data['raw_data']:
                metrics = data['raw_data'][metrics_file]

                # Check failure modes
                if 'failure_modes' in metrics:
                    for failure_mode, count in metrics['failure_modes'].items():
                        if count > 0:
                            record = {
                                'service': service_name,
                                'source_file': metrics_file,
                                'failure_mode': failure_mode,
                                'count': count,
                                'failure_context': f"failure_mode: {failure_mode}",
                                'timestamp': metrics.get('query_window', {}).get('end', '')
                            }
                            failure_records.append(record)

                # Check events
                if 'events' in metrics:
                    events = metrics['events']
                    if events.get('failed', 0) > 0:
                        for event in events.get('timeline', []):
                            if event.get('type') in ['Error', 'Warning']:
                                record = event.copy()
                                record['service'] = service_name
                                record['source_file'] = metrics_file
                                record['failure_context'] = f"event: {event.get('type')}"
                                failure_records.append(record)

    return failure_records


def main():
    """Main classification function"""
    # Load parsed data
    parsed_file = Path('/home/coding/aide-de-camp/docs/research/deployment-data/parsed-data.json')

    if not parsed_file.exists():
        print(f"Error: {parsed_file} not found")
        return

    with open(parsed_file, 'r') as f:
        data = json.load(f)

    # Extract failure records
    failure_records = extract_failure_records(data)

    print(f"Found {len(failure_records)} failure records to classify")

    # Classify each failure record
    classified_failures = []
    for record in failure_records:
        classified = classify_failure(record)
        classified_failures.append(classified)

    # Create output structure
    output = {
        'metadata': {
            'generated_at': '2026-08-06T22:56:28.820259Z',
            'pattern_categories': [cat.name for cat in PATTERN_CATEGORIES],
            'total_failures_classified': len(classified_failures),
            'source_data': 'parsed-data.json'
        },
        'pattern_definitions': [
            {
                'name': cat.name,
                'description': cat.description,
                'severity': cat.severity,
                'patterns_count': len(cat.patterns),
                'keywords_count': len(cat.keywords)
            }
            for cat in PATTERN_CATEGORIES
        ],
        'classified_failures': classified_failures,
        'summary': {
            'by_pattern_type': {},
            'by_service': {},
            'by_severity': {}
        }
    }

    # Generate summary statistics
    for failure in classified_failures:
        pattern_type = failure.get('pattern_type', 'Unknown')
        service = failure.get('service', 'unknown')
        severity = failure.get('pattern_severity', 'unknown')

        output['summary']['by_pattern_type'][pattern_type] = \
            output['summary']['by_pattern_type'].get(pattern_type, 0) + 1
        output['summary']['by_service'][service] = \
            output['summary']['by_service'].get(service, 0) + 1
        output['summary']['by_severity'][severity] = \
            output['summary']['by_severity'].get(severity, 0) + 1

    # Save to output file
    output_file = Path('/home/coding/aide-de-camp/docs/research/deployment-data/classified-failures.json')
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Classification saved to {output_file}")
    print(f"Summary: {output['summary']}")


if __name__ == '__main__':
    main()
