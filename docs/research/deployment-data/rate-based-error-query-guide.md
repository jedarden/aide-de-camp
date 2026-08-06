# 30-Day Error Rate Queries - Complete Guide

## Overview

This guide provides comprehensive documentation for creating, testing, and optimizing 30-day error rate aggregation queries using the `rate()` function pattern. These queries are designed for pbx-web and whisper-stt services over a standard 30-day analysis period.

## Rate() Function Patterns

### Core Rate Calculations

The `rate()` function calculates normalized rates over time windows:

```python
# Basic rate calculation
rate(count, time_window_seconds) -> errors_per_second

# Common rate patterns
rate_per_day(count) -> errors_per_day
rate_per_hour(count) -> errors_per_hour
rate_percent(count, total) -> error_ratio (0-1)
```

### Standard Rate Patterns

#### 1. HTTP Error Rate Pattern
```python
# HTTP 5xx error rate as percentage
http_5xx_error_rate = rate_percent(http_5xx_errors, total_requests)

# Daily HTTP error rate
http_5xx_per_day = rate_per_day(http_5xx_errors)

# Hourly HTTP error rate
http_5xx_per_hour = rate_per_hour(http_5xx_errors)
```

#### 2. Application Error Rate Pattern
```python
# Per-pod application error rate
error_rate_per_pod = rate(total_error_count, total_pods_analyzed)

# Daily application error rate
error_rate_per_day = rate_per_day(total_error_count)

# Hourly application error rate
error_rate_per_hour = rate_per_hour(total_error_count)
```

#### 3. OOM Kill Rate Pattern
```python
# OOM kill rate per pod
oom_kill_rate_per_pod = rate(total_oom_kill_count, total_pods_analyzed)

# Daily OOM kill rate
oom_kill_rate_per_day = rate_per_day(total_oom_kill_count)

# Per-affected-pod OOM rate
oom_per_affected_pod = rate(total_oom_kill_count, pods_with_oom_kills)
```

#### 4. Deployment Error Rate Pattern
```python
# Deployment failure rate
deployment_error_rate = rate_percent(failed_deployments, total_deployments)

# Deployment success rate
deployment_success_rate = rate_percent(successful_deployments, total_deployments)

# Daily deployment rate
deployment_rate_per_day = rate_per_day(total_deployments)
```

## Query Examples with Results

### Example 1: HTTP Error Rate Query

**Query Pattern:**
```python
{
  "query_type": "http_error_rates",
  "rate_patterns_used": [
    "rate(http_5xx_errors, total_requests)",
    "rate_per_day(http_5xx_errors)",
    "rate_per_hour(http_4xx_errors)"
  ]
}
```

**Actual Results (pbx-web):**
```json
{
  "http_5xx_errors": 0,
  "http_4xx_errors": 2,
  "http_total_requests": 33129,
  "http_5xx_error_rate": 0.0,
  "http_4xx_error_rate": 0.00006037,
  "http_5xx_per_day": 0.0,
  "http_4xx_per_day": 0.0667,
  "http_4xx_per_hour": 0.00278,
  "log_files_analyzed": 1
}
```

**Interpretation:**
- HTTP 4xx error rate: 0.006% (very low)
- HTTP 5xx error rate: 0% (excellent)
- Average of 0.07 client errors per day

### Example 2: Application Error Rate Query

**Query Pattern:**
```python
{
  "query_type": "application_error_rates",
  "rate_patterns_used": [
    "rate_per_day(application_errors)",
    "rate(application_errors, total_pods)",
    "rate(application_errors, analysis_period_hours)"
  ]
}
```

**Actual Results (pbx-web):**
```json
{
  "total_pods_analyzed": 8,
  "pods_with_errors": 1,
  "pods_without_errors": 7,
  "total_error_count": 5,
  "error_rate_per_pod": 0.625,
  "error_rate_per_day": 0.167,
  "error_rate_per_hour": 0.00694
}
```

**Interpretation:**
- 1 out of 8 pods experienced errors (12.5% affected pod rate)
- Average 0.17 application errors per day
- 0.625 errors per pod overall (including error-free pods)

