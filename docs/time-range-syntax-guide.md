# Time Range Syntax and Usage Guide

This guide documents how time ranges are specified in queries for the aide-de-camp infrastructure analysis system, including syntax examples for 30-day windows and timezone handling.

## Overview

Time ranges in queries use ISO 8601 timestamp format with UTC timezone. All time-based queries specify a start time, end time, and duration in days.

## Time Range Parameter Syntax

### Standard Time Range Structure

```python
time_range = {
    "start": "2026-07-07T00:00:00Z",    # Start timestamp (inclusive)
    "end": "2026-08-06T23:59:59Z",      # End timestamp (inclusive)  
    "days": 30                           # Duration in days
}
```

### Field Descriptions

- **start**: ISO 8601 UTC timestamp for the beginning of the analysis period (inclusive)
- **end**: ISO 8601 UTC timestamp for the end of the analysis period (inclusive)
- **days**: Integer representing the total duration in days

## Time Range Specification Methods

### Method 1: Fixed Date Range (Absolute)

Specify exact start and end timestamps:

```python
time_range = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
}
```

Use case: Historical analysis for a specific period

### Method 2: Relative to Current Date

Calculate time range relative to when the query runs:

```python
from datetime import datetime, timedelta

end_date = datetime.now(timezone.utc)
start_date = end_date - timedelta(days=30)

time_range = {
    "start": start_date.strftime("%Y-%m-%dT00:00:00Z"),
    "end": end_date.strftime("%Y-%m-%dT23:59:59Z"),
    "days": 30
}
```

Use case: Rolling window analysis (last 30 days from now)

### Method 3: Date Filtering

Simple cutoff date for filtering workflows/events:

```python
cutoff_date = "2026-07-07"  # YYYY-MM-DD format
# Filter condition: creation_timestamp >= cutoff_date
```

Use case: Kubernetes workflow filtering, event log filtering

## 30-Day Window Specifications

### Standard 30-Day Window Pattern

```python
ANALYSIS_PERIOD_30D = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z", 
    "days": 30
}
```

### Calculated 30-Day Window

```python
from datetime import datetime, timedelta, timezone

def create_30day_window(end_date: datetime = None) -> dict:
    """Create a 30-day time range window."""
    if end_date is None:
        end_date = datetime.now(timezone.utc)
    
    start_date = end_date - timedelta(days=30)
    
    return {
        "start": start_date.strftime("%Y-%m-%dT00:00:00Z"),
        "end": end_date.strftime("%Y-%m-%dT23:59:59Z"),
        "days": 30
    }

# Usage
current_window = create_30day_window()
custom_window = create_30day_window(datetime(2026, 8, 6, tzinfo=timezone.utc))
```

### Custom Day Windows

```python
def create_day_window(days: int, end_date: datetime = None) -> dict:
    """Create a custom day time range window."""
    if end_date is None:
        end_date = datetime.now(timezone.utc)
    
    start_date = end_date - timedelta(days=days)
    
    return {
        "start": start_date.strftime("%Y-%m-%dT00:00:00Z"),
        "end": end_date.strftime("%Y-%m-%dT23:59:59Z"),
        "days": days
    }

# Examples
7_day_window = create_day_window(7)
14_day_window = create_day_window(14)
90_day_window = create_day_window(90)
```

## Timezone Considerations

### UTC as Standard Timezone

All timestamps use **UTC (Coordinated Universal Time)** as the standard timezone:

```python
from datetime import datetime, timezone

# Always use UTC for timestamp creation
utc_now = datetime.now(timezone.utc)
utc_timestamp = utc_now.strftime("%Y-%m-%dT%H:%M:%SZ")  
# Result: "2026-08-06T14:30:00Z"
```

### ISO 8601 UTC Timestamp Format

The system uses ISO 8601 format with `Z` suffix to indicate UTC:

```
Format: YYYY-MM-DDTHH:MM:SSZ
Example: 2026-08-06T14:30:00Z
         │││││││││││││││││││││
         │││││││││││││││││└┴┴┴ UTC indicator
         ││││││││││└┴┴┴┴┴┴┴┴┴┴┴┴┴ Seconds (00-59)
         ││││││└┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴ Minutes (00-59)
         ││││└┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴ Hours (00-23)
         └┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴┴ Date separator
```

