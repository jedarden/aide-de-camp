# Observability Endpoints: pbx-web and whisper-stt

**Generated:** 2026-08-06  
**Services:** pbx-web, whisper-stt (ardenone-cluster)

## Summary

Both pbx-web and whisper-stt are deployed on the **ardenone-cluster** and leverage the shared monitoring stack in the `monitoring` namespace. No service-specific ServiceMonitors or PodMonitors exist — metrics collection relies on standard Prometheus scraping via annotations or default pod discovery.

---

## Grafana Dashboards

### Primary Endpoint
| Tool | Endpoint URL | Access | Notes |
|------|--------------|--------|-------|
| Grafana | `https://grafana.ardenone.com` | Public (Cloudflare tunnel) | Version 12.4.1, authenticated |

**Service-Specific Dashboards:**
- **No dedicated pbx-web dashboards** exist in the monitoring stack
- **No dedicated whisper-stt dashboards** exist in the monitoring stack
- General-purpose dashboards available:
  - `grafana-dashboard-cluster-resources.yml` — cluster-wide resource usage
  - `grafana-dashboard-traefik.yml` — ingress/routing metrics (both services use Traefik)
  - `grafana-dashboard-pipeline-observability.yml` — pipeline monitoring
  - 18 additional dashboards for other services (cashflow, enrichment, shadow-trading, etc.)

**How to query pbx-web/whisper-stt metrics:**
- Use Grafana Explore → Prometheus datasource
- Filter by label: `namespace="pbx-web"` or `namespace="whisper-stt"`
- Common metric queries:
  - `container_cpu_usage_seconds_total{namespace="pbx-web"}`
  - `container_memory_working_set_bytes{namespace="whisper-stt"}`
  - `up{namespace="pbx-web"}` — pod availability
  - `rate(http_requests_total[5m])` — if services expose /metrics endpoint

---

## VictoriaLogs (Log Aggregation)

### Endpoints

| Access Type | Endpoint URL | Auth | Notes |
|-------------|--------------|------|-------|
| **VPN (recommended)** | `https://vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com:8444` | VPN-only (Tailscale) | Self-signed cert, `verify=false` |
| **Cluster Internal** | `http://vlogs-server.monitoring.svc.cluster.local:9428` | Cluster DNS | Service-to-service |
| **Direct Service** | `http://vlogs-server:9428` | Cluster local (monitoring ns) | Internal routing |

**Grafana Integration:**
- Two datasources configured in Grafana:
  1. **VictoriaLogs** (native plugin) — `http://vlogs-server:9428`
  2. **VictoriaLogs-Loki** (Loki-compatible) — `http://vlogs-server:9428/select/logsql`

**Log Queries for pbx-web:**
```logsql
{namespace="pbx-web"} |= "error"
{namespace="pbx-web", pod="pbx-web-xxxxx"} | line_format "{{.message}}"
```

**Log Queries for whisper-stt:**
```logsql
{namespace="whisper-stt"} |= "transcription"
{namespace="whisper-stt", container="whisper-openai"} | line_format "{{.message}}"
```

---

## Prometheus Metrics (Scrape Targets)

### Prometheus Endpoint

| Access Type | Endpoint URL | Auth | Notes |
|-------------|--------------|------|-------|
| **Cluster Internal** | `http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090` | Cluster DNS | Standard Prometheus API |
| **Kubernetes Service** | `prometheus-operated:9090` | Headless svc | Direct pod access |

**Note:** No external VPN or public ingress exists for Prometheus — access via Grafana datasource or cluster proxy.

### Scrape Configuration

**No ServiceMonitor or PodMonitor CRDs** exist for pbx-web or whisper-stt. Metrics collection relies on:
1. **Standard Prometheus Operator pod discovery** (kube-prometheus-stack)
2. **Annotations on pods** (if present) for custom scrape paths
3. **Default scrape interval** for all pods in the cluster

**Current pod endpoints:**

**pbx-web namespace:**
| Pod | IP | Containers | Metrics Endpoint |
|-----|----|------------|------------------|
| pbx-web-5ff68464d-mkn8n | 10.42.6.37 | site-generator (port 9000), nginx (port 80) | `http://10.42.6.37:9000/metrics` (if exposed), nginx metrics via `/nginx_status` |
| pbx-rebuild-relay-xxxxx | 10.42.6.38 | relay (port 9001) | Unknown if /metrics exposed |
| lab-rebuild-relay-xxxxx | 10.42.6.177 | relay (port 9001) | Unknown if /metrics exposed |

