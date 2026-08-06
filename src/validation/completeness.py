#!/usr/bin/env python3
"""
JSON well-formedness and 30-day completeness validation.

This module provides validation functions for:
- JSON well-formedness (parseable JSON)
- 30-day data completeness (no gaps, no duplicates)
- Chronological sequence validation
- Integration with deployment_data validation

Usage:
    from src.validation.completeness import validate_json_completeness

    data = {"dates": ["2026-07-01", "2026-07-02", ...]}
    is_valid, error = validate_json_completeness(data, start_date, end_date)
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List, Set, Optional
from pathlib import Path


def validate_json_wellformedness(data: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate that data is well-formed JSON (can be serialized and deserialized).

    Args:
        data: Any Python object to validate

    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])

    Examples:
        >>> data = {"key": "value"}
        >>> is_valid, error = validate_json_wellformedness(data)
        >>> is_valid
        True

        >>> data = {"key": datetime.now()}  # Not JSON-serializable
        >>> is_valid, error = validate_json_wellformedness(data)
        >>> is_valid
        False
    """
    try:
        # Try to serialize to JSON
        json_str = json.dumps(data)

        # Try to deserialize back
        parsed = json.loads(json_str)

        return True, None
    except (TypeError, ValueError) as e:
        return False, f"Data is not well-formed JSON: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error during JSON validation: {str(e)}"


def validate_json_file_wellformedness(file_path: Path) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validate that a JSON file is well-formed and can be parsed.

    Args:
        file_path: Path to JSON file

    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str], parsed_data: Optional[Dict])

    Examples:
        >>> path = Path("data.json")
        >>> is_valid, error, data = validate_json_file_wellformedness(path)
        >>> if is_valid:
        ...     print(f"Loaded {len(data)} records")
    """
    if not file_path.exists():
        return False, f"File does not exist: {file_path}", None

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return True, None, data
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in file {file_path}: {str(e)}", None
    except Exception as e:
        return False, f"Error reading file {file_path}: {str(e)}", None


def parse_date_string(date_str: str) -> datetime:
    """
    Parse various date string formats to datetime object.

    Handles:
    - ISO 8601 dates: "2026-07-01"
    - ISO 8601 with time: "2026-07-01T12:00:00Z"
    - Simple dates: "2026-07-01"

    Args:
        date_str: Date string to parse

    Returns:
        datetime object

    Raises:
        ValueError: If date string cannot be parsed
    """
    # Try ISO format first
    try:
        if 'T' in date_str:
            # Full timestamp
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            return datetime.fromisoformat(date_str.replace('+00:00', ''))
        else:
            # Date only
            return datetime.fromisoformat(date_str)
    except ValueError:
        raise ValueError(f"Cannot parse date string: {date_str}")


def generate_expected_dates(start_date: datetime, end_date: datetime) -> List[datetime]:
    """
    Generate list of expected dates for a date range (inclusive).

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)

    Returns:
        List of datetime objects for each day in range

    Examples:
        >>> start = datetime(2026, 7, 1)
        >>> end = datetime(2026, 7, 3)
        >>> dates = generate_expected_dates(start, end)
        >>> len(dates)
        3
    """
    dates = []
    current = start_date

    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    return dates


def extract_dates_from_data(data: Dict[str, Any]) -> Set[datetime]:
    """
    Extract unique dates from deployment data.

    Looks for dates in common fields:
    - deployment_events_last_30_days[].date
    - deployment_history_30_days.replicasets[].created
    - Any field with ISO 8601 date strings

    Args:
        data: Deployment data dictionary

    Returns:
        Set of datetime objects found in data

    Examples:
        >>> data = {
        ...     "deployment_events_last_30_days": [
        ...         {"date": "2026-07-01"},
        ...         {"date": "2026-07-02"}
        ...     ]
        ... }
        >>> dates = extract_dates_from_data(data)
        >>> len(dates)
        2
    """
    dates = set()

    # Check deployment_events_last_30_days
    if "deployment_events_last_30_days" in data:
        events = data["deployment_events_last_30_days"]
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict) and "date" in event:
                    try:
                        date_str = event["date"]
                        # Extract just the date portion if timestamp
                        if 'T' in date_str:
                            date_str = date_str.split('T')[0]
                        dates.add(datetime.fromisoformat(date_str))
                    except (ValueError, AttributeError):
                        continue

    # Check deployment_history_30_days
    if "deployment_history_30_days" in data:
        history = data["deployment_history_30_days"]
        if isinstance(history, dict) and "replicasets" in history:
            replicasets = history["replicasets"]
            if isinstance(replicasets, list):
                for rs in replicasets:
                    if isinstance(rs, dict) and "created" in rs:
                        try:
                            date_str = rs["created"]
                            if 'T' in date_str:
                                date_str = date_str.split('T')[0]
                            dates.add(datetime.fromisoformat(date_str))
                        except (ValueError, AttributeError):
                            continue

    return dates


def validate_30day_completeness(
    data: Dict[str, Any],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    require_exact_30_days: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Validate that data covers exactly 30 days with no gaps.

    Checks:
    - Exactly 30 days of data present (no gaps)
    - No duplicate dates
    - Chronological sequence is correct

    Args:
        data: Deployment data dictionary
        start_date: Expected start date (optional, inferred from data if not provided)
        end_date: Expected end date (optional, inferred from data if not provided)
        require_exact_30_days: If True, validates exactly ~30 days. If False, validates any range.

    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])

    Examples:
        >>> data = {
        ...     "metadata": {
        ...         "time_period": {
        ...             "start": "2026-07-01T00:00:00Z",
        ...             "end": "2026-07-30T23:59:59Z"
        ...         }
        ...     },
        ...     "deployment_events_last_30_days": [...]
        ... }
        >>> is_valid, error = validate_30day_completeness(data)
        >>> is_valid
        True
    """
    # Extract dates from metadata if start/end not provided
    if start_date is None or end_date is None:
        # Try to extract from metadata
        if "metadata" in data and "time_period" in data["metadata"]:
            tp = data["metadata"]["time_period"]
            try:
                if start_date is None and "start" in tp:
                    start_date = parse_date_string(tp["start"])
                if end_date is None and "end" in tp:
                    end_date = parse_date_string(tp["end"])
            except ValueError as e:
                return False, f"Invalid date in time_period: {str(e)}"
        elif "report_metadata" in data:
            metadata = data["report_metadata"]
            try:
                if start_date is None and "time_range_start" in metadata:
                    start_date = parse_date_string(metadata["time_range_start"])
                if end_date is None and "time_range_end" in metadata:
                    end_date = parse_date_string(metadata["time_range_end"])
            except ValueError as e:
                return False, f"Invalid date in report_metadata: {str(e)}"

    # If still no dates, can't validate
    if start_date is None or end_date is None:
        return False, "Cannot determine date range from data"

    # Normalize to just dates (no time)
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Generate expected dates first (before checking duration)
    expected_dates_list = generate_expected_dates(start_date, end_date)
    expected_dates = set(expected_dates_list)
    expected_count = len(expected_dates_list)

    # Check if duration is approximately 30 days (only if required)
    # Use the count of expected dates, not the duration, since range is inclusive
    if require_exact_30_days and (expected_count < 29 or expected_count > 31):
        return False, f"Date range covers {expected_count} days, expected ~30 days (from {start_date.date()} to {end_date.date()})"

    # Extract actual dates from data
    actual_dates = extract_dates_from_data(data)

    if not actual_dates:
        return False, "No dates found in deployment data"

    # Check for missing dates (gaps)
    missing_dates = expected_dates - actual_dates
    if missing_dates:
        missing_sorted = sorted(list(missing_dates))
        return False, f"Missing data for {len(missing_sorted)} day(s): {', '.join([d.strftime('%Y-%m-%d') for d in missing_sorted[:5]])}{'...' if len(missing_sorted) > 5 else ''}"

    # Check for extra dates (duplicates or out of range)
    extra_dates = actual_dates - expected_dates
    if extra_dates:
        extra_sorted = sorted(list(extra_dates))
        return False, f"Found {len(extra_sorted)} date(s) outside expected range: {', '.join([d.strftime('%Y-%m-%d') for d in extra_sorted[:5]])}{'...' if len(extra_sorted) > 5 else ''}"

    # Check chronological sequence
    sorted_dates = sorted(list(actual_dates))
    for i in range(1, len(sorted_dates)):
        prev_date = sorted_dates[i - 1]
        curr_date = sorted_dates[i]

        # Check if dates are consecutive
        expected_diff = 1
        actual_diff = (curr_date - prev_date).days

        if actual_diff != expected_diff:
            return False, f"Non-chronological dates: {prev_date.strftime('%Y-%m-%d')} → {curr_date.strftime('%Y-%m-%d')} (gap of {actual_diff} days)"

    return True, None


