# 30-Day Deployment Analysis: pbx-web vs whisper-stt

**Analysis Period:** 2026-07-07 to 2026-08-06 (30 days)
**Cluster:** ardenone-cluster
**Generated:** 2026-08-06

---

## Executive Summary

Both `pbx-web` and `whisper-stt` services demonstrated **exceptional stability** over the 30-day analysis period with **zero pod restarts**, **no deployment failures**, and **no error events**. However, the analysis reveals a **stagnation pattern**: neither service has triggered CI/CD builds in over 30 days, suggesting manual deployments or image pinning that may introduce operational risk.

**Key Finding:** The services are stable but operationally stagnant. Recent deployments occurred without triggering CI workflows, indicating a gap in the automated deployment pipeline.

---

## Statistical Summary

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Current Image** | ronaldraygun/pbx-web:1.0.9 | ronaldraygun/whisper-stt:1.8.6 |
| **Last Deployment** | 2026-07-28 | 2026-07-12 |
| **Deployment Strategy** | Recreate | Recreate |
| **ReplicaSets (30d)** | 3 | 1 |
| **Current Pod Age** | 9 days | 25 days |
| **Pod Restarts** | 0 | 0 |
| **CI/CD Builds (30d)** | 0 | 0 |
| **Deployment Failures** | 0 | 0 |
| **Probe Failures** | 0 | 0 |
| **Error Events** | 0 | 0 |

---

## Deployment Timeline

### pbx-web Activity
```
2026-07-28 17:05 UTC - New ReplicaSet (pbx-web-765bb76db8) - 0/0 replicas
2026-07-27 17:56 UTC - lab-rebuild-relay deployment (relay service)
2026-07-15 03:24 UTC - pbx-rebuild-relay deployment (relay service)
2026-07-13 18:18 UTC - New ReplicaSet (pbx-web-5ff68464d) - 1/1 replicas (active)
2026-07-13 18:07 UTC - Previous ReplicaSet (pbx-web-754f4cfdf7) - 0/0 replicas
```

**Pattern:** Multiple deployments in mid-July, with the most recent on July 28. The July 13 deployment created the currently active pod (9 days old).

### whisper-stt Activity
```
2026-07-12 16:53 UTC - New ReplicaSet (whisper-stt-847fd8d7b9) - 1/1 replicas (active)
2026-07-08 03:26 UTC - Previous ReplicaSet (whisper-stt-6c497489fb) - 0/0 replicas
2026-07-08 03:16 UTC - Previous ReplicaSet (whisper-stt-5b8558f478) - 0/0 replicas
2026-07-08 03:09 UTC - Previous ReplicaSet (whisper-stt-5dbff75cbd) - 0/0 replicas
```

**Pattern:** Rapid successive deployments on July 8, followed by a stable deployment on July 12. The current pod has been running for 25 days without interruption.

---

## Common Failure Patterns

### ✅ No Observed Failures

Over the 30-day period, **no failure patterns were observed** for either service:

- **Zero pod restarts** across all containers
- **No probe failures** (liveness/readiness probes all healthy)
- **No error events** in kubernetes event logs
- **No deployment rollbacks** or progressive failures
- **No resource exhaustion** events

### Identified Stability Factors

**1. Recreate Strategy (Both Services)**
- Both deployments use `strategy: Recreate` instead of RollingUpdate
- This eliminates rollout-related issues (e.g., two versions running simultaneously)
- Trade-off: Brief service interruption during deployments

**2. Proper Probe Configuration**
- **pbx-web:** 5s readiness initial delay, 10s liveness initial delay
- **whisper-stt:** 60s readiness initial delay, 120s liveness initial delay
- Both services have appropriate probe delays to prevent premature termination during startup

**3. Resource Allocation**
- Both services have non-trivial resource requests/limits configured
- Prevents resource starvation and OOM kills

