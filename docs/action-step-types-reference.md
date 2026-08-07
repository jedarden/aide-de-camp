# Action Execution Step Types - Complete Reference

## Overview

This document provides comprehensive documentation for all 9 action execution step types implemented in aide-de-camp. Each step type includes field definitions, execution behavior, error handling, and concrete examples.

## Step Type Classification

### Read-Only Step Types (6)
These steps query external systems without mutating any state:

1. **deployment_info** - Get deployment/statefulset information from Kubernetes
2. **git_log** - Get recent git history from repository
3. **argocd_apps** - Get ArgoCD application status
4. **open_beads** - Get open beads for project from bead forge
5. **ci_status** - Check CI/workflow status (gates workflow if not green)
6. **pod_status** - Get pod status via kubectl proxy

### Mutating/Gating Step Types (3)
These steps perform state changes or enforce workflow gates:

1. **gitops_commit** - Templated declarative-config edit with git commit
2. **image_tag** - Resolve image tag/digest from CI output
3. **argocd_sync_status** - Poll ArgoCD until Synced/Healthy (blocking gate)

---

## Read-Only Step Types

### 1. deployment_info

Get deployment/statefulset information from Kubernetes cluster via kubectl proxy.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `namespace` | string | Yes | Kubernetes namespace to query |
| `cluster` | string | Yes | Cluster name for proxy lookup |
| `proxy_url` | string | No | Override kubectl proxy URL (auto-detected if None) |
| `timeout` | float | No | HTTP request timeout in seconds (default: 10.0) |

#### Execution Behavior

1. Validates that `namespace` is provided
2. Resolves kubectl proxy URL from cluster configuration
3. Queries Kubernetes API for deployments and statefulsets
4. Returns structured deployment/statefulset information

#### Error Handling

- **Missing namespace**: Returns failed StepResult with error "Namespace is required"
- **No proxy configured**: Returns failed StepResult with cluster-specific error
- **HTTP errors**: Returns failed StepResult with HTTP exception details
- **Timeout**: Returns failed StepResult after timeout expires

#### Example

```python
from src.action.steps.read import PodStatusStep

# Initialize step
step = PodStatusStep(
    proxy_url=None,  # Auto-detect from cluster config
    timeout=10.0,
)

# Execute step
result = await step.execute(
    namespace="production",
    cluster="apexalgo-iad",
    project_cfg={"cluster": "apexalgo-iad", "namespace": "production"}
)

# Success result
# {
#     "success": true,
#     "data": {
#         "total_pods": 3,
#         "phase_counts": {
#             "Running": 2,
#             "Pending": 1,
#             "Failed": 0,
#             "Succeeded": 0,
#             "Unknown": 0
#         },
#         "pods": [
#             {
#                 "name": "app-7d8f9c5b-abc123",
#                 "phase": "Running",
#                 "ready": 1,
#                 "total": 1,
#                 "ready_ratio": "1/1"
#             },
#             {
#                 "name": "app-7d8f9c5b-xyz789",
#                 "phase": "Running",
#                 "ready": 1,
#                 "total": 1,
#                 "ready_ratio": "1/1"
#             },
#             {
#                 "name": "database-migration-12345",
#                 "phase": "Pending",
#                 "ready": 0,
#                 "total": 1,
#                 "ready_ratio": "0/1"
#             }
#         ],
#         "namespace": "production",
#         "cluster": "apexalgo-iad"
#     }
# }
```

### 2. git_log

Get recent git history from repository using git command.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo_path` | string | Yes | Path to git repository |
| `commit_count` | int | No | Number of commits to retrieve (default: 10) |
| `timeout` | int | No | Git command timeout in seconds (default: 10) |

#### Execution Behavior

1. Validates that `repo_path` exists and is a git repository
2. Executes `git log` command with specified parameters
3. Parses git output into structured format
4. Returns commit history with metadata

#### Error Handling

- **Missing repo_path**: Returns failed StepResult with validation error
- **Invalid repository**: Returns failed StepResult if git command fails
- **Timeout**: Returns failed StepResult after timeout expires
- **Parse errors**: Returns failed StepResult with JSON decode error

#### Example

```python
from src.action.steps import execute_git_log_step

# Execute step
result = await execute_git_log_step(
    intent_id="intent-123",
    session_id="session-456", 
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/mta-my-way"
    }
)

