# Metrics Aggregation Functions Reference

This document provides comprehensive documentation for aggregation functions used in error rates and latency metrics queries in Victorialogs (LogQL) and Prometheus (PromQL).

## Table of Contents
1. [Rate Functions](#rate-functions)
2. [Average Functions](#average-functions)
3. [Quantile Functions](#quantile-functions)
4. [Count Functions](#count-functions)
5. [Sum Functions](#sum-functions)
6. [Increase Functions](#increase-functions)
7. [Combined Usage Examples](#combined-usage-examples)

---

## Rate Functions

### `rate()`

**Syntax:** `rate(metric[time_range])`

**Description:** Calculates the per-second average rate of increase for a counter metric over the specified time range. This is the most common function for calculating error rates, request rates, and other counter-based metrics.

**Use Cases:**
- Calculating error rates per second
- Measuring request throughput
- Tracking container resource usage rates
- Computing derivative metrics from counters

**Parameters:**
- `metric`: A counter metric (e.g., `http_requests_total`, `container_cpu_usage_seconds_total`)
- `time_range`: Time window for rate calculation (e.g., `[5m]`, `[1h]`, `[24h]`)

**Examples:**

```promql
# HTTP 5xx error rate (errors per second)
rate(nginx_http_requests_total{namespace="pbx-web",status=~"5.."}[5m])

# Container CPU usage rate (CPU seconds per second = CPU cores used)
rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m])

# Network receive rate (bytes per second)
rate(container_network_receive_bytes_total{namespace="whisper-stt"}[5m])

# Disk write rate (bytes per second)
rate(container_fs_writes_bytes_total{namespace="pbx-web"}[5m])
```

**Important Notes:**
- Use with **counter metrics** only (metrics that only increase)
- Automatically handles counter resets
- Result is in "units per second"
- Recommended time range: `4x` the scrape interval (e.g., `[1m]` for 15s scrape)

---

### `irate()`

**Syntax:** `irate(metric[time_range])`

**Description:** Calculates the **instantaneous** per-second rate using only the last two data points in the time range. More reactive than `rate()` but more volatile.

**Use Cases:**
- Alerting on sudden rate spikes
- Real-time monitoring where immediate response is needed
- Debugging sudden changes in system behavior

**Parameters:**
- Same as `rate()`

**Examples:**

```promql
# Instantaneous HTTP error rate (for alerting)
irate(http_requests_total{status=~"5.."}[5m])

# Instantaneous CPU throttling rate
irate(container_cpu_cfs_throttled_periods_total{namespace="whisper-stt"}[5m])
```

**Important Notes:**
- More volatile than `rate()` - expect spikes
- Better for alerting, worse for dashboards
- Uses only last two samples in range

---

## Average Functions

### `avg()`

**Syntax:** `avg(metric)` or `avg(metric) by (label1, label2)`

**Description:** Calculates the arithmetic mean across all matching time series. Returns a single value (or per-label values with `by` clause).

**Use Cases:**
- Computing average latency across pods
- Average resource utilization across a namespace
- Calculating average error rates across instances

**Parameters:**
- `metric`: Any metric or metric expression
- Optional `by (labels)`: Group by specific labels

**Examples:**

```promql
# Average pod uptime across namespace
avg(up{namespace="pbx-web"})

# Average CPU usage by pod
avg(rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m])) by (pod)

# Average memory usage percentage
avg(
  container_memory_usage_bytes{namespace="pbx-web"}
  / container_spec_memory_limit_bytes{namespace="pbx-web"}
  * 100
) by (pod)

# Average HTTP request duration across all instances
avg(
  rate(http_request_duration_seconds_sum{namespace="pbx-web"}[5m])
  / rate(http_request_duration_seconds_count{namespace="pbx-web"}[5m])
)
```

**Important Notes:**
- Returns a single time series (or per-group with `by`)
- Works across multiple time series
- Can be combined with other functions for complex calculations

---

### `avg_over_time()`

**Syntax:** `avg_over_time(metric[time_range])`

**Description:** Calculates the average value of a single time series over the specified time range. Differs from `avg()` in that it averages **over time** for one series, not across multiple series.

**Use Cases:**
- Calculating percentage uptime over a time window
- Smoothing out gauge metric fluctuations
- Computing average availability percentages

**Parameters:**
- `metric`: A single time series or label selector
- `time_range`: Time window (e.g., `[1d]`, `[7d]`, `[30d]`)

**Examples:**

```promql
# Pod uptime percentage over 24 hours
avg_over_time(up{namespace="pbx-web"}[1d]) * 100

# Average memory usage percentage over last hour
avg_over_time(
  container_memory_usage_bytes{namespace="whisper-stt",pod="pod-1"}
  / container_spec_memory_limit_bytes{namespace="whisper-stt",pod="pod-1"}
  * 100
[1h])

# Average CPU usage over last day for specific pod
avg_over_time(
  rate(container_cpu_usage_seconds_total{namespace="pbx-web",pod="pod-1"}[5m])
[1d])
```

**Important Notes:**
- Averages over **time**, not across series
- Commonly used with gauge metrics
- Returns smoothed, less volatile values

---

## Quantile Functions

### `histogram_quantile()`

**Syntax:** `histogram_quantile(φ, histogram_metric)`

**Description:** Calculates the φ-quantile (0 ≤ φ ≤ 1) from a Prometheus histogram bucket metric. This is the standard function for computing percentiles like p50, p95, p99.

**Use Cases:**
- Computing p50 (median), p95, p99 latencies
- Analyzing request duration distributions
- Understanding worst-case performance scenarios

**Parameters:**
- `φ`: Quantile to calculate (0.5 = median, 0.95 = 95th percentile, 0.99 = 99th percentile)
- `histogram_metric`: Histogram bucket metric with `le` (less than or equal) labels

**Examples:**

```promql
# 95th percentile HTTP request duration
histogram_quantile(0.95, 
  rate(http_request_duration_seconds_bucket{namespace="pbx-web"}[5m])
)

# 99th percentile latency (worst-case performance)
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{namespace="pbx-web"}[5m])) by (le, instance)
)

# Median (p50) processing time
histogram_quantile(0.5,
  rate(whisper_transcription_duration_seconds_bucket{namespace="whisper-stt"}[5m])
)

# Multiple percentiles in one query (for Grafana dashboard)
histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
```

**Important Notes:**
- Requires **histogram bucket** metrics (with `le` labels)
- Must use `rate()` or `irate()` on histogram buckets first
- Result is in the same unit as the histogram (seconds, bytes, etc.)
- Extrapolates for incomplete buckets - may be inaccurate for sparse data

---

### `quantile_over_time()`

**Syntax:** `quantile_over_time(φ, metric[time_range])` (LogQL only)

**Description:** Calculates the φ-quantile over values in the specified time range. This is a **Victorialogs (LogQL) function** for computing percentiles from time series data.

**Use Cases:**
- Computing percentiles from extracted log values
- Analyzing latency distributions from log data
- Time-based percentile calculations when histograms aren't available

**Parameters:**
- `φ`: Quantile to calculate (0.95 = 95th percentile)
- `metric`: A metric or extracted value with time range
- `time_range`: Time window (e.g., `[30d]`, `[7d]`, `[1h]`)

**Examples:**

```logql
# 95th percentile request duration from nginx logs (Victorialogs)
{namespace="pbx-web", container="nginx"} 
|~ `".*?([0-9]+\\.?[0-9]*)"` 
| unwrap request_duration 
| quantile_over_time(0.95)(request_duration)[30d]

# Extract processing time and compute 99th percentile (LogQL)
{namespace="whisper-stt"} |= "duration"
| unwrap processing_time
| quantile_over_time(0.99)(processing_time)[7d]

# 90th percentile of extracted numeric values
{namespace="pbx-web"} | json | unwrap response_time
| quantile_over_time(0.90)(response_time)[24h]
```

**Important Notes:**
- **LogQL only** - Not available in PromQL
- Works with `| unwrap` to extract numeric values from logs
- Can compute percentiles from any numeric log field
- Time range affects data included in percentile calculation

---

## Count Functions

### `count_over_time()`

**Syntax:** `count_over_time(log_query[time_range])` (LogQL only)

**Description:** Counts the number of log entries matching the query over the specified time range. This is a **Victorialogs (LogQL) function** for counting log events.

**Use Cases:**
- Counting error occurrences over time
- Counting HTTP 4xx/5xx responses from logs
- Analyzing event frequency patterns

**Parameters:**
- `log_query`: A log selector query (e.g., `{namespace="app"} |= "error"`)
- `time_range`: Time window (e.g., `[24h]`, `[30d]`, `[7d]`)

**Examples:**

```logql
# Count 5xx errors in last 30 days
count_over_time({namespace="pbx-web", container="nginx"} |~ `"[5][0-9][0-9] " ` [30d])

# Count application errors in last hour
count_over_time({namespace="whisper-stt"} |= "error" |= "Error" |= "ERROR" [1h])

# Count failed transcription attempts in last week
count_over_time({namespace="whisper-stt"} |= "failed" |= "Failed" |= "FAILED" [7d])

# Error rate by hour (time-series count)
sum by (hour) (count_over_time({namespace="whisper-stt"} |= "error" [1h]))
```

**Important Notes:**
- **LogQL only** - Not available in PromQL
- Counts **log lines**, not metric values
- Can be combined with `|~` (regex) and `|=` (exact match)
- Returns total count, not rate

---

## Sum Functions

### `sum()`

**Syntax:** `sum(metric)` or `sum(metric) by (label1, label2)`

**Description:** Sums values across all matching time series. Returns a single value (or per-label values with `by` clause).

**Use Cases:**
- Total resource usage across namespace
- Summing request counts across all pods
- Aggregating error counts by service

**Parameters:**
- `metric`: Any metric or expression
- Optional `by (labels)`: Group by specific labels

**Examples:**

```promql
# Total CPU usage across namespace (in cores)
sum(rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m]))

# Total memory usage across all pods
sum(container_memory_usage_bytes{namespace="whisper-stt"}) by (pod)

# Sum HTTP 5xx errors by status code
sum(rate(http_requests_total{namespace="pbx-web",status=~"5.."}[5m])) by (status)

# Network traffic summed by pod
sum(rate(container_network_receive_bytes_total{namespace="whisper-stt"}[5m])) by (pod)
```

**Important Notes:**
- Useful for aggregating across dimensions
- Use `by (label)` to preserve grouping
- Can be combined with `rate()` for rate sums

---

## Increase Functions

### `increase()`

**Syntax:** `increase(metric[time_range])`

**Description:** Calculates the **total increase** in a counter metric over the specified time range. Similar to `rate()` but returns the absolute increase, not per-second rate.

**Use Cases:**
- Counting total events in a time window
- Measuring total restarts in last hour
- Calculating total requests processed in a period

**Parameters:**
- `metric`: A counter metric
- `time_range`: Time window for increase calculation

**Examples:**

```promql
# Container restarts in last 24 hours
increase(kube_pod_container_status_restarts_total{namespace="pbx-web"}[24h])

# Total HTTP requests in last hour
increase(http_requests_total{namespace="pbx-web"}[1h])

# Total network bytes received in last day
increase(container_network_receive_bytes_total{namespace="whisper-stt"}[24h])
```

**Important Notes:**
- Returns **absolute count**, not rate
- Automatically handles counter resets
- Commonly used for "count of events in time window" queries

---

## Combined Usage Examples

### Error Rate Dashboard Query

```promql
# Error rate percentage (total errors / total requests)
sum(rate(http_requests_total{namespace="pbx-web",status=~"5.."}[5m]))
/ sum(rate(http_requests_total{namespace="pbx-web"}[5m]))
* 100
```

### Average Latency by Service

```promql
# Average request duration across all instances
avg(
  rate(http_request_duration_seconds_sum{namespace="pbx-web"}[5m])
  / rate(http_request_duration_seconds_count{namespace="pbx-web"}[5m])
) by (pod)
```

### 95th Percentile Latency with Error Rate

```promql
# Combined dashboard query
{
  # Latency
  "p95_latency": histogram_quantile(0.95, 
    rate(http_request_duration_seconds_bucket{namespace="pbx-web"}[5m])
  ),
  
  # Error rate
  "error_rate": sum(rate(http_requests_total{namespace="pbx-web",status=~"5.."}[5m]))
}
```

### Resource Utilization Score

```promql
# Combined health score (0-100)
(
  avg(up{namespace="pbx-web"}) 
  * avg(rate(probe_success{namespace="pbx-web"}[5m]))
  * (1 - avg(rate(kube_pod_container_status_restarts_total{namespace="pbx-web"}[1h])))
) * 100
```

### Victorialogs Multi-Function Query

```logql
# Complex LogQL query combining multiple aggregation functions
{namespace="whisper-stt"} 
|~ `duration:\s+(\d+\.\d+)`
| unwrap processing_duration
| quantile_over_time(0.95)(processing_duration)[30d]
```

---

## Quick Reference Table

| Function | Type | Use Case | Returns |
|----------|------|----------|---------|
| `rate()` | PromQL | Per-second rate from counter | units/second |
| `irate()` | PromQL | Instantaneous rate (reactive) | units/second |
| `avg()` | PromQL | Average across series | single value |
| `avg_over_time()` | PromQL | Average over time window | time series |
| `histogram_quantile()` | PromQL | Percentile from histogram buckets | scalar value |
| `quantile_over_time()` | LogQL | Percentile over time range | scalar value |
| `count_over_time()` | LogQL | Count log lines in range | total count |
| `sum()` | PromQL | Sum across series | single value |
| `increase()` | PromQL | Total increase in range | absolute count |

---

## Performance Considerations

### Best Practices

1. **Use appropriate time ranges:**
   - Short ranges (`[1m]`, `[5m]`) for real-time metrics
   - Long ranges (`[1h]`, `[24h]`) for trends and analysis

2. **Choose the right function:**
   - `rate()` for steady-state monitoring
   - `irate()` for alerting on spikes
   - `avg_over_time()` for smoothing gauge metrics
   - `histogram_quantile()` for latency percentiles

3. **Optimize queries:**
   - Use `by (label)` to reduce result cardinality
   - Combine functions to reduce query count
   - Use `sum()` and `avg()` for aggregation instead of multiple queries

4. **Victorialogs vs Prometheus:**
   - Use Victorialogs for `count_over_time()` and `quantile_over_time()`
   - Use Prometheus for `histogram_quantile()` and standard metric functions
   - Victorialogs has longer retention (30 days), Prometheus is real-time

---

## Testing Your Queries

### CLI Testing

```bash
# Test PromQL query (Prometheus)
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(container_cpu_usage_seconds_total%7Bnamespace%3D%22pbx-web%22%7D%5B5m%5D))" | jq .

# Test LogQL query (Victorialogs)
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D%20%7C%3D%20%22error%22%20%7C%7E%20%225%5B0-9%5D%5B0-9%5D%20%22%20%5B24h%5D" | jq .

# Query with time range (Prometheus)
curl -s "http://localhost:9090/api/v1/query_range?query=rate(http_requests_total%5B5m%5D)&start=$(date -d '1 hour ago' +%s)&end=$(date +%s)&step=60" | jq .
```

---

## Related Documentation

- [Metrics Query Templates](metrics-query-templates.md) - Ready-to-use query templates
- [Metrics Infrastructure Summary](metrics-infrastructure-summary.md) - Tools and access guide
- [Query Patterns and Time Ranges](query-patterns-and-time-ranges.md) - Time range syntax reference
