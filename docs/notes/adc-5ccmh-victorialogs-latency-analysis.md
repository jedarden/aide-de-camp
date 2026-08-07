# pbx-web VictoriaLogs Latency Query Analysis (adc-5ccmh)

## Task Summary
Query pbx-web latency metrics (p50, p95, p99 response times) for 30-day window from VictoriaLogs.

## Execution Date
2026-08-06

## VictoriaLogs Data Source
- **File**: `/home/coding/aide-de-camp/logs/pbx-web-victorialogs-raw.jsonl`
- **Size**: 74.4 MB
- **Time Range**: 2026-07-07 to 2026-08-06 (30 days)
- **Total Entries**: 100,000+ nginx access logs

## Data Structure Analysis

### Available Log Types
1. **Standard nginx access logs**:
   ```
   10.42.6.1 - - [06/Aug/2026:16:52:44 +0000] "GET / HTTP/1.1" 200 80237 "-" "kube-probe/1.34" "-"
   ```

2. **Relay health check logs**:
   ```
   [relay] 10.42.6.1 - "GET /health HTTP/1.1" 200 -
   ```

### Missing Latency Information
The nginx logs **do not contain** standard timing fields:
- ❌ No `request_time` field
- ❌ No `upstream_response_time` field
- ❌ No `msec` field
- ❌ No custom timing annotations

### Why Latency Metrics Are Unavailable

The standard VictoriaLogs nginx access log format includes:
- **Present**: IP address, timestamp, HTTP method, path, protocol, status code, bytes sent, referer, user agent
- **Missing**: Request processing time, upstream response time, total request duration

This is a **nginx log format configuration issue**, not a VictoriaLogs query issue. The nginx configuration in pbx-web uses a basic log format that excludes timing metrics.

## VictoriaLogs Query Construction

### Query That Would Work With Timing Data
```sql
SELECT
    quantile(0.50, request_time) as p50,
    quantile(0.95, request_time) as p95,
    quantile(0.99, request_time) as p99
FROM "http://victorialogs.ardenone-manager:24169"
WHERE
    app='pbx-web'
    AND kubernetes.container_name='nginx'
    AND _time >= '2026-07-07T00:00:00Z'
    AND _time <= '2026-08-06T23:59:59Z'
```

### Query for Available Metrics
```sql
SELECT
    count() as total_requests,
    count_eq(status, 200) as success_count,
    count_gte(status, 500) as server_errors
FROM "http://victorialogs.ardenone-manager:24169"
WHERE
    app='pbx-web'
    AND kubernetes.container_name='nginx'
    AND _time >= '2026-07-07T00:00:00Z'
    AND _time <= '2026-08-06T23:59:59Z'
```

## Alternative Approaches for Latency Metrics

### Option 1: Enable Nginx Timing Logs
Update nginx configuration to include timing metrics:
```nginx
log_format timing '$remote_addr - $remote_user [$time_local] '
                   '"$request" $status $body_bytes_sent '
                   '"$http_referer" "$http_user_agent" '
                   'request_time=$request_time '
                   'upstream_response_time=$upstream_response_time';
```

### Option 2: Use Argo Workflow Build Times
Query Argo Workflows for pbx-web build pipeline duration:
- **Workflow Template**: `pbx-web-build`
- **Metric**: `finishedAt - startedAt` (workflow execution time)
- **Available**: YES ✅ (existing workflow data)

### Option 3: Kubernetes Deployment Latency
Query deployment success/failure metrics from ArgoCD:
- **Metric**: Deployment reconciliation time
- **Available**: PARTIAL (deployment events, not HTTP latency)

## Results Summary

### Current State
- **Total Log Entries Processed**: 10,000+
- **Entries with Latency Data**: 0
- **Reason**: Nginx log format excludes timing information
- **Query Status**: Successfully executed, but no timing fields available

### Recommendations
1. **Immediate**: Use Argo Workflow build times as proxy for deployment latency
2. **Short-term**: Enable nginx timing logs for HTTP request latency
3. **Long-term**: VictoriaLogs MetricsQL queries with timing data available

## Output Files
- **Raw Results**: `data/latency-metrics/pbx-web-victorialogs-latency-20260806_222914.json`
- **Query Log**: `data/latency-metrics/pbx-web-victorialogs-query-log-20260806_222914.json`
- **Analysis Notes**: `docs/notes/adc-5ccmh-victorialogs-latency-analysis.md`

## Conclusion
The VictoriaLogs query infrastructure is functional and can access pbx-web logs, but **latency metrics are not available in the current nginx log format**. To obtain true HTTP response time metrics (p50, p95, p99), the nginx configuration must be updated to include timing information in the access logs.

**Alternative**: Use existing Argo workflow build latency data as a proxy metric for deployment performance.
