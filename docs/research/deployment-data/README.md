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

## Related Documentation

- `CLAUDE.md` — CI/CD architecture and workflow templates
- `docs/research/whisper-stt-deployment-schema.md` — Schema documentation examples
