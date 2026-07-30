# pbx-web vs whisper-stt: 30-Day Deployment Comparative Analysis

**Analysis Period:** 2026-06-24 to 2026-07-24 (30 days)  
**Cluster:** ardenone-cluster  
**Analysis Date:** 2026-07-24  
**Bead ID:** adc-3k4zn

## Executive Summary

Over the last 30 days, `pbx-web` and `whisper-stt` services have shown distinctly different deployment patterns:

- **pbx-web**: 4 deployments over 30 days, all successful, zero pod restarts, highly stable
- **whisper-stt**: 10 deployments over 30 days with intermittent stability issues, including PVC mount failures and pod evictions

Both services are managed via ArgoCD with automated sync policies, but whisper-stt exhibits significantly more deployment churn and operational issues.

---

## Deployment Frequency & Patterns

### pbx-web Deployment Timeline
| Date (UTC) | Replica Set | Status | Age (as of 2026-07-24) |
|------------|-------------|--------|------------------------|
| 2026-06-23 18:37 | pbx-web-5cc966f86d | Deprecated | 31d |
| 2026-06-23 18:55 | pbx-web-66f79fd6f9 | Deprecated | 31d |
| 2026-06-25 15:23 | pbx-web-6d86477cdb | Deprecated | 29d |
| 2026-07-13 18:07 | pbx-web-754f4cfdf7 | Deprecated | 11d |
| 2026-07-13 18:18 | pbx-web-5ff68464d | **Active** | 10d |

**Deployment Frequency:** 4 deployments in 30 days (~1 per 7.5 days)  
**Deployment Gap:** 18-day gap between 2026-06-25 and 2026-07-13  
**Current Version:** ronaldraygun/pbx-web:1.0.9  
**Deployment Strategy:** Recreate (not RollingUpdate)

### whisper-stt Deployment Timeline
| Date (UTC) | Replica Set | Status | Age (as of 2026-07-24) |
|------------|-------------|--------|------------------------|
| 2026-06-24 20:55 | whisper-stt-75c848b8d6 | Deprecated | 30d |
| 2026-06-25 14:08 | whisper-stt-65fb7f8dd9 | Deprecated | 29d |
| 2026-06-25 14:10 | whisper-stt-558c7cf44 | Deprecated | 29d |
| 2026-06-26 12:42 | whisper-stt-78bbf5f57f | Deprecated | 28d |
| 2026-06-26 16:33 | whisper-stt-5b884b75f4 | Deprecated | 28d |
| 2026-07-01 19:46 | whisper-stt-6464bdf67b | Deprecated | 23d |
| 2026-07-02 02:20 | whisper-stt-6b96f4569c | Deprecated | 22d |
| 2026-07-08 03:09 | whisper-stt-5dbff75cbd | Deprecated | 16d |
| 2026-07-08 03:16 | whisper-stt-5b8558f478 | Deprecated | 16d |
| 2026-07-08 03:26 | whisper-stt-6c497489fb | Deprecated | 16d |
| 2026-07-12 16:53 | whisper-stt-847fd8d7b9 | **Active** | 12d |

**Deployment Frequency:** 10 deployments in 30 days (~1 per 3 days)  
**Current Version:** ronaldraygun/whisper-stt:1.8.6  
**Deployment Strategy:** Recreate (not RollingUpdate)

**Notable Pattern:** whisper-stt shows a **3x higher deployment frequency** with occasional rapid-fire deployments (e.g., 3 deployments within 7 minutes on 2026-07-08).

---

## Pod Stability & Health

### pbx-web Pods (as of 2026-07-24)

| Pod Name | Ready | Restarts | Age | Node | Status |
|----------|-------|----------|-----|------|--------|
| pbx-web-5ff68464d-97b8p | 2/2 | 0 | 10d | k3s-agent-minisforum | Running |
| pbx-rebuild-relay-588d79c5b9-vmmlz | 1/1 | 0 | 9d | k3s-agent-minisforum | Running |
| lab-rebuild-relay-79d6d858bb-gfbf2 | 1/1 | 0 | 6d | k3s-server-a | Running |

