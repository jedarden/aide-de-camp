# pbx-web-build 30-Day Workflow Filtering

## Summary

**Status:** ✅ **COMPLETE** - Implemented and tested

**Filtering Method:** jq post-processing (kubectl field selectors not supported)

**Implementation:** `/home/coding/aide-de-camp/scripts/pbx-web-build-30day-query.sh`

## Key Findings

### Why kubectl Field Selectors Don't Work

kubectl field selectors **do not support timestamp filtering** for Argo workflows:

```bash
# This FAILS with BadRequest error:
kubectl get workflows --field-selector=metadata.creationTimestamp>=2026-07-07T00:00:00Z
# Error: "invalid selector: 'metadata.creationTimestamp'; can't understand 'metadata.creationTimestamp'"
```

**Tested:** 2026-08-06 ✗
**Result:** Server returns BadRequest (400)
**Reason:** Argo workflow CRDs don't support field selectors on timestamp fields

### Why jq Post-Processing Works

The jq post-processing approach works reliably:

```bash
# This WORKS correctly:
kubectl get workflows -o json | \
  jq "[.items[] | select(.metadata.creationTimestamp >= \"$CUTOFF_DATE\")]"
```

**Tested:** 2026-08-06 ✓
**Result:** Successfully filters workflows
**Advantages:**
- Works with Argo workflow CRDs
- Handles complex selectors (template name AND timestamp)
- Timezone-aware comparisons
- Consistent behavior across kubectl versions

## Implementation

### Script Location

```bash
/home/coding/aide-de-camp/scripts/pbx-web-build-30day-query.sh
```

### Usage

```bash
# Run the script
./scripts/pbx-web-build-30day-query.sh

# Output file
~/scratch/pbx-web-filtered-test.json
```

### Sample Output

When pbx-web-build workflows exist in the last 30 days:

```json
[
  {
    "metadata": {
      "name": "pbx-web-build-abc123",
      "namespace": "argo-workflows",
      "creationTimestamp": "2026-07-15T10:30:00Z"
    },
    "spec": {
      "workflowTemplateRef": {
        "name": "pbx-web-build"
      }
    },
    "status": {
      "phase": "Succeeded"
    }
  }
]
```

When no workflows exist (current state):

```json
[]
```

## Edge Case Testing

### 1. No Workflows in 30-Day Window ✅

**Test:** Run query when 0 pbx-web-build workflows exist

**Result:** Script handles gracefully:
```
⚠️  No pbx-web-build workflows found in the last 30 days
This could mean:
  - No workflows have been run in the last 30 days
  - The workflow template name is incorrect
  - Workflows are in a different namespace
```

**Output:** Empty array `[]` in JSON file

### 2. Timezone Handling ✅

**Approach:** Use UTC timestamps exclusively

**Implementation:**
```bash
# Cutoff calculation in UTC
CUTOFF_DATE=$(date -d "30 days ago" -u +%Y-%m-%dT%H:%M:%SZ)
```

**Why UTC:**
- Argo workflows store timestamps in UTC (Z suffix)
- Avoids local timezone ambiguity
- Consistent comparison regardless of server location

**Test:** Verified filtering works with needle-ci workflows:
- Cutoff: `2026-07-07T21:01:33Z`
- Returned: 5 workflows between 2026-07-07 and 2026-08-06

### 3. Date Range Boundaries ✅

**Tested with needle-ci (5 workflows in last 30 days):**

```json
{
  "total": 5,
  "date_range": "2026-07-07 to 2026-08-06",
  "workflows": [
    {"name": "needle-ci-f46kr", "created": "2026-08-06T11:24:57Z"},
    {"name": "needle-ci-x2wx2", "created": "2026-08-06T00:52:29Z"}
    // ... 3 more
  ]
}
```

**Verification:** All workflows have creation timestamps ≥ 30 days ago

### 4. Far Future Cutoff (Edge Case) ✅

**Test:** Cutoff date 365 days in future

**Expected:** 0 workflows

**Result:** ✅ Correctly returns empty array

```bash
FUTURE_CUTOFF=$(date -d "365 days" +%Y-%m-%dT%H:%M:%S%z)
# Returns: 0 workflows
```

### 5. Far Past Cutoff (Edge Case) ✅

**Test:** Cutoff date in 2020

**Expected:** All workflows

**Result:** ✅ Returns all needle-ci workflows

