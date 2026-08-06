# Action Execution Step Vocabulary

This document describes the action execution step vocabulary for the Action Execution Model. Steps are deterministic operations that execute as part of action workflows through GitOps patterns or read-only status checks.

## Overview

The Action Execution Model implements a step-based workflow system where:

- **No LLM calls**: Execution is fully deterministic
- **GitOps mutations**: All mutations execute as declarative-config GitOps edits (commit + push)
- **Read-only checks**: Status checks use kubectl proxies and ArgoCD read-only APIs
- **Progress streaming**: Each step outcome streams to canvas via SSE
- **Failure handling**: Failed steps halt the workflow

## Step Types

Steps are categorized into **mutating** (respect dry_run) and **read-only** operations.

### Mutating Steps

These steps modify state and respect the `dry_run` flag in ExecutionContext.

#### `ci_status`

**Purpose**: Check CI/workflow status. Gates the workflow if CI is not green.

**Implementation**: Queries Argo Workflows API for latest workflow with project label.

**Parameters** (from ExecutionContext):
- `project_slug`: Project label to filter workflows
- `cluster`: Cluster name for logging context

**Returns**:
```python
{
    "status": "success" | "failed" | "running" | "pending" | "error" | "no_workflows",
    "phase": "Succeeded" | "Failed" | "Running" | "Pending" | "Error" | "Unknown",
    "workflow_name": str,
    "created_at": str,
    "message": str,
    "cluster": str,
    "project_slug": str
}
```

**Example**:
```yaml
workflows:
  deploy:
    steps:
      - ci_status  # Halts workflow if CI is not green
```

**Error cases**:
- Kubeconfig not found → returns `{"status": "skipped"}`
- kubectl command fails → returns `{"success": false, "error": "..."}`
- No workflows found → returns `{"status": "no_workflows"}`

---

#### `image_tag`

**Purpose**: Resolve image tag/digest from CI. Never returns `:latest` — always a specific tag or digest.

**Implementation**: Extracts image information from CI workflow output/metadata.

**Parameters** (from ExecutionContext):
- `ci_status_result`: Optional result from CIStatusStep execution
- `project_slug`: Used to build registry path

**Returns**:
```python
{
    "tag": str,  # Never "latest" or ":latest"
    "registry_path": str,  # e.g., "ronaldraygun/myapp:v1.2.3"
    "digest": str | None,  # Present if tag is a digest
    "project_slug": str
}
```

**Example**:
```yaml
workflows:
  deploy:
    steps:
      - ci_status
      - image_tag  # Extracts image tag from CI workflow
```

**Error cases**:
- CI status not provided or failed → `{"success": false, "error": "..."}`
- Tag would be `:latest` → Refuses and returns error

---

#### `gitops_commit`

**Purpose**: Templated declarative-config edit. The executor authors the edit (never LLM-authored), commits, and pushes.

**Implementation**: Makes templated field substitutions in declarative-config, commits with standard git identity, pushes to origin.

**Parameters** (from ExecutionContext):
- `repo_path`: Path to repository
- `dry_run`: If True, skips mutation

**Returns**:
```python
{
    "status": "success" | "not_implemented",
    "commit_hash": str | None,
    "repo_path": str
}
```

**Example**:
```yaml
workflows:
  deploy:
    steps:
      - ci_status
      - image_tag
      - gitops_commit  # Updates image tag in manifest
```

**Note**: Current implementation returns `{"status": "not_implemented"}` — requires declarative-config-specific implementation for templated substitutions.

---

### Read-Only Steps

These steps query external systems without mutating any state.

#### `argocd_sync_status`

**Purpose**: Poll ArgoCD until application is Synced/Healthy. Used to verify GitOps sync completion.

**Implementation**: Polls ArgoCD read-only API with timeout and retry logic.

**Parameters** (from ExecutionContext):
- `cluster`: Cluster name for logging
- `argocd_app`: ArgoCD application name (defaults to project_slug)

**Returns**:
```python
{
    "status": "synced" | "timeout" | "unknown",
    "sync_status": str,  # "Synced" | "OutOfSync" | "Unknown"
    "health_status": str,  # "Healthy" | "Degraded" | "Unknown"
    "application": str,
    "cluster": str,
    "duration_seconds": float | None
}
```

