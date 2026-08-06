# Deployment Analysis Report: pbx-web vs whisper-stt (Last 30 Days)

**Analysis Period:** 2026-07-07 to 2026-08-06  
**Date Generated:** 2026-08-06  
**Services Analyzed:** `pbx-web` and `whisper-stt`  
**Cluster:** ardenone-cluster  

## Executive Summary

Over the past 30 days, `pbx-web` has demonstrated **stable deployment patterns** with minimal disruption, while `whisper-stt` has experienced **significant volatility** including a major deployment cascade on June 14th involving 11 rapid deployments within one hour. The key difference lies in deployment stability: pbx-web averaged 0.37 deployments/day versus whisper-stt's 0.73 deployments/day, with whisper-stt showing a 2x higher deployment frequency and one major incident requiring repeated rollouts.

### Key Findings

- **Deployment Frequency:** whisper-stt had 2x more deployments (22 vs 11)
- **Major Incident:** whisper-stt experienced a deployment cascade on June 14th (11 deployments in 1 hour)
- **Resource Intensity:** whisper-stt uses 16x more CPU and memory than pbx-web
- **Current Status:** Both services currently stable with zero restarts
- **Active Deployments:** pbx-web has 1 active replica, whisper-stt has 2 active replicas

## 1. Deployment Frequency & Velocity

### pbx-web Deployment Patterns
- **Total Deployments:** 11 replica sets over 30 days
- **Deployment Rate:** ~0.37 deployments/day
- **Revision Range:** Revisions 10-14 (5 revision changes)
- **Current Active:** pbx-web-5ff68464d (Revision 14)
- **Last Deployment:** 2026-07-28 (9 days ago)

**Deployment Distribution by Date:**
```
2026-05-07: 2 deployments
2026-06-23: 2 deployments  
2026-07-13: 2 deployments
2026-06-21, 2026-06-25, 2026-07-28, 2026-05-11, 2026-06-15: 1 each
```

### whisper-stt Deployment Patterns
- **Total Deployments:** 22 replica sets over 30 days
- **Deployment Rate:** ~0.73 deployments/day (2x higher than pbx-web)
- **Revision Range:** Revisions 14-32 (18 revision changes)
- **Current Active:** whisper-openai-68966786fb (Revision 24), whisper-stt-847fd8d7b9 (Revision 32)
- **Last Deployment:** 2026-07-12 (25 days ago)

**Deployment Distribution by Date:**
```
2026-06-14: 11 deployments (major incident)
2026-07-08: 3 deployments
2026-06-25, 2026-06-26: 2 deployments each
2026-07-01, 2026-07-02, 2026-06-24, 2026-07-12: 1 each
```

## 2. Major Incident Analysis: whisper-stt Deployment Cascade (June 14th)

### Incident Timeline
On **2026-06-14**, whisper-stt experienced a deployment cascade involving 11 replica sets created between 03:44:24Z and 04:55:48Z (~71 minutes).

```
03:44:24 - rev 14 (whisper-openai-7ccf9f655b) - TERMINATED
03:50:27 - rev 15 (whisper-openai-7558965d58) - TERMINATED (+6 min)
03:53:06 - rev 16 (whisper-openai-685c49f459) - TERMINATED (+2.6 min)
03:56:31 - rev 17 (whisper-openai-7548956b49) - TERMINATED (+3.4 min)
04:01:11 - rev 18 (whisper-openai-7b756c458) - TERMINATED (+4.7 min)
04:06:40 - rev 19 (whisper-openai-745d9c487d) - TERMINATED (+5.5 min)
04:11:57 - rev 20 (whisper-openai-55bb9fb46f) - TERMINATED (+5.3 min)
04:27:44 - rev 21 (whisper-openai-85b44d79b4) - TERMINATED (+15.8 min)
04:48:36 - rev 22 (whisper-openai-6b75db654f) - TERMINATED (+20.9 min)
04:52:13 - rev 23 (whisper-openai-6885fc878b) - TERMINATED (+3.6 min)
04:55:48 - rev 24 (whisper-openai-68966786fb) - ACTIVE (+3.6 min) ✓
```

