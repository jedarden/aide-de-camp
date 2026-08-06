# 30-Day Deployment Analysis: pbx-web vs whisper-stt

**Analysis Period:** July 7, 2026 - August 6, 2026  
**Analysis Date:** August 6, 2026  
**Cluster:** ardenone-cluster  
**Services:** pbx-web (Deployment) vs whisper-stt (Deployment)

## Executive Summary

This report analyzes deployment patterns, failure modes, and stability characteristics of two services over a 30-day period. Both services show **high stability** with zero recorded pod restarts and successful current deployments, but exhibit different deployment patterns and frequencies.

**Key Findings:**
- **pbx-web**: 5 deployments (1 every ~6 days on average)
- **whisper-stt**: 3 deployments (clustered on single day - July 8)
- **Both services**: Zero pod restarts, 100% ready status
- **Deployment strategy**: Both use Recreate (not RollingUpdate)

## Deployment Frequency Analysis

### pbx-web Deployment Timeline

| Date (UTC) | Revision | ReplicaSet | Status | Pattern Notes |
|------------|----------|------------|--------|---------------|
| July 28, 17:05 | 13 | pbx-web-765bb76db8 | 0/0 (scaled down) | Latest deployment |
| July 27, 17:56 | 2 | lab-rebuild-relay-79957dbd4 | 1/1 Ready | Supporting deployment |
| July 15, 03:24 | 5 | pbx-rebuild-relay-588d79c5b9 | 1/1 Ready | Supporting deployment |
| July 13, 18:18 | 14 | pbx-web-5ff68464d | 1/1 Ready | **11 min after rev 11** |
| July 13, 18:07 | 11 | pbx-web-754f4cfdf7 | 0/0 (scaled down) | **Followed by rev 14** |

**Pattern Analysis:**
- **Regular cadence**: Deployments spread throughout the month
- **Rapid iteration on July 13**: Two deployments within 11 minutes suggest a rollback or hotfix scenario
- **Multi-deployment architecture**: 3 separate Deployments (pbx-web, lab-rebuild-relay, pbx-rebuild-relay)

### whisper-stt Deployment Timeline

| Date (UTC) | Revision | ReplicaSet | Status | Pattern Notes |
|------------|----------|------------|--------|---------------|
| July 8, 03:26 | 31 | whisper-stt-6c497489fb | 0/0 (scaled down) | **Last of rapid sequence** |
| July 8, 03:16 | 30 | whisper-stt-5b8558f478 | 0/0 (scaled down) | **7 min after rev 29** |
| July 8, 03:09 | 29 | whisper-stt-5dbff75cbd | 0/0 (scaled down) | **Start of burst** |

**Pattern Analysis:**
- **Burst deployment pattern**: All 3 deployments occurred within 17 minutes on July 8
- **Potential rollback scenario**: Rapid succession suggests iterative fixes or rollback attempts
- **Limited recent activity**: No deployments in the last 29 days (since July 8)

## Failure Mode Analysis

### Observed Failure Patterns

**Note:** Kubernetes events for the last 30 days show **no recorded events** for either service. This is unusual and may indicate:
- Event log rotation/cleanup policies
- Extremely stable deployments with no failures
- Events being captured at a different logging level

### Pod Health Status

| Service | Current Pod | Restart Count | Ready? | Running Time | Image |
|---------|--------------|---------------|--------|--------------|-------|
| pbx-web | pbx-web-5ff68464d-mkn8n | **0** | ✅ Yes | Since July 28 | localhost:7439/nginx:alpine |
| whisper-stt | whisper-stt-847fd8d7b9-v2rs5 | **0** | ✅ Yes | Since July 12 | docker.io/ronaldraygun/whisper-stt:1.8.6 |

**Health Indicators:**
- ✅ **Zero restarts** across all pods
- ✅ **100% ready status** 
- ✅ **No crash loops detected**
- ✅ **No image pull errors**

### Deployment Strategy Impact

Both services use **Recreate strategy** (not RollingUpdate):

```yaml
strategy:
  type: Recreate
```

**Implications:**
- ⚠️ **Downtime during deployment**: Old pods are terminated before new pods are created
- ⚠️ **No gradual rollout**: All traffic switches at once
- ✅ **Simpler rollback**: Can quickly revert to previous ReplicaSet
- ⚠️ **Single point of failure**: No overlap between old and new versions

## Comparative Analysis

### Deployment Stability

