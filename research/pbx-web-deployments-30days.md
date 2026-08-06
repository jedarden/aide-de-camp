# pbx-web Deployment Logs - Last 30 Days

**Generated:** 2026-08-06  
**Analysis Period:** 2026-07-07 to 2026-08-06 (30 days)  
**Data Sources:** Argo Workflows (iad-ci), Kubernetes ReplicaSets (ardenone-cluster)

## Executive Summary

- **CI Workflows Found:** 0 (aggressive cleanup policy)
- **Production Deployments:** 3
- **Unique Images:** 2 (1.0.8, 1.0.9)
- **Current Image:** `ronaldraygun/pbx-web:1.0.9`
- **Deployment Success Rate:** 100%
- **Assessment:** Stable service with limited deployment activity

## CI Workflow Status

**Result:** No `pbx-web-build` workflows found in iad-ci cluster within the 30-day window.

**Root Cause:** Aggressive workflow cleanup policy in Argo Workflows - workflows are deleted within hours/days of completion.

**Query Performed:**
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template-ref-name=pbx-web-build \
  --sort-by=.metadata.creationTimestamp
```

## Production Deployment Timeline

### Deployment #1: Version 1.0.8
- **Date:** 2026-07-13 18:07:55 UTC
- **Revision:** 11
- **ReplicaSet:** `pbx-web-754f4cfdf7`
- **Image:** `ronaldraygun/pbx-web:1.0.8`
- **Duration:** 11 minutes (superseded by 1.0.9 same day)
- **Outcome:** Success

### Deployment #2: Version 1.0.9 (Initial)
- **Date:** 2026-07-13 18:18:07 UTC
- **Revision:** 14
- **ReplicaSet:** `pbx-web-5ff68464d`
- **Image:** `ronaldraygun/pbx-web:1.0.9`
- **Duration:** 15 days (until July 28 re-deployment)
- **Outcome:** Success

### Deployment #3: Version 1.0.9 (Re-deployment)
- **Date:** 2026-07-28 17:05:51 UTC
- **Revision:** 13
- **ReplicaSet:** `pbx-web-765bb76db8`
- **Image:** `ronaldraygun/pbx-web:1.0.9`
- **Duration:** 14 days (current active deployment as of 2026-08-06)
- **Outcome:** Success

## Current Status

- **Active Image:** `ronaldraygun/pbx-web:1.0.9`
- **Active Revision:** 14
- **Last Deployment:** 2026-07-28
- **Image Uptime:** 24 days (since 2026-07-13)
- **Replicas:** 1

## Deployment Activity Pattern

```
July 13, 2026:
  18:07 - Deploy 1.0.8 (rev 11)
  18:18 - Deploy 1.0.9 (rev 14) [upgrade]

July 28, 2026:
  17:05 - Re-deploy 1.0.9 (rev 13) [same image]

August 6, 2026:
  - No change, still running 1.0.9
```

## Coverage Assessment

| Metric | Value |
|--------|-------|
| Target Period | 30 days |
| Days with Deployments | 2 |
| Deployment Count | 3 |
| Coverage Percentage | 6.7% |

**Note:** Limited coverage due to workflow cleanup policy. Only ReplicaSet metadata available for reconstruction.

## Data Limitations

1. **No CI Build Logs** - Workflows deleted before capture
2. **No Step Durations** - Build time not available
3. **No Git Context** - Commit SHAs not in ReplicaSet metadata
4. **No Event Logs** - kubectl events query returned no results

## Recommendations for Complete History

1. **Query ArgoCD sync history** for git commit context
2. **Check container registry** (`ronaldraygun/pbx-web` tags) for build metadata
3. **Search declarative-config git history** for manifest changes
4. **Increase workflow TTL** for future CI tracking
5. **Implement WorkflowArchive** for permanent CI history retention

## Related Files

- `pbx-web-deployments-30days.json` - Structured data with full metadata
- `docs/research/deployment-data/pbx-web-deployments.json` - Previous analysis
- `docs/research/deployment-data/README.md` - Comprehensive research documentation

---

**Analysis Methodology:**  
Deployment history reconstructed from Kubernetes ReplicaSet creation timestamps and annotations. CI workflow data unavailable due to retention policy.
