# Query Patterns and Time Range Syntax

This document provides comprehensive guidance on constructing queries with 30-day time ranges for error rates and latency metrics in the aide-de-camp infrastructure analysis system.

## Time Range Syntax

### Standard 30-Day Period Format

The system uses ISO 8601 timestamp format for specifying time ranges:

```python
ANALYSIS_PERIOD = {
    "start": "2026-07-07T00:00:00Z",    # Start date (inclusive)
    "end": "2026-08-06T23:59:59Z",       # End date (inclusive)
    "days": 30                           # Duration in days
}
```

### Time Range Construction

```python
from datetime import datetime, timedelta

# Method 1: Fixed date range
time_range = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
}

# Method 2: Relative to current date
end_date = datetime.now()
start_date = end_date - timedelta(days=30)

time_range = {
    "start": start_date.strftime("%Y-%m-%dT00:00:00Z"),
    "end": end_date.strftime("%Y-%m-%dT23:59:59Z"),
    "days": 30
}

# Method 3: Date filtering (for workflows/events)
cutoff_date = "2026-07-07"  # YYYY-MM-DD format
# Filter condition: creation_timestamp >= cutoff_date
```

## Error Rate Query Patterns

### 1. HTTP Error Rates (from nginx logs)

```python
# Query pattern for HTTP error rates
def query_http_error_rates(service: str, time_range: dict) -> dict:
    """
    Collect HTTP 5xx and 4xx error rates from nginx logs.
    
    Returns:
        {
            "http_5xx_errors": int,
            "http_4xx_errors": int,
            "http_total_requests": int,
            "http_5xx_error_rate": float,  # 5xx / total
            "http_4xx_error_rate": float   # 4xx / total
        }
    """
```

**Example Query:**
```python
# For pbx-web service over 30 days
nginx_metrics = {
    "http_5xx_errors": 42,
    "http_4xx_errors": 158,
    "http_total_requests": 12500,
    "http_5xx_error_rate": 42 / 12500,  # 0.00336 (0.34%)
    "http_4xx_error_rate": 158 / 12500  # 0.01264 (1.26%)
}
```

### 2. Application Error Rates (from pod logs)

```python
# Query pattern for application errors
def query_application_error_rates(service: str, time_range: dict) -> dict:
    """
    Collect error counts from pod log analysis files.
    
    Returns:
        {
            "total_pods_analyzed": int,
            "pods_with_errors": int,
            "total_error_count": int,
            "error_rate_per_pod": float,  # errors / pods
            "error_rate_per_day": float   # errors / 30
        }
    """
```

**Example Query:**
```python
# For whisper-stt service over 30 days
pod_errors = {
    "total_pods_analyzed": 8,
    "pods_with_errors": 3,
    "total_error_count": 127,
    "error_rate_per_pod": 127 / 8,      # 15.875 errors/pod
    "error_rate_per_day": 127 / 30      # 4.23 errors/day
}
```

### 3. Deployment Error Rates

```python
# Query pattern for deployment success/failure rates
def query_deployment_error_rates(service: str, time_range: dict) -> dict:
    """
    Collect deployment success and failure metrics.
    
    Returns:
        {
            "total_deployments": int,
            "successful_deployments": int,
            "failed_deployments": int,
            "deployment_error_rate": float,      # failed / total
            "deployment_success_rate": float     # successful / total
        }
    """
```

**Example Query:**
```python
# For pbx-web deployments over 30 days
deployment_metrics = {
    "total_deployments": 24,
    "successful_deployments": 22,
    "failed_deployments": 2,
    "deployment_error_rate": 2 / 24,     # 0.083 (8.3%)
    "deployment_success_rate": 22 / 24   # 0.917 (91.7%)
}
```

### 4. OOM Kill Error Rates

```python
# Query pattern for OOM (Out of Memory) kill rates
def query_oom_kill_rates(service: str, time_range: dict) -> dict:
    """
    Collect OOM kill metrics from pod logs.
    
    Returns:
        {
            "pods_with_oom_kills": int,
            "total_oom_kill_count": int,
            "oom_kill_rate_per_pod": float,
            "oom_kills_per_day": float
        }
    """
```

