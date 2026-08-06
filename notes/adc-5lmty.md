# Task adc-5lmty: Query pbx-web-build Workflows (Last 30 Days)

## Execution Summary

**Date:** 2026-08-06  
**Cluster:** iad-ci  
**Workflow Template:** pbx-web-build  
**Query Period:** 2026-07-07 to 2026-08-06 (30 days)

## Findings

### No pbx-web-build Workflow Runs Found

**Critical Discovery:** The `pbx-web-build` WorkflowTemplate exists but has **never been executed** despite being created on 2026-05-27 (over 2 months ago).

### Verification Steps

1. **Confirmed WorkflowTemplate exists:**
   ```bash
   kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
     get workflowtemplate -n argo-workflows pbx-web-build
   # Result: pbx-web-build (71d old)
   ```

2. **Verified no workflows exist:**
   ```bash
   kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
     get workflows -n argo-workflows \
     -l workflows.argoproj.io/workflow-template=pbx-web-build
   # Result: No resources found
   ```

3. **Checked all workflows in namespace:**
   - 100+ workflows from other templates (needle-ci, spaxel-build, acb-bots-build, etc.)
   - Zero pbx-web-build executions

## Implications

This finding suggests that:
- The `pbx-web-build` template may be configured but not integrated with a sensor/trigger
- The build process for pbx-web may be handled outside of Argo Workflows
- The template may be a placeholder or awaiting configuration
- There may be a missing sensor configuration (unlike `spaxel-sensor` which triggers spaxel-build)

## Output

Raw JSON saved to: `~/scratch/pbx-web-raw-30d.json`

```json
{
  "items": [],
  "query_metadata": {
    "workflow_template": "pbx-web-build",
    "template_created": "2026-05-27T02:25:59Z",
    "query_date": "2026-08-06",
    "time_range": "2026-07-07 to 2026-08-06 (30 days)",
    "finding": "No pbx-web-build workflows have ever been executed despite WorkflowTemplate existing for over 2 months"
  }
}
```

## Recommendation

Investigate why pbx-web-build is not being triggered:
1. Check for missing EventBus/Sensor configuration
2. Verify if pbx-web deployments use alternative build mechanism
3. Review declarative-config for pbx-web-build integration