# Success result
# {
#     "success": true,
#     "data": {
#         "commits": [
#             {
#                 "hash": "a1b2c3d4e5f6",
#                 "message": "feat: add new trading strategy"
#             },
#             {
#                 "hash": "f6e5d4c3b2a1",
#                 "message": "fix: correct position sizing calculation"
#             },
#             {
#                 "hash": "1a2b3c4d5e6f",
#                 "message": "chore: bump to v1.2.3"
#             }
#         ],
#         "count": 3,
#         "repo_path": "/home/coding/mta-my-way"
#     }
# }
```

### 3. argocd_apps

Get ArgoCD application status from ArgoCD API.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cluster` | string | No | Cluster name for context |
| `project_slug` | string | No | Project slug to filter applications |
| `argocd_app` | string | No | Specific ArgoCD application name |
| `base_url` | string | No | ArgoCD API base URL (from config if None) |
| `timeout` | float | No | HTTP request timeout in seconds (default: 10.0) |

#### Execution Behavior

1. Resolves ArgoCD base URL from configuration
2. Queries ArgoCD API for applications
3. Filters by project_slug or specific app if provided
4. Returns structured application status information

#### Error Handling

- **Missing ArgoCD config**: Returns failed StepResult if base URL not configured
- **HTTP errors**: Returns failed StepResult with HTTP exception details  
- **Authentication errors**: Returns failed StepResult with auth failure details
- **Timeout**: Returns failed StepResult after timeout expires

#### Example

```python
from src.action.steps import execute_argocd_apps_step

# Execute step
result = await execute_argocd_apps_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "apexalgo-iad",
        "argocd_app": "mta-my-way-prod"
    }
)

# Success result
# {
#     "success": true,
#     "data": {
#         "applications": [
#             {
#                 "name": "mta-my-way-prod",
#                 "namespace": "mta-my-way",
#                 "sync_status": "Synced",
#                 "health_status": "Healthy",
#                 "operation": null
#             }
#         ],
#         "cluster": "apexalgo-iad"
#     }
# }
```

### 4. open_beads

Get open beads for project from bead forge using `bf list` command.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo_path` | string | Yes | Path to repository with bead forge |
| `project_slug` | string | No | Project slug filter (optional) |
| `timeout` | int | No | `bf list` command timeout in seconds (default: 10) |

#### Execution Behavior

1. Uses `bf list --status open --format json` command
2. Adds project filter if in aide-de-camp workspace with project_slug
3. Parses JSON output into structured format
4. Returns open bead information

#### Error Handling

- **Missing repo_path**: Falls back to `/home/coding/aide-de-camp`
- **bf command fails**: Returns failed StepResult with command stderr
- **JSON parse errors**: Returns empty list instead of failing
- **Timeout**: Returns failed StepResult after timeout expires

#### Example

```python
from src.action.steps import execute_open_beads_step

# Execute step
result = await execute_open_beads_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/aide-de-camp"
    }
)

# Success result
# {
#     "success": true,
#     "data": {
#         "open_beads": [
#             {
#                 "id": "adc-123abc",
#                 "title": "Add machine learning features",
#                 "status": "open",
#                 "priority": "high",
#                 "created_at": "2026-08-01T10:00:00Z"
#             },
#             {
#                 "id": "adc-456def", 
#                 "title": "Fix position sizing bug",
#                 "status": "open",
#                 "priority": "critical",
#                 "created_at": "2026-08-05T14:30:00Z"
#             }
#         ],
#         "count": 2,
#         "repo_path": "/home/coding/aide-de-camp",
#         "project_filter": "mta-my-way"
#     }
# }
```

### 5. ci_status

Check CI/workflow status from Argo Workflows to gate deployment workflows.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `kubectl_config` | string | No | Path to kubectl config for CI cluster (default: `/home/coding/.kube/iad-ci.kubeconfig`) |
| `project_slug` | string | No | Project label to filter workflows |
| `cluster` | string | No | Cluster name (default: `iad-ci`) |
| `timeout` | int | No | Query timeout in seconds (default: 15) |

#### Execution Behavior

1. Validates kubectl config exists
2. Queries Argo Workflows for recent workflows with project label
3. Gets most recent workflow (last in sorted list)
4. Maps Argo workflow phases to simple status
5. Returns workflow status information

#### Error Handling

- **Missing kubeconfig**: Returns StepResult with success=False but data.status="skipped"
- **No workflows found**: Returns success=True with data.status="no_workflows"
- **kubectl failures**: Returns failed StepResult with command stderr
- **Timeout**: Returns failed StepResult with timeout error
- **Parse errors**: Returns failed StepResult with JSON decode error

#### Example

```python
from src.action.steps.read import CIStatusStep

