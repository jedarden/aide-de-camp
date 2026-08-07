"""
JSONL file loading utilities.

Provides basic file loading functionality for JSONL (JSON Lines) files,
where each line is a valid JSON object. This module handles file I/O and
basic JSON parsing, with field extraction and normalization.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Dict, Optional, Any

from logging import getLogger

logger = getLogger(__name__)

# Format constants
FORMAT_DEPLOYMENT = 'deployment'
FORMAT_POD = 'pod'
FORMAT_EVENT = 'event'
FORMAT_REPLICASET = 'replicaset'
FORMAT_UNKNOWN = 'unknown'


def detect_format(raw_entry: Dict[str, Any]) -> str:
    """
    Detect the service log format based on entry structure and field names.

    Analyzes the raw entry's field names and structure to determine which
    service format it uses. Each format has a unique signature of fields.

    Args:
        raw_entry: Raw log entry dictionary

    Returns:
        Format string: 'deployment', 'pod', 'event', 'replicaset', or 'unknown'
    """
    # Deployment format: has commit_hash and deploy_type (pbx-web build history)
    if 'commit_hash' in raw_entry and 'deploy_type' in raw_entry:
        return FORMAT_DEPLOYMENT

    # Pod format: has name/status/podIP but no commit_hash (whisper-stt pods)
    if 'name' in raw_entry and 'status' in raw_entry and 'podIP' in raw_entry:
        if 'commit_hash' not in raw_entry:
            return FORMAT_POD

    # Event format: has type/reason/object fields (Kubernetes events)
    if 'type' in raw_entry and 'reason' in raw_entry and 'object' in raw_entry:
        return FORMAT_EVENT

    # ReplicaSet format: has name/replicas/readyReplicas but no podIP/commit_hash
    if 'name' in raw_entry and 'replicas' in raw_entry and 'readyReplicas' in raw_entry:
        if 'commit_hash' not in raw_entry and 'podIP' not in raw_entry:
            return FORMAT_REPLICASET

    # Fallback for unknown formats
    logger.debug(f"Unable to detect format for entry with keys: {list(raw_entry.keys())}")
    return FORMAT_UNKNOWN


def load_jsonl(file_path: str) -> tuple[list[Dict], int, int]:
    """
    Load a JSONL file and parse each line as a JSON object.

    Reads the file line by line, parsing each line as a separate JSON object.
    Empty lines are skipped. Returns successfully parsed entries with error statistics.

    Args:
        file_path: Path to the JSONL file (str).

    Returns:
        Tuple of (entries, errors_count, skipped_count):
        - entries: List of successfully parsed Dict objects
        - errors_count: Number of lines with JSON decode errors
        - skipped_count: Number of empty lines skipped

    Raises:
        FileNotFoundError: If the specified file does not exist.
    """
    path = Path(file_path)

    if not path.exists():
        logger.error(f"JSONL file not found: {path}")
        raise FileNotFoundError(f"JSONL file not found: {path}")

    if not path.is_file():
        logger.error(f"Path is not a file: {path}")
        raise ValueError(f"Path is not a file: {path}")

    entries = []
    errors_count = 0
    skipped_count = 0

    with path.open('r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines
            if not line:
                skipped_count += 1
                logger.debug(f"Skipping empty line {line_num} in {path}")
                continue

            try:
                obj = json.loads(line)
                entries.append(obj)
                logger.debug(f"Successfully parsed line {line_num} in {path}")
            except json.JSONDecodeError as e:
                errors_count += 1
                logger.warning(f"Failed to parse line {line_num} in {path}: {e}")
                continue

    logger.info(f"Loaded {len(entries)} entries from {path} ({errors_count} errors, {skipped_count} empty lines skipped)")
    return entries, errors_count, skipped_count


def normalize_timestamp(ts_input: Optional[Any]) -> Optional[str]:
    """
    Normalize timestamp to ISO 8601 format (UTC).

    Handles multiple input formats:
    - Unix epoch timestamps (int/float, seconds or milliseconds)
    - ISO 8601 strings (with or without timezone)
    - datetime objects

    Includes validation and error handling:
    - Type checking before processing
    - Invalid format logging at DEBUG level
    - Graceful fallback to None for unparseable formats

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
            # Validate timestamp is reasonable (between 1970 and 2100)
            if ts_input < 0 or ts_input > 4_102_444_800:  # Jan 1, 2100
                logger.warning(f"Timestamp out of valid range: {ts_input}")
                return None

            # Detect if timestamp is in milliseconds (typically > 10^11)
            if ts_input > 100_000_000_000:  # Milliseconds since epoch
                ts_input = ts_input / 1000
            dt = datetime.fromtimestamp(ts_input, tz=timezone.utc)
            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Handle string timestamps
        if isinstance(ts_input, str):
            ts_input = ts_input.strip()

            # Validate string is not empty after stripping
            if not ts_input:
                logger.debug("Empty timestamp string after stripping")
                return None

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
                logger.debug(f"Failed to parse timestamp string as epoch: '{ts_input}'")
                pass

        # Handle datetime objects
        if isinstance(ts_input, datetime):
            return ts_input.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Unhandled type - log for debugging
        logger.debug(f"Unhandled timestamp type: {type(ts_input).__name__}, value: {ts_input}")
        return None

    except (ValueError, OSError, OverflowError) as e:
        logger.debug(f"Failed to normalize timestamp '{ts_input}': {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error normalizing timestamp '{ts_input}': {e}")
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


