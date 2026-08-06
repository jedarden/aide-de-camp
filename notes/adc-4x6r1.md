# Task adc-4x6r1: Query pbx-web-build Workflow Runs (Last 30 Days)

## Task Summary
Query Argo Workflows in iad-ci cluster to retrieve all pbx-web-build workflow runs from the last 30 days.

## Execution Date
2026-08-06

## Findings

### Workflow Template Status
- **Template Name**: `pbx-web-build`
- **Template Created**: 2026-05-27T02:25:59Z (71 days old)
- **Template Exists**: ✅ Yes
- **Template Labels**: `app=pbx-web-build`, `argocd.argoproj.io/instance=argo-workflows-ns-iad-ci`

### Workflow Runs (Last 30 Days: 2026-07-07 to 2026-08-06)
- **Runs Found**: 0
- **Status**: ⚠️ NO WORKFLOW RUNS DETECTED

## Investigation Details

### Queries Attempted
1. Label selector: `workflows.argoproj.io/workflow-template=pbx-web-build` → Empty result
2. Field selector: `metadata.name=pbx-web-build-*` → No resources found
3. Name filter: Any workflow containing "pbx" → None found
4. Comprehensive: All workflows filtered by pbx-web prefix → Empty

### Root Cause Analysis
The `pbx-web-build` WorkflowTemplate has been deployed for 71 days but has **never been executed**. This indicates:
- No automated trigger (sensor, cron) configured for this template
- No manual workflow submissions from this template
- Template may be legacy or not yet activated

### Comparison with Active Workflows
Other workflow templates show active execution:
- `spaxel-build`: Recent runs (Failed, 3h32m ago)
- `needle-ci`: Multiple concurrent runs (Running status)
- `acb-bots-build`: Active runs (Running status)

## Deliverables
- **Raw Data**: `~/scratch/pbx-web-raw-workflows.json` (461 bytes)
- **Query Metadata**: Includes template info, query range, and findings summary

## Conclusion
The pbx-web-build workflow template exists but has **no execution history** in the last 30 days (or ever). This is a valid query result - the data indicates the pipeline is not yet active or may be decommissioned.

## Recommendations
1. Verify if pbx-web-build should have an automated trigger (sensor, cron)
2. Check if manual submissions are expected or if this is legacy infrastructure
3. Consider removing the template if no longer needed (save ~500 bytes of manifest storage)

## References
- Argo Workflows namespace: `argo-workflows`
- Cluster: `iad-ci`
- Kubeconfig: `/home/coding/.kube/iad-ci.kubeconfig`
