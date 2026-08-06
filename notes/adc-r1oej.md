# Kubectl Field Selector Date Filtering Test

## Task
Test kubectl field selector syntax for filtering workflows by creation date.

## Findings

**Result: FAILED** - kubectl field selectors DO NOT support date comparisons on `metadata.creationTimestamp`

### Test Results

1. **Primary test** - filtering by creationTimestamp:
   ```bash
   kubectl get workflows -n argo-workflows --field-selector=metadata.creationTimestamp>=2026-07-07T13:46:42-04:00
   ```
   **Error:** `invalid selector: 'metadata.creationTimestamp'; can't understand 'metadata.creationTimestamp'`

2. **Control test** - filtering by name:
   ```bash
   kubectl get workflows -n argo-workflows --field-selector=metadata.name=test-workflow
   ```
   **Result:** SUCCESS - field selectors work for other metadata fields

### Conclusion

The kubectl field selector mechanism does not support `metadata.creationTimestamp` for date-based filtering, even though it supports other metadata fields like `metadata.name`. This is a fundamental limitation of the Kubernetes API server's field selector implementation for custom resources like Argo Workflows.

### Recommended Alternatives

Since field selectors cannot be used for date filtering, the recommended approaches are:

1. **jq-based JSON parsing:**
   ```bash
   kubectl get workflows -o json | jq '.items[] | select(.metadata.creationTimestamp < "30-days-ago")'
   ```

2. **Client-side filtering** in scripts with date libraries

3. **Sort-based approaches:**
   ```bash
   kubectl get workflows --sort-by=.metadata.creationTimestamp
   ```

### Test Environment
- Cluster: iad-ci
- Namespace: argo-workflows
- Total workflows: 16
- Test date: 2026-08-06

Full results saved to: `~/scratch/kubectl-field-selector-test.json`
