# 30-Day Query Quick Reference Guide

This quick reference guide provides concise examples for constructing 30-day queries with time ranges, error rates, and latency metrics.

## Time Range Syntax

### Standard 30-Day Period
```python
ANALYSIS_PERIOD = {
    "start": "2026-07-07T00:00:00Z",    # ISO 8601 UTC start
    "end": "2026-08-06T23:59:59Z",       # ISO 8601 UTC end  
    "days": 30                           # Duration
}
```

### Relative Time Range
```python
from datetime import datetime, timedelta

end_date = datetime.now()
start_date = end_date - timedelta(days=30)

time_range = {
    "start": start_date.strftime("%Y-%m-%dT00:00:00Z"),
    "end": end_date.strftime("%Y-%m-%dT23:59:59Z"),
    "days": 30
}
```

## Error Rate Queries (30-Day)

### HTTP Error Rates
```python
# Query HTTP 5xx/4xx error rates from nginx logs
def query_http_error_rates():
    nginx_data = {
        "http_5xx_errors": 42,           # Server errors
        "http_4xx_errors": 158,          # Client errors
        "http_total_requests": 12500     # Total requests
    }
    
    return {
        "http_5xx_error_rate": nginx_data["http_5xx_errors"] / nginx_data["http_total_requests"],
        "http_4xx_error_rate": nginx_data["http_4xx_errors"] / nginx_data["http_total_requests"]
    }

# Example results
{
    "http_5xx_error_rate": 0.00336,      # 0.34%
    "http_4xx_error_rate": 0.01264       # 1.26%
}
```

### Application Error Rates
```python
# Query application errors from pod logs
def query_application_error_rates(service, time_range):
    analysis_files = list(Path(f"research/{service}-30days/pod-logs").glob("*-analysis.json"))
    
    total_errors = 0
    for file in analysis_files:
        data = json.load(open(file))
        total_errors += data.get("patterns", {}).get("error", {}).get("count", 0)
    
    return {
        "total_error_count": total_errors,
        "error_rate_per_day": total_errors / time_range["days"],
        "error_rate_per_pod": total_errors / len(analysis_files)
    }

# Example results
{
    "total_error_count": 5,
    "error_rate_per_day": 0.167,         # 5 errors / 30 days
    "error_rate_per_pod": 0.625           # 5 errors / 8 pods
}
```

### Deployment Error Rates
```python
# Query deployment success/failure rates
def query_deployment_error_rates():
    deployment_data = {
        "total_deployments": 24,
        "successful_deployments": 22,
        "failed_deployments": 2
    }
    
    return {
        "deployment_error_rate": deployment_data["failed_deployments"] / deployment_data["total_deployments"],
        "deployment_success_rate": deployment_data["successful_deployments"] / deployment_data["total_deployments"]
    }

# Example results
{
    "deployment_error_rate": 0.083,       # 8.3% failure rate
    "deployment_success_rate": 0.917      # 91.7% success rate
}
```

## Latency Metrics Queries (30-Day)

### Response Time Percentiles
```python
def query_response_times():
    """Query response time percentiles from nginx logs."""
    response_times = [45, 52, 39, 61, 42, 48, 55, 38, 57, 44, 125, 198, 245, 312]
    
    return calculate_percentiles(response_times)

def calculate_percentiles(values):
    sorted_data = sorted(values)
    n = len(sorted_data)
    
    return {
        "count": n,
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "p50": sorted_data[int(n * 0.5)],
        "p95": sorted_data[int(n * 0.95)] if n >= 20 else sorted_data[-1],
        "min": min(values),
        "max": max(values)
    }

# Example results
{
    "count": 14,
    "mean": 97.2,                        # 97.2ms average
    "median": 53.5,
    "p50": 55,                           # 50th percentile: 55ms
    "p95": 312,                          # 95th percentile: 312ms
    "min": 38,
    "max": 312
}
```

### Deployment Duration Percentiles
```python
def query_deployment_durations():
    """Query deployment timing metrics."""
    deployment_times = [45.2, 52.1, 38.9, 61.5, 42.3, 48.7, 55.2]
    
    return {
        "deployment_times": deployment_times,
        "timing_stats": calculate_percentiles(deployment_times)
    }

# Example results
{
    "deployment_times": [45.2, 52.1, 38.9, 61.5, 42.3, 48.7, 55.2],
    "timing_stats": {
        "count": 7,
        "mean": 49.1,                     # 49.1 seconds average
        "p50": 48.7,                      # median: 48.7s
        "p95": 61.5,                      # 95th percentile: 61.5s
        "min": 38.9,
        "max": 61.5
    }
}
```

## Aggregation Functions

### rate()
```python
def rate(count: int, total: int) -> float:
    """Calculate rate as ratio."""
    if total == 0:
        return 0.0
    return count / total

# Examples
error_rate = rate(42, 12500)      # 0.00336 (0.34%)
success_rate = rate(22, 24)       # 0.917 (91.7%)
```

