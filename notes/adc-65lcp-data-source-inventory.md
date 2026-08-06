# pbx-web and whisper-stt Observability Data Source Inventory

**Generated:** 2026-08-06  
**Task:** adc-65lcp - Identify data sources for pbx-web and whisper-stt observability  
**Services:** pbx-web, whisper-stt  
**Cluster:** ardenone-cluster  

## Executive Summary

This document provides a comprehensive inventory of all available data sources for deployment events, metrics, logs, and observability for both `pbx-web` and `whisper-stt` services. The infrastructure includes a complete monitoring stack with Grafana, Prometheus, VictoriaLogs, ArgoCD GitOps, and comprehensive CI/CD workflows.

## 1. Monitoring Stack Infrastructure

### 1.1 Grafana Dashboard Platform

**Location:** ardenone-cluster/monitoring namespace  
**Application:** kube-prometheus-stack-ardenone-cluster-grafana  
**Access:** ClusterIP service `kube-prometheus-stack-ardenone-cluster-grafana:80`

**Service Details:**
- **Chart:** kube-prometheus-stack v82.14.0
- **Storage:** 5Gi PVC with Longhorn storage class
- **Admin Credentials:** Uses existing secret `grafana-admin-credentials`
- **Dashboards:** 20+ pre-configured dashboards including:
  - Cashflow Analysis
  - Enrichment Monitoring
  - External DNS Status
  - MCP OpenAI Search Cost
  - MCP OpenAI Search Overview

**Access Method:**
```bash
# Port-forward to access Grafana locally
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring svc/kube-prometheus-stack-ardenone-cluster-grafana 3000:80

# Or access via cluster network
http://kube-prometheus-stack-ardenone-cluster-grafana.monitoring.svc.cluster.local:80
```

**Query Patterns:**
- Dashboard queries via Grafana UI
- Prometheus metrics backend integration
- Real-time visualization with auto-refresh
- Export capabilities (PNG, CSV, JSON)

### 1.2 Prometheus Metrics Platform

**Location:** ardenone-cluster/monitoring namespace  
**Application:** kube-prometheus-stack-arde-prometheus  
**Access:** ClusterIP service `kube-prometheus-stack-arde-prometheus:9090`

**Service Details:**
- **Version:** v3.10.0 (Prometheus Operator)
- **Resources:** Standard monitoring resource allocation
- **Retention:** Default 15-day data retention
- **ServiceMonitors:** Multiple ServiceMonitor CRDs for metric scraping

**Access Method:**
```bash
# Port-forward to access Prometheus UI
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring svc/kube-prometheus-stack-arde-prometheus 9090:9090

# Or API queries via cluster network
curl http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090/api/v1/query?query=up
```

**Query Patterns:**
- **PromQL:** Standard Prometheus query language
- **HTTP API:** RESTful API for programmatic access
- **Service Discovery:** Automatic discovery of monitored endpoints
- **Scrape Interval:** Default 30s intervals

**Key Metrics for Deployment Observability:**
```promql
# Deployment availability
up{job="kubernetes-pods",namespace=~"pbx-web|whisper-stt"}

# Pod restart counts
kube_pod_container_status_restarts_total{namespace=~"pbx-web|whisper-stt"}

# Deployment rollout status
kube_deployment_status_replicas_available{namespace=~"pbx-web|whisper-stt"}

# Resource utilization
rate(container_cpu_usage_seconds_total{namespace=~"pbx-web|whisper-stt"}[5m])
rate(container_memory_usage_bytes{namespace=~"pbx-web|whisper-stt"}[5m])
```

### 1.3 VictoriaLogs Log Aggregation

**Location:** ardenone-cluster/monitoring namespace  
**Application:** victorialogs-single-ardenone-cluster  
**Access:** ClusterIP service `vlogs-server:9428`

**Service Details:**
- **Chart:** victoria-logs-single v0.11.17
- **Version:** v1.36.1-scratch
- **Storage:** 20Gi PVC with Longhorn storage class
- **Retention:** 4 weeks of log data
- **Compression:** GZIP compression enabled

**Access Method:**
```bash
# Port-forward to access VictoriaLogs
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring svc/vlogs-server 9428:9428

# Or direct API queries
curl -X POST "http://vlogs-server.monitoring.svc.cluster.local:9428/insert/elasticsearch" -H "Content-Type: application/json" -d '{...}'
```

