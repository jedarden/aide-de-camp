#!/usr/bin/env python3
"""
Parse and categorize deployment events into structured dataset.

This script processes deployment logs from multiple sources (JSONL files,
deployment data files, and pod logs) to extract and categorize deployment
events for analysis.

Output columns: timestamp, service, event_type, status, error_code, duration
"""

import json
import pandas as pd
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Event type categorization mapping
EVENT_TYPE_MAPPINGS = {
    # Deployment lifecycle events
    'deployment_rollout': 'deployment_start',
    'deployment_rollback': 'deployment_rollback',
    'deployment_complete': 'deployment_complete',
    'deployment_failed': 'deployment_failed',
    'deployment_start': 'deployment_start',

    # Configuration changes
    'config_change': 'config_change',
    'image_bump': 'image_bump',
    'bugfix': 'bugfix_deployment',
    'feature': 'feature_deployment',

    # Pod events
    'pod_crash': 'pod_crash',
    'pod_restart': 'pod_restart',
    'pod_ready': 'pod_ready',
    'pod_not_ready': 'pod_not_ready',

    # Failure events
    'oom_kill': 'oom',
    'readiness_fail': 'readiness_fail',
    'timeout': 'timeout',
    'crash_loop_back_off': 'crash_loop_back_off',
    'image_pull_error': 'image_pull_error',
    'container_failed': 'container_failed',

    # Generic events
    'unknown': 'unknown_event'
}


