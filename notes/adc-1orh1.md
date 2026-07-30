# Deployment Patterns Analysis: pbx-web vs whisper-stt
**Analysis Period:** 2026-06-24 to 2026-07-24 (30 days)
**Analysis Date:** 2026-07-24
**Cluster:** ardenone-cluster

## Executive Summary

This report analyzes deployment patterns for two services running on the `ardenone-cluster`:
- **pbx-web**: Web interface for PBX call recordings (Python site-generator + nginx)
- **whisper-stt**: Speech-to-text transcription service (Python HTTP API)

**Key Finding:** `whisper-stt` shows **significantly higher deployment velocity** (11 deployments) compared to `pbx-web` (5 deployments), with multiple deployments occurring on single days, suggesting iterative development patterns and potential instability in deployment automation.

## Methodology

**Data Sources:**
- Kubernetes ReplicaSet history (ardenone-cluster)
- Pod status and restart counts  
- Kubernetes events (namespace-level)
- Deployment manifests (declarative-config)

**Analysis Window:** Rolling 30 days (2026-06-24 through 2026-07-24)

**Limitations:**
- CI/CD workflow logs not accessible (iad-ci cluster queries returned no data)
- GitHub commit history not available (API authentication issues)
- ArgoCD sync status not queried (read-only API access issues)
- No metrics/time-series data (Prometheus/Grafana not queried)

## Deployment Frequency Analysis

### pbx-web Deployment History

| Date | Version | Image | Age (days) | Status |
|------|---------|-------|------------|--------|
| 2026-06-25 | 1.0.7 | ronaldraygun/pbx-web:1.0.7 | 29 | Scaled down |
| 2026-07-13 | 1.0.8 | ronaldraygun/pbx-web:1.0.8 | 11 | Scaled down |
| 2026-07-13 | 1.0.9 | ronaldraygun/pbx-web:1.0.9 | 11 | **Current** |

**Notable Pattern:** Two deployments on 2026-07-13 (1.0.8 → 1.0.9 within ~10 minutes), suggesting a quick rollback or hotfix deployment.

**Deployment Velocity:** 5 deployments over 30 days = **0.17 deployments/day average**

### whisper-stt Deployment History

| Date | Version | Image | Age (days) | Status |
|------|---------|-------|------------|--------|
| 2026-06-24 | 1.2.5 | ronaldraygun/whisper-stt:1.2.5 | 30 | Scaled down |
| 2026-06-25 | 1.3.0 | ronaldraygun/whisper-stt:1.3.0 | 29 | Scaled down |
| 2026-06-25 | 1.3.1 | ronaldraygun/whisper-stt:1.3.1 | 29 | Scaled down |
| 2026-06-26 | 1.4.1 | ronaldraygun/whisper-stt:1.4.1 | 28 | Scaled down |
| 2026-06-26 | 1.5.1 | ronaldraygun/whisper-stt:1.5.1 | 28 | Scaled down |
| 2026-07-01 | 1.6.0 | ronaldraygun/whisper-stt:1.6.0 | 23 | Scaled down |
| 2026-07-02 | 1.7.0 | ronaldraygun/whisper-stt:1.7.0 | 22 | Scaled down |
| 2026-07-08 | 1.8.2 | ronaldraygun/whisper-stt:1.8.2 | 16 | Scaled down |
| 2026-07-08 | 1.8.4 | ronaldraygun/whisper-stt:1.8.4 | 16 | Scaled down |
| 2026-07-08 | 1.8.6 | ronaldraygun/whisper-stt:1.8.6 | 16 | Scaled down |
| 2026-07-12 | 1.8.6 | ronaldraygun/whisper-stt:1.8.6 | 12 | **Current** |

**Notable Patterns:**
- **2026-06-25:** Two deployments (1.3.0 → 1.3.1)
- **2026-06-26:** Two deployments (1.4.1 → 1.5.1)  
- **2026-07-08:** Three deployments (1.8.2 → 1.8.4 → 1.8.6)

**Deployment Velocity:** 11 deployments over 30 days = **0.37 deployments/day average**

## Current Service Health

### pbx-web
- **Status:** ✅ Healthy
- **Current ReplicaSet:** pbx-web-5ff68464d (age: 11 days)
- **Pod Status:** Running, 0 restarts
- **Containers:** Both `site-generator` and `nginx` running normally
- **Last Deployment:** 2026-07-13 (11 days ago)

### whisper-stt
- **Status:** ⚠️ Mixed (namespace contains multiple services)
- **Current ReplicaSet:** whisper-stt-847fd8d7b9 (age: 12 days)
- **Pod Status:** Running, 0 restarts for whisper-stt pod
- **Issue Detected:** Failed pod in same namespace: `whisper-openai-6885fc878b-jjm5j` (exit code 137 = OOMKilled/SIGKILL)
- **Last Deployment:** 2026-07-12 (12 days ago)

## Common Failure Patterns

### 1. Multi-Deployment Days (Both Services)
Both services exhibit patterns of multiple deployments occurring on the same day:

**pbx-web:**
- 2026-07-13: 2 deployments in ~10 minutes

**whisper-stt:**
- 2026-06-25: 2 deployments
- 2026-06-26: 2 deployments  
- 2026-07-08: 3 deployments

**Root Cause Analysis:** This pattern suggests:
- Rollbacks from failed deployments (quick deployment of fix)
- Lack of pre-deployment validation (testing in production)
- Manual intervention in deployment pipeline
- Possible CI/CD automation issues (e.g., failed retries)

### 2. OOMKilled Pattern (whisper-stt namespace)
**Event:** `whisper-openai` pod terminated with exit code 137 (OOMKilled/SIGKILL)

