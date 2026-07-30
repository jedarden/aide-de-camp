# Deployment Analysis Report: pbx-web vs whisper-stt
**Date:** 2026-07-24  
**Analysis Period:** 2026-06-24 to 2026-07-24 (30 days)  
**Cluster:** ardenone-cluster  
**Analyst:** Claude (aide-de-camp)

---

## Executive Summary

Comparative analysis of `pbx-web` and `whisper-stt` deployment patterns over a 30-day period reveals **significant stability disparities**. The `pbx-web` namespace demonstrates operational excellence with zero failures, while `whisper-stt` exhibits recurring PVC mounting issues and container termination problems.

**Key Finding:** `whisper-stt` experiences **continuous PVC mounting failures** recurring every 2-3 minutes for 6+ days, with a container terminated via SIGKILL (exit code 137).

---

## Service Overview

### pbx-web
- **Deployments:** 3 (lab-rebuild-relay, pbx-rebuild-relay, pbx-web)
- **Strategy:** Recreate
- **Total Pods:** 3 running
- **Resource Profile:** Minimal CPU (1-6m), Low Memory (18-73Mi)
- **Stability:** Excellent - no failures observed

### whisper-stt  
- **Deployments:** 2 (whisper-openai, whisper-stt)
- **Strategy:** RollingUpdate
- **Total Pods:** 2 running, 1 failed
- **Resource Profile:** Low CPU (1-5m), High Memory (2.8-5.6Gi)
- **Stability:** Poor - recurring failures

---

## Failure Patterns Identified

### Pattern 1: PVC Mounting Failure (whisper-stt Only)

**Severity:** CRITICAL  
**Frequency:** Every 2-3 minutes continuously  
**Duration:** 6+ days (4,855+ occurrences)  
**Affected Resource:** whisper-openai-68966786fb-jsb5d

**Event Details:**
```
Warning  FailedMount  pod/whisper-openai-68966786fb-jsb5d  
MountVolume.SetUp failed for volume "pvc-d5891df2-b37f-4043-96a1-7098e218378c"
rpc error: code = Aborted desc = no Pending workload pods for volume
map[Failed:[whisper-openai-6885fc878b-jjm5j] Running:[whisper-openai-68966786fb-jsb5d]]
```

**Analysis:**
- Volume attachment conflict between pods
- One pod (whisper-openai-6885fc878b-jjm5j) in failed state blocks volume detachment
- Active pod (whisper-openai-68966786fb-jsb5d) cannot mount the same PVC
- PVC: whisper-openai-model-cache (10Gi, Longhorn backend)

**Impact:**
- Pod unable to fully start/recover
- Potential data access issues
- Continuous warning noise obscures other issues

---

### Pattern 2: Container Termination via SIGKILL (whisper-stt Only)

**Severity:** HIGH  
**Exit Code:** 137 (SIGKILL - force termination)  
**Affected Pod:** whisper-openai-6885fc878b-jjm5j  
**State:** ContainerStatusUnknown

**Pod Details:**
```
Name: whisper-openai-6885fc878b-jjm5j
Status: ContainerStatusUnknown
Exit Code: 137
Reason: "The container could not be located when the pod was terminated"
Age: 40 days (orphaned)
```

**Analysis:**
- Exit code 137 typically indicates **OOM kill** or manual SIGKILL
- Pod left in indeterminate state
- Blocks PVC detachment (see Pattern 1)
- No restarts observed

**Likely Causes:**
1. Memory exhaustion (whisper-stt uses 40-80x more memory than pbx-web)
2. Manual intervention to kill stuck process
3. Node eviction or resource pressure

---

### Pattern 3: Resource Usage Asymmetry

**Observation:** Massive memory footprint difference between services

| Metric | pbx-web | whisper-stt | Ratio |
|--------|---------|-------------|-------|
| Memory Range | 18-73 Mi | 2.8-5.6 Gi | 40-80x |
| CPU Range | 1-6m | 1-5m | Similar |
| Pods | 3 | 2 | - |

**Analysis:**
- whisper-stt memory-intensive (ML model loading)
- pbx-web lightweight (web serving)
- whisper-stt at higher risk of memory pressure events

---

### Pattern 4: Deployment Stability

**pbx-web:** Model of stability
- Zero restarts across all pods
- Zero warning events in 30-day window
- All pods running 6-11 days continuously
- Recreate strategy prevents conflicts

**whisper-stt:** Operational churn
- 1 failed pod with 40-day age (zombie)
- Recurring PVC mount failures
- Multiple replica sets created (deployment instability)
- RollingUpdate strategy exposes volume conflicts

---

## Cluster Infrastructure

**Cluster:** ardenone-cluster  
**Nodes:** 7 nodes (1 control-plane, 6 agents)  
**Storage:** Longhorn (distributed block storage)  
**Kubernetes Version:** v1.33.6+k3s1 / v1.34.3+k3s1

**Node Distribution:**
- whisper-stt pods spread across: k3s-lenovo-tiny, k3s-agent-minisforum
- pbx-web pods on: k3s-agent-minisforum, k3s-server-a
- No node-specific failures observed

