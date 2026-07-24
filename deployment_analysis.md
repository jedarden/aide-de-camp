# pbx-web vs whisper-stt: 30-Day Deployment Analysis

**Analysis Period:** June 24, 2026 - July 24, 2026 (Rolling 30 Days)  
**Analysis Date:** July 24, 2026  
**Cluster:** ardenone-cluster  
**CI/CD System:** iad-ci Argo Workflows

---

## Executive Summary

**Key Finding:** No deployments occurred for either service during the 30-day analysis period. Both services are running with stale deployments (40-84 days old), with whisper-stt experiencing a persistent pod failure due to disk space constraints.

---

## 1. Deployment Frequency Analysis

### CI/CD Workflow Activity
- **pbx-web-build workflow**: No executions in the last 30 days
- **whisper-stt-build workflow**: No executions in the last 30 days
- **Templates exist** but have not been triggered since approximately May 2026

### Current Deployment Ages

| Service | Deployment Name | Age | Image Version |
|---------|----------------|-----|---------------|
| pbx-web | pbx-web | 84 days | ronaldraygun/pbx-web:1.0.9 |
| pbx-web | lab-rebuild-relay | 82 days | python:3-slim |
| pbx-web | pbx-rebuild-relay | 83 days | python:3-slim |
| whisper-stt | whisper-stt | 83 days | ronaldraygun/whisper-stt:1.8.6 |
| whisper-stt | whisper-openai | 40 days | fedirz/faster-whisper-server:latest-cpu |

**Deployment Frequency: 0 deployments per service in the analysis period**

---

## 2. Pod Health & Failure Patterns

### pbx-web Pod Status
```
NAME                                 READY   STATUS    RESTARTS   AGE
lab-rebuild-relay-79d6d858bb-gfbf2   1/1     Running   0          6d18h
pbx-rebuild-relay-588d79c5b9-vmmlz   1/1     Running   0          9d
pbx-web-5ff68464d-97b8p              2/2     Running   0          10d
```

**Status:** ✅ All pods healthy, zero restarts

### whisper-stt Pod Status
```
NAME                              READY   STATUS                   RESTARTS   AGE
whisper-openai-6885fc878b-jjm5j   0/1     ContainerStatusUnknown   0          40d
whisper-openai-68966786fb-jsb5d   1/1     Running                  0          40d
whisper-stt-847fd8d7b9-v2rs5      1/1     Running                  0          12d
```

**Status:** ⚠️ One failed pod, ongoing PVC mount issues

---

## 3. Critical Failure Mode: Disk Space Exhaustion

### whisper-openai Pod Failure Details

**Pod:** `whisper-openai-6885fc878b-jjm5j`  
**Failure Date:** June 14, 2026, 04:53:55 UTC  
**Root Cause:** Node ephemeral-storage exhaustion

```
Termination Reason: "The node was low on resource: ephemeral-storage. 
Threshold quantity: 1631311281, available: 1137364Ki"
Exit Code: 137 (SIGKILL)
```

### Persistent PVC Impact

The failed pod continues to affect cluster operations 40 days later:

```
Warning: FailedMount for pod/whisper-openai-68966786fb-jsb5d
"MountVolume.SetUp failed for volume pvc-d5891df2-b37f-4043-96a1-7098e218378c: 
no Pending workload pods for volume to be mounted: 
map[Failed:[whisper-openai-6885fc878b-jjm5j] Running:[whisper-openai-68966786fb-jsb5d]]"
```

**Impact:** The failed pod's PVC attachment is blocking clean volume operations.

---

## 4. Resource Configuration Comparison

### pbx-web Resources (Lightweight)
| Container | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| site-generator | 10m | 500m | 128Mi | 512Mi |
| nginx | 5m | 100m | 32Mi | 128Mi |

**Total per pod:** 15m CPU / 600m CPU limit, 160Mi / 640Mi memory

### whisper-openai Resources (Heavy)
| Container | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| whisper-openai | 1 | 8 | 4Gi | 8Gi |

**Per pod:** 1 CPU / 8 CPU limit, 4Gi / 8Gi memory

**Observation:** whisper-openai uses ~13x more memory and ~16x more CPU than pbx-web, making it more susceptible to resource constraints.

