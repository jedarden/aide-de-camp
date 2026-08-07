# VictoriaLogs Query Syntax Examples for pbx-web and whisper-stt

**Purpose:** Practical query examples for 30-day error rate and latency analysis  
**Target:** VictoriaLogs LogQL syntax  
**Services:** pbx-web, whisper-stt (whisper-openai)

## Basic Query Structure

```logql
{namespace="service-name"} |= "search-term" | range time_range
```

**Components:**
- `{selector}`: Stream selector (filters logs by labels)
- `|=`: Full-text match operator
- `| range`: Time range filter
- `|`: Pipeline for further processing

## Stream Selectors

### By Namespace

```logql
# All pbx-web logs
{namespace="pbx-web"}

# All whisper-stt logs
{namespace="whisper-stt"}

# Both services
{namespace=~"pbx-web|whisper-stt"}
```

### By Container

```logql
# pbx-web Python logs only
{namespace="pbx-web", container="site-generator"}

# pbx-web nginx logs only
{namespace="pbx-web", container="nginx"}

# whisper-stt application logs
{namespace="whisper-stt", container="whisper-openai"}
```

### By Kubernetes Labels

```logql
# Using app label
{app="pbx-web"}
{app="whisper-openai"}

# Using cluster label
{cluster="ardenone"}
```

## Error Detection Queries

### pbx-web Error Patterns

```logql
# Python application errors
{namespace="pbx-web", container="site-generator"} |= "error"
{namespace="pbx-web", container="site-generator"} |= "Error"
{namespace="pbx-web", container="site-generator"} |= "failed"
{namespace="pbx-web", container="site-generator"} |= "Exception"

# Specific error types
{namespace="pbx-web"} |= "status error"
{namespace="pbx-web"} |= "recording fetch error"
{namespace="pbx-web"} |= "rebuild failed"
{namespace="pbx-web"} |= "Failed to read sidecar"
```

### pbx-web HTTP Errors

```logql
# 5xx server errors (nginx logs)
{namespace="pbx-web", container="nginx"} |~ `"[5][0-9][0-9] "`

# 4xx client errors
{namespace="pbx-web", container="nginx"} |~ `"[4][0-9][0-9] "`

# 404 not found
{namespace="pbx-web", container="nginx"} |~ `" 404 "`

# 500 server error
{namespace="pbx-web", container="nginx"} |~ `" 500 "`
```

### whisper-stt Error Patterns

```logql
# Application errors
{namespace="whisper-stt"} |= "error"
{namespace="whisper-stt"} |= "Error"
{namespace="whisper-stt"} |= "ERROR"
{namespace="whisper-stt"} |= "failed"

# OOM kill detection
{namespace="whisper-stt"} |= "OOM"
{namespace="whisper-stt"} |= "out of memory"
{namespace="whisper-stt"} |= "Kill"
{namespace="whisper-stt"} |= "MemoryError"

# Model errors
{namespace="whisper-stt"} |= "model"
{namespace="whisper-stt"} |= "inference"
{namespace="whisper-stt"} |= "transcription"
```

## Time Range Queries

### 30-Day Ranges

```logql
# Last 30 days
{namespace="pbx-web"} |= "error" | range 30d

# Last 30 days, 1-hour resolution
{namespace="pbx-web"} |= "error" | range 30d resolution 1h

# Specific 30-day window
{namespace="whisper-stt"} |= "error" | range 2026-07-07:00:00:00Z : 2026-08-06:00:00:00Z
```

### Common Time Ranges

```logql
# Last 24 hours
{namespace="pbx-web"} | range 24h

# Last 7 days
{namespace="whisper-stt"} | range 7d

# Last 48 hours
{namespace="pbx-web"} | range 48h

# Custom range (from timestamp)
{namespace="whisper-stt"} | range 1720485600000 : 1723084799000
```

## Aggregation Queries

### Count Over Time

```logql
# Total error count over 30 days
count_over_time({namespace="pbx-web"} |= "error"[30d])

# Daily error count
count_over_time({namespace="pbx-web"} |= "error"[1d])

# Hourly error count
count_over_time({namespace="whisper-stt"} |= "error"[1h])
```

### Rate Calculations

```logql
# Error rate per minute
rate({namespace="pbx-web"} |= "error"[1m])

# Error rate per hour
rate({namespace="whisper-stt"} |= "error"[1h])

# 5-minute average rate
avg_over_time(rate({namespace="pbx-web"} |= "error"[5m])[1h])
```

## Pattern Matching

### Regex Match (`|~`)