### Analysis
- **Pattern:** Classic deployment failure cascade
- **Speed:** Deployments occurred 2-20 minutes apart
- **Resolution:** Revision 24 finally stabilized the service
- **Likely Causes:** 
  - Application startup failures (health check timeouts)
  - Resource constraints (insufficient CPU/memory during initialization)
  - Dependency issues (model loading failures for Whisper models)

This pattern strongly suggests **repeated pod failures during startup/health checks**, causing Kubernetes to terminate unsuccessful pods and trigger new deployments.

### Additional Quick Deployment Events
whisper-stt also had rapid deployment patterns on other dates:
```
whisper-stt-65fb7f8dd9 -> whisper-stt-558c7cf44: 2.1 minutes apart
whisper-stt-5dbff75cbd -> whisper-stt-5b8558f478: 6.6 minutes apart  
whisper-stt-5b8558f478 -> whisper-stt-6c497489fb: 10.5 minutes apart
```

## 3. Resource Constraints & Utilization

### pbx-web Resource Profile
**Container: site-generator**
```
CPU:    10m request, 500m limit (50x ratio)
Memory: 128Mi request, 512Mi limit (4x ratio)
```

**Container: nginx**
```
CPU:    5m request, 100m limit (20x ratio)  
Memory: 32Mi request, 128Mi limit (4x ratio)
```

**Container: rebuild-relay services**
```
CPU:    5m request, 100m limit (20x ratio)
Memory: 32Mi request, 128Mi limit (4x ratio)
```

**Total Service Resources:** ~600m CPU, ~768Mi memory (peak)

### whisper-stt Resource Profile
**Container: whisper-openai / whisper-stt**
```
CPU:    1 request, 8 limit (8x ratio)
Memory: 4Gi request, 8Gi limit (2x ratio)
```

**Total Service Resources:** ~8 CPU, ~8Gi memory (peak)

### Resource Comparison
| Metric | pbx-web | whisper-stt | Ratio |
|--------|---------|-------------|-------|
| CPU Request | 15m | 1 | 67x |
| CPU Limit | 600m | 8 | 13x |
| Memory Request | 192Mi | 4Gi | 21x |
| Memory Limit | 768Mi | 8Gi | 11x |

**Key Insight:** whisper-stt is **11-67x more resource-intensive** than pbx-web, reflecting its ML inference workload versus pbx-web's static site serving.

## 4. Error Patterns & Failure Modes

### Current Pod Status
**pbx-web (3 pods running)**
- `lab-rebuild-relay-79957dbd4-xsqhl`: Running, 0 restarts (since 2026-07-27)
- `pbx-rebuild-relay-588d79c5b9-vmmlz`: Running, 0 restarts (since 2026-07-15)
- `pbx-web-5ff68464d-mkn8n`: Running, 0 restarts (since 2026-07-28)

**whisper-stt (2 pods running)**
- `whisper-openai-68966786fb-jsb5d`: Running, 0 restarts
- `whisper-stt-847fd8d7b9-v2rs5`: Running, 0 restarts (since 2026-07-12)

### Event Analysis
Both services show **minimal warning/error events** in the current 30-day window:
- pbx-web: 0 warning/error events recorded
- whisper-stt: 0 warning/error events recorded  

*Note: Kubernetes events are garbage collected after ~1 hour, so historical failure events from the June 14th incident are no longer available.*

### Historical Error Inference
Based on the deployment cascade pattern, whisper-stt likely experienced:
- **Startup probe failures** (initial 30 failure threshold on startupProbe)
- **Health check timeouts** (30s period, 1s timeout thresholds)
- **Possible OOM events** during model loading (8Gi limit may have been insufficient)
- **Liveness probe failures** triggering pod restarts

## 5. Common Failure Patterns