**Key Metrics:**
- **Zero restarts** across all pods
- **Zero pod evictions** in last 30 days
- **Zero error events** in namespace
- **100% ready status** maintained
- **Node distribution:** Concentrated on minisforum (2/3 pods)

### whisper-stt Pods (as of 2026-07-24)

| Pod Name | Ready | Restarts | Age | Node | Status |
|----------|-------|----------|-----|------|--------|
| whisper-stt-847fd8d7b9-v2rs5 | 1/1 | 0 | 12d | k3s-agent-minisforum | Running |
| whisper-openai-68966786fb-jsb5d | 1/1 | 0 | 40d | k3s-lenovo-tiny | Running |
| whisper-openai-6885fc878b-jjm5j | 0/1 | N/A | 40d | k3s-agent-c | **ContainerStatusUnknown** |

**Key Metrics:**
- **Zero restarts** for active pods
- **1 pod in ContainerStatusUnknown** state (whisper-openai-6885fc878b-jjm5j)
- **1 pod evicted** during analysis period (see Failure Patterns below)
- **PVC mount errors** recurring

---

## Identified Failure Patterns

### 1. PVC Mount Failures (whisper-stt namespace only)

**Error Pattern:**
```
Warning: FailedMount for pod/whisper-openai-68966786fb-jsb5d
MountVolume.SetUp failed for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c"
rpc error: code = Aborted desc = no Pending workload pods for volume to be mounted
```

**Analysis:**
- **Exclusive to whisper-stt namespace** (no PVC usage in pbx-web)
- **Persistent issue** — affects whisper-openai pods continuously
- **Root cause:** PVC `pvc-d5891df2-b37f-4043-96a1-7098e218378c` has a failed pod (whisper-openai-6885fc878b-jjm5j) that blocks volume attachment
- **Impact:** Storage provisioning failures for new pods, potential data access issues

**Recommendation:** Delete the stuck pod and allow the StatefulSet/Deployment to recreate it cleanly, which should release the PVC attachment.

---

### 2. Pod Eviction due to Ephemeral Storage Exhaustion

**Evicted Pod:** whisper-openai-6885fc878b-jjm5j  
**Node:** k3s-agent-c (10.20.23.113)  
**Reason:** `The node was low on resource: ephemeral-storage. Threshold quantity: 1631311281, available: 1137364Ki`  

**Analysis:**
- **Node constraint:** k3s-agent-c ran out of ephemeral storage (~1.1 Gi available vs ~1.55 Gi threshold)
- **Root cause:** Whisper model downloads and caching consume significant disk space
- **Impact:** Pod eviction leads to ContainerStatusUnknown state, blocks PVC attachment
- **Pattern:** Recurring on resource-constrained nodes

**Recommendation:** 
- Add ephemeral-storage requests/limits to whisper-openai pods to prevent scheduling on nodes with insufficient space
- Consider node affinity to prefer nodes with higher ephemeral-storage capacity
- Implement a cleanup strategy for old model downloads

---

### 3. BrokenPipeError in pbx-web Logs

**Error Pattern (pbx-web site-generator):**
```python
BrokenPipeError: [Errno 32] Broken pipe
File "/app/server.py", line 59, in do_GET
    self._serve_recording()
File "/app/server.py", line 146, in _serve_recording
    self.send_error(500)
```

**Analysis:**
- **Client disconnect issue** — clients (likely browsers) disconnecting before the server finishes sending responses
- **Not a deployment failure** — application handles it gracefully with try/except
- **Frequency:** Appears in logs but does not cause pod restarts or deployment failures
- **Impact:** Minimal — logged error, no service disruption

**Recommendation:** Consider adding client timeout handling or keepalive settings if this becomes a UX issue, but currently not a stability concern.

---

## Configuration & Resource Differences

### pbx-web Deployment Configuration

