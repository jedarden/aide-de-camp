# Argo Workflows Query: pbx-web-build History

## Task
Query Argo Workflows in iad-ci cluster for pbx-web-build executions for the last 30 days (2026-07-07 to 2026-08-06).

## Method
- **Command**: `kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows -l workflows.argoproj.io/workflow-template-ref-name=pbx-web-build --sort-by=.metadata.creationTimestamp`
- **Template**: pbx-web-build (exists, created 2026-05-27T02:25:59Z)
- **Timeframe**: 2026-07-07 to 2026-08-06

## Results

**No pbx-web-build workflow executions found in the last 30 days.**

### Investigation Details
- Total workflows in argo-workflows namespace: 20
- WorkflowTemplate `pbx-web-build` exists (created 2026-05-27)
- Zero executions matching the template label in the timeframe
- Zero executions with "pbx-web" in name or template reference

### Recent Workflows in Namespace
Most recent workflows include:
- needle-ci workflows (active, 2026-08-06)
- spaxel-build (running, 2026-08-06)
- mta-my-way-build (failed, 2026-08-06)
- Other CI/build workflows (acm, seam, etc.)

## Conclusion
The pbx-web-build workflow has not been executed in the last 30 days. The workflow template exists but is dormant during this period.

## Files
- Raw output: `/tmp/pbx-web-workflows-raw.txt`