---

## 5. Node Distribution & Placement

### Pod Distribution Across Nodes
| Service | Node | Pod Count |
|---------|------|-----------|
| pbx-web | k3s-server-a | 1 |
| pbx-web | k3s-agent-minisforum | 2 |
| whisper-stt | k3s-lenovo-tiny | 1 |
| whisper-stt | k3s-agent-minisforum | 1 |

**Node Health:** All 7 nodes in Ready state, no node-level issues detected.

---

## 6. Error Event Summary

### pbx-web Namespace
**Events:** No error or warning events in the last 30 days

### whisper-stt Namespace
**Events:** Persistent FailedMount warnings (ongoing for 40+ days)
- Root cause: Failed pod blocking PVC operations
- Frequency: Repeated mount failures for new pod attempts

---

## 7. Shared Failure Patterns

### Identified Common Patterns

| Pattern | pbx-web | whisper-stt | Correlation |
|---------|---------|-------------|-------------|
| **Deployment Staleness** | 82-84 days | 40-83 days | ✅ Both lack recent updates |
| **Missing CI/CD Activity** | No workflows run | No workflows run | ✅ No automated deployments |
| **Resource Type** | Lightweight | Heavy | ❌ Different profiles |
| **Failure Impact** | None (0 restarts) | PVC blocking issue | ❌ whisper-stt only |
| **Node Issues** | None observed | Ephemeral-storage exhaustion | ❌ whisper-stt only |

### Correlation Analysis
**Deployment Events → Stability Issues:** ❌ No correlation found
- Neither service experienced deployments in the analysis period
- Stability issue in whisper-stt predates analysis window by 10 days

**Resource Constraints → Failures:** ✅ Partial correlation
- whisper-stt's heavy resource profile (8Gi memory) contributes to disk pressure
- pbx-web's lightweight profile avoids resource constraints

---

## 8. Root Cause Analysis

### Primary Issue: Lack of Deployment Hygiene
1. **No automated deployments** in 30 days despite workflow templates existing
2. **Stale images** running for 40-84 days without updates
3. **No pod lifecycle management** — failed pod remains for 40 days

### Secondary Issue: Resource Planning
1. **whisper-openai's heavy resource footprint** (8Gi memory) contributes to ephemeral-storage pressure
2. **Failed pod cleanup not automated** — PVC remains attached to failed pod
3. **No monitoring alerts** for failed pods or PVC mount issues

---

## 9. Recommendations

### Immediate Actions
1. **Clean up failed pod**: Delete `whisper-openai-6885fc878b-jjm5j` to unblock PVC operations
2. **Resume CI/CD workflows**: Trigger `whisper-stt-build` and `pbx-web-build` workflows
3. **Add resource monitoring**: Alert on ephemeral-storage usage thresholds

### Process Improvements
1. **Automate failed pod cleanup**: Implement pod failure handlers
2. **Establish deployment cadence**: Monthly security/stability updates even without code changes
3. **Resource rightsizing**: Review whisper-openai resource limits vs actual usage

### Monitoring Enhancements
1. **Alert on pod failures**: Immediate notification for Failed status pods
2. **PVC health monitoring**: Detect mount failures early
3. **Deployment age alerts**: Flag deployments older than 90 days

---

## 10. Conclusion

**Deployment Stability:** pbx-web demonstrates superior stability with zero failures, attributed to its lightweight resource profile and simpler architecture.

**whisper-stt Issues:** Stem from two factors:
1. Heavy resource footprint (8Gi memory, 8 CPU limit) leading to ephemeral-storage exhaustion
2. Lack of automated cleanup for failed pods, causing persistent PVC issues

**Common Root Cause:** Both services suffer from **deployment neglect** — no automated updates in 30+ days, indicating a broken or ignored CI/CD pipeline.

**Risk Assessment:** 
- **pbx-web**: Low risk — stable but outdated
- **whisper-stt**: Medium risk — failed pod creating operational debt, potential cascade failures

---

**Report Generated:** July 24, 2026  
**Next Review Date:** August 24, 2026  
**Analyst:** Automated via aide-de-camp research task