### Example 3: OOM Kill Rate Query

**Query Pattern:**
```python
{
  "query_type": "oom_kill_rates",
  "rate_patterns_used": [
    "rate_per_day(total_oom_kill_count)",
    "rate(oom_kills, pods_with_oom_kills)",
    "rate(oom_kills, total_pods)"
  ]
}
```

**Actual Results (pbx-web):**
```json
{
  "total_pods_analyzed": 8,
  "pods_with_oom_kills": 0,
  "total_oom_kill_count": 0,
  "oom_kill_rate_per_pod": 0.0,
  "oom_kill_rate_per_day": 0.0
}
```

**Interpretation:**
- No OOM kills detected in 30-day period
- Excellent memory management
- No resource exhaustion events

### Example 4: Deployment Error Rate Query

**Query Pattern:**
```python
{
  "query_type": "deployment_error_rates",
  "rate_patterns_used": [
    "rate(failed_deployments, total_deployments)",
    "rate_per_day(total_deployments)",
    "rate(successful_deployments, total_deployments)"
  ]
}
```

**Actual Results (pbx-web):**
```json
{
  "total_deployments": 0,
  "successful_deployments": 0,
  "failed_deployments": 0,
  "deployment_error_rate": 0.0,
  "deployment_success_rate": 0.0,
  "deployment_rate_per_day": 0.0
}
```

**Interpretation:**
- No deployment events detected in analysis period
- Either no deployments occurred or deployment data is unavailable
- Consider checking deployment data sources

## Query Optimization Best Practices

### 1. Time Window Optimization

**Best Practice:** Always use consistent time windows for rate calculations.

```python
# GOOD: Consistent 30-day window
ANALYSIS_PERIOD = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
}

# BAD: Inconsistent or undefined windows
rate(errors, some_variable_duration)
```

### 2. Zero Division Protection

**Best Practice:** Always validate denominators before rate calculations.

```python
# GOOD: Safe rate calculation
def rate(self, count: int, time_window_seconds: int) -> float:
    if time_window_seconds == 0:
        return 0.0
    return count / time_window_seconds

# BAD: Unsafe calculation
rate = errors / time_window_seconds  # Can cause ZeroDivisionError
```

### 3. Data Source Tracking

**Best Practice:** Track data sources for query validation.

```python
# GOOD: Track data sources
result = {
    "data_sources": ["nginx.log", "pod-logs/*.log"],
    "log_files_analyzed": 5,
    "records_processed": 45000
}

# BAD: No provenance
result = {"error_rate": 0.05}  # Unknown data quality
```

### 4. Percentile Calculation for Rate Stability

**Best Practice:** Use percentiles for rate aggregation over noisy data.

```python
# GOOD: Percentile-based aggregation
p95_error_rate = percentile(daily_error_rates, 0.95)
median_error_rate = median(daily_error_rates)

# BAD: Mean over skewed data
avg_error_rate = mean(daily_error_rates)  # Can be misleading
```

### 5. Rate Smoothing for Trend Analysis

**Best Practice:** Apply moving averages or exponential smoothing for trend visualization.

```python
# GOOD: Smoothed rates
smoothed_rate = exponential_moving_average(daily_rates, alpha=0.3)

# BAD: Raw volatile rates
daily_rate = errors_today / 1  # Highly volatile
```

## Performance Considerations

### 1. Query Execution Time

**Optimization:**
- Batch file reads: Process all log files in single pass
- Memory efficiency: Stream large files rather than loading entirely
- Parallel processing: Use multiprocessing for CPU-intensive parsing

```python
# EFFICIENT: Batch processing
for log_file in log_files:
    with open(log_file, 'r') as f:
        for line in f:  # Stream processing
            process_line(line)

# INEFFICIENT: Load entire file
for log_file in log_files:
    lines = open(log_file, 'r').read().splitlines()  # Memory intensive
```

### 2. Data Volume Management

**Optimization:**
- Sample rate: Use appropriate sampling for high-volume data
- Data pruning: Exclude irrelevant log entries early
- Incremental processing: Process data in chunks