**4. Node Affinity (whisper-stt only)**
- whisper-stt uses node affinity to prefer high-CPU nodes (minisforum, lenovo-tiny)
- Ensures the service runs on hardware capable of handling ML inference workloads
- pbx-web lacks affinity but still landed on minisforum (scheduler decision)

---

## Divergences

### Resource Profile

| Aspect | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Container Count** | 2 (site-generator + nginx) | 1 (whisper-stt) |
| **Memory Request** | 128Mi (site-gen) + 32Mi (nginx) | 4Gi |
| **Memory Limit** | 512Mi (site-gen) + 128Mi (nginx) | 8Gi |
| **CPU Request** | 10m (site-gen) + 5m (nginx) | 1000m |
| **CPU Limit** | 500m (site-gen) + 100m (nginx) | 8000m |
| **Storage** | emptyDir for www/cache | PVC for model cache + jobs data |

**Analysis:** whisper-stt is a **resource-heavy ML service** (4-8x memory, 20-80x CPU) while pbx-web is a lightweight static site generator + reverse proxy.

### Startup Latency

| Service | Liveness Delay | Readiness Delay | Interpretation |
|---------|----------------|-----------------|----------------|
| pbx-web | 10s | 5s | Fast-starting web service |
| whisper-stt | 120s | 60s | Slow-starting ML service (model loading) |

**Analysis:** whisper-stt requires significantly longer startup time due to ML model loading from the PVC cache. The 120s liveness delay accommodates this cold start.

### Deployment Velocity

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Current Pod Age** | 9 days | 25 days |
| **Last Deployment** | July 28 | July 12 |
| **Deployment Cadence** | Higher (4 in July) | Lower (stabilized after July 12) |

**Analysis:** pbx-web has more frequent deployments, likely due to its role as a web frontend that receives more frequent updates. whisper-stt stabilizes for longer periods between deployments.

### Node Scheduling