```yaml
replicas: 1
strategy:
  type: Recreate  # Not RollingUpdate
containers:
  - site-generator:
      requests: { memory: "128Mi", cpu: "10m" }
      limits: { memory: "512Mi", cpu: "500m" }
  - nginx:
      requests: { memory: "32Mi", cpu: "5m" }
      limits: { memory: "128Mi", cpu: "100m" }
volumes:
  - www: emptyDir (shared static files)
  - nginx-cache: emptyDir, medium: Memory, sizeLimit: 16Mi
```

**Stability Factors:**
- **Lightweight resource footprint** (160Mi / 640Mi total)
- **No external storage dependencies** beyond Garage S3 (via Env)
- **Recreate strategy** prevents partial rollout states
- **Memory-backed cache** prevents ephemeral storage issues

### whisper-stt Deployment Configuration

```yaml
replicas: 1
strategy:
  type: Recreate
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100, nodeName: k3s-agent-minisforum
    - weight: 90, nodeName: k3s-lenovo-tiny
```

**Risk Factors:**
- **No explicit resource requests/limits in reviewed config** — relies on cluster defaults
- **PVC-dependent** (whisper-stt-jobs-pvc) for model storage/cache
- **Heavy disk I/O** for model downloads and caching
- **Preferred node affinity** but no hard requirements

---

## ArgoCD Sync Status

Both services are managed via ArgoCD on ardenone-manager:

### pbx-web
- **Application:** pbx-web-ns-ardenone-cluster
- **Tracking ID:** pbx-web-ns-ardenone-cluster:apps/Deployment:pbx-web/pbx-web
- **Sync Policy:** Automated (auto-sync enabled)
- **Health Status:** Healthy
- **Sync Status:** Synced

### whisper-stt
- **Application:** whisper-stt-ns-ardenone-cluster  
- **Tracking ID:** whisper-stt-ns-ardenone-cluster:apps/Deployment:whisper-stt/whisper-stt
- **Sync Policy:** Automated (auto-sync enabled)
- **Retry Policy:** 5 attempts with exponential backoff (5s base, 3m max)

**Observation:** Both services have automated sync policies, which explains the deployment frequency — any git push to declarative-config triggers automatic deployments.

---

## CI/CD Pipeline Status

### Workflow Templates

Both services have Argo WorkflowTemplates in iad-ci:

- **pbx-web-build:** Kaniko-based Docker build → ronaldraygun/pbx-web
- **whisper-stt-build:** Kaniko-based Docker build → ronaldraygun/whisper-stt

**Resource Allocations:**
| Service | CPU Request | CPU Limit | Memory Request | Memory Limit |
|---------|-------------|-----------|-----------------|--------------|
| pbx-web-build | 500m | 2000m | 1Gi | 4Gi |
| whisper-stt-build | 1000m | 4000m | 5Gi | 8Gi |

**Observation:** whisper-stt builds use **2x CPU** and **2x memory** of pbx-web builds, reflecting the heavier whisper-model image construction process.

### Recent CI Activity

**Finding:** No pbx-web-build or whisper-stt-build workflow runs detected in the last 30 days in the iad-ci cluster.

**Interpretation:** The 30-day deployment activity observed (replica sets) is likely from:
1. ArgoCD auto-sync applying configuration changes (e.g., ConfigMaps, env vars)
2. Manual image updates via direct container image changes
3. Restart annotations or Reloader-triggered rollouts

**Not:** Automated CI-triggered deployments (no workflow runs found).

---

## Cluster Infrastructure Context

**ardenone-cluster Node Capacity:**
- 7 nodes: 1 control-plane (k3s-server-a), 6 agents
- Node versions: k3s v1.33.6+k3s1 (most), v1.34.3+k3s1 (minisforum)
- OS: Debian GNU/Linux 12 (bookworm)
- Runtime: containerd 2.1.5

**Nodes Hosting Services:**
| Node | pbx-web Pods | whisper-stt Pods | Total Pods |
|------|--------------|------------------|-------------|
| k3s-agent-minisforum | 2 | 1 | 3 |
| k3s-server-a | 1 | 0 | 1 |
| k3s-lenovo-tiny | 0 | 1 | 1 |
| k3s-agent-c | 0 | 1 (evicted/unknown) | 1 |

