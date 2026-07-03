# kubectl delete pod Task Analysis (adc-5jl)

## Task Status
**BEAD STATUS:** Marked for closure as incomplete specification

## Current Environment
- **Cluster:** iad-kalshi (Rackspace Spot, us-east-iad-1)
- **Context:** apexalgo-iad-kalshi-oidc
- **Access:** Read-only via kubectl-proxy over Tailscale

## Command Analysis

### Complete `kubectl delete pod` Syntax
```bash
# Basic syntax
kubectl delete pod <pod-name> [-n <namespace>]

# With selectors
kubectl delete pod -l <label-selector> [-n <namespace>]

# Force delete (stuck pods)
kubectl delete pod <pod-name> [-n <namespace>] --force --grace-period=0
```

### What's Missing
The provided command `kubectl delete pod` is **incomplete**:
1. **No pod name specified** — required positional argument
2. **No namespace specified** — defaults to `default` namespace (likely wrong target)
3. **No selector provided** — alternative to pod name for bulk deletion

## Why This Cannot Be Executed

Attempting to run without arguments:
```bash
$ kubectl delete pod
error: you must specify at least one pod name or selector
```

## Required Information for Completion

To properly execute this task, the following must be specified:

1. **Target Pod Name OR Selector**
   - Specific pod: `-n <namespace> <pod-name>`
   - By label: `-n <namespace> -l app=myapp`
   - By annotation: `-n <namespace> -l canary=true`

2. **Namespace** (unless using `default` namespace)
   - Common namespaces: `kalshi-tape`, `weather-fast`, `devpod-observer`, etc.

3. **Confirmation of Intent**
   - Is this a specific pod removal?
   - Is this a cleanup of completed pods?
   - Is this a rolling update restart?

## Constraints from Infrastructure

**CRITICAL:** Current access to iad-kalshi is **READ-ONLY** via kubectl-proxy:
- Cannot delete, create, or modify resources
- Would need admin kubeconfig with OIDC token for write access
- Admin kubeconfig at `/home/coding/.kube/iad-kalshi-admin.kubeconfig` (has ~3 day expiry)

## Corrective Actions Needed

For future iterations of this task bead:

1. **Specify the exact target**:
   ```markdown
   ## Target
   - Namespace: kalshi-tape
   - Pod: kalshi-tape-7d6f8c9b4-x2k9m
   - Reason: Stuck in CrashLoopBackOff
   ```

2. **Or specify deletion criteria**:
   ```markdown
   ## Target
   - Namespace: weather-fast
   - Selector: app=weather-fast,status=completed
   - Reason: Cleanup completed jobs
   ```

3. **For production clusters**, follow GitOps:
   - If the pod is managed by ArgoCD (Deployment/StatefulSet/etc.)
   - Edit the manifest in `jedarden/declarative-config`
   - Commit, push, let ArgoCD sync
   - Direct deletion fights the controller and gets reverted

## Recommendation

This bead should be reworked with one of these approaches:

1. **Specific Pod Deletion:** Add exact pod name and namespace
2. **Cleanup Routine:** Define criteria (completed pods, age threshold, namespace)
3. **Infrastructure Change:** If this is for deployment updates, use GitOps flow instead

---

**Bead:** adc-5jl  
**Issue:** Incomplete specification — missing pod name, namespace, and deletion criteria  
**Resolution:** Document analysis in notes, close bead as incomplete  
**Date:** 2026-07-02
