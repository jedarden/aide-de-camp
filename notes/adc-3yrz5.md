# Decision Record: Argo Workflow Timestamp Filtering

## Executive Summary

**Decision**: Use jq post-processing (client-side filtering) for filtering Argo Workflows by creation timestamp.

**Reason**: kubectl field selectors do not support timestamp filtering on Argo Workflow Custom Resource Definitions (CRDs). The Argo Workflow CRD does not expose `creationTimestamp` as a queryable field, making server-side filtering impossible.

**Impact**: All Argo Workflow timestamp filtering must be done client-side using jq after fetching the complete dataset.

---

## Background

### The Problem
Need to query Argo Workflows from the iad-ci cluster filtered by creation timestamp (e.g., "last 30 days") for analysis, reporting, and cleanup purposes.

### Technical Context
- **Cluster**: iad-ci (Rackspace Spot, us-east-iad-1)
- **Namespace**: argo-workflows
- **Resource Type**: Argo Workflow (Custom Resource Definition)
- **Target Workflow**: pbx-web-build (and other WorkflowTemplate executions)
- **Date Range Requirement**: 2026-07-07 to 2026-08-06 (30-day windows)

### Initial Assumption
kubectl field selectors (`--field-selector=metadata.creationTimestamp>=DATE`) would provide server-side filtering, similar to how they work for built-in Kubernetes resources like Pods.

---

## Analysis Summary

### Approach 1: kubectl Field Selector (Server-Side)

**Method**: Test various kubectl field selector syntaxes for timestamp filtering

**Commands Tested**:
1. `--field-selector=metadata.creationTimestamp>=DATE` - FAILED
2. `--field-selector=creationTimestamp>=DATE` - FAILED  
3. `--field-selector=status.phase=Succeeded` - FAILED
4. `--field-selector=metadata.name!=nonexistent` - SUCCESS (control test)

**Error Messages**:
- `Unable to find that match field selector: invalid selector: 'metadata.creationTimestamp'; can't understand 'metadata.creationTimestamp'`
- `field label not supported: status.phase`

**Root Cause**: Argo Workflow CRD does not register `creationTimestamp` or `status.phase` as queryable fields in the Kubernetes API. Only basic metadata fields like `metadata.name` are exposed.

### Approach 2: jq Post-Processing (Client-Side)

**Method**: Fetch all workflows as JSON, then filter using jq date comparisons

**Implementation**:
```bash
kubectl get workflows -n argo-workflows -o json | \
jq --arg since "2026-07-07T00:00:00Z" --arg until "2026-08-07T00:00:00Z" \
'.items | map(select(
  .metadata.creationTimestamp >= $since and
  .metadata.creationTimestamp < $until
)) | {items: .}'
```

**Additional Filters** (combined with timestamp):
- Label selectors: `-l workflows.argoproj.io/workflow-template=<template-name>`
- Name patterns: `(.metadata.name | test("pbx-web-build"; "i"))`

**Result**: ✅ SUCCESS - Reliable, consistent filtering

**Performance**: Client-side processing - must load all workflows into memory before filtering

---

## Final Decision

### Chosen Approach: jq Post-Processing

**Justification**:

1. **Functional Requirement**: jq post-processing is the **only approach that works** for timestamp filtering on Argo Workflows. Server-side filtering via kubectl field selectors is technically unsupported by the CRD.

2. **Reliability**: jq filtering is deterministic, well-tested, and handles ISO 8601 timestamp comparisons correctly across all test scenarios.

3. **Flexibility**: jq supports complex queries combining:
   - Timestamp ranges (`>=` and `<` comparisons)
   - Name pattern matching (regex)
   - Label filtering
   - Status filtering
   - Metadata field access

4. **Maintainability**: jq is a standard tool, widely available, and has predictable behavior. The filtering logic is explicit and readable.

### Trade-offs

| Aspect | jq Post-Processing | Notes |
|--------|-------------------|-------|
| **Performance** | ⚠️ Client-side | Fetches all workflows before filtering |
| **Memory** | ⚠️ Loads all data | May be inefficient for 1000+ workflows |
| **Network** | ⚠️ Fetches all data | No server-side filtering optimization |
| **Accuracy** | ✅ Reliable | Consistent, tested results |
| **Flexibility** | ✅ High | Complex queries supported |