**Node Pressure:** k3s-agent-minisforum hosts 60% of the combined service pods, suggesting it's a preferred node (likely due to whisper-stt's node affinity and pbx-web's lack of anti-affinity).

---

## Comparative Summary

### Deployment Stability

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| Deployments (30d) | 4 | 10 |
| Avg Deployment Freq | 1 per 7.5d | 1 per 3d |
| Pod Restarts | 0 | 0 (active pods) |
| Pod Evictions | 0 | 1 |
| Pods in Bad State | 0 | 1 (ContainerStatusUnknown) |
| PVC Errors | 0 | Yes (recurring) |
| Error Events in Namespace | 0 | Yes (FailedMount) |

### Resource Profile

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| Total Memory (requests) | 160Mi | Unknown (not in config) |
| Total CPU (requests) | 15m | Unknown (not in config) |
| Storage Dependencies | None (S3 only) | PVC + ephemeral storage |
| Deployment Strategy | Recreate | Recreate |
| Node Affinity | None | Preferred (minisforum > lenovo-tiny) |

### Operational Risk

**pbx-web:** **LOW** — highly stable, no failures, lightweight resources  
**whisper-stt:** **MEDIUM** — PVC issues, pod evictions, higher deployment churn

---

## Recommendations

### Immediate Actions (whisper-stt)

1. **Fix the ContainerStatusUnknown pod:**
   ```bash
   kubectl --server=http://traefik-ardenone-cluster:8001 delete pod whisper-openai-6885fc878b-jjm5j -n whisper-stt
   ```
   This should release the PVC attachment and allow the Deployment to recreate it cleanly.

2. **Add resource requests to whisper-stt pods:**
   ```yaml
   resources:
     requests:
       memory: "512Mi"
       cpu: "100m"
       ephemeral-storage: "2Gi"
     limits:
       memory: "2Gi"
       cpu: "1000m"
       ephemeral-storage: "4Gi"
   ```
   This will prevent scheduling on nodes with insufficient capacity.

3. **Review PVC mount configuration:**
   The recurring `FailedMount` errors suggest a storage class or volume template issue. Consider checking the StorageClass and PVC reclaim policy.

### Longer-term Improvements

1. **Consider RollingUpdate strategy** for both services to enable zero-downtime deployments (currently using Recreate).

2. **Add pod anti-affinity** for pbx-web to spread across nodes:
   ```yaml
   affinity:
     podAntiAffinity:
       preferredDuringSchedulingIgnoredDuringExecution:
       - weight: 100
         podAffinityTerm:
           labelSelector: { matchLabels: { app: pbx-web } }
           topologyKey: kubernetes.io/hostname
   ```

3. **Implement node selectors for whisper-stt** to prefer nodes with higher ephemeral-storage capacity.

4. **Investigate the rapid-fire deployments** on whisper-stt (e.g., 3 deployments in 7 minutes on 2026-07-08) to determine if these are intentional or caused by a config-drift loop.

---

## Conclusion

pbx-web demonstrates **excellent deployment stability** over the 30-day analysis period with zero failures and minimal deployment churn. whisper-stt shows **moderate stability issues** primarily related to storage management (PVC mount failures and pod evictions), but maintains service availability through redundant pods.

The higher deployment frequency for whisper-stt (10 vs 4 deployments) is not inherently problematic but correlates with the operational issues observed. Both services would benefit from more explicit resource declarations and rollout strategy refinements.

**Overall Assessment:** pbx-web is production-stable; whisper-stt requires storage-related remediation to reach equivalent stability.

---

## Data Sources

- ArgoCD API (argocd-ro-ardenone-manager-ts)
- ardenone-cluster kubectl queries (pods, deployments, replicasets, events, nodes)
- iad-ci Argo Workflows (workflowtemplates, workflow runs)
- declarative-config repository (k8s/ardenone-cluster/pbx-web, whisper-stt)
- Pod logs (pbx-web site-generator, whisper-stt)

**Analysis Methodology:** Retrospective analysis of Kubernetes API objects, ArgoCD sync history, and CI/CD workflow records over the 30-day window. No real-time monitoring or external APM data was used.
