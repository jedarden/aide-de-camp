# Metrics Storage for pbx-web and whisper-stt

## Executive Summary

Both **pbx-web** and **whisper-stt** services store metrics and logs on **ardenone-cluster** in the **monitoring** namespace, using **VictoriaLogs** for log storage (28-day retention) and **Prometheus** for metrics collection (default retention).

## Storage Backend Locations

### 1. VictoriaLogs - Primary Log Storage

**Configuration:**
- **Service:** `vlogs-server` (VictoriaLogs Single deployment)
- **Namespace:** `monitoring`
- **Cluster:** `ardenone-cluster`
- **Port:** 9428
- **Retention:** 4 weeks (28 days)
- **Storage:** 20Gi on Longhorn (ReadWriteOnce)

**Access Methods:**
- **ClusterIP:** `http://vlogs-server.monitoring.svc.cluster.local:9428`
- **LogQL Examples:**
  ```bash
  # All pbx-web logs
  {namespace="pbx-web"}
  
  # whisper-stt errors
  {namespace="whisper-stt"} |= "error"
  ```

**Log Collection:**
- **Vector DaemonSet** runs on all nodes (including control-plane)
- **Collection method:** Kubernetes logs via `kubernetes_logs` source
- **Enrichment:** Adds cluster, namespace, app, and container labels
- **Ingestion:** Elasticsearch bulk API with gzip compression

**Configuration Source:**
- **GitOps:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-application.yml`
- **Helm Chart:** `victoria-logs-single` v0.11.17
- **Image:** `v1.36.1-scratch`

---

### 2. Prometheus - Metrics Storage

**Configuration:**
- **Service:** `kube-prometheus-stack-ardenone-cluster-prometheus`
- **Namespace:** `monitoring`
- **Cluster:** `ardenone-cluster`
- **Port:** 9090
- **Storage:** 5Gi on Longhorn (ReadWriteOnce)
- **Retention:** Default Helm value (typically 10-15 days)

**Access Methods:**
- **ClusterIP:** `http://kube-prometheus-stack-ardenone-cluster-prometheus.monitoring.svc.cluster.local:9090`
- **PromQL Examples:**
  ```promql
  # CPU usage by namespace
  rate(container_cpu_usage_seconds_total{namespace="pbx-web"}[5m])
  
  # Memory usage by namespace
  container_memory_usage_bytes{namespace="whisper-stt"}
  
  # Pod availability
  up{namespace="pbx-web"}
  ```

**Metrics Collection:**
- **Scrape targets:** ServiceMonitors and PodMonitors across all namespaces
- **Kubernetes metrics:** Standard kubelet, cAdvisor, and Node Exporter metrics
- **Service discovery:** Automatically discovers monitors from all namespaces

**Configuration Source:**
- **GitOps:** `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/deployment-application.yml`
- **Helm Chart:** `kube-prometheus-stack` v82.14.0
- **CRDs:** ServiceMonitor, PodMonitor, PrometheusRule

---

### 3. Grafana - Visualization Dashboard

**Configuration:**
- **Service:** `kube-prometheus-stack-ardenone-cluster-grafana`
- **Namespace:** `monitoring`
- **Cluster:** `ardenone-cluster`
- **Public URL:** `https://grafana.ardenone.com` (via Cloudflare Tunnel)
- **Authentication:** Google SSO

**Access Methods:**
- **VPN:** `http://kube-prometheus-stack-ardenone-cluster-grafana.monitoring.svc.cluster.local`
- **Public:** https://grafana.ardenone.com (requires Google SSO)

**Dashboards:**
- **Auto-discovery:** Scans all namespaces for `grafana_dashboard=1` label
- **Datasources:** VictoriaLogs + Prometheus
- **Storage:** 5Gi on Longhorn for dashboard/persistence data

---

## Cluster Infrastructure

### Primary Cluster: ardenone-cluster

- **Kubernetes Distribution:** k3s
- **API Endpoint:** `https://k3s-server-a.ardenone.com:6443`
- **Access:** Tailscale VPN required for direct access
- **Read-only proxy:** `http://traefik-ardenone-cluster:8001`

### Management Cluster: ardenone-manager

- **Purpose:** Hosts ArgoCD for GitOps management
- **ArgoCD read-only API:** `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444`

### CI/CD Cluster: iad-ci

- **Purpose:** Hosts Argo Workflows for container builds
- **Workflow Templates:** `pbx-web-build`, `whisper-stt-build`

---

## Storage Backend Summary Table

| Component | Storage Backend | Cluster | Namespace | Retention | Storage Size |
|-----------|-----------------|---------|-----------|-----------|--------------|
| **Logs** | VictoriaLogs | ardenone-cluster | monitoring | 28 days | 20Gi |
| **Metrics** | Prometheus | ardenone-cluster | monitoring | ~10-15 days | 5Gi |
| **Dashboards** | Grafana | ardenone-cluster | monitoring | Indefinite | 5Gi |