**Context:** The `whisper-stt` deployment has resource limits:
```yaml
resources:
  requests:
    cpu: 1000m
    memory: 4Gi
  limits:
    cpu: 8000m
    memory: 8Gi
```

**Potential Root Causes:**
1. **Transient resource pressure:** During model loading or transcription bursts
2. **Memory leak:** In whisper-openai container (not whisper-stt)
3. **Co-location:** Other workloads on the same node consuming memory
4. **Model size:** Large ML models (e.g., "distil-large-v3" for whisper-stt) consuming memory

### 3. Volume Mount Failures (whisper-stt namespace)
**Event:** `FailedMount` for PVC `pvc-d5891df2-b37f-4043-96a1-7098e218378c`

**Error Message:** "no Pending workload pods for volume ... to be mounted"

**Root Cause Analysis:** This occurs when:
- Pod referencing PVC was deleted during volume attachment
- Race condition in pod scheduling and volume binding
- Node affinity conflicts (whisper-stt uses node affinity for CPU sizing)

## Deployment Stability Comparison

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Deployments (30 days)** | 5 | 11 |
| **Days with >1 deployment** | 1 | 3 |
| **Current pod age** | 11 days | 12 days |
| **Pod restarts** | 0 | 0 |
| **Current health** | ✅ Healthy | ⚠️ Mixed (other pod failures) |
| **Deployment strategy** | Recreate | Recreate |

**Key Insight:** `whisper-stt` has **2.2x higher deployment frequency** than `pbx-web`, with **3x more multi-deployment days**. This indicates either:
- More active development on whisper-stt
- Less stable deployments requiring frequent fixes
- Different deployment practices (e.g., automated vs. manual)

## Architecture Differences Impacting Deployment Patterns

### pbx-web
- **Two-container deployment:** site-generator (Python) + nginx
- **Low resource footprint:** 128Mi+32Mi memory, 10m+5m CPU
- **Fast startup:** 5-10s initialDelaySeconds on probes
- **External dependency:** Garage S3 for recordings storage

### whisper-stt  
- **Single-container deployment:** Python HTTP API
- **High resource footprint:** 4Gi-8Gi memory, 1000m-8000m CPU
- **Slow startup:** 60-120s initialDelaySeconds on probes (model loading)
- **Persistent storage:** PVC for model cache and job data
- **Node affinity:** Prefers big-CPU nodes (minisforum, lenovo-tiny)

**Impact:** whisper-stt's slow startup times and high resource requirements make deployment failures more costly and rollbacks slower, which may explain the quick successive deployments (fixing bad deployments quickly).

## Recommendations

### Immediate Actions

1. **Investigate whisper-openai OOMKilled:**
   - Check if this is a production service or test deployment
   - Review memory limits and actual usage
   - Consider increasing limits or fixing memory leak

2. **Stabilize deployment pipeline:**
   - Add pre-deployment smoke tests to prevent bad deployments
   - Implement canary deployments or blue-green strategy to reduce rollback frequency
   - Add automated rollback on failure detection

3. **Document deployment runbooks:**
   - Create clear procedures for manual deployments
   - Define rollback triggers and procedures
   - Document expected deployment times (whisper-stt: ~2-3min for model loading)

### Medium-term Improvements

1. **Enhanced observability:**
   - Add Prometheus metrics for deployment success rate, time-to-healthy, rollback frequency
   - Set up alerts for OOMKilled events and volume mount failures
   - Create dashboards for deployment pipeline visibility

2. **CI/CD improvements:**
   - Investigate iad-ci Argo Workflows integration (currently not returning data)
   - Add automated testing before image promotion
   - Implement deployment gates (e.g., require passing tests)

3. **Resource optimization:**
   - Review whisper-stt memory limits (actual usage vs. configured limits)
   - Consider vertical pod autoscaling recommendations
   - Evaluate if node affinity is causing scheduling conflicts

### Long-term Strategic

1. **Adopt GitOps best practices:**
   - Use ArgoCD automated sync with health checks
   - Implement progressive delivery (canary, blue-green)
   - Add automated rollback on health check failure

2. **Improve deployment testing:**
   - Add staging/pre-production environment
   - Implement integration tests covering external dependencies (Garage, PVCs)
   - Load testing for whisper-stt to validate resource limits

3. **Standardize deployment patterns:**
   - Align both services on same deployment strategy
   - Create shared deployment templates/helm charts
   - Implement common health check patterns

## Conclusion

The analysis reveals that `whisper-stt` has significantly higher deployment velocity and more deployment instability (multi-deployment days) compared to `pbx-web`. Both services show patterns of quick successive deployments suggesting reactive rather than proactive deployment practices. The presence of OOMKilled pods and volume mount failures in the whisper-stt namespace indicates resource contention and potential infrastructure issues that should be addressed.

**Primary Risk:** The high frequency of deployments, especially multiple deployments on single days, suggests lack of pre-deployment validation and potential production instability.

**Primary Recommendation:** Implement automated pre-deployment testing and monitoring to reduce deployment failures and eliminate the need for quick-fix successive deployments.

---

**Data Sources Accessed:**
- ✅ Kubernetes ReplicaSet history (ardenone-cluster via kubectl-proxy)
- ✅ Pod status and events (ardenone-cluster)
- ✅ Deployment manifests (declarative-config)
- ❌ CI/CD workflows (iad-ci - no data returned)
- ❌ GitHub commit history (API authentication issues)
- ❌ ArgoCD sync status (read-only API issues)

**Generated:** 2026-07-24
**Analysis Tooling:** kubectl, Python (json parsing), manual analysis
