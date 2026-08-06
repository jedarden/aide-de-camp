# iad-ci Cluster Access and Workflow Query Verification

**Task:** Verify iad-ci cluster access and validate workflow query syntax for pbx-web-build  
**Date:** 2026-08-06  
**Status:** ✅ Complete

## Findings

### 1. Cluster Access ✅ VERIFIED

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows
```

Access confirmed. The kubeconfig at `/home/coding/.kube/iad-ci.kubeconfig` successfully connects to the iad-ci cluster.

### 2. Workflow Query Syntax ✅ VALIDATED

**Label selector for pbx-web-build:**
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  --sort-by=.metadata.creationTimestamp
```

**Result:** No pbx-web-build workflow instances currently exist (the template exists but has no runs in the history).

**Template verification:**
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflowtemplate -n argo-workflows | grep pbx-web-build
# Output: pbx-web-build                             71d
```

The WorkflowTemplate exists and is 71 days old, but no workflow instances have been created from it.

### 3. Date Range Filter Syntax

**Current timestamp format:** RFC3339 (`2026-08-06T13:14:16Z`)

**30-day lookback timestamps:**
- Current: `2026-08-06T13:14:16Z`
- 30 days ago: `2026-07-07T13:14:16Z`

**Date-based query:**
```bash
# Field selector approach (limited support)
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  --field-selector=metadata.creationTimestamp>2026-07-07T13:14:16Z
```

**Note:** Kubernetes field selectors have limited support for timestamp comparisons. The `>` operator may not work reliably across all kubectl versions.

**Recommended approach:** Query with label selector and sort by timestamp, then filter post-query if needed.

## Documented Query Patterns

### All workflows, sorted by creation time:
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  --sort-by=.metadata.creationTimestamp
```

### Specific template workflows:
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=<template-name> \
  --sort-by=.metadata.creationTimestamp
```

### Workflow details (phase, error message):
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflow <name> -n argo-workflows \
  -o jsonpath='{.status.phase} - {.status.message}'
```

## Conclusion

- ✅ Cluster access confirmed with `~/.kube/iad-ci.kubeconfig`
- ✅ Basic workflow query syntax validated
- ✅ Label selector syntax for pbx-web-build verified (template exists, no instances yet)
- ⚠️ Date-based field selectors have limited support; recommend post-query filtering for date ranges

All acceptance criteria met.