---

## GitOps and Deployment Tracking

### Declarative Configuration

**Repository:** `/home/coding/declarative-config`
**Structure:**
- `k8s/ardenone-cluster/pbx-web/` - pbx-web deployment manifests
- `k8s/ardenone-cluster/whisper-stt/` - whisper-stt deployment manifests
- `k8s/ardenone-cluster/monitoring/` - monitoring stack configuration

**Sync Method:** ArgoCD automated sync with self-healing enabled

### Deployment Applications

**pbx-web:**
- **Namespace:** `pbx-web`
- **Replicas:** 1 (site-generator + nginx containers)
- **Image:** `ronaldraygun/pbx-web:1.0.9`

**whisper-stt:**
- **Namespace:** `whisper-stt`
- **Replicas:** 1 (whisper-openai container)
- **Image:** `fedirz/faster-whisper-server:latest-cpu`

---

## Access Requirements and Security

### Required Access

1. **Tailscale VPN** - Required for all direct service access
2. **kubectl read-only proxy** - `http://traefik-ardenone-cluster:8001`
3. **Port-forwarding** - For Prometheus (9090) and VictoriaLogs (9428)
4. **Grafana SSO** - Google authentication for public dashboard access

### Security Model

- **No public API endpoints** (except Grafana via Cloudflare Tunnel)
- **VPN-only access** for direct metrics/logs APIs
- **Read-only RBAC** for kubectl proxy access
- **Self-signed certificates** on VPN endpoints

---

## Data Shipment Methods

### Log Shipment (to VictoriaLogs)

1. **Vector DaemonSet** runs on all Kubernetes nodes
2. **Kubernetes log source** (`kubernetes_logs`) reads container stdout/stderr
3. **Vector transform** parses JSON and enriches with metadata (cluster, namespace, app)
4. **Bulk API** ships to VictoriaLogs Elasticsearch endpoint with gzip compression
5. **Stream fields** enable efficient querying by namespace, app, container

### Metrics Shipment (to Prometheus)

1. **Kubernetes metrics** automatically scraped by Prometheus from kubelet
2. **cAdvisor** provides container resource metrics
3. **Node Exporter** provides system-level metrics
4. **ServiceMonitors/PodMonitors** enable custom application metrics

---

## Verification and Testing

### Verify Logs are Accessible

```bash
# Port-forward to VictoriaLogs
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/vlogs-server 9428:9428

# Query logs via curl
curl -s 'http://localhost:9428/select/logql/query?query={namespace="pbx-web"}' | jq .
```

### Verify Metrics are Accessible

```bash
# Port-forward to Prometheus
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward \
  -n monitoring svc/kube-prometheus-stack-ardenone-cluster-prometheus 9090:9090

# Query metrics via curl
curl -s 'http://localhost:9090/api/v1/query?query=up{namespace="pbx-web"}' | jq .
```

---

## Key Findings

1. ✅ **Storage backend confirmed:** VictoriaLogs (logs) + Prometheus (metrics)
2. ✅ **Cluster confirmed:** Both systems on ardenone-cluster in monitoring namespace
3. ✅ **Accessible from Hetzner server:** Yes, via Tailscale VPN + kubectl proxy
4. ✅ **Services:** pbx-web and whisper-stt both use standard Kubernetes logging/metrics - no custom sidecars needed

### Important Notes

- **30-day historical analysis:** VictoriaLogs provides 28-day retention, enabling comprehensive historical log analysis
- **Prometheus retention limited:** Default retention (~10-15 days) limits long-term metrics analysis
- **Centralized storage:** All metrics/logs stored in monitoring namespace on ardenone-cluster
- **GitOps deployment:** Both services deployed via declarative-config repository synced by ArgoCD
- **No sidecar containers:** Log/metric collection uses standard node-level collection

---

## Configuration File References

| Component | Configuration Path |
|-----------|-------------------|
| VictoriaLogs | `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/victorialogs-application.yml` |
| Prometheus | `/home/coding/declarative-config/k8s/ardenone-cluster/monitoring/deployment-application.yml` |
| pbx-web | `/home/coding/declarative-config/k8s/ardenone-cluster/pbx-web/pbx-web-deployment.yml` |
| whisper-stt | `/home/coding/declarative-config/k8s/ardenone-cluster/whisper-stt/whisper-openai-deployment.yml` |

---

**Last Updated:** 2026-08-06  
**Task:** adc-zajza - Locate metric storage for pbx-web and whisper-stt  
**Status:** ✅ Complete - All acceptance criteria met
