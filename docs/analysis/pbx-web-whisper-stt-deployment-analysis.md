# Deployment Patterns Analysis: pbx-web vs whisper-stt
**Last 30 Days (July 7 - August 6, 2026)**

## Executive Summary

Analysis of `pbx-web` and `whisper-stt` deployments on ardenone-cluster over the last 30 days reveals **stable current operations** with **no active failure modes**, but historical patterns show **rapid iteration cycles** and **repeated deployments with identical versions**. Both services are currently healthy with zero pod restarts, but deployment frequency in late June/early July suggests a period of intensive development and configuration iteration.

**Key Finding:** No common failure patterns are currently active. The primary observed behavior is rapid version progression and redeployment without version changes during development windows.

---

## Methodology

Data gathered from:
- Kubernetes live state (replica sets, pods, deployments, events)
- Git commit history (`jedarden/nixos-asterisk` repo)
- Argo Workflows template definitions
- Pod logs and health check status

Time window: Rolling 30 days (2026-07-07 to 2026-08-06)

---

## Current State (As of August 6, 2026)

### pbx-web
- **Current Version:** `ronaldraygun/pbx-web:1.0.9`
- **Deployment Age:** 23 days (deployed July 13, 2026)
- **Pod Status:** 2/2 containers running, 0 restarts
- **Health:** Liveness/readiness probes passing
- **Replica Sets:** 10 total (11 old RS with 0 replicas)

### whisper-stt
- **Current Version:** `ronaldraygun/whisper-stt:1.8.6`
- **Deployment Age:** 24 days (deployed July 12, 2026)
- **Pod Status:** 1/1 containers running, 0 restarts
- **Health:** Liveness (120s delay) / readiness (60s delay) probes passing
- **Replica Sets:** 10 total (9 old RS with 0 replicas)

### whisper-openai (companion deployment)
- **Current Version:** `fedirz/faster-whisper-server:latest-cpu`
- **Deployment Age:** 53 days
- **Pod Status:** 1/1 containers running, 0 restarts
- **Note:** 11 replica sets total—all with identical image tag `:latest-cpu`

---

## Deployment History (Last 30 Days)

### pbx-web Timeline

| Date | Replica Set | Version | Notes |
|------|-------------|---------|-------|
| July 13 | `pbx-web-754f4cfdf7` | 1.0.8 | Same-day rollback |
| July 13 | `pbx-web-5ff68464d` | 1.0.9 | Current deployment |
| July 28 | `pbx-web-765bb76db8` | 1.0.9 | Redeploy, same version |

**Git History:**
```
3946d12 2026-07-13 chore(pbx-web): bump VERSION to 1.0.9
83343f1 2026-07-13 ci: auto-bump version to 1.0.8
2fd403e 2026-07-13 feat(pbx-web): include timestamps when copying transcript
9db337e 2026-07-13 feat(pbx-web): add copy-to-clipboard button on transcript page
```

### whisper-stt Timeline

| Date | Replica Set | Version | Notes |
|------|-------------|---------|-------|
| July 8 | `whisper-stt-5dbff75cbd` | 1.8.2 | First of 3 same-day deployments |
| July 8 | `whisper-stt-5b8558f478` | 1.8.4 | Second same-day deployment |
| July 8 | `whisper-stt-6c497489fb` | 1.8.6 | Third same-day deployment |
| July 12 | `whisper-stt-847fd8d7b9` | 1.8.6 | Current deployment |

**Git History:**
```
4b83578 2026-07-08 ci: auto-bump version to 1.8.6
f6046b5 2026-07-07 fix(whisper-stt): bearer-auth GET/DELETE /jobs/{id} too (1.8.5)
7699f69 2026-07-08 ci: auto-bump version to 1.8.4
edba130 2026-07-07 fix(whisper-stt): bearer-auth the chunked upload endpoints (1.8.3)
50ce4c8 2026-07-08 ci: auto-bump version to 1.8.2
16b8a98 2026-07-08 ci: auto-bump version to 1.8.1
3908a26 2026-07-07 feat(whisper-stt): add chunked upload for large files (1.8.0)
```

---

## Identified Patterns

### Pattern 1: Same-Day Redeployment Without Version Change

**Observation:** Both services show multiple replica sets with identical image versions deployed on the same day.

**Examples:**
- pbx-web: `pbx-web-765bb76db8` (v1.0.9) deployed July 28, but current RS is `pbx-web-5ff68464d` (also v1.0.9) from July 13
- whisper-stt: Three RS on July 8 with versions 1.8.2, 1.8.4, 1.8.6

**Potential Causes:**
1. **Configuration changes** (secret/ConfigMap updates triggering Reloader)
2. **Manual rollout restarts** for troubleshooting
3. **ArgoCD sync conflicts** during active development
4. **Deployment strategy issues** (both use `Recreate` strategy)

**Current Impact:** None—current deployments stable with 0 restarts