| Service | Node Affinity | Current Node |
|--------|---------------|--------------|
| pbx-web | None (scheduler's choice) | k3s-agent-minisforum |
| whisper-stt | Prefers minisforum (w=100), lenovo-tiny (w=90) | k3s-agent-minisforum |

**Analysis:** whisper-stt's explicit affinity ensures it runs on high-CPU nodes suitable for ML workloads. pbx-web relies on the scheduler, which also selected minisforum (likely due to resource availability).

---

## CI/CD Pipeline Gap

### Critical Finding: No Workflow Activity

**Workflow Runs (Last 30 Days):**
- `pbx-web-build`: **0 runs**
- `whisper-stt-build`: **0 runs**

Despite deployments occurring within the 30-day window, **no Argo Workflow builds were triggered**. This indicates:

1. **Manual Deployments:** Deployments may have been performed manually (e.g., `kubectl apply` of image tag changes in declarative-config)
2. **Image Pinning:** Services may be pinned to specific image tags without triggering CI rebuilds
3. **Pipeline Gap:** The CI/CD automation may have a gap where image updates don't trigger workflow runs

**Risk:** Manual deployments bypass:
- Automated testing (fmt, clippy, unit tests)
- Image vulnerability scanning
- Deployment approval workflows
- Audit trail in Argo UI

---

## Infrastructure Context

### Cluster Node Capacity

```
NAME                   CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)   
k3s-agent-minisforum   912m         5%       29698Mi         46%         
k3s-lenovo-tiny        842m         7%       26971Mi         42%         
k3s-agent-a             364m         9%       6079Mi          38%         
k3s-agent-b             319m         7%       4021Mi          25%         
k3s-agent-c             333m         8%       5250Mi          32%         
k3s-agent-d             491m         12%      8534Mi          53%         
k3s-server-a            570m         14%      4819Mi          60%         
```

Both services currently run on `k3s-agent-minisforum`, which has **ample capacity** (5% CPU, 46% memory available). This explains the lack of resource-related failures.

---

## Root Cause Analysis

### Why Zero Failures?

1. **Recreate Strategy:** Eliminates rolling update complexity
2. **Proper Startup Delays:** Probes don't fire before services are ready
3. **Resource Headroom:** Both services run on nodes with significant spare capacity
4. **Image Stability:** Long-lived image pins (1.0.9, 1.8.6) reduce churn
5. **Single Replica:** No multi-replica scaling issues (pod anti-affinity, distributed state)

### Why CI/CD Stagnation?

**Hypothesis 1: Manual Tag Updates**
- Image tags in declarative-config may be updated manually without triggering builds
- ArgoCD syncs the tag change, triggering a Recreate rollout without CI involvement

**Hypothesis 2: Pre-built Images**
- Images may be built and pushed separately (e.g., manual `docker build && push`)
- Deployments consume pre-existing images rather than triggering builds

**Hypothesis 3: Workflow Template Mismatch**
- Workflow templates exist (`pbx-web-build`, `whisper-stt-build`) but may not be automatically triggered
- Deployments may happen via direct image tag updates in declarative-config

---

## Recommendations

### Operational Improvements

1. **Re-enable CI/CD Automation**
   - Investigate why workflow builds aren't triggering
   - Ensure image tag updates in declarative-config trigger Argo Workflow runs
   - Implement pre-deploy testing (fmt, clippy, unit tests)

2. **Consider Rolling Updates**
   - Evaluate switching from `Recreate` to `RollingUpdate` for pbx-web
   - This would eliminate the brief service interruption during deployments
   - whisper-stt may need to keep Recreate due to PVC mount constraints

3. **Add Health Check Metrics**
   - Implement `/health` endpoint metrics (response time, last deployment timestamp)
   - Add Prometheus scrape targets for both services
   - Enable alerting on probe failures (currently absent)

4. **Document Manual Deployment Process**
   - If manual deployments are intentional, document the procedure
   - Add a pre-flight checklist to the documentation
   - Consider adding a `--dry-run` validation step

### Risk Mitigation

1. **Image Scanning**
   - Implement Trivy/Grype scans in CI pipeline
   - Block deployment of images with high-severity vulnerabilities
   - Currently absent from manual deployments

2. **Deployment Validation**
   - Add post-deployment smoke tests to verify functionality
   - Implement automated rollback on health check failures
   - Currently no automated rollback mechanism

3. **Capacity Planning**
   - Monitor whisper-stt's resource usage as transcription load increases
   - Consider HPA (Horizontal Pod Autoscaler) if load becomes variable
   - Current single-replica design creates a single point of failure

---

## Conclusion

Both `pbx-web` and `whisper-stt` have demonstrated **exceptional operational stability** over the 30-day analysis period with **zero failures, zero restarts, and zero errors**. This stability is attributable to:

- Conservative deployment strategy (Recreate)
- Appropriate probe configuration
- Adequate resource allocation
- Sufficient node capacity

However, the **absence of CI/CD workflow activity** represents an operational gap that may introduce risk over time. Manual deployments bypass automated testing and validation, potentially allowing vulnerabilities or configuration errors to reach production.

**Overall Assessment:** Services are **stable but operationally stagnant**. Addressing the CI/CD gap should be the priority before considering other architectural changes.

---

## Artifacts

Raw kubernetes data exports:
- `/home/coding/aide-de-camp/research-data/adc-168pu/pbx-web-replicasets.json`
- `/home/coding/aide-de-camp/research-data/adc-168pu/whisper-stt-replicasets.json`
- `/home/coding/aide-de-camp/research-data/adc-168pu/pbx-web-pods.json`
- `/home/coding/aide-de-camp/research-data/adc-168pu/whisper-stt-pods.json`
- `/home/coding/aide-de-camp/research-data/adc-168pu/pbx-web-deployment.json`
- `/home/coding/aide-de-camp/research-data/adc-168pu/whisper-stt-deployment.json`
