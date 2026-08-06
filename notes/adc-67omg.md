# PBX-Web Workflow History Query

**Date:** 2026-08-06
**Task:** Query last 30 days of Argo Workflow executions for `pbx-web-build` template

## Findings

No workflow executions found for the `pbx-web-build` template in the iad-ci cluster.

### Query Details

- **Cluster:** iad-ci
- **Namespace:** argo-workflows
- **Template:** pbx-web-build (verified to exist)
- **Date Range:** Last 30 days (since 2026-07-07)
- **Output:** `/tmp/pbx-web-workflows-raw.json` (119 bytes, empty result set)

### Technical Notes

The field selector `creationTimestamp>=...` is not supported for Workflows (returns BadRequest). The query used label filtering only:
```bash
kubectl get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  --sort-by=.metadata.creationTimestamp \
  -o json
```

### Background Verification

- ✅ `pbx-web-build` WorkflowTemplate exists (71d old)
- ✅ Other workflows exist in the cluster (needle-ci, seam-ci, etc.)
- ❌ No pbx-web-build workflow executions found in current history

### Conclusion

The `pbx-web-build` template has not been executed recently (or executions have been cleaned up by Argo's podGC/history retention policies). The last execution, if any, is older than the current workflow retention window.
