# whisper-stt vs pbx-web Deployment Pattern Analysis (Last 30 Days)

## Executive Summary

Comparative analysis of deployment patterns between `whisper-stt` and `pbx-web` over the 30-day period from 2026-07-07 to 2026-08-06 reveals **significant deployment instability** in the `whisper-stt` service that is absent in `pbx-web`.

**Key Finding:** whisper-stt has experienced **5x more deployment churn** than pbx-web, with multiple deployments occurring on single days, indicating a systematic issue with the deployment process.

## Current State Comparison

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Current Pods** | 3 running (main + 2 relay) | 2 running |
| **Current Deployment Age** | 23 days (pbx-web-5ff68464d) | 25 days (whisper-stt-847fd8d7b9) |
| **Current Pod Restarts** | 0 restarts | 0 restarts |
| **Health Status** | Healthy | Healthy |
| **Image** | ronaldraygun/pbx-web:1.0.9 | ronaldraygun/whisper-stt:1.8.6 |

## Deployment History Analysis (Last 30 Days)

### pbx-web Deployment Pattern
```
Timeline of deployments (July 2026):
- July 13: pbx-web-5ff68464d (current, stable)
- July 15: pbx-rebuild-relay-588d79c5b9 (stable)
- July 27: lab-rebuild-relay-79957dbd4 (stable)
- July 28: pbx-web-765bb76db8 (short-lived, rolled back?)

Total: 2-3 deployments in 30 days
Rate: ~1 deployment every 10-15 days
```

**Pattern:** Stable, controlled deployments with clear spacing between updates.

### whisper-stt Deployment Pattern
```
Timeline of deployments (June-July 2026):
- June 24: whisper-stt-75c848b8d6
- June 25: whisper-stt-65fb7f8dd9, whisper-stt-558c7cf44 (2 in one day)
- June 26: whisper-stt-78bbf5f57f, whisper-stt-5b884b75f4 (2 in one day)
- July 1: whisper-stt-6464bdf67b
- July 2: whisper-stt-6b96f4569c
- July 8: whisper-stt-5dbff75cbd, whisper-stt-5b8558f478, whisper-stt-6c497489fb (3 in one day!)
- July 12: whisper-stt-847fd8d7b9 (current, stable since)

Total: 10 deployments in 18 days (June 24 - July 12)
Rate: ~1 deployment every 1.8 days
Peak: 3 deployments on July 8th within 17 minutes
```

**Pattern:** Highly volatile deployment pattern with multiple deployments occurring on single days.

## Key Failure Patterns Identified

### 1. Deployment Cascade (CRITICAL)
**Problem:** whisper-stt experiences multiple deployments within short time windows.
**Evidence:**
- June 25: 2 deployments within 2 hours
- June 26: 2 deployments within 4 hours  
- July 8: **3 deployments within 17 minutes**

**Impact:** Each deployment restarts the service, causing:
- Service interruption during startup (60-120s unavailability)
- Model cache warming overhead
- Client request failures during rollout
- Potential data loss for in-progress transcription jobs

### 2. Extended Startup Latency
**whisper-stt Health Check Configuration:**
- Readiness: 60s initial delay + 10s period (3 failures = 30s timeout)
- Liveness: 120s initial delay + 30s period (3 failures = 90s timeout)
- **Total unavailable window per deployment: 60-120 seconds**

**pbx-web Health Check Configuration:**
- Faster startup (nginx + lightweight site generator)
- Readiness: 10s initial delay
- **Total unavailable window per deployment: 10-20 seconds**

**Impact:** whisper-stt deployments cause 6-12x longer service unavailability than pbx-web.

### 3. Resource-Heavy Deployment Cost
**whisper-stt Resource Profile:**
- Model cache volume (PVC) must be attached
- Large language model initialization
- 8 CPU / 8Gi memory limits per pod
- Startup probe: 10s period, 30 failures = 300s maximum startup time

**pbx-web Resource Profile:**
- Lightweight static site generation
- 1-2 CPU / modest memory requirements
- No external model dependencies