**Example Query:**
```python
# For whisper-stt service over 30 days
oom_metrics = {
    "pods_with_oom_kills": 2,
    "total_oom_kill_count": 5,
    "oom_kill_rate_per_pod": 5 / 8,      # 0.625 kills/pod
    "oom_kills_per_day": 5 / 30          # 0.167 kills/day
}
```

## Latency Metrics Query Patterns

### 1. Response Time Percentiles (from nginx logs)

```python
# Query pattern for HTTP response times
def query_response_times(service: str, time_range: dict) -> dict:
    """
    Collect response time metrics from nginx logs.
    
    Returns:
        {
            "response_time_stats": {
                "count": int,
                "mean": float,
                "median": float,
                "p50": float,
                "p95": float,
                "min": float,
                "max": float
            }
        }
    """
```

**Example Query:**
```python
# For pbx-web response times over 30 days
response_time_metrics = {
    "response_time_stats": {
        "count": 12500,
        "mean": 245.5,        # 245.5ms average
        "median": 198.0,
        "p50": 198.0,         # 50th percentile
        "p95": 512.0,         # 95th percentile
        "min": 45.0,
        "max": 2500.0
    }
}
```

### 2. Deployment Duration Percentiles

```python
# Query pattern for deployment timing
def query_deployment_durations(service: str, time_range: dict) -> dict:
    """
    Collect deployment duration metrics.
    
    Returns:
        {
            "deployment_times": [float],
            "timing_stats": {
                "count": int,
                "mean": float,
                "p50": float,
                "p95": float
            }
        }
    """
```

**Example Query:**
```python
# For whisper-stt deployments over 30 days
deployment_timing = {
    "deployment_times": [45.2, 52.1, 38.9, 61.5, 42.3],  # seconds
    "timing_stats": {
        "count": 5,
        "mean": 48.0,         # 48 seconds average
        "p50": 45.2,
        "p95": 61.5,
        "min": 38.9,
        "max": 61.5
    }
}
```

### 3. Application Processing Latency

```python
# Query pattern for application timing from logs
def query_application_timing(service: str, time_range: dict) -> dict:
    """
    Extract timing information from application log timestamps.
    
    Returns:
        {
            "timestamp_deltas": [float],     # time between log entries
            "delta_stats": {
                "mean": float,
                "p50": float,
                "p95": float
            }
        }
    """
```

**Example Query:**
```python
# For pbx-web application processing over 30 days
app_timing = {
    "timestamp_deltas": [0.125, 0.089, 0.234, 0.156],  # seconds
    "delta_stats": {
        "count": 4,
        "mean": 0.151,        # 151ms average processing time
        "p50": 0.141,
        "p95": 0.234,
        "min": 0.089,
        "max": 0.234
    }
}
```

## Aggregation Functions

### Rate Calculation

```python
def rate(count: int, total: int) -> float:
    """Calculate rate as ratio."""
    if total == 0:
        return 0.0
    return count / total

# Examples
error_rate = rate(42, 12500)      # 0.00336
success_rate = rate(22, 24)       # 0.917
```

### Average (Mean) Calculation

```python
import statistics

def avg(values: list) -> float:
    """Calculate arithmetic mean."""
    if not values:
        return 0.0
    return statistics.mean(values)

# Example
avg_time = avg([45.2, 52.1, 38.9, 61.5, 42.3])  # 48.0
```

### Percentile Calculation

```python
import statistics

def percentile(values: list, p: float) -> float:
    """
    Calculate percentile value.
    
    Args:
        values: List of numeric values
        p: Percentile (0.0 to 1.0)
    
    Returns:
        Percentile value
    """
    if not values:
        return 0.0
    sorted_values = sorted(values)
    n = len(sorted_values)
    index = int(n * p)
    return sorted_values[min(index, n - 1)]

# Examples
p50 = percentile([45, 52, 39, 61, 42], 0.50)  # 45 (median)
p95 = percentile([45, 52, 39, 61, 42], 0.95)  # 61 (95th percentile)
```

### Median Calculation

```python
def median(values: list) -> float:
    """Calculate median value."""
    if not values:
        return 0.0
    return statistics.median(values)

# Example
median_time = median([45.2, 52.1, 38.9, 61.5, 42.3])  # 45.2
```

## Complete 30-Day Query Example