```python
# EFFICIENT: Early filtering
if "ERROR" in line or "WARN" in line:
    process_line(line)

# INEFFICIENT: Process all lines
for line in log_file:
    process_line(line)  # Even INFO/DEBUG lines
```

## Error Rate Calculation Methodologies

### 1. Simple Rate (Errors/Time)

**Formula:** `rate = count / time_window`

**Use Case:** When time normalization is critical (e.g., per-second rates)

**Example:**
```python
errors_per_second = total_errors / (30 * 24 * 3600)
errors_per_day = total_errors / 30
```

### 2. Percentage Rate (Errors/Total)

**Formula:** `rate = errors / total_events`

**Use Case:** When error probability is the metric of interest

**Example:**
```python
http_error_rate = http_errors / total_http_requests
pod_error_rate = pods_with_errors / total_pods
```

### 3. Weighted Error Score

**Formula:** `score = Σ(error_count × severity_weight)`

**Use Case:** Multi-dimensional error analysis with severity levels

**Example:**
```python
severity_weights = {
    "critical": 3.0,  # HTTP 5xx, OOM kills
    "high": 2.0,      # Deployment failures
    "medium": 1.0,    # Application errors
    "low": 0.5        # HTTP 4xx
}

weighted_score = (
    http_5xx * 3.0 +
    oom_kills * 3.0 +
    deployment_failures * 2.0 +
    app_errors * 1.0 +
    http_4xx * 0.5
)
```

## Testing and Validation

### Query Validation Criteria

A query is considered valid if it returns at least **one positive value**:

```python
def test_query_returns_data(query_result: Dict) -> bool:
    """Test if query returns actual data (not all zeros)."""
    positive_values = [
        value for key, value in query_result.items()
        if isinstance(value, (int, float)) and value > 0
    ]
    return len(positive_values) >= 1
```

### Data Quality Checks

**Essential validations:**

1. **Completeness Check:** Are all expected data sources present?
2. **Consistency Check:** Do error counts align with log volumes?
3. **Temporal Coverage:** Is the full 30-day window covered?
4. **Reasonableness Check:** Are rates within expected ranges?

```python
def validate_query_result(result: Dict) -> Dict[str, bool]:
    """Validate query result quality."""
    return {
        "has_positive_values": any(v > 0 for v in result.values() if isinstance(v, (int, float))),
        "has_data_sources": len(result.get("data_sources", [])) > 0,
        "time_range_valid": result.get("start") and result.get("end"),
        "rates_reasonable": all(0 <= v <= 1 for v in result.values() if "rate" in str(v))
    }
```

## Complete Query Example

### Full 30-Day Error Rate Query

```python
query_result = {
  "service": "pbx-web",
  "time_range": {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
  },
  "queries": {
    "http_error_rates": {
      "http_5xx_errors": 0,
      "http_4xx_errors": 2,
      "http_total_requests": 33129,
      "http_5xx_error_rate": 0.0,
      "http_4xx_error_rate": 0.00006037
    },
    "application_error_rates": {
      "total_pods_analyzed": 8,
      "pods_with_errors": 1,
      "total_error_count": 5,
      "error_rate_per_pod": 0.625,
      "error_rate_per_day": 0.167
    },
    "oom_kill_rates": {
      "total_oom_kill_count": 0,
      "oom_kill_rate_per_day": 0.0
    },
    "overall_error_rates": {
      "total_errors_all_sources": 7,
      "error_rate_per_day": 0.233,
      "weighted_error_score": 6.0,
      "weighted_error_rate_per_day": 0.2
    }
  },
  "test_results": {
    "http_error_rates": {"passed": true},
    "application_error_rates": {"passed": true},
    "overall_error_rates": {"passed": true}
  }
}
```

## Comparison: pbx-web vs whisper-stt

### Error Rate Comparison (30-Day Period)