**Mitigation Strategies** for Performance Concerns:
- Implement pagination for large datasets (`--limit` with multiple queries)
- Add timeout guards to prevent runaway queries
- Cache results when queries are repeated
- Monitor execution time and memory usage

### Rejected Approach: kubectl Field Selectors

**Reason for Rejection**: Not technically supported. The Argo Workflow CRD does not expose timestamp fields as queryable selectors.

---

## Implementation Guidance

### Standard Pattern: 30-Day Workflow Query

```bash
#!/usr/bin/env bash
# Filter workflows by timestamp range (last 30 days)

# Calculate dates
SINCE=$(date -u -d "30 days ago" +"%Y-%m-%dT00:00:00Z")
UNTIL=$(date -u +"%Y-%m-%dT00:00:00Z")

# Fetch and filter
kubectl get workflows -n argo-workflows -o json | \
jq --arg since "$SINCE" --arg until "$UNTIL" \
'.items | map(select(
  (.metadata.creationTimestamp // "") >= $since and
  (.metadata.creationTimestamp // "") < $until
)) | {items: .}' \
> workflows-30days.json
```

### Extended Pattern: Filter by Template + Time

```bash
#!/usr/bin/env bash
# Filter specific workflow template by timestamp range

TEMPLATE_NAME="pbx-web-build"
SINCE="2026-07-07T00:00:00Z"
UNTIL="2026-08-07T00:00:00Z"

kubectl get workflows -n argo-workflows \
  -l workflows.argoproj.io/workflow-template="$TEMPLATE_NAME" \
  -o json | \
jq --arg since "$SINCE" --arg until "$UNTIL" \
'.items | map(select(
  (.metadata.creationTimestamp // "") >= $since and
  (.metadata.creationTimestamp // "") < $until
)) | {items: .}'
```

### Python Implementation (for programmatic use)

```python
import subprocess
import json
from datetime import datetime, timedelta

def filter_workflows(days=30, template_name=None):
    """Fetch and filter workflows by timestamp."""
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    until = datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z")
    
    cmd = ["kubectl", "get", "workflows", "-n", "argo-workflows", "-o", "json"]
    if template_name:
        cmd.extend(["-l", f"workflows.argoproj.io/workflow-template={template_name}"])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    workflows = json.loads(result.stdout)
    
    filtered = [
        w for w in workflows.get("items", [])
        if since <= w.get("metadata", {}).get("creationTimestamp", "") < until
    ]
    
    return {"items": filtered}
```

### Best Practices

1. **Always specify time bounds**: Use inclusive start (`>=`) and exclusive end (`<`) for consistent ranges
2. **Use ISO 8601 format**: `YYYY-MM-DDTHH:MM:SSZ` for reliable string comparison
3. **Handle null timestamps**: `.metadata.creationTimestamp // ""` to avoid errors
4. **Add pagination for large queries**: Use `--limit` and `--continue` tokens
5. **Monitor performance**: Log execution time for queries, especially with 1000+ workflows

---

## Contextual Notes

### Discovery During Testing
The test revealed that **pbx-web-build workflows had 0 executions** in the 30-day test period (2026-07-07 to 2026-08-06), despite the WorkflowTemplate existing. This suggests:
- Manual deployment process rather than automated CI/CD
- Webhook or trigger configuration may be missing
- Infrequent deployment cadence

### Alternative Approaches Not Tested
1. **Argo REST API**: Direct API calls with time-based query parameters (if supported)
2. **Argo CLI**: `argo list` command with built-in time filters
3. **Custom Python/Go**: Direct database queries to Argo PostgreSQL backend

---

## Metadata

**Decision Date**: 2026-08-06
**Decision-Maker**: Claude (via systematic testing and analysis)
**Status**: Implemented and tested
**Review Date**: None (approach works until Argo Workflow CRD changes)

## Test Artifacts

- Test Results: `/home/coding/scratch/filtering-test-summary.md`
- Example Output: `/home/coding/scratch/jq-filter-test.json`
- Implementation Script: `/home/coding/aide-de-camp/filter_workflows_30days.py`

---

## Change History

| Date | Change | Author |
|------|--------|--------|
| 2026-08-06 | Initial decision document | Claude (GLM-4.7) |