# Initialize step
step = CIStatusStep(
    kubectl_config="/home/coding/.kube/iad-ci.kubeconfig",
    timeout=15,
)

# Execute step
result = await step.execute(
    project_slug="mta-my-way"
)

# Success result (CI passed)
# {
#     "success": true,
#     "data": {
#         "status": "success",
#         "phase": "Succeeded",
#         "workflow_name": "mta-my-way-build-xyz123",
#         "created_at": "2026-08-06T14:30:00Z",
#         "message": "",
#         "cluster": "iad-ci",
#         "project_slug": "mta-my-way"
#     }
# }

# Success result (CI failed - gates workflow)
# {
#     "success": true,
#     "data": {
#         "status": "failed",
#         "phase": "Failed",
#         "workflow_name": "mta-my-way-build-xyz124",
#         "created_at": "2026-08-06T15:45:00Z",
#         "message": "Build failed: unit tests failed",
#         "cluster": "iad-ci",
#         "project_slug": "mta-my-way"
#     }
# }

# Skipped result (kubeconfig not found)
# {
#     "success": false,
#     "data": {
#         "status": "skipped",
#         "reason": "CI cluster not accessible",
#         "cluster": "iad-ci"
#     },
#     "error": "Kubeconfig not found at /home/coding/.kube/iad-ci.kubeconfig"
# }
```

### 6. pod_status

Get pod status from Kubernetes cluster via kubectl proxy for post-sync verification.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `namespace` | string | Yes | Kubernetes namespace to query |
| `cluster` | string | Yes | Cluster name for proxy lookup |
| `proxy_url` | string | No | Override kubectl proxy URL (auto-detected if None) |
| `timeout` | float | No | HTTP request timeout in seconds (default: 10.0) |

#### Execution Behavior

1. Validates that `namespace` is provided
2. Resolves kubectl proxy URL from cluster configuration
3. Queries Kubernetes API for all pods in namespace
4. Extracts pod phases, container readiness, and counts
5. Returns structured pod status information

#### Error Handling

- **Missing namespace**: Returns failed StepResult with "Namespace is required"
- **No proxy configured**: Returns failed StepResult with cluster-specific error
- **HTTP errors**: Returns failed StepResult with HTTP exception details
- **Timeout**: Returns failed StepResult after timeout expires

#### Example

```python
from src.action.steps import execute_pod_status_step

# Execute step
result = await execute_pod_status_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "apexalgo-iad",
        "namespace": "production"
    }
)

# Success result (all pods running)
# {
#     "success": true,
#     "data": {
#         "total_pods": 3,
#         "running": 3,
#         "pending": 0,
#         "failed": 0,
#         "pod_names": ["app-7d8f9c5b-abc123", "app-7d8f9c5b-xyz789", "app-7d8f9c5b-def456"],
#         "namespace": "production",
#         "cluster": "apexalgo-iad"
#     }
# }

# Success result (some pods not ready)
# {
#     "success": true,
#     "data": {
#         "total_pods": 3,
#         "running": 2,
#         "pending": 1,
#         "failed": 0,
#         "pod_names": ["app-7d8f9c5b-abc123", "app-7d8f9c5b-xyz789", "app-7d8f9c5b-new123"],
#         "namespace": "production",
#         "cluster": "apexalgo-iad"
#     }
# }
```

---

## Mutating/Gating Step Types

### 1. gitops_commit

Perform templated declarative-config edit with git commit and push.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo_path` | string | Yes | Path to git repository |
| `file_path` | string | Yes | Path to manifest file to edit |
| `field_updates` | dict | Yes | Field substitutions to apply |
| `commit_message` | string | Yes | Git commit message |
| `dry_run` | bool | No | Skip actual commit if True (default: False) |

#### Execution Behavior

