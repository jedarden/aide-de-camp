# Metrics Sources and Query Guide for pbx-web and whisper-stt

**Generated:** 2026-08-06  
**Services:** pbx-web, whisper-stt (whisper-openai)  
**Cluster:** ardenone-cluster

## Executive Summary

**Primary Metrics Storage:** VictoriaLogs (4-week retention, covers 30-day analysis)  
**Secondary Metrics:** Prometheus (10-day retention only, real-time monitoring)  
**Query Method:** VictoriaLogs LogQL via port-forward or VPN  
**Access Pattern:** Log-based metrics extracted from container logs

## Metrics Storage Locations

### 1. VictoriaLogs (Primary - 30-Day Coverage)

**Endpoint:** `http://vlogs-server.monitoring.svc.cluster.local:9428`  
**Retention:** 4 weeks (28 days)  
**Storage:** 20Gi Longhorn PVC  
**Service Account:** victoria-logs-vector (RBAC for log collection)

**Access Methods:**
```bash
# Port-forward access
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/vlogs-server 9428:9428

# Then access via
curl -s http://localhost:9428/health
```

**Web UI:** `http://localhost:9428` (after port-forward)

### 2. Prometheus (Secondary - Real-Time Only)

**Endpoint:** `http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090`  
**Retention:** 10 days only  
**Limitation:** Insufficient for 30-day analysis

**Access Methods:**
```bash
# Port-forward access
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/kube-prometheus-stack-arde-prometheus 9090:9090
```

### 3. Grafana (Visualization)

**Endpoint:** `https://grafana.ardenone.com`  
**Authentication:** Google SSO  
**Datasource:** VictoriaLogs (victoriametrics-logs-datasource)

## Service Log Sources

### pbx-web Logs

**Namespace:** `pbx-web`  
**Containers:** 
- `site-generator` (Python service, port 9000)
- `nginx` (static file server, port 80)

**Log Stream:** Collected by Vector DaemonSet → VictoriaLogs  
**Enriched Fields:**
- `cluster`: "ardenone"
- `namespace`: "pbx-web"
- `app`: "pbx-web"
- `kubernetes.container_name`: "site-generator" or "nginx"

**Log Patterns:**
```python
# Python logs (site-generator)
print(f"[pbx-web] status error for {uid}: {e}", file=sys.stderr)
print(f"[pbx-web] recording fetch error for {key}: {e}", file=sys.stderr)
print(f"[pbx-web] rebuild failed: {exc}", file=sys.stderr)

# Nginx access logs (nginx)
# HTTP status codes in access logs
```

### whisper-stt Logs

**Namespace:** `whisper-stt`  
**Containers:**
- `whisper-openai` (FastAPI/uvicorn, port 8000)

**Log Stream:** Collected by Vector DaemonSet → VictoriaLogs  
**Enriched Fields:**
- `cluster`: "ardenone"
- `namespace`: "whisper-stt"
- `app`: "whisper-openai"
- `kubernetes.container_name`: "whisper-openai"

**Log Patterns:**
```python
# FastAPI/Uvicorn logs
# Application errors and warnings
# Health check responses
# Model loading and inference logs
```

## Query Methods

### 1. VictoriaLogs LogQL Queries

**Endpoint:** `http://localhost:9428/select/logsql/query` (after port-forward)  
**Method:** POST  
**Content-Type:** application/json

**Query Structure:**
```json
{
  "query": "{namespace=\"pbx-web\"} |= \"error\"",
  "timeRange": "30d"
}
```

**Error Rate Queries:**

```logql
# pbx-web HTTP 5xx errors (nginx logs)
{namespace="pbx-web", container="nginx"} |~ `"[5][0-9][0-9] "`
| line_format "{{.timestamp}} [{{.level}}] {{.message}}"
| range 30d

# pbx-web application errors (Python stderr)
{namespace="pbx-web", container="site-generator"} |= "error" |= "Error" |= "failed"
| range 30d

# whisper-stt application errors
{namespace="whisper-stt"} |= "error" |= "Error" |= "ERROR" |= "failed"
| range 30d

# OOM kill detection
{namespace="whisper-stt"} |= "OOM" |= "out of memory" |= "Kill"
| range 30d
```

**Latency Queries:**

```logql
# No direct timing metrics in logs
# Use nginx response times if available in access logs
{namespace="pbx-web", container="nginx"} |~ `"request_time"`
| line_format "{{.request_time}}"
| range 30d
```

**Count Aggregation:**

```logql
# Error count over 30 days
count_over_time({namespace="pbx-web"} |= "error"[30d])

# Error rate per day
count_over_time({namespace="pbx-web"} |= "error"[1d])
```

### 2. API Access Examples

**Using curl:**
```bash
# Port-forward first
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/vlogs-server 9428:9428

# Query for errors
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{namespace=\"pbx-web\"} |= \"error\"",
    "timeRange": "30d",
    "limit": 1000
  }'
```

**Using Python:**
```python
import requests

# Port-forward must be active
url = "http://localhost:9428/select/logsql/query"
payload = {
    "query": '{namespace="pbx-web"} |= "error"',
    "timeRange": "30d",
    "limit": 1000
}

response = requests.post(url, json=payload)
results = response.json()
```

### 3. Prometheus PromQL Queries

**Note:** Only 10-day retention, not suitable for 30-day analysis

**Resource Usage Queries:**