def extract_deployment_fields(raw_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize fields from deployment log entries.

    Handles pbx-web build history format with commit tracking.

    Args:
        raw_entry: Raw deployment entry with commit_hash, deploy_type, etc.

    Returns:
        Normalized dictionary with standard schema fields
    """
    timestamp = normalize_timestamp(raw_entry.get('timestamp'))
    service = raw_entry.get('service', 'pbx-web')

    # Determine status from deploy_type
    deploy_type = raw_entry.get('deploy_type', '').lower()
    if deploy_type == 'rollback':
        status = 'failure'
    elif deploy_type == 'bugfix':
        status = 'warning'
    elif deploy_type in ['feature_addition', 'config_change', 'initial_deployment']:
        status = 'success'
    else:
        status = 'unknown'

    # Determine event type
    event_type = f"deployment_{deploy_type}" if deploy_type else 'deployment'

    # Extract error code if failure
    error_code = deploy_type if deploy_type == 'rollback' else None

    # Build metadata
    metadata = {
        'source_fields': {
            'commit_hash': raw_entry.get('commit_hash'),
            'author': raw_entry.get('author'),
            'message': raw_entry.get('message'),
            'files_changed': raw_entry.get('files_changed'),
            'files': raw_entry.get('files', []),
            'image_version': raw_entry.get('image_version')
        },
        'raw_format': FORMAT_DEPLOYMENT
    }

    return {
        'timestamp': timestamp,
        'service': service,
        'event_type': event_type,
        'status': status,
        'error_code': error_code,
        'duration_ms': None,
        'cluster': raw_entry.get('cluster', 'ardenone-cluster'),
        'namespace': raw_entry.get('namespace', 'pbx-web'),
        'metadata': metadata
    }


def extract_pod_fields(raw_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize fields from pod log entries.

    Handles whisper-stt pod status format with pod health information.

    Args:
        raw_entry: Raw pod entry with name, status, restartCount, etc.

    Returns:
        Normalized dictionary with standard schema fields
    """
    timestamp = normalize_timestamp(raw_entry.get('startTime'))
    service = raw_entry.get('service', 'whisper-stt')

    # Determine status from pod status
    pod_status = raw_entry.get('status', '').lower()
    if pod_status == 'running':
        status = 'success' if raw_entry.get('ready', False) else 'warning'
    elif pod_status in ['failed', 'error', 'crashloopbackoff']:
        status = 'failure'
    elif pod_status in ['pending', 'containercreating']:
        status = 'warning'
    else:
        status = 'unknown'

    event_type = 'pod_status'

    # Extract error code if failure
    error_code = pod_status if pod_status in ['failed', 'error', 'crashloopbackoff'] else None

    # Duration: calculate from startTime to now
    duration_ms = None
    start_time = raw_entry.get('startTime')
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            now = datetime.now(start_dt.tzinfo)
            duration_ms = int((now - start_dt).total_seconds() * 1000)
        except (ValueError, OSError):
            pass

    # Build metadata
    metadata = {
        'source_fields': {
            'name': raw_entry.get('name'),
            'ready': raw_entry.get('ready'),
            'restartCount': raw_entry.get('restartCount'),
            'nodeName': raw_entry.get('nodeName'),
            'podIP': raw_entry.get('podIP'),
            'image': raw_entry.get('image'),
            'conditions': raw_entry.get('conditions', [])
        },
        'raw_format': FORMAT_POD
    }

    return {
        'timestamp': timestamp,
        'service': service,
        'event_type': event_type,
        'status': status,
        'error_code': error_code,
        'duration_ms': duration_ms,
        'cluster': raw_entry.get('cluster', 'ardenone-cluster'),
        'namespace': raw_entry.get('namespace', 'whisper-stt'),
        'metadata': metadata
    }


def extract_event_fields(raw_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize fields from Kubernetes event log entries.

    Handles Kubernetes event format with type, reason, and object fields.

    Args:
        raw_entry: Raw event entry with type, reason, object, message, etc.

    Returns:
        Normalized dictionary with standard schema fields
    """
    timestamp = normalize_timestamp(raw_entry.get('lastTimestamp') or raw_entry.get('firstTimestamp'))
    service = raw_entry.get('service', 'pbx-web')

    # Determine status from event type
    event_type_field = raw_entry.get('type', '').lower()
    if event_type_field == 'warning':
        status = 'warning'
    elif event_type_field == 'normal':
        status = 'success'
    else:
        status = 'unknown'

    event_type = f"event_{raw_entry.get('reason', '').lower()}" if raw_entry.get('reason') else 'event'

    # Error code from reason
    error_code = raw_entry.get('reason') if event_type_field == 'warning' else None

    # Build metadata
    metadata = {
        'source_fields': {
            'type': raw_entry.get('type'),
            'reason': raw_entry.get('reason'),
            'object': raw_entry.get('object'),
            'message': raw_entry.get('message'),
            'firstTimestamp': raw_entry.get('firstTimestamp'),
            'lastTimestamp': raw_entry.get('lastTimestamp')
        },
        'raw_format': FORMAT_EVENT
    }

    return {
        'timestamp': timestamp,
        'service': service,
        'event_type': event_type,
        'status': status,
        'error_code': error_code,
        'duration_ms': None,
        'cluster': raw_entry.get('cluster', 'ardenone-cluster'),
        'namespace': raw_entry.get('namespace', 'pbx-web'),
        'metadata': metadata
    }


def extract_replicaset_fields(raw_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize fields from ReplicaSet log entries.

    Handles Kubernetes ReplicaSet format with replica and readiness information.

    Args:
        raw_entry: Raw replicaset entry with name, replicas, readyReplicas, etc.

    Returns:
        Normalized dictionary with standard schema fields
    """
    timestamp = normalize_timestamp(raw_entry.get('createdAt'))
    service = raw_entry.get('service', 'pbx-web')

    # Determine status from replica readiness
    replicas = raw_entry.get('replicas', 0)
    ready_replicas = raw_entry.get('readyReplicas', 0)

    if ready_replicas == replicas and replicas > 0:
        status = 'success'
    elif ready_replicas == 0 and replicas > 0:
        status = 'failure'
    elif ready_replicas < replicas:
        status = 'warning'
    else:
        status = 'unknown'

    event_type = 'replicaset_status'

    # Error code if not all replicas ready
    error_code = 'replicas_unready' if ready_replicas < replicas else None

    # Duration: calculate from createdAt to now
    duration_ms = None
    created_at = raw_entry.get('createdAt')
    if created_at:
        try:
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            now = datetime.now(created_dt.tzinfo)
            duration_ms = int((now - created_dt).total_seconds() * 1000)
        except (ValueError, OSError):
            pass

    # Build metadata
    metadata = {
        'source_fields': {
            'name': raw_entry.get('name'),
            'replicas': replicas,
            'readyReplicas': ready_replicas,
            'observedGeneration': raw_entry.get('observedGeneration'),
            'conditions': raw_entry.get('conditions')
        },
        'raw_format': FORMAT_REPLICASET
    }

    return {
        'timestamp': timestamp,
        'service': service,
        'event_type': event_type,
        'status': status,
        'error_code': error_code,
        'duration_ms': duration_ms,
        'cluster': raw_entry.get('cluster', 'ardenone-cluster'),
        'namespace': raw_entry.get('namespace', 'pbx-web'),
        'metadata': metadata
    }


def parse_entry(raw_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse a log entry and normalize it to the unified schema.

    This is the main entry point for multi-format log parsing. It detects
    the format of the raw entry and dispatches to the appropriate field
    extraction function, normalizing all formats to the same output schema.

    Args:
        raw_entry: Raw log entry dictionary from JSONL file

    Returns:
        Normalized dictionary with fields:
        - timestamp: ISO 8601 formatted timestamp (or None)
        - service: Service name (pbx-web, whisper-stt, etc.)
        - event_type: Entry type (deployment, pod_status, event, replicaset_status, unknown)
        - status: Normalized status (success, failure, warning, unknown)
        - error_code: Error identifier or None
        - duration_ms: Duration in milliseconds or None
        - cluster: Cluster name
        - namespace: Namespace name
        - metadata: Additional metadata including source fields and format

    Examples:
        >>> raw = {"commit_hash": "abc123", "deploy_type": "feature_addition", "service": "pbx-web"}
        >>> parse_entry(raw)
        {
            'timestamp': None,
            'service': 'pbx-web',
            'event_type': 'deployment_feature_addition',
            'status': 'success',
            'error_code': None,
            'duration_ms': None,
            'cluster': 'ardenone-cluster',
            'namespace': 'pbx-web',
            'metadata': {...}
        }
    """
    # Detect the format
    log_format = detect_format(raw_entry)

    # Dispatch to appropriate extraction function
    if log_format == FORMAT_DEPLOYMENT:
        return extract_deployment_fields(raw_entry)
    elif log_format == FORMAT_POD:
        return extract_pod_fields(raw_entry)
    elif log_format == FORMAT_EVENT:
        return extract_event_fields(raw_entry)
    elif log_format == FORMAT_REPLICASET:
        return extract_replicaset_fields(raw_entry)
    else:
        # Unknown format - log a warning and return minimal info
        logger.warning(f"Unknown log format for entry with keys: {list(raw_entry.keys())}")

        # Return minimal normalized entry for unknown formats
        return {
            'timestamp': None,
            'service': raw_entry.get('service', 'unknown'),
            'event_type': 'unknown',
            'status': 'unknown',
            'error_code': None,
            'duration_ms': None,
            'cluster': raw_entry.get('cluster', 'unknown'),
            'namespace': raw_entry.get('namespace', 'unknown'),
            'metadata': {
                'source_fields': raw_entry,
                'raw_format': FORMAT_UNKNOWN
            }
        }


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

    This function implements field extraction and normalization for multiple
    service log formats. It now uses the multi-format parser which automatically
    detects the format and normalizes all formats to the same output schema.

    Includes robust error handling for malformed/missing fields:
    - Missing required fields get default values
    - Invalid data types are handled gracefully
    - Timestamp format is validated before normalization
    - Completely invalid entries are logged and skipped

    Args:
        raw_entry: Raw log entry dictionary from JSONL file

    Returns:
        Normalized dictionary with fields:
        - timestamp: ISO 8601 formatted timestamp (or None)
        - service: Service name (pbx-web, whisper-stt, etc.)
        - event_type: Entry type (deployment, pod_status, event, replicaset_status, unknown)
        - status: Normalized status (success, failure, warning, unknown)
        - error_code: Error identifier or None
        - duration_ms: Duration in milliseconds or None
        - cluster: Cluster name
        - namespace: Namespace name
        - metadata: Additional metadata including source fields and format

    Examples:
        >>> raw = {"commit_hash": "abc123", "deploy_type": "feature_addition", "service": "pbx-web"}
        >>> extract_fields(raw)
        {
            'timestamp': None,
            'service': 'pbx-web',
            'event_type': 'deployment_feature_addition',
            'status': 'success',
            'error_code': None,
            'duration_ms': None,
            'cluster': 'ardenone-cluster',
            'namespace': 'pbx-web',
            'metadata': {...}
        }
    """
    # Validate input type
    if not isinstance(raw_entry, dict):
        logger.error(f"Invalid entry type: expected dict, got {type(raw_entry).__name__}")
        return _get_minimal_entry()

    # Check for completely empty or invalid entries
    if not raw_entry:
        logger.warning("Empty entry provided, returning minimal entry")
        return _get_minimal_entry()

    try:
        # Use the new multi-format parser
        result = parse_entry(raw_entry)

        # Validate the result has the expected structure
        if not isinstance(result, dict):
            logger.error(f"Parser returned non-dict result: {type(result).__name__}")
            return _get_minimal_entry()

        # Ensure all required fields are present (with defaults if missing)
        _ensure_required_fields(result)

        return result

    except Exception as e:
        logger.warning(f"Failed to extract fields from entry: {e}, using minimal entry")
        return _get_minimal_entry()


def _get_minimal_entry() -> Dict[str, Any]:
    """
    Get a minimal valid entry with default values.

    Returns:
        Dictionary with all required fields set to safe defaults
    """
    return {
        'timestamp': None,
        'service': 'unknown',
        'event_type': 'unknown',
        'status': 'unknown',
        'error_code': None,
        'duration_ms': None,
        'cluster': 'unknown',
        'namespace': 'unknown',
        'metadata': {
            'source_fields': {},
            'raw_format': FORMAT_UNKNOWN
        }
    }


def _ensure_required_fields(entry: Dict[str, Any]) -> None:
    """
    Ensure all required fields exist in the entry, adding defaults if missing.

    Args:
        entry: Entry dictionary to validate and populate
    """
    required_fields = {
        'timestamp': None,
        'service': 'unknown',
        'event_type': 'unknown',
        'status': 'unknown',
        'error_code': None,
        'duration_ms': None,
        'cluster': 'unknown',
        'namespace': 'unknown',
        'metadata': {
            'source_fields': {},
            'raw_format': FORMAT_UNKNOWN
        }
    }

    for field, default_value in required_fields.items():
        if field not in entry:
            logger.debug(f"Adding missing field '{field}' with default value: {default_value}")
            entry[field] = default_value
        elif field == 'metadata' and not isinstance(entry.get('metadata'), dict):
            logger.warning(f"Invalid metadata field type, using default: {entry.get('metadata')}")
            entry[field] = default_value