1. Validates repo_path exists and is git repository
2. Reads manifest file from declarative-config
3. Applies templated field substitutions (YAML/JSON)
4. Writes updated manifest back to file
5. Commits with standard git identity
6. Pushes to origin (unless dry_run)
7. Returns commit information

#### Error Handling

- **Missing repo_path**: Returns failed StepResult with validation error
- **File not found**: Returns failed StepResult with file path error
- **Invalid YAML/JSON**: Returns failed StepResult with parse error
- **Git failures**: Returns failed StepResult with git command stderr
- **Push failures**: Returns failed StepResult with push error

#### Example

```python
from src.action.steps import execute_gitops_commit_step

# Execute step
result = await execute_gitops_commit_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/declarative-config"
    },
    file_path="k8s/apexalgo-iad/mta-my-way/deployment.yaml",
    field_updates={
        "image.tag": "v1.2.3",
        "replicas": 3
    },
    commit_message="chore: bump mta-my-way to v1.2.3",
    dry_run=False
)

# Success result
# {
#     "success": true,
#     "data": {
#         "commit_sha": "abc123def456",
#         "commit_message": "chore: bump mta-my-way to v1.2.3",
#         "files_updated": [
#             "k8s/apexalgo-iad/mta-my-way/deployment.yaml"
#         ],
#         "pushed": true,
#         "branch": "main"
#     }
# }

# Dry run result
# {
#     "success": true,
#     "data": {
#         "status": "skipped",
#         "reason": "dry_run enabled",
#         "would_update": {
#             "file_path": "k8s/apexalgo-iad/mta-my-way/deployment.yaml",
#             "field_updates": {"image.tag": "v1.2.3", "replicas": 3}
#         }
#     }
# }
```

### 2. image_tag

Resolve image tag/digest from CI workflow output, never returning `:latest`.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ci_status_result` | StepResult | Yes | Result from CIStatusStep execution |
| `workflow_name` | string | No | Override workflow name (extracted from ci_result if None) |
| `project_slug` | string | No | Project slug for registry path construction |

#### Execution Behavior

1. Validates ci_status_result is provided and successful
2. Extracts workflow metadata from CI status result
3. Parses image tag from workflow output/artifacts
4. Validates tag is not `:latest` (refuses if so)
5. Constructs registry path from project config
6. Returns image tag and digest information

#### Error Handling

- **Missing ci_result**: Returns failed StepResult with "CI status result not provided"
- **CI result failed**: Returns failed StepResult with dependency error
- **Tag is :latest**: Returns failed StepResult with refusal message
- **Parse failures**: Returns failed StepResult with extraction error

#### Example

```python
from src.action.steps.read import ImageTagStep

# Initialize step
step = ImageTagStep()

# First get CI status
ci_step = CIStatusStep()
ci_result = await ci_step.execute(project_slug="mta-my-way")

# Execute image tag extraction
result = await step.execute(
    ci_status_result=ci_result
)

# Success result
# {
#     "success": true,
#     "data": {
#         "tag": "v1.2.3",
#         "registry_path": "ronaldraygun/mta-my-way:v1.2.3",
#         "digest": "sha256:abc123def456...",
#         "project_slug": "mta-my-way"
#     }
# }

# Success result (digest only)
# {
#     "success": true,
#     "data": {
#         "tag": "sha256:abc123def456",
#         "registry_path": "ronaldraygun/mta-my-way@sha256:abc123def456",
#         "digest": "sha256:abc123def456",
#         "project_slug": "mta-my-way"
#     }
# }

# Failure result (CI failed)
# {
#     "success": false,
#     "data": {},
#     "error": "CI status result not provided or failed"
# }

# Failure result (:latest refused)
# {
#     "success": false,
#     "data": {"tag": "latest"},
#     "error": "Refusing to return :latest tag"
# }
```

### 3. argocd_sync_status

Poll ArgoCD until application reaches Synced/Healthy state (blocking gate).

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cluster` | string | Yes | Cluster name for context |
| `argocd_app` | string | Yes | ArgoCD application name to poll |
| `base_url` | string | No | ArgoCD API base URL (from config if None) |
| `timeout` | int | No | Poll timeout in seconds (default: 300) |
| `poll_interval` | int | No | Seconds between polls (default: 5) |

#### Execution Behavior

