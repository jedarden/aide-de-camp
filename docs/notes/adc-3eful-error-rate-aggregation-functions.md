# Error Rate Aggregation Functions for 30-Day Queries

This document describes the error rate aggregation functions used in 30-day error rate analysis for pbx-web and whisper-stt services.

## Time Range Syntax

### Absolute Time Range (ISO 8601 Format)
```python
{
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "description": "Absolute 30-day window using ISO 8601 timestamps"
}
```
**Usage:** Best for reproducible analysis periods and historical comparisons.

### Relative Time Range (Days Offset from Today)
```python
{
    "start": (datetime.now() - timedelta(days=30)).isoformat() + "Z",
    "end": datetime.now().isoformat() + "Z",
    "days": 30,
    "description": "Relative 30-day window from current time"
}
```
**Usage:** Best for monitoring current status and rolling windows.

### Date-Only Range
```python
{
    "start_date": "2026-07-07",
    "end_date": "2026-08-06",
    "description": "Date-only range (implies T00:00:00Z start, T23:59:59Z end)"
}
```
**Usage:** Simplified syntax when exact time boundaries aren't critical.

## Error Rate Aggregation Functions

### 1. Pod-Level Error Rate

**Formula:** `error_rate_per_pod = total_error_count / total_pods_analyzed`

**Aggregation Functions:**
- `SUM(error_counts)` - Sum all error counts across all pods
- `COUNT(pods)` - Count total number of pods analyzed
- `COUNT(pods_with_errors)` - Count pods that have at least one error
- `AVG(error_rate_per_pod)` - Calculate average error rate per pod

**Data Source:** Pod log analysis files (`*pod-logs/*-analysis.json`)

**Example Results:**
```
pbx-web:
  total_pods_analyzed: 8
  pods_with_errors: 1
  pods_with_errors_percentage: 12.5%
  total_error_count: 5
  error_rate_per_pod: 0.62

whisper-stt:
  total_pods_analyzed: 10
  pods_with_errors: 2
  pods_with_errors_percentage: 20.0%
  total_error_count: 2
  error_rate_per_pod: 0.2
```

**Implementation:**
```python
total_pods = len(analysis_files)
total_error_count = sum(pattern.get("error", {}).get("count", 0) for pattern in all_patterns)
error_rate_per_pod = total_error_count / total_pods
```

### 2. HTTP Error Rate

**Formula:** `http_5xx_error_rate = http_5xx_errors / total_http_requests`

**Aggregation Functions:**
- `COUNT(requests)` - Count requests by HTTP status code (5xx, 4xx, 2xx, 3xx)
- `SUM(requests)` - Sum all HTTP requests for total count
- `RATE(error_requests / total_requests)` - Calculate error rate percentage

**Data Source:** Nginx access logs (`*pod-logs/*nginx*.log`)

**Example Results:**
```
pbx-web:
  total_http_requests: 33,129
  http_5xx_errors: 0
  http_5xx_error_rate_percent: 0.0%
  http_4xx_errors: 2
  http_4xx_error_rate_percent: 0.006%
  http_2xx_requests: 33,125
  http_3xx_requests: 2

whisper-stt:
  total_http_requests: 0 (no nginx logs found)
```

**Implementation:**
```python
# Parse HTTP status codes from nginx log format
for line in nginx_log:
    status_match = re.search(r'"\w+ [^\s]+ HTTP/\d\.\d" (\d+)', line)
    if status_match:
        status_code = int(status_match.group(1))
        total_requests += 1
        if status_code >= 500: http_5xx_errors += 1
        elif status_code >= 400: http_4xx_errors += 1

http_5xx_error_rate = (http_5xx_errors / total_requests * 100)
```

### 3. Deployment Error Rate

**Formula:** `deployment_error_rate = failed_deployments / total_deployments`

**Aggregation Functions:**
- `COUNT(deployments)` - Count deployments by status (failed, success)
- `SUM(deployments)` - Sum all deployments for total count
- `RATE(failed_deployments / total_deployments)` - Calculate deployment failure rate

**Data Source:** Kubernetes deployment events (`deployments-30days.json`)

**Example Results:**
```
whisper-stt:
  total_deployments: 10
  successful_deployments: 10
  failed_deployments: 0
  deployment_error_rate_percent: 0.0%
  deployment_success_rate_percent: 100.0%
```

**Implementation:**
```python
for deployment in deployments:
    total_deployments += 1
    success = deployment.get("success", True)
    status = deployment.get("status", "unknown")
    if status == "failed" or not success:
        failed_deployments += 1
    else:
        successful_deployments += 1

deployment_error_rate = (failed_deployments / total_deployments * 100)
```

### 4. OOM Kill Rate

**Formula:** `oom_kill_rate = total_oom_kills / total_pods_analyzed`

