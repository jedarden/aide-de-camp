# Latency Aggregation Functions and Formulas

## Overview

This document provides comprehensive documentation of latency aggregation functions used for 30-day latency analysis, including quantile calculations, averaging methods, and time-series aggregation patterns.

## Core Latency Concepts

### Duration Calculation

The fundamental latency metric is **duration** - the time elapsed between two events:

```python
duration_seconds = finished_at - started_at
```

**Examples:**
- Workflow latency: `workflow.finished_at - workflow.started_at`
- Deployment latency: `deployment.completed_at - deployment.created_at`
- Pod restart latency: `pod.started_at - pod.stopped_at`

**Important Notes:**
- Always use ISO 8601 timestamps with timezone: `2026-07-07T00:00:00Z`
- Duration must be positive (finished_at > started_at)
- Filter out invalid durations (negative, zero, or future dates)

---

## Aggregation Functions

### 1. Percentile Calculations (QUANTILE)

#### Purpose
Percentiles describe the distribution of latency values, showing what percentage of operations complete within a given time.

#### Formula
```python
from statistics import quantiles

percentiles = quantiles(durations, n=100, method='inclusive')
p50 = percentiles[49]    # 50th percentile (median)
p75 = percentiles[74]    # 75th percentile
p90 = percentiles[89]    # 90th percentile
p95 = percentiles[94]    # 95th percentile
p99 = percentiles[98]    # 99th percentile
```

#### Key Percentiles

| Percentile | Meaning | Use Case |
|------------|---------|----------|
| **p50** | Median latency - 50% of operations complete faster | Typical user experience |
| **p75** | 75th percentile - 3 out of 4 operations complete faster | Good performance baseline |
| **p90** | 90th percentile - 9 out of 10 operations complete faster | SLA targets |
| **p95** | 95th percentile - 19 out of 20 operations complete faster | Critical performance threshold |
| **p99** | 99th percentile - 99 out of 100 operations complete faster | Worst-case performance analysis |

#### Quantile Method: `inclusive`

The `inclusive` method includes both endpoints in the calculation:

```python
# For sorted data [x0, x1, ..., xn-1]
# Inclusive method uses linear interpolation between closest ranks
percentile = (n - 1) * p + 1  # where p is percentile (0.0 to 1.0)
```

**Why `inclusive`?**
- Handles edge cases better for small datasets
- Standard method for percentile calculation in statistics
- Consistent with SQL percentile functions (PERCENTILE_CONT)

#### Manual Calculation (Fallback)

If `statistics.quantiles` is unavailable:

```python
def manual_percentile(data, p):
    """
    Calculate p-th percentile (0-100 scale)
    p = 50 for p50, 95 for p95, etc.
    """
    sorted_data = sorted(data)
    n = len(sorted_data)
    index = int(n * p / 100)
    return sorted_data[min(index, n - 1)]
```

#### Example Results

**Workflow Latency Distribution (30 days):**
- p50: 1457 seconds (~24 minutes)
- p75: 3209 seconds (~53 minutes)
- p90: 10773 seconds (~3 hours)
- p95: 15541 seconds (~4.3 hours)
- p99: 19356 seconds (~5.4 hours)

**Interpretation:**
- 50% of workflows complete in under 24 minutes
- 95% of workflows complete in under 4.3 hours
- 1% of workflows take over 5.4 hours (outliers)

---

### 2. Average Calculations (AVG, MEDIAN, STDEV)

#### Purpose
Average metrics provide central tendency and variability measurements for latency data.

#### Mean (Average) Latency

```python
mean_seconds = statistics.mean(durations)
```

**Formula:**
```
mean = (d1 + d2 + ... + dn) / n
```

**Use Case:**
- Overall latency performance
- Capacity planning
- Resource allocation

**Limitations:**
- Sensitive to outliers (single long workflow skews the mean)
- Use with percentiles for complete picture

#### Median Latency

```python
median_seconds = statistics.median(durations)
```

**Formula:**
```
median = middle_value(sorted_durations)
```

**Use Case:**
- Typical user experience
- More robust to outliers than mean
- Often similar to p50 but calculated differently

**Note:** For large datasets, median ≈ p50, but they use different calculation methods.

#### Standard Deviation

```python
stddev_seconds = statistics.stdev(durations)
```

**Formula:**
```
stddev = sqrt(sum((x - mean)^2) / (n - 1))
```

**Use Case:**
- Measure latency variability
- Higher stddev = more inconsistent performance
- Use for outlier detection: `mean + 2*stddev` (95% confidence)

**Example:**
- Mean: 241,220 seconds (~67 hours)
- StdDev: 399,037 seconds (~110 hours)
- **Interpretation:** Deployment intervals are highly variable

---

### 3. Min/Max Calculations

#### Purpose
Identify extreme values in latency distribution.

```python
min_seconds = min(durations)
max_seconds = max(durations)
```

