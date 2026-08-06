# Task adc-1xuwy: Filter Workflows to Last 30 Days

## Task Completed

Filtered workflows from `~/scratch/pbx-web-raw-all.json` to include only workflows from the last 30 days.

## Execution Summary

**Source Data:**
- Fetched 27 workflows from iad-ci cluster via kubectl
- All workflows fell within the 30-day window (2026-07-07 to 2026-08-06)

**Results:**
- **Total workflows filtered:** 27
- **Output file:** `~/scratch/pbx-web-raw-30d.json`
- **Date range:** 2026-07-27 to 2026-08-06 (10 days)
- **File validation:** ✓ Valid JSON

**Key Findings:**
- All available workflows are within the retention period (~10 days)
- Oldest workflow: `gribtract-ci-manual-mbntt` (2026-07-27T18:59:34Z)
- Newest workflow: Multiple from 2026-08-06T16:03:23Z
- Workflow types include: gribtract-ci, warden-build, b2-usage-exporter-build, needle-ci, acb-bots-build

**Verification:**
```bash
# Valid JSON structure confirmed
# Workflow count: 27
# Date range verified within 30-day window
```

## Deliverable Status
✓ Filtered workflow JSON for last 30 days saved to `~/scratch/pbx-web-raw-30d.json`
✓ File verified as valid JSON
✓ Workflow count logged (27 workflows)