```python
#!/usr/bin/env python3
"""
Complete example: Query error rates and latency for 30-day period.
"""

from datetime import datetime, timedelta
import json
from pathlib import Path

# Define 30-day time range
ANALYSIS_PERIOD = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
}

def query_service_metrics(service: str, time_range: dict) -> dict:
    """
    Query all metrics for a service over the specified time range.
    
    Args:
        service: Service name ('pbx-web' or 'whisper-stt')
        time_range: Time range dict with 'start', 'end', 'days'
    
    Returns:
        Complete metrics dictionary with error rates and latency
    """
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
            "application_errors": {
                "total_error_count": 127,
                "error_rate_per_day": 127 / time_range["days"]
            },
            "deployment_errors": {
                "total_deployments": 24,
                "failed_deployments": 2,
                "deployment_error_rate": 2 / 24,
                "deployment_success_rate": 22 / 24
            },
            "oom_kills": {
                "total_oom_kill_count": 5,
                "oom_kills_per_day": 5 / time_range["days"]
            }
        },
        "latency_metrics": {
            "response_times": {
                "mean": 245.5,
                "p50": 198.0,
                "p95": 512.0
            },
            "deployment_durations": {
                "mean": 48.0,
                "p50": 45.2,
                "p95": 61.5
            },
            "application_timing": {
                "mean": 0.151,
                "p50": 0.141,
                "p95": 0.234
            }
        }
    }

# Execute query
results = query_service_metrics("pbx-web", ANALYSIS_PERIOD)
print(json.dumps(results, indent=2))
```

## Data Sources and File Locations

### Pod Logs
```
/home/coding/aide-de-camp/research/{service}-30days/pod-logs/
├── {pod-name}-analysis.json     # Pre-analyzed error patterns
└── {pod-name}.log               # Raw log files
```

### Deployment Data
```
/home/coding/aide-de-camp/research/
├── {service}-deployments-30days.json
└── {service}-30days/deployments-30days.json
```

### Output Files
```
/home/coding/aide-de-camp/data/
├── error_latency_metrics_30d_{timestamp}.json
└── error_latency_metrics_30d_enhanced_{timestamp}.json
```

## Time Filtering in Queries

### Kubernetes Workflows
```python
# Filter workflows by creation timestamp
def filter_workflows_by_time(workflows: list, cutoff_date: str) -> list:
    """
    Filter workflows to those created on or after cutoff_date.
    
    Args:
        workflows: List of workflow objects
        cutoff_date: YYYY-MM-DD format string
    
    Returns:
        Filtered list of workflows
    """
    cutoff_dt = datetime.fromisoformat(cutoff_date).replace(tzinfo=timezone.utc)
    
    filtered = []
    for workflow in workflows:
        creation_ts = workflow.get('metadata', {}).get('creationTimestamp')
        if creation_ts:
            created_dt = datetime.fromisoformat(creation_ts.rstrip('Z'))
            if created_dt >= cutoff_dt:
                filtered.append(workflow)
    
    return filtered
```

### Log Entries by Timestamp
```python
# Filter log entries by time range
def filter_logs_by_time(log_entries: list, start: str, end: str) -> list:
    """
    Filter log entries within time range.
    
    Args:
        log_entries: List of log entry dicts with 'timestamp' field
        start: ISO 8601 start timestamp
        end: ISO 8601 end timestamp
    
    Returns:
        Filtered list of log entries
    """
    start_dt = datetime.fromisoformat(start.rstrip('Z'))
    end_dt = datetime.fromisoformat(end.rstrip('Z'))
    
    filtered = []
    for entry in log_entries:
        ts = entry.get('timestamp')
        if ts:
            entry_dt = datetime.fromisoformat(ts.rstrip('Z'))
            if start_dt <= entry_dt <= end_dt:
                filtered.append(entry)
    
    return filtered
```

## Usage Examples

### Query 1: Error Rate Summary for 30 Days
```python
from query_error_latency_metrics import ErrorLatencyMetricsCollector

collector = ErrorLatencyMetricsCollector("pbx-web")
metrics = collector.collect_all_metrics()

# Access error rates
print(f"HTTP 5xx Error Rate: {metrics['error_metrics']['nginx']['http_5xx_error_rate']:.2%}")
print(f"Deployment Success Rate: {metrics['error_metrics']['overall']['deployment_success_rate']:.2%}")
```

