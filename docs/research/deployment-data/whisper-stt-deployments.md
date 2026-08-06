# whisper-stt Deployment Data - Last 30 Days

**Query Date:** 2026-08-06  
**Cluster:** iad-ci  
**WorkflowTemplate:** whisper-stt-build  
**Target Period:** 2026-07-07 to 2026-08-06 (30 days)

## Findings

### No Deployment Data Available

After querying Argo Workflows in the iad-ci cluster, **no whisper-stt-build workflow instances were found** for the last 30 days.

### Investigation Results

1. **Workflow Template Exists:** The `whisper-stt-build` WorkflowTemplate is present and was created 71 days ago.

2. **No Workflow Instances:** Zero workflow instances matching `whisper-stt-build` were found in the cluster.

3. **Workflow Retention:** The oldest workflows in the cluster are only ~9 days old, indicating that Argo Workflows has a cleanup mechanism (likely TTL-based) that removes completed workflows after approximately 9 days.

4. **Implications:** 
   - Either no whisper-stt builds have been triggered in the last 30 days, OR
   - Any builds that did run have been cleaned up by the workflow retention policy

### Cluster Workflow Analysis

- Total workflows in cluster: 27
- Oldest workflow age: ~9 days
- No workflows older than 30 days exist in the cluster

### Conclusion

Deployment history for whisper-stt from the last 30 days is **not retrievable** through Argo Workflows due to the workflow retention policy. Alternative data sources would be needed:
- Container registry tags (ronaldraygun/whisper-stt)
- Git commit history for nixos-asterisk repo
- Argo Workflows audit logs (if enabled)