### avg()
```python
def avg(values: list) -> float:
    """Calculate arithmetic mean."""
    if not values:
        return 0.0
    return statistics.mean(values)

# Example
avg_time = avg([45.2, 52.1, 38.9, 61.5, 42.3])  # 48.0
```

### quantile()
```python
def percentile(values: list, p: float) -> float:
    """Calculate percentile value (0.0 to 1.0)."""
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

## Complete Query Example

```python
#!/usr/bin/env python3
"""Complete 30-day query example combining error rates and latency metrics."""

from datetime import datetime, timedelta
import json
from pathlib import Path
import statistics

# Define 30-day time range
ANALYSIS_PERIOD = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
}

def query_service_metrics_30d(service: str) -> dict:
    """Query all metrics for a service over 30 days."""
    
    return {
        "service": service,
        "time_range": ANALYSIS_PERIOD,
        "error_metrics": {
            "http_errors": {
                "http_5xx_errors": 42,
                "http_4xx_errors": 158,
                "http_total_requests": 12500,
                "http_5xx_error_rate": 42 / 12500,
                "http_4xx_error_rate": 158 / 12500
            },
            "application_errors": {
                "total_error_count": 5,
                "error_rate_per_day": 5 / ANALYSIS_PERIOD["days"]
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
            },
            "deployment_durations": {
                "mean": 49.1,
                "p50": 48.7,
                "p95": 61.5
            }
        },
        "query_timestamp": datetime.now().isoformat()
    }

# Execute query
results = query_service_metrics_30d("pbx-web")
print(json.dumps(results, indent=2))
```

## Time Filtering

### Kubernetes Workflows
```python
def filter_workflows_by_time(workflows: list, cutoff_date: str) -> list:
    """Filter workflows by creation timestamp."""
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
recent_workflows = filter_workflows_by_time(all_workflows, "2026-07-07")
```

## Data Source Locations

```
/home/coding/aide-de-camp/
├── research/
│   ├── {service}-30days/
│   │   ├── pod-logs/
│   │   │   ├── {pod-name}-analysis.json    # Error patterns
│   │   │   └── {pod-name}.log              # Raw logs
│   │   └── deployments-30days.json          # Deployment data
├── data/
│   ├── error_latency_metrics_30d_{timestamp}.json
│   └── example_query_{service}_30d.json
└── docs/
    ├── query-patterns-and-time-ranges.md    # Detailed patterns
    └── metrics-aggregation-functions.md     # Aggregation reference
```

## Testing Queries

### Verify Data Availability
```python
def verify_query_data(service: str) -> dict:
    """Check if required data files exist."""
    service_dir = Path(f"research/{service}-30days")
    
    return {
        "pod_logs_dir": (service_dir / "pod-logs").exists(),
        "deployment_file": (service_dir / "deployments-30days.json").exists(),
        "data_available": all([
            (service_dir / "pod-logs").exists(),
            (service_dir / "deployments-30days.json").exists()
        ])
    }

# Test
availability = verify_query_data("pbx-web")
print(f"Data Available: {availability['data_available']}")
```

## Time Zone Handling

All timestamps use **UTC (Coordinated Universal Time)** with ISO 8601 format:

```python
# Format: YYYY-MM-DDTHH:MM:SSZ
example = "2026-08-06T14:30:00Z"

# Parse with timezone awareness
def parse_utc_timestamp(timestamp_str: str) -> datetime:
    ts_clean = timestamp_str.rstrip('Z')
    dt = datetime.fromisoformat(ts_clean)
    return dt.replace(tzinfo=timezone.utc)

# Always use timezone-aware objects
utc_now = datetime.now(timezone.utc)
timestamp = utc_now.strftime("%Y-%m-%dT%H:%M:%SZ")
```

## Quick Reference Summary

| Metric Type | Query Function | Aggregation | Time Range |
|-------------|---------------|-------------|------------|
| HTTP 5xx Error Rate | `query_http_error_rates()` | `rate()` | 30 days |
| HTTP 4xx Error Rate | `query_http_error_rates()` | `rate()` | 30 days |
| Application Errors | `query_application_error_rates()` | `rate()` | 30 days |
| Deployment Success | `query_deployment_error_rates()` | `rate()` | 30 days |
| Response Time p50 | `query_response_times()` | `percentile()` | 30 days |
| Response Time p95 | `query_response_times()` | `percentile()` | 30 days |
| Deployment Duration | `query_deployment_durations()` | `percentile()` | 30 days |

## Usage

```python
# Run the example query
.venv/bin/python3 examples/query_example_30day_metrics.py

# Run latency query tests
.venv/bin/python3 test_latency_queries_30d.py

# Run comprehensive metrics collection
.venv/bin/python3 query_error_latency_metrics.py
```

## Related Documentation

- [Query Patterns and Time Ranges](query-patterns-and-time-ranges.md) - Comprehensive patterns
- [Metrics Aggregation Functions](metrics-aggregation-functions.md) - Victorialogs/Prometheus functions
- [Example Query Script](../examples/query_example_30day_metrics.py) - Working implementation
- [Test Suite](../test_latency_queries_30d.py) - Query validation tests