**Use Cases:**
- **Min:** Best-case performance (fastest workflow/deployment)
- **Max:** Worst-case performance (slowest workflow/deployment)
- **Range:** `max - min` shows latency spread

**Example:**
- Min: 20 seconds (exceptionally fast workflow)
- Max: 20,310 seconds (~5.6 hours, problematic outlier)
- **Range:** 20,290 seconds (significant variability)

---

### 4. Sum and Count

#### Purpose
Aggregate total time spent and operation counts.

```python
sum_seconds = sum(durations)
count = len(durations)
```

**Use Cases:**
- **Sum:** Total time spent on all operations (capacity planning)
- **Count:** Total operations analyzed (sample size validation)
- **Rate:** `sum / count` = average time per operation

---

## Advanced Aggregation Patterns

### 1. Weighted Latency Score

Combine multiple latency metrics into single score:

```python
weighted_latency = (workflow_p95 + deployment_mean) / 2
```

**Use Case:**
- Compare services with different latency profiles
- Create unified latency score for dashboards
- Balance workflow and deployment latencies

### 2. Latency Upper Bound Estimate

Estimate worst-case latency including variability:

```python
latency_upper_bound = p95 + (2 * stddev)
```

**Use Case:**
- Conservative latency estimates for SLA planning
- Capacity planning for peak loads
- Timeout threshold setting

**Interpretation:**
- 95% of operations complete under p95
- Adding 2*stddev covers ~95% confidence interval
- Result is conservative upper bound for most operations

### 3. Pod Restart Rate

Calculate restart frequency as latency indicator:

```python
restart_rate = total_restart_count / total_pods_analyzed
restart_pod_percentage = (pods_with_restarts / total_pods) * 100
```

**Use Case:**
- High restart rate indicates instability
- Correlates with latency (restarts cause delays)
- Service health metric alongside latency

---

## Time-Series Aggregation

### 1. Daily Aggregation

Group latency by day for trend analysis:

```python
from collections import defaultdict

daily_durations = defaultdict(list)

for duration in durations:
    day_key = started_at.strftime('%Y-%m-%d')
    daily_durations[day_key].append(duration)

daily_p95 = {
    day: statistics.quantiles(durs, n=100, method='inclusive')[94]
    for day, durs in daily_durations.items()
}
```

**Use Case:**
- Identify latency trends over 30 days
- Spot performance degradation
- Correlate latency with deployment events

### 2. Hourly Aggregation (for granular analysis)

```python
hourly_durations = defaultdict(list)

for duration in durations:
    hour_key = started_at.strftime('%Y-%m-%d:%H')
    hourly_durations[hour_key].append(duration)

hourly_p95 = {
    hour: statistics.quantiles(durs, n=100, method='inclusive')[94]
    for hour, durs in hourly_durations.items()
}
```

**Use Case:**
- Identify time-of-day patterns
- Detect peak-hour latency spikes
- Diagnose periodic performance issues

---

## Data Quality Validation

### 1. Sample Size Validation

Ensure sufficient data for meaningful aggregation:

```python
if count < 10:
    warning = "Sample size too small for reliable percentiles"
elif count < 30:
    warning = "Sample size moderate - use percentiles with caution"
else:
    status = "Sample size adequate for reliable aggregation"
```

**Minimum Sample Sizes:**
- **p50:** At least 10 samples
- **p95:** At least 20 samples
- **p99:** At least 100 samples (requires large dataset)

### 2. Invalid Data Filtering

```python
valid_durations = []
invalid_count = 0

for started_at, finished_at in timestamps:
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at)
        duration = (end - start).total_seconds()

        if duration > 0:
            valid_durations.append(duration)
        else:
            invalid_count += 1
    except Exception:
        invalid_count += 1
```

**Filter Rules:**
- Duration must be positive (> 0)
- Timestamps must be parseable (ISO 8601)
- Finished_at must be after started_at
- Filter future dates (data quality issue)

### 3. Outlier Detection

```python
mean = statistics.mean(durations)
stddev = statistics.stdev(durations)

outliers = [d for d in durations if abs(d - mean) > 2 * stddev]
```

**Use Case:**
- Identify anomalous operations
- Investigate outliers individually
- Consider removing for clean aggregation (with documentation)

---

## Practical Examples

### Example 1: Workflow SLA Monitoring

**SLA Requirement:** 95% of workflows complete within 6 hours (21,600 seconds)

```python
p95_workflow = quantiles(workflow_durations, n=100, method='inclusive')[94]

if p95_workflow <= 21600:
    status = "SLA_MET"
else:
    status = "SLA_VIOLATION"
    violation_seconds = p95_workflow - 21600
```

### Example 2: Deployment Performance Comparison

Compare two services:

```python
# Service A
p95_a = 15541.6
mean_a = 241220.571

# Service B
p95_b = 12345.0
mean_b = 150000.0

# Relative performance
p95_ratio = p95_a / p95_b  # 1.26x slower
mean_ratio = mean_a / mean_b  # 1.61x slower
```

