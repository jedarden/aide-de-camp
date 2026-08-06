# pbx-web-build Workflow Investigation Summary

**Date:** 2026-08-06
**Task:** Query pbx-web-build workflow runs from Argo for last 30 days (since 2026-07-07)

## Query Method

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows -l workflows.argoproj.io/workflow-template=pbx-web-build --sort-by=.metadata.creationTimestamp -o json
```

## Findings

### Workflow Template Status
- **Template exists:** `pbx-web-build` WorkflowTemplate is present in argo-workflows namespace
- **Template age:** 71 days (created 2026-05-27)
- **Purpose:** Builds pbx-web container from jedarden/nixos-asterisk repo

### Workflow Run Results
- **Total pbx-web-build workflows found:** 0
- **Query result:** Empty list (saved to `pbx-web-raw-workflows.json`)

### Additional Context
- **Total workflows in namespace:** 13
- **Recent workflows include:**
  - needle-ci (multiple runs with failures)
  - vista-build (recent successful runs)
  - seam-ci (recent failures)
  - gribtract-ci (errors: template not found)
  - warden-build (error: template not found)
  - b2-usage-exporter-build (error: template not found)

## Analysis

The pbx-web-build workflow template has not been executed in the recent period (at least not within the retention window of the workflow controller). This could indicate:

1. **No trigger conditions met:** The workflow may only run on specific git events (commits to pbx-web/VERSION) that haven't occurred
2. **Workflow retention policy:** Old workflows may be automatically cleaned up (TTL-based retention)
3. **Manual execution only:** The workflow may be run manually rather than via automated triggers

## Recommendations

To verify the template is functional, consider:
1. Checking git history for jedarden/nixos-asterisk pbx-web/VERSION commits
2. Verifying webhook/sensor configuration for pbx-web-build triggers
3. Manual workflow execution test if needed
