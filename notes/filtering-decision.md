# Filtering Decision Record

**Decision Bead**: adc-34d7r  
**Analysis Bead**: adc-3wh6c  
**Decision Date**: 2026-08-06  
**Analysis Document**: `/home/coding/scratch/filtering-analysis.md`

---

## Decision

**jq Post-Processing** (client-side filtering)

---

## Justification

jq post-processing is the **only viable approach** for filtering Argo Workflows by creation timestamp. The kubectl field selector approach fundamentally cannot work because the Argo Workflow CRD does not expose `creationTimestamp` as a queryable field. All tested kubectl field selector syntaxes failed with "field label not supported" or silent exit code 1 failures.

The choice is not between two working approaches, but between one working approach (jq) and one non-functional approach (kubectl field selectors).

---

## Key Factors

1. **Reliability (9/10)**: jq post-processing actually works and produces consistent results. kubectl field selectors scored 0/10 because they don't work at all.

2. **Flexibility (8/10)**: jq can combine multiple filters (name patterns, labels, dates, status) in a single expression. kubectl field selectors are extremely limited.

3. **Maintainability (8/10)**: jq has clear syntax, excellent documentation, and visible error messages. kubectl field selectors have unclear syntax and silent failures.

4. **CRD Compatibility**: jq bypasses custom resource limitations by filtering client-side. kubectl field selectors require CRD-level field exposure that Argo Workflows doesn't provide.

---

## Trade-offs

**What we're giving up**:
- Server-side filtering efficiency (would have been ideal, but isn't available)
- Minimal dependencies (must install jq in addition to kubectl)
- Theoretical performance on large datasets (but kubectl field selectors don't work anyway)

**What we're gaining**:
- A working, reliable solution
- Flexible filtering capabilities
- Clear, maintainable syntax
- Consistent behavior without silent failures

---

## Edge Cases

**Timezone Handling**:
- ✅ jq correctly handles ISO 8601 timestamps with timezone markers
- ✅ Use UTC consistently (`2026-07-07T00:00:00Z` format)

**Missing Fields**:
- ✅ Handles gracefully with `.metadata.creationTimestamp // ""` default
- ✅ No jq errors on incomplete data

**Empty Results**:
- ✅ Returns `{items: []}` - clear indication of no matches
- ✅ No silent failures

**Large Datasets (1000+ workflows)**:
- ⚠️ Performance concerns with client-side processing
- ⚠️ Mitigation: Use label pre-filtering, pagination, caching

**Invalid Dates**:
- ✅ String comparison works for ISO 8601 format
- ⚠️ Requires proper format (YYYY-MM-DDTHH:MM:SSZ)

---

## Migration

**Current State**: No filtering is implemented yet. This is a greenfield decision.

**Implementation Steps**:
1. Install jq on the iad-ci cluster (if not already present)
2. Implement jq filtering pattern in analysis scripts
3. Test with 30-day window (2026-07-07 to 2026-08-06)
4. Monitor performance metrics
5. If dataset grows beyond 1000 workflows, implement pagination strategy

**No migration needed** - this is a new implementation.

**Rollback Plan**:
- If jq performance becomes problematic, investigate Argo REST API
- If Argo REST API doesn't support server-side filtering, keep jq with pagination
- Final fallback: Direct database queries (if Argo database access becomes available)

---

## Implementation Pattern

```bash
#!/bin/bash
# Standard filtering pattern for Argo Workflows by date range

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

**Performance Optimization** (for large datasets):
```bash
# Use label pre-filtering to reduce dataset size before jq processing
kubectl get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template=NAME \
  --limit=500 \
  -o json | jq '...'
```

---

## Decision Rationale Summary

**Decision**: jq Post-Processing

**Why**: kubectl field selectors cannot filter Argo Workflows by timestamp due to CRD limitations. jq post-processing is the only reliable method that actually works.

**Confidence**: **HIGH** - The analysis is definitive. One approach works, the other doesn't.

**Alternatives Considered**:
- kubectl field selectors: ❌ DOES NOT WORK
- Argo REST API: ⚠️ NOT TESTED (future investigation)
- Direct database queries: ⚠️ NOT AVAILABLE (security concern)

**Review Trigger**: Re-analyze if Argo Workflow CRD adds field selector support for timestamps.

---

**Decision Made By**: Claude (adc-34d7r)  
**Decision Date**: 2026-08-06  
**Implementation Target**: Immediate (no migration needed)  
**Next Review**: When Argo Workflow CRD is upgraded or dataset exceeds 1000 workflows
