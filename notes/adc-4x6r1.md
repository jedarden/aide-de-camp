# Task adc-4x6r1: Query pbx-web-build Workflow Runs

## Objective
Query Argo Workflows in iad-ci cluster to retrieve all pbx-web-build workflow runs from the last 30 days.

## Execution Summary

### Query Attempted
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  --sort-by=.metadata.creationTimestamp -o json
```

### Key Findings

**No pbx-web-build workflow runs exist in the cluster.**

#### Root Cause: Cluster Retention Policy

The iad-ci cluster has an aggressive workflow retention policy:
- **Retention period:** ~7-10 days (workflows are automatically deleted after this period)
- **Oldest workflow currently in cluster:** 2026-07-27 (10 days ago from 2026-08-06)
- **Total workflows in cluster:** 34
- **Workflow template exists:** Yes (created 2026-05-27), but no runs within retention window

### Evidence

1. **Template verification:**
   ```bash
   kubectl get workflowtemplate pbx-web-build -n argo-workflows
   # Result: pbx-web-build created 2026-05-27 (71 days ago)
   ```

2. **No runs found:**
   ```bash
   kubectl get workflows -n argo-workflows -o json | \
     jq -r '.items[] | select(.spec.workflowTemplateRef?.name == "pbx-web-build")'
   # Result: No workflows returned
   ```

3. **Cluster age distribution:**
   - Oldest workflow: 2026-07-27 (9 days old)
   - No workflows older than 30 days exist in cluster
   - Active workflows include: spaxel-build, armor-build, needle-ci-verify, acb-build

## Implications

1. **30-day analysis not possible:** The cluster retention policy prevents historical analysis beyond 10 days
2. **External logging required:** For long-term analysis, logs must be stored outside Argo Workflows (Loki, Elasticsearch, etc.)
3. **Template likely unused:** pbx-web-build template exists but shows no recent runs - may be deprecated or rarely triggered

## Recommendations

1. **Check retention policy:** Review Argo Workflows controller configuration for TTL settings
2. **External log aggregation:** If pbx-web-build logs exist in Loki/Elasticsearch, query there instead
3. **Template investigation:** Verify if pbx-web-build is still actively used or can be decommissioned
4. **Policy adjustment:** Consider longer retention for critical workflows if historical analysis is needed

## Deliverables

- Raw findings saved to: `~/scratch/pbx-web-raw-workflows.json`
- This documentation: `notes/adc-4x6r1.md`

## Next Steps

- Query external log sources (Loki/Elasticsearch) if available
- Investigate why pbx-web-build has no recent runs despite template existing
- Consider if this analysis can proceed with a shorter timeframe (e.g., last 7 days)
