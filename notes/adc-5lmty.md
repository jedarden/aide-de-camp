# Task adc-5lmty: pbx-web-build 30-day Workflow Query Results

## Task Completed
Successfully queried the last 30 days of pbx-web-build workflows from iad-ci Argo Workflows.

## Key Findings
**Result: 0 pbx-web-build workflows found**

### Investigation Summary
1. **Workflow Template Status**: The `pbx-web-build` workflow template exists in the argo-workflows namespace (created 2026-05-27)

2. **Workflow Instance Status**: No workflow instances have been created from the pbx-web-build template in the available retention window

3. **Available Workflows**: The namespace contains 27 total workflows dating from 2026-07-27 to 2026-08-06 (10-day retention window)

4. **Template Purpose**: The pbx-web-build template is designed to build pbx-web containers from the jedarden/nixos-asterisk repository (container path: pbx-web)

### Possible Explanations
- The workflow may not have been triggered in the last 30 days
- Argo Workflows may have a retention policy that cleans up completed workflows
- The workflow might be triggered manually rather than on a schedule
- Development may be focused on other components

### Data Saved
Raw JSON output saved to: `~/scratch/pbx-web-raw-30d.json`

The file contains:
- Query metadata (date, namespace, timeframe)
- Findings summary  
- Empty items array (0 workflows)

## Next Steps
This finding suggests that either:
1. pbx-web-build is not actively being built via Argo Workflows
2. Build activity happens outside the Argo Workflows pipeline
3. Workflow retention is shorter than 30 days

Further investigation could check:
- GitHub actions or other CI/CD systems for pbx-web builds
- Manual build processes
- Argo Workflows retention policies
