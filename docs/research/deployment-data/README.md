# Deployment Data Research

This directory contains research data collected from Argo Workflow deployments, used to analyze deployment patterns, track build history, and identify failure modes.

## Purpose

Deployment data files store structured records of CI/CD workflow executions, providing:
- Historical tracking of all container builds and deployments
- Timeline analysis (when builds started, finished, and their duration)
- Success/failure pattern identification
- Image digest and tag tracking for reproducibility audits

## File Schema

Each deployment data file follows this JSON structure:

```json
{
  "workflow_name": "name-of-argo-workflow-template",
  "workflow_run_id": "unique-workflow-run-identifier",
  "creationTimestamp": "2024-08-06T14:23:15Z",
  "phase": "Succeeded|Failed|Error",
  "startedAt": "2024-08-06T14:23:20Z",
  "finishedAt": "2024-08-06T14:28:45Z",
  "duration_seconds": 325,
  "container_image": {
    "repository": "ronaldraygun/container-name",
    "digest": "sha256:abc123...",
    "tag": "v1.2.3",
    "pinned": true
  },
  "git_commit": {
    "sha": "abc123def456...",
    "message": "commit message",
    "author": "jedarden"
  },
  "nodes": [
    {
      "name": "build-step-name",
      "phase": "Succeeded",
      "startedAt": "2024-08-06T14:23:25Z",
      "finishedAt": "2024-08-06T14:28:30Z"
    }
  ]
}
```

## Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `workflow_name` | string | Name of the WorkflowTemplate executed |
| `workflow_run_id` | string | Unique identifier for this workflow run |
| `creationTimestamp` | ISO 8601 | When the workflow was created/submitted |
| `phase` | enum | Final workflow state: `Succeeded`, `Failed`, or `Error` |
| `startedAt` | ISO 8601 | When workflow execution began |
| `finishedAt` | ISO 8601 | When workflow execution completed |
| `duration_seconds` | number | Total execution time in seconds |
| `container_image.repository` | string | Full image repository path |
| `container_image.digest` | string | SHA256 digest of the built image |
| `container_image.tag` | string | Semantic version tag applied |
| `container_image.pinned` | boolean | Whether digest was pinned (not `:latest`) |
| `git_commit.sha` | string | Full git commit SHA built from |
| `git_commit.message` | string | Commit message |
| `git_commit.author` | string | Commit author |
| `nodes` | array | Per-step execution details |

## Validation

### Required Fields Validation

The validation system ensures deployment data completeness through required field checks:

**Standard Format Required Fields:**
- `date` — Deployment date/time (ISO 8601 timestamp)
- `environment` — Deployment environment (e.g., production, staging)
- `region` — Deployment region (e.g., us-east-1, eu-west-1, cluster name)
- `deployment_id` — Unique deployment identifier (replicaSet, deployment name, or generated ID)
- `status` — Deployment status (success, failed, unknown)

**Validation Behavior:**
- Checks all deployment entries for required fields
- Collects all errors across entries (does not stop at first failure)
- Returns `(False, ["Missing required field X in entry Y"])` for missing fields
- Returns `(True, [])` when all required fields are present

**Usage Example:**

```python
from validate_deployment_file import validate_required_fields, map_deployment_to_standard_format

# Map deployment data to standard format
metadata = {
    "service": "pbx-web",
    "namespace": "pbx-web",
    "cluster": "ardenone-cluster"
}

standard_deployments = [
    map_deployment_to_standard_format(deployment, metadata)
    for deployment in deployment_data["deployments"]
]

# Validate required fields
is_valid, errors = validate_required_fields(standard_deployments)

if not is_valid:
    for error in errors:
        print(f"Validation error: {error}")
```

**Testing:**

Run the validation test suite:

```bash
cd /home/coding/aide-de-camp
.venv/bin/python test_required_fields_validation.py
```

Tests cover:
- Missing required field detection
- All required fields present validation
- Multiple entries with missing fields
- Deployment data mapping to standard format
- Integration with real deployment data structure

### Running Validation

Validate deployment data files:

```bash
cd /home/coding/aide-de-camp/docs/research/deployment-data
python validate_deployment_file.py
```

This validates:
- JSON parseability
- Top-level structure completeness
- Deployment array structure
- Required field presence
- Status value validity
- Timestamp format (ISO 8601)
- Duration field types

## Usage

### Extracting data

Data is extracted from the `iad-ci` cluster using kubectl:

```bash
kubectl --kubeconfig=/home/coding/.kube/iad-ci.kubeconfig \
  get workflow <name> -n argo-workflows -o json
```