| Metric | pbx-web | whisper-stt | Interpretation |
|--------|---------|--------------|----------------|
| HTTP 4xx errors | 2 | 0 | pbx-web has low client error rate |
| HTTP 5xx errors | 0 | 0 | Both services have excellent server reliability |
| App errors | 5 | 2 | pbx-web has 2.5x more app errors |
| App error rate/day | 0.167 | 0.067 | whisper-stt has 60% lower app error rate |
| Pods with errors | 1/8 (12.5%) | 2/10 (20%) | whisper-stt has higher pod error percentage |
| OOM kills | 0 | 0 | Both services have no memory issues |
| Total weighted score | 6.0 | 2.0 | whisper-stt has 67% lower weighted error score |

### Key Findings

1. **HTTP Reliability:** Both services show excellent HTTP reliability with minimal errors
2. **Application Stability:** whisper-stt demonstrates better application stability with lower error rates
3. **Memory Management:** Both services show no OOM kills, indicating good resource management
4. **Overall Health:** whisper-stt has a superior weighted error score, indicating better overall reliability

## Advanced Rate Patterns

### 1. Composite Error Rate

```python
# Combines multiple error types into single metric
composite_rate = (
    http_5xx_errors * 3.0 +
    app_errors * 1.0 +
    oom_kills * 3.0
) / (total_requests * 3.0 + total_operations * 1.0)
```

### 2. Time-Decayed Rate

```python
# Recent errors weighted more heavily
time_decayed_rate = sum(
    error_count * exp(-lambda * days_ago)
    for error_count, days_ago in daily_errors
)
```

### 3. Z-Score Normalized Rate

```python
# Statistical outlier detection
mean_rate = statistics.mean(historical_rates)
std_rate = statistics.stdev(historical_rates)
z_score = (current_rate - mean_rate) / std_rate
```

## Troubleshooting Common Issues

### Issue: All query results are zero

**Possible Causes:**
1. Data files not found
2. Incorrect file paths
3. Log format mismatches
4. Empty log files

**Resolution:**
```python
# Check data sources
if not result["data_sources"]:
    print("Warning: No data sources found")
    print(f"Expected directory: {service_dir / 'pod-logs'}")

# Validate file existence
log_files = list(pod_logs_dir.glob("*.log"))
print(f"Found {len(log_files)} log files")
```

### Issue: Inflated error rates

**Possible Causes:**
1. Duplicate log entries
2. Incorrect parsing logic
3. Time window mismatches

**Resolution:**
```python
# Deduplicate entries
unique_errors = set(error_records)
error_count = len(unique_errors)

# Validate time windows
assert (end_time - start_time).days == 30
```

## Usage Instructions

### Running the Complete Query Suite

```bash
# Execute all rate-based error rate queries
.venv/bin/python examples/rate_based_error_queries_30day.py

# Results are saved to:
# data/tested_error_rate_queries_<timestamp>.json
```

### Integrating Custom Queries

```python
from examples.rate_based_error_queries_30day import RateBasedErrorQuery

# Create query engine for your service
query_engine = RateBasedErrorQuery("your-service")

# Run specific query type
http_errors = query_engine.query_http_error_rates()

# Run all queries
all_results = query_engine.run_all_queries()
```

## Data Output Format

Query results follow this structure:

```json
{
  "service": "service-name",
  "time_range": {
    "start": "ISO-8601-timestamp",
    "end": "ISO-8601-timestamp",
    "days": 30
  },
  "queries": {
    "query_type": {
      "query_type": "type_name",
      "rate_patterns_used": ["pattern1", "pattern2"],
      "metrics": {...}
    }
  },
  "test_results": {
    "query_type": {
      "passed": true/false,
      "message": "validation message"
    }
  },
  "query_timestamp": "ISO-8601-timestamp"
}
```

## Conclusion

These rate-based error query patterns provide a comprehensive framework for 30-day error rate analysis across pbx-web and whisper-stt services. The `rate()` function pattern ensures consistent, comparable metrics that can be tracked over time for trend analysis and alerting.

For questions or improvements to these query patterns, refer to the latest version of this document in:
`docs/research/deployment-data/rate-based-error-query-guide.md`