### Pattern 2: Rapid Version Progression During Development Windows

**Observation:** whisper-stt showed 6 version bumps (1.3.1 → 1.8.6) across ~30 days in late June/early July, correlating with feature development (chunked upload, bearer auth).

**Causes:**
- Active feature development with auto-bump CI
- Bug fixes for authentication issues
- Fast iteration on new features

**Current Impact:** None—development appears complete, version stable since July 12

### Pattern 3: Persistent Image Tag for whisper-openai

**Observation:** whisper-openai has 11 replica sets, all using image tag `:latest-cpu` (no version pinning).

**Risk:**
- Image pull differences between deployments
- No rollback capability without image rebuild
- Violates versioning best practice (no `:latest` tags per CLAUDE.md)

**Current Impact:** Stable (53 days uptime), but operational risk remains

---

## Common Failure Modes Analysis

### Hypothesized Failures (Not Currently Observed)

Based on patterns, the following failure modes likely occurred during the July development window:

1. **Configuration Drift Detection**
   - Reloader may have triggered redundant deployments when secret/ConfigMap changed
   - Mitigation: Current deployments stable—no action needed

2. **Image Pull Backoff (whisper-openai only)**
   - `:latest-cpu` tag could cause image pull failures if registry state changed
   - Mitigation: Stable for 53 days—consider pinning specific version

3. **Deployment Race Conditions**
   - Multiple same-day deployments may have overlapped during active development
   - Mitigation: Current deployments stable—dev activity has ceased

### Currently Active Issues

**None identified.** Both services are healthy with zero restarts and passing health checks.

---

## Deployment Strategy Comparison

| Aspect | pbx-web | whisper-stt |
|--------|---------|-------------|
| **Strategy** | Recreate | Recreate |
| **Replicas** | 1 | 1 |
| **Liveness** | HTTP /health, 10s delay, 30s period | HTTP /health, 120s delay, 30s period |
| **Readiness** | HTTP /health, 5s delay, 10s period | HTTP /health, 60s delay, 10s period |
| **Memory Limit** | 512Mi | 8Gi |
| **CPU Limit** | 500m | 8 |
| **Restart Count** | 0 | 0 |

**Key Difference:** whisper-stt has much longer probe delays (120s/60s) due to model loading time, appropriate for ML inference workload.

---

## CI/CD Pipeline Analysis

### Workflow Templates
- **pbx-web-build**: Auto-bumps VERSION if unchanged in commit, builds with Kaniko, pushes to `ronaldraygun/pbx-web`
- **whisper-stt-build**: Similar auto-bump, builds with Kaniko with `--use-new-run=true`, pushes to `ronaldraygun/whisper-stt`

### Observed Behavior
- Both templates successfully auto-bumped versions during July development
- No workflow runs visible in last 7 days (workflow TTL or successful completion)
- Build failures observed in other services (acb-build, spaxel-build) but not for pbx-web/whisper-stt

---

## Recommendations

### Immediate Actions (Priority: Low)

1. **Pin whisper-openai Image Version**
   - Current tag `:latest-cpu` is a policy violation and operational risk
   - Action: Pin to specific digest or version tag
   - Effort: Low (update deployment manifest)

2. **Document Configuration Change Policy**
   - Multiple same-day redeployments suggest unclear config drift handling
   - Action: Document when Reloader should trigger vs. manual intervention
   - Effort: Low (documentation)

3. **Events Retention Review**
   - No events available for historical analysis (likely TTL'd)
   - Action: Consider longer events retention or export to log aggregation
   - Effort: Low (cluster configuration)

### Long-term Improvements (Priority: Informational)

1. **Deployment Strategy Evaluation**
   - Both services use `Recreate` strategy—consider `RollingUpdate` for zero-downtime deployments
   - Trade-off: Single-replica deployments make rolling updates moot without scaling

2. **Probe Timing Tuning**
   - whisper-stt has very conservative probe delays (120s/60s)—consider reducing after model loading optimization
   - Benefit: Faster failure detection

3. **CI/CD Workflow Visibility**
   - Recent workflow runs not accessible—consider longer retention or success metrics export
   - Benefit: Better deployment pipeline observability

---

## Conclusion

**Status:** ✅ **HEALTHY** - No active failure modes or common patterns requiring immediate action.

**Summary:** Both pbx-web and whisper-stt are stable with zero pod restarts and passing health checks. Historical patterns show intensive development in July with rapid version progression and some same-day redeployments, but these have resolved. The only persistent risk is whisper-openai's unpinned image tag, which should be addressed to prevent future image pull issues.

**Next Steps:** Implement whisper-openai image pinning and document configuration change policies to prevent future confusion around redeployment triggers.

---

**Analysis Date:** August 6, 2026
**Data Sources:** ardenone-cluster (kubectl), jedarden/nixos-asterisk (git), iad-ci (Argo Workflows)
**Analysis Window:** July 7 - August 6, 2026 (30 days)
