# Deployment Data Extraction - Task Summary

## Task: Extract structured deployment data from workflow JSON

### Findings

**Raw Workflow Data Status:** Empty
- `pbx-web-raw-workflows.json`: Contains empty array (zero workflow runs)
- `whisper-stt-raw-workflows.json`: Contains empty array (zero workflow runs)

**Root Cause:**
- Both `pbx-web-build` and `whisper-stt-build` WorkflowTemplates exist in iad-ci cluster
- However, there are **ZERO** workflow executions for either template in the last 30 days
- Query summaries confirm the workflow templates have never been executed (or runs are outside retention window)

### Solution: Transform Existing ReplicaSet Data

Since no Argo Workflow data exists, I transformed the existing Kubernetes ReplicaSet deployment history into the requested structured format.

**Script Created:** `transform_deployment_data.py`
- Reads existing ReplicaSet deployment data
- Transforms to workflow-style format with: timestamp, image_tag, status, duration_seconds
- Sets duration_seconds to null (ReplicaSets don't have workflow timing data)
- Infers status from replica count (success if replicas > 0, unknown otherwise)

### Output Files Created

1. **pbx-web-deployments-structured.json**
   - 17 deployment records
   - Date range: 2026-05-02 to 2026-07-28
   - Image tags: ronaldraygun/pbx-web:1.0.0 through 1.0.9

2. **whisper-stt-deployments-structured.json**
   - 22 deployment records
   - Date range: 2026-06-14 to 2026-07-12
   - Image tags: ronaldraygun/whisper-stt:1.2.5 through 1.8.6

### Schema Verification

✓ Both files are valid JSON
✓ Each deployment record includes required fields:
  - timestamp (ISO 8601 format)
  - image_tag (container image reference)
  - status (success/unknown)
  - duration_seconds (null - no workflow timing data available)

### Data Limitations

- No workflow execution timing data (duration_seconds is null)
- Status inferred from replica count rather than workflow phase
- Workflow-based deployment tracking is not active for these services
