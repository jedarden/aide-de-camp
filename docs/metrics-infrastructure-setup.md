# Metrics Collection Infrastructure Setup

## Overview

This document describes the metrics collection infrastructure for `pbx-web` and `whisper-stt` services deployed on `ardenone-cluster`.

## Observability Tools Available

### 1. Victorialogs (Primary Logs & Metrics Store)
- **Service**: `vlogs-server` in `monitoring` namespace
- **Port**: 9428
- **Retention**: **4 weeks (28 days)** ✅ *Meets 30-day requirement*
- **Access Methods**: 
  - VPN: `https://vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com:9428`
  - Port-forward: `kubectl port-forward -n monitoring svc/vlogs-server 9428:9428`
- **Primary Use Case**: Log aggregation and querying with full 30-day coverage

### 2. Prometheus (Metrics Collection)
- **Service**: `kube-prometheus-stack-arde-prometheus` in `monitoring` namespace
- **Port**: 9090
- **Retention**: **10 days** ⚠️ *Does NOT meet 30-day requirement*
- **Access Methods**:
  - Port-forward: `kubectl port-forward -n monitoring svc/kube-prometheus-stack-arde-prometheus 9090:9090`
  - VPN: Via Grafana proxy (if configured)
- **Primary Use Case**: Real-time metrics and alerting (last 10 days only)

### 3. Grafana (Visualization)
- **Service**: `kube-prometheus-stack-ardenone-cluster-grafana` in `monitoring` namespace
- **Port**: 80
- **Access**: `https://grafana.ardenone.com` (public via Cloudflare Tunnel)
- **Primary Use Case**: Dashboard visualization and query building

## Service Discovery

### pbx-web Service
- **Namespace**: `pbx-web`
- **Pods**: `pbx-web-5ff68464d-mkn8n` (2 containers: site-generator, nginx)
- **Resources**: CPU requests 10m-500m, Memory 128Mi-512Mi
- **Health Checks**: HTTP /health on port 9000 (site-generator)

### whisper-stt Service  
- **Namespace**: `whisper-stt`
- **Pods**: `whisper-openai-68966786fb-jsb5d` (container: whisper-openai)
- **Resources**: CPU requests 1000m-8000m, Memory 4Gi-8Gi
- **Health Checks**: HTTP /health on port 8080

## Connectivity & Access Requirements

### VPN Access Required
Both Victorialogs and Prometheus require VPN access via Tailscale:
- **Victorialogs VPN**: `vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com`
- **Grafana**: Public access available at `grafana.ardenone.com`
- **kubectl proxy**: Read-only access via `http://traefik-ardenone-cluster:8001`

### Authentication
- **No authentication required** for kubectl proxy (read-only)
- **VPN certificate** required for direct service access
- **Grafana authentication** via Google SSO for dashboard access

## Metric Availability Summary

| Tool | Retention | 30-Day Coverage | Primary Access | Auth Required |
|------|-----------|-----------------|-----------------|---------------|
| Victorialogs | 28 days | ✅ Yes | VPN / Port-forward | VPN cert |
| Prometheus | 10 days | ❌ No | Port-forward | VPN cert |
| Grafana | N/A (visualization) | ✅ Yes (via Victorialogs) | Public URL | Google SSO |

## Data Sources

### Available Metrics (Prometheus)
- `container_cpu_usage_seconds_total` - CPU usage per container
- `container_memory_usage_bytes` - Memory usage per container  
- `container_fs_reads_bytes_total` - Disk read operations
- `container_fs_writes_bytes_total` - Disk write operations
- `rate(http_requests_total[5m])` - HTTP request rate
- `up{namespace="..."}` - Pod availability status

### Available Logs (Victorialogs)
- Kubernetes pod logs with full metadata
- Labels: `namespace`, `app`, `kubernetes.pod_name`, `kubernetes.container_name`
- Log types: nginx access logs, application logs, health check logs
- Full-text search and field extraction available

## Limitations & Constraints

### Prometheus Limitations
- **10-day retention** - Cannot provide 30-day metrics directly
- Must use Victorialogs for historical log-based metrics beyond 10 days
- No direct public access - requires VPN or port-forward

### Victorialogs Limitations  
- Requires VPN connection for API access
- No built-in visualization - requires Grafana or custom queries
- LogQL syntax required for complex queries

### General Constraints
- VPN connectivity required for most operations
- No public metrics API endpoints (except Grafana)
- kubectl proxy provides read-only cluster access

## Query Templates

See separate sections below for detailed query templates for each metric type.
