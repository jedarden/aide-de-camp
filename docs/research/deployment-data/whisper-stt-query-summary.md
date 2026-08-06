# whisper-stt-build Workflow Query Summary

**Query Date:** 2026-08-06  
**Cluster:** iad-ci  
**Namespace:** argo-workflows  
**Time Range:** Last 30 days (since 2026-07-07)

## Findings

### Workflow Template Status
- **Template exists:** ✅ `whisper-stt-build` workflow template is present in the cluster
- **Workflow runs:** ❌ **ZERO** workflow runs found for this template

### Query Results
**Result:** Empty items array (no workflows match the selector)

### Cross-verification
Searched all workflows in argo-workflows namespace and filtered by spec.workflowTemplateRef.name == "whisper-stt-build":
- **Count:** 0 workflows

### Other Active Workflows (for context)
The following workflow templates have active runs in the cluster:
- seam-ci: 5 runs
- needle-ci: 5 runs  
- gribtract-ci: 3 runs
- warden-build: 1 run
- b2-usage-exporter-build: 1 run
- armor-build: 1 run

## Conclusion

The whisper-stt-build workflow template exists but has never been executed (or no runs have occurred in the retention period). This suggests:

1. New template: May have been recently deployed and not yet triggered
2. Manual trigger only: May require manual workflow submission (no CI auto-trigger configured)
3. Build not needed: May be part of a dormant or planned service

## Raw Data
Full workflow query output saved to: whisper-stt-raw-workflows.json (empty result)

## Next Steps

To trigger a whisper-stt-build workflow, use kubectl create with workflowTemplateRef.
