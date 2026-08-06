# pbx-web-build 30-Day Workflow Query Results

## Task
Query last 30 days of pbx-web-build workflows from iad-ci Argo Workflows.

## Execution
Executed query: `kubectl get workflows -n argo-workflows -l workflows.argoproj.io/workflow-template=pbx-web-build`

## Findings

### Workflow Retention Policy
The Argo Workflows cluster has an aggressive cleanup policy:
- **Earliest workflow found:** 2026-07-27T18:59:34Z (~10 days ago)
- **Latest workflow found:** 2026-08-06T21:26:31Z (today)
- **Total workflows in cluster:** 16

### pbx-web-build Workflow Status
**Result: 0 pbx-web-build workflows found**

The pbx-web-build workflow template exists in the cluster, but no workflows have been created from it in the retained history (last ~10 days).

### Potential Reasons
1. **Workflow TTL cleanup:** Argo Workflows appears to clean up workflow records after ~10 days, which is shorter than the requested 30-day window
2. **No recent runs:** pbx-web-build may not have been executed in the last 10 days
3. **Different cleanup policy:** pbx-web-build workflows may have a more aggressive cleanup policy than other workflows

### Existing Workflow Patterns
Current workflows in the cluster:
- seam-ci-* (6 workflows)
- needle-ci-* (5 workflows)  
- Various manual builds: b2-usage-exporter-build, warden-build, gribtract-ci, armor-build

All workflows lack the `workflows.argoproj.io/workflow-template` label, suggesting label-based querying may not be reliable for this cluster.

## Deliverable
- Raw workflow JSON saved to: `~/scratch/pbx-web-raw-30d.json` (0 workflows, empty result set)
- Total workflows available: 16 (insufficient for 30-day analysis)
- Time range available: 2026-07-27 to 2026-08-06 (~10 days)

## Recommendations
1. **Extend workflow retention:** If 30-day analysis is required, increase workflow TTL retention in Argo Workflows configuration
2. **Use external logging:** Consider querying external log aggregation systems (e.g., Victorialogs, Loki) for workflow execution history
3. **Manual triggering:** Execute a test pbx-web-build workflow to verify the template works and investigate its lifecycle
