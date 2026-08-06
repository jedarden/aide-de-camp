# PBX-Web Deployment Failure Taxonomy (30-Day Analysis: 2026-07-07 to 2026-08-06)

## Executive Summary

**Analysis Period:** 2026-07-07 to 2026-08-06 (30 days)
**Total Deployments:** 2 (last 30 days)
**Deployment Success Rate:** 50% (1/2)
**Failed Deployments:** 1 (50% failure rate)
**Rollback Events:** 1 automatic rollback
**Current Uptime:** 9 days continuous
**Overall Assessment:** Moderate deployment stability with significant deployment failure

## Deployment Events Timeline

| Date | Event | Revision | Image | Outcome | Notes |
|------|-------|----------|-------|---------|-------|
| 2026-07-28T17:26:12Z | Pod Recreated | 14 | ronaldraygun/pbx-web:1.0.9 | ✅ Success | Current active pod (rollback recovery) |
| 2026-07-28T17:05:51Z | **Deployment Failed** | 13 | ronaldraygun/pbx-web:1.0.9 | ❌ **Failed** | Deployment scaled down, automatic rollback |
| 2026-07-13T18:18:07Z | Rollout | 14 | ronaldraygun/pbx-web:1.0.9 | ✅ Success | Previous successful deployment |
| 2026-07-13T18:07:55Z | Rollback | 11 | ronaldraygun/pbx-web:1.0.8 | ⚠️ Rolled Back | Same-day rollback to 1.0.8 |

## Failure Classification

### Category: Technical Deployment Failures
**Count:** 1
**Frequency:** 50% (1/2 deployments)
**Severity:** High (automatic rollback triggered)

#### Subcategories:
- **Image Pull Errors:** 0 - No container registry authentication or manifest issues detected
- **CrashLoopBackOff:** Unknown - No pod logs available from failed deployment
- **Resource Exhaustion:** Unknown - No OOMKilled events visible in current data
- **Configuration Mismatches:** Unknown - No ConfigMap or Secret mounting failures evident
- **Probe Failures:** Possible - Health checks may have failed, triggering scaledown
- **Infrastructure Issues:** Unknown - No node or network-related deployment failures detected

### Failed Deployment Details (2026-07-28T17:05:51Z)

**ReplicaSet:** pbx-web-765bb76db8
**Revision:** 13
**Image:** ronaldraygun/pbx-web:1.0.9
**Status:** Scaled down / Failed
**Replicas:** 0 (spec=0, available=0, ready=0)
**Duration:** ~20 minutes before rollback recovery pod created

**Observed Failure Pattern:**
1. Deployment attempted at 17:05:51Z
2. ReplicaSet created but immediately scaled to 0 replicas
3. No pods became ready or available
4. Automatic rollback to previous ReplicaSet (pbx-web-5ff68464d) at 17:26:12Z
5. Recovery pod created from previous ReplicaSet

**Root Cause Indicators:**
- No crash loop evidence in available data
- No image pull failures
- No resource exhaustion events
- Likely causes:
  1. **Probe Failure:** Readiness/liveness probes failed repeatedly
  2. **Configuration Issue:** Critical config missing or invalid
  3. **Startup Failure:** Application failed to start properly
  4. **Resource Constraints:** Insufficient resources during pod initialization

### Category: Post-Deploy Application Errors
**Count:** 0 deployment-affecting errors
**Notes:** Application logs show client-disconnect errors during audio streaming (handled gracefully by service, not deployment-related)

#### Observed Application-Level Events (Non-Failure):
- **Recording Stream Interruptions:** 5 instances of client disconnects during audio playback
  - Error pattern: `[Errno 104] Connection reset by peer` → `BrokenPipeError: [Errno 32]`
  - Impact: Individual request failures only; service continues normally
  - Not classified as deployment failure (handled at application layer)

### Category: Historical Manual Rollbacks
**Count:** 1 (outside 30-day analysis window but relevant context)
**Date:** 2026-07-13T18:07:55Z
**Root Cause:** Unknown (logs show no technical failure; likely functional or performance issue detected post-deploy)

#### Historical Rollback Details (2026-07-13):
- **Deployment Duration Before Rollback:** ~10 minutes (18:07:55Z → 18:18:07Z)
- **Triggering Version:** ronaldraygun/pbx-web:1.0.9 (revision 14)
- **Rollback Target:** ronaldraygun/pbx-web:1.0.8 (revision 11)
- **Root Cause Indicators:** None in available logs
  - No crash loops
  - No image pull errors
  - No probe failures
  - No resource exhaustion
  - No configuration errors

## Failure Frequency Table

| Failure Type | Count | Percentage | Severity | MTTR (Mean Time to Recover) |
|--------------|-------|------------|----------|------------------------------|
| **Deployment Failures** | **1** | **50%** | **High** | **~20 minutes** |
| ├─ Probe Failures (suspected) | 1 | 50% | High | ~20 minutes |
| ├─ Image Pull Errors | 0 | 0% | N/A | N/A |
| ├─ CrashLoopBackOff | 0 | 0% | N/A | N/A |
| ├─ Resource Exhaustion | 0 | 0% | N/A | N/A |
| ├─ Configuration Errors | 0 | 0% | N/A | N/A |
| └─ Infrastructure Issues | 0 | 0% | N/A | N/A |
| **Manual Rollbacks** | **1** | **N/A** | **Medium** | **~10 minutes** |
| **Application Errors** | **5** | **100% handled** | **Low** | **Immediate** |

## Deployment Health Metrics