### Querying and analysis

Parse JSON files with `jq` to filter by time range, workflow type, or failure status:

```bash
# Find all failed workflows
jq 'select(.phase == "Failed")' *.json

# Calculate average build time by workflow
jq -s 'group_by(.workflow_name) | map({name: .[0].workflow_name, avg_duration: (map(.duration_seconds) | add / length)})'
```

### Research output

Analysis results and findings are documented in:
- `docs/research/` — Detailed research notes and findings
- `notes/adc-*.md` — Project-specific observations and patterns

## File Naming Convention

Files are named using the pattern:
```
<workflow-name>-<date>.json
```

Example:
```
whisper-stt-build-2024-08-06.json
pbx-web-build-2024-08-06.json
```

## Data Sources

- **Cluster:** `iad-ci` (Rackspace Spot, us-east-iad-1)
- **Namespace:** `argo-workflows`
- **Templates:** WorkflowTemplates synced from `jedarden/declarative-config`

## Coverage Report

**Generated:** 2026-08-06
**Target Period:** 2026-07-07 to 2026-08-06 (30 days)

### Summary

| Service | CI Workflows Found | Production Deployments | Coverage Days | Status |
|---------|-------------------|------------------------|---------------|---------|
| pbx-web | 0 | 2 | 15 (2026-07-13 to 2026-07-28) | ⚠️ Partial |
| whisper-stt | 0 | 0 | 0 | ❌ No data |

### pbx-web Deployment Analysis

**Data Sources:** Argo Workflows CI + Production Cluster (ardenone-cluster)

**Coverage:**
- Target range: 2026-07-07 to 2026-08-06 (30 days)
- Actual coverage: 2026-07-13 to 2026-07-28 (15 days)
- **Gap:** 15 days of coverage missing from target 30-day window

**Statistics:**
- CI workflows found: 0 (aggressive workflow cleanup policy)
- Production deployments in window: 2
  - 2026-07-13: Initial deployment of revision 14 (ronaldraygun/pbx-web:1.0.9)
  - 2026-07-28: Current active deployment (ronaldraygun/pbx-web:1.0.9)
- Success/Failed/Error: 0/0/0 (CI level), 2/0/0 (production level)

**Root Cause:** No pbx-web-build workflows found in iad-ci cluster due to aggressive cleanup policy (workflows deleted within hours/days) and lack of recent CI builds. Current production image was deployed prior to analysis window.

### whisper-stt Deployment Analysis

**Data Sources:** Argo Workflows CI

**Coverage:**
- Target range: 2026-07-07 to 2026-08-06 (30 days)
- Actual coverage: 0 days
- **Gap:** Complete coverage missing

**Statistics:**
- CI workflows found: 0
- Total deployments: 0
- Success/Failed/Error: 0/0/0

**Root Cause:** No whisper-stt-build workflow instances found. Workflow retention policy appears to be ~9 days. All workflows within the 30-day window have been cleaned up.

### Data Completeness Assessment

All deployment data files contain the required schema fields:
- ✅ Metadata complete (query metadata, timestamps)
- ✅ Findings complete (workflows found, analysis notes)
- ✅ Data structure complete (arrays and objects properly formatted)

### Coverage Gaps & Limitations

1. **Aggressive Workflow Cleanup:** iad-ci cluster deletes workflows within hours/days of completion, preventing historical analysis beyond ~9 days.

2. **No Recent CI Activity:** Both services show no CI workflow executions in the 30-day window, indicating:
   - Production images are stable (no new builds)
   - CI is only run when needed (efficient resource usage)

3. **Alternative Data Sources Recommended:**
   - ArgoCD application sync history
   - declarative-config git commits for deployment manifests
   - Container registry image tags and build dates
   - Kubernetes ReplicaSets in target namespaces

### Recommendations for Future Monitoring

1. **Adjust Workflow TTL:** Increase workflow retention period for historical analysis
2. **External Logging:** Consider WorkflowArchive or external logging for workflow history
3. **Cross-Reference Sources:** Query ArgoCD for deployment history instead of relying solely on workflows
4. **Git History Analysis:** Track declarative-config git commits for deployment triggers

## Related Documentation

- `CLAUDE.md` — CI/CD architecture and workflow templates
- `docs/research/whisper-stt-deployment-schema.md` — Schema documentation examples
- `coverage-report.json` — Detailed coverage analysis (JSON format)
- `validate_deployment_file.py` — Validation functions and tests
