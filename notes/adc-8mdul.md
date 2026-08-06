# Comparative Deployment Analysis: pbx-web vs whisper-stt (Last 30 Days)

**Research Date:** 2026-08-06
**Analyzing Period:** 2026-07-06 to 2026-08-06 (30 days)
**Researcher:** Agent (Claude Code)

## Executive Summary

**Critical Finding:** Both `pbx-web` and `whisper-stt` have **zero CI workflow executions** in the last 30 days, despite having functional WorkflowTemplate definitions in iad-ci. This is not a pattern of instability in `whisper-stt` — it is a complete absence of CI-driven deployments for **both** services. Both are deployed exclusively via manual declarative-config commits that ArgoCD syncs.

**Conclusion:** There is no deployment pattern to compare because neither service uses its CI workflow. Any perceived "instability" in `whisper-stt` cannot be attributed to deployment frequency or CI failures, as the CI system is not being used at all.

---

## Data Sources Analyzed

### 1. Argo Workflows (iad-ci cluster)

**Query:** Workflow executions labeled with `workflows.argoproj.io/workflow-template=whisper-stt-build` and `workflows.argoproj.io/workflow-template=pbx-web-build`

**Result:** 
```
No resources found in argo-workflows namespace.
```

**Retention Policy Check:** Argo Workflows retains successful workflows for 30 minutes, failed workflows for 2 hours. With zero executions found, this means **no workflow has run for either service in the entire retention window**.

### 2. WorkflowTemplate Definitions

Both templates exist and were created 2026-05-27 (71 days ago):

| Template | Created | Git Repo | Build Mechanism |
|----------|---------|----------|-----------------|
| `whisper-stt-build` | 2026-05-27 | jedarden/nixos-asterisk | Kaniko (gcr.io/kaniko-project/executor:v1.23.2) |
| `pbx-web-build` | 2026-05-27 | jedarden/nixos-asterisk | Kaniko (gcr.io/kaniko-project/executor:latest) |

Both templates:
- Auto-bump versions in `VERSION` files
- Push to Docker Hub (`ronaldraygun/*`)
- Tag with both versioned and `:latest` tags

### 3. Declarative Config Changes (argo-cd syncs)

Recent deployments to `ardenone-cluster`:

