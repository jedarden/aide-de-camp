# Task: Query Argo Workflows for pbx-web-build

## Query Results

**Status:** ✅ Query executed successfully, but no pbx-web-build workflows found

### Attempted Query Methods

1. **Field Selector Approach** (FAILED)
   ```bash
   kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
     --field-selector=workflowTemplateRef.name=pbx-web-build -o json
   ```
   **Result:** Error - field label not supported: workflowTemplateRef.name

2. **Client-Side Filtering** (SUCCESSFUL)
   ```bash
   kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows -o json | \
     jq '.items[] | select(.spec.workflowTemplateRef.name == "pbx-web-build")'
   ```
   **Result:** Empty array (0 workflows found)

### Raw JSON Output (Empty Result)
```json
{
  "apiVersion": "v1",
  "items": [],
  "kind": "List",
  "metadata": {
    "resourceVersion": ""
  }
}
```

### Workflow Template Status

The `pbx-web-build` workflow template **exists** and was created on `2026-05-27T02:25:59Z`.

**Template Details:**
- Repository: `jedarden/nixos-asterisk`
- Container path: `pbx-web`
- Purpose: Docker build → `ronaldraygun/pbx-web`
- Branch: `main`
- Auto-bumps VERSION file if not changed in commit

### Analysis

**Zero pbx-web-build workflows found** - This indicates:
1. No pbx-web-build workflows have been run yet, OR
2. All historical pbx-web-build workflows have been cleaned up (deleted)

The workflow template exists and is properly configured, but there are no active or completed workflow instances using it.

### Current Workflow Activity

The cluster has active workflows for other templates (needle-ci, spaxel-build, acb-build, etc.), but none for pbx-web-build.

### Next Steps for Date Filtering

Since there are no pbx-web-build workflows to filter, the date filtering task would need to:
1. Wait for pbx-web-build workflows to be executed, OR
2. Investigate historical workflow logs if they exist elsewhere