### Query 2: Latency Percentiles for 30 Days
```python
latency = metrics['latency_metrics']

if 'nginx_response_times' in latency:
    stats = latency['nginx_response_times']
    print(f"Response Time p50: {stats['p50']:.0f}ms")
    print(f"Response Time p95: {stats['p95']:.0f}ms")

if 'deployment_durations' in latency:
    stats = latency['deployment_durations']
    print(f"Deployment Duration p50: {stats['p50']:.1f}s")
    print(f"Deployment Duration p95: {stats['p95']:.1f}s")
```

### Query 3: Combined Error and Latency Query
```python
from query_error_latency_metrics_enhanced import EnhancedErrorLatencyMetricsCollector

collector = EnhancedErrorLatencyMetricsCollector("whisper-stt")
metrics = collector.collect_all_metrics()

# Print comprehensive results
print(f"Service: {metrics['service']}")
print(f"Time Range: {metrics['analysis_period']['start']} to {metrics['analysis_period']['end']}")
print(f"Total Errors: {metrics['error_metrics']['overall']['total_errors_all_sources']}")
print(f"Error Rate/Day: {metrics['error_metrics']['overall']['error_rate_per_day']:.2f}")
```

## Testing Queries

### Verify Data Availability
```python
def verify_query_data(service: str, time_range: dict) -> dict:
    """
    Verify that required data files exist for the query.
    
    Returns:
        Dict with data availability status
    """
    service_dir = Path(f"/home/coding/aide-de-camp/research/{service}-30days")
    
    checks = {
        "pod_logs_dir": (service_dir / "pod-logs").exists(),
        "deployment_file": (service_dir / "deployments-30days.json").exists(),
        "nginx_logs": list((service_dir / "pod-logs").glob("*nginx*.log")),
        "analysis_files": list((service_dir / "pod-logs").glob("*-analysis.json"))
    }
    
    checks["data_available"] = all([
        checks["pod_logs_dir"],
        len(checks["nginx_logs"]) > 0,
        len(checks["analysis_files"]) > 0
    ])
    
    return checks

# Test data availability
availability = verify_query_data("pbx-web", ANALYSIS_PERIOD)
print(f"Data Available: {availability['data_available']}")
```

### Run Query with Validation
```python
def run_validated_query(service: str, time_range: dict) -> dict:
    """
    Run query with data validation and gap reporting.
    
    Returns:
        Metrics dict with data gaps reported
    """
    # Verify data availability
    availability = verify_query_data(service, time_range)
    
    if not availability["data_available"]:
        return {
            "error": "Insufficient data for query",
            "availability": availability
        }
    
    # Run query
    collector = ErrorLatencyMetricsCollector(service)
    metrics = collector.collect_all_metrics()
    
    # Add data availability info
    metrics["data_availability"] = availability
    metrics["data_gaps_count"] = len(metrics.get("data_gaps", []))
    
    return metrics

# Execute validated query
results = run_validated_query("pbx-web", ANALYSIS_PERIOD)
if "error" in results:
    print(f"Query failed: {results['error']}")
else:
    print(f"Query successful with {results['data_gaps_count']} data gaps")
```

## Time Zone Considerations

### UTC as Standard Time Zone

All timestamps in the aide-de-camp system use **UTC (Coordinated Universal Time)** as the standard time zone:

```python
from datetime import datetime, timezone

# Always use UTC for timestamp creation
utc_now = datetime.now(timezone.utc)
utc_timestamp = utc_now.strftime("%Y-%m-%dT%H:%M:%SZ")  # 2026-08-06T14:30:00Z
```

### ISO 8601 UTC Timestamp Format

The system uses ISO 8601 format with `Z` suffix to indicate UTC:

```
Format: YYYY-MM-DDTHH:MM:SSZ
Example: 2026-08-06T14:30:00Z
```

The `Z` suffix explicitly indicates UTC time zone (zero offset from UTC).

### Time Zone-Aware datetime Objects

When working with datetime objects in Python, always use timezone-aware objects:

```python
from datetime import datetime, timezone

# CORRECT: timezone-aware datetime
utc_datetime = datetime.now(timezone.utc)
timestamp = utc_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")

# INCORRECT: naive datetime (no timezone info)
naive_datetime = datetime.now()  # Missing timezone information
```

### Parsing ISO 8601 Timestamps with Time Zone

When parsing timestamps from data sources, explicitly handle timezone information:

