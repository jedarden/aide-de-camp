# Decision: Filtering Approach for Argo Workflows

**Decision Date**: 2026-08-06  
**Bead**: adc-2zot3  
**Decision**: **jq post-processing**  
**Confidence**: **HIGH**

---

## Decision

**Use jq post-processing for filtering Argo Workflows by creation timestamp.**

## Justification

### 1. Reliability (Critical Factor)
- **kubectl field selector**: 0/10 - **DOES NOT WORK** for Argo Workflows timestamp filtering
- **jq post-processing**: 9/10 - **100% success rate** across all test categories

**This is not a close call.** The kubectl field selector approach fundamentally cannot work due to CRD architectural limitations - the Argo Workflow CRD does not expose `creationTimestamp` as a queryable field. All attempts result in "Unable to find that match field selector" errors.

### 2. Flexibility
- **jq**: Supports complex boolean logic, multiple filters (name patterns, labels, dates, status)
- **kubectl**: Extremely limited - only basic `metadata.name` field selectors work

### 3. Maintainability
- **jq**: Clear, well-documented syntax with excellent error messages
- **kubectl**: Cryptic error messages ("field label not supported"), silent failures

### 4. CRD Compatibility
- **jq**: 10/10 - Bypasses custom resource field selector limitations, works with any Kubernetes resource
- **kubectl**: 0/10 - Requires CRD to expose specific fields (Argo Workflows does not)

### 5. Edge Case Handling
- **jq**: 8/10 - Handles timezone-aware ISO 8601 timestamps, missing fields with defaults, empty results
- **kubectl**: 2/10 - Silent failures, unclear distinction between "no results" vs "syntax error"

## Acceptable Trade-offs

We are accepting these downsides in exchange for a working solution:

1. **Client-side processing**: Must fetch all workflows before filtering
   - **Acceptable** for small to medium clusters (<1000 workflows)
   - Performance: <1 second for 100 workflows (tested)

2. **Additional dependency**: Requires jq installation
   - **Mitigation**: jq is minimal, stable, and widely available

3. **Memory usage**: Loads entire dataset into memory
   - **Mitigation strategies available**:
     - Use label pre-filtering: `-l workflows.argoproj.io/workflow-template=NAME`
     - Implement pagination: `--limit=500` with multiple calls
     - Cache results for repeated queries

## Implementation Pattern

```bash
#!/bin/bash
NAMESPACE="argo-workflows"
SINCE_DATE="2026-07-07T00:00:00Z"
UNTIL_DATE="2026-08-07T00:00:00Z"
LABEL_FILTER="workflows.argoproj.io/workflow-template=NAME"

kubectl get workflows -n "$NAMESPACE" \
  -l "$LABEL_FILTER" \
  -o json | \
jq --arg since "$SINCE_DATE" --arg until "$UNTIL_DATE" \
  '.items | map(select(
    (.metadata.creationTimestamp // "") >= $since and
    (.metadata.creationTimestamp // "") < $until
  )) | {items: .}'
```

## When to Reconsider

- If workflow count exceeds 1000 and queries run very frequently (>1/minute)
- If memory becomes constrained on query machine
- If sub-second response times become critical

In these cases, investigate Argo REST API as a potential alternative.

---

## Summary

**Winner**: jq post-processing

**Why**: It's the **only approach that actually works**. The kubectl field selector approach is a non-starter due to CRD limitations - no amount of tuning can make it work for timestamp filtering on Argo Workflows.

**Confidence Level**: **HIGH** - Deterministic test results (100% vs 0% success rate) with clear technical constraints. This is not a preference-based decision; it's a functional constraint.
