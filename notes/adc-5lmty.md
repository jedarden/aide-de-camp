# Task adc-5lmty: pbx-web-build 30-Day Workflow Query

## Summary

Query executed to retrieve last 30 days of pbx-web-build workflows from iad-ci Argo Workflows.

## Results

**Finding: No pbx-web-build workflows found in the last 30 days.**

### Query Details
- **Date:** 2026-08-06
- **Window:** Last 30 days (2026-07-07 to 2026-08-06)
- **Cluster:** iad-ci
- **Namespace:** argo-workflows
- **Template:** pbx-web-build (exists, created 2026-05-27)

### Visible Workflows Context
- Total workflows visible: 23
- Oldest workflow: 2026-07-27 (gribtract-ci-manual-mbntt)
- Newest workflow: Various from 2026-08-05

### Analysis
The workflow retention period appears to be approximately 10 days (oldest visible is from 2026-07-27, 10 days ago from 2026-08-06). This suggests:

1. **Short retention policy:** Workflows are cleaned up after ~10 days, which is shorter than the 30-day query window
2. **Infrequent execution:** pbx-web-build may not have been executed in the last 10 days
3. **Manual triggering:** The workflow may only run on-demand rather than on a schedule

### Verification Steps Performed
1. ✓ Verified workflow template exists (pbx-web-build, created 2026-05-27)
2. ✓ Checked all workflows in argo-workflows namespace
3. ✓ Searched for pbx-web related workflow names
4. ✓ Identified oldest workflow timestamp (2026-07-27)
5. ✓ Saved results to ~/scratch/pbx-web-raw-30d.json

### Deliverables
- Raw query results: `~/scratch/pbx-web-raw-30d.json`
- All visible workflows: `~/scratch/pbx-web-all-workflows-visible.json`

### Recommendations
- Check workflow retention policy in workflow controller configuration
- Verify if pbx-web-build is triggered manually or via automation
- Consider alternative data sources for 30-day deployment analysis (e.g., deployment logs, build history)