**Example**:
```yaml
workflows:
  deploy:
    steps:
      - gitops_commit
      - argocd_sync_status  # Polls until Synced/Healthy
```

**Behavior**:
- Polls every 5 seconds for up to 5 minutes
- Returns `synced` when both sync and health are optimal
- Returns `timeout` if sync doesn't complete in time
- Returns `unknown` if app doesn't exist or is deleted

---

#### `pod_status`

**Purpose**: Get pod health via kubectl proxy. Used for post-sync verification.

**Implementation**: Queries kubectl proxy API for pod information in namespace.

**Parameters** (from ExecutionContext):
- `namespace`: Kubernetes namespace (required)
- `cluster`: Cluster name for proxy lookup

**Returns**:
```python
{
    "total_pods": int,
    "phase_counts": {
        "Running": int,
        "Pending": int,
        "Failed": int,
        "Succeeded": int,
        "Unknown": int
    },
    "pods": [
        {
            "name": str,
            "phase": str,
            "ready": int,
            "total": int,
            "ready_ratio": str  # e.g., "2/2"
        }
    ],
    "namespace": str,
    "cluster": str
}
```

**Example**:
```yaml
workflows:
  deploy:
    steps:
      - argocd_sync_status
      - pod_status  # Verifies pods are running post-sync
```

---

#### `deployment_info`

**Purpose**: Get deployment/statefulset details. Queries workload information without mutations.

**Implementation**: Queries kubectl proxy for Deployments and StatefulSets.

**Parameters** (from ExecutionContext):
- `namespace`: Kubernetes namespace (required)
- `cluster`: Cluster name for proxy lookup

**Returns**:
```python
{
    "deployments": [
        {
            "name": str,
            "replicas": int,
            "ready": int,
            "updated": int
        }
    ],
    "statefulsets": [
        {
            "name": str,
            "replicas": int,
            "ready": int
        }
    ],
    "namespace": str,
    "cluster": str
}
```

**Example**:
```yaml
workflows:
  status_check:
    steps:
      - deployment_info  # Get current workload state
```

---

#### `git_log`

**Purpose**: Get recent git history. Retrieves recent commits for audit trails.

**Implementation**: Runs `git log -10 --oneline` in repository.

**Parameters** (from ExecutionContext):
- `repo_path`: Path to repository (required)

**Returns**:
```python
{
    "commits": [
        {
            "hash": str,
            "message": str
        }
    ],
    "count": int,
    "repo_path": str
}
```

**Example**:
```yaml
workflows:
  audit:
    steps:
      - git_log  # Get last 10 commits
```

---

#### `argocd_apps`

**Purpose**: Get ArgoCD application status. Queries ArgoCD for application information.

**Implementation**: Queries ArgoCD read-only API for applications.

**Parameters** (from ExecutionContext):
- `project_slug`: Optional filter for specific application
- `cluster`: Cluster name for logging

**Returns**:
```python
{
    "applications": [
        {
            "name": str,
            "namespace": str,
            "sync_status": str,
            "health_status": str,
            "operation": dict | None
        }
    ],
    "cluster": str
}
```

**Example**:
```yaml
workflows:
  health_check:
    steps:
      - argocd_apps  # Check application sync/health status
```

---

#### `open_beads`

**Purpose**: Get open beads for project. Queries project tracking system via `bf` CLI.

**Implementation**: Runs `bf list --status open --format json`.

**Parameters** (from ExecutionContext):
- `repo_path`: Repository path (defaults to aide-de-camp workspace)
- `project_slug`: Optional project filter

**Returns**:
```python
{
    "open_beads": [],  # Array of bead objects
    "count": int,
    "repo_path": str,
    "project_filter": str | None
}
```

**Example**:
```yaml
workflows:
  project_status:
    steps:
      - open_beads  # List open tracking beads
```

## ExecutionContext Fields

The `ExecutionContext` contains project configuration and runtime context needed for step execution.

### Core Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `intent_id` | str | Yes | Intent ID for tracking and SSE targeting |
| `session_id` | str | Yes | Session ID for SSE targeting |
| `project_slug` | str \| None | No | Project slug for registry lookup |
| `project_cfg` | dict[str, Any] | No | Project configuration from registry |
| `dry_run` | bool | No | If True, skip mutating operations (default: False) |

### Convenience Properties