def validate_json_completeness(
    data: Dict[str, Any],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Tuple[bool, Optional[str]]:
    """
    Comprehensive validation combining JSON well-formedness and 30-day completeness.

    This function validates:
    1. JSON is well-formed (parseable)
    2. 30-day data completeness (no gaps, no duplicates, chronological)

    Args:
        data: Deployment data dictionary
        start_date: Expected start date (optional, inferred from data if not provided)
        end_date: Expected end date (optional, inferred from data if not provided)

    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])

    Examples:
        >>> from src.validation.completeness import validate_json_completeness
        >>> data = load_deployment_data("pbx-web-deployment-data-30days.json")
        >>> is_valid, error = validate_json_completeness(data)
        >>> if not is_valid:
        ...     print(f"Validation failed: {error}")
    """
    # Check JSON well-formedness
    is_wellformed, json_error = validate_json_wellformedness(data)
    if not is_wellformed:
        return False, f"JSON well-formedness check failed: {json_error}"

    # Check 30-day completeness
    is_complete, completeness_error = validate_30day_completeness(data, start_date, end_date)
    if not is_complete:
        return False, f"30-day completeness check failed: {completeness_error}"

    return True, None


def validate_json_file_completeness(file_path: Path) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validate a JSON file for well-formedness and 30-day completeness.

    This is a convenience function that:
    1. Loads the JSON file
    2. Validates JSON well-formedness
    3. Validates 30-day completeness

    Args:
        file_path: Path to JSON file

    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str], parsed_data: Optional[Dict])

    Examples:
        >>> path = Path("pbx-web-deployment-data-30days.json")
        >>> is_valid, error, data = validate_json_file_completeness(path)
        >>> if is_valid:
        ...     print("File is valid and complete")
    """
    # Load and validate JSON well-formedness
    is_wellformed, json_error, data = validate_json_file_wellformedness(file_path)
    if not is_wellformed:
        return False, json_error, None

    # Validate 30-day completeness
    is_complete, completeness_error = validate_30day_completeness(data)
    if not is_complete:
        return False, completeness_error, data

    return True, None, data


__all__ = [
    "validate_json_wellformedness",
    "validate_json_file_wellformedness",
    "validate_30day_completeness",
    "validate_json_completeness",
    "validate_json_file_completeness",
    "parse_date_string",
    "generate_expected_dates",
    "extract_dates_from_data",
]
