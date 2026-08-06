# pbx-web Deployment Data Collection (adc-3c6jx)

## Investigation Summary

Task: Retrieve pbx-web deployment logs for the last 30 days.

## Findings

**Result: No deployment data available for the requested 30-day period.**

### Data Source
- Arg o Workflows in iad-ci cluster
- WorkflowTemplate: `pbx-web-build` (exists, created 2026-05-27)
- Namespace: argo-workflows

### Retention Policy Discovery
- Current retention window: approximately 9 days
- Oldest workflow in system: `gribtract-ci-manual-mbntt` (9 days old, 2026-07-28)
- Total workflows in namespace: 26

### Queries Attempted
1. Label selector: `workflows.argoproj.io/workflow-template=pbx-web-build`
   - Result: 0 workflows
   
2. Name pattern search: workflows starting with or containing "pbx-web"
   - Result: 0 workflows
   
3. Broad search: any workflow containing "pbx"
   - Result: 0 workflows

### Conclusion
The pbx-web-build WorkflowTemplate exists and was created on 2026-05-27, but **no workflow executions are retained** in the current Argo Workflows retention window. This suggests either:
- No pbx-web deployments have been executed in the last 9 days
- Any deployments that did occur have been garbage collected by the TTL policy

## Output
Structured JSON saved to: `~/scratch/pbx-web-deployments-30d.json`

## Recommendations for Future Data Collection
1. Configure Argo Workflow retention policy to keep workflows longer (e.g., 30+ days)
2. Set up external archival of workflow executions to a database or log system
3. Check if workflow data is archived in a log aggregation system (ELK, Loki, etc.)
4. Consider implementing a workflow execution export/logging mechanism in the CI pipeline