These properties extract common values from `project_cfg`:

| Property | Type | Source | Description |
|----------|------|--------|-------------|
| `cluster` | str \| None | `project_cfg["cluster"]` | Cluster name |
| `namespace` | str \| None | `project_cfg["namespace"]` | Kubernetes namespace |
| `repo_path` | str \| None | `project_cfg["repo_path"]` | Repository filesystem path |
| `argocd_app` | str \| None | `project_cfg["argocd_app"]` | ArgoCD application name |

### Example

```python
ctx = ExecutionContext(
    intent_id="intent-abc123",
    session_id="session-xyz789",
    project_slug="myapp",
    project_cfg={
        "cluster": "iad-ci",
        "namespace": "production",
        "repo_path": "/home/coding/myapp",
        "argocd_app": "myapp-deployment"
    },
    dry_run=False
)

# Access convenience properties
assert ctx.cluster == "iad-ci"
assert ctx.namespace == "production"
```

---

## StepResult Fields

The `StepResult` contains the outcome of a single workflow step execution.

### Core Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `step_name` | str | Yes | Name of the step that was executed |
| `status` | StepStatus | Yes | Execution status (see StepStatus below) |
| `output` | dict[str, Any] | No | Step output data (default: {}) |
| `error` | str \| None | No | Error message if step failed |
| `started_at` | float | Yes | Unix timestamp when step started |
| `completed_at` | float \| None | No | Unix timestamp when step completed |
| `duration_ms` | float | No | Step execution duration in milliseconds (default: 0.0) |

### Methods

**`to_dict()`**: Converts result to dictionary for SSE broadcasting.

### Example

```python
result = StepResult(
    step_name="pod_status",
    status=StepStatus.COMPLETED,
    output={
        "total_pods": 3,
        "running": 3,
        "phase_counts": {"Running": 3}
    },
    started_at=1699200000.0,
    completed_at=1699200005.5,
    duration_ms=5500.0
)

# Broadcast to canvas
sse_data = result.to_dict()
```

---

## StepStatus Enumeration

Step execution status follows a state progression:

| Status | String Value | Description |
|--------|-------------|-------------|
| `StepStatus.PENDING` | `"pending"` | Step has not started yet |
| `StepStatus.IN_PROGRESS` | `"in_progress"` | Step is currently executing |
| `StepStatus.COMPLETED` | `"completed"` | Step completed successfully |
| `StepStatus.FAILED` | `"failed"` | Step failed with error |
| `StepStatus.SKIPPED` | `"skipped"` | Step was skipped (e.g., due to dry_run) |

### Status Conventions

- **Initial state**: `PENDING` when step is created
- **Execution**: Set to `IN_PROGRESS` when executor starts
- **Success**: Set to `COMPLETED` with output data populated
- **Failure**: Set to `FAILED` with error message populated
- **Dry run**: Set to `SKIPPED` for mutating steps when `dry_run=True`

### Workflow Impact

- `FAILED`: Halts workflow immediately, subsequent steps not executed
- `COMPLETED`: Proceeds to next step in sequence
- `SKIPPED`: Proceeds to next step (no-op)
- `IN_PROGRESS`: Step is still running (intermediate state)

---

## ActionResult Fields

The `ActionResult` contains the complete execution result for a workflow.

### Core Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `intent_id` | str | Yes | Intent ID for tracking |
| `session_id` | str | Yes | Session ID for SSE targeting |
| `project_slug` | str \| None | No | Project slug that was executed |
| `workflow_name` | str | Yes | Name of the workflow that was executed |
| `status` | str | Yes | Final workflow status: `"running"`, `"completed"`, `"failed"`, `"cancelled"` |
| `steps` | list[StepResult] | No | All step results in execution order (default: []) |
| `started_at` | float | Yes | Unix timestamp when workflow started |
| `completed_at` | float \| None | No | Unix timestamp when workflow completed |
| `duration_ms` | float | No | Workflow execution duration in milliseconds (default: 0.0) |
| `error` | str \| None | No | Error message if workflow failed |

### Methods

**`add_step(step: StepResult)`**: Appends a step result to the steps list.

**`to_dict()`**: Converts result to dictionary for SSE broadcasting.

### Workflow Status Values

