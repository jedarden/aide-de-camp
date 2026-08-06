# Kubectl Field Selector Date Filtering Test

**Task:** Test kubectl field selector syntax for filtering workflows by creation date

## Test Results

### Conclusion
**kubectl field selectors do NOT support creationTimestamp filtering on Argo Workflows custom resources.**

### Tests Performed

1. **metadata.creationTimestamp>=DATE** ❌
   - Error: `invalid selector: 'metadata.creationTimestamp'; can't understand 'metadata.creationTimestamp'`
   
2. **creationTimestamp>=DATE** (without metadata prefix) ❌
   - Error: Silent failure with exit code 1
   
3. **status.phase=Succeeded** ❌
   - Error: `field label not supported: status.phase`
   
4. **metadata.name!=nonexistent** ✅
   - Works! Basic metadata.name field selectors are supported

### Root Cause
The Argo Workflow CRD (`argoproj.io/v1alpha1`) does not expose `creationTimestamp` as a queryable field selector. Field selectors on custom resources are limited to a subset of metadata fields defined by the CRD schema.

## Alternative Approaches

Since field selectors don't work, we need alternative methods to filter workflows by age:

1. **Client-side filtering with jq**
   ```bash
   kubectl get workflows -n argo-workflows -o json | \
     jq --arg date "$(date -d '30 days ago' -Iseconds)" \
       '.items[] | select(.metadata.creationTimestamp < $date)'
   ```

2. **Direct JSONPath filtering**
   ```bash
   kubectl get workflows -n argo-workflows -o jsonpath='{.items[?(@.metadata.creationTimestamp < "2026-07-07T13:36:48-04:00")].metadata.name}'
   ```

3. **Custom Python script** (most reliable for complex date arithmetic)

4. **Argo Workflow API** (if available) with time-based queries

## Test Data
- Test date: `2026-07-07T13:36:48-04:00` (30 days ago from 2026-08-06)
- Cluster: iad-ci
- Kubernetes client version: v1.29.6
- Full results: `~/scratch/kubectl-field-selector-test.json`

**Bead:** adc-r1oej
