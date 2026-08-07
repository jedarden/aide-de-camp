# Metrics Endpoints Documentation

**Generated:** 2026-08-07  
**Services:** pbx-web, whisper-stt  
**Cluster:** ardenone-cluster  

## Overview

This document identifies and documents all metrics and health endpoints for the pbx-web and whisper-stt services, including monitoring infrastructure endpoints.

---

## Monitoring Infrastructure Endpoints

### VictoriaLogs (Primary Metrics Source)

**Purpose:** Long-term metrics storage and log aggregation (28-day retention)

- **Internal Endpoint:** `http://vlogs-server.monitoring.svc.cluster.local:9428`
- **External VPN Endpoint:** `https://vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com:9428`
- **Port:** 9428
- **Service:** `vlogs-server`
- **Namespace:** `monitoring`
- **Cluster:** `ardenone-cluster`
- **Active Endpoint:** `10.42.6.103:9428`
- **Access:** VPN certificate required (no public access)

**Access Methods:**
```bash
# Port-forward access
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/vlogs-server 9428:9428

# Direct cluster access (requires VPN)
curl -k https://vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com:9428
```

### Prometheus (Real-time Metrics)

**Purpose:** Real-time metrics collection and querying (10-day retention)

- **Internal Endpoint:** `http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090`
- **Port:** 9090
- **Service:** `kube-prometheus-stack-arde-prometheus`
- **Namespace:** `monitoring`
- **Cluster:** `ardenone-cluster`
- **Access:** VPN certificate required (no public access)

**Access Methods:**
```bash
# Port-forward access
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/kube-prometheus-stack-arde-prometheus 9090:9090
```

### Grafana (Visualization Dashboards)

**Purpose:** Metrics visualization and dashboards

- **Public URL:** `https://grafana.ardenone.com`
- **Authentication:** Google SSO
- **Access:** Public via Cloudflare Tunnel

---

## Service-Specific Endpoints

### pbx-web Service

**Namespace:** `pbx-web`  
**Cluster:** `ardenone-cluster`

#### Main Application Container (site-generator)

- **Health Endpoint:** `HTTP /health` on port 9000
- **Metrics Port:** 9000
- **Active Endpoints:** `10.42.6.37:9000`, `10.42.6.37:80`
- **Health Check Configuration:**
  - Liveness probe: `HTTP GET /health:9000`
  - Readiness probe: `HTTP GET /health:9000`
  - Initial delay: 10s (liveness), 5s (readiness)
  - Timeout: 5s (liveness), 5s (readiness)

#### Nginx Container

- **Port:** 80
- **Health Endpoint:** `HTTP /` on port 80
- **Liveness/Readiness:** `HTTP GET /` on port 80

#### Rebuild Relay Services

- **pbx-rebuild-relay:** Port 9001, `/health` endpoint (`10.42.6.38:9001`)
- **lab-rebuild-relay:** Port 9001, `/health` endpoint (`10.42.6.177:9001`)

**Access Methods:**
```bash
# Via kubectl proxy (read-only)
curl http://traefik-ardenone-cluster:8001/api/v1/namespaces/pbx-web/pods

# Port-forward to specific pod
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n pbbx-web pod/pbx-web-<pod-id> 9000:9000

# Health check via port-forward
curl http://localhost:9000/health
```

---

### whisper-stt Service

**Namespace:** `whisper-stt`  
**Cluster:** `ardenone-cluster`

#### Main Application Container (whisper-stt)

- **Health Endpoint:** `HTTP /health` on port 8080
- **Metrics Port:** 8080
- **Active Endpoint:** `10.42.6.3:8080`
- **Health Check Configuration:**
  - Liveness probe: `HTTP GET /health:8080`
  - Readiness probe: `HTTP GET /health:8080`
  - Initial delay: 120s (liveness), 60s (readiness)
  - Timeout: 1s (liveness), 1s (readiness)

#### Alternative Deployment (whisper-openai)

- **Health Endpoint:** `HTTP /health` on port 8000
- **Metrics Port:** 8000
- **Active Endpoint:** `10.42.2.128:8000`
- **Startup probe:** `HTTP GET /health:8000`

**Access Methods:**
```bash
# Via kubectl proxy (read-only)
curl http://traefik-ardenone-cluster:8001/api/v1/namespaces/whisper-stt/pods

# Port-forward to specific pod
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n whisper-stt pod/whisper-stt-<pod-id> 8080:8080

# Health check via port-forward
curl http://localhost:8080/health
```

---

## Authentication & Access Requirements

| Service | Authentication | Access Method |
|---------|---------------|----------------|
| VictoriaLogs | VPN certificate | Port-forward or VPN |
| Prometheus | VPN certificate | Port-forward or VPN |
| Grafana | Google SSO | Public (Cloudflare Tunnel) |
| pbx-web health endpoints | None (after port-forward) | Port-forward only |
| whisper-stt health endpoints | None (after port-forward) | Port-forward only |
| kubectl proxy | None (read-only) | Read-only access |

---

## Key Limitations

1. **No Application `/metrics` Endpoints:** Neither pbx-web nor whisper-stt expose Prometheus `/metrics` endpoints
2. **No ServiceMonitor Resources:** No Prometheus Operator custom resources for scraping
3. **Limited Latency Data:** No application-level timing metrics in logs
4. **Prometheus Retention:** Only 10 days (insufficient for 30-day analysis)
5. **Infrastructure-Only Metrics:** Only Kubernetes infrastructure metrics available
6. **VPN Required:** All direct service-to-service communication requires VPN

---

## Recommended Access Patterns

### For 30-Day Historical Analysis

Use **VictoriaLogs** as the primary data source:
- 28-day retention period
- Suitable for historical deployment analysis
- Access via port-forward or VPN

### For Real-time Health Checks

Use **service-specific health endpoints**:
- pbx-web: `http://<pod-ip>:9000/health`
- whisper-stt: `http://<pod-ip>:8080/health`
- Access via port-forward from aide-de-camp environment

### For Visualization

Use **Grafana dashboards**:
- Public access via `https://grafana.ardenone.com`
- Google SSO authentication
- Pre-configured dashboards for both services

---

## Verification from aide-de-camp Environment

All endpoints were verified accessible from the aide-de-camp environment on 2026-08-07:

✅ VictoriaLogs: `10.42.6.103:9428` - Active  
✅ pbx-web: `10.42.6.37:9000` - Active  
✅ pbx-web nginx: `10.42.6.37:80` - Active  
✅ pbx-rebuild-relay: `10.42.6.38:9001` - Active  
✅ lab-rebuild-relay: `10.42.6.177:9001` - Active  
✅ whisper-stt: `10.42.6.3:8080` - Active  
✅ whisper-openai: `10.42.2.128:8000` - Active  
✅ kubectl proxy: Read-only access verified  

---

## Summary

- **Primary Monitoring Backend:** VictoriaLogs (28-day retention)
- **Real-time Metrics:** Prometheus (10-day retention)
- **Visualization:** Grafana (public access)
- **Service Health Checks:** HTTP `/health` endpoints on service ports
- **Access Method:** Port-forward or VPN for all internal services
- **No Application Metrics:** Services expose only health endpoints, not `/metrics`

For deployment reliability analysis, rely on VictoriaLogs for historical data and service health endpoints for real-time status checks.
