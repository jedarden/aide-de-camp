#!/usr/bin/env python3
"""
Comprehensive validation script for pod-logs-index.jsonl.

Validates the generated JSONL file against the schema requirements specified
in pod-logs-schema.md, including all 28 fields across 5 categories.
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict


def load_jsonl(file_path: str) -> List[Dict[str, Any]]:
    """Load JSONL file and return list of entries."""
    entries = []
    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Error parsing line {line_num}: {e}")
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        return []
    return entries


def validate_timestamp_format(timestamp: Optional[str], allow_date_only: bool = False) -> bool:
    """Validate ISO 8601 timestamp format."""
    if timestamp is None:
        return True

    # Try ISO 8601 with Z suffix
    try:
        datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
        return True
    except ValueError:
        pass

    # Try ISO 8601 with microseconds and Z suffix
    try:
        datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
        return True
    except ValueError:
        pass

    # Try date only (YYYY-MM-DD) if allowed
    if allow_date_only:
        try:
            datetime.strptime(timestamp, '%Y-%m-%d')
            return True
        except ValueError:
            pass

    return False


def validate_dns_subdomain(name: Optional[str]) -> bool:
    """Validate Kubernetes DNS subdomain format."""
    if name is None:
        return True
    # DNS subdomain regex: [a-z0-9]([-a-z0-9]*[a-z0-9])?
    pattern = r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
    return bool(re.match(pattern, name))


def validate_container_image(image: Optional[str]) -> bool:
    """Validate container image reference format."""
    if image is None:
        return True
    # Container image regex: ([^/]+/)?[^:]+(:[^:]+)?
    pattern = r'^([^/]+/)?[^:]+(:[^:]+)?$'
    return bool(re.match(pattern, image))


def validate_entry(entry: Dict[str, Any], line_num: int) -> List[Dict[str, Any]]:
    """Validate a single JSONL entry against schema requirements."""
    errors = []
    warnings = []

    # Check required top-level categories
    required_categories = ['pod_identification', 'log_file_metadata', 'analysis_metadata', 'pattern_detection', 'temporal_boundaries']
    for category in required_categories:
        if category not in entry:
            errors.append(f"Missing required category: {category}")

    if errors:
        return errors  # Critical errors, stop validation

    # Validate pod_identification (8 fields)
    pod_id = entry['pod_identification']
    required_pod_fields = ['pod_name', 'namespace', 'pod_phase', 'restart_count', 'creation_timestamp',
                          'deletion_timestamp', 'container_image', 'node_name']
    for field in required_pod_fields:
        if field not in pod_id:
            errors.append(f"Missing pod_identification.{field}")

    # Type validations
    if not validate_dns_subdomain(pod_id.get('pod_name')):
        errors.append(f"Invalid pod_name format: {pod_id.get('pod_name')}")

    if not validate_dns_subdomain(pod_id.get('namespace')):
        errors.append(f"Invalid namespace format: {pod_id.get('namespace')}")

    valid_phases = ['Pending', 'Running', 'Succeeded', 'Failed', 'Unknown']
    if pod_id.get('pod_phase') not in valid_phases:
        errors.append(f"Invalid pod_phase: {pod_id.get('pod_phase')}")

    if not isinstance(pod_id.get('restart_count'), int) or pod_id.get('restart_count') < 0:
        errors.append(f"Invalid restart_count: {pod_id.get('restart_count')}")

    if not validate_timestamp_format(pod_id.get('creation_timestamp')):
        errors.append(f"Invalid creation_timestamp format: {pod_id.get('creation_timestamp')}")

    if not validate_timestamp_format(pod_id.get('deletion_timestamp')):
        errors.append(f"Invalid deletion_timestamp format: {pod_id.get('deletion_timestamp')}")

    if not validate_container_image(pod_id.get('container_image')):
        errors.append(f"Invalid container_image format: {pod_id.get('container_image')}")

    # Validate log_file_metadata (5 fields)
    log_meta = entry['log_file_metadata']
    required_log_fields = ['log_file_path', 'log_size_bytes', 'log_line_count', 'collection_date', 'log_type']
    for field in required_log_fields:
        if field not in log_meta:
            errors.append(f"Missing log_file_metadata.{field}")

    if not isinstance(log_meta.get('log_size_bytes'), int) or log_meta.get('log_size_bytes') < 0:
        errors.append(f"Invalid log_size_bytes: {log_meta.get('log_size_bytes')}")

    if log_meta.get('log_line_count') is not None:
        if not isinstance(log_meta.get('log_line_count'), int) or log_meta.get('log_line_count') < 0:
            errors.append(f"Invalid log_line_count: {log_meta.get('log_line_count')}")

    if not validate_timestamp_format(log_meta.get('collection_date'), allow_date_only=True):
        errors.append(f"Invalid collection_date format: {log_meta.get('collection_date')}")

    valid_log_types = ['current', 'previous', 'stderr', None]
    if log_meta.get('log_type') not in valid_log_types:
        errors.append(f"Invalid log_type: {log_meta.get('log_type')}")

    # Validate analysis_metadata (2 fields)
    analysis_meta = entry['analysis_metadata']
    required_analysis_fields = ['analysis_file_path', 'analysis_date']
    for field in required_analysis_fields:
        if field not in analysis_meta:
            errors.append(f"Missing analysis_metadata.{field}")

    if not validate_timestamp_format(analysis_meta.get('analysis_date')):
        errors.append(f"Invalid analysis_date format: {analysis_meta.get('analysis_date')}")

    # Validate pattern_detection (4 categories × 3 fields = 12)
    pattern_det = entry['pattern_detection']
    required_pattern_categories = ['startup', 'oom_kill', 'error', 'performance']
    for category in required_pattern_categories:
        if category not in pattern_det:
            errors.append(f"Missing pattern_detection.{category}")
        else:
            cat_data = pattern_det[category]
            required_subfields = ['count', 'timestamps', 'samples']
            for subfield in required_subfields:
                if subfield not in cat_data:
                    errors.append(f"Missing pattern_detection.{category}.{subfield}")

            # Validate array consistency
            count = cat_data.get('count', 0)
            timestamps = cat_data.get('timestamps', [])
            samples = cat_data.get('samples', [])

            if not isinstance(count, int) or count < 0:
                errors.append(f"Invalid pattern_detection.{category}.count: {count}")

            if not isinstance(timestamps, list):
                errors.append(f"pattern_detection.{category}.timestamps must be an array")
            elif len(timestamps) != count:
                errors.append(f"pattern_detection.{category}.timestamps length ({len(timestamps)}) != count ({count})")

            if not isinstance(samples, list):
                errors.append(f"pattern_detection.{category}.samples must be an array")
            elif len(samples) != count:
                errors.append(f"pattern_detection.{category}.samples length ({len(samples)}) != count ({count})")

    # Validate temporal_boundaries (4 fields)
    temp_bound = entry['temporal_boundaries']
    required_temp_fields = ['first_log_entry', 'last_log_entry', 'analysis_date', 'collection_date']
    for field in required_temp_fields:
        if field not in temp_bound:
            errors.append(f"Missing temporal_boundaries.{field}")

    if not validate_timestamp_format(temp_bound.get('first_log_entry')):
        errors.append(f"Invalid first_log_entry format: {temp_bound.get('first_log_entry')}")

    if not validate_timestamp_format(temp_bound.get('last_log_entry')):
        errors.append(f"Invalid last_log_entry format: {temp_bound.get('last_log_entry')}")

    if not validate_timestamp_format(temp_bound.get('analysis_date')):
        errors.append(f"Invalid temporal_boundaries.analysis_date format: {temp_bound.get('analysis_date')}")

    if not validate_timestamp_format(temp_bound.get('collection_date'), allow_date_only=True):
        errors.append(f"Invalid temporal_boundaries.collection_date format: {temp_bound.get('collection_date')}")

    return errors


def validate_completeness(entries: List[Dict[str, Any]], metadata_file: str) -> Dict[str, Any]:
    """Validate that all pod logs from metadata are represented in the index."""
    # Load original metadata
    try:
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
    except Exception as e:
        return {'error': f'Failed to load metadata: {e}'}

    if not isinstance(metadata, list):
        metadata = []

    # Get unique log file paths from metadata
    expected_logs = set()
    for entry in metadata:
        log_path = entry.get('log_file_path')
        if log_path:
            expected_logs.add(log_path)

    # Get log file paths from index
    indexed_logs = set()
    for entry in entries:
        log_path = entry.get('log_file_metadata', {}).get('log_file_path', '')
        # Remove 'research/' prefix if present for comparison
        if log_path.startswith('research/'):
            log_path = log_path[9:]
        indexed_logs.add(log_path)

    missing_logs = expected_logs - indexed_logs
    extra_logs = indexed_logs - expected_logs

    return {
        'expected_count': len(expected_logs),
        'indexed_count': len(indexed_logs),
        'missing_logs': list(missing_logs),
        'extra_logs': list(extra_logs),
        'complete': len(missing_logs) == 0
    }


def main():
    """Main entry point for validation script."""
    if len(sys.argv) < 2:
        print("Usage: validate_pod_logs_schema.py <jsonl_file> [metadata_file]")
        print("\nArguments:")
        print("  jsonl_file     Path to JSONL file to validate")
        print("  metadata_file  Optional path to metadata JSON for completeness check")
        sys.exit(1)

    jsonl_file = sys.argv[1]
    metadata_file = sys.argv[2] if len(sys.argv) > 2 else 'data/pod-log-metadata.json'

    print("="*60)
    print("POD LOGS INDEX SCHEMA VALIDATION")
    print("="*60)
    print(f"\nValidating: {jsonl_file}")
    print(f"Metadata reference: {metadata_file}\n")

    # Load JSONL entries
    print("Loading JSONL file...")
    entries = load_jsonl(jsonl_file)
    print(f"✓ Loaded {len(entries)} entries")

    if not entries:
        print("✗ No entries to validate")
        sys.exit(1)

    # Validate each entry
    print("\nValidating entries against schema...")
    all_errors = []
    for line_num, entry in enumerate(entries, 1):
        errors = validate_entry(entry, line_num)
        all_errors.extend([(line_num, error) for error in errors])

    # Print validation results
    print("\n" + "="*60)
    print("VALIDATION RESULTS")
    print("="*60)

    print(f"\nTotal entries: {len(entries)}")
    print(f"Entries with errors: {len(set([e[0] for e in all_errors]))}")
    print(f"Total errors: {len(all_errors)}")

    if all_errors:
        print("\nErrors (first 20):")
        for line_num, error in all_errors[:20]:
            print(f"  Line {line_num}: {error}")
        if len(all_errors) > 20:
            print(f"  ... and {len(all_errors) - 20} more errors")
    else:
        print("\n✓ All entries are valid!")

    # Completeness check
    print("\n" + "="*60)
    print("COMPLETENESS CHECK")
    print("="*60)

    completeness = validate_completeness(entries, metadata_file)
    if 'error' in completeness:
        print(f"\n✗ Could not check completeness: {completeness['error']}")
    else:
        print(f"\nExpected logs: {completeness['expected_count']}")
        print(f"Indexed logs: {completeness['indexed_count']}")

        if completeness['missing_logs']:
            print(f"\n✗ Missing {len(completeness['missing_logs'])} logs:")
            for log in completeness['missing_logs'][:5]:
                print(f"  - {log}")
            if len(completeness['missing_logs']) > 5:
                print(f"  ... and {len(completeness['missing_logs']) - 5} more")
        else:
            print("\n✓ All expected logs are indexed!")

        if completeness['extra_logs']:
            print(f"\n⚠ Found {len(completeness['extra_logs'])} extra logs not in metadata:")
            for log in completeness['extra_logs'][:5]:
                print(f"  - {log}")
            if len(completeness['extra_logs']) > 5:
                print(f"  ... and {len(completeness['extra_logs']) - 5} more")

    print("\n" + "="*60)
    print("FINAL RESULT")
    print("="*60)

    valid = len(all_errors) == 0 and completeness.get('complete', False)
    if valid:
        print("\n✓ VALID - pod-logs-index.jsonl is complete and valid!")
        sys.exit(0)
    else:
        print("\n✗ INVALID - Validation failed")
        if all_errors:
            print(f"  Schema errors: {len(all_errors)}")
        if not completeness.get('complete', False):
            print(f"  Incomplete: {len(completeness.get('missing_logs', []))} missing logs")
        sys.exit(1)


if __name__ == '__main__':
    main()