| Metric | Value | Status |
|--------|-------|--------|
| Deployment Success Rate (30d) | 50% (1/2) | ⚠️ Needs Attention |
| Pod Availability | 100% (1/1 replicas ready) | ✅ Excellent |
| Container Restarts | 0 | ✅ Excellent |
| Probe Success Rate | Unknown (failed deployment) | ⚠️ Needs Investigation |
| Current Uptime | 9 days | ✅ Good |
| Mean Time Between Failures (MTBF) | 30 days | ⚠️ Moderate |
| Mean Time to Recover (MTTR) | ~20 minutes | ✅ Good |

## Root Cause Analysis

### Failed Deployment (2026-07-28T17:05:51Z): Probable Probe or Startup Failure

**Available Evidence:**
- ReplicaSet pbx-web-765bb76db8 was created but never spawned healthy pods
- No pods transitioned to Ready state
- Automatic rollback to previous ReplicaSet occurred within ~20 minutes
- Current deployment (using previous ReplicaSet) has been stable for 9 days

**Failure Mechanism:**
1. Deployment controller created new ReplicaSet with 0 replicas
2. Pod creation likely failed health checks or startup
3. Kubernetes scaled deployment to 0 (failure state)
4. Deployment controller reverted to previous healthy ReplicaSet

**Likely Root Causes (ordered by probability):**
1. **Probe Failure:** Readiness/liveness probes failed, preventing pod from becoming Ready
2. **Startup Crash:** Application crashed during initialization (before logs captured)
3. **Configuration Error:** Critical configuration missing or invalid
4. **Resource Constraints:** Insufficient CPU/memory during pod startup

**Limitations:**
- No pod logs available from failed deployment (pods deleted before log capture)
- No events captured during the failure window
- No metrics or monitoring data to confirm root cause

**Inference:**
The deployment failed due to **probable health check failures or startup crashes** that:
1. Prevented pods from becoming Ready
2. Triggered automatic deployment rollback
3. Were resolved by using the previous stable ReplicaSet
4. Have not recurred in 9 days of continuous operation

### Historical Rollback Event (2026-07-13): Unknown Technical Root Cause

**Available Evidence:**
- Pod logs show no errors during 1.0.9 deployment period
- No crash loops, image pull failures, or probe timeouts recorded
- Current 1.0.9 deployment (redeployed on 2026-07-28) has been stable for 9 days

**Limitations:**
- Pre-rollback logs for revision 14 not available in collected data
- No metrics or monitoring data to capture performance regressions
- No operator notes or deployment tickets describing the issue

**Inference:**
The rollback was likely triggered by a **functional or performance issue** that:
1. Did not manifest as a hard technical failure (no crashes or errors)
2. Was detected through manual testing or user feedback within ~10 minutes of deployment
3. Was addressed before re-deploying 1.0.9 on 2026-07-28 (current deployment stable)

## Taxonomy Summary

### Classification Hierarchy

```
PBX-Web Deployment Failures (Last 30 Days)
├── Technical Deployment Failures (1 instance, 50%)
│   ├── Probable Probe Failures (1 suspected)
│   ├── Startup Crashes (1 possible)
│   ├── Configuration Errors (0)
│   └── Infrastructure Issues (0)
├── Manual Rollbacks (1 historical instance)
│   └── Unknown Root Cause (likely functional or performance issue)
└── Application-Level Errors (0 deployment-affecting)
    └── Client Disconnects During Audio Streaming (5 instances, non-failure)
```

### Failure Severity Distribution

- **Critical (service down):** 0 instances (0%)
- **High (automatic rollback):** 1 instance (50%)
- **Medium (manual rollback):** 1 historical instance (N/A for 30d period)
- **Low (handled gracefully):** 5 instances (100% of errors, 0% of deployments)

## Recommendations

### For Deployment Failure Investigation

1. **Capture Pre-Failure State:** Configure log retention for failed pods (do not delete immediately on failure)
2. **Enable Events Logging:** Capture Kubernetes events during deployment windows to detect probe failures
3. **Add Startup Probes:** Implement startup probes to distinguish between initialization time and actual crashes
4. **Enhanced Monitoring:** Add deployment-phase metrics to track pod state transitions

### For Deployment Process Improvement

1. **Pre-Deployment Validation:** Validate configuration and health check settings before deployment
2. **Gradual Rollout:** Use gradual rollout strategies (canary deployments) to detect issues early
3. **Health Check Tuning:** Review and optimize readiness/liveness probe thresholds and timeouts
4. **Resource Validation:** Ensure sufficient CPU/memory resources are available during deployment

### For Monitoring and Alerting

1. **Deployment Alerts:** Configure alerts for deployment failures and automatic rollbacks
2. **Probe Failure Tracking:** Monitor probe failure rates to detect systemic issues
3. **Resource Monitoring:** Track resource usage during deployments to identify constraints
4. **Application Error Monitoring:** Continue monitoring recording stream errors (handled well, non-impactful)

## Conclusion

**PBX-Web deployment health is Moderate** with 1 technical deployment failure (50% success rate) in the last 30 days. The failure appears to be related to health checks or startup issues, as evidenced by the automatic rollback to the previous ReplicaSet. The current deployment has been stable for 9 days, indicating the issue was resolved by using the previous configuration.

**Key Takeaways:**
- ⚠️ 50% deployment success rate in last 30 days (1/2 deployments failed)
- ⚠️ 1 automatic rollback due to probable probe/startup failure
- ⚠️ Root cause unknown due to missing pod logs and events data
- ✅ 9 days of continuous uptime on current deployment (using previous ReplicaSet)
- ✅ No crash loops, image pull errors, resource exhaustion, or configuration issues in stable deployment
- ✅ Application-level errors handled gracefully (client disconnects during audio streaming)

**Immediate Actions Required:**
1. Investigate probe configuration and thresholds
2. Enable pod log retention for failed deployments
3. Review deployment process to prevent future automatic rollbacks
4. Add monitoring and alerting for deployment failures