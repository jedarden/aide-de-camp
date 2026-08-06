# Task: Query pbx-web-build workflow runs for last 30 days

## Execution Summary

Query completed successfully on 2026-08-06. **Result: No pbx-web-build workflow runs found in the last 30 days.**

## Methodology

1. Verified kubectl access to iad-ci cluster (dependency: needle-3b251)
2. Queried Argo Workflows API for pbx-web-build workflows
3. Searched with multiple approaches:
   - Label selector: `workflows.argoproj.io/workflow-template=pbx-web-build`
   - Name pattern search for `pbx-web-build` and `pbx-web`
   - Broad search for any PBX-related workflows
4. Confirmed workflow template exists (created 2026-05-27T02:25:59Z)
5. Applied 30-day date range: 2026-07-07 to 2026-08-06

## WorkflowTemplate Details

- **Name**: pbx-web-build
- **Namespace**: argo-workflows
- **Created**: 2026-05-27T02:25:59Z
- **Purpose**: Builds `ronaldraygun/pbx-web` container from `jedarden/nixos-asterisk` repo
- **Container path**: pbx-web
- **Git branch**: main
- **Build strategy**: Kaniko executor with git-based context

## Findings

- **pbx-web-build workflow runs**: 0 (in the last 30 days)
- **Workflow template status**: Exists and properly configured via ArgoCD
- **Recent workflow activity**: None detected in current cluster state

## Analysis

The absence of pbx-web-build workflow runs indicates:

1. **No recent rebuilds**: The pbx-web container has not required rebuilding in the last 30 days
2. **Trigger mechanism**: The workflow runs when:
   - The `pbx-web/VERSION` file changes in the nixos-asterisk repo
   - Manual workflow submission is triggered
3. **TTL cleanup**: Any workflow runs older than the cluster's TTL setting would have been automatically cleaned up from the workflow history

## Raw Data

Empty workflow list (valid result - no workflows found) saved to: `~/scratch/pbx-web-raw-workflows.json`

## Query Used

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  --sort-by=.metadata.creationTimestamp \
  -o json > ~/scratch/pbx-web-raw-workflows.json
```