### Example 3: Latency Trend Detection

Compare first 15 days vs last 15 days:

```python
first_half_p95 = quantiles(durations[:n//2], n=100, method='inclusive')[94]
second_half_p95 = quantiles(durations[n//2:], n=100, method='inclusive')[94]

if second_half_p95 > first_half_p95 * 1.2:
    trend = "DEGRADATION: p95 increased by 20%+"
elif second_half_p95 < first_half_p95 * 0.8:
    trend = "IMPROVEMENT: p95 decreased by 20%+"
else:
    trend = "STABLE: p95 within 20% of baseline"
```

---

## Performance Considerations

### 1. Quantile Calculation Performance

**Method:** `statistics.quantiles(data, n=100, method='inclusive')`

**Time Complexity:** O(n log n) due to sorting

**Optimization for Large Datasets:**
```python
# Use sampling for datasets > 10,000 points
import random

if len(durations) > 10000:
    sample = random.sample(durations, 10000)
    percentiles = statistics.quantiles(sample, n=100, method='inclusive')
else:
    percentiles = statistics.quantiles(durations, n=100, method='inclusive')
```

### 2. Memory Efficiency

For large time-series data:

```python
# Stream processing instead of loading all data
def calculate_quantiles_streaming(duration_iterator):
    durations = []
    for duration in duration_iterator:
        durations.append(duration)
        if len(durations) >= 10000:  # Process in batches
            yield statistics.quantiles(durations, n=100, method='inclusive')
            durations = []
    if durations:
        yield statistics.quantiles(durations, n=100, method='inclusive')
```

---

## Common Pitfalls

### 1. Mixing Timezones

**Problem:** Mixing UTC and local timestamps creates invalid durations

**Solution:**
```python
# Always normalize to UTC
start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
end = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
```

### 2. Small Sample Sizes

**Problem:** Calculating p99 with < 100 samples is unreliable

**Solution:**
```python
if len(durations) < 100:
    # Use p95 instead of p99
    percentile_result = p95
    warning = "Insufficient data for p99, using p95"
```

### 3. Ignoring Data Distribution

**Problem:** Using only mean/average ignores distribution shape

**Solution:** Always report percentiles alongside averages:
```python
report = {
    "mean": mean,
    "median": median,
    "p50": p50,
    "p95": p95,
    "p99": p99
}
```

---

## Query Syntax Reference

### Time Range Syntax

```python
# Absolute time range (ISO 8601)
{
    "start": "2026-07-07T00:00:00Z",
    "end": "2026-08-06T23:59:59Z"
}

# Date-only range (implicit midnight)
{
    "start_date": "2026-07-07",   # Implies T00:00:00Z
    "end_date": "2026-08-06"      # Implies T23:59:59Z
}

# Relative time range
{
    "days": 30,
    "anchor_date": "2026-08-06"
}
```

### Percentile Query Syntax

```python
SELECT
    QUANTILE(duration, 0.50) as p50,
    QUANTILE(duration, 0.95) as p95,
    QUANTILE(duration, 0.99) as p99,
    MIN(duration) as min_latency,
    MAX(duration) as max_latency
FROM workflows
WHERE started_at >= '2026-07-07T00:00:00Z'
  AND finished_at <= '2026-08-06T23:59:59Z'
```

### Average Query Syntax

```python
SELECT
    AVG(duration) as mean_latency,
    MEDIAN(duration) as median_latency,
    STDEV(duration) as stddev_latency,
    SUM(duration) as total_latency,
    COUNT(*) as operation_count
FROM deployments
WHERE created_at >= '2026-07-07T00:00:00Z'
  AND completed_at <= '2026-08-06T23:59:59Z'
```

---

## Summary

| Function | Purpose | Formula | Output |
|----------|---------|---------|--------|
| **QUANTILE** | Percentile calculation | `quantiles(data, n=100, method='inclusive')` | p50, p75, p90, p95, p99 |
| **AVG** | Mean latency | `sum(durations) / count` | Average in seconds |
| **MEDIAN** | Median latency | `middle_value(sorted_data)` | Median in seconds |
| **STDEV** | Variability | `sqrt(sum((x-mean)^2)/(n-1))` | Std dev in seconds |
| **MIN/MAX** | Extremes | `min(data)`, `max(data)` | Range bounds |
| **SUM/COUNT** | Aggregation | `sum(durations)`, `len(durations)` | Totals |

---

## References

- Python `statistics.quantiles`: https://docs.python.org/3/library/statistics.html#statistics.quantiles
- ISO 8601 timestamp format: https://en.wikipedia.org/wiki/ISO_8601
- Percentile calculation methods: https://en.wikipedia.org/wiki/Percentile
- SLA monitoring best practices: Industry standard SLO/SLA documentation