| Status | Description |
|--------|-------------|
| `"running"` | Workflow is currently executing (initial state) |
| `"completed"` | All steps completed successfully |
| `"failed"` | One or more steps failed, workflow halted |
| `"cancelled"` | Workflow was cancelled before completion |

---

## Example Workflow Definition

Complete workflow definition in project registry:

```yaml
# config/registry.yaml
projects:
  myapp:
    cluster: iad-ci
    namespace: production
    repo_path: /home/coding/myapp
    argocd_app: myapp-deployment
    
    workflows:
      deploy:
        description: "Deploy application to production"
        steps:
          - ci_status              # Check CI is green
          - image_tag              # Resolve image tag
          - gitops_commit          # Update manifest
          - argocd_sync_status     # Wait for sync
          - pod_status             # Verify pods running
      
      health_check:
        description: "Check application health"
        steps:
          - deployment_info        # Get workload state
          - pod_status             # Check pod status
          - argocd_apps            # Verify ArgoCD sync status
      
      audit:
        description: "Audit deployment state"
        steps:
          - git_log                # Get recent commits
          - argocd_apps            # Check application status
          - open_beads             # List open tracking beads
```

---

## Step Execution Contract

### Step Executor Contract

All step executors must:

1. **Be deterministic** — no LLM calls, no randomness
2. **Complete within timeout** — respect execution time limits
3. **Return clear StepResult** — include status and output/error
4. **Handle errors gracefully** — convert exceptions to StepResult with FAILED status
5. **Respect dry_run flag** — skip mutations when `dry_run=True`

### Execution Flow

For each step execution:

1. ActionExecutor validates step is registered
2. ActionExecutor broadcasts step started event via SSE
3. Step executor runs implementation
4. Step executor returns StepResult
5. ActionExecutor broadcasts step completed event via SSE
6. If step FAILED → workflow halts, subsequent steps not executed

### Error Handling

- **ValidationError**: Missing required fields in ExecutionContext
- **RuntimeError**: Execution failures (kubectl timeout, git error, etc.)
- **ValueError**: Invalid step type or configuration

All errors are converted to StepResult with `status=StepStatus.FAILED` and `error` field populated.

## Step Vocabulary Design Principles

1. **Deterministic Execution**: No LLM calls during step execution
2. **GitOps Mutations Only**: All mutations go through declarative-config commits
3. **Read-Book Proxies**: All read operations use kubectl proxies or read-only APIs
4. **Progress Streaming**: Each step completion broadcasts to canvas via SSE
5. **Failure Halt**: Failed steps stop workflow execution immediately
6. **Idempotent**: Steps can be safely retried without side effects

## Workflow Definition Example

Workflows are defined in project registry entries as sequences of step names:

```yaml
projects:
  my-app:
    cluster: iad-kalshi
    namespace: production
    repo_path: /home/coding/declarative-config
    argocd_app: my-app-prod

    workflows:
      deploy:
        description: "Deploy application to production"
        steps:
          - ci_status          # Gate: verify CI green
          - image_tag          # Get image tag from CI
          - gitops_commit      # Update declarative-config
          - argocd_sync_status # Wait for ArgoCD sync
          - pod_status         # Verify pod health

      status_check:
        description: "Check deployment status without changes"
        steps:
          - deployment_info    # Get deployment info
          - argocd_apps        # Check ArgoCD status
          - pod_status         # Check pod health
          - open_beads         # Get open project beads
```

## Adding New Step Types

When adding a new step type:

1. **Add to step vocabulary**: Document the step in this file
2. **Implement step executor**: Create execute function in `src/action/steps/`
3. **Register in executor**: Add to `_step_executors` dict in `ActionExecutor`
4. **Add to validation**: Add step type to `known_steps` set in registry.py
5. **Write tests**: Add unit tests in `tests/test_action_*.py`

## Step Naming Convention

Step names use snake_case and describe the operation:

- **Noun phrases for queries**: `ci_status`, `pod_status`, `deployment_info`
- **Verb phrases for actions**: `gitops_commit`, `argocd_sync_status`
- **Compound names for specificity**: `argocd_apps`, `open_beads`

## Related Documentation

- [Action Execution Model Plan](../../plan/plan.md#action-execution-model)
- [Project Registry](../../config/registry.yaml)
- [Action Executor Implementation](../src/action/executor.py)
- [Action Models](../src/action/models.py)
