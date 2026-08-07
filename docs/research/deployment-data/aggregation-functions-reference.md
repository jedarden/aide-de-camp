# Aggregation Functions - Complete Reference Guide

**Document Version:** 1.0  
**Last Updated:** 2026-08-06  
**Task ID:** adc-3n6dq  
**Purpose:** Comprehensive reference for all aggregation functions used in deployment data queries

---

## Table of Contents

1. [Overview](#overview)
2. [Rate Functions](#rate-functions)
3. [Average Functions](#average-functions)
4. [Quantile/Percentile Functions](#quantilepercentile-functions)
5. [Basic Aggregation Functions](#basic-aggregation-functions)
6. [Combined Query Examples](#combined-query-examples)
7. [Usage Patterns and Best Practices](#usage-patterns-and-best-practices)
8. [Performance Considerations](#performance-considerations)
9. [Error Handling](#error-handling)

---

## Overview

This guide provides comprehensive documentation for aggregation functions used in deployment data analysis queries, including:

- **Rate calculations** for time-based metrics (errors per second/day/hour)
- **Average functions** for central tendency statistics
- **Quantile/Percentile functions** for distribution analysis
- **Basic aggregations** for count, sum, min, max

These functions are used in analyzing:
- HTTP error rates
- Application error patterns
- OOM kill frequencies
- Deployment success/failure rates
- Latency percentiles (p50, p95, p99)
- Workflow duration statistics

---

## Rate Functions

Rate functions normalize counts over time windows, converting raw counts into time-series metrics.

### When to Use `rate()` vs Direct Values

| Use Case | Use `rate()` | Use Direct Values |
|----------|-------------|-------------------|
| Time-series comparison | ✅ Yes - Normalizes for time differences | ❌ No - Different time windows not comparable |
| Error probability analysis | ❌ No - Use `rate_percent()` instead | ✅ Yes - Raw count/total ratio |
| Resource consumption over time | ✅ Yes - Per-second/hour/day rates | ❌ No - Doesn't show temporal patterns |
| SLO compliance tracking | ✅ Yes - Rate-based SLOs (e.g., 99.9% success rate) | ✅ Yes - For absolute thresholds (e.g., <100 errors) |
| Capacity planning | ✅ Yes - Rate informs sizing decisions | ❌ No - Doesn't scale with time |

### Core Rate Functions

#### `rate(count, time_window_seconds) -> errors_per_second`

**Purpose:** Calculate normalized rate per second.

**Formula:** `rate = count / time_window_seconds`

**Example:**
```python
def rate(count: int, time_window_seconds: int) -> float:
    """Calculate rate per second with zero-division protection."""
    if time_window_seconds == 0:
        return 0.0
    return count / time_window_seconds

# Calculate HTTP 5xx errors per second over 30 days
http_5xx_count = 5
time_window = 30 * 24 * 3600  # 30 days in seconds
error_rate = rate(http_5xx_count, time_window)
# Result: 5 / 2,592,000 = 0.00000193 errors/second
```

**Use Case:** When you need per-second rates for real-time monitoring or SLOs expressed as "per-second" metrics.

---

#### `rate_per_day(count) -> errors_per_day`

**Purpose:** Calculate daily rate from a count over a time period.

**Formula:** `rate_per_day = count / days_in_period`

**Example:**
```python
def rate_per_day(count: int, days: int = 30) -> float:
    """Calculate rate per day with zero-division protection."""
    if days == 0:
        return 0.0
    return count / days

# Calculate application errors per day
total_app_errors = 5
error_rate_per_day = rate_per_day(total_app_errors, days=30)
# Result: 5 / 30 = 0.167 errors/day
```

**Use Case:** Daily error rates for trending and capacity planning. More human-readable than per-second rates.

---

#### `rate_per_hour(count) -> errors_per_hour`

**Purpose:** Calculate hourly rate from a count over a time period.

**Formula:** `rate_per_hour = count / hours_in_period`

**Example:**
```python
def rate_per_hour(count: int, hours: int) -> float:
    """Calculate rate per hour with zero-division protection."""
    if hours == 0:
        return 0.0
    return count / hours

# Calculate HTTP 4xx errors per hour
http_4xx_count = 2
hours = 30 * 24  # 720 hours in 30 days
error_rate_per_hour = rate_per_hour(http_4xx_count, hours)
# Result: 2 / 720 = 0.00278 errors/hour
```

**Use Case:** Hourly rates for diurnal pattern analysis and staffing decisions.

---

#### `rate_percent(count, total) -> error_ratio (0-1)`

**Purpose:** Calculate percentage ratio (0-1 range, not 0-100).

**Formula:** `rate_percent = count / total`

**Example:**
```python
def rate_percent(count: int, total: int) -> float:
    """Calculate percentage rate (0-1 range) with zero-division protection."""
    if total == 0:
        return 0.0
    return count / total

# Calculate HTTP 5xx error rate as percentage
http_5xx_errors = 0
total_requests = 33129
error_rate = rate_percent(http_5xx_errors, total_requests)
# Result: 0 / 33129 = 0.0 (0% error rate)

# Calculate HTTP 4xx error rate
http_4xx_errors = 2
error_rate_4xx = rate_percent(http_4xx_errors, total_requests)
# Result: 2 / 33129 = 0.00006037 (0.006% error rate)
```

**Use Case:** Error probability analysis, SLO compliance (e.g., "99.9% success rate"), comparative metrics across services.

---

### Rate Function Patterns

#### HTTP Error Rate Pattern
```python
http_5xx_error_rate = rate_percent(http_5xx_errors, total_requests)
http_5xx_per_day = rate_per_day(http_5xx_errors, days=30)
http_4xx_per_hour = rate_per_hour(http_4xx_errors, hours=720)
```

#### Application Error Rate Pattern
```python
error_rate_per_pod = rate(total_error_count, total_pods_analyzed)
error_rate_per_day = rate_per_day(total_error_count, days=30)
error_rate_per_hour = rate_per_hour(total_error_count, hours=720)
```

#### OOM Kill Rate Pattern
```python
oom_kill_rate_per_pod = rate(total_oom_kill_count, total_pods_analyzed)
oom_kill_rate_per_day = rate_per_day(total_oom_kill_count, days=30)
oom_per_affected_pod = rate(total_oom_kill_count, pods_with_oom_kills)
```

#### Deployment Error Rate Pattern
```python
deployment_error_rate = rate_percent(failed_deployments, total_deployments)
deployment_success_rate = rate_percent(successful_deployments, total_deployments)
deployment_rate_per_day = rate_per_day(total_deployments, days=30)
```

---

## Average Functions

Average functions calculate central tendency statistics for numerical distributions.

### Core Average Functions

#### `avg(values) / mean(values) -> arithmetic_mean`

**Purpose:** Calculate arithmetic mean (average) of a list of values.

**Formula:** `mean = sum(values) / count(values)`

**Example:**
```python
import statistics

# Calculate mean latency
latencies_ms = [45, 67, 23, 89, 156, 234, 412, 12, 523]
mean_latency = statistics.mean(latencies_ms)
# Result: 177.89 ms
```

**Use Case:** General average calculation, baseline performance metric, capacity planning.

---

#### `median(values) -> middle_value`

**Purpose:** Calculate median (middle value) of a sorted list.

**Formula:** After sorting, median is the middle value (odd count) or average of two middle values (even count).

**Example:**
```python
import statistics

# Calculate median latency
latencies_ms = [45, 67, 23, 89, 156, 234, 412, 12, 523]
median_latency = statistics.median(latencies_ms)
# Result: 89 ms (middle value after sorting: [12, 23, 45, 67, 89, 156, 234, 412, 523])
```

**Use Case:** Robust central tendency metric, less sensitive to outliers than mean. Best for latency SLOs.

---

#### `sum(values) -> total`

**Purpose:** Calculate sum of all values.

**Formula:** `sum = Σ(values)`

**Example:**
```python
# Calculate total deployment duration
durations_seconds = [234, 567, 123, 890, 456]
total_duration = sum(durations_seconds)
# Result: 2270 seconds
```

**Use Case:** Total resource consumption, cumulative metrics, volume calculations.

---

#### `stddev(values) -> standard_deviation`

**Purpose:** Calculate standard deviation (measure of spread).

**Formula:** `stddev = sqrt(Σ(x - mean)² / n)`

**Example:**
```python
import statistics

# Calculate latency standard deviation
latencies_ms = [45, 67, 23, 89, 156, 234, 412, 12, 523]
stddev_latency = statistics.stdev(latencies_ms)
# Result: 189.67 ms
```

**Use Case:** Variability analysis, outlier detection, stability metrics, capacity planning headroom.

---

### Average Function Examples

```python
import statistics

class AverageLatencyQuery:
    """Calculate average latency statistics over 30-day periods."""
    
    def calculate_average(self) -> dict[str, float]:
        """Calculate average latency statistics."""
        if not self.durations:
            return {
                "count": 0,
                "mean": 0,
                "median": 0,
                "sum": 0,
                "stddev": 0,
                "min": 0,
                "max": 0
            }
        
        return {
            "count": len(self.durations),
            "mean": statistics.mean(self.durations),
            "median": statistics.median(self.durations),
            "sum": sum(self.durations),
            "stddev": statistics.stdev(self.durations) if len(self.durations) > 1 else 0,
            "min": min(self.durations),
            "max": max(self.durations)
        }
```

---

## Quantile/Percentile Functions

Quantile and percentile functions calculate distribution statistics for positional analysis.

### When to Use Percentiles vs Mean

| Use Case | Use Percentiles | Use Mean |
|----------|----------------|----------|
| SLO compliance (e.g., "99% of requests < 100ms") | ✅ Yes - p99 directly answers this | ❌ No - Mean doesn't capture tail behavior |
| Outlier analysis | ✅ Yes - p99/p95 show tail behavior | ✅ Yes - Mean with stddev shows overall spread |
| Capacity planning | ✅ Yes - p95 informs worst-case sizing | ✅ Yes - Mean informs average-case sizing |
| Trend analysis | ✅ Yes - Percentile trends show distribution shifts | ✅ Yes - Mean trends show average shifts |
| Small sample sizes (<20) | ❌ No - Percentiles unreliable | ✅ Yes - Mean more stable with small samples |

### Core Percentile Functions

#### `quantiles(values, n=100, method='inclusive') -> list[percentiles]`

**Purpose:** Calculate n-quantiles using Python's statistics module.

**Method types:**
- `'inclusive'` - Percentile calculated as if values are continuous (RECOMMENDED for latency)
- `'exclusive'` - Percentile calculated excluding boundaries (more conservative)

**Example:**
```python
import statistics

# Calculate percentiles using statistics.quantiles
durations_ms = [12, 23, 45, 67, 89, 156, 234, 412, 523]
quantiles = statistics.quantiles(durations_ms, n=100, method='inclusive')

# Extract specific percentiles
p50 = quantiles[49]   # 50th percentile (median)
p75 = quantiles[74]   # 75th percentile
p90 = quantiles[89]   # 90th percentile
p95 = quantiles[94]   # 95th percentile
p99 = quantiles[98]   # 99th percentile
```

**Use Case:** General percentile calculation, distribution analysis, SLO tracking.

---

#### `percentiles(values, qs=(50, 95)) -> dict[int, int]`

**Purpose:** Calculate nearest-rank percentiles (custom function from aide-de-camp).

**Formula:** `percentile_q = values[ceil(q/100 * n) - 1]` after sorting ascending.

**Example:**
```python
from src.instrument.timings import percentiles

# Calculate p50 and p95 percentiles
latency_samples = [12, 23, 45, 67, 89, 156, 234, 412, 523]
result = percentiles(latency_samples, qs=(50, 95))
# Result: {50: 89, 95: 523}

# Calculate multiple percentiles at once
result = percentiles(latency_samples, qs=(50, 75, 90, 95, 99))
# Result: {50: 89, 75: 234, 90: 412, 95: 523, 99: 523}
```

**Use Case:** Timing statistics, latency SLOs, performance monitoring where nearest-rank method is preferred.

---

#### Manual Percentile Calculation

```python
def manual_percentile(values: list[float], p: float) -> float:
    """Calculate p-th percentile manually using nearest-rank method.
    
    Args:
        values: List of numerical values
        p: Percentile to calculate (0-100)
    
    Returns:
        The p-th percentile value
    """
    if not values:
        raise ValueError("Cannot calculate percentile of empty list")
    if not 0 <= p <= 100:
        raise ValueError(f"Percentile must be between 0 and 100, got {p}")
    
    sorted_data = sorted(values)
    n = len(sorted_data)
    
    # Nearest-rank method: ceil(p/100 * n)
    index = (p * n + 99) // 100 - 1  # ceil(p/100 * n) - 1
    index = max(0, min(n - 1, index))  # Clamp to valid range
    
    return sorted_data[index]

# Example usage
latencies = [12, 23, 45, 67, 89, 156, 234, 412, 523]
p50 = manual_percentile(latencies, 50)   # 89
p95 = manual_percentile(latencies, 95)   # 523
p99 = manual_percentile(latencies, 99)   # 523
```

---

### Percentile Calculation Classes

```python
import statistics
from datetime import datetime

class LatencyPercentileQuery:
    """Calculate latency percentiles over 30-day periods."""
    
    def calculate_quantiles(self) -> dict[str, float]:
        """Calculate percentile statistics using quantiles."""
        if not self.durations:
            return {
                "count": 0,
                "p50": 0,
                "p75": 0,
                "p90": 0,
                "p95": 0,
                "p99": 0,
                "min": 0,
                "max": 0
            }
        
        # Using statistics.quantiles (Python 3.8+)
        quantiles = statistics.quantiles(self.durations, n=100, method='inclusive')
        return {
            "count": len(self.durations),
            "p50": quantiles[49],   # 50th percentile
            "p75": quantiles[74],   # 75th percentile
            "p90": quantiles[89],   # 90th percentile
            "p95": quantiles[94],   # 95th percentile
            "p99": quantiles[98],   # 99th percentile
            "min": min(self.durations),
            "max": max(self.durations)
        }
```

---

### Sample Size Requirements for Percentiles

| Percentile | Minimum Recommended Samples | Minimum Usable Samples |
|------------|------------------------------|------------------------|
| p50 | 2 | 2 |
| p75 | 4 | 2 |
| p90 | 10 | 5 |
| p95 | 20 | 10 |
| p99 | 100 | 20 |

**Warning:** Percentiles calculated with insufficient samples are statistically unreliable. Always report sample count alongside percentile values.

---

### SQL Percentile Functions

```sql
-- PostgreSQL: PERCENTILE_CONT (continuous percentile distribution)
SELECT 
    service_name,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms) as p50_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_latency_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms) as p99_latency_ms,
    COUNT(*) as sample_count
FROM deployment_metrics
WHERE timestamp BETWEEN '2026-07-07' AND '2026-08-06'
GROUP BY service_name;

-- PostgreSQL: PERCENTILE_DISC (discrete percentile, nearest-rank)
SELECT 
    service_name,
    PERCENTILE_DISC(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_latency_ms
FROM deployment_metrics
GROUP BY service_name;
```

---

## Basic Aggregation Functions

Basic aggregations provide fundamental statistical operations on numerical data.

### Core Basic Functions

#### `count(values) -> integer`

**Purpose:** Count number of items in a list.

**Example:**
```python
total_pods = len(pods_list)  # 8
total_errors = len(error_records)  # 5
```

**Use Case:** Volume metrics, sample size reporting, denominator for rate calculations.

---

#### `min(values) -> minimum_value`

**Purpose:** Find minimum value in a list.

**Example:**
```python
latencies_ms = [45, 67, 23, 89, 156]
min_latency = min(latencies_ms)  # 23 ms
```

**Use Case:** Best-case performance, minimum resource consumption, optimistic capacity planning.

---

#### `max(values) -> maximum_value`

**Purpose:** Find maximum value in a list.

**Example:**
```python
latencies_ms = [45, 67, 23, 89, 156]
max_latency = max(latencies_ms)  # 156 ms
```

**Use Case:** Worst-case performance, peak resource consumption, pessimistic capacity planning.

---

### Basic Aggregation Example

```python
def calculate_basic_stats(values: list[float]) -> dict[str, float]:
    """Calculate basic aggregation statistics."""
    if not values:
        return {
            "count": 0,
            "min": 0,
            "max": 0,
            "sum": 0,
            "mean": 0
        }
    
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "sum": sum(values),
        "mean": statistics.mean(values)
    }
```

---

## Combined Query Examples

### Example 1: Combined Rate + Average Query

```python
def comprehensive_error_query(data_file: str) -> dict[str, any]:
    """Combined query returning rates, averages, and percentiles."""
    
    # Load data
    with open(data_file, 'r') as f:
        data = json.load(f)
    
    # Extract error counts
    http_5xx_errors = data.get('http_5xx_errors', 0)
    http_4xx_errors = data.get('http_4xx_errors', 0)
    total_requests = data.get('total_requests', 0)
    app_errors = data.get('application_errors', 0)
    pods_analyzed = data.get('total_pods_analyzed', 1)
    
    # Calculate rates
    time_window_days = 30
    time_window_hours = 30 * 24
    
    result = {
        "service": data.get('service', 'unknown'),
        "time_range": {
            "start": "2026-07-07T00:00:00Z",
            "end": "2026-08-06T23:59:59Z",
            "days": time_window_days
        },
        "rate_metrics": {
            # Rate functions
            "http_5xx_error_rate": rate_percent(http_5xx_errors, total_requests),
            "http_4xx_error_rate": rate_percent(http_4xx_errors, total_requests),
            "http_5xx_per_day": rate_per_day(http_5xx_errors, time_window_days),
            "http_4xx_per_hour": rate_per_hour(http_4xx_errors, time_window_hours),
            "app_error_rate_per_pod": rate(app_errors, pods_analyzed),
            "app_error_rate_per_day": rate_per_day(app_errors, time_window_days)
        },
        "aggregation_metrics": {
            # Basic aggregations
            "total_errors": http_5xx_errors + http_4xx_errors + app_errors,
            "error_count": len([e for e in [http_5xx_errors, http_4xx_errors, app_errors] if e > 0]),
            "max_error_type_count": max([http_5xx_errors, http_4xx_errors, app_errors]),
            "min_error_type_count": min([http_5xx_errors, http_4xx_errors, app_errors])
        },
        "query_timestamp": datetime.now().isoformat()
    }
    
    return result
```

---

### Example 2: Percentile + Average Latency Query

```python
def comprehensive_latency_query(data_file: str) -> dict[str, any]:
    """Combined query returning percentiles and averages."""
    
    percentile_query = LatencyPercentileQuery(
        "2026-07-07T00:00:00Z",
        "2026-08-06T23:59:59Z"
    )
    
    with open(data_file, 'r') as f:
        data = json.load(f)
    
    workflows = data.get('workflows', [])
    
    for workflow in workflows:
        status = workflow.get('status', {})
        started = status.get('startedAt')
        finished = status.get('finishedAt')
        
        if started and finished:
            percentile_query.add_duration(started, finished)
    
    quantiles = percentile_query.calculate_quantiles()
    
    # Calculate averages from the same data
    if percentile_query.durations:
        avg_stats = {
            "mean": statistics.mean(percentile_query.durations),
            "median": statistics.median(percentile_query.durations),
            "sum": sum(percentile_query.durations),
            "stddev": statistics.stdev(percentile_query.durations) if len(percentile_query.durations) > 1 else 0,
            "min": min(percentile_query.durations),
            "max": max(percentile_query.durations)
        }
    else:
        avg_stats = {"mean": 0, "median": 0, "sum": 0, "stddev": 0, "min": 0, "max": 0}
    
    return {
        "time_range": {
            "start": "2026-07-07T00:00:00Z",
            "end": "2026-08-06T23:59:59Z",
            "days": 30
        },
        "percentile_stats": quantiles,
        "average_stats": avg_stats,
        "sample_size": len(percentile_query.durations),
        "query_timestamp": datetime.now().isoformat()
    }
```

---

### Example 3: Multi-Service Comparison Query

```python
def multi_service_comparison_query(service_data: dict[str, dict]) -> dict[str, any]:
    """Compare aggregation metrics across multiple services."""
    
    results = {}
    
    for service, data in service_data.items():
        # Calculate per-service metrics
        http_errors = data.get('http_errors', {})
        app_errors = data.get('app_errors', {})
        
        results[service] = {
            "rate_metrics": {
                "http_5xx_rate": rate_percent(
                    http_errors.get('5xx', 0),
                    http_errors.get('total', 1)
                ),
                "app_error_rate_per_pod": rate(
                    app_errors.get('total', 0),
                    app_errors.get('pods', 1)
                )
            },
            "average_metrics": {
                "mean_latency_ms": statistics.mean(data.get('latencies', [0])),
                "median_latency_ms": statistics.median(data.get('latencies', [0]))
            },
            "percentile_metrics": {
                "p95_latency_ms": data.get('latencies', [0])[int(len(data.get('latencies', [1])) * 0.95)] if len(data.get('latencies', [])) > 0 else 0
            }
        }
    
    # Calculate comparative metrics
    comparison = {
        "service_results": results,
        "comparison": {
            "lowest_http_error_rate": min(
                s['rate_metrics']['http_5xx_rate'] 
                for s in results.values()
            ),
            "highest_app_error_rate": max(
                s['rate_metrics']['app_error_rate_per_pod'] 
                for s in results.values()
            )
        }
    }
    
    return comparison
```

---

## Usage Patterns and Best Practices

### 1. Zero Division Protection

**Always validate denominators:**
```python
def safe_rate(count: int, denominator: int) -> float:
    """Calculate rate with zero-division protection."""
    if denominator == 0:
        return 0.0
    return count / denominator

# Usage
error_rate = safe_rate(error_count, total_requests)
```

---

### 2. Time Window Consistency

**Use consistent time windows:**
```python
# GOOD: Consistent 30-day window
ANALYSIS_PERIOD = {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30,
    "hours": 720,
    "seconds": 30 * 24 * 3600
}

# Apply consistently
error_rate_per_day = rate_per_day(errors, ANALYSIS_PERIOD["days"])
error_rate_per_hour = rate_per_hour(errors, ANALYSIS_PERIOD["hours"])
```

---

### 3. Data Quality Validation

**Validate before computing:**
```python
def validate_aggregation_data(values: list[float]) -> dict[str, bool]:
    """Validate data before aggregation."""
    return {
        "has_data": len(values) > 0,
        "no_negative": all(v >= 0 for v in values),
        "no_nulls": all(v is not None for v in values),
        "reasonable_range": max(values) < 10**9,  # < 1 billion
        "sufficient_for_percentile": len(values) >= 20  # For p95
    }

# Usage
validation = validate_aggregation_data(durations)
if not all(validation.values()):
    print(f"Warning: Data validation failed: {validation}")
```

---

### 4. Sample Size Checks

**Check sample size for percentiles:**
```python
def safe_percentile(values: list[float], p: float) -> float:
    """Calculate percentile with sample size checks."""
    n = len(values)
    
    # Minimum sample requirements
    min_samples = {
        50: 2,
        75: 4,
        90: 10,
        95: 20,
        99: 100
    }.get(p, 10)
    
    if n < min_samples:
        print(f"Warning: {p}th percentile with only {n} samples (recommended: {min_samples})")
        return max(values) if values else 0  # Fallback
    
    return manual_percentile(values, p)
```

---

### 5. Combining Multiple Aggregations

**Combine for comprehensive analysis:**
```python
def comprehensive_stats(values: list[float]) -> dict[str, float]:
    """Calculate all common statistics in one pass."""
    if not values:
        return {k: 0 for k in ['count', 'mean', 'median', 'p50', 'p95', 'p99', 'min', 'max', 'stddev']}
    
    n = len(values)
    sorted_values = sorted(values)
    
    return {
        "count": n,
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "p50": manual_percentile(values, 50),
        "p95": manual_percentile(values, 95),
        "p99": manual_percentile(values, 99),
        "min": min(values),
        "max": max(values),
        "stddev": statistics.stdev(values) if n > 1 else 0
    }
```

---

### 6. Rate Smoothing for Trend Analysis

**Apply smoothing for noisy data:**
```python
def exponential_moving_average(values: list[float], alpha: float = 0.3) -> list[float]:
    """Calculate exponentially smoothed moving average."""
    if not values:
        return []
    
    smoothed = [values[0]]
    for value in values[1:]:
        smoothed.append(alpha * value + (1 - alpha) * smoothed[-1])
    
    return smoothed

# Usage
daily_error_rates = [0.1, 0.15, 0.05, 0.2, 0.1, 0.08, 0.12]
smoothed_rates = exponential_moving_average(daily_error_rates, alpha=0.3)
```

---

### 7. Data Source Tracking

**Track data provenance:**
```python
result = {
    "metrics": {...},
    "provenance": {
        "data_sources": ["nginx.log", "pod-logs/*.log"],
        "log_files_analyzed": 5,
        "records_processed": 45000,
        "time_range": {
            "start": "2026-07-07T00:00:00Z",
            "end": "2026-08-06T23:59:59Z"
        },
        "generated_at": datetime.now().isoformat()
    }
}
```

---

## Performance Considerations

### 1. Memory Efficiency

**Stream large files:**
```python
# EFFICIENT: Stream processing
for log_file in log_files:
    with open(log_file, 'r') as f:
        for line in f:  # Stream line by line
            process_line(line)

# INEFFICIENT: Load entire file
for log_file in log_files:
    lines = open(log_file, 'r').read().splitlines()  # Memory intensive
```

---

### 2. Early Filtering

**Filter early to reduce data volume:**
```python
# EFFICIENT: Early filtering
if "ERROR" in line or "WARN" in line:
    process_line(line)

# INEFFICIENT: Process all lines
for line in log_file:
    process_line(line)  # Even INFO/DEBUG lines
```

---

### 3. Batch Processing

**Use generators for large datasets:**
```python
def duration_generator(workflows: list[dict]) -> float:
    """Yield durations one at a time (memory efficient)."""
    for workflow in workflows:
        status = workflow.get('status', {})
        started = status.get('startedAt')
        finished = status.get('finishedAt')
        
        if started and finished:
            try:
                start = datetime.fromisoformat(started.replace('Z', '+00:00'))
                end = datetime.fromisoformat(finished.replace('Z', '+00:00'))
                duration = (end - start).total_seconds()
                if duration > 0:
                    yield duration
            except:
                continue

# Usage
durations = list(duration_generator(workflows))
mean = statistics.mean(durations)
```

---

### 4. Single-Pass Aggregation

**Calculate multiple statistics in one pass:**
```python
def single_pass_stats(values: list[float]) -> dict[str, float]:
    """Calculate mean, min, max in one pass (O(n) not O(3n))."""
    if not values:
        return {"mean": 0, "min": 0, "max": 0, "count": 0}
    
    count = 0
    total = 0.0
    min_val = float('inf')
    max_val = float('-inf')
    
    for value in values:
        count += 1
        total += value
        min_val = min(min_val, value)
        max_val = max(max_val, value)
    
    return {
        "count": count,
        "mean": total / count,
        "min": min_val,
        "max": max_val,
        "sum": total
    }
```

---

## Error Handling

### 1. Comprehensive Error Handling

```python
def safe_query_with_errors(data_file: str) -> dict[str, any]:
    """Query with comprehensive error handling."""
    try:
        with open(data_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        return {"error": f"File not found: {data_file}"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}
    
    try:
        query = LatencyPercentileQuery("2026-07-07T00:00:00Z", "2026-08-06T23:59:59Z")
        # ... process data
        return query.calculate_quantiles()
    except ValueError as e:
        return {"error": f"Invalid data values: {e}"}
    except Exception as e:
        return {"error": f"Query failed: {e}"}
```

---

### 2. Empty Data Handling

```python
def handle_empty_data(values: list[float]) -> dict[str, float]:
    """Return zeros for empty data instead of crashing."""
    if not values:
        return {
            "count": 0,
            "mean": 0,
            "median": 0,
            "p50": 0,
            "p95": 0,
            "p99": 0,
            "min": 0,
            "max": 0,
            "stddev": 0,
            "sum": 0
        }
    
    # Proceed with normal calculation
    return comprehensive_stats(values)
```

---

### 3. Invalid Value Filtering

```python
def clean_values(values: list[float]) -> list[float]:
    """Filter out invalid values before aggregation."""
    return [
        v for v in values
        if v is not None
        and isinstance(v, (int, float))
        and not math.isnan(v)
        and not math.isinf(v)
        and v >= 0  # For latency, duration, counts
    ]

# Usage
raw_values = [12.5, None, 23.1, float('nan'), 45.6, float('inf'), -5.0]
clean_values_list = clean_values(raw_values)  # [12.5, 23.1, 45.6]
```

---

## Output Format

### Standard Aggregation Result Structure

```json
{
  "service": "service-name",
  "time_range": {
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z",
    "days": 30
  },
  "rate_metrics": {
    "error_rate_per_day": 0.167,
    "error_rate_per_hour": 0.00694,
    "http_5xx_error_rate": 0.0,
    "http_4xx_error_rate": 0.00006
  },
  "average_metrics": {
    "mean_latency_ms": 87.6,
    "median_latency_ms": 45.2,
    "stddev_latency_ms": 95.4,
    "sum_latency_ms": 3679.2
  },
  "percentile_metrics": {
    "count": 42,
    "p50_latency_ms": 45.2,
    "p95_latency_ms": 234.1,
    "p99_latency_ms": 412.8,
    "min_latency_ms": 12.3,
    "max_latency_ms": 523.4
  },
  "basic_metrics": {
    "total_count": 156,
    "min_value": 12.3,
    "max_value": 523.4
  },
  "data_quality": {
    "total_records": 50,
    "valid_records": 42,
    "invalid_records": 8,
    "validation_warnings": []
  },
  "query_timestamp": "2026-08-06T18:22:45.123456"
}
```

---

## Summary

This reference guide provides comprehensive documentation for all aggregation functions used in deployment data analysis:

1. **Rate functions** - `rate()`, `rate_per_day()`, `rate_per_hour()`, `rate_percent()`
2. **Average functions** - `mean()`, `median()`, `sum()`, `stddev()`
3. **Quantile/Percentile functions** - `quantiles()`, `percentiles()`, manual calculation
4. **Basic aggregations** - `count()`, `min()`, `max()`

Each function includes:
- Purpose and formula
- Python implementation examples
- SQL equivalents where applicable
- Use cases and best practices
- Error handling and data validation

Combined query examples demonstrate how to use multiple aggregation functions together for comprehensive analysis.

---

## Related Documentation

- [Rate-Based Error Query Guide](rate-based-error-query-guide.md) - Detailed rate function patterns for error analysis
- [30-Day Latency Query Examples](latency-query-examples-30d.md) - Percentile and average latency queries
- [Pattern Statistics](pattern-statistics.json) - Real-world aggregation examples

---

**Document Location:** `docs/research/deployment-data/aggregation-functions-reference.md`  
**Maintained By:** aide-de-camp project  
**Last Updated:** 2026-08-06
