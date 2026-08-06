# pbx-web Deployment Logs & Events (30 Days)

**Collection Date:** 2026-08-06  
**Analysis Period:** 2026-07-07 to 2026-08-06 (30 days)  
**Cluster:** ardenone-cluster  
**Namespace:** pbx-web

## Overview

This directory contains deployment logs, events, and runtime data for the pbx-web service collected over a 30-day period. The data sources include Kubernetes deployment history, Argo Workflows CI/CD logs, pod runtime logs, and infrastructure events.

## Directory Structure

```
research/pbx-web-30days/
├── README.md                      # This file
├── argo-runs/                     # CI/CD workflow executions
│   ├── workflows.jsonl            # Workflow run records (JSON Lines)
│   └── README.md                  # Argo data documentation
├── k8s-events/                    # Kubernetes events and deployment history
│   ├── deployment.yaml            # Current deployment specification
│   ├── deployment-describe.txt   # Detailed deployment information
│   ├── deployment.json            # Deployment metadata (JSON)
│   ├── replicasets.jsonl         # ReplicaSet history (JSON Lines)
│   ├── events.jsonl               # Kubernetes events (JSON Lines)
│   └── pbx-web-*.json            # Additional deployment-related data
├── pod-logs/                      # Container runtime logs
│   ├── pbx-web-current-*.log      # Current pod logs (nginx + site-generator)
│   └── pod-*.log                  # Historical pod logs
└── queries/                       # Data collection scripts
    └── get-pbx-web-workflows-30days.sh
```

## Data Sources

### 1. Kubernetes Cluster (ardenone-cluster)

**Access Method:** kubectl-proxy over Tailscale  
**Endpoint:** `http://traefik-ardenone-cluster:8001`  
**Namespace:** `pbx-web`  
**Access Level:** Read-only

### 2. Argo Workflows (iad-ci)

**Access Method:** Direct kubeconfig  
**Kubeconfig:** `/home/coding/.kube/iad-ci.kubeconfig`  
**Namespace:** `argo-workflows`  
**Workflow Template:** `pbx-web-build`

### 3. Current Deployment State

**Deployment:** `pbx-web`  
**Current ReplicaSet:** `pbx-web-5ff68464d`  
**Current Pod:** `pbx-web-5ff68464d-mkn8n`  
**Pod Age:** 9 days (created 2026-07-28)  
**Containers:**
- `site-generator`: `ronaldraygun/pbx-web:1.0.9`
- `nginx`: `localhost:7439/nginx:alpine`

## Collection Results

### Argo Workflows (CI/CD)

**Finding:** No pbx-web-build workflow executions found in the last 30 days.

- **Total workflows in namespace:** 16
- **pbx-web related:** 0
- **Workflow template status:** Template exists but unused in analysis period

### Kubernetes Deployment History

**ReplicaSets (Last 30 days):**
- `pbx-web-765bb76db8` - Created 2026-07-28 (rolled over)
- `pbx-web-5ff68464d` - Created 2026-07-13 (current, running 9 days)
- `pbx-web-754f4cfdf7` - Created 2026-07-13 (rolled over)

**Deployment Activity:**
- Most recent deployment: 2026-07-28 (9 days ago)
- Current image: `ronaldraygun/pbx-web:1.0.9`
- No deployment failures detected
- No error events in namespace

### Pod Runtime Logs

**Current Pod Logs Coverage:**
- **Site generator logs:** 2,761 lines
  - Time range: 2026-07-28 to 2026-08-06
  - Content: Pagefind search indexing, bucket change detection, site rebuilds
  - Growth: 175 → 197 pages indexed
  - Performance: ~1.5-2 seconds per index rebuild

- **Nginx logs:** 33,137 lines
  - Time range: 2026-08-03 to 2026-08-06 (3 days)
  - Content: Access logs from health checks and web traffic
  - Status codes: All successful (no 5xx errors detected)
  - Traffic patterns: Primarily kube-probe health checks

### Infrastructure Events

**Events in pbx-web namespace:** No warning or error events detected in the 30-day period.

**Pod Status:**
- All pods running normally
- No OOM kills detected
- No crash loop backoffs
- No image pull errors

## Key Findings

1. **Deployment Stability:** The current deployment has been stable for 9 days with no rollbacks or failures.

2. **CI/CD Activity:** No Argo workflow executions for pbx-web-build in the 30-day period, suggesting deployments may be manual or using a different pipeline.

3. **Service Health:** No error events, crashes, or resource issues detected in Kubernetes events.

4. **Performance:** Pagefind indexing shows consistent performance (~1.5-2 seconds) with gradual content growth (175→197 pages).

5. **Traffic Pattern:** Predominantly health check traffic from kube-probe, no significant user traffic patterns observed.

## Data Quality Notes

- **Pod log retention:** Current pod logs only cover 9 days (since last pod restart on 2026-07-28)
- **Event retention:** Kubernetes events show no errors, but may have been pruned by the cluster
- **Workflow retention:** No workflows found - either not executed or deleted after completion per TTL policy

## Related Services

The pbx-web namespace also contains:
- `pbx-rebuild-relay` - Deployment with 1 running pod (22 days old)
- `lab-rebuild-relay` - Deployment with 1 running pod (9 days old)

These services are not the primary focus of this collection but are present in the same namespace.

## Commands Used for Data Collection

```bash
# Argo Workflows
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows -o json

# Kubernetes Events
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n pbx-web -o json
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web -o json
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o yaml

# Pod Logs
kubectl --server=http://traefik-ardenone-cluster:8001 logs pbx-web-5ff68464d-mkn8n -n pbx-web -c site-generator --timestamps=true
kubectl --server=http://traefik-ardenone-cluster:8001 logs pbx-web-5ff68464d-mkn8n -n pbx-web -c nginx --timestamps=true
```

## Analysis Notes

This data collection provides a comprehensive view of pbx-web deployment stability and runtime behavior over the 30-day period. The absence of CI/CD workflow executions suggests the deployment process may need investigation, but the operational stability indicates the current deployment is functioning correctly.

**Generated by:** aide-de-camp (ADC-1FFMB task)  
**Data freshness:** 2026-08-06 13:47 UTC