The `Z` suffix explicitly indicates UTC timezone (zero offset from UTC).

### Timezone-Aware datetime Objects

Always use timezone-aware datetime objects:

```python
from datetime import datetime, timezone

# CORRECT: timezone-aware datetime
utc_datetime = datetime.now(timezone.utc)
timestamp = utc_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

# INCORRECT: naive datetime (missing timezone)
naive_datetime = datetime.now()  # No timezone information
```

### Parsing ISO 8601 Timestamps

When parsing timestamps from data sources, explicitly handle timezone information:

```python
from datetime import datetime, timezone

def parse_utc_timestamp(timestamp_str: str) -> datetime:
    """
    Parse ISO 8601 timestamp string and ensure UTC timezone.
    
    Args:
        timestamp_str: ISO 8601 timestamp (e.g., "2026-08-06T14:30:00Z")
    
    Returns:
        Timezone-aware datetime object in UTC
    """
    # Remove 'Z' suffix if present
    ts_clean = timestamp_str.rstrip('Z')
    
    # Parse and explicitly set UTC timezone
    dt = datetime.fromisoformat(ts_clean)
    return dt.replace(tzinfo=timezone.utc)

# Example
timestamp = "2026-08-06T14:30:00Z"
dt = parse_utc_timestamp(timestamp)
# Result: datetime.datetime(2026, 8, 6, 14, 30, tzinfo=datetime.timezone.utc)
```

### Timezone Filtering in Queries

When filtering data by time range, ensure timezone-aware comparisons:

```python
def filter_by_time_range(data: list, start_ts: str, end_ts: str) -> list:
    """
    Filter data entries by time range with timezone-aware comparisons.
    
    Args:
        data: List of entries with 'timestamp' field
        start_ts: ISO 8601 start timestamp (UTC)
        end_ts: ISO 8601 end timestamp (UTC)
    
    Returns:
        Filtered list of entries within time range
    """
    start_dt = parse_utc_timestamp(start_ts)
    end_dt = parse_utc_timestamp(end_ts)
    
    filtered = []
    for entry in data:
        ts = entry.get('timestamp')
        if ts:
            # Parse timestamp with timezone
            entry_dt = parse_utc_timestamp(ts)
            
            # Compare timezone-aware datetime objects
            if start_dt <= entry_dt <= end_dt:
                filtered.append(entry)
    
    return filtered
```

## Time Range Examples

### Example 1: Fixed Historical Period

```python
# Analyze specific historical 30-day period
historical_period = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
}

# Use in query
metrics = query_service_metrics("pbx-web", historical_period)
```

### Example 2: Rolling Window (Last 30 Days)

```python
# Analyze last 30 days from now
rolling_window = create_30day_window()

# Use in query
metrics = query_service_metrics("whisper-stt", rolling_window)
```

### Example 3: Custom Date Range

```python
# Analyze specific period (e.g., incident investigation)
incident_period = {
    "start": "2026-08-01T00:00:00Z",
    "end": "2026-08-03T23:59:59Z",
    "days": 3
}

# Use in query
metrics = query_service_metrics("pbx-web", incident_period)
```

### Example 4: Kubernetes Workflow Filtering

```python
# Filter workflows by creation date
cutoff_date = "2026-07-07"  # YYYY-MM-DD format

def filter_workflows_by_time(workflows: list, cutoff_date: str) -> list:
    """Filter workflows created on or after cutoff_date."""
    cutoff_dt = datetime.fromisoformat(cutoff_date).replace(tzinfo=timezone.utc)
    
    filtered = []
    for workflow in workflows:
        creation_ts = workflow.get('metadata', {}).get('creationTimestamp')
        if creation_ts:
            created_dt = datetime.fromisoformat(creation_ts.rstrip('Z'))
            if created_dt >= cutoff_dt:
                filtered.append(workflow)
    
    return filtered

# Usage
recent_workflows = filter_workflows_by_time(all_workflows, cutoff_date)
```

## Timezone Best Practices

### 1. Always Use UTC for Storage
Store all timestamps in UTC timezone to ensure consistency across systems.

### 2. Use Timezone-Aware datetime Objects
Never use naive datetime objects for comparisons or calculations.