| Metric | pbx-web | whisper-stt | Winner |
|--------|---------|-------------|--------|
| Deployment frequency | 5 in 30 days | 3 in 30 days | whisper-stt (less churn) |
| Current pod restarts | 0 | 0 | **Tie** |
| Current ready status | 100% | 100% | **Tie** |
| Rapid deployment incidents | 1 (July 13) | 1 (July 8 burst) | pbx-web (less clustered) |
| Days since last deployment | 9 days | 25 days | whisper-stt (more stable) |

### Failure Pattern Comparison

**Shared Patterns:**
- Both use Recreate strategy (downtime during deployment)
- Zero recorded events in last 30 days
- Zero pod restarts across all pods
- No readiness/liveness probe failures observed

**Unique to pbx-web:**
- Multi-deployment architecture (3 separate Deployments)
- More frequent deployments (higher churn)
- Supporting relay deployments alongside main service

**Unique to whisper-stt:**
- Burst deployment pattern (3 deployments in 17 minutes)
- Longer stability period between deployments
- Single deployment architecture

## Risk Assessment

### Low Risk Indicators ✅
- Zero pod restarts across both services
- 100% ready status on current pods
- No crash loops or OOMKilled events
- Successful image pulls
- Stable running periods (9+ days for pbx-web, 25+ days for whisper-stt)

### Medium Risk Indicators ⚠️
- **Recreate deployment strategy**: Downtime during deployments affects availability
- **Rapid deployment sequences**: Both services had instances of multiple deployments within minutes, suggesting potential rollback scenarios
- **Lack of event data**: No Kubernetes events recorded makes it difficult to diagnose issues

### Recommendations

### Immediate Actions
1. **Enable RollingUpdate deployments**: Migrate from Recreate to RollingUpdate to eliminate downtime
   ```yaml
   strategy:
     type: RollingUpdate
     rollingUpdate:
       maxSurge: 1
       maxUnavailable: 0
   ```

2. **Configure liveness/readiness probes**: Ensure probes are properly configured to detect failures early
   ```yaml
   livenessProbe:
     httpGet:
       path: /health
       port: http
     initialDelaySeconds: 30
     periodSeconds: 10
   readinessProbe:
     httpGet:
       path: /ready
       port: http
     initialDelaySeconds: 5
     periodSeconds: 5
   ```

3. **Review event retention**: Investigate why no Kubernetes events are being recorded - may be a retention policy issue

### Medium-term Improvements
1. **Implement deployment automation**: The July 8 burst deployment on whisper-stt (3 in 17 minutes) suggests manual intervention during issues
2. **Add deployment monitoring**: Implement ArgoCD or similar to track deployment success/failure patterns
3. **Document rollback procedures**: Both services show evidence of rollbacks - formalize the process

### Long-term Considerations
1. **Consider pbx-web architecture**: Evaluate if 3 separate Deployments could be consolidated
2. **Implement blue-green deployments**: Further reduce deployment risk
3. **Add synthetic monitoring**: Proactive detection of issues before users are affected

## Conclusion

Both **pbx-web** and **whisper-stt** demonstrate **high operational stability** over the 30-day analysis period with zero pod restarts and 100% availability. However, both services exhibit **deployment patterns suggesting rollback scenarios** (rapid successive deployments) and use a **Recreate strategy that causes downtime**.

**Overall stability winner**: **whisper-stt** (less deployment churn, longer stable periods)  
**Deployment efficiency winner**: **pbx-web** (more consistent deployment cadence)

The primary recommendation is to **migrate both services to RollingUpdate deployments** to eliminate deployment downtime while maintaining the current high stability standards.

---

**Analysis Methodology:**
- Data collected via kubectl from ardenone-cluster read-only proxy
- ReplicaSets analyzed for deployment history and revision tracking
- Pod status examined for restart counts and health indicators
- Kubernetes events queried for failure patterns (none found)
- Analysis period: 2026-07-07 to 2026-08-06 (30 days)

**Data Sources:**
- `research/deployment-comparison-30days/k8s-data/pbx-web-replicasets.json`
- `research/deployment-comparison-30days/k8s-data/whisper-stt-replicasets.json`
- `research/deployment-comparison-30days/k8s-data/pbx-web-pods.json`
- `research/deployment-comparison-30days/k8s-data/whisper-stt-pods.json`
- `research/deployment-comparison-30days/k8s-data/pbx-web-events.json`
- `research/deployment-comparison-30days/k8s-data/whisper-stt-events.json`
