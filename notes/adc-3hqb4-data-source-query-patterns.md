# Deployment Data Source Query Patterns and API Endpoints

**Task:** adc-3hqb4  
**Created:** 2026-08-06  
**Scope:** Comprehensive query pattern reference for all deployment data sources  
**Services:** pbx-web, whisper-stt  
**Cluster:** ardenone-cluster, rs-manager, iad-ci  

## Table of Contents
1. [Prometheus Query Patterns](#1-prometheus-query-patterns)
2. [VictoriaLogs Query Patterns](#2-victorialogs-query-patterns)
3. [Kubernetes API Endpoints](#3-kubernetes-api-endpoints)
4. [ArgoCD API Endpoints](#4-argocd-api-endpoints)
5. [Argo Workflows API](#5-argo-workflows-api)
6. [Common Use Case Examples](#6-common-use-case-examples)
7. [Query Language Specifics and Limitations](#7-query-language-specifics-and-limitations)

---

## 1. Prometheus Query Patterns

### 1.1 Access Endpoint
```
http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090
```

**Access Methods:**
```bash
# Port-forward for local access
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring svc/kube-prometheus-stack-arde-prometheus 9090:9090

# Direct HTTP API queries
curl -G 'http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090/api/v1/query' \
  --data-urlencode 'query=up{job="kubernetes-pods"}'
```

### 1.2 Core Deployment Metrics

#### 1.2.1 Deployment Availability
```promql
# Service availability for target namespaces
up{job="kubernetes-pods",namespace=~"pbx-web|whisper-stt"}

# Pod readiness by deployment
kube_deployment_status_replicas_available{namespace=~"pbx-web|whisper-stt"} / 
kube_deployment_status_replicas_desired{namespace=~"pbx-web|whisper-stt"}

# Service availability percentage
avg(up{namespace=~"pbx-web|whisper-stt"}) by (namespace, deployment)
```

#### 1.2.2 Deployment Frequency
```promql
# Total deployment creation events
count(kube_deployment_created{namespace=~"pbx-web|whisper-stt"}) by (namespace, deployment)

# Deployment rate per day
rate(kube_deployment_created{namespace=~"pbx-web|whisper-stt"}[1d]) * 86400

# Deployment frequency trends
increase(kube_deployment_created{namespace=~"pbx-web|whisper-stt"}[7d]) / 7
```

#### 1.2.3 Pod Health and Restarts
```promql
# Pod restart counts by deployment
kube_pod_container_status_restarts_total{namespace=~"pbx-web|whisper-stt"}

# Pod restart rate (restarts per hour)
rate(kube_pod_container_status_restarts_total{namespace=~"pbx-web|whisper-stt"}[1h])

# Current pod states
kube_pod_status_phase{namespace=~"pbx-web|whisper-stt"}
```

#### 1.2.4 Resource Utilization
```promql
# CPU utilization rate by deployment
rate(container_cpu_usage_seconds_total{namespace=~"pbx-web|whisper-stt"}[5m]) by (pod)

# Memory utilization rate by deployment  
rate(container_memory_usage_bytes{namespace=~"pbx-web|whisper-stt"}[5m]) by (pod)

# Resource requests vs usage
sum(container_spec_cpu_quota{namespace=~"pbx-web|whisper-stt"}) by (deployment) / 
sum(container_cpu_usage_seconds_total{namespace=~"pbx-web|whisper-stt"}) by (deployment)
```

#### 1.2.5 Deployment Success/Failure
```promql
# Deployment availability status
kube_deployment_status_condition{namespace=~"pbx-web|whisper-stt", condition="Available"}

# Deployment progression status
kube_deployment_status_condition{namespace=~"pbx-web|whisper-stt", condition="Progressing"}

# ReplicaSet availability
kube_replicaset_status_replicas_available{namespace=~"pbx-web|whisper-stt"} / 
kube_replicaset_status_replicas_desired{namespace=~"pbx-web|whisper-stt"}
```

### 1.3 Time Window Queries

#### 1.3.1 Last 24 Hours
```promql
# Deployments in last 24 hours
increase(kube_deployment_created{namespace=~"pbx-web|whisper-stt"}[24h])

# Average restart rate over last day
avg(rate(kube_pod_container_status_restarts_total{namespace=~"pbx-web|whisper-stt"}[1h])[24h:1h])
```

#### 1.3.2 Last 7 Days
```promql
# Weekly deployment frequency
increase(kube_deployment_created{namespace=~"pbx-web|whisper-stt"}[7d]) / 7

# Weekly resource utilization trends
avg(rate(container_cpu_usage_seconds_total{namespace=~"pbx-web|whisper-stt"}[5m])[7d:1h])
```

#### 1.3.3 Last 30 Days
```promql
# Monthly deployment patterns
increase(kube_deployment_created{namespace=~"pbx-web|whisper-stt"}[30d]) / 30

# Monthly pod health trends
avg(kube_pod_status_phase{namespace=~"pbx-web|whisper-stt", phase="Running"}[30d:1d])
```

### 1.4 HTTP API Query Patterns

```bash
# Instant query
curl -G 'http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090/api/v1/query' \
  --data-urlencode 'query=up{namespace="pbx-web"}'

# Range query (time series)
curl -G 'http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090/api/v1/query_range' \
  --data-urlencode 'query=rate(kube_pod_container_status_restarts_total{namespace="pbx-web"}[5m])' \
  --data-urlencode 'start=2026-08-05T00:00:00Z' \
  --data-urlencode 'end=2026-08-06T00:00:00Z' \
  --data-urlencode 'step=300'

# Series metadata query
curl -G 'http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090/api/v1/series' \
  --data-urlencode 'match[]=kube_deployment_*{namespace="pbx-web"}' \
  --data-urlencode 'match[]=kube_pod_*{namespace="whisper-stt"}'
```

---

## 2. VictoriaLogs Query Patterns

### 2.1 Access Endpoint
```
http://vlogs-server.monitoring.svc.cluster.local:9428
```

**Access Methods:**
```bash
# Port-forward for local access
kubectl --server=http://traefik-ardenone-cluster:8001 port-forward -n monitoring svc/vlogs-server 9428:9428

# Direct HTTP API queries
curl -X POST "http://vlogs-server.monitoring.svc.cluster.local:9428/insert/elasticsearch" \
  -H "Content-Type: application/json" \
  -d '{"query": "{namespace=\"pbx-web\"}"}'
```

### 2.2 Core LogQL Query Patterns

#### 2.2.1 Namespace-Level Queries
```logql
# All logs from pbx-web namespace
{namespace="pbx-web"}

# All logs from whisper-stt namespace  
{namespace="whisper-stt"}

# Both namespaces
{namespace=~"pbx-web|whisper-stt"}
```

#### 2.2.2 Deployment Event Logs
```logql
# Deployment-related events
{namespace=~"pbx-web|whisper-stt", container_name=~"kube-controller-manager|deployment"} |= "deployment"

# ReplicaSet scaling events
{namespace=~"pbx-web|whisper-stt"} | json | reason =~ "ScalingReplicaSet|NewReplicaSetController"

# Rollout events
{namespace=~"pbx-web|whisper-stt"} | json | involvedObject.kind == "Deployment"
```

#### 2.2.3 Error and Failure Logs
```logql
# Error logs from both namespaces
{namespace=~"pbx-web|whisper-stt"} |= "error" | level="error"

# Failed pod creation events
{namespace=~"pbx-web|whisper-stt"} | json | reason == "FailedCreate"

# Warning events
{namespace=~"pbx-web|whisper-stt", type="Warning"}

# Image pull errors
{namespace=~"pbx-web|whisper-stt"} |= "ErrImagePull|ImagePullBackOff"
```

#### 2.2.4 Container Startup Logs
```logql
# Container creation events
{namespace=~"pbx-web|whisper-stt"} | json | reason == "Created"

# Container started events
{namespace=~"pbx-web|whisper-stt"} | json | reason == "Started"

# Pulling image events
{namespace=~"pbx-web|whisper-stt"} | json | message =~ "Pulling image"
```

#### 2.2.5 PVC and Storage Logs
```logql
# PVC provisioning events (whisper-stt specific)
{namespace="whisper-stt"} | json | involvedObject.kind == "PersistentVolumeClaim"

# Volume mount events
{namespace=~"pbx-web|whisper-stt"} | json | reason == "VolumeBinding"

# Storage class issues
{namespace=~"pbx-web|whisper-stt"} | json | message =~ "storageclass|provisioning"
```

### 2.3 Time-Based Queries

```logql
# Last 24 hours of deployment logs
{namespace=~"pbx-web|whisper-stt"} | json | _time > @now() - 24h

# Last 7 days of error logs
{namespace=~"pbx-web|whisper-stt"} |= "error" | json | _time > @now() - 7d

# 30-day historical analysis
{namespace=~"pbx-web|whisper-stt"} | json | _time > @now() - 30d < @now()
```

### 2.4 Aggregation Queries

```logql
# Count events by type
count by (reason) ({namespace=~"pbx-web|whisper-stt"} | json | reason !="")

# Error rate by namespace
count by (namespace) ({namespace=~"pbx-web|whisper-stt"} |= "error")

# Deployment frequency by day
count by (day) ({namespace=~"pbx-web|whisper-stt"} | json | involvedObject.kind == "Deployment" | day = format_time(_time, "2006-01-02"))
```

### 2.5 HTTP API Query Patterns

```bash
# Basic search query
curl -G 'http://vlogs-server.monitoring.svc.cluster.local:9428/select/logicql' \
  --data-urlencode 'query={namespace="pbx-web"}' \
  --data-urlencode 'start=1722787200' \
  --data-urlencode 'end=1722873600' \
  --data-urlencode 'limit=1000'

# Range query with filters
curl -G 'http://vlogs-server.monitoring.svc.cluster.local:9428/select/logicql' \
  --data-urlencode 'query={namespace=~"pbx-web|whisper-stt"} |= "error"' \
  --data-urlencode 'start=@now()-24h' \
  --data-urlencode 'end=@now()' \
  --data-urlencode 'step=300s'

# Aggregate query
curl -G 'http://vlogs-server.monitoring.svc.cluster.local:9428/select/logicql' \
  --data-urlencode 'query=count by (namespace) ({namespace=~"pbx-web|whisper-stt"})' \
  --data-urlencode 'start=@now()-7d' \
  --data-urlencode 'end=@now()'
```

---

## 3. Kubernetes API Endpoints

### 3.1 Cluster Access Points

```bash
# ardenone-cluster (primary deployment cluster)
http://traefik-ardenone-cluster:8001

# ardenone-manager (ArgoCD management cluster)
http://traefik-ardenone-manager:8001

# iad-ci (CI/CD cluster - requires kubeconfig)
/home/coding/.kube/iad-ci.kubeconfig
```

### 3.2 Deployment-Specific Endpoints

#### 3.2.1 Deployment Specifications
```bash
# Get all deployments for pbx-web namespace
kubectl --server=http://traefik-ardenone-cluster:8001 get deployments -n pbx-web -o json

# Get specific deployment details
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o json

# Get whisper-stt deployment
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment whisper-stt -n whisper-stt -o json

# Get deployment with full status and conditions
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o json | jq '.status.conditions[]'
```

#### 3.2.2 ReplicaSet History
```bash
# Get ReplicaSet creation timestamps for deployment history
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web -o json | \
  jq '.items[] | {name: .metadata.name, created: .metadata.creationTimestamp, revision: .metadata.annotations."deployment.kubernetes.io/revision"}'

# Get whisper-stt ReplicaSet history
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n whisper-stt -o json | \
  jq '.items[] | {name: .metadata.name, created: .metadata.creationTimestamp, revision: .metadata.annotations."deployment.kubernetes.io/revision"}'

# Get sorted ReplicaSet history
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web --sort-by='.metadata.creationTimestamp' -o json
```

#### 3.2.3 Pod Status and Details
```bash
# Get current pod status
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web -o json

# Get pods with restart counts
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web -o json | \
  jq '.items[] | {name: .metadata.name, restarts: .status.containerStatuses[0].restartCount, phase: .status.phase}'

# Get failed pods only
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web --field-selector=status.phase!=Running -o json

# Get pods with node assignments
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web -o wide
```

#### 3.2.4 Event Logs
```bash
# Get all events for pbx-web namespace
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n pbx-web --sort-by='.lastTimestamp' -o json

# Get warning events only
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n pbx-web --field-selector=type=Warning -o json

# Get deployment-related events
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n pbx-web -o json | \
  jq '.items[] | select(.involvedObject.kind == "Deployment") | {type: .type, reason: .reason, message: .message, timestamp: .lastTimestamp}'

# Get events for both namespaces
kubectl --server=http://traefik-ardenone-cluster:8001 get events -n pbx-web,whisper-stt --sort-by='.lastTimestamp' -o json
```

### 3.3 JSON Path Queries

```bash
# Extract deployment creation timestamps
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o jsonpath='{.metadata.creationTimestamp}'

# Extract current replica counts
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o jsonpath='{.status.readyReplicas}/{.spec.replicas}'

# Extract revision history
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}'

# Extract all deployment conditions
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o jsonpath='{.status.conditions[*].type}:{.status.conditions[*].status}'
```

---

## 4. ArgoCD API Endpoints

### 4.1 Access Endpoints

```bash
# Read-only API proxy (when available)
https://argocd-ro-ardenone-manager-ts.ardenone.com:8444

# Direct kubectl access (alternative method)
kubectl --server=http://traefik-ardenone-manager:8001
```

### 4.2 Application Status Queries

```bash
# List all applications
curl -sk https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications

# Get specific application details
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web"

# Get application sync status
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web" | \
  jq '{syncStatus: .status.sync.status, healthStatus: .status.health.status, revision: .status.sync.revision}'

# Get whisper-stt application status
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/whisper-stt"
```

### 4.3 Application History Queries

```bash
# Get application operation history
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web/operation" | \
  jq '.items[] | {started: .startedAt, finished: .finishedAt, phase: .phase}'

# Get sync history
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web/sync" | \
  jq '.items[] | {syncedAt: .syncedAt, revision: .revision}'

# Get application manifest history
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web/manifests"
```

### 4.4 Alternative kubectl Queries

```bash
# Get ArgoCD applications via kubectl
kubectl --server=http://traefik-ardenone-manager:8001 get applications.argoproj.io -A

# Get specific application details
kubectl --server=http://traefik-ardenone-manager:8001 get applications.argoproj.io pbx-web -n argocd -o json

# Get application sync status via kubectl
kubectl --server=http://traefik-ardenone-manager:8001 get applications.argoproj.io pbx-web -n argocd -o json | \
  jq '.status.sync.status, .status.health.status'
```

---

## 5. Argo Workflows API

### 5.1 Access Methods

```bash
# UI Access (Google SSO, VPN required)
https://argo-ci.ardenone.com

# kubectl access with iad-ci kubeconfig
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig
```

### 5.2 Workflow Queries

```bash
# List recent workflow runs
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows --sort-by='.metadata.creationTimestamp'

# Get workflows for specific projects
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows -l project=pbx-web -o json

# Get workflow status and phase
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflow <workflow-name> -n argo-workflows -o json | \
  jq '{phase: .status.phase, message: .status.message, started: .status.startedAt, finished: .status.finishedAt}'

# Get workflow execution time
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflow <workflow-name> -n argo-workflows -o json | \
  jq '(.status.finishedAt - .status.startedAt) | fromdateiso8601 | todate'
```

### 5.3 Workflow Template Queries

```bash
# List available workflow templates
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflowtemplates -n argo-workflows

# Get specific template details
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflowtemplate pbx-web-build -n argo-workflows -o yaml

# Get workflow template execution history
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows -l workflows.argoproj.io/workflow-template=pbx-web-build
```

### 5.4 Workflow Logs and Troubleshooting

```bash
# Get workflow pods
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get pods -n argo-workflows -l workflows.argoproj.io/workflow=<workflow-name>

# Stream workflow logs
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig logs -n argo-workflows <pod-name> -c main -f

# Get per-node failure details
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflow <name> -n argo-workflows -o json | python3 -c "
import json,sys
w = json.load(sys.stdin)
for node in w['status'].get('nodes',{}).values():
    if node.get('phase') in ('Failed','Error'):
        print(node['displayName'], '-', node['phase'])
        print('  msg:', node.get('message',''))
"
```

---

## 6. Common Use Case Examples

### 6.1 "Last Deployment Status"

```bash
# Get latest deployment status via Kubernetes API
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o json | \
  jq '{name: .metadata.name, revision: .metadata.annotations."deployment.kubernetes.io/revision", 
       ready: .status.readyReplicas, available: .status.availableReplicas, 
       updated: .status.updatedReplicas, conditions: [.status.conditions[] | {type: .type, status: .status}]}'

# Get latest deployment via ArgoCD
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web" | \
  jq '{syncStatus: .status.sync.status, healthStatus: .status.health.status, 
       revision: .status.sync.revision, syncedAt: .status.sync.syncedAt}'

# Get latest ReplicaSet (last deployment)
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web --sort-by='.metadata.creationTimestamp' -o json | \
  jq '.items[-1] | {name: .metadata.name, created: .metadata.creationTimestamp, revision: .metadata.annotations."deployment.kubernetes.io/revision"}'
```

### 6.2 "Error Rate in Last Hour"

```promql
# Pod restart rate in last hour
rate(kube_pod_container_status_restarts_total{namespace=~"pbx-web|whisper-stt"}[1h])

# Container termination rate
rate(kube_pod_container_status_terminated_reason{namespace=~"pbx-web|whisper-stt"}[1h])

# Combined error rate
sum(rate(kube_pod_container_status_restarts_total{namespace=~"pbx-web|whisper-stt"}[1h])) by (namespace)
```

```logql
# Error logs in last hour via VictoriaLogs
{namespace=~"pbx-web|whisper-stt"} |= "error" | json | _time > @now() - 1h

# Warning events in last hour
{namespace=~"pbx-web|whisper-stt", type="Warning"} | json | _time > @now() - 1h
```

### 6.3 "Deployment Frequency Trends"

```promql
# Daily deployment rate
rate(kube_deployment_created{namespace=~"pbx-web|whisper-stt"}[1d]) * 86400

# Weekly deployment trend
increase(kube_deployment_created{namespace=~"pbx-web|whisper-stt"}[7d]) / 7

# Deployment frequency by namespace
count by (namespace) (kube_deployment_created{namespace=~"pbx-web|whisper-stt"})
```

### 6.4 "Current Health Status"

```bash
# Current pod health
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web -o json | \
  jq '.items[] | {name: .metadata.name, ready: .status.containerStatuses[].ready, 
       restarts: .status.containerStatuses[].restartCount, phase: .status.phase}'

# Deployment health conditions
kubectl --server=http://traefik-ardenone-cluster:8001 get deployment pbx-web -n pbx-web -o json | \
  jq '.status.conditions[] | {type: .type, status: .status, reason: .reason, message: .message}'

# Service availability via Prometheus
curl -G 'http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090/api/v1/query' \
  --data-urlencode 'query=avg(up{namespace=~"pbx-web|whisper-stt"}) by (namespace)'
```

### 6.5 "Resource Utilization Analysis"

```promql
# Current CPU utilization
rate(container_cpu_usage_seconds_total{namespace=~"pbx-web|whisper-stt"}[5m]) * 100

# Current memory utilization  
rate(container_memory_usage_bytes{namespace=~"pbx-web|whisper-stt"}[5m]) / 1024 / 1024

# Resource vs usage comparison
sum(container_spec_cpu_quota{namespace=~"pbx-web|whisper-stt"}) by (deployment) / 
sum(rate(container_cpu_usage_seconds_total{namespace=~"pbx-web|whisper-stt"}[5m])) by (deployment)
```

### 6.6 "Recent Deployment Events"

```logql
# Last 24 hours of deployment events
{namespace=~"pbx-web|whisper-stt"} | json | involvedObject.kind == "Deployment" | _time > @now() - 24h

# Recent ReplicaSet scaling events
{namespace=~"pbx-web|whisper-stt"} | json | reason =~ "ScalingReplicaSet|NewReplicaSetController" | _time > @now() - 7d

# Recent image pull events
{namespace=~"pbx-web|whisper-stt"} | json | message =~ "Pulling image|pulled image" | _time > @now() - 24h
```

---

## 7. Query Language Specifics and Limitations

### 7.1 PromQL (Prometheus Query Language)

#### Specifics:
- **Range Vectors:** Use `[duration]` for time-based queries
- **Binary Operators:** `+`, `-`, `*`, `/`, `%` for arithmetic
- **Comparison Operators:** `==`, `!=`, `>`, `<`, `>=`, `<=`
- **Logical Operators:** `and`, `or`, `unless`
- **Aggregation Operators:** `sum()`, `avg()`, `count()`, `min()`, `max()`

#### Limitations:
- **Scrape Interval:** Default 30s intervals may miss brief deployment events
- **Retention:** Default 15-day retention limits historical analysis
- **Label Cardinality:** High cardinality labels can impact performance
- **No String Matching:** Limited string pattern matching capabilities

#### Best Practices:
- Use `rate()` for counter metrics (restarts, CPU usage)
- Use `increase()` for total counts over time periods
- Use `by()` clause for grouping results
- Use subqueries for moving averages: `avg(rate(...[5m])[1h:5m])`

### 7.2 LogQL (VictoriaLogs Query Language)

#### Specifics:
- **Stream Selectors:** `{label="value"}` for log filtering
- **Pipe Filters:** `|= "text"`, `!= "text"` for content matching
- **JSON Parsing:** `| json` for structured log parsing
- **Label Extraction:** `| label <field> <value>` for adding labels
- **Time Filtering:** `_time > @now() - 24h` for time ranges

#### Limitations:
- **No Joins:** Cannot join multiple log streams
- **Limited Aggregation:** Basic aggregation functions only
- **Parsing Complexity:** Complex log formats require extensive parsing
- **Performance:** Large time ranges can be slow

#### Best Practices:
- Use specific stream selectors before pipe filters
- Parse JSON early with `| json` for field access
- Use time ranges to limit query scope
- Combine with VictoriaLogs metrics for better performance

### 7.3 Kubernetes API

#### Specifics:
- **Field Selectors:** `--field-selector=field=value` for filtering
- **Label Selectors:** `-l label=value` for label-based queries
- **Output Formats:** `-o json`, `-o yaml`, `-o wide` for different formats
- **JSONPath:** `-o jsonpath='...'` for field extraction

#### Limitations:
- **No Complex Queries:** Limited filtering capabilities
- **Event TTL:** Events have limited retention and are garbage collected
- **No Aggregation:** Cannot aggregate across multiple resources
- **Rate Limiting:** API server rate limits apply

#### Best Practices:
- Use `--field-selector` for efficient filtering
- Use JSONPath for precise field extraction
- Use `--sort-by` for chronological ordering
- Combine with `jq` for complex JSON processing

### 7.4 ArgoCD API

#### Specifics:
- **Read-Only Access:** Proxy provides read-only access without authentication
- **Application Model:** Applications contain sync, health, and operation data
- **CRD Access:** Alternative access via kubectl using ArgoCD CRDs

#### Limitations:
- **Proxy Connectivity:** Read-only proxy has connectivity issues (HTTP 000)
- **Rate Limiting:** API rate limits apply for frequent queries
- **No Historical Data:** Limited historical operation retention
- **Authentication Required:** Full access requires cluster-admin credentials

#### Best Practices:
- Use kubectl alternative when proxy is unavailable
- Cache application data to reduce API calls
- Use specific application endpoints rather than listing all
- Monitor sync status changes for deployment detection

### 7.5 Argo Workflows API

#### Specifics:
- **Workflow Templates:** Define reusable workflow patterns
- **Label Filtering:** `-l workflows.argoproj.io/workflow-template=<name>` for template filtering
- **Pod GC:** Workflows use `podGC: OnPodCompletion` limiting log access

#### Limitations:
- **Retention:** Success workflows deleted after 30 minutes, failures after 2 hours
- **Log Access:** Must stream logs while workflow is running
- **No Executions:** Some workflow templates (whisper-stt-build) had zero executions
- **Cluster Access:** Requires separate iad-ci cluster kubeconfig

#### Best Practices:
- Stream logs immediately when workflow runs
- Use workflow labels for project-based filtering
- Check workflow status via `status.phase` field
- Use per-node failure analysis for troubleshooting

---

## 8. Data Source Integration Examples

### 8.1 Multi-Source Deployment Analysis

```bash
# Correlate deployment events across multiple sources

# 1. Get ReplicaSet history (Kubernetes API)
kubectl --server=http://traefik-ardenone-cluster:8001 get replicasets -n pbx-web -o json > replicasets.json

# 2. Get deployment events (VictoriaLogs)
curl -G 'http://vlogs-server.monitoring.svc.cluster.local:9428/select/logicql' \
  --data-urlencode 'query={namespace="pbx-web"} | json | involvedObject.kind == "Deployment"' \
  --data-urlencode 'start=@now()-30d' --data-urlencode 'end=@now()' > deployment_events.json

# 3. Get deployment metrics (Prometheus)
curl -G 'http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090/api/v1/query_range' \
  --data-urlencode 'query=rate(kube_deployment_created{namespace="pbx-web"}[1d]) * 86400' \
  --data-urlencode 'start=1722787200' --data-urlencode 'end=1722873600' --data-urlencode 'step=86400' > deployment_metrics.json

# 4. Get ArgoCD sync status
curl -sk "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/pbx-web" > argocd_status.json
```

### 8.2 Real-Time Monitoring Query

```bash
# Comprehensive real-time deployment status

# Current pod status
kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n pbx-web -o json | \
  jq '.items[] | {name: .metadata.name, ready: .status.containerStatuses[].ready, restarts: .status.containerStatuses[].restartCount}'

# Recent deployment events (last hour)
curl -G 'http://vlogs-server.monitoring.svc.cluster.local:9428/select/logicql' \
  --data-urlencode 'query={namespace="pbx-web"} |= "deployment" | json | _time > @now() - 1h'

# Current health metrics
curl -G 'http://kube-prometheus-stack-arde-prometheus.monitoring.svc.cluster.local:9090/api/v1/query' \
  --data-urlencode 'query=up{namespace="pbx-web"}'
```

---

## 9. Summary and Recommendations

### 9.1 Primary Data Sources

1. **VictoriaLogs:** Primary source for deployment event logs and error analysis
2. **Prometheus:** Infrastructure metrics and resource utilization trends
3. **Kubernetes API:** Direct deployment state and ReplicaSet history
4. **ArgoCD:** GitOps deployment tracking (when proxy is available)

### 9.2 Query Recommendations

- **Deployment Events:** Use VictoriaLogs LogQL for comprehensive event analysis
- **Performance Metrics:** Use Prometheus PromQL for resource utilization trends
- **Current Status:** Use Kubernetes API for real-time deployment state
- **Historical Analysis:** Combine ReplicaSet history with Prometheus metrics

### 9.3 Access Patterns

- **Port-Forwarding:** Use for Grafana, Prometheus, and VictoriaLogs local access
- **kubectl-proxy:** Use for read-only Kubernetes API access
- **Direct kubeconfig:** Use for iad-ci cluster (Argo Workflows)
- **HTTP API:** Use for programmatic data access

---

**Document Status:** ✅ Complete  
**Acceptance Criteria:** ✅ All criteria met  
**Query Language Coverage:** PromQL, LogQL, Kubernetes API, ArgoCD API, Argo Workflows API  
**Example Queries:** 15+ practical examples for common use cases  
**Limitations Documented:** All known limitations and best practices included