```python
# CORRECT
utc_dt = datetime.now(timezone.utc)

# INCORRECT  
naive_dt = datetime.now()
```

### 3. Explicitly Parse with Timezone
When reading timestamps, always ensure timezone information is preserved.

```python
# CORRECT
dt = datetime.fromisoformat(ts.rstrip('Z')).replace(tzinfo=timezone.utc)

# INCORRECT (loses timezone)
dt = datetime.fromisoformat(ts)
```

### 4. Include 'Z' Suffix When Formatting
Use 'Z' suffix to explicitly indicate UTC timezone.

```python
timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

### 5. Validate Timezone Before Comparisons
Ensure both datetime objects have timezone info before comparing.

```python
# This will raise TypeError if one is naive
if start_dt <= entry_dt <= end_dt:
    filtered.append(entry)
```

## Common Timezone Pitfalls

### Pitfall 1: Comparing Naive and Aware Objects

```python
# INCORRECT: This raises TypeError
naive_dt = datetime.now()
aware_dt = datetime.now(timezone.utc)
if naive_dt < aware_dt:  # TypeError!
    pass

# CORRECT: Both objects timezone-aware
aware_dt1 = datetime.now(timezone.utc)
aware_dt2 = datetime.now(timezone.utc)
if aware_dt1 < aware_dt2:  # Works correctly
    pass
```

### Pitfall 2: Losing Timezone During Parsing

```python
# INCORRECT: Loses timezone information  
ts = "2026-08-06T14:30:00Z"
dt = datetime.fromisoformat(ts)  # No timezone info after parsing 'Z'

# CORRECT: Preserves timezone information
ts = "2026-08-06T14:30:00Z"
dt = datetime.fromisoformat(ts.rstrip('Z')).replace(tzinfo=timezone.utc)
```

### Pitfall 3: Assuming Local Timezone

```python
# INCORRECT: Assumes system local timezone
local_dt = datetime.now()

# CORRECT: Explicitly uses UTC
utc_dt = datetime.now(timezone.utc)
```

## Integration with Query Examples

### Complete 30-Day Query with Time Range

```python
from datetime import datetime, timedelta, timezone
import json

def query_service_with_timerange(service: str, time_range: dict) -> dict:
    """Query service metrics with specified time range."""
    
    return {
        "service": service,
        "time_range": time_range,
        "error_metrics": {
            "http_errors": {
                "http_5xx_errors": 42,
                "http_4xx_errors": 158,
                "http_total_requests": 12500,
                "http_5xx_error_rate": 42 / 12500,
                "http_4xx_error_rate": 158 / 12500
            },
            "deployment_errors": {
                "total_deployments": 24,
                "failed_deployments": 2,
                "deployment_error_rate": 2 / 24,
                "deployment_success_rate": 22 / 24
            }
        },
        "latency_metrics": {
            "response_times": {
                "mean": 97.2,
                "p50": 55,
                "p95": 312
            }
        },
        "query_timestamp": datetime.now(timezone.utc).isoformat()
    }

# Execute 30-day query
time_range_30d = create_30day_window()
results = query_service_with_timerange("pbx-web", time_range_30d)
print(json.dumps(results, indent=2))
```

## Related Documentation

- [Query Patterns and Time Ranges](query-patterns-and-time-ranges.md) - Comprehensive patterns and advanced usage
- [30-Day Query Quick Reference](query-quick-reference-30d.md) - Concise examples for common queries
- [Metrics Aggregation Functions](metrics-aggregation-functions.md) - Victorialogs/Prometheus functions

## Summary

| Aspect | Specification | Example |
|--------|--------------|---------|
| **Format** | ISO 8601 with 'Z' suffix | `"2026-08-06T14:30:00Z"` |
| **Timezone** | UTC only | `datetime.now(timezone.utc)` |
| **30-day pattern** | Fixed or calculated | See `create_30day_window()` |
| **Parsing** | Preserve timezone | `parse_utc_timestamp()` |
| **Filtering** | Timezone-aware comparison | `filter_by_time_range()` |

Time ranges in the aide-de-camp system use UTC timestamps with ISO 8601 format, support both fixed and relative specifications, and require timezone-aware datetime handling for correctness.