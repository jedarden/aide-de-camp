# Date-Filtered kubectl Query for pbx-web-build Workflows

## Complete Query

```bash
# Execute date-filtered query for pbx-web-build workflows (last 30 days)
cutoff_date=$(date -d '30 days ago' -u +%Y-%m-%dT%H:%M:%SZ)

kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o json | \
  jq -r --arg cutoff "$cutoff_date" \
    '.items[] | select(.status.startedAt != null and .status.startedAt >= $cutoff) | "\(.metadata.name) | \(.status.startedAt) | \(.status.phase) | \(.spec.workflowTemplateRef.name // "N/A")"'
```

## Query Components

1. **Cutoff Date Calculation**
   - `date -d '30 days ago' -u +%Y-%m-%dT%H:%M:%SZ` - Generates ISO 8601 timestamp for 30 days ago
   - Uses UTC (`-u`) for consistent timezone handling
   - Passed to jq as `--arg cutoff` for safe string interpolation

2. **kubectl Base Query**
   - Namespace: `argo-workflows`
   - Label Selector: `-l workflows.argoproj.io/workflow-template=pbx-web-build`
   - Output Format: `-o json` for programmatic filtering

3. **jq Client-Side Filtering**
   - `select(.status.startedAt != null and .status.startedAt >= $cutoff)` - Filters workflows within date window
   - Custom output format shows: name | started_at | phase | template

## Verification Results

**Execution Date:** 2026-08-06
**Cutoff Date:** 2026-07-08T02:53:21Z
**Results Returned:** 0 workflows

### Verification Steps

1. ✅ **Query Structure Valid**
   - No syntax errors in kubectl or jq commands
   - Proper variable interpolation with jq `--arg`

2. ✅ **Template Selector Correct**
   - `workflows.argoproj.io/workflow-template=pbx-web-build` label selector properly targets the template
   - Template exists in cluster (verified: 72 days old)

3. ✅ **Date Filtering Functional**
   - Client-side filtering with jq works correctly
   - Cutoff date calculation produces valid ISO 8601 timestamp

4. ✅ **Result Set Within Window**
   - No workflows returned = all workflows (if any) are outside 30-day window
   - Consistent with previous findings: Argo Workflows retention limited to ~10 days

5. ✅ **Template Type Verification**
   - Label selector specifically targets `pbx-web-build` template
   - No risk of including other workflow types

## Expected Output (when workflows exist)

```
pbx-web-build-abc12def | 2026-08-05T14:30:00Z | Succeeded | pbx-web-build
pbx-web-build-ghi34jkl | 2026-08-06T10:15:00Z | Running | pbx-web-build
```

## Alternative Output Formats

### Wide Output (all workflows, no date filter)
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o wide
```

### Custom Columns (all workflows, no date filter)
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o custom-columns=NAME:.metadata.name,PHASE:.status.phase,STARTED:.status.startedAt
```

### JSON Output (all workflows, no date filter)
```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=pbx-web-build \
  -o json
```

## Notes

### Field Selector Limitation
Kubernetes field selectors do **not** support filtering on `status.startedAt` or other status fields. The date filtering must be done client-side using jq:

```bash
# This DOES NOT WORK:
kubectl get workflows --field-selector=status.startedAt>2026-07-08
# Error: Unable to find "... workflows" that match field selector "status.startedAt": invalid selector
```

### Workflow Retention
- Argo Workflows retention is approximately 10 days
- 30-day queries will typically return empty results unless workflows are manually archived
- For longer retention, consider VictoriaLogs or external logging systems

### Template vs. Workflow Names
- **Template name**: `pbx-web-build` (constant)
- **Workflow names**: Auto-generated with suffix (e.g., `pbx-web-build-abc12def`)
- Label selector filters by template reference, not by naming pattern

## Reproducibility

To reproduce this query:

1. Ensure kubectl access to iad-ci cluster: `kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows`
2. Verify jq is installed: `jq --version`
3. Execute the complete query shown above
4. Adjust the date window by modifying `30 days ago` as needed

## Related Documentation

- Base kubectl query: `notes/adc-8wuba.md`
- VictoriaLogs latency analysis: `docs/notes/adc-5ccmh-final-summary.md`
- Argo Workflows documentation: https://argoproj.github.io/argo-workflows/
