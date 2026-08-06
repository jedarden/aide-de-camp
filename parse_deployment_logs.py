#!/usr/bin/env python3
"""
Parse deployment logs for pbx-web and whisper-stt services.

This module loads deployment data from JSON files, extracts deployment timestamps,
and creates a validated pandas DataFrame for analysis.
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple


def parse_pbx_web_deployments(file_path: str) -> List[Dict[str, str]]:
    """
    Parse deployment events from pbx-web deployment data JSON file.

    Args:
        file_path: Path to pbx-web deployment data JSON file

    Returns:
        List of dictionaries with service_name and deployment_time keys
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    deployments = []
    events = data.get('deployment_events_last_30_days', [])

    for event in events:
        deployment_time = event.get('timestamp')
        if deployment_time:
            deployments.append({
                'service_name': 'pbx-web',
                'deployment_time': deployment_time
            })

    return deployments


def parse_whisper_stt_deployments(file_path: str) -> List[Dict[str, str]]:
    """
    Parse deployment events from whisper-stt deployment data JSON file.

    Args:
        file_path: Path to whisper-stt deployment data JSON file

    Returns:
        List of dictionaries with service_name and deployment_time keys
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    deployments = []
    replicasets = data.get('deployment_history_30_days', {}).get('replicasets', [])

    for rs in replicasets:
        created_time = rs.get('created')
        if created_time:
            deployments.append({
                'service_name': 'whisper-stt',
                'deployment_time': created_time
            })

    return deployments


def validate_timestamp(timestamp_str: str) -> bool:
    """
    Validate ISO 8601 timestamp string.

    Args:
        timestamp_str: String to validate as ISO 8601 timestamp

    Returns:
        True if valid timestamp, False otherwise
    """
    if not timestamp_str or not isinstance(timestamp_str, str):
        return False

    try:
        # Handle various ISO formats
        ts = timestamp_str
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        datetime.fromisoformat(ts.replace('+00:00', ''))
        return True
    except (ValueError, AttributeError):
        return False


def load_deployment_logs(
    pbx_web_file: str = '/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json',
    whisper_stt_file: str = '/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json'
) -> pd.DataFrame:
    """
    Load and parse deployment logs for both services.

    Args:
        pbx_web_file: Path to pbx-web deployment data file
        whisper_stt_file: Path to whisper-stt deployment data file

    Returns:
        Validated pandas DataFrame with columns: service_name, deployment_time
    """
    # Parse deployments from both services
    pbx_deployments = parse_pbx_web_deployments(pbx_web_file)
    whisper_deployments = parse_whisper_stt_deployments(whisper_stt_file)

    # Combine all deployments
    all_deployments = pbx_deployments + whisper_deployments

    # Create DataFrame
    df = pd.DataFrame(all_deployments)

    return df


def validate_deployment_data(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Perform data quality checks on deployment DataFrame.

    Args:
        df: DataFrame with deployment data (deployment_time should be datetime)

    Returns:
        Tuple of (is_valid: bool, validation_message: str)
    """
    if df.empty:
        return False, "DataFrame is empty - no deployment events found"

    # Check for null values
    null_counts = df.isnull().sum()
    if null_counts['deployment_time'] > 0:
        return False, f"Found {null_counts['deployment_time']} null deployment times"

    if null_counts['service_name'] > 0:
        return False, f"Found {null_counts['service_name']} null service names"

    # Check for NaT (Not a Time) values which result from failed datetime parsing
    nat_count = df['deployment_time'].isna().sum()
    if nat_count > 0:
        return False, f"Found {nat_count} invalid timestamps that couldn't be parsed"

    # Check for duplicate rows
    duplicates = df.duplicated().sum()
    if duplicates > 0:
        return False, f"Found {duplicates} duplicate deployment events"

    # Verify datetime type
    if not pd.api.types.is_datetime64_any_dtype(df['deployment_time']):
        return False, "deployment_time column is not datetime type"

    return True, "Data quality validation passed"


def main():
    """
    Main function to load, parse, and validate deployment logs.
    """
    print("=" * 60)
    print("Loading and Parsing Deployment Logs")
    print("=" * 60)

    # Load deployment logs
    print("\n1. Loading deployment data from JSON files...")
    df = load_deployment_logs()

    print(f"   ✓ Loaded {len(df)} deployment events")

    # Parse deployment times to datetime
    print("\n2. Converting deployment timestamps to datetime...")
    df['deployment_time'] = pd.to_datetime(df['deployment_time'], errors='coerce')

    # Sort by deployment time
    df = df.sort_values('deployment_time')

    print(f"   ✓ Converted {len(df)} timestamps")
    print(f"   Date range: {df['deployment_time'].min()} to {df['deployment_time'].max()}")

    # Data quality checks
    print("\n3. Performing data quality validation...")
    is_valid, message = validate_deployment_data(df)

    if is_valid:
        print(f"   ✓ {message}")
    else:
        print(f"   ✗ Validation failed: {message}")
        return

    # Show deployments by service
    print("\n4. Deployment summary by service:")
    service_counts = df['service_name'].value_counts()
    for service, count in service_counts.items():
        print(f"   {service}: {count} deployments")

    # Show sample data
    print("\n5. Sample deployment data (first 5 rows):")
    print(df.head().to_string(index=False))

    print("\n6. DataFrame schema:")
    print(df.dtypes.to_string())

    print("\n" + "=" * 60)
    print("✓ Deployment log parsing complete")
    print("=" * 60)

    return df


if __name__ == "__main__":
    df = main()

    # Save to CSV for further analysis
    if df is not None and not df.empty:
        output_file = '/home/coding/aide-de-camp/deployment_logs_parsed.csv'
        df.to_csv(output_file, index=False)
        print(f"\n✓ Saved parsed deployment data to: {output_file}")