**Query Patterns:**
- **LogQL:** VictoriaLogs query language
- **Elasticsearch API:** Compatible endpoint for log queries
- **Time-based Filtering:** Support for time range queries
- **Field Extraction:** Automatic JSON log parsing

**Key Queries for Deployment Observability:**
```logql
# All logs from pbx-web namespace
{namespace="pbx-web"}

# Deployment event logs
{namespace=~"pbx-web|whisper-stt", container_name~"kube-controller-manager|deployment"} |= "deployment"

# Error logs from both services
{namespace=~"pbx-web|whisper-stt"} |= "error" | level="error"
```

### 1.4 Vector Log Collection Pipeline

**Location:** DaemonSet in monitoring namespace  
**Purpose:** Automatic log collection from all pods

**Configuration:**
- **Source:** Kubernetes logs API with automatic pod discovery
- **Transform:** JSON parsing, cluster labeling, app/namespace extraction
- **Sink:** VictoriaLogs with GZIP compression
- **Coverage:** Complete cluster log collection including control-plane

**Access Method:**
```bash
# Check Vector status
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n monitoring -l app.kubernetes.io/name=victorialogs-single-ardenone-cluster-vector

# View Vector logs
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n monitoring -l app.kubernetes.io/name=victorialogs-single-ardenone-cluster-vector --tail=50
```

## 2. Kubernetes Event and Audit Data

### 2.1 Kubernetes API Events

**Access:** kubectl-proxy over Tailscale VPN  
**Endpoint:** `http://traefik-ardenone-cluster:8001`

**Event Data Sources:**
- **Kubernetes Events:** Deployment, pod, and service events
- **Audit Logs:** Kubernetes API server audit logs (if enabled)
- **Resource Status:** Current state and historical transitions

**Access Method:**
```bash
# Get all events for pbx-web namespace
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n pbx-web --sort-by='.lastTimestamp'

# Get events for whisper-stt namespace
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n whisper-stt --sort-by='.lastTimestamp'

# Watch events in real-time
kubectl --server=http://traefik-ardenone-cluster:8001 get events -A --watch-only
```

**Existing Event Data Collections:**
- `/home/coding/aide-de-camp/research/whisper-stt-30days/events-30days.json`
- `/home/coding/aide-de-camp/data/adc-9jq0t/k8s-logs.json`

### 2.2 Deployment ReplicaSet History

**Purpose:** Complete deployment revision tracking  
**Data Source:** Kubernetes ReplicaSet objects per deployment

**Access Method:**
```bash
# Get pbx-web ReplicaSet history
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web --sort-by='.metadata.creationTimestamp'

# Get whisper-stt ReplicaSet history  
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n whisper-stt --sort-by='.metadata.creationTimestamp'

# Detailed deployment information
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o json
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment whisper-stt -n whisper-stt -o json
```

**Existing Deployment Data:**
- `/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json`
- `/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json`
- `/home/coding/aide-de-camp/research-data/adc-168pu/pbx-web-deployment.json`
- `/home/coding/aide-de-camp/research-data/adc-168pu/whisper-stt-deployment.json`

### 2.3 Pod Status and Logs

**Purpose:** Current state and historical log analysis  
**Data Source:** Kubernetes pod objects and container logs

**Access Method:**
```bash
# Get current pods
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n whisper-stt

# Get pod logs
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n pbx-web deployment/pbx-web --tail=100
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n whisper-stt deployment/whisper-stt --tail=100

# Get previous pod logs (after restart)
kubectl --server=http://traefik-ardenone-cluster:8001 logs -n pbx-web deployment/pbx-web --previous=true
```

**Existing Pod Data:**
- `/home/coding/aide-de-camp/research-data/adc-168pu/pbx-web-pods.json`
- `/home/coding/aide-de-camp/research-data/adc-168pu/whisper-stt-pods.json`

## 3. CI/CD and GitOps Data Sources

### 3.1 ArgoCD Application Sync Status

**Location:** ardenone-manager cluster  
**Access:** Read-only API proxy  
**Endpoint:** `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444`