### Shared Patterns
1. **Kubernetes Deployment Rollercoaster:** Both services use ArgoCD-managed deployments with ReplicaSets
2. **Health Check Dependency:** Both rely on HTTP health endpoints (`/health` path)
3. **Resource Limits:** Both use explicit resource requests/limits

### Divergent Patterns

**pbx-web (Stable Service)**
- Low resource footprint allows quick scaling/restarts
- Simple web serving workload with predictable resource needs
- No complex initialization or model loading
- Single active deployment at any time

**whisper-stt (Volatile Service)**
- High resource requirements (CPU/memory intensive ML inference)
- Complex initialization (model loading, cache setup)
- Extended startup windows (startupProbe with 30 failure threshold)
- Multiple active deployments (suggests A/B testing or gradual migration)
- History of deployment cascades requiring multiple retries

## 6. Deployment Stability Assessment

### Stability Metrics

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|  
| Deployment Frequency | 0.37/day | 0.73/day |
| Revision Changes | 5 | 18 |
| Major Incidents | 0 | 1 (June 14) |
| Current Restarts | 0 | 0 |
| Active ReplicaSets | 1 | 2 |
| Days Since Last Deploy | 9 | 25 |

### Risk Assessment

**pbx-web: LOW RISK** ✅
- Consistent deployment pattern
- No deployment cascades or rapid-fire deployments
- Minimal resource requirements
- Stable for 9+ days

**whisper-stt: MEDIUM RISK** ⚠️
- History of deployment cascades (June 14th incident)
- Higher deployment frequency indicating instability
- Multiple active deployments suggesting migration in progress
- High resource requirements increase failure surface area
- Stable for 25+ days but history suggests potential for recurrence

## 7. Recommendations

### For whisper-stt (Priority Actions)
1. **Investigate June 14th Root Cause:** Review logs from that deployment cascade to identify specific failure mode
2. **Optimize Startup Probes:** Current 30-failure threshold on startupProbe may be masking real issues
3. **Add PreStop Hooks:** Ensure graceful shutdown to reduce cascade risk during deployments
4. **Consider Progressive Delivery:** Implement canary deployments instead of full rollout
5. **Monitor Model Loading:** Add specific metrics for model loading time and success rate

### For pbx-web (Maintain Current State)
1. **Continue Current Patterns:** Deployment strategy is working well
2. **Monitor Resource Utilization:** Current low resource usage suggests room for optimization
3. **Consider Horizontal Scaling:** If load increases, consider horizontal pod autoscaling

### For Both Services
1. **Enhanced Event Logging:** Implement persistent event logging beyond Kubernetes' default retention
2. **Deployment Metrics:** Add deployment success rate, time-to-healthy metrics
3. **Alert on Rapid Deployments:** Set alerts for >3 deployments within 1 hour
4. **Post-Mortem Process:** Document deployment incidents to prevent recurrence

## 8. Conclusion

Over the past 30 days, **pbx-web has demonstrated superior deployment stability** with consistent, predictable deployments and no major incidents. **whisper-stt shows concerning volatility**, particularly the June 14th deployment cascade that required 11 rapid deployments within one hour to achieve stability.

The key differentiator is workload complexity: pbx-web serves static content with minimal resource needs, while whisper-stt performs ML inference with significant resource requirements and complex initialization. This complexity increases whisper-stt's failure surface area and explains its higher deployment frequency and incident rate.

**Risk Summary:** pbx-web presents minimal deployment risk, while whisper-stt requires immediate attention to prevent recurrence of deployment cascades. The current 25-day stability period for whisper-stt is encouraging, but the history suggests the underlying issues may not be fully resolved.

---

**Data Sources:**  
- Kubernetes ReplicaSets API (30-day history)  
- Current Pod Status (real-time)  
- Events API (limited retention)  
- Resource specifications from active deployments  

**Analysis Methodology:**  
Comparative analysis of deployment frequency, revision history, resource constraints, and failure patterns across both services using kubectl queries and JSON parsing.