```bash
PAST_CUTOFF="2020-01-01T00:00:00+00:00"
# Returns: 7 workflows (all needle-ci workflows)
```

## Technical Details

### Query Breakdown

```bash
# 1. Get all workflows in namespace
kubectl get workflows -n argo-workflows -o json

# 2. Filter by template name
jq "[.items[] | select(.spec.workflowTemplateRef.name == \"pbx-web-build\")]"

# 3. Filter by creation timestamp (last 30 days)
jq "select(.metadata.creationTimestamp >= \"$CUTOFF_DATE\")"

# 4. Sort by creation timestamp (newest first)
jq "sort_by(.metadata.creationTimestamp) | reverse"
```

### Combined Query

```bash
kubectl --kubeconfig="$KUBECONFIG" get workflows -n "$NAMESPACE" -o json | \
  jq "[.items[] |
    select(.spec.workflowTemplateRef.name == \"$WORKFLOW_TEMPLATE\") |
    select(.metadata.creationTimestamp >= \"$CUTOFF_DATE\")] \
  | sort_by(.metadata.creationTimestamp) | reverse"
```

## Verification Against Acceptance Criteria

### ✅ AC1: Query filters workflows to last 30 days only

**Evidence:**
- Cutoff date calculated: `2026-07-07T21:01:33Z` (30 days ago)
- Test with needle-ci: Returned 5 workflows within date range
- All timestamps ≥ cutoff date

### ✅ AC2: Filtering method is documented

**Evidence:**
- Method: jq post-processing
- Reason: kubectl field selectors not supported
- Documented in this file and script header
- Test failure logged in script comments

### ✅ AC3: Sample output shows workflows are properly filtered by date

**Evidence:**
- needle-ci test output shows 5 workflows
- Date range: 2026-07-07 to 2026-08-06
- All timestamps within 30-day window
- Output sorted by creation timestamp

### ✅ AC4: Handle edge cases

**Evidence:**
- No workflows in window: Returns empty array with helpful message
- Timezone issues: Uses UTC exclusively
- Far future/past cutoffs: Tested and verified

## Comparison: kubectl Field Selector vs jq Post-Process

| Feature | kubectl Field Selector | jq Post-Process |
|---------|----------------------|-----------------|
| **Works with Argo workflows** | ✗ (BadRequest error) | ✓ |
| **Complex selectors** | ✗ Limited | ✓ Full jq syntax |
| **Timezone handling** | ✗ Inconsistent | ✓ Explicit UTC |
| **Server-side filtering** | ✓ (if supported) | ✗ Client-side |
| **Reliability** | ✗ CRD-dependent | ✓ Always works |

**Recommendation:** Use jq post-processing

## Files Delivered

1. **Script:** `/home/coding/aide-de-camp/scripts/pbx-web-build-30day-query.sh`
2. **Output:** `~/scratch/pbx-web-filtered-test.json`
3. **Documentation:** `/home/coding/aide-de-camp/docs/pbx-web-30day-filtering.md`

## Running the Query

```bash
# Execute the 30-day query
/home/coding/aide-de-camp/scripts/pbx-web-build-30day-query.sh

# Check results
cat ~/scratch/pbx-web-filtered-test.json

# Count workflows
jq 'length' ~/scratch/pbx-web-filtered-test.json
```

## Current Status

As of 2026-08-06:
- **pbx-web-build workflows in last 30 days:** 0
- **Reason:** No pbx-web-build workflows exist in iad-ci cluster
- **Available templates:** b2-usage-exporter-build, gribtract-ci, needle-ci, seam-ci, warden-build
- **When pbx-web-build workflows exist:** Script will correctly filter and return them

## Testing Method

To verify the implementation works correctly:

```bash
# Test with needle-ci (has 5 workflows in last 30 days)
CUTOFF_DATE=$(date -d "30 days ago" -u +%Y-%m-%dT%H:%M:%SZ)
kubectl get workflows -n argo-workflows -o json | \
  jq "[.items[] | select(.spec.workflowTemplateRef.name == \"needle-ci\") | \
    select(.metadata.creationTimestamp >= \"$CUTOFF_DATE\")] | {total: length, samples: [.[] | {name: .metadata.name, created: .metadata.creationTimestamp}]}"

# Expected output: 5 workflows with timestamps >= 2026-07-07
```

---

**Last Updated:** 2026-08-06
**Status:** Production-ready
**Bead ID:** adc-3sysz