```logql
# HTTP status codes (3 digits)
{namespace="pbx-web", container="nginx"} |~ `"[0-9][0-9][0-9] "`

# IP addresses
{namespace="pbx-web"} |~ `[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+`

# UUID patterns
{namespace="pbx-web"} |~ `[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}`
```

### Exact Match (`==`)

```logql
# Match exact error message
{namespace="pbx-web"} == "[pbx-web] rebuild failed"
```

### Not Match (`!=`)

```logql
# Exclude health check logs
{namespace="pbx-web"} != "health"
{namespace="pbx-web"} != "/health"
```

### Not Contains (`!~`)

```logql
# Exclude successful operations
{namespace="pbx-web"} !~ "success"
{namespace="pbx-web"} !~ "200 OK"
```

## Pipeline Operations

### Extract Fields

```logql
# Extract error message content
{namespace="pbx-web"} |= "error" 
| line_format "{{.log}}"

# Extract timestamp and message
{namespace="whisper-stt"} |= "error"
| line_format "{{.timestamp}}: {{.message}}"
```

### Filter by Level

```logql
# Assuming logs have level field (if structured)
{namespace="pbx-web"} | level="error"

# If no structured fields, use text matching
{namespace="pbx-web"} |= "error" |~ `"level":"error"`
```

## Combined Queries

### Multiple Conditions

```logql
# Errors in pbx-web OR whisper-stt
{namespace="pbx-web"} |= "error" or {namespace="whisper-stt"} |= "error"

# Both error AND failed
{namespace="pbx-web"} |= "error" and {namespace="pbx-web"} |= "failed"

# Error but NOT health check
{namespace="pbx-web"} |= "error" and {namespace="pbx-web"} !~ "health"
```

## API Query Examples

### curl Commands

```bash
# Port-forward first
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/vlogs-server 9428:9428

# Basic error query
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{namespace=\"pbx-web\"} |= \"error\"",
    "timeRange": "30d",
    "limit": 100
  }'

# HTTP 5xx errors
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{namespace=\"pbx-web\", container=\"nginx\"} |~ \\"5[0-9][0-9]\\"",
    "timeRange": "30d",
    "limit": 1000
  }'

# whisper-stt OOM kills
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{namespace=\"whisper-stt\"} |= \"OOM\"",
    "timeRange": "30d",
    "limit": 100
  }'

# Aggregated error count
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "count_over_time({namespace=\"pbx-web\"} |= \"error\"[30d])",
    "timeRange": "30d"
  }'
```

### Python Examples

```python
import requests
import json

# Port-forward must be active
url = "http://localhost:9428/select/logsql/query"

# pbx-web errors over 30 days
payload = {
    "query": '{namespace="pbx-web"} |= "error"',
    "timeRange": "30d",
    "limit": 10000
}

response = requests.post(url, json=payload)
results = response.json()

# Process results
for entry in results:
    timestamp = entry.get('timestamp')
    log_content = entry.get('log')
    print(f"{timestamp}: {log_content}")

# whisper-stt HTTP errors (if applicable)
payload = {
    "query": '{namespace="whisper-stt"} |= "error"',
    "timeRange": "30d",
    "limit": 5000
}

response = requests.post(url, json=payload)
errors = response.json()

# Count by error type
error_counts = {}
for entry in errors:
    log = entry.get('log', '')
    if 'OOM' in log:
        error_counts['oom'] = error_counts.get('oom', 0) + 1
    elif 'inference' in log.lower():
        error_counts['inference'] = error_counts.get('inference', 0) + 1
    else:
        error_counts['other'] = error_counts.get('other', 0) + 1

print("Error breakdown:", error_counts)
```

## Performance Considerations

### Query Optimization

1. **Use specific selectors:** Narrow results with namespace and container labels
2. **Time-box queries:** Use specific time ranges instead of open-ended queries
3. **Limit results:** Set appropriate `limit` parameter
4. **Avoid broad regex:** Use specific patterns instead of `.*`

### Large Query Handling

```bash
# For 30-day analysis, process in chunks
for day in {1..30}; do
  start_date=$(date -d "$day days ago" +%Y-%m-%d)
  curl -s -X POST http://localhost:9428/select/logsql/query \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": \"{namespace=\\\"pbx-web\\\"} |= \\\"error\\\"\",
      \"start\": \"${start_date}T00:00:00Z\",
      \"end\": \"${start_date}T23:59:59Z\"
    }"
done
```

## Common Query Patterns

### Daily Error Summary

```logql
# Count errors per day for 30 days
count_over_time({namespace="pbx-web"} |= "error"[1d])
```

### Error Rate Trends

```logql
# Hourly error rate for the last 7 days
rate({namespace="whisper-stt"} |= "error"[1h])
```

### Top Error Messages

```logql
# Group by error message (if using structured logs)
topk(10, {namespace="pbx-web"} |= "error")
```

## Time Range Syntax Reference

| Syntax | Meaning | Example |
|--------|---------|---------|
| `30d` | Last 30 days | `| range 30d` |
| `7d` | Last 7 days | `| range 7d` |
| `24h` | Last 24 hours | `| range 24h` |
| `1h` | Last 1 hour | `| range 1h` |
| `5m` | Last 5 minutes | `| range 5m` |
| `ISO:ISO` | Specific range | `| range 2026-07-01:00:00:00Z : 2026-08-01:00:00:00Z` |

## Troubleshooting Queries

### No Results Returned

1. **Check time range:** Ensure logs exist within the queried period
2. **Verify selector:** Confirm namespace and container names are correct
3. **Check retention:** VictoriaLogs has 28-day retention
4. **Test broadly:** Start with `{namespace="service-name"}` without filters

### Too Many Results

1. **Narrow selector:** Add container label
2. **Reduce time range:** Use 7d instead of 30d for testing
3. **Add filters:** Use more specific pattern matching
4. **Set limit:** Add `"limit": 100` parameter

### Query Timeouts

1. **Reduce time range:** Process in smaller chunks
2. **Limit results:** Add explicit `"limit"` parameter
3. **Optimize patterns:** Use specific instead of broad regex
4. **Use API:** For large queries, use API with pagination

## Related Documentation

- **VictoriaLogs API:** `http://localhost:9428/select/logsql/api/v1/query` (after port-forward)
- **Metrics Guide:** `/home/coding/aide-de-camp/docs/metrics-sources-and-query-guide.md`
- **Vector Config:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-application.yml`

## Quick Reference

**30-Day Error Query:**
```bash
curl -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"{namespace=\"pbx-web\"} |= \"error\"","timeRange":"30d"}'
```

**HTTP 5xx Query:**
```bash
curl -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"{namespace=\"pbx-web\",container=\"nginx\"} |~ \\"5[0-9][0-9]\","timeRange":"30d"}'
```

**Daily Error Count:**
```bash
curl -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"count_over_time({namespace=\"whisper-stt\"} |= \"error\"[1d])","timeRange":"30d"}'
```