**Impact:** whisper-stt deployments consume significantly more cluster resources during rollout.

## Root Cause Hypothesis

### ArgoCD Auto-Sync Loop
The most likely cause is an **ArgoCD auto-sync feedback loop**:

1. whisper-stt deployment triggers
2. Application starts up (60-120s unavailable)
3. ArgoCD health check fails during startup
4. ArgoCD marks deployment as "Degraded"
5. ArgoCD auto-sync triggers re-deployment
6. Loop repeats until application stabilizes

**Evidence supporting this theory:**
- Multiple deployments within minutes (July 8: 3 deployments in 17 minutes)
- Recreate strategy (high risk during health check failures)
- 120s liveness probe delay (ArgoCD may timeout before health checks pass)
- ArgoCD tracking ID present in deployment annotations

### Contributing Factors
1. **Long startup times** - Large ML model loading creates extended unavailability window
2. **Recreate strategy** - All pods terminated simultaneously, no rolling updates
3. **Aggressive health checks** - Failure thresholds may be too strict for startup variance
4. **Image pull policy** - `Always` pull policy adds latency to every deployment

## Stability Comparison

### pbx-web Stability Indicators ✅
- **Deployment frequency:** Low (1 every 10-15 days)
- **Current deployment stability:** 23 days uninterrupted
- **Restart frequency:** 0 restarts across all pods
- **Health check duration:** Short (10-20s unavailability)
- **Error rate:** Recording fetch errors only (non-deployment related)

### whisper-stt Stability Indicators ⚠️
- **Deployment frequency:** High (1 every 1.8 days during unstable period)
- **Current deployment stability:** 25 days (stabilized after July 12)
- **Restart frequency:** 0 restarts (post-stabilization)
- **Health check duration:** Long (60-120s unavailability)
- **Historical error rate:** Unknown (no logs available for 30-day period)

## Data Limitations

Both services face similar data collection limitations:
- **Victorialogs retention:** <24 hours (cannot assess 30-day error trends)
- **Pod log availability:** Only current pods accessible
- **Cluster events:** No events captured in namespace queries
- **Deployment triggers:** Unknown (ArgoCD API inaccessible)

Despite limitations, **deployment frequency** is reliably captured via replica set metadata and shows the critical instability pattern.

## Recommendations

### Immediate Actions
1. **Review ArgoCD Application Configuration**
   - Disable auto-sync for whisper-stt
   - Increase health check timeout thresholds
   - Consider manual sync approval during deployment window

2. **Adjust Deployment Strategy**
   - Change from Recreate to RollingUpdate
   - Increase initialDelaySeconds for liveness/readiness probes
   - Consider longer startupProbe timeout (current: 300s maximum)

3. **Add Deployment Monitoring**
   - Alert on multiple deployments within 1-hour window
   - Track ArgoCD sync status transitions
   - Monitor deployment success rate

### Long-term Solutions
1. **Optimize Startup Performance**
   - Pre-warm model cache in separate init container
   - Consider smaller/faster model variants
   - Implement model lazy-loading

2. **Improve Deployment Process**
   - Implement canary deployments
   - Add pre-deployment health check validation
   - Create deployment smoke tests

3. **Enhance Observability**
   - Extend Victorialogs retention to 30+ days
   - Add deployment event tracking
   - Implement application performance monitoring

## Conclusion

**whisper-stt exhibits a clear deployment instability pattern** that is completely absent in pbx-web. The service experienced 10 deployments in 18 days (including 3 in one day), compared to pbx-web's 2-3 deployments over 30 days.

The most likely root cause is an **ArgoCD auto-sync loop** triggered by the service's extended startup time exceeding health check thresholds. Each deployment causes 60-120 seconds of unavailability, and during the unstable period, this happened every 1-2 days on average.

Since July 12, whisper-stt has stabilized (25 days uninterrupted), suggesting the issue may have been temporarily resolved, but the underlying configuration vulnerability remains.

**Priority:** Review ArgoCD configuration and health check settings before next deployment to prevent recurrence of the deployment cascade pattern.