def normalize_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """
    Normalize various timestamp formats to datetime objects.

    Args:
        ts_str: Timestamp string in various formats

    Returns:
        datetime object or None if parsing fails
    """
    if not ts_str or not isinstance(ts_str, str):
        return None

    try:
        # Handle ISO 8601 formats
        ts_str = ts_str.strip()
        if ts_str.endswith('Z'):
            ts_str = ts_str[:-1] + '+00:00'
        elif ts_str.endswith('-04:00') or ts_str.endswith('-05:00'):
            pass  # Already has timezone
        elif ' ' in ts_str and not any(tz in ts_str for tz in ['+', '-']):
            # Format like "2026-08-04 23:42:12 -04:00"
            match = re.match(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+([+-]\d{2}:\d{2})', ts_str)
            if match:
                ts_str = match.group(1).replace(' ', 'T') + match.group(2)

        # Try parsing with fromisoformat
        return datetime.fromisoformat(ts_str)
    except (ValueError, AttributeError) as e:
        logger.debug(f"Failed to parse timestamp '{ts_str}': {e}")
        return None


def categorize_event(event_data: Dict[str, Any]) -> str:
    """
    Categorize an event based on its properties.

    Args:
        event_data: Raw event data dictionary

    Returns:
        Event category string
    """
    # Check for explicit event_type field
    if 'event_type' in event_data:
        raw_type = event_data['event_type']
        return EVENT_TYPE_MAPPINGS.get(raw_type, raw_type)

    # Check deploy_type field
    if 'deploy_type' in event_data:
        deploy_type = event_data['deploy_type']
        if deploy_type == 'rollback':
            return 'deployment_rollback'
        elif deploy_type in ['bugfix', 'feature']:
            return f'{deploy_type}_deployment'
        elif deploy_type in ['config_change', 'image_bump']:
            return deploy_type
        else:
            return 'deployment_start'

    # Check for failure indicators
    if 'status' in event_data:
        status = str(event_data['status']).lower()
        if 'fail' in status or 'error' in status:
            return 'deployment_failed'
        elif 'complete' in status or 'success' in status:
            return 'deployment_complete'

    # Check pod status for crash patterns
    if 'restartCount' in event_data and event_data.get('restartCount', 0) > 0:
        return 'pod_restart'

    # Check for failure conditions
    if 'reason' in event_data:
        reason = event_data['reason'].lower()
        if 'oom' in reason:
            return 'oom'
        elif 'crash' in reason:
            return 'pod_crash'
        elif 'timeout' in reason:
            return 'timeout'
        elif 'readiness' in reason or 'ready' in reason:
            return 'readiness_fail'

    # Default to deployment_start for generic deployment events
    return 'deployment_start'


def extract_error_code(event_data: Dict[str, Any]) -> Optional[str]:
    """
    Extract error code from event data.

    Args:
        event_data: Raw event data dictionary

    Returns:
        Error code string or None
    """
    # Check for explicit error code
    if 'error_code' in event_data:
        return str(event_data['error_code'])

    # Check for error in status/reason
    if 'reason' in event_data:
        reason = event_data['reason']
        if 'Error' in str(reason) or 'Failed' in str(reason):
            return str(reason)

    # Check for failure outcome
    if event_data.get('outcome') == 'failure':
        return 'deployment_failed'

    # Check container status codes
    if 'exit_code' in event_data:
        return f"exit_code_{event_data['exit_code']}"

    return None


def extract_duration(event_data: Dict[str, Any]) -> Optional[float]:
    """
    Extract deployment duration in seconds.

    Args:
        event_data: Raw event data dictionary

    Returns:
        Duration in seconds or None
    """
    if 'duration' in event_data:
        duration = event_data['duration']
        try:
            return float(duration)
        except (ValueError, TypeError):
            pass

    # Calculate from start and end timestamps
    if 'start_time' in event_data and 'end_time' in event_data:
        start = normalize_timestamp(event_data['start_time'])
        end = normalize_timestamp(event_data['end_time'])
        if start and end:
            return (end - start).total_seconds()

    return None


def extract_status(event_data: Dict[str, Any]) -> str:
    """
    Extract event status.

    Args:
        event_data: Raw event data dictionary

    Returns:
        Status string: 'success', 'failure', or 'unknown'
    """
    # Check explicit outcome field
    if 'outcome' in event_data:
        outcome = event_data['outcome']
        if isinstance(outcome, str):
            if outcome.lower() in ['success', 'successful', 'succeeded']:
                return 'success'
            elif outcome.lower() in ['failure', 'failed', 'error']:
                return 'failure'

    # Check status field
    if 'status' in event_data:
        status = str(event_data['status']).lower()
        if 'success' in status or 'complete' in status or 'ready' in status:
            return 'success'
        elif 'fail' in status or 'error' in status or 'crash' in status:
            return 'failure'

    # Check pod status
    if 'ready' in event_data:
        return 'success' if event_data['ready'] else 'failure'

    # Check for error indicators
    if event_data.get('error_code') or event_data.get('reason'):
        return 'failure'

    return 'unknown'


def parse_jsonl_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse a JSONL file and extract deployment events.

    Args:
        filepath: Path to JSONL file

    Returns:
        List of parsed event dictionaries
    """
    events = []
    try:
        with open(filepath, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    event_data = json.loads(line)
                    events.append(event_data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON at line {line_num} in {filepath}: {e}")
                    continue

    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")

    return events


def parse_deployment_data_file(filepath: str, service: str) -> List[Dict[str, Any]]:
    """
    Parse deployment data JSON file.

    Args:
        filepath: Path to deployment data JSON file
        service: Service name (pbx-web or whisper-stt)

    Returns:
        List of parsed event dictionaries
    """
    events = []
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Extract deployment events from comprehensive format
        if service in data and 'deployment_events' in data[service]:
            for event in data[service]['deployment_events']:
                event['service'] = service
                events.append(event)

        # Extract from deployment_events_last_30_days format
        elif 'deployment_events_last_30_days' in data:
            for event in data['deployment_events_last_30_days']:
                event['service'] = service
                events.append(event)

    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON in {filepath}: {e}")
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")

    return events


def process_event(event_data: Dict[str, Any], default_service: Optional[str] = None) -> Dict[str, Any]:
    """
    Process a raw event into standardized format.

    Args:
        event_data: Raw event data dictionary
        default_service: Default service name if not in event data

    Returns:
        Standardized event dictionary
    """
    # Extract service
    service = event_data.get('service', default_service or 'unknown')

    # Extract and normalize timestamp
    timestamp = None
    for ts_field in ['timestamp', 'time', 'created', 'startTime', 'lastTimestamp', 'date']:
        if ts_field in event_data:
            timestamp = normalize_timestamp(event_data[ts_field])
            if timestamp:
                break

    # Categorize event
    event_type = categorize_event(event_data)

    # Extract status
    status = extract_status(event_data)

    # Extract error code
    error_code = extract_error_code(event_data)

    # Extract duration
    duration = extract_duration(event_data)

    return {
        'timestamp': timestamp,
        'service': service,
        'event_type': event_type,
        'status': status,
        'error_code': error_code,
        'duration': duration,
        'raw_data': json.dumps(event_data)  # Keep raw data for reference
    }


def main():
    """
    Main function to parse deployment events from multiple sources.
    """
    logger.info("Starting deployment event parsing...")

    # Define data sources
    data_sources = [
        # JSONL files
        ('/home/coding/aide-de-camp/data/pbx-web-logs.jsonl', 'pbx-web'),
        ('/home/coding/aide-de-camp/data/whisper-stt-pods.jsonl', 'whisper-stt'),

        # Deployment data files
        ('/home/coding/aide-de-camp/docs/research/deployment-data/pbx-web-deployment-data-30days.json', 'pbx-web'),
        ('/home/coding/aide-de-camp/docs/research/deployment-data/whisper-stt-deployment-data-30days.json', 'whisper-stt'),

        # Comprehensive deployment events
        ('/home/coding/aide-de-camp/docs/research/deployment-data/deployment-events-30days-comprehensive.json', None),

        # Pod logs index
        ('/home/coding/aide-de-camp/pod-logs-index.jsonl', None),
    ]

    all_processed_events = []

    # Process each data source
    for filepath, default_service in data_sources:
        logger.info(f"Processing: {filepath}")

        if not Path(filepath).exists():
            logger.warning(f"File not found, skipping: {filepath}")
            continue

        # Parse based on file type
        if filepath.endswith('.jsonl'):
            raw_events = parse_jsonl_file(filepath)
        else:
            # Determine service for JSON files
            service = default_service
            if 'pbx-web' in filepath:
                service = 'pbx-web'
            elif 'whisper-stt' in filepath:
                service = 'whisper-stt'

            if service:
                raw_events = parse_deployment_data_file(filepath, service)
            else:
                # For comprehensive files, extract all services
                raw_events = []
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)

                    for svc in ['pbx-web', 'whisper-stt']:
                        if svc in data and 'deployment_events' in data[svc]:
                            for event in data[svc]['deployment_events']:
                                event['service'] = svc
                                raw_events.append(event)
                except Exception as e:
                    logger.error(f"Error parsing {filepath}: {e}")

        # Process events
        for event_data in raw_events:
            try:
                # Determine service for this event
                event_service = default_service
                if 'service' in event_data:
                    event_service = event_data['service']
                elif 'namespace' in event_data:
                    namespace = event_data['namespace']
                    if 'pbx' in namespace:
                        event_service = 'pbx-web'
                    elif 'whisper' in namespace:
                        event_service = 'whisper-stt'

                processed = process_event(event_data, event_service)

                # Only add events with valid timestamps
                if processed['timestamp']:
                    all_processed_events.append(processed)
                else:
                    logger.debug(f"Skipping event with invalid timestamp: {event_data}")

            except Exception as e:
                logger.warning(f"Failed to process event: {e}")
                continue

    # Create DataFrame
    logger.info(f"Creating DataFrame with {len(all_processed_events)} events...")
    df = pd.DataFrame(all_processed_events)

    if df.empty:
        logger.warning("No valid events found!")
        return None

    # Remove raw_data column for cleaner output (keep internal processing)
    output_df = df.drop(columns=['raw_data'])

    # Sort by timestamp
    output_df = output_df.sort_values('timestamp').reset_index(drop=True)

    # Format timestamp for output
    output_df['timestamp'] = output_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S %z')

    # Replace None values with empty strings for cleaner CSV output
    output_df = output_df.fillna('')

    # Output to CSV
    output_file = '/home/coding/aide-de-camp/data/parsed_deployments.csv'
    output_df.to_csv(output_file, index=False)

    logger.info(f"✓ Saved {len(output_df)} deployment events to: {output_file}")

    # Print summary statistics
    logger.info("\n=== Event Summary ===")
    logger.info(f"Total events: {len(output_df)}")
    logger.info(f"Date range: {output_df['timestamp'].min()} to {output_df['timestamp'].max()}")

    logger.info("\nEvents by service:")
    for service, count in output_df['service'].value_counts().items():
        logger.info(f"  {service}: {count}")

    logger.info("\nEvents by type:")
    for event_type, count in output_df['event_type'].value_counts().items():
        logger.info(f"  {event_type}: {count}")

    logger.info("\nEvents by status:")
    for status, count in output_df['status'].value_counts().items():
        logger.info(f"  {status}: {count}")

    return output_df


if __name__ == "__main__":
    df = main()
    if df is not None:
        print(f"\n✓ Parsing complete. Processed {len(df)} deployment events.")
    else:
        print("\n✗ Parsing failed or no events found.")