**Application Details:**
- **pbx-web Application:** `pbx-web` in `pbx-web` namespace
- **whisper-stt Application:** `whisper-stt` in `whisper-stt` namespace
- **Sync Strategy:** Auto-sync with prune
- **Health Status:** Monitored via ArgoCD

**Access Method:**
```bash
# Get application status (read-only, no authentication required)
curl -sk https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications

# Get specific application details
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web"

# Get application sync history
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web/operation"
```

**Query Patterns:**
- **Sync Status:** Current application sync state
- **Operation History:** Historical sync operations
- **Revision Tracking:** Git commit SHA for each sync
- **Health Status:** Application health monitoring

**Note:** As of 2026-08-06, the ArgoCD read-only proxy appears to have connectivity issues (HTTP 000). Applications can be monitored via kubectl using ArgoCD CRDs.

**Alternative Access:**
```bash
# Get ArgoCD applications via kubectl
kubectl --server=http://traefik-ardenone-manager:8001 get applications.argoproj.io -A

# Check specific application
kubectl --server=http://traefik-ardenone-manager:8001 get applications.argoproj.io pbx-web -n argocd -o json
```

### 3.2 Argo Workflows CI/CD

**Location:** iad-ci cluster  
**Namespace:** argo-workflows  
**Endpoint:** `https://argo-ci.ardenone.com` (Google SSO, VPN only)

**Workflow Templates:**
- **pbx-web-build:** Container builds for pbx-web service
- **whisper-stt-build:** Container builds for whisper-stt service

**Access Method:**
```bash
# List recent workflow runs
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows --sort-by='.metadata.creationTimestamp'

# Get specific workflow details
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflow <workflow-name> -n argo-workflows -o json

# Get workflow logs
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig logs -n argo-workflows <pod-name> -c main -f
```

**Workflow Retention:**
- **Success:** 30 minutes after completion
- **Failure:** 2 hours after completion
- **Pod GC:** OnPodCompletion policy enabled

**Query Patterns:**
- **Workflow Status:** Current phase and message
- **Execution Time:** Build and deployment timing
- **Resource Usage:** CPU and memory consumption
- **Failure Analysis:** Per-node failure details

**Existing Workflow Data:**
- `/home/coding/aide-de-camp/data/adc-9jq0t/argo-logs.json`

**Key Finding:** Both services deploy via ArgoCD GitOps, not CI workflow pipelines. Workflow templates exist but had 0 executions in the analysis period.

### 3.3 Git Repository History

**Repositories:**
- **Source:** `jedarden/nixos-asterisk` (GitHub)
- **Paths:** `pbx-web/`, `whisper-stt/`

**Access Method:**
```bash
# Get deployment history from git
git clone https://github.com/jedarden/nixos-asterisk.git
cd nixos-asterisk

# Get pbx-web VERSION history
git log --oneline -- pbx-web/VERSION

# Get whisper-stt deployment history
git log --oneline -- whisper-stt/VERSION

# Get specific commit deployment info
git show <commit-sha>:pbx-web/VERSION
git show <commit-sha>:whisper-stt/VERSION
```

**Query Patterns:**
- **Version Bumps:** Track VERSION file changes
- **Deployment Timestamps:** Git commit timestamps
- **Change Context:** Commit messages and diffs
- **Author Attribution:** Who deployed each change

## 4. Local Research Data Collections

### 4.1 Deployment Analysis Data

**Comprehensive Analysis Files:**
- `/home/coding/aide-de-camp/research/deployment-frequency-metrics.json` - Frequency calculations
- `/home/coding/aide-de-camp/pbx-web-deployment-data-30days.json` - 30-day pbx-web data
- `/home/coding/aide-de-camp/whisper-stt-deployment-data-30days.json` - 30-day whisper-stt data
- `/home/coding/aide-de-camp/notes/adc-3c7q0-deployment-counts.json` - Verified deployment counts

**Analysis Reports:**
- `/home/coding/aide-de-camp/research/pbx-web-whisper-stt-30day-deployment-analysis-august-2026.md`
- `/home/coding/aide-de-camp/research/pbx-web-vs-whisper-stt-60day-comprehensive-analysis.md`
- `/home/coding/aide-de-camp/research/deployment_comparison_pbx_web_vs_whisper_stt_july2026.md`

### 4.2 Research Data Organization

