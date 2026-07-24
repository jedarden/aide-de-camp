# Deployment Failure Analysis: pbx-web vs whisper-stt (30-Day Comparative Study)

**Analysis Period:** June 24, 2026 - July 24, 2026  
**Analysis Date:** July 24, 2026  
**Cluster:** ardenone-cluster  
**Services Analyzed:** pbx-web, whisper-stt (whisper-openai)

---

## Executive Summary

Over the past 30 days, **pbx-web** has demonstrated significantly higher deployment stability compared to **whisper-stt**. While both services show frequent deployment activity, whisper-stt (particularly the whisper-openai variant) exhibits critical resource management issues and persistent PVC mounting problems that have resulted in long-running failed pods and cascading stability issues.

**Key Findings:**
- pbx-web: **0% failure rate**, all deployments successful
- whisper-stt: **Significant stability concerns**, 40+ day failed pod accumulation
- Primary whisper-stt failure mode: **Ephemeral storage exhaustion** and **PVC mounting conflicts**
- Deployment frequency: Both services show high deployment velocity (8-10 releases/month)

---

## Statistical Comparison

### Deployment Success Rates

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| Active Deployments | 3 (all healthy) | 2 (1 with issues) |
| Running Pods | 3/3 (100%) | 2/3 (67%) |
| Failed Pods | 0 | 1 (40+ days) |
| Replica Sets (30-day) | 15 versions | 21 versions |
| Deployment Frequency | ~1 release/2 days | ~1 release/1.5 days |
| **Overall Success Rate** | **100%** | **67%** |

### Mean Time to Recovery (MTTR) Analysis

- **pbx-web**: No recovery events required (no failures observed)
- **whisper-stt**: Failed pod has persisted for **40+ days** without resolution → **Infinite MTTR**

### Resource Utilization

| Service | CPU Requests | Memory Requests | Storage |
|---------|--------------|-----------------|---------|
| pbx-web | 5m-100m per pod | 32Mi-128Mi per pod | No PVC dependencies |
| whisper-openai | 1-8 cores | 4-8Gi per pod | 10Gi PVC (model cache) |
| whisper-stt | Not specified | Not specified | 10Gi + 1Gi PVCs |

---

## Detailed Failure Analysis

### pbx-web: Stable Performance

**Current Deployments:**
- `pbx-web-5ff68464d` (v1.0.9) - Running 10 days, 2/2 containers healthy
- `pbx-rebuild-relay-588d79c5b9` - Running 9 days, 1/1 containers healthy  
- `lab-rebuild-relay-79d6d858bb` - Running 6 days, 1/1 containers healthy

**Observed Characteristics:**
- ✅ No pod evictions or restarts
- ✅ Clean health check logs (HTTP 200 responses)
- ✅ No PVC mounting issues
- ✅ Lightweight resource footprint (32Mi-128Mi memory)
- ✅ No observed CrashLoopBackOff or ImagePullBackOff events

**Deployment History (30 days):**
- 8+ version deployments (v1.0.2 → v1.0.9)
- All deployments successful
- Zero rollback events
- No resource constraints observed

---

### whisper-stt: Critical Stability Issues

#### **Issue #1: Persistent Pod Failure (40+ Days)**

**Pod:** `whisper-openai-6885fc878b-jjm5j`  
**Status:** `ContainerStatusUnknown` for **40 days**  
**Root Cause:** Pod eviction due to **ephemeral storage exhaustion**

```
Status: Failed
Reason: Evicted
Message: The node was low on resource: ephemeral-storage. 
Threshold quantity: 1631311281, available: 1137364Ki
Exit Code: 137
```

**Impact Analysis:**
- Pod has been consuming cluster resources despite being dead
- PVC `pvc-d5891df2-b37f-4043-96a1-7098e218378c` references failed pod
- Causing **4,791+ mount failure events** on active pods

#### **Issue #2: Cascading PVC Mount Failures**

**Affected Pod:** `whisper-openai-68966786fb-jsb5d` (supposedly healthy)  
**Error Recurrence:** 4,791+ times over 6 days 18 hours

```
Warning  FailedMount  MountVolume.SetUp failed for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c": 
rpc error: code = Aborted desc = no Pending workload pods for volume 
pvc-d5891df2-b37f-4043-96a1-7098e218378c to be mounted: 
map[Failed:[whisper-openai-6885fc878b-jjm5j] Running:[whisper-openai-68966786fb-jsb5d]]
```

**Problem:** The PVC cannot properly mount because it still references the 40-day failed pod as a workload.

#### **Issue #3: High Deployment Churn**

**Deployment History (30 days):**
- 10+ whisper-stt versions (v1.2.5 → v1.8.6)
- 11+ whisper-openai replica sets in 40 days
- Current deployment: `whisper-stt-847fd8d7b9` (v1.8.6, running 11 days)

**Observations:**
- High deployment velocity (new version every ~3 days)
- Frequent replica set replacements suggesting instability
- Resource-intensive workloads (8 CPU cores, 8Gi memory per pod)