```python
from datetime import datetime, timezone

# Parse ISO 8601 timestamp and ensure UTC
def parse_utc_timestamp(timestamp_str: str) -> datetime:
    """
    Parse ISO 8601 timestamp string and ensure UTC timezone.
    
    Args:
        timestamp_str: ISO 8601 timestamp (e.g., "2026-08-06T14:30:00Z")
    
    Returns:
        timezone-aware datetime object in UTC
    """
    # Remove 'Z' suffix if present
    ts_clean = timestamp_str.rstrip('Z')
    
    # Parse and explicitly set UTC timezone
    dt = datetime.fromisoformat(ts_clean)
    return dt.replace(tzinfo=timezone.utc)

# Example usage
timestamp = "2026-08-06T14:30:00Z"
dt = parse_utc_timestamp(timestamp)
print(dt)  # 2026-08-06 14:30:00+00:00
```

### Handling Timezone-Aware Comparisons

When comparing timestamps, ensure both datetime objects are timezone-aware:

```python
from datetime import datetime, timezone

def filter_by_time_range(data: list, start_ts: str, end_ts: str) -> list:
    """
    Filter data entries by time range with timezone-aware comparisons.
    
    Args:
        data: List of entries with 'timestamp' field
        start_ts: ISO 8601 start timestamp (UTC)
        end_ts: ISO 8601 end timestamp (UTC)
    
    Returns:
        Filtered list of entries
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

### Time Zone Best Practices

1. **Always use UTC for storage** - Store all timestamps in UTC timezone
2. **Use timezone-aware datetime objects** - Never use naive datetime objects
3. **Explicitly parse with timezone** - When reading timestamps, always ensure timezone info
4. **Include 'Z' suffix** - When formatting timestamps, use 'Z' to indicate UTC
5. **Validate timezone before comparisons** - Ensure both objects have timezone info before comparing

### Common Time Zone Pitfalls

**Pitfall 1: Comparing naive and aware datetime objects**
```python
# INCORRECT: This will raise TypeError
naive_dt = datetime.now()
aware_dt = datetime.now(timezone.utc)
if naive_dt < aware_dt:  # TypeError: can't compare offset-naive and offset-aware datetimes
    pass
```

**Pitfall 2: Losing timezone information during parsing**
```python
# INCORRECT: Loses timezone information
ts = "2026-08-06T14:30:00Z"
dt = datetime.fromisoformat(ts)  # No timezone info after parsing 'Z'

# CORRECT: Preserve timezone information
ts = "2026-08-06T14:30:00Z"
dt = datetime.fromisoformat(ts.rstrip('Z')).replace(tzinfo=timezone.utc)
```

### Kubernetes Time Zone Handling

Kubernetes timestamps are returned in UTC by default:

```python
# Kubernetes creationTimestamp format
creation_timestamp = "2026-08-06T14:30:00Z"

# Parse with timezone
dt = parse_utc_timestamp(creation_timestamp)
```

### Time Zone Testing

Always test timestamp parsing and comparison logic with timezone-aware objects:

```python
def test_timezone_handling():
    """Test timezone-aware timestamp handling."""
    from datetime import datetime, timezone
    
    # Create timezone-aware datetime
    utc_dt = datetime.now(timezone.utc)
    timestamp_str = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Parse and verify timezone preservation
    parsed_dt = parse_utc_timestamp(timestamp_str)
    
    # Verify timezone info is present
    assert parsed_dt.tzinfo == timezone.utc
    assert parsed_dt == utc_dt
    
    print("Timezone handling test passed")

test_timezone_handling()
```

## Summary

- **Time Range**: ISO 8601 format with explicit start/end timestamps
- **Time Zone**: All timestamps use UTC with 'Z' suffix
- **Error Rates**: Calculate as ratios (count / total) for various error types
- **Latency Metrics**: Use percentile calculations (p50, p95) for timing data
- **Aggregation Functions**: `rate()`, `avg()`, `percentile()`, `median()`
- **Data Sources**: Pod logs, nginx logs, deployment files
- **Query Execution**: Use collector classes or direct query functions
- **Validation**: Always verify data availability before running queries
- **Time Zone Safety**: Always use timezone-aware datetime objects

This system provides comprehensive 30-day error rate and latency analysis for infrastructure monitoring and reliability assessment.