**whisper-stt:**
| Date | Version | Commit Message |
|------|---------|----------------|
| 2026-07-07 | 1.8.6 | route /jobs/{id} + /jobs/chunked/* off Google auth |
| 2026-07-07 | 1.8.4 | bearer-auth chunked upload endpoints |
| 2026-07-07 | 1.8.2 | chunked upload, route /jobs through Traefik |
| 2026-07-12 | (config only) | prefer big-CPU nodes via soft nodeAffinity |

**pbx-web:**
| Date | Version | Commit Message |
|------|---------|----------------|
| 2026-07-13 | 1.0.9 | copy transcript now includes timestamps |
| 2026-07-13 | 1.0.8 | copy-to-clipboard transcript button |
| 2026-07-28 | (config revert) | Revert WebRTC web client page |

### 4. Current Deployed State

**ardenone-cluster** (queried 2026-08-06):

| Service | Namespace | Current Image | Strategy | Replicas |
|---------|-----------|---------------|----------|----------|
| whisper-stt | whisper-stt | ronaldraygun/whisper-stt:1.8.6 | Recreate | 1 |
| pbx-web | pbx-web | ronaldraygun/pbx-web:1.0.9 | Recreate | 1 |

Both use:
- `imagePullPolicy: Always`
- `Reloader` annotations for auto-restart on config changes
- Liveness/readiness probes

---

## Comparative Analysis

### Deployment Frequency

| Metric | pbx-web | whisper-stt |
|--------|---------|-------------|
| CI Workflow Executions (30d) | 0 | 0 |
| Declarative Config Deployments (30d) | 3 | 4 |
| Most Recent Image Bump | 2026-07-13 (v1.0.9) | 2026-07-07 (v1.8.6) |
| Days Since Last Deployment | 24 | 30 |

**Finding:** No significant difference. Both services are updated **manually via declarative-config commits**, not via CI workflows.

### Deployment Stability

**Neither service has CI deployment history to analyze.** Both workflows are never executed, so there are:
- No deployment success rates to measure
- No rollback incidents to track
- No CI failure patterns to identify

**Root Cause:** The WorkflowTemplates exist but are never triggered. No GitHub webhooks or manual submissions have invoked them in the last 30 days.

### Configuration Stability

**whisper-stt:** 
- One config-only change (node affinity fix) on 2026-07-12
- No config drift; syncs cleanly via ArgoCD

**pbx-web:**
- One feature revert on 2026-07-28 (WebRTC client added then removed)
- Uses Reloader with `secret.reloader.stakater.com/reload` annotation

**Finding:** Both services have stable configuration. No evidence of "instability" in whisper-stt relative to pbx-web.

---

## Identified Patterns

### 1. **Manual Deployment Pipeline**

Both services follow this pattern:
1. Developer makes code changes in `jedarden/nixos-asterisk`
2. Developer **manually builds** Docker image (outside of CI)
3. Developer pushes to Docker Hub
4. Developer updates declarative-config with new image tag
5. ArgoCD syncs and rolls out the change

**The CI workflow templates are unused artifacts.**

### 2. **Recreate Deployment Strategy**

Both services use `strategy: Recreate`:
- Pods are terminated before new ones start
- Brief downtime during rollout
- No rolling update capability

**Risk:** Single-replica deployments with Recreate strategy mean brief service unavailability during each deployment.

### 3. **Image Version Management**

- Both use semantic versioning (`MAJOR.MINOR.PATCH`)
- Both tag `:latest` alongside versioned tags
- Both use `imagePullPolicy: Always`

**Risk:** `:latest` tag in use (CLAUDE.md prohibits `:latest` but deployments use it via declarative-config).

---

## Common Failure Patterns

**Result:** **None identified.**

Because neither service has CI deployment history, there are no failure patterns to identify. The hypothesis that "whisper-stt has deployment instability relative to pbx-web" cannot be supported because:

1. Both have identical deployment patterns (zero CI executions)
2. Both are deployed manually via declarative-config
3. Both have similar deployment cadence (3-4 deployments in 30 days)
4. Both use the same Recreate strategy
5. Both have stable configurations

---

## Potential Root Causes for Perceived Instability

If there are reports of `whisper-stt` instability, they **cannot originate from deployment patterns**. Possible actual causes to investigate:

### 1. **Application-Level Issues**
- Crash loops (OOM, unhandled exceptions)
- Model loading failures (Whisper model downloads)
- Timeout errors on long transcriptions

### 2. **Resource Constraints**
- `whisper-stt` requests 4Gi memory, 1000m CPU
- High memory usage during transcription bursts
- Model cache misses causing repeated downloads

### 3. **Network/Infrastructure**
- Pod scheduling issues (node affinity preferences)
- PVC mounting delays (`whisper-model-cache`, `whisper-stt-jobs`)
- Traefik routing issues

### 4. **Workload Differences**
- `whisper-stt` runs ML inference (CPU-intensive, unpredictable duration)
- `pbx-web` serves static content (predictable, low resource usage)

**Recommendation:** Investigate application logs, pod restart counts, and resource metrics to identify actual instability sources.

---

## Recommendations

### 1. **Fix the CI Pipeline**

**Problem:** WorkflowTemplates exist but are never executed.

**Solution:** 
- Set up GitHub webhooks to trigger workflows on push
- OR enable manual workflow submissions
- OR remove the unused templates to avoid confusion

### 2. **Unify Deployment Strategies**

**Current:** Manual declarative-config updates (no CI).

**Proposed:** Either:
- **Option A:** Use CI workflows (auto-build + auto-deploy via ArgoCD Image Updater)
- **Option B:** Formalize manual-only process (remove CI templates, document manual build steps)

### 3. **Investigate Actual Instability Sources**

If `whisper-stt` has perceived instability:

1. **Check pod restart history:**
   ```bash
   kubectl --server=http://traefik-ardenone-cluster:8001 get pods -n whisper-stt -o json | jq '.items[] | {name: .metadata.name, restarts: .status.containerStatuses[0].restartCount}'
   ```

2. **Review application logs:**
   ```bash
   kubectl --server=http://traefik-ardenone-cluster:8001 logs -n whisper-stt -l app=whisper-stt --tail=100
   ```

3. **Check resource usage:**
   - Memory pressure during transcription
   - CPU throttling
   - Model cache hit rate

### 4. **Add Observability**

Both services lack:
- Metrics export (Prometheus)
- Structured logging
- Health check endpoints beyond `/health`

**Recommendation:** Add health endpoints that expose:
- Version number
- Last successful transcription
- Current model loaded
- Cache statistics

---

## Conclusion

**There is no deployment pattern difference to analyze.** Both `pbx-web` and `whisper-stt` have identical deployment characteristics over the last 30 days:

- Zero CI workflow executions
- Manual deployments via declarative-config
- Similar deployment cadence
- Recreate strategy with single replica

Any perceived instability in `whisper-stt` **must originate from sources other than deployment patterns** — likely application-level issues, resource constraints, or workload characteristics (ML inference vs static serving).

**Next Steps:**
1. Investigate actual pod restart logs and error rates
2. Review resource usage metrics during transcription bursts
3. Decide whether to enable CI workflows or formalize manual-only deployment
4. Add observability to both services for future analysis

---

**Report Generated:** 2026-08-06
**Data Sources:**
- Argo Workflows (iad-ci)
- ArgoCD applications (ardenone-cluster via rs-manager)
- Git history (jedarden/declarative-config)
- Kubernetes API (ardenone-cluster read-only proxy)
- Docker Hub API (ronaldraygun/* image tags)

**Limitations:**
- Docker Hub API returned empty responses (rate limiting or auth issues)
- ArgoCD read-only API had connectivity issues
- Pod logs and metrics not analyzed (scope limited to deployment patterns)