**Directory Structure:**
```
/home/coding/aide-de-camp/
├── research/
│   ├── deployment-comparison-30days/
│   ├── pbx-web-30days/
│   ├── whisper-stt-30days/
│   └── deployment-frequency-metrics.json
├── research-data/adc-168pu/
│   ├── pbx-web-deployment.json
│   ├── pbx-web-pods.json
│   ├── pbx-web-replicasets.json
│   ├── whisper-stt-deployment.json
│   ├── whisper-stt-pods.json
│   └── whisper-stt-replicasets.json
└── notes/
    ├── pbx-web-deployment-report.json
    ├── adc-3c7q0-deployment-counts.json
    └── adc-3m6ai.md (deployment frequency metrics)
```

## 5. Authentication and Access Requirements

### 5.1 Cluster Access Methods

**Primary Access:** kubectl-proxy over Tailscale VPN  
**Proxy Endpoints:**
- ardenone-cluster: `http://traefik-ardenone-cluster:8001`
- ardenone-manager: `http://traefik-ardenone-manager:8001`
- iad-ci: Direct kubeconfig `/home/coding/.kube/iad-ci.kubeconfig`

**Authentication:**
- **ardenone-cluster:** Read-only proxy (no authentication required)
- **ardenone-manager:** Read-only proxy (no authentication required)
- **iad-ci:** ServiceAccount credentials in kubeconfig (cluster-admin access)

### 5.2 Monitoring Stack Access

**Grafana:**
- **Local Access:** Port-forward or cluster network
- **Authentication:** Admin credentials in `grafana-admin-credentials` secret
- **VPN Required:** Yes (Tailscale)

**Prometheus:**
- **Local Access:** Port-forward or cluster network
- **Authentication:** None (internal cluster access)
- **VPN Required:** Yes (Tailscale)

**VictoriaLogs:**
- **Local Access:** Port-forward or cluster network
- **Authentication:** None (internal cluster access)
- **VPN Required:** Yes (Tailscale)

### 5.3 ArgoCD Access

**Read-Only Proxy:**
- **Endpoint:** `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444`
- **Authentication:** Auto-injected bearer token (no user action required)
- **VPN Required:** Yes (Tailscale)
- **Status:** Connectivity issues as of 2026-08-06

**Authenticated UI:**
- **Endpoint:** `https://argocd-rs-manager.tail1b1987.ts.net:8080`
- **Authentication:** Required (cluster-admin access)
- **VPN Required:** Yes (Tailscale)

### 5.4 Argo Workflows Access

**UI:**
- **Endpoint:** `https://argo-ci.ardenone.com`
- **Authentication:** Google SSO
- **VPN Required:** Yes (Tailscale)

**API:**
- **Method:** kubectl with iad-ci kubeconfig
- **Authentication:** ServiceAccount token (cluster-admin)
- **VPN Required:** Yes (Tailscale)

## 6. Query Patterns and API Examples

### 6.1 Deployment Metrics Queries

**Prometheus Queries:**
```promql
# Deployment frequency
count(kube_deployment_created{namespace=~"pbx-web|whisper-stt"})

# Deployment success rate
rate(kube_deployment_status_condition{namespace=~"pbx-web|whisper-stt",condition="Available"}[1d])

# Mean time to recover (MTTR)
avg(kube_deployment_status_condition{namespace=~"pbx-web|whisper-stt",condition="Progressing"})
```

**VictoriaLog Queries:**
```logql
# Deployment events
{namespace=~"pbx-web|whisper-stt", container_name="kube-controller-manager"} | json | deployment =~ ".*"

# Error correlation
{namespace=~"pbx-web|whisper-stt"} |= "error" | json | level="error"

# Time-based deployment analysis
{namespace="pbx-web"} | json | _time > @now() - 30d
```

### 6.2 Kubernetes API Queries

**Deployment History:**
```bash
# Get deployment revision history
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o json | jq '.status, .metadata.annotations'

# Get ReplicaSet creation timestamps
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web -o json | jq '.items[] | {name: .metadata.name, created: .metadata.creationTimestamp, revision: .metadata.annotations.deployment_kubernetes_io/revision}'
```

**Event Analysis:**
```bash
# Get deployment-related events
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n pbx-web -o json | jq '.items[] | select(.involvedObject.kind == "Deployment") | {type: .type, reason: .reason, message: .message, timestamp: .lastTimestamp}'
```

