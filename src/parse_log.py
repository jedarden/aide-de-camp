"""
JSONL file loading utilities.

Provides basic file loading functionality for JSONL (JSON Lines) files,
where each line is a valid JSON object. This module handles file I/O and
basic JSON parsing, with field extraction and normalization.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Iterator, Dict, Optional, Any

from logging import getLogger

logger = getLogger(__name__)


def load_jsonl(file_path: str) -> Iterator[Dict]:
    """
    Load a JSONL file and parse each line as a JSON object.

    Reads the file line by line, parsing each line as a separate JSON object.
    Empty lines are skipped. Yields individual parsed dict objects.

    Args:
        file_path: Path to the JSONL file (str).

    Yields:
        Dict objects parsed from each line in the file.

    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    with path.open('r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            try:
                obj = json.loads(line)
                yield obj
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse line {line_num} in {path}: {e}")
                continue


def normalize_timestamp(ts_input: Optional[Any]) -> Optional[str]:
    """
    Normalize timestamp to ISO 8601 format (UTC).

    Handles multiple input formats:
    - Unix epoch timestamps (int/float, seconds or milliseconds)
    - ISO 8601 strings (with or without timezone)
    - datetime objects

    Args:
        ts_input: Timestamp in various formats

    Returns:
        ISO 8601 formatted string with 'Z' suffix (UTC), or None if parsing fails
    """
    if ts_input is None:
        return None

    try:
        # Handle Unix epoch timestamps (numbers)
        if isinstance(ts_input, (int, float)):
            # Detect if timestamp is in milliseconds (typically > 10^11)
            if ts_input > 100_000_000_000:  # Milliseconds since epoch
                ts_input = ts_input / 1000
            dt = datetime.utcfromtimestamp(ts_input)
            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Handle string timestamps
        if isinstance(ts_input, str):
            ts_input = ts_input.strip()

            # Already ISO 8601 format
            if 'T' in ts_input:
                # Remove timezone suffix if present and normalize to Z
                if ts_input.endswith('Z'):
                    return ts_input
                # Handle other timezone formats
                if '+' in ts_input:
                    # Split off timezone and convert to Z
                    parts = ts_input.split('+')
                    if len(parts) == 2:
                        ts_base = parts[0]
                        return f"{ts_base}Z"
                # If no timezone info, assume UTC
                if len(ts_input) == 19:  # YYYY-MM-DDTHH:MM:SS
                    return f"{ts_input}Z"
                return ts_input

            # Try Unix epoch as string
            try:
                epoch = float(ts_input)
                return normalize_timestamp(epoch)
            except ValueError:
                pass

        # Handle datetime objects
        if isinstance(ts_input, datetime):
            return ts_input.strftime('%Y-%m-%dT%H:%M:%SZ')

    except (ValueError, OSError, OverflowError) as e:
        logger.debug(f"Failed to normalize timestamp '{ts_input}': {e}")
        return None

    return None


def detect_entry_type(raw_entry: Dict[str, Any]) -> str:
    """
    Detect the entry type based on field presence.

    Maps raw entries to their semantic type for pbx-web service.

    Args:
        raw_entry: Raw log entry dictionary

    Returns:
        Entry type string: 'metadata', 'pod_info', 'deployment', 'error', 'health_metric', or 'unknown'
    """
    # Check for metadata entry
    if 'namespace' in raw_entry and 'cluster' in raw_entry and 'data_collection_timestamp' in raw_entry:
        return 'metadata'

    # Check for pod_info entry
    if 'pod_name' in raw_entry and 'age_days' in raw_entry and 'restart_count' in raw_entry:
        return 'pod_info'

    # Check for deployment_metric entry
    if 'metric_type' in raw_entry and raw_entry.get('metric_type') == 'deployment_history':
        return 'deployment'

    # Check for error_info entry
    if 'error_type' in raw_entry and 'error_pattern' in raw_entry:
        return 'error'

    # Check for health_metric entry
    if 'health_metric' in raw_entry and 'value' in raw_entry:
        return 'health_metric'

    return 'unknown'


def extract_status(raw_entry: Dict[str, Any], entry_type: str) -> str:
    """
    Extract and normalize status from raw entry.

    Args:
        raw_entry: Raw log entry dictionary
        entry_type: Detected entry type

    Returns:
        Normalized status: 'success', 'failure', 'warning', or 'unknown'
    """
    # Default status
    default_status = 'unknown'

    if entry_type == 'pod_info':
        status = raw_entry.get('status', '').lower()
        if status == 'running':
            return 'success'
        elif status in ['failed', 'error', 'crashloopbackoff']:
            return 'failure'
        elif status in ['pending', 'containercreating']:
            return 'warning'

    if entry_type == 'health_metric':
        health_status = raw_entry.get('health_status', '').lower()
        if 'all pods running' in health_status or 'healthy' in health_status:
            return 'success'
        elif 'degraded' in health_status or 'warning' in health_status:
            return 'warning'
        elif 'down' in health_status or 'failed' in health_status:
            return 'failure'

    if entry_type == 'error':
        severity = raw_entry.get('severity', '').lower()
        if severity == 'critical':
            return 'failure'
        elif severity == 'intermittent':
            return 'warning'
        else:
            return 'failure'

    if entry_type == 'deployment':
        # For deployment metrics, infer from restart counts or age
        restart_count = raw_entry.get('restart_count', 0)
        if restart_count == 0:
            return 'success'
        elif restart_count > 0:
            return 'warning'

    return default_status


def extract_duration_ms(raw_entry: Dict[str, Any], entry_type: str) -> Optional[int]:
    """
    Extract and convert duration to milliseconds.

    Args:
        raw_entry: Raw log entry dictionary
        entry_type: Detected entry type

    Returns:
        Duration in milliseconds, or None if not available
    """
    if entry_type == 'pod_info':
        # Convert age_days to milliseconds
        age_days = raw_entry.get('age_days')
        if age_days is not None:
            try:
                return int(age_days * 24 * 60 * 60 * 1000)
            except (ValueError, TypeError):
                pass

    if entry_type == 'deployment':
        # Convert current_deployment_age_days to milliseconds
        age_days = raw_entry.get('current_deployment_age_days')
        if age_days is not None:
            try:
                return int(age_days * 24 * 60 * 60 * 1000)
            except (ValueError, TypeError):
                pass

    return None


def extract_error_code(raw_entry: Dict[str, Any], entry_type: str) -> Optional[str]:
    """
    Extract error code from raw entry.

    Args:
        raw_entry: Raw log entry dictionary
        entry_type: Detected entry type

    Returns:
        Error code string, or None if not applicable
    """
    if entry_type == 'error':
        return raw_entry.get('error_type')

    # Check for failure status in pod_info
    if entry_type == 'pod_info':
        status = raw_entry.get('status', '').lower()
        if status in ['failed', 'error', 'crashloopbackoff']:
            return status

    return None


def extract_fields(raw_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize fields from a raw log entry.

    This function implements field extraction and normalization for pbx-web
    service logs, mapping raw field names to the standardized output schema.

    Args:
        raw_entry: Raw log entry dictionary from JSONL file

    Returns:
        Normalized dictionary with fields:
        - timestamp: ISO 8601 formatted timestamp (or None)
        - service: Service name (always 'pbx-web' for now)
        - event_type: Entry type (metadata, pod_info, deployment, error, health_metric, unknown)
        - status: Normalized status (success, failure, warning, unknown)
        - error_code: Error identifier or None
        - duration_ms: Duration in milliseconds or None
        - cluster: Cluster name
        - namespace: Namespace name
        - metadata: Additional metadata including source fields

    Examples:
        >>> raw = {
        ...     "pod_name": "pbx-web-5ff68464d-mkn8n",
        ...     "age_days": 8,
        ...     "restart_count": 0,
        ...     "status": "running"
        ... }
        >>> extract_fields(raw)
        {
            'timestamp': None,
            'service': 'pbx-web',
            'event_type': 'pod_info',
            'status': 'success',
            'error_code': None,
            'duration_ms': 691200000,
            'cluster': 'ardenone-cluster',
            'namespace': 'pbx-web',
            'metadata': {...}
        }
    """
    # Detect entry type
    entry_type = detect_entry_type(raw_entry)

    # Extract timestamp (check multiple possible fields)
    timestamp = None
    for ts_field in ['timestamp', 'data_collection_timestamp', 'creation_timestamp', 'time']:
        if ts_field in raw_entry:
            timestamp = normalize_timestamp(raw_entry[ts_field])
            if timestamp:
                break

    # Extract service (hardcoded for pbx-web initially)
    service = raw_entry.get('service', 'pbx-web')

    # Extract and normalize status
    status = extract_status(raw_entry, entry_type)

    # Extract error code
    error_code = extract_error_code(raw_entry, entry_type)

    # Extract duration
    duration_ms = extract_duration_ms(raw_entry, entry_type)

    # Extract cluster and namespace
    cluster = raw_entry.get('cluster', 'ardenone-cluster')
    namespace = raw_entry.get('namespace', 'pbx-web')

    # Build metadata object with source fields
    metadata = {
        'source_fields': {},
        'raw_entry_type': entry_type
    }

    # Preserve select source fields in metadata
    preserve_fields = ['pod_name', 'image', 'restart_count', 'health_status',
                      'error_pattern', 'severity', 'metric_type', 'health_metric']

    for field in preserve_fields:
        if field in raw_entry:
            metadata['source_fields'][field] = raw_entry[field]

    # Return normalized entry
    return {
        'timestamp': timestamp,
        'service': service,
        'event_type': entry_type,
        'status': status,
        'error_code': error_code,
        'duration_ms': duration_ms,
        'cluster': cluster,
        'namespace': namespace,
        'metadata': metadata
    }
