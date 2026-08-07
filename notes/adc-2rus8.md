# iad-ci Cluster Access Verification

## Task: Verify iad-ci cluster access and test workflow queries

## Connection Method

**Kubeconfig:** `~/.kube/iad-ci.kubeconfig`
- ServiceAccount: `argocd-manager` with cluster-admin access
- Direct kubeconfig (not proxied)
- Rackspace Spot cluster in us-east-iad-1

## Verification Results

### ✅ 1. Cluster Connection
Successfully connected to iad-ci cluster using:
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows
```

Connection verified - can list workflows in argo-workflows namespace.

### ✅ 2. List Workflows
Successfully retrieved workflow list. Recent workflows include:
- Multiple `needle-ci-*` workflows (mostly failed with "Max duration limit exceeded")
- `armor-build-*` workflows (mix of Failed and Running)
- `seam-ci-*` workflows (Failed with "main: Error (exit code 1)")
- `mta-my-way-build-*` workflows (Failed with child failures)
- Various other build workflows

### ✅ 3. View Workflow Details
Successfully retrieved workflow details using:
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflow -n argo-workflows <name> -o jsonpath='{.status.phase} - {.status.message}'
```

Tested on `armor-build-kgkvv`: Returns `Running -`

### ✅ 4. pbx-web-build WorkflowTemplate
**Template exists:** `pbx-web-build` (AGE: 71d)

**Template Details:**
- Repo: `jedarden/nixos-asterisk`
- Container path: `pbx-web`
- Branch: `main`
- Entry point: `build`
- ServiceAccount: `argo-workflow`

**Build Steps:**
1. `resolve-version`: Auto-bumps PATCH version if VERSION file unchanged in commit
2. `docker-build`: Uses Kaniko to build `ronaldraygun/pbx-web:{version}` and `:latest`

**Resource Limits:**
- CPU: 500m request, 2000m limit
- Memory: 1Gi request, 4Gi limit
- Build timeout: 1800s (30 minutes)
- Retry strategy: 2 retries with exponential backoff

## ⚠️ Finding: No pbx-web-build Workflow Runs

**Issue:** No recent (or any) pbx-web-build workflow runs found in the cluster.

**Search attempts:**
1. Label selector: `-l workflows.argoproj.io/workflow-template=pbx-web-build` → No results
2. Text search: `grep pbx-web` → No results

**Implications:**
- The WorkflowTemplate exists but hasn't been executed
- May need manual submission to test build logs retrieval
- Could indicate the build pipeline is new or hasn't been triggered yet

## Next Steps for Log Retrieval

To fetch pbx-web deployment logs:
1. Submit a pbx-web-build workflow manually (or wait for a CI trigger)
2. Query workflow status with `kubectl get workflow <name> -n argo-workflows`
3. Stream logs from running pods or retrieve from completed workflows
4. Use Argo UI at `https://argo-ci.ardenone.com` for visual log inspection

## Access Verification Complete

All acceptance criteria met:
- ✅ Can successfully connect to iad-ci cluster using kubectl
- ✅ Can list workflows in argo-workflows namespace
- ✅ Can view a single workflow's details
- ✅ Connection method documented (uses `~/.kube/iad-ci.kubeconfig`)
