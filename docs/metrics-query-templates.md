# Metrics Query Templates

This document provides ready-to-use query templates for analyzing pbx-web and whisper-stt service metrics.

## Error Rate Metrics

### Victorialogs (LogQL) - Error Rate Queries

#### pbx-web HTTP Error Rates
```logql
# 5xx error rate (nginx)
count_over_time({namespace="pbx-web", container="nginx"} |~ `"[5][0-9][0-9] " `[30d])
# Returns: Count of 5xx errors in last 30 days

# 4xx client error rate (nginx)  
count_over_time({namespace="pbx-web", container="nginx"} |~ `"[4][0-9][0-9] " `[30d])
# Returns: Count of 4xx errors in last 30 days

# Error rate by response code
count by (_msg) ({namespace="pbx-web", container="nginx"} |~ `"[45][0-9][0-9] " ` | line_format "{{_msg}}"`)
# Returns: Error count grouped by HTTP status

# Recent errors (last 24 hours)
{namespace="pbx-web"} |= "error" |= "Error" |= "ERROR" | line_format "{{.timestamp}} {{.pod}}: {{_msg}}"
```

#### whisper-stt Error Detection
```logql
# Application errors and exceptions
{namespace="whisper-stt"} |= "error" |= "Error" |= "ERROR" |= "exception" |= "Exception"
# Returns: Log lines containing error indicators

# HTTP errors from whisper API
{namespace="whisper-stt", container="whisper-openai"} |~ `"[45][0-9][0-9] " `
# Returns: HTTP error responses

# Failed transcription attempts
{namespace="whisper-stt"} |= "failed" |= "Failed" |= "FAILED" |= "timeout" |= "Timeout"
# Returns: Failed processing events

# Error rate over time (hourly buckets)
sum by (hour) (count_over_time({namespace="whisper-stt"} |= "error" [1h]))
```

### Prometheus (PromQL) - Error Rate Queries

#### pbx-web Error Rates
```promql
# HTTP error rate (if nginx exposes metrics)
rate(nginx_http_requests_total{namespace="pbx-web",status=~"5.."}[5m])
# Returns: Per-second rate of 5xx errors

# Pod restart rate (indicates crashes)
increase(kube_pod_container_status_restarts_total{namespace="pbx-web"}[1h])
# Returns: Container restarts in last hour

# Liveness probe failures
rate(probe_success{namespace="pbx-web",job="kubelet"}[5m]) == 0
# Returns: Pods failing health checks
```

## Latency & Response Time Metrics

### Victorialogs (LogQL) - Latency Queries

#### pbx-web Request Duration
```logql
# Extract request duration from nginx logs
{namespace="pbx-web", container="nginx"} 
|~ `".*?([0-9]+\\.?[0-9]*)"` 
| unwrap request_duration 
| quantile_over_time(0.95)(request_duration)[30d]
# Note: Requires nginx to log request duration

# Slow requests (> 1 second)
{namespace="pbx-web", container="nginx"} |~ `request_time: [1-9]`
# Returns: Requests taking longer than 1 second

# Response time distribution
histogram_quantile(0.95, 
  sum(rate(http_request_duration_seconds_bucket{namespace="pbx-web"}[5m])) by (le)
)
```

#### whisper-stt Processing Time
```logql
# Find processing duration logs
{namespace="whisper-stt"} |= "duration" |= "processing" |= "transcription" 
| line_format "{{.timestamp}} processing_time: {{_msg}}"

# Slow transcriptions (> 10s)
{namespace="whisper-stt"} |~ `.*([1-9][0-9]+\\.?[0-9]*s).*`
# Returns: Processing operations taking > 10 seconds
```

### Prometheus (PromQL) - Latency Queries

#### General Response Time
```promql
# HTTP request duration (if service exports metrics)
rate(http_request_duration_seconds_sum{namespace="pbx-web"}[5m]) 
/ rate(http_request_duration_seconds_count{namespace="pbx-web"}[5m])

# 95th percentile latency
histogram_quantile(0.95, 
  rate(http_request_duration_seconds_bucket{namespace="pbx-web"}[5m])
)

# Average latency by service
avg(rate(http_request_duration_seconds_sum{namespace=~"pbx-web|whisper-stt"}[5m])
  / rate(http_request_duration_seconds_count{namespace=~"pbx-web|whisper-stt"}[5m])
) by (namespace)
```

## Resource Utilization Metrics

### Prometheus (PromQL) - Resource Queries

#### CPU Usage
```promql
# Current CPU usage by namespace
sum(rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m])) by (pod)
# Returns: CPU usage rate per pod

# CPU usage percentage (normalized to request)
sum(rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m])) by (pod)
/ sum(kube_pod_container_resource_requests{namespace="pbx-web",resource="cpu"}) by (pod)
* 100

# CPU utilization for whisper-stt (high-request pod)
sum(rate(container_cpu_usage_seconds_total{namespace="whisper-stt"}[5m])) by (pod)
sum(kube_pod_container_resource_requests{namespace="whisper-stt",resource="cpu"}) by (pod)

