# Metrics Quick Reference: pbx-web and whisper-stt

**Last Updated:** 2026-08-06  
**Purpose:** Quick reference for metrics access and queries

## TL;DR - One-Line Summary

**VictoriaLogs** (`http://localhost:9428`) is your 30-day metrics source. Port-forward first, then query with LogQL. Prometheus has only 10-day retention.

## Access Pattern

```bash
# 1. Port-forward VictoriaLogs
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/vlogs-server 9428:9428

# 2. Query for errors (30 days)
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"{namespace=\"pbx-web\"} |= \"error\"","timeRange":"30d"}'
```

## Metrics Sources

| Source | Endpoint | Retention | Use For |
|--------|----------|-----------|---------|
| **VictoriaLogs** | `http://vlogs-server:9428` | 28 days | 30-day error analysis |
| Prometheus | `http://kube-prometheus-stack-arde-prometheus:9090` | 10 days | Real-time monitoring |
| Grafana | `https://grafana.ardenone.com` | N/A | Visualization (Google SSO) |

## Service Stream Selectors

```
pbx-web:          {namespace="pbx-web"}
whisper-stt:      {namespace="whisper-stt"}
pbx-web nginx:    {namespace="pbx-web", container="nginx"}
pbx-web Python:   {namespace="pbx-web", container="site-generator"}
```

## Error Rate Queries (30-Day)

### pbx-web Errors

```bash
# Application errors (Python)
curl -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"{namespace=\"pbx-web\"} |= \"error\"","timeRange":"30d"}'

# HTTP 5xx errors (nginx)
curl -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"{namespace=\"pbx-web\",container=\"nginx\"} |~ \\"5[0-9][0-9]\","timeRange":"30d"}'
```

### whisper-stt Errors

```bash
# Application errors
curl -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"{namespace=\"whisper-stt\"} |= \"error\"","timeRange":"30d"}'

# OOM kills
curl -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"{namespace=\"whisper-stt\"} |= \"OOM\"","timeRange":"30d"}'
```

## Metric Name Mappings

### pbx-web

| Metric Type | Log Pattern | VictoriaLogs Query |
|-------------|--------------|-------------------|
| HTTP Errors | `5xx` status codes | `{container="nginx"} |~ "5[0-9][0-9]"` |
| App Errors | `error`, `failed` | `{container="site-generator"} |= "error"` |
| S3 Errors | `recording fetch error` | `|= "recording fetch error"` |
| Rebuild Failures | `rebuild failed` | `|= "rebuild failed"` |

### whisper-stt

| Metric Type | Log Pattern | VictoriaLogs Query |
|-------------|--------------|-------------------|
| App Errors | `error`, `Error` | `|= "error"` |
| OOM Kills | `OOM`, `Kill` | `|= "OOM"` |
| Model Errors | `inference`, `model` | `|= "inference"` |
| Memory Issues | `MemoryError` | `|= "MemoryError"` |

## Latency Metrics

**Not available in logs.** Use Prometheus infrastructure metrics as proxy:

```promql
# CPU usage (latency proxy)
sum(rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m])) by (pod)

# Memory pressure
sum(container_memory_usage_bytes{namespace="whisper-stt"}) by (pod)
```

## Authentication

| Method | Auth Required |
|--------|---------------|
| VictoriaLogs port-forward | No |
| VictoriaLogs VPN | Not configured |
| Prometheus port-forward | No |
| Grafana web UI | Google SSO |

## Time Range Syntax

```
30d = last 30 days
7d  = last 7 days
24h = last 24 hours
1h  = last 1 hour
```

## Limitations

- No ServiceMonitor resources for these services
- No `/metrics` endpoints on services
- No application-level latency timing in logs
- Prometheus retention insufficient for 30-day analysis
- Log-based metrics only (pattern matching)

## Quick Commands

```bash
# Setup port-forward
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/vlogs-server 9428:9428

# Test connection
curl -s http://localhost:9428/health

# pbx-web error count (30 days)
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"count_over_time({namespace=\"pbx-web\"} |= \"error\"[30d])"}'

# whisper-stt error count (30 days)
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"count_over_time({namespace=\"whisper-stt\"} |= \"error\"[30d])"}'

# Daily error breakdown (30 days)
curl -s -X POST http://localhost:9428/select/logsql/query \
  -H "Content-Type: application/json" \
  -d '{"query":"count_over_time({namespace=\"pbx-web\"} |= \"error\"[1d])","timeRange":"30d"}'
```

## File Locations

```
VictoriaLogs config:  /home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-application.yml
pbx-web deployment:  /home/coding/declarative-config/k8s/ardenone-cluster/pbx-web/pbx-web-deployment.yml
whisper-stt deployment: /home/coding/declarative-config/k8s/ardenone-cluster/whisper-stt/whisper-openai-deployment.yml
Grafana datasource:  /home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-grafana-datasource.yml
```

## What Works

✅ 28-day error rate analysis via VictoriaLogs  
✅ Real-time monitoring via Prometheus  
✅ Log-based error detection and counting  
✅ Infrastructure resource metrics (CPU, memory)  
✅ HTTP error rate analysis from nginx logs

## What Doesn't Work

❌ Application-level latency timing  
❌ User-based metrics (caller-ID tracking)  
❌ Business metrics (transcription success rates)  
❌ 30-day queries in Prometheus (10-day retention)  
❌ Structured application metrics endpoints

## Key Takeaway

For 30-day error rate analysis: **Use VictoriaLogs** with port-forward and LogQL queries. For latency: Use **Prometheus infrastructure metrics** as a performance proxy. Services have no custom metrics exporters.