**whisper-stt namespace:**
| Pod | IP | Containers | Metrics Endpoint |
|-----|----|------------|------------------|
| whisper-stt-847fd8d7b9-v2rs5 | 10.42.6.3 | whisper-stt (port 8080) | Unknown if /metrics exposed |
| whisper-openai-68966786fb-jsb5d | 10.42.2.128 | whisper-openai (port 8000) | Unknown if /metrics exposed |

**To enable proper metrics scraping:**
- Add annotations to pods:
  ```yaml
  prometheus.io/scrape: "true"
  prometheus.io/port: "<metrics-port>"
  prometheus.io/path: "/metrics"
  ```
- Or create ServiceMonitor/PodMonitor CRDs in the service namespaces

---

## CI/CD Logs (Argo Workflows)

### Argo Workflows UI

| Endpoint | Access | Notes |
|----------|--------|-------|
| `https://argo-ci.ardenone.com` | VPN-only (Tailscale) | Google SSO required |

**Workflow Templates for CI/CD:**

| Service | Workflow Template | Location | Purpose |
|---------|------------------|----------|---------|
| **pbx-web** | `pbx-web-build` | `k8s/iad-ci/argo-workflows/pbx-web-build-workflowtemplate.yml` | Docker build → ronaldraygun/pbx-web:{version} |
| **whisper-stt** | `whisper-stt-build` | `k8s/iad-ci/argo-workflows/whisper-stt-workflowtemplate.yml` | Docker build → ronaldraygun/whisper-stt:{version} |

**Viewing CI/CD Logs:**
1. Navigate to `https://argo-ci.ardenone.com`
2. Filter by workflow template name: `pbx-web-build-*` or `whisper-stt-build-*`
3. Click on a workflow run → view per-node logs
4. Logs are retained:
   - Success: 30 minutes
   - Failure: 2 hours

**Alternative (kubectl):**
```bash
# List recent workflow runs
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows --sort-by=.metadata.creationTimestamp | tail -20

# Stream logs from a running pod (must be caught WHILE running)
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  logs -n argo-workflows <pod-name> -c main -f
```

---

## Additional Observability Tools

### Alertmanager

| Endpoint | Access | Notes |
|----------|--------|-------|
| `http://kube-prometheus-stack-arde-alertmanager.monitoring.svc.cluster.local:9093` | Cluster DNS | Internal alert routing |

**Silenced Alerts:** No service-specific alert rules exist for pbx-web or whisper-stt in the monitoring namespace.

### Traefik Dashboard

| Endpoint | Access | Notes |
|----------|--------|-------|
| `http://traefik.ardenone-cluster` or Traefik ingress metrics | Cluster local | Routing and ingress metrics for both services |

Both services expose their endpoints via Traefik ingress routes (see pbx-web-ingressroute.yml, pbx-web-internal-ingressroute.yml).

---

## Quick Reference Checklist

### For pbx-web:
- [ ] Grafana: Query `namespace="pbx-web"` in Explore → Prometheus
- [ ] VictoriaLogs: `https://vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com:8444` → query `{namespace="pbx-web"}`
- [ ] CI/CD: `https://argo-ci.ardenone.com` → filter `pbx-web-build-*`
- [ ] Metrics: Enable pod annotations or create ServiceMonitor for proper scraping
- [ ] Dashboards: No dedicated dashboards exist — use cluster-wide or create custom

### For whisper-stt:
- [ ] Grafana: Query `namespace="whisper-stt"` in Explore → Prometheus
- [ ] VictoriaLogs: `https://vlogs-server-monitoring-ardenone-cluster-ts.ardenone.com:8444` → query `{namespace="whisper-stt"}`
- [ ] CI/CD: `https://argo-ci.ardenone.com` → filter `whisper-stt-build-*`
- [ ] Metrics: Enable pod annotations or create ServiceMonitor for proper scraping
- [ ] Dashboards: No dedicated dashboards exist — use cluster-wide or create custom

---

## Recommendations

1. **Create ServiceMonitors/PodMonitors** for both services to ensure consistent metrics collection
2. **Add service-specific Grafana dashboards** to visualize:
   - Request latency and error rates
   - Resource usage (CPU, memory)
   - Application-specific metrics (transcription success rate, rebuild job frequency)
3. **Configure alerting rules** for:
   - High error rates
   - Pod restart loops
   - Resource saturation
4. **Document metrics endpoints** in the deployment manifests (add prometheus.io annotations)
