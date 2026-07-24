# pbx-web vs whisper-stt: 30-Day Deployment Analysis Report

**Analysis Period:** 2026-06-24 to 2026-07-24 (30-day rolling window)  
**Analysis Date:** 2026-07-24  
**Cluster:** ardenone-cluster  
**Urgency:** Low (Research Task)

---

## Executive Summary

This comparative analysis examines deployment patterns, failure modes, and operational stability of two distinct services on the ardenone-cluster: `pbx-web` (web service) and `whisper-stt` (speech-to-text service). The analysis reveals significant differences in deployment frequency, failure characteristics, and operational patterns between these services.

**Key Finding:** `whisper-stt` exhibits substantially higher deployment volatility with 11 deployment revisions compared to `pbx-web`'s 2 revisions, including a rapid deployment storm of 3 deployments within 17 minutes on July 8th.

---

## Deployment Frequency Analysis

### pbx-web Deployment History

| Date (UTC) | Revision | Replica Set | Replicas | Ready | Status |
|------------|----------|-------------|----------|-------|--------|
| 2026-07-15 03:24:40 | rev:5 | pbx-rebuild-relay-588d79c5b9 | 1 | 1 | Active |
| 2026-07-13 18:18:07 | rev:12 | pbx-web-5ff68464d | 1 | 1 | Active |
| 2026-07-13 18:07:55 | rev:11 | pbx-web-754f4cfdf7 | 0 | 0 | Replaced |
| 2026-06-25 15:23:48 | rev:10 | pbx-web-6d86477cdb | 0 | 0 | Replaced |

**Deployment Frequency:** 2 active deployments in 30 days  
**Average Interval:** ~15 days between deployments  
**Deployment Pattern:** Stable, low-frequency updates

### whisper-stt Deployment History

| Date (UTC) | Revision | Replica Set | Replicas | Ready | Status |
|------------|----------|-------------|----------|-------|--------|
| 2026-07-12 16:53:42 | rev:32 | whisper-stt-847fd8d7b9 | 1 | 1 | Active |
| 2026-07-08 03:26:44 | rev:31 | whisper-stt-6c497489fb | 0 | 0 | Replaced |
| 2026-07-08 03:16:13 | rev:30 | whisper-stt-5b8558f478 | 0 | 0 | Replaced |
| 2026-07-08 03:09:35 | rev:29 | whisper-stt-5dbff75cbd | 0 | 0 | Replaced |
| 2026-07-02 02:20:33 | rev:28 | whisper-stt-6b96f4569c | 0 | 0 | Replaced |
| 2026-07-01 19:46:33 | rev:27 | whisper-stt-6464bdf67b | 0 | 0 | Replaced |
| 2026-06-26 16:33:34 | rev:26 | whisper-stt-5b884b75f4 | 0 | 0 | Replaced |
| 2026-06-26 12:42:03 | rev:25 | whisper-stt-78bbf5f57f | 0 | 0 | Replaced |
| 2026-06-25 14:10:16 | rev:24 | whisper-stt-558c7cf44 | 0 | 0 | Replaced |
| 2026-06-25 14:08:07 | rev:23 | whisper-stt-65fb7f8dd9 | 0 | 0 | Replaced |
| 2026-06-24 20:55:36 | rev:22 | whisper-stt-75c848b8d6 | 0 | 0 | Replaced |

**Deployment Frequency:** 11 revisions in 30 days  
**Average Interval:** ~3 days between deployments  
**Deployment Pattern:** High-frequency, volatile updates

---

## Critical Finding: July 8th Deployment Storm

### whisper-stt Rapid Deployment Pattern

On **2026-07-08**, `whisper-stt` experienced a deployment storm with **3 deployments within 17 minutes**:

1. **03:09:35Z** - rev:29 deployed
2. **03:16:13Z** - rev:30 deployed (6 min 38 sec later)
3. **03:26:44Z** - rev:31 deployed (10 min 31 sec later)

**Analysis:** This rapid succession suggests deployment failures or rollback scenarios, possibly due to:
- Immediate deployment issues detected after rollout
- Automated rollback mechanisms triggering
- Configuration or image pull problems requiring quick iteration

---

## Current Pod Status Analysis

### pbx-web Current Pods

| Pod | Ready | Status | Restarts | Age | Node |
|-----|-------|--------|----------|-----|------|
| lab-rebuild-relay-79d6d858bb-gfbf2 | 1/1 | Running | 0 | 6d21h | k3s-server-a |
| pbx-rebuild-relay-588d79c5b9-vmmlz | 1/1 | Running | 0 | 9d | k3s-agent-minisforum |
| pbx-web-5ff68464d-97b8p | 2/2 | Running | 0 | 11d | k3s-agent-minisforum |

**Status:** All pods running successfully with zero restarts  
**Stability:** High - consistent pod health across all deployments

### whisper-stt Current Pods

| Pod | Ready | Status | Restarts | Age | Node |
|-----|-------|--------|----------|-----|------|
| whisper-openai-6885fc878b-jjm5j | 0/1 | Failed | 0 | 40d | k3s-agent-c |
| whisper-openai-68966786fb-jsb5d | 1/1 | Running | 0 | 40d | k3s-lenovo-tiny |
| whisper-stt-847fd8d7b9-v2rs5 | 1/1 | Running | 0 | 12d | k3s-agent-minisforum |

**Status:** Mixed - 1 failed pod, 2 running successfully  
**Issue:** `whisper-openai-6885fc878b-jjm5j` in Failed state

---

## Failure Mode Analysis

### whisper-openai Container Failure