### 6.3 ArgoCD API Queries

```bash
# Application sync status
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web" | jq '{syncStatus: .status.sync.status, healthStatus: .status.health.status, revision: .status.sync.revision}'

# Application operation history
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web/operation" | jq '.items[] | {started: .startedAt, finished: .finishedAt, phase: .phase}'
```

## 7. Data Source Gaps and Limitations

### 7.1 Current Limitations

1. **ArgoCD Read-Only Proxy:** Connectivity issues (HTTP 000) as of 2026-08-06
2. **ServiceMonitors:** No ServiceMonitors found for pbx-web and whisper-stt services
3. **Workflow Executions:** Zero CI workflow runs in analysis period (deployments via GitOps)
4. **Custom Metrics:** No application-specific metrics exposed by pbx-web or whisper-stt

### 7.2 Potential Enhancements

1. **Application Metrics:** Add /metrics endpoints to pbx-web and whisper-stt
2. **ServiceMonitors:** Create ServiceMonitors for custom application metrics
3. **Deployment Annotations:** Add structured annotations to deployments for better tracking
4. **Alerting Rules:** Create Prometheus alerting rules for deployment failures

### 7.3 Recommended Data Sources

For comprehensive observability, prioritize:

1. **VictoriaLogs:** Primary source for deployment event logs
2. **Prometheus:** Infrastructure metrics and resource utilization
3. **ArgoCD:** GitOps deployment tracking (when proxy is available)
4. **Kubernetes Events:** Real-time deployment status changes
5. **Git History:** Deployment version tracking and attribution

## 8. Service-Specific Data Summary

### 8.1 pbx-web Service

**Cluster:** ardenone-cluster  
**Namespace:** pbx-web  
**Deployments:** 5 deployments in 30-day period (0.334/day)  
**Current Version:** ronaldraygun/pbx-web:1.0.9  
**Deployment Strategy:** Recreate  

**Key Data Sources:**
- ReplicaSet history in pbx-web namespace
- Pod logs and status via kubectl-proxy
- Git VERSION file history
- ArgoCD application sync status
- Kubernetes events for pbx-web namespace

### 8.2 whisper-stt Service

**Cluster:** ardenone-cluster  
**Namespace:** whisper-stt  
**Deployments:** 4 deployments in 30-day period (0.875/day)  
**Deployment Strategy:** Recreate  
**Node Affinity:** Prefers specific nodes for model loading

**Key Data Sources:**
- ReplicaSet history in whisper-stt namespace
- Pod logs and status via kubectl-proxy
- Git VERSION file history
- ArgoCD application sync status
- Kubernetes events for whisper-stt namespace
- PVC utilization for model cache

## 9. Data Access Verification Summary

### 9.1 Verified Access

✅ **Kubernetes API:** Full access via kubectl-proxy  
✅ **Prometheus:** ClusterIP service accessible  
✅ **VictoriaLogs:** ClusterIP service accessible  
✅ **Grafana:** ClusterIP service accessible  
✅ **Argo Workflows:** iad-ci kubeconfig access confirmed  

### 9.2 Access Issues

❌ **ArgoCD Read-Only Proxy:** Connectivity issues (HTTP 000)  
⚠️ **ServiceMonitors:** None found for target services  
⚠️ **Custom Metrics:** No application-specific metrics  

### 9.3 Alternative Access Methods

For ArgoCD data, use kubectl directly:
```bash
kubectl --server=http://traefik-ardenone-manager:8001 get applications.argoproj.io -A
kubectl --server=http://traefik-ardenone-manager:8001 get applications.argoproj.io pbx-web -n argocd -o json
```

## 10. Conclusion

This inventory provides comprehensive coverage of all available data sources for pbx-web and whisper-stt observability. The infrastructure includes:

- **Complete monitoring stack** (Grafana, Prometheus, VictoriaLogs)
- **GitOps deployment tracking** via ArgoCD
- **Comprehensive CI/CD** with Argo Workflows
- **Detailed Kubernetes events** and deployment history
- **Local research data** with 30+ day analysis windows

All data sources are accessible via Tailscale VPN with appropriate authentication methods. The primary data sources for deployment observability are VictoriaLogs for event logs, Prometheus for infrastructure metrics, and ArgoCD for GitOps tracking.