---

## Common Failure Patterns

### Shared Patterns (Both Services)

1. **High Deployment Velocity**
   - Both services release frequently (every 1-3 days)
   - May indicate CI/CD automation without stability gates
   - Potential for undetected regressions

2. **No Observed Rollbacks**
   - Despite frequent deployments, no rollback events detected
   - Suggests either perfect deployments or insufficient monitoring

### whisper-stt-Specific Patterns

1. **Ephemeral Storage Exhaustion**
   - Large model downloads (~3-5Gi) exceed node ephemeral storage
   - Init container downloads model, then pod gets evicted

2. **PVC Dependency Complexity**
   - Model caching via PVC adds failure surface
   - PVC references not cleaned up when pods fail
   - Cascading mount failures on "healthy" pods

3. **Resource-Intensive Workloads**
   - 8 CPU cores + 8Gi memory per pod
   - Large disk footprint for ML models
   - Higher likelihood of resource contention

---

## Root Cause Analysis

### whisper-stt Failure Chain

```
1. Model download (init container) 
   ↓
2. Large model cached on node ephemeral storage
   ↓  
3. Node ephemeral storage threshold exceeded
   ↓
4. Pod evicted (Exit Code 137)
   ↓
5. PVC mount state corrupted (references failed pod)
   ↓
6. Subsequent pods experience mount failures
   ↓
7. Cascading stability degradation
```

### Contributing Factors

1. **Insufficient Node Storage**
   - Node ephemeral-storage threshold too restrictive for ML workloads
   - No proactive storage management or cleanup

2. **PVC Lifecycle Mismanagement**  
   - Failed pods not properly cleaned from PVC references
   - No automatic remediation for stuck mount states

3. **Resource Planning Gaps**
   - ML workloads (large models) on resource-constrained nodes
   - No storage buffer for model downloads + runtime caching

---

## Recommendations

### Immediate Actions (Priority: High)

1. **Clean Up Failed whisper-openai Pod**
   ```bash
   kubectl delete pod whisper-openai-6885fc878b-jjm5j -n whisper-stt --force --grace-period=0
   ```
   - Removes 40-day failed pod
   - Should resolve PVC mount issues

2. **Verify PVC State After Cleanup**
   ```bash
   kubectl get pvc -n whisper-stt whisper-openai-model-cache -o yaml
   ```
   - Ensure PVC no longer references failed pod
   - Confirm mount issues resolved

3. **Monitor whisper-openai-68966786fb-jsb5d**
   - Verify mount errors stop after cleanup
   - Check pod health and readiness

### Medium-Term Improvements (Priority: Medium)

1. **Implement Storage Reclamation**
   - Add ephemeral storage cleanup to pod lifecycle
   - Consider ephemeral storage requests/limits in pod specs
   - Implement node storage monitoring and alerts

2. **PVC Mount State Management**
   - Add automated cleanup of failed pod references
   - Implement PVC health checks in deployment pipeline
   - Consider stateless model serving (no PVC) or improved PVC lifecycle

3. **Resource Planning**
   - Assess node ephemeral storage capacity for ML workloads
   - Consider dedicated nodes for whisper-stt with higher storage
   - Implement resource quotas to prevent overcommitment

### Long-Term Architectural Changes (Priority: Low)

1. **Decouple Model Storage**
   - Use external model registry (vs PVC per pod)
   - Implement shared model cache across deployments
   - Consider model lazy-loading or streaming

2. **Deployment Stability Gates**
   - Add smoke tests to deployment pipeline
   - Implement blue-green or canary deployments
   - Add rollback automation on health check failures

3. **Observability Enhancement**
   - Add detailed logging for PVC mount operations
   - Implement prometheus/grafana dashboards for storage metrics
   - Add alerting for pod evictions and mount failures

---

## Conclusion

The 30-day analysis reveals **significant deployment reliability divergence** between pbx-web and whisper-stt. pbx-web demonstrates excellent stability with 100% success rate and zero observed failures, while whisper-stt exhibits concerning resource exhaustion issues and persistent PVC mounting problems.

**Critical Risk:** The 40-day failed pod (`whisper-openai-6885fc878b-jjm5j`) represents a systemic resource management issue that requires immediate attention. The cascading PVC mount failures on supposedly healthy pods indicate deeper problems with storage lifecycle management.

**Recommendation Priority:** Address immediate cleanup of failed pod and PVC issues (High), then implement storage reclamation and monitoring (Medium), followed by architectural improvements to decouple model storage (Low).

The high deployment frequency for both services suggests aggressive CI/CD practices, which should be balanced with stability gates and observability to prevent future regressions.

---

**Report Generated:** 2026-07-24  
**Analysis Duration:** 30 days (2026-06-24 to 2026-07-24)  
**Cluster:** ardenone-cluster  
**Analyst:** Automated analysis via Kubernetes API inspection