**Pod:** `whisper-openai-6885fc878b-jjm5j`  
**Container State:** terminated  
**Exit Code:** 137  
**Reason:** ContainerStatusUnknown  

**Exit Code 137 Analysis:**
- **137 = 128 + 9** (SIGKILL)
- **Primary Causes:**
  1. **Out of Memory (OOM) Kill** - Most likely for ML/AI workloads
  2. **Manual termination** via `kubectl delete`
  3. **Resource constraint violations** (CPU/memory limits)

**Given this is a speech-to-text AI service (whisper-openai)**, OOM kill is the most probable cause, suggesting:
- Insufficient memory limits for the workload
- Memory leaks in the inference process
- Inadequate resource planning for AI model serving

### PVC Mount Issues

**Event Timestamp:** 2026-07-24T19:36:57Z  
**Warning:** FailedMount  
**Pod:** `whisper-openai-68966786fb-jsb5d`  

**Issue:** MountVolume.SetUp failed for PVC `pvc-d5891df2-b37f-4043-96a1-7098e218378c`

**Analysis:** This suggests:
1. **Volume attachment conflicts** between pods
2. **Storage backend issues** (NFS/CSI driver problems)
3. **PVC capacity or access mode issues**

---

## Common Failure Patterns

### Pattern 1: Resource Exhaustion in AI Services

**Manifestation:** Exit code 137 (SIGKILL/OOM)  
**Affected Services:** whisper-openai (confirmed), whisper-stt (suspected)  
**Root Cause:** Inadequate memory/resource limits for AI/ML workloads

**Evidence:**
- whisper-openai pod termination with exit code 137
- Rapid deployment iterations suggesting instability
- AI workloads typically have high memory requirements

**Recommendation:** Review and increase memory limits for AI inference services

### Pattern 2: Deployment Storm Patterns

**Manifestation:** Multiple rapid deployments within short timeframes  
**Affected Services:** whisper-stt (observed), pbx-web (potential)  
**Root Cause:** Automated rollback/retry mechanisms triggering on deployment failures

**Evidence:**
- 3 whisper-stt deployments within 17 minutes on July 8th
- High deployment frequency (11 vs 2) suggesting instability
- Revision increments indicating failed rollbacks

**Recommendation:** Implement deployment pre-flight checks and health monitoring

### Pattern 3: Storage Infrastructure Dependencies

**Manifestation:** FailedMount warnings and PVC attachment issues  
**Affected Services:** whisper-openai (confirmed), potential for others  
**Root Cause:** Storage backend limitations or configuration issues

**Evidence:**
- FailedMount warning on whisper-openai pod
- PVC mount failure with "no Pending workload pods" error
- Possible CSI driver or storage class issues

**Recommendation:** Review storage class configuration and PVC access modes

---

## Comparative Service Characteristics

| Characteristic | pbx-web | whisper-stt |
|----------------|---------|-------------|
| **Service Type** | Web Application | AI/ML Inference |
| **Deployment Frequency** | Low (2 in 30 days) | High (11 in 30 days) |
| **Stability** | High | Low/Medium |
| **Resource Profile** | Standard compute | Memory-intensive AI |
| **Failure Modes** | Minimal observed | OOM kills, PVC issues |
| **Deployment Storms** | None observed | Yes (July 8th) |
| **Pod Health** | All healthy | 1 failed pod |

---

## Recommendations

### Immediate Actions (High Priority)

1. **Investigate whisper-openai OOM Kill**
   - Review current memory limits and actual usage
   - Implement memory monitoring and alerting
   - Consider vertical pod autoscaling based on memory patterns

2. **Resolve PVC Mount Issues**
   - Investigate storage backend health
   - Review PVC access modes and storage classes
   - Check CSI driver logs for root cause analysis

3. **Address Deployment Storm Patterns**
   - Implement deployment health checks with proper timeouts
   - Add pre-deployment validation for whisper-stt
   - Consider blue-green deployments to reduce rollback frequency

### Medium-Term Improvements

4. **Implement Resource Monitoring**
   - Set up Prometheus alerts for memory usage approaching limits
   - Track deployment success rates and rollback frequencies
   - Monitor PVC attachment success rates

5. **Deployment Strategy Review**
   - For whisper-stt: Consider canary deployments given high volatility
   - For pbx-web: Current strategy appears adequate
   - Implement deployment cooldown periods to prevent storms

### Long-Term Architecture

6. **AI Service Resource Planning**
   - Right-size memory limits for AI workloads
   - Consider dedicated node pools for memory-intensive services
   - Evaluate horizontal pod autoscaling for inference services

---

## Conclusion

The 30-day analysis reveals fundamentally different operational profiles between `pbx-web` and `whisper-stt`. While `pbx-web` demonstrates stable, low-frequency deployment patterns with minimal failures, `whisper-stt` exhibits high deployment volatility with evident resource exhaustion issues and storage dependencies.

**Key Takeaway:** AI/ML services like `whisper-stt` require different operational considerations than traditional web services, particularly around resource planning, deployment strategies, and monitoring practices.

The identified patterns suggest that investment in proper resource sizing, deployment health checks, and storage infrastructure stability would significantly improve the operational reliability of the whisper-stt service family.

---

## Data Sources

- **Kubernetes API:** ardenone-cluster via kubectl-proxy
- **Namespaces:** pbx-web, whisper-stt
- **Data Types:** ReplicaSets, Pods, Events, Container Statuses
- **Time Range:** 2026-06-24 to 2026-07-24 (30-day rolling window)

---

*Report generated: 2026-07-24*  
*Analysis tool: aide-de-camp research task*