---

## Comparison Summary

| Aspect | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Stability** | Excellent (0 failures) | Poor (1 failed, recurring issues) |
| **Restarts** | 0 | 0 (but 1 SIGKILL) |
| **Warning Events** | 0 | 4,855+ |
| **PVC Issues** | 0 | 1 critical |
| **Memory Usage** | 18-73 Mi | 2.8-5.6 Gi |
| **Deployment Churn** | Low | Medium |
| **Pod Age Range** | 6-11 days | 12-40 days |
| **Failed Pods** | 0 | 1 |

---

## Root Cause Analysis

### Primary Issue: PVC Attachment Orphan State

**Root Cause:** The whisper-openai-6885fc878b-jjm5j pod was SIGKILLed (likely OOM) but Kubernetes could not properly clean up its volume attachments, leaving the PVC in an orphaned state.

**Why This Happens:**
1. Pod killed suddenly (137) → no graceful shutdown
2. Volume detachment attempted → fails because container already gone
3. New pod tries to mount same PVC → blocked by orphaned attachment
4. Retry loop every 2-3 minutes → 4,855+ warnings

**Why whisper-stt Not pbx-web:**
- whisper-stt uses heavy PVC-backed storage for models (10Gi each)
- pbx-web uses no PVCs (ephemeral storage only)
- Memory pressure affects whisper-stt more (5+ Gi vs 73 Mi)

---

## Recommendations

### Immediate Actions (Priority 1)

1. **Delete Orphaned Pod**
   ```bash
   kubectl --server=http://traefik-ardenone-cluster:8001 delete pod whisper-openai-6885fc878b-jjm5j -n whisper-stt --force --grace-period=0
   ```
   - Removes volume attachment blocker
   - Allows PVC cleanup

2. **Verify PVC Cleanup**
   ```bash
   kubectl --server=http://traefik-ardenone-cluster:8001 get pvc -n whisper-stt
   kubectl --server=http://traefik-ardenone-cluster:8001 describe pvc whisper-openai-model-cache -n whisper-stt
   ```
   - Confirm volume detached properly

3. **Restart Affected Pod**
   ```bash
   kubectl --server=http://traefik-ardenone-cluster:8001 rollout restart deployment whisper-openai -n whisper-stt
   ```
   - Should clear PVC mount errors

### Medium-term Actions (Priority 2)

4. **Add Resource Limits**
   - whisper-stt pods need explicit memory limits
   - Prevents OOM → graceful shutdown instead of SIGKILL
   - Consider Horizontal Pod Autoscaler for memory scaling

5. **Implement Pod Disruption Budgets**
   - Prevents orphaned state during voluntary disruptions
   - Ensures graceful volume cleanup

6. **Add Liveness/Readiness Probes**
   - Detect stuck pods earlier
   - Auto-restart instead of manual intervention

### Long-term Actions (Priority 3)

7. **Review Storage Backend**
   - Evaluate Longhorn attachment handling
   - Consider multi-attach RWX volumes if model sharing needed

8. **Observability Enhancements**
   - Alert on PVC mount failures (after 3 consecutive failures)
   - Monitor memory usage trends for whisper-stt
   - Track pod exit code 137 as critical alert

9. **Architecture Review**
   - Consider separating model loading from serving (sidecar pattern)
   - Evaluate if 10Gi model cache PVCs are necessary for both deployments

---

## Appendix: Data Collection Methods

### Tools Used
- kubectl (via read-only proxy on ardenone-cluster)
- ArgoCD read-only API
- Direct pod inspection
- Events history analysis

### Queries Executed
```bash
# Pod enumeration
kubectl get pods -n {pbx-web,whisper-stt} -o wide

# Detailed status
kubectl get pods -n {namespace} -o json

# Events history
kubectl get events -n {namespace} --sort-by='.lastTimestamp' --field-selector type=Warning

# Resource usage
kubectl top pod -n {namespace}

# Replica set history
kubectl get replicasets -n {namespace} -o custom-columns="..."

# PVC inspection
kubectl get pvc -n whisper-stt
kubectl describe pvc -n whisper-stt {pvc-name}
```

### Time Window
- Analysis focused on 2024-06-24 to 2024-07-24 (last 30 days)
- Historical pod ages used as indicators of deployment longevity
- Event timestamps verified for recency

---

## Conclusion

**pbx-web** operates as a model of stability with zero failures over the 30-day analysis period. **whisper-stt** suffers from a critical PVC attachment orphan state caused by a SIGKILLed pod, resulting in 4,855+ recurring mount failures.

**Single Point of Failure:** The orphaned whisper-openai-6885fc878b-jjm5j pod blocks PVC detachment, creating a continuous retry loop that prevents proper volume management.

**Recommended Path Forward:** Delete the orphaned pod (Priority 1) → verify PVC cleanup → restart deployment → implement resource limits and monitoring to prevent recurrence.

---

**Report Generated:** 2026-07-24  
**Analysis Duration:** 30 days (2026-06-24 to 2026-07-24)  
**Next Review Date:** 2026-08-24 (recommended quarterly)
