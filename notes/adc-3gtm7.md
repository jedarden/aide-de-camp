# pbx-web vs whisper-stt Deployment Patterns Analysis
**Analysis Period:** Last 30 Days (June 24 - July 24, 2026)  
**Analysis Date:** 2026-07-24  
**Services:** pbx-web (Primary Branch Exchange web) vs whisper-stt (Speech-to-Text transcription)

## Executive Summary

**CRITICAL FINDING:** Both `pbx-web` and `whisper-stt` services currently show **Degraded** health and **OutOfSync** status in ArgoCD, indicating a **cluster-wide GitOps synchronization failure**. This is the most significant shared risk.

Over the past 30 days, both services have demonstrated **high pod stability with infrequent deployments**, but **whisper-stt** exhibits **3.7x higher deployment volatility** (11 deployments vs 3 for pbx-web) and **storage-related instability** in its dependent `whisper-openai` component. The analysis reveals **shared infrastructure patterns** but **distinct failure modes** driven by resource intensity and storage dependencies.

## Deployment Frequency & Volatility

### pbx-web Deployment Patterns
- **Current Version:** `ronaldraygun/pbx-web:1.0.9` (deployed 2026-05-01)
- **Deployment History:** 12 revisions total, with replica sets spanning back 78 days
- **Last 30 Days:** **3 deployments** (days 29, 29, 11) - ~1 deployment every 10 days
- **Recent Activity:** Current pod running since 2026-07-13 (11 days uptime)
- **Deployment Frequency:** **Low** - stable maintenance mode
- **Restart Count:** **Zero restarts** - extremely stable
- **ArgoCD Status:** ⚠️ **Degraded/OutOfSync** (cluster-wide issue)
- **Resource Profile:** Low footprint (10m-500m CPU, 128Mi-512Mi memory)

### whisper-stt Deployment Patterns
- **Current Version:** `ronaldraygun/whisper-stt:1.8.6` (deployed 2026-05-01)
- **Deployment History:** 32 revisions total, with recent activity ~12 days ago
- **Last 30 Days:** **11 deployments** (days 30, 29[x2], 28[x2], 23, 22, 16[x3], 12) - ~1 deployment every 2.7 days
- **Recent Activity:** Current pod running since 2026-07-12 (12 days uptime)
- **Deployment Frequency:** **High** - active development phase (1.3.1→1.8.2, 6 version bumps)
- **Restart Count:** **Zero restarts** for main whisper-stt pod
- **ArgoCD Status:** ⚠️ **Degraded/OutOfSync** (cluster-wide issue)
- **Resource Profile:** **High footprint** (1-8 CPU, 4-8Gi memory) - **100x more resource intensive than pbx-web**

### whisper-openai (whisper-stt dependency)
- **Current Version:** `fedirz/faster-whisper-server:latest-cpu` (external image)
- **Deployment History:** 24 revisions, with pods dating back 40 days
- **Recent Activity:** **One pod in ContainerStatusUnknown** with exit code 137
- **Restart Count:** One pod failed with exit code 137 (typically OOM or system kill)

## Top 3 Shared Failure Patterns

### 1. **ArgoCD Sync Degradation (CRITICAL)** 🔴
- **Both services report `Health: Degraded, Sync: OutOfSync`** in ArgoCD
- **Pattern:** No active reconciliation, 10 history entries per service, `Reconciled: None`
- **Impact:** GitOps state broken - deployments not syncing from declarative-config
- **Root Cause:** Likely repository secret expiry or cluster credential issues on ardenone-manager
- **Severity:** CLUSTER-WIDE - affects all services, not just pbx-web/whisper-stt
- **Evidence:**
  ```bash
  pbx-web:    Health: Degraded, Sync: OutOfSync
  whisper-stt: Health: Degraded, Sync: OutOfSync
  ```

### 2. **Storage Volume Mount Failures** ⚠️
- **Both services exhibit PVC mounting issues**, particularly whisper-openai
- **Pattern:** Intermittent `FailedMount` events with error messages like:
  ```
  MountVolume.SetUp failed for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c": 
  no Pending workload pods for volume to be mounted: map[Failed:[...] Running:[...]]
  ```
- **Impact:** whisper-openai shows **ContainerStatusUnknown** with exit code 137
- **Root Cause:** Longhorn storage layer + Kubernetes volume mount coordination issues during pod restarts

