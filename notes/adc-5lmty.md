# Task adc-5lmty: Query last 30 days of pbx-web-build workflows

## Summary
Executed query for pbx-web-build workflows from iad-ci Argo Workflows covering the last 30 days (2026-07-07 to 2026-08-06).

## Approach
1. Verified access to iad-ci cluster via `/home/coding/.kube/iad-ci.kubeconfig`
2. Queried workflows using: `kubectl get workflows -n argo-workflows -l workflows.argoproj.io/workflow-template=pbx-web-build --sort-by=.metadata.creationTimestamp -o json`
3. Searched for workflows by name pattern and label selectors
4. Investigated WorkflowTemplate existence and configuration

## Results
**0 pbx-web-build workflows found**

The pbx-web-build WorkflowTemplate exists but has never been triggered:
- Template created: 2026-05-27T02:25:59Z
- Template type: Manual trigger (not CronWorkflow)
- No workflows in history matching this template

## Deliverables
- `~/scratch/pbx-web-raw-30d.json` - Empty workflow list (valid result)
- `~/scratch/pbx-web-query-summary.md` - Investigation notes and findings

## Context
Only needle-ci workflows have been active in the last 30 days. pbx-web-build appears to be manually triggered only when VERSION changes require rebuild, suggesting intentional on-demand deployment rather than continuous integration.