# CPU throttling (indicating resource pressure)
rate(container_cpu_cfs_throttled_periods_total{namespace="whisper-stt"}[5m])
/ rate(container_cpu_cfs_periods_total{namespace="whisper-stt"}[5m]) > 0.1
```

#### Memory Usage
```promql
# Current memory usage
sum(container_memory_usage_bytes{namespace="pbx-web"}) by (pod)
# Returns: Current memory bytes per pod

# Memory usage percentage vs limit
sum(container_memory_usage_bytes{namespace="pbx-web"}) by (pod)
/ sum(kube_pod_container_resource_limits{namespace="pbx-web",resource="memory"}) by (pod)
* 100

# Memory usage for whisper-stt (large memory footprint)
sum(container_memory_working_set_bytes{namespace="whisper-stt"}) by (pod)

# Memory pressure detection
container_memory_usage_bytes{namespace="whisper-stt"}
/ container_spec_memory_limit_bytes{namespace="whisper-stt"} > 0.9
```

#### Disk & Network I/O
```promql
# Disk read rate
sum(rate(container_fs_reads_bytes_total{namespace="pbx-web"}[5m])) by (pod)

# Disk write rate  
sum(rate(container_fs_writes_bytes_total{namespace="pbx-web"}[5m])) by (pod)

# Network traffic (if cNI metrics available)
sum(rate(container_network_receive_bytes_total{namespace="whisper-stt"}[5m])) by (pod)
sum(rate(container_network_transmit_bytes_total{namespace="whisper-stt"}[5m])) by (pod)
```

### Victorialogs (LogQL) - Resource Event Queries

#### Resource Pressure Events
```logql
# Out of memory events
{namespace="whisper-stt"} |= "OOM" |= "out of memory" |= "memory limit"

# CPU throttling events
{namespace="whisper-stt"} |= "throttling" |= "CFS throttled"

# Disk pressure events
{namespace="whisper-stt"} |= "disk pressure" |= "no space left"

# Resource exhaustion patterns
{namespace=~"pbx-web|whisper-stt"} |= "resource" |= "limit" |= "quota"
```

## Availability & Uptime Metrics

### Prometheus (PromQL) - Availability Queries

#### Pod Availability
```promql
# Pod uptime status
up{namespace="pbx-web"} == 1
# Returns: Pods that are currently up

# Pod restart count
increase(kube_pod_container_status_restarts_total{namespace="pbx-web"}[24h])
# Returns: Container restarts in last 24h

# Pod availability percentage over time
avg_over_time(up{namespace="pbx-web"}[1d]) * 100
# Returns: % uptime over last 24 hours

# CrashLoopBackOff detection
kube_pod_status_phase{namespace="whisper-stt",phase="Failed"}
```

### Combined Health Queries

#### Service Health Dashboard Query Set
```promql
# Overall service health score
(
  avg(up{namespace="pbx-web"}) 
  * avg(rate(probe_success{namespace="pbx-web"}[5m]))
  * (1 - avg(rate(kube_pod_container_status_restarts_total{namespace="pbx-web"}[1h])))
) * 100

# whisper-stt service health (accounting for resource pressure)
(
  avg(up{namespace="whisper-stt"})
  * (1 - max(rate(container_cpu_cfs_throttled_periods_total{namespace="whisper-stt"}[5m])
           / rate(container_cpu_cfs_periods_total{namespace="whisper-stt"}[5m])))
  * (1 - max(container_memory_usage_bytes{namespace="whisper-stt"} 
           / container_spec_memory_limit_bytes{namespace="whisper-stt"}))
) * 100
```

## Time Range Modifiers

### Victorialogs Time Filters
- `[1h]` - Last 1 hour
- `[24h]` - Last 24 hours  
- `[7d]` - Last 7 days
- `[30d]` - Last 30 days (full retention)

### Prometheus Time Ranges
- `[5m]` - 5 minute window
- `[1h]` - 1 hour window
- `[24h]` - 24 hour window
- Note: Limited to 10 days retention

## Usage Examples

### CLI Examples
```bash
# Query Victorialogs for pbx-web errors (last 24h)
curl -s "http://localhost:9428/select/logsql/query?query=%7Bnamespace%3D%22pbx-web%22%7D%20%7C%3D%20%22error%22%20%7C%3D%20%22Error%22%20%7C%3D%20%22ERROR%22%5B24h%5D&limit=100" | jq .

# Query Prometheus for CPU usage (current)
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(container_cpu_usage_seconds_total%7Bnamespace%3D%22pbx-web%22%7D%5B5m%5D))%20by%20(pod)" | jq .

# Get whisper-stt memory usage history
curl -s "http://localhost:9090/api/v1/query_range?query=container_memory_usage_bytes%7Bnamespace%3D%22whisper-stt%22%7D&start=$(date -d '10 days ago' +%s)&end=$(date +%s)&step=300" | jq .
```

## Notes

1. **30-day coverage**: Use Victorialogs for queries beyond 10 days
2. **Resource queries**: Prefer Prometheus for real-time, Victorialogs for events
3. **Error detection**: Victorialogs provides more flexible error pattern matching
4. **Performance**: Prometheus is more efficient for metric calculations
5. **Authorization**: All queries require VPN access or port-forward setup