**Aggregation Functions:**
- `COUNT(OOM_killed_pods)` - Count pods that experienced OOM kills
- `SUM(OOM_kill_events)` - Sum all OOM kill events across pods
- `RATE(OOM_kills / total_pods)` - Calculate OOM kill rate per pod

**Data Source:** Pod log analysis patterns for OOM indicators

**Example Results:**
```
pbx-web:
  total_pods_analyzed: 8
  pods_with_oom_kills: 0
  pods_with_oom_percentage: 0.0%
  total_oom_kill_count: 0
  oom_kill_rate_per_pod: 0.0

whisper-stt:
  total_pods_analyzed: 10
  pods_with_oom_kills: 0
  pods_with_oom_percentage: 0.0%
  total_oom_kill_count: 0
  oom_kill_rate_per_pod: 0.0
```

**Implementation:**
```python
oom_count = pattern.get("oom_kill", {}).get("count", 0)
if oom_count > 0:
    pods_with_oom += 1
    total_oom_kills += oom_count

oom_kill_rate = total_oom_kills / total_pods
oom_pod_percentage = (pods_with_oom / total_pods * 100)
```

### 5. Overall Error Rate

**Formula:** `overall_error_rate_per_day = total_errors_all_sources / days_in_period`

**Aggregation Functions:**
- `SUM(all_error_types)` - Sum errors across all sources
  - Pod errors + OOM kills + HTTP 5xx + HTTP 4xx + Deployment failures
- `COUNT(days)` - Count days in analysis period
- `RATE(total_errors / days)` - Calculate daily error rate

**Data Source:** Combined from all previous queries

**Example Results:**
```
pbx-web:
  pod_errors: 5
  oom_kills: 0
  http_5xx_errors: 0
  http_4xx_errors: 2
  deployment_failures: 0
  total_errors_all_sources: 7
  error_rate_per_day: 0.23
  error_breakdown:
    pod_errors_percent: 71.4%
    oom_kills_percent: 0.0%
    http_5xx_percent: 0.0%
    http_4xx_percent: 28.6%
    deployment_failures_percent: 0.0%

whisper-stt:
  pod_errors: 2
  oom_kills: 0
  http_5xx_errors: 0
  http_4xx_errors: 0
  deployment_failures: 0
  total_errors_all_sources: 2
  error_rate_per_day: 0.07
```

**Implementation:**
```python
total_errors_all_sources = (pod_errors + oom_kills +
                            http_5xx + http_4xx + deploy_errors)
error_rate_per_day = total_errors_all_sources / days

error_breakdown = {
    "pod_errors_percent": (pod_errors / total_errors_all_sources * 100),
    "oom_kills_percent": (oom_kills / total_errors_all_sources * 100),
    # ... etc
}
```

## Query Execution Summary

**Test Results (2026-08-06):**
- Total query types: 5
- Services tested: pbx-web, whisper-stt
- Queries executed successfully: 4/5 per service
- Data availability: 100% for pod logs, 50% for nginx logs, 50% for deployment data

**Performance Metrics:**
- Average execution time: <1 second per service
- Data sources accessed: 3 per service (pod logs, nginx logs, deployment events)
- Files analyzed: 18 (pbx-web: 8 pod logs, 10 whisper-stt: 10 pod logs)

## Usage Example

```python
from error_rate_query_examples import ErrorRateQueryExamples, TIME_RANGE_EXAMPLES

# Select time range syntax
time_range = TIME_RANGE_EXAMPLES["absolute_30_day"]

# Create query instance for service
query_examples = ErrorRateQueryExamples("pbx-web", time_range)

# Run all error rate queries
results = query_examples.run_all_queries()

# Access specific query results
pod_errors = results["query_results"]["pod_error_rate_from_logs"]["metrics"]
http_errors = results["query_results"]["http_error_rate_from_nginx"]["metrics"]
```

## Data Availability Notes

- **Pod log analysis:** Available for both services (100% coverage)
- **Nginx logs:** Available for pbx-web only (whisper-stt uses different logging)
- **Deployment events:** Available for whisper-stt only (pbx-web data in different format)
- **OOM kill patterns:** Available for both services (currently 0 events)

## Summary

The 30-day error rate aggregation system provides comprehensive error analysis across multiple dimensions:

1. **Pod-level errors** - Application errors in container logs
2. **HTTP errors** - Request/response errors from nginx access logs
3. **Deployment errors** - Failed deployment events from k8s
4. **OOM kills** - Memory pressure events causing pod terminations
5. **Overall error rate** - Combined view across all sources

All queries use standard aggregation functions (SUM, COUNT, RATE, AVG) and can be executed against 30-day rolling windows or absolute time periods using ISO 8601 timestamps.

**Generated:** 2026-08-06
**Query Script:** `error_rate_query_examples.py`
**Test Results:** `data/error_rate_query_examples_30d_20260806_204652.json`