```promql
# CPU usage by namespace
sum(rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m])) by (pod)

# Memory usage percentage
sum(container_memory_usage_bytes{namespace="whisper-stt"}) by (pod)

# Network error rates
sum(rate(container_network_receive_errors_total{namespace="pbx-web"}[5m])) by (pod)
```

## Metric Name Mappings

### pbx-web Metrics

**Log-Based Metrics:**
- `error_count`: Count of log lines containing "error", "Error", "failed"
- `http_5xx_rate`: Nginx 5xx status code count
- `rebuild_failure`: Rebuild operation failures
- `s3_fetch_error`: Garage S3 fetch errors

**Infrastructure Metrics:**
- `container_cpu_usage_seconds_total{namespace="pbx-web"}`
- `container_memory_usage_bytes{namespace="pbx-web"}`
- `container_network_receive_errors_total{namespace="pbx-web"}`

### whisper-stt Metrics

**Log-Based Metrics:**
- `error_count`: Application error log count
- `oom_kill_count`: OOM kill events
- `model_load_failures`: Model loading failures
- `inference_error`: Transcription inference errors

**Infrastructure Metrics:**
- `container_cpu_usage_seconds_total{namespace="whisper-stt"}`
- `container_memory_usage_bytes{namespace="whisper-stt"}`
- `container_network_receive_errors_total{namespace="whisper-stt"}`

## Authentication and Credentials

### VictoriaLogs Access

**Internal Cluster Access:** No authentication required (ClusterIP service)  
**Port-Forward Access:** No authentication required  
**VPN Access:** Not configured (disabled in service-connectors.yml.disabled)

### Prometheus Access

**Internal Cluster Access:** No authentication required (ClusterIP service)  
**Port-Forward Access:** No authentication required

### Grafana Access

**Authentication:** Google SSO required  
**URL:** `https://grafana.ardenone.com`  
**Datasource Configuration:** Auto-provisioned by VictoriaLogs datasource ConfigMap

## Query Pattern Examples for 30-Day Analysis

### Error Rate Analysis

**pbx-web HTTP Errors:**
```bash
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{namespace=\"pbx-web\", container=\"nginx\"} |~ \\"5[0-9][0-9]\\"",
    "timeRange": "30d",
    "limit": 10000
  }' | jq '.[] | .timestamp'
```

**whisper-stt Application Errors:**
```bash
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{namespace=\"whisper-stt\"} |= \"error\" |= \"Error\"",
    "timeRange": "30d",
    "limit": 10000
  }' | jq '.[] | .log'
```

### Daily Error Count Pattern

```bash
# Day-by-day error count
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "count_over_time({namespace=\"pbx-web\"} |= \"error\"[1d])",
    "timeRange": "30d"
  }'
```

### Latency Pattern Analysis

**Note:** Direct latency metrics not available in logs. Use infrastructure metrics:

```promql
# Container CPU as latency proxy (high CPU = slow response)
sum(rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m])) by (pod)

# Memory pressure indicator
sum(container_memory_usage_bytes{namespace="whisper-stt"}) by (pod)
```

## Limitations and Gaps

### Missing Components

1. **No ServiceMonitor Resources:** Neither pbx-web nor whisper-stt has ServiceMonitor/PodMonitor resources for Prometheus scraping
2. **No Application Metrics Endpoints:** Services do not expose `/metrics` endpoints
3. **No Custom Dashboards:** Grafana has no dashboards specific to these services
4. **No Alerting Rules:** No Prometheus alerting rules for error rates or latency
5. **Log-Based Metrics Only:** Error rates derived from log pattern matching, not structured metrics

### Coverage Gaps

1. **Latency Metrics:** No application-level latency timing in logs
2. **Request Rates:** No structured request count metrics
3. **User Tracking:** No caller-ID or user-based metrics in logs
4. **Business Metrics:** No transcription success rates, call duration metrics

## Recommended Query Workflow

1. **Establish Port-Forward:**
   ```bash
   kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
     -n monitoring svc/vlogs-server 9428:9428
   ```

2. **Test Query:**
   ```bash
   curl -s http://localhost:9428/health
   ```

3. **Execute Error Rate Query:**
   ```bash
   curl -s -X POST http://localhost:9428/select/logsql/query \
     -H "Content-Type: application/json" \
     -d '{"query":"{namespace=\"pbx-web\"} |= \"error\"","timeRange":"30d"}'
   ```

4. **Analyze Results:** Process JSON response for error patterns and timestamps

## Related Documentation

- **VictoriaLogs Configuration:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-application.yml`
- **Grafana Datasource:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-grafana-datasource.yml`
- **pbx-web Deployment:** `/home/coding/declarative-config/k8s/ardenone-cluster/pbx-web/pbx-web-deployment.yml`
- **whisper-stt Deployment:** `/home/coding/declarative-config/k8s/ardenone-cluster/whisper-stt/whisper-openai-deployment.yml`
- **Vector Config:** Embedded in victorialogs-application.yml (lines 108-168)

## Conclusion

**Primary Metrics Source:** VictoriaLogs (28-day retention, log-based metrics)  
**Query Method:** VictoriaLogs LogQL via port-forward  
**Access Pattern:** Log pattern matching for error rates  
**Latency Metrics:** Limited to infrastructure resource usage  
**Authentication:** Internal cluster access only (no external VPN)

Both services rely on infrastructure metrics and log-based error detection rather than structured application metrics. For 30-day error rate analysis, query VictoriaLogs for error patterns in container logs. For latency analysis, use Prometheus infrastructure metrics as a proxy for performance degradation.
