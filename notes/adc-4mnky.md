# pbx-web-build Workflow Data Verification Report

## Task
Verify the filtered 30-day dataset is complete and meets expectations.

## File Verified
- **Path:** `~/scratch/pbx-web-raw-30d.json`
- **Size:** 820K
- **Format:** Kubernetes List response (items array)

## Critical Findings

### ❌ FAILED: pbx-web workflows missing
- **Expected:** pbx-web-build workflows
- **Actual:** ZERO pbx-web workflows found
- **Workflows present:** 27 workflows of various other types:
  - needle-ci (7 workflows)
  - seam-ci (3 workflows)  
  - acb-bots-build (4 workflows)
  - acb-build (1 workflow)
  - armor-build (1 workflow)
  - mta-my-way-build (2 workflows)
  - warden-build (1 workflow)
  - spaxel-build (1 workflow)
  - sun-sim-build (1 workflow)
  - b2-usage-exporter-build (1 workflow)
  - gribtract-ci-manual (3 workflows)

### ❌ FAILED: Date range insufficient
- **Expected:** ~30 days of data
- **Actual:** 9-10 days only
  - **Oldest:** 2026-07-27T18:59:34Z
  - **Newest:** 2026-08-06T16:03:23Z
  - **Span:** 10 calendar days (July 27 - August 6)

### ✅ PASSED: Required field completeness
All 27 workflows have required fields:
- `metadata.creationTimestamp` - present (27/27)
- `metadata.name` - present (27/27)
- `status.phase` - present (27/27)

No missing or corrupted entries detected.

## Status Breakdown
```
Running:  5 workflows
Succeeded: 2 workflows
Failed:   18 workflows
Error:    4 workflows
```

## Conclusion
**DATASET IS INCOMPLETE AND INCORRECT**

The file `pbx-web-raw-30d.json` does not contain pbx-web-build workflow data and spans only 10 days instead of 30. This appears to be a different dataset or the query/filter did not execute correctly.

## Recommended Actions
1. Investigate the query/filter logic that produced this dataset
2. Re-run the pbx-web-build workflow collection with correct:
   - Workflow template filter: `pbx-web-build`
   - Date range: actual 30-day window (2026-07-07 to 2026-08-06)
3. Verify the Argo Workflows API query parameters

## Metadata
- **Verification Date:** 2026-08-06
- **Total Workflows Examined:** 27
- **Expected Workflow Type:** pbx-web-build
- **Expected Date Range:** 30 days