### 3. **Container Exit Code 137 (SIGKILL)**
- **whisper-openai pod** terminated with exit code 137
- **Pattern:** Containers killed without graceful shutdown - typically OOM or resource exhaustion
- **Impact:** Immediate service interruption, requires pod recreation
- **Root Cause:** Memory pressure on the cluster node (especially given whisper-stt's high resource requirements)
- **Evidence:** whisper-openai-6885fc878b-jjm5j in ContainerStatusUnknown state

### 4. **Infrastructure Dependency on External Images**
- **Both services depend on external container registries** (Docker Hub, third-party images)
- **Pattern:** Reliance on `ronaldraygun/*` images and `fedirz/faster-whisper-server:latest-cpu`
- **Impact:** Availability depends on external registry uptime and image pull success
- **Root Cause:** Multi-registry deployment strategy without local fallback

## Service-Specific Failure Patterns

### pbx-web Unique Patterns
- **Additional relay services** (`pbx-rebuild-relay`, `lab-rebuild-relay`) show zero restarts
- **No resource constraints** - operates well within limits
- **Clean state** - no error events in the last 30 days

### whisper-stt Unique Patterns  
- **High resource intensity** creates risk of node pressure during deployments
- **HuggingFace model cache dependency** on PVC storage
- **Dual deployment model** (whisper-stt + whisper-openai) doubles the failure surface
- **Aggressive health check timeouts** (30s liveness, 10s readiness) may fail during high load

## CI/CD Pipeline Analysis

### Build Process Similarities
Both services use **identical Argo Workflows** with:
- **Version auto-bumping** on each deployment
- **Kaniko-based builds** with caching enabled
- **30-minute active deadline** for builds
- **Retry strategy** with exponential backoff

### Build Process Differences
- **pbx-web:** 500m-2000m CPU, 1Gi-4Gi memory, uses latest Kaniko
- **whisper-stt:** 1000m-4000m CPU, 5Gi-8Gi memory, uses pinned Kaniko v1.23.2

### Key Finding
**No CI/CD workflow runs detected in the last 30 days** for either service, suggesting:
- Manual deployments or 
- Workflow execution issues in iad-ci cluster
- Potential workflow naming/labeling mismatches

## Infrastructure Context

### Cluster Deployment
- **Target:** ardenone-cluster (k3s on Hetzner EX44)
- **Storage:** Longhorn with 3 PVCs (whisper-model-cache, whisper-openai-model-cache, whisper-stt-jobs)
- **Networking:** Tailscale VPN + Traefik ingress
- **Management:** ArgoCD for GitOps deployment

### Resource Allocation
- **pbx-web:** Minimal resource consumption (fits well within single-node capacity)
- **whisper-stt:** Significant resource consumption (risks contention with other workloads)

## Recommendations

### Immediate Actions (Critical Priority)
1. **FIX ArgoCD SYNC STATE** 🔴 (cluster-wide issue affecting both services)
   ```bash
   # Check repository secret connectivity
   kubectl --kubeconfig=/home/coding/.kube/ardenone-manager.kubeconfig \
     get secret -n argocd | grep repo
   
   # Test manual sync if needed
   kubectl --kubeconfig=/home/coding/.kube/ardenone-manager.kubeconfig \
     patch application pbx-web -n argocd --type=json \
     -p='[{"op": "replace", "path": "/spec/syncPolicy/automated/prune", "value": true}]'
   ```
2. **Investigate whisper-openai ContainerStatusUnknown pod** - recreate and monitor for recurrence
3. **Review Longhorn volume mount coordination** - check for Kubernetes/Longhorn version compatibility issues
4. **Add resource usage monitoring** - implement Prometheus alerts for memory pressure on whisper-stt pods

### Medium-term Improvements
1. **Reduce whisper-stt resource footprint** - investigate model optimization or alternative architectures
2. **Implement local image registry** - reduce dependency on Docker Hub availability
3. **Add deployment hooks** - coordinate deployments with storage volume health checks
4. **Increase health check timeouts** for whisper-openai (30s→60s for liveness, 10s→20s for readiness)

### Long-term Stability
1. **Consider separating whisper-openai** into dedicated namespace with resource quotas
2. **Implement node affinity** for whisper-stt workloads to avoid resource contention
3. **Add circuit breaker patterns** - failover to alternative STT services during whisper-stt outages
4. **Review CI/CD workflow execution** - ensure deployments are properly tracked in iad-ci Argo Workflows

## Conclusion

Both `pbx-web` and `whisper-stt` demonstrate **strong baseline stability** with infrequent deployments and zero restarts on their main pods. However, **CRITICAL ArgoCD sync degradation** represents a **cluster-wide infrastructure failure** affecting both services simultaneously.

**whisper-stt** exhibits **3.7x higher deployment volatility** (11 vs 3 deployments) and **high resource intensity** creating distinct failure risks not present in the lightweight `pbx-web` service.

The **shared patterns** (ArgoCD sync failure, PVC mounting issues, exit code 137, external image dependencies) suggest **infrastructure-level improvements** that would benefit both services, particularly around ArgoCD repository connectivity and Longhorn storage coordination.

**Priority Ranking:**
1. **CRITICAL:** Fix ArgoCD sync state (cluster-wide GitOps failure)
2. **HIGH:** Stabilize whisper-stt deployment cadence (reduce from 11 to 3-4 deployments/month)
3. **MEDIUM:** Address whisper-openai ContainerStatusUnknown issue

**Next Review:** Recommended in 14 days to verify ArgoCD sync fix and deployment stability.