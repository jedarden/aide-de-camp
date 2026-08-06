# Whisper-STT Build Workflow Query Summary

## Query Details
- **Date**: 2026-08-06
- **Cluster**: iad-ci
- **Namespace**: argo-workflows
- **Query**: `kubectl get workflows -n argo-workflows --sort-by=.metadata.creationTimestamp -o json`
- **Filter**: workflows with `whisper-stt-build` template reference

## Findings

### No Whisper-STT Workflows Found
**Result**: 0 workflow runs using the `whisper-stt-build` WorkflowTemplate were found in the iad-ci cluster.

### Current Workflow State
- **Total workflows in namespace**: 15
- **Oldest workflow**: 2026-07-27 (10 days ago)
- **Most recent workflow**: 2026-08-06 (today)

### Workflow Templates Found
The `whisper-stt-build` WorkflowTemplate **does exist** in the cluster:
- Created: 2026-05-27T02:26:47Z
- Status: Available

However, there are no workflow runs using this template in the last 30 days (or at all in the current workflow history).

### Other Active Workflows
The following workflow templates have active runs in the last 30 days:
- needle-ci (5 runs)
- seam-ci (4 runs)
- gribtract-ci (3 runs, manual)
- warden-build (1 run, manual)
- b2-usage-exporter-build (1 run, manual)

## Possible Reasons
1. **No runs in last 30 days**: The whisper-stt-build workflow may not have been executed recently
2. **Retention policy**: Argo Workflows may have a retention policy that cleans up old workflow records (oldest visible is 10 days)
3. **Different deployment**: whisper-stt-build may be deployed from a different CI/CD system or manual process

## Raw Data
All workflow data (15 workflows) saved to: `whisper-stt-raw-workflows.json`

## Recommendation
To investigate whisper-stt-build deployments:
1. Check the nixos-asterisk repo for deployment evidence
2. Verify if builds are happening outside of Argo Workflows
3. Check declarative-config for evidence of whisper-stt-build triggers
4. Consider running whisper-stt-build manually to test the workflow template
