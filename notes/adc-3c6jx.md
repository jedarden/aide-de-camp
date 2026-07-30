# pbx-web Deployment Data Collection (adc-3c6jx)

## Task
Fetch pbx-web deployment logs for last 30 days (2026-06-24 to 2026-07-24).

## Findings
**No pbx-web workflow executions found in the last 30 days.**

### Investigation Details
- **Cluster:** iad-ci
- **Namespace:** argo-workflows
- **Workflow Template:** `pbx-web-build` (exists, created 2026-05-27)
- **Query Method:** kubectl workflow search by name and labels

### Results
- Total deployments found: **0**
- Template exists but has never been executed

### Comparison Context
The `whisper-stt-build` workflow template also exists (created same date as pbx-web-build) but similarly has no workflow runs in the last 30 days.

## Deliverable
Structured JSON data saved to: `~/scratch/pbx-web-deployments-30d.json`

The file contains:
- Query metadata (date range, cluster, namespace)
- Template information
- Empty deployments array (no runs found)
- Summary of findings

## Implications
For the comparative analysis between pbx-web and whisper-stt deployment patterns, both services have **zero deployment activity** in the last 30 days despite having workflow templates defined. This suggests:
1. Manual deployment processes may be in use
2. CI/CD automation may not be active for these services
3. Deployment activity may occur outside the Argo Workflows system