1. Resolves ArgoCD base URL from configuration
2. Polls ArgoCD API for application status
3. Checks if both sync_status == "Synced" AND health_status == "Healthy"
4. Returns success when both conditions met
5. Handles Unknown status (app doesn't exist)
6. Times out after max duration with failure

#### Error Handling

- **Missing base URL**: Returns failed StepResult with config error
- **HTTP errors**: Logs warning and retries (resilient polling)
- **App not found**: Returns success with data.status="unknown"
- **Timeout**: Returns StepResult with data.status="timeout"
- **ArgoCD API errors**: Returns failed StepResult with API error

#### Example

```python
from src.action.steps import execute_argocd_sync_status_step

# Execute step
result = await execute_argocd_sync_status_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "apexalgo-iad",
        "argocd_app": "mta-my-way-prod"
    }
)

# Success result (synced and healthy)
# {
#     "success": true,
#     "data": {
#         "status": "synced",
#         "sync_status": "Synced",
#         "health_status": "Healthy",
#         "application": "mta-my-way-prod",
#         "cluster": "apexalgo-iad",
#         "duration_seconds": 15.3
#     }
# }

# Success result (app unknown - doesn't exist)
# {
#     "success": true,
#     "data": {
#         "status": "unknown",
#         "sync_status": "Unknown",
#         "health_status": "Unknown",
#         "application": "mta-my-way-prod",
#         "cluster": "apexalgo-iad"
#     }
# }

# Timeout result (didn't sync in time)
# {
#     "success": false,
#     "data": {
#         "status": "timeout",
#         "reason": "Sync did not complete within timeout",
#         "application": "mta-my-way-prod",
#         "cluster": "apexalgo-iad",
#         "timeout_seconds": 300
#     }
# }
```

---

## Parameters Reference Table

### Common Parameters (All Steps)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `intent_id` | string | Required | Intent ID for tracking and SSE targeting |
| `session_id` | string | Required | Session ID for SSE targeting |
| `project_slug` | string | Optional | Project slug for registry lookup |
| `project_cfg` | dict | {} | Project configuration from registry |

### Read-Only Step Parameters

| Step | Parameter | Type | Required | Default | Description |
|------|-----------|------|----------|---------|-------------|
| **deployment_info** | `namespace` | string | Yes | - | Kubernetes namespace |
| | `cluster` | string | Yes | - | Cluster name |
| | `proxy_url` | string | No | Auto-detect | Override proxy URL |
| | `timeout` | float | No | 10.0 | HTTP timeout |
| **git_log** | `repo_path` | string | Yes | - | Repository path |
| | `commit_count` | int | No | 10 | Number of commits |
| | `timeout` | int | No | 10 | Git timeout |
| **argocd_apps** | `cluster` | string | No | - | Cluster name |
| | `project_slug` | string | No | - | Project filter |
| | `argocd_app` | string | No | - | Specific app name |
| | `timeout` | float | No | 10.0 | HTTP timeout |
| **open_beads** | `repo_path` | string | Yes* | - | Repository path |
| | `project_slug` | string | No | - | Project filter |
| | `timeout` | int | No | 10 | Command timeout |
| **ci_status** | `kubectl_config` | string | No | `/home/coding/.kube/iad-ci.kubeconfig` | Kubeconfig path |
| | `project_slug` | string | No | - | Project filter |
| | `cluster` | string | No | `iad-ci` | Cluster name |
| | `timeout` | int | No | 15 | Query timeout |
| **pod_status** | `namespace` | string | Yes | - | Kubernetes namespace |
| | `cluster` | string | Yes | - | Cluster name |
| | `proxy_url` | string | No | Auto-detect | Override proxy URL |
| | `timeout` | float | No | 10.0 | HTTP timeout |

* `repo_path` falls back to `/home/coding/aide-de-camp` if not provided

### Mutating/Gating Step Parameters

| Step | Parameter | Type | Required | Default | Description |
|------|-----------|------|----------|---------|-------------|
| **gitops_commit** | `repo_path` | string | Yes | - | Repository path |
| | `file_path` | string | Yes | - | Manifest to edit |
| | `field_updates` | dict | Yes | - | YAML/JSON substitutions |
| | `commit_message` | string | Yes | - | Git commit message |
| | `dry_run` | bool | No | False | Skip commit if True |
| **image_tag** | `ci_status_result` | StepResult | Yes | - | CI status result |
| | `workflow_name` | string | No | From CI result | Override workflow |
| | `project_slug` | string | No | From CI result | For registry path |
| **argocd_sync_status** | `cluster` | string | Yes | - | Cluster name |
| | `argocd_app` | string | Yes | - | Application to poll |
| | `timeout` | int | No | 300 | Poll timeout (seconds) |
| | `poll_interval` | int | No | 5 | Seconds between polls |

---

## Usage Patterns

### Pattern 1: Fail-Fast Workflow with CI Gate

```python
from src.action.models import ExecutionContext, ActionResult, StepResult, StepStatus
from src.action.steps.read import CIStatusStep
from src.action.steps import execute_gitops_commit_step, execute_argocd_sync_status_step
import time

async def deploy_with_ci_gate(ctx: ExecutionContext) -> ActionResult:
    """Execute deployment workflow gated by CI status."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="deploy",
        status="running",
        started_at=time.time(),
    )
    
    # Step 1: Check CI status (gate)
    ci_step = CIStatusStep()
    ci_result = await ci_step.execute(
        project_slug=ctx.project_slug
    )
    
    if ci_result.data.get("status") != "success":
        # CI failed - don't proceed
        workflow.status = "failed"
        workflow.error = f"CI gate failed: {ci_result.data.get('phase')}"
        return finalize_workflow(workflow)
    
    workflow.add_step(to_step_result(ci_result, "ci_status"))
    
    # Step 2: Get image tag
    from src.action.steps.read import ImageTagStep
    tag_step = ImageTagStep()
    tag_result = await tag_step.execute(ci_status_result=ci_result)
    workflow.add_step(to_step_result(tag_result, "image_tag"))
    
    # Step 3: GitOps commit
    commit_result = await execute_gitops_commit_step(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        project_slug=ctx.project_slug,
        project_cfg=ctx.project_cfg,
        file_path="k8s/deployment.yaml",
        field_updates={"image.tag": tag_result.data["tag"]},
        commit_message=f"chore: bump to {tag_result.data['tag']}",
        dry_run=ctx.dry_run,
    )
    workflow.add_step(to_step_result(commit_result, "gitops_commit"))
    
    # Step 4: Wait for ArgoCD sync
    sync_result = await execute_argocd_sync_status_step(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        project_slug=ctx.project_slug,
        project_cfg=ctx.project_cfg,
    )
    workflow.add_step(to_step_result(sync_result, "argocd_sync_status"))
    
    workflow.status = "completed" if sync_result.data.get("status") == "synced" else "failed"
    return finalize_workflow(workflow)
```

### Pattern 2: Diagnostic Workflow (Continue on Error)

```python
async def diagnostic_workflow(ctx: ExecutionContext) -> ActionResult:
    """Execute diagnostic checks, collecting all results."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="diagnose",
        status="running",
        started_at=time.time(),
    )
    
    checks = [
        ("pod_status", lambda: execute_pod_status_step(ctx)),
        ("deployment_info", lambda: execute_deployment_info_step(ctx)),
        ("argocd_apps", lambda: execute_argocd_apps_step(ctx)),
    ]
    
    failed = []
    
    for check_name, check_fn in checks:
        try:
            result = await check_fn()
            workflow.add_step(to_step_result(result, check_name))
            if not result.get("success"):
                failed.append(check_name)
        except Exception as e:
            error_result = StepResult(
                step_name=check_name,
                status=StepStatus.FAILED,
                error=str(e),
                started_at=time.time(),
                completed_at=time.time(),
                duration_ms=0,
            )
            workflow.add_step(error_result)
            failed.append(check_name)
    
    # Determine overall status
    if not failed:
        workflow.status = "completed"
    elif len(failed) < len(checks):
        workflow.status = "partial_failure"
        workflow.error = f"Failed checks: {', '.join(failed)}"
    else:
        workflow.status = "failed"
        workflow.error = "All diagnostic checks failed"
    
    return finalize_workflow(workflow)
```

### Pattern 3: Dry Run Execution

```python
async def deploy_with_dry_run(ctx: ExecutionContext) -> ActionResult:
    """Execute deployment with dry-run support."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="safe_deploy",
        status="running",
        started_at=time.time(),
    )
    
    # Read-only steps always execute
    ci_result = await CIStatusStep().execute(project_slug=ctx.project_slug)
    workflow.add_step(to_step_result(ci_result, "ci_status"))
    
    # Mutating steps respect dry_run
    if ctx.dry_run:
        # Create synthetic SKIPPED result
        commit_result = StepResult(
            step_name="gitops_commit",
            status=StepStatus.SKIPPED,
            output={"reason": "dry_run enabled"},
            started_at=time.time(),
            completed_at=time.time(),
            duration_ms=1.0,
        )
    else:
        # Execute actual commit
        commit_result = await execute_gitops_commit_step(ctx)
    
    workflow.add_step(commit_result)
    
    workflow.status = "dry_run" if ctx.dry_run else "completed"
    return finalize_workflow(workflow)
```

---

## Error Handling Summary

### Error Response Structure

All steps return standardized error responses:

```python
{
    "success": False,
    "data": {...},  # Partial context data
    "error": "Error message describing what went wrong"
}
```

### Common Error Categories

| Error Type | Causes | Recovery Strategy |
|------------|--------|-------------------|
| **Validation Errors** | Missing required fields, invalid parameters | Fix input parameters and retry |
| **Configuration Errors** | Missing kubeconfig, cluster config not found | Fix configuration files |
| **Network Errors** | HTTP timeouts, connection failures | Retry with exponential backoff |
| **Authentication Errors** | Invalid credentials, permission denied | Fix authentication setup |
| **Resource Not Found** | Files, namespaces, apps don't exist | Verify resource exists or create it |
| **Timeout Errors** | Operations exceed time limits | Increase timeout or optimize operation |

### Step-Specific Error Handling

| Step | Common Errors | Handling |
|------|---------------|----------|
| **ci_status** | Missing kubeconfig, no workflows found | Returns skipped status, continues workflow |
| **image_tag** | CI failed, tag is :latest | Fails workflow, blocks deployment |
| **gitops_commit** | Git failures, invalid YAML | Fails workflow, requires manual fix |
| **argocd_sync_status** | App not found, sync timeout | Returns unknown/timeout status |
| **deployment_info** | No proxy, invalid namespace | Returns failed with context |
| **pod_status** | No proxy, namespace not found | Returns failed with pod context |

---

## Quick Reference

### Step Type Selection Guide

| Use Case | Recommended Step Type |
|----------|----------------------|
| **Gate workflow on CI** | `ci_status` |
| **Get current deployment state** | `deployment_info` |
| **Verify pods after sync** | `pod_status` |
| **Check ArgoCD sync** | `argocd_sync_status` |
| **Update deployment** | `gitops_commit` |
| **Resolve image tag** | `image_tag` |
| **Get git history** | `git_log` |
| **List open beads** | `open_beads` |
| **Check ArgoCD apps** | `argocd_apps` |

### Execution Order in Typical Deployment Workflow

```
1. ci_status (gate - fail if CI not green)
2. image_tag (resolve from CI output)
3. gitops_commit (update declarative-config)
4. argocd_sync_status (poll until synced)
5. deployment_info (verify deployment)
6. pod_status (post-sync verification)
```

### Return Value Quick Check

| Step | Success Indicator | Key Fields |
|------|------------------|------------|
| **ci_status** | `data.status == "success"` | `phase`, `workflow_name` |
| **image_tag** | `success == True` | `tag`, `registry_path` |
| **gitops_commit** | `success == True` | `commit_sha`, `files_updated` |
| **argocd_sync_status** | `data.status == "synced"` | `sync_status`, `health_status` |
| **deployment_info** | `success == True` | `deployments`, `statefulsets` |
| **pod_status** | `success == True` | `total_pods`, `running` |
| **git_log** | `success == True` | `commits`, `count` |
| **open_beads** | `success == True` | `open_beads`, `count` |
| **argocd_apps** | `success == True` | `applications` |

---

**Document Version:** 1.0  
**Last Updated:** 2026-08-06  
**Maintained By:** aide-de-camp project  
**Related Documents:**
- `docs/action-execution-model-types.md` (Core type definitions)
- `docs/step-result.md` (StepResult detailed documentation)
- `src/action/models.py` (Pydantic model implementations)