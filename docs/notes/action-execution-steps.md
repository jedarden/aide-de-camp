# Action Execution Step Vocabulary

This document describes the action execution step vocabulary for the Action Execution Model. Steps are deterministic operations that execute as part of action workflows through GitOps patterns or read-only status checks.

## Overview

The Action Execution Model implements a step-based workflow system where:

- **No LLM calls**: Execution is fully deterministic
- **GitOps mutations**: All mutations execute as declarative-config GitOps edits (commit + push)
- **Read-only checks**: Status checks use kubectl proxies and ArgoCD read-only APIs
- **Progress streaming**: Each step outcome streams to canvas via SSE
- **Failure handling**: Failed steps halt the workflow

## Foundation: Core Type System

The Action Execution Model is built on four core data types that define the execution context, results, and status reporting. These types are the foundation for all step implementations.

### ExecutionContext

The `ExecutionContext` contains project configuration and runtime context needed for step execution.

#### Purpose

The `ExecutionContext` is passed to all step executors and provides:
- **Tracking identifiers**: `intent_id` and `session_id` for SSE targeting and logging
- **Project context**: `project_slug` and `project_cfg` for registry lookups and configuration
- **Execution control**: `dry_run` flag to skip mutating operations
- **Convenience accessors**: Properties for commonly used configuration values

#### Lifecycle

1. **Creation**: Created by `ActionExecutor` when starting a workflow
2. **Population**: Fields populated from intent classification and project registry
3. **Usage**: Passed to each step executor during workflow execution
4. **Scope**: Exists only for the duration of a single workflow execution

#### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `intent_id` | `str` | Intent ID for tracking and SSE targeting |
| `session_id` | `str` | Session ID for SSE targeting |

#### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `project_slug` | `Optional[str]` | `None` | Project slug for registry lookup |
| `project_cfg` | `dict[str, Any]` | `{}` | Project configuration from registry |
| `dry_run` | `bool` | `False` | If True, skip mutating operations |

#### Convenience Properties

| Property | Type | Source | Description |
|----------|------|--------|-------------|
| `cluster` | `str \| None` | `project_cfg["cluster"]` | Cluster name |
| `namespace` | `str \| None` | `project_cfg["namespace"]` | Kubernetes namespace |
| `repo_path` | `str \| None` | `project_cfg["repo_path"]` | Repository filesystem path |
| `argocd_app` | `str \| None` | `project_cfg["argocd_app"]` | ArgoCD application name |

#### Type Definition

```python
from src.action.models import ExecutionContext

ctx = ExecutionContext(
    intent_id="int-12345",
    session_id="sess-67890",
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "rs-manager",
        "namespace": "argocd",
        "repo_path": "ardent/declarative-config",
        "argocd_app": "mta-my-way-deploy"
    },
    dry_run=False
)

# Access convenience properties
cluster = ctx.cluster  # "rs-manager"
namespace = ctx.namespace  # "argocd"
```

---

### StepResult

The `StepResult` contains the outcome of a single workflow step execution.

#### Purpose

The `StepResult` captures:
- **Step identification**: Which step was executed
- **Execution status**: Success, failure, or in-progress state
- **Output data**: Structured data returned by the step
- **Error information**: Error messages if execution failed
- **Timing metrics**: Duration and completion timestamps

#### Status Handling

The `status` field follows the `StepStatus` enum progression:
- **IN_PROGRESS**: Set when step starts execution
- **COMPLETED**: Set on successful execution
- **FAILED**: Set on execution error (includes `error` field)
- **SKIPPED**: Set when step is bypassed (e.g., dry_run mode)

#### Data Structure

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `step_name` | `str` | Yes | Name of the step that was executed |
| `status` | `StepStatus` | Yes | Execution status |
| `output` | `dict[str, Any]` | No | Step output data (default: {}) |
| `error` | `str \| None` | No | Error message if step failed |
| `started_at` | `float` | Yes | Unix timestamp when step started |
| `completed_at` | `float \| None` | No | Unix timestamp when step completed |
| `duration_ms` | `float` | No | Step execution duration in milliseconds (default: 0.0) |

#### Methods

**`to_dict()`**: Converts result to dictionary for SSE broadcasting.

#### Type Definition

```python
from src.action.models import StepResult, StepStatus

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

### StepStatus Enumeration (StatusCode)

The `StepStatus` enum defines the valid states for step execution.

#### Purpose

The `StepStatus` enum provides:
- **Type safety**: Ensures only valid status values are used
- **State tracking**: Defines the execution lifecycle of steps
- **Workflow control**: Determines if workflow should continue or halt

#### Status Codes and Semantics

| Status | String Value | Description | Workflow Impact |
|--------|-------------|-------------|-----------------|
| `StepStatus.PENDING` | `"pending"` | Step has not started yet | No impact (initial state) |
| `StepStatus.IN_PROGRESS` | `"in_progress"` | Step is currently executing | No impact (intermediate state) |
| `StepStatus.COMPLETED` | `"completed"` | Step completed successfully | Proceeds to next step |
| `StepStatus.FAILED` | `"failed"` | Step failed with error | **Halts workflow immediately** |
| `StepStatus.SKIPPED` | `"skipped"` | Step was skipped (e.g., dry_run) | Proceeds to next step (no-op) |

#### State Progression

```
PENDING → IN_PROGRESS → COMPLETED
                     → FAILED
                     → SKIPPED
```

**Common transition patterns:**
1. **Success:** `PENDING` → `IN_PROGRESS` → `COMPLETED`
2. **Error:** `PENDING` → `IN_PROGRESS` → `FAILED`
3. **Dry run:** `PENDING` → `SKIPPED`
4. **Conditional skip:** `PENDING` → `SKIPPED` (e.g., gate not met)

#### Type Definition

```python
from src.action.models import StepStatus

# All valid status values
StepStatus.PENDING      # "pending"
StepStatus.IN_PROGRESS # "in_progress"
StepStatus.COMPLETED   # "completed"
StepStatus.FAILED      # "failed"
StepStatus.SKIPPED     # "skipped"

# Usage in StepResult
result = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    # ... other fields
)
```

---

### ActionResult

The `ActionResult` contains the complete execution result for a workflow.

#### Purpose

The `ActionResult` aggregates:
- **Workflow identification**: Which workflow was executed
- **Overall status**: Final workflow state (running, completed, failed, cancelled)
- **Step results**: Collection of all individual step results
- **Timing information**: Workflow-level duration metrics
- **Error context**: Error message if workflow failed

#### Data Structure

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `intent_id` | `str` | Yes | Intent ID for tracking |
| `session_id` | `str` | Yes | Session ID for SSE targeting |
| `project_slug` | `str \| None` | No | Project slug that was executed |
| `workflow_name` | `str` | Yes | Name of the workflow that was executed |
| `status` | `str` | Yes | Final workflow status |
| `steps` | `list[StepResult]` | No | All step results in execution order (default: []) |
| `started_at` | `float` | Yes | Unix timestamp when workflow started |
| `completed_at` | `float \| None` | No | Unix timestamp when workflow completed |
| `duration_ms` | `float` | No | Workflow execution duration in milliseconds (default: 0.0) |
| `error` | `str \| None` | No | Error message if workflow failed |

#### Methods

**`add_step(step: StepResult)`**: Appends a step result to the steps list.

**`to_dict()`**: Converts result to dictionary for SSE broadcasting.

#### Workflow Status Values

| Status | Description |
|--------|-------------|
| `"running"` | Workflow is currently executing |
| `"completed"` | All steps completed successfully |
| `"failed"` | One or more steps failed, workflow halted |
| `"cancelled"` | Workflow was cancelled before completion |

---

## Execution Flow

```
User Utterance
    ↓
Intent Classification (LLM)
    ↓
Action Intent → project_slug + workflow_name
    ↓
ExecutionContext Creation (intent_id, session_id, project_cfg)
    ↓
ActionResult Initialization (status: "running")
    ↓
┌─────────────────────────────────────────────────────┐
│ For each step in workflow.steps:                    │
│                                                       │
│  1. Create StepResult (status: IN_PROGRESS)          │
│  2. Broadcast SSE: ACTION_STEP_STARTED               │
│  3. Execute step implementation                     │
│  4. Update StepResult (status: COMPLETED/FAILED)     │
│  5. Broadcast SSE: ACTION_STEP_COMPLETED             │
│  6. If FAILED: halt workflow, broadcast ACTION_WORKFLOW_FAILED │
│                                                       │
└─────────────────────────────────────────────────────┘
    ↓
All Steps Completed
    ↓
ActionResult Finalization (status: "completed")
    ↓
Broadcast SSE: ACTION_WORKFLOW_COMPLETED
    ↓
Canvas Update (real-time UI feedback)
```

## Step Types

Steps are categorized into **mutating** (respect dry_run) and **read-only** operations.

### Mutating Steps (3 types)

These steps modify state or control workflow execution flow.

#### 1. ci_status

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

**Gate Behavior**:
- **`phase == "Succeeded"`** → Workflow proceeds
- **`phase != "Succeeded"`** → Workflow fails/blocks
- **CI cluster not accessible** → Returns `status: "skipped"` (non-blocking)
- **No workflows found** → Returns `status: "no_workflows"` (non-blocking)

**Implementation**: 
- **Source**: `src/action/steps.py:execute_ci_status_step()`
- **Command**: `kubectl --kubeconfig /home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows -l project={project_slug}`
- **API**: Argo Workflows Kubernetes API in `iad-ci` cluster
- **Filtering**: Most recent workflow by `metadata.creationTimestamp`

**Dry Run Handling**: Still executes the CI status check (read-only), returns same result as normal mode.

**Error Cases**:
- Kubeconfig not found → Returns `status: "skipped"` with warning (non-blocking)
- kubectl timeout → RuntimeError after 15 seconds
- kubectl failure → RuntimeError from stderr
- Workflow parse error → RuntimeError during JSON parsing

---

#### 2. image_tag

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

**Current State**: Returns `{"status": "not_implemented"}` — requires CI-specific implementation.

**Planned Implementation**: Query Argo Workflows or container registry to resolve image references.

**Dry Run Handling**: Executes normally (read-only query), no special handling needed.

**Error Cases**:
- Build not found → Returns error if build_id doesn't exist
- CI API timeout → RuntimeError after timeout
- No image published → RuntimeError if build completed but no image pushed
- Not implemented → Returns `status: "not_implemented"` (current state)

---

#### 3. gitops_commit

**Purpose**: Templated declarative-config edit. The executor authors the edit (never LLM-authored), commits, and pushes.

**Implementation**: Makes templated field substitutions in declarative-config, commits with standard git identity, pushes to origin.

**Parameters** (from ExecutionContext):
- `repo_path`: Path to repository (required)
- `dry_run`: If True, skips mutation
- `template_file`: Path to manifest template within declarative-config
- `substitutions`: Key-value pairs for template substitution
- `commit_message`: Git commit message following project conventions

**Returns**:
```python
{
    "status": "success" | "not_implemented" | "skipped",
    "commit": str | None,  # Commit hash if successful
    "repo_path": str
}
```

**Mutation Behavior** (when implemented):
1. Checkout target branch (default: `main`)
2. Apply template substitutions to manifest file
3. Stage changes with `git add`
4. Commit with standard git identity (`github@jedarden.com`)
5. Push to Forgejo `origin` (GitHub mirror syncs automatically)

**Template Substitution**: Field-level substitution (never structural edits):
- **Image tags**: `image: ronaldraygun/app:v1.0.0` → `image: ronaldraygun/app:v1.2.3`
- **Replica counts**: `replicas: 3` → `replicas: 5`
- **Resource limits**: `memory: "256Mi"` → `memory: "512Mi"`
- **ConfigMap values**: `value: "prod"` → `value: "staging"`

**Current State**: Returns `{"status": "not_implemented"}` — requires declarative-config-specific implementation.

**Dry Run Handling**: Skips all git operations (no checkout, no edit, no commit, no push), returns `status: "skipped"` with planned changes in output.

**Template Safety Constraints**:
- **Field substitution only** - No structural YAML changes
- **Type-preserving** - Numbers stay numbers, strings stay strings
- **No LLM involvement** - Deterministic template engine
- **File-scoped** - Edits only specified files, never multi-file refactors

**Error Cases**:
- repo_path not configured → ValueError if `project_cfg.repo_path` is None
- Repository path does not exist → RuntimeError if path not on disk
- Template file not found → RuntimeError if template_file doesn't exist
- Git operation timeout → RuntimeError during git operations
- Push rejected → RuntimeError if git push fails
- Not implemented → Returns `status: "not_implemented"` (current state)

---

### Read-Only Steps (6 types)

These steps query external systems without mutating any state.

#### 1. argocd_sync_status

**Purpose**: Poll ArgoCD until application is Synced/Healthy. Used to verify GitOps sync completion.

**Implementation**: Polls ArgoCD read-only API with timeout and retry logic.

**Parameters** (from ExecutionContext):
- `cluster`: Cluster name for logging
- `argocd_app`: ArgoCD application name (defaults to project_slug)
- `timeout`: Maximum poll duration (default: 300 seconds / 5 minutes)
- `poll_interval`: Seconds between polls (default: 5 seconds)

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

**Behavior**:
- Polls every 5 seconds for up to 5 minutes
- Returns `synced` when both sync and health are optimal
- Returns `timeout` if sync doesn't complete in time
- Returns `unknown` if app doesn't exist or is deleted

**Implementation**: 
- **Source**: `src/action/steps.py:execute_argocd_sync_status_step()`
- **API**: ArgoCD read-only proxy at `https://argocd-ro-ardenone-manager-ts.ardenone.com:8444`
- **Config**: ArgoCD base URL from `config/registry.yaml`

**Error Cases**:
- ArgoCD API timeout → Network/proxy connectivity issue
- App not found → Returns `status: "unknown"` with `sync_status: "Unknown"`
- Timeout exceeded → Returns `status: "timeout"` after 300 seconds
- ArgoCD base URL not configured → RuntimeError from missing `config/registry.yaml`

---

#### 2. pod_status

**Purpose**: Get pod health via kubectl proxy. Used for post-sync verification.

**Implementation**: Queries kubectl proxy API for pod information in namespace.

**Parameters** (from ExecutionContext):
- `namespace`: Kubernetes namespace (required)
- `cluster`: Cluster name for proxy lookup
- `proxy_url`: Override auto-detected proxy URL (optional)
- `timeout`: HTTP request timeout (default: 10.0 seconds)

**Returns**:
```python
{
    "total_pods": int,
    "running": int,
    "pending": int,
    "failed": int,
    "pod_names": list[str],  # List of pod names
    "namespace": str,
    "cluster": str
}
```

**Implementation**: 
- **Source**: `src/action/steps.py:execute_pod_status_step()`
- **API**: kubectl proxy at `{proxy_url}/api/v1/namespaces/{namespace}/pods`
- **Config**: Cluster proxy from `config/clusters.yaml`

**Error Cases**:
- Namespace not configured → ValueError if `project_cfg.namespace` is None
- Cluster proxy not found → ValueError if cluster lacks proxy in `config/clusters.yaml`
- HTTP timeout → HTTPError from kubectl proxy
- Malformed pod data → Exception during parsing

---

#### 3. deployment_info

**Purpose**: Get deployment/statefulset details. Queries workload information without mutations.

**Implementation**: Queries kubectl proxy for Deployments and StatefulSets.

**Parameters** (from ExecutionContext):
- `namespace`: Kubernetes namespace (required)
- `cluster`: Cluster name for proxy lookup
- `timeout`: HTTP request timeout (default: 10.0 seconds)

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

**Implementation**: 
- **Source**: `src/action/steps.py:execute_deployment_info_step()`
- **API**: 
  - Deployments: `{proxy_url}/apis/apps/v1/namespaces/{namespace}/deployments`
  - StatefulSets: `{proxy_url}/apis/apps/v1/namespaces/{namespace}/statefulsets`
- **Config**: Cluster proxy from `config/clusters.yaml`

**Error Cases**:
- Namespace not configured → ValueError if `project_cfg.namespace` is None
- Cluster proxy not found → ValueError if cluster lacks proxy
- HTTP timeout → HTTPError from kubectl proxy
- RBAC denied → HTTPError 403 if proxy lacks permissions

---

#### 4. git_log

**Purpose**: Get recent git history. Retrieves recent commits for audit trails.

**Implementation**: Runs `git log -10 --oneline` in repository.

**Parameters** (from ExecutionContext):
- `repo_path`: Path to repository (required)
- `commit_limit`: Number of commits to return (default: 10)

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

**Implementation**: 
- **Source**: `src/action/steps.py:execute_git_log_step()`
- **Command**: `git -C {repo_path} log -{limit} --oneline`
- **Parsing**: Splits line by space into hash + message
- **Timeout**: 10 seconds on subprocess execution

**Error Cases**:
- repo_path not configured → ValueError if `project_cfg.repo_path` is None
- Repository path does not exist → RuntimeError if path not on disk
- git command timeout → RuntimeError after 10 seconds
- git log failure → RuntimeError from stderr

---

#### 5. argocd_apps

**Purpose**: Get ArgoCD application status. Queries ArgoCD for application information.

**Implementation**: Queries ArgoCD read-only API for applications.

**Parameters** (from ExecutionContext):
- `project_slug`: Optional filter for specific application
- `cluster`: Cluster name for logging
- `argocd_app`: ArgoCD app name (defaults to `project_slug`)
- `timeout`: HTTP request timeout (default: 10.0 seconds)

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

**Implementation**: 
- **Source**: `src/action/steps.py:execute_argocd_apps_step()`
- **API**: `{argocd_base_url}/api/v1/applications`
- **Config**: ArgoCD base URL from `config/registry.yaml`
- **Filtering**: Client-side filter by `app.metadata.name == argocd_app_name`

**Error Cases**:
- ArgoCD base URL not configured → RuntimeError from missing `config/registry.yaml`
- HTTP timeout → HTTPError from ArgoCD API
- RBAC denied → HTTPError 403 if proxy token lacks permissions
- App not found → Returns empty `applications` list (no error)

---

#### 6. open_beads

**Purpose**: Get open beads for project. Queries project tracking system via `bf` CLI.

**Implementation**: Runs `bf list --status open --format json`.

**Parameters** (from ExecutionContext):
- `repo_path`: Repository path (defaults to `/home/coding/aide-de-camp`)
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

**Implementation**: 
- **Source**: `src/action/steps.py:execute_open_beads_step()`
- **Command**: `bf list --status open --format json --project {project_slug}`
- **Working Directory**: `cwd=repo_path`
- **Parsing**: JSON parse of `bf list` output, falls back to empty list

**Error Cases**:
- bf command not found → RuntimeError if `bf` not in PATH
- bf list timeout → RuntimeError after 10 seconds
- JSON parse error → Returns empty `open_beads` list (no error)
- Repository path does not exist → RuntimeError if path not on disk

---

## Data Structures

### ExecutionContext

The `ExecutionContext` contains project configuration and runtime context needed for step execution.

#### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `intent_id` | `str` | Intent ID for tracking and SSE targeting |
| `session_id` | `str` | Session ID for SSE targeting |

#### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `project_slug` | `Optional[str]` | `None` | Project slug for registry lookup |
| `project_cfg` | `dict[str, Any]` | `{}` | Project configuration from registry |
| `dry_run` | `bool` | `False` | If True, skip mutating operations |

#### Convenience Properties

| Property | Type | Source | Description |
|----------|------|--------|-------------|
| `cluster` | `str \| None` | `project_cfg["cluster"]` | Cluster name |
| `namespace` | `str \| None` | `project_cfg["namespace"]` | Kubernetes namespace |
| `repo_path` | `str \| None` | `project_cfg["repo_path"]` | Repository filesystem path |
| `argocd_app` | `str \| None` | `project_cfg["argocd_app"]` | ArgoCD application name |

#### Example Usage

```python
from src.action.models import ExecutionContext

ctx = ExecutionContext(
    intent_id="int-12345",
    session_id="sess-67890",
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "rs-manager",
        "namespace": "argocd",
        "repo_path": "ardent/declarative-config",
        "argocd_app": "mta-my-way-deploy"
    },
    dry_run=False
)

# Access convenience properties
cluster = ctx.cluster  # "rs-manager"
namespace = ctx.namespace  # "argocd"
```

### StepResult

The `StepResult` contains the outcome of a single workflow step execution.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `step_name` | `str` | Yes | Name of the step that was executed |
| `status` | `StepStatus` | Yes | Execution status |
| `output` | `dict[str, Any]` | No | Step output data (default: {}) |
| `error` | `str \| None` | No | Error message if step failed |
| `started_at` | `float` | Yes | Unix timestamp when step started |
| `completed_at` | `float \| None` | No | Unix timestamp when step completed |
| `duration_ms` | `float` | No | Step execution duration in milliseconds (default: 0.0) |

#### Methods

**`to_dict()`**: Converts result to dictionary for SSE broadcasting.

#### Example

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

### StepStatus Enumeration

Step execution status follows a state progression:

| Status | String Value | Description |
|--------|-------------|-------------|
| `StepStatus.PENDING` | `"pending"` | Step has not started yet |
| `StepStatus.IN_PROGRESS` | `"in_progress"` | Step is currently executing |
| `StepStatus.COMPLETED` | `"completed"` | Step completed successfully |
| `StepStatus.FAILED` | `"failed"` | Step failed with error |
| `StepStatus.SKIPPED` | `"skipped"` | Step was skipped (e.g., due to dry_run) |

#### Status Transition Diagram

```
PENDING → IN_PROGRESS → COMPLETED
                     → FAILED
                     → SKIPPED
```

**Common transition patterns:**
1. **Success:** `PENDING` → `IN_PROGRESS` → `COMPLETED`
2. **Error:** `PENDING` → `IN_PROGRESS` → `FAILED`
3. **Dry run:** `PENDING` → `SKIPPED`
4. **Conditional skip:** `PENDING` → `SKIPPED` (e.g., gate not met)

#### Workflow Impact

- `FAILED`: Halts workflow immediately, subsequent steps not executed
- `COMPLETED`: Proceeds to next step in sequence
- `SKIPPED`: Proceeds to next step (no-op)
- `IN_PROGRESS`: Step is still running (intermediate state)

### ActionResult

The `ActionResult` contains the complete execution result for a workflow.

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `intent_id` | `str` | Yes | Intent ID for tracking |
| `session_id` | `str` | Yes | Session ID for SSE targeting |
| `project_slug` | `str \| None` | No | Project slug that was executed |
| `workflow_name` | `str` | Yes | Name of the workflow that was executed |
| `status` | `str` | Yes | Final workflow status |
| `steps` | `list[StepResult]` | No | All step results in execution order (default: []) |
| `started_at` | `float` | Yes | Unix timestamp when workflow started |
| `completed_at` | `float \| None` | No | Unix timestamp when workflow completed |
| `duration_ms` | `float` | No | Workflow execution duration in milliseconds (default: 0.0) |
| `error` | `str \| None` | No | Error message if workflow failed |

#### Methods

**`add_step(step: StepResult)`**: Appends a step result to the steps list.

**`to_dict()`**: Converts result to dictionary for SSE broadcasting.

#### Workflow Status Values

| Status | Description |
|--------|-------------|
| `"running"` | Workflow is currently executing |
| `"completed"` | All steps completed successfully |
| `"failed"` | One or more steps failed, workflow halted |
| `"cancelled"` | Workflow was cancelled before completion |

---

## Step Execution Contract

### Step Executor Contract

All step executors must:

1. **Be deterministic** — no LLM calls, no randomness
2. **Complete within timeout** — respect execution time limits
3. **Return clear StepResult** — include status and output/error
4. **Handle errors gracefully** — convert exceptions to StepResult with FAILED status
5. **Respect dry_run flag** — skip mutations when `dry_run=True`

### Execution Flow Detail

For each step execution:

1. ActionExecutor validates step is registered
2. ActionExecutor creates StepResult with `status=IN_PROGRESS`
3. ActionExecutor broadcasts `ACTION_STEP_STARTED` event via SSE
4. Step executor runs implementation with ExecutionContext
5. Step executor returns StepResult with updated status
6. ActionExecutor broadcasts `ACTION_STEP_COMPLETED` event via SSE
7. If step FAILED → workflow halts, broadcast `ACTION_WORKFLOW_FAILED`

### Error Handling

All errors are converted to StepResult with `status=StepStatus.FAILED` and `error` field populated:

- **ValidationError**: Missing required fields in ExecutionContext (ValueError)
- **RuntimeError**: Execution failures (kubectl timeout, git error, etc.)
- **HTTPError**: External API failures (kubectl proxy, ArgoCD API)
- **TimeoutError**: Operation exceeded time limits

---

## Usage Examples

### Example 1: Simple Health Check Workflow

A read-only workflow to check application health without mutations:

```yaml
# config/registry.yaml
projects:
  pbx-web:
    cluster: ardenone-cluster
    namespace: pbx-web
    argocd_app: pbx-web
    workflows:
      status:
        description: "Check PBX web service health"
        steps:
          - pod_status           # Get pod status
          - deployment_info      # Get deployment details
          - argocd_apps          # Verify ArgoCD sync status
```

**Usage**: "Check the status of pbx-web"
**Result**: Shows pod counts, deployment replica states, and ArgoCD sync status

### Example 2: Deployment Workflow with CI Gate

A complete deployment workflow that gates on CI and verifies deployment:

```yaml
projects:
  whisper-stt:
    cluster: ardenone-cluster
    namespace: whisper-stt
    argocd_app: whisper-stt
    repo_path: /home/coding/declarative-config
    workflows:
      deploy:
        description: "Deploy Whisper STT service"
        steps:
          - ci_status             # Gate on green CI
          - image_tag             # Resolve image tag
          - gitops_commit         # Update manifest
          - argocd_sync_status    # Wait for sync
          - pod_status            # Verify pods running
```

**Usage**: "Deploy whisper-stt to production"
**Result**: Full CI-to-production pipeline with verification at each step

### Example 3: Audit Workflow

Read-only workflow for deployment state audit:

```yaml
projects:
  declarative-config:
    repo_path: /home/coding/declarative-config
    workflows:
      audit:
        description: "Audit GitOps repository state"
        steps:
          - git_log              # Get recent commits
          - argocd_apps          # Check all application statuses
          - open_beads           # List open tracking beads
```

**Usage**: "Audit the declarative-config repository"
**Result**: Shows recent git activity, application sync states, and open work items

### Example 4: Multi-Cluster Status Check

Check the same application across multiple clusters:

```yaml
projects:
  options-pipeline:
    cluster: rs-manager
    namespace: production
    argocd_app: options-pipeline
    workflows:
      status:
        description: "Check options pipeline health"
        steps:
          - pod_status           # Check pod status
          - deployment_info      # Check deployment state
          - argocd_apps          # Verify ArgoCD sync
```

**Usage**: "Check the status of options-pipeline"
**Result**: Shows health metrics for the production deployment

### Example 5: Diagnostics Workflow

Workflow for troubleshooting deployment issues:

```yaml
projects:
  myapp:
    cluster: iad-ci
    namespace: staging
    argocd_app: myapp-staging
    workflows:
      diagnose:
        description: "Diagnose deployment issues"
        steps:
          - pod_status           # Check pod phases
          - deployment_info      # Check rollout status
          - argocd_apps          # Check sync state
          - git_log              # Check recent changes
```

**Usage**: "Diagnose myapp-staging deployment issues"
**Result**: Provides comprehensive diagnostic data for troubleshooting

## Best Practices

### Workflow Design

1. **Start with CI gates**: Use `ci_status` as the first step to block workflows on failed CI
2. **End with verification**: Use `pod_status` or `deployment_info` as final steps to verify deployment health
3. **Group related steps**: Place mutating steps (`gitops_commit`) immediately before their verification steps (`argocd_sync_status`)
4. **Use read-only steps for monitoring**: Create workflows that only use read-only steps for health checks without side effects
5. **Consider step timeout**: Plan for long-running steps like `argocd_sync_status` (5-minute timeout)

### Error Handling

1. **Validate inputs early**: Check required `project_cfg` fields before starting workflow
2. **Provide meaningful error messages**: Include context (cluster, namespace, step name) in error messages
3. **Use timeouts appropriately**: Set reasonable timeouts for external API calls (10-30 seconds for most operations)
4. **Handle missing infrastructure gracefully**: Return informative errors when clusters/namespaces don't exist
5. **Log step lifecycle**: Use structured logging at step start, completion, and failure

### Configuration Management

1. **Centralize configuration**: Store cluster proxy URLs and ArgoCD endpoints in `config/*.yaml` files
2. **Use convenience properties**: Access `ctx.cluster`, `ctx.namespace` instead of `ctx.project_cfg["cluster"]`
3. **Validate project configuration**: Ensure all required fields are present before step execution
4. **Document required fields**: Clearly document which `project_cfg` fields each step requires
5. **Use consistent naming**: Follow cluster and naming conventions across all projects

### Dry Run Mode

1. **Always respect dry_run**: Mutating steps must skip operations when `ctx.dry_run == True`
2. **Return planned changes**: In dry-run mode, return what WOULD be done in the output
3. **Use dry_run for validation**: Allow users to test workflows without side effects
4. **Document dry_run behavior**: Clearly document which steps respect dry_run and how

### Performance Considerations

1. **Use async operations**: All step implementations should be async for concurrent operations
2. **Set appropriate timeouts**: Balance between waiting for completion and detecting failures
3. **Cache external queries**: Consider caching API responses when appropriate
4. **Minimize external calls**: Batch queries when possible to reduce latency
5. **Monitor step duration**: Track execution time to identify bottlenecks

### Testing

1. **Test step implementations independently**: Unit test each step execution function
2. **Mock external APIs**: Use mock responses for kubectl, ArgoCD, git operations
3. **Test error cases**: Verify error handling for timeouts, missing config, API failures
4. **Test dry_run mode**: Ensure mutating steps skip operations correctly
5. **Test workflow composition**: Verify multi-step workflows execute correctly

### GitOps Conventions

1. **Use standard git identity**: All commits should use `github@jedarden.com` / `jedarden`
2. **Follow commit message conventions**: Use conventional commit format (`chore:`, `fix:`, `feat:`)
3. **Never force-push**: Reconcile with merge commits if needed
4. **Push to Forgejo primary**: Target `git.ardenone.com` as source of truth, GitHub mirror syncs automatically

### SSE Broadcasting

1. **Broadcast step lifecycle**: Send events for step started, step completed, workflow started/completed/failed
2. **Include timing information**: Always include `started_at`, `completed_at`, `duration_ms` in results
3. **Target by session_id**: Use SSE targeting to send updates to the correct user session
4. **Use structured data**: Convert results to dictionaries for consistent serialization

### Project Registry Design

1. **Use descriptive workflow names**: Names should indicate purpose (deploy, status, audit)
2. **Provide workflow descriptions**: Help users understand what each workflow does
3. **Define clear intent support**: Specify which intent types each project supports
4. **Use aliases for common names**: Make projects discoverable by multiple names
5. **Organize workflows logically**: Group related workflows under each project

## Implementation Status

### Fully Implemented Steps (Production Ready)

These steps are fully implemented and tested:

| Step | Status | Notes |
|------|--------|-------|
| `pod_status` | ✅ Complete | Queries kubectl proxy for pod information |
| `deployment_info` | ✅ Complete | Gets Deployment and StatefulSet details |
| `git_log` | ✅ Complete | Retrieves recent git history |
| `argocd_apps` | ✅ Complete | Queries ArgoCD application status |
| `open_beads` | ✅ Complete | Lists open beads via bf CLI |
| `argocd_sync_status` | ✅ Complete | Polls ArgoCD until Synced/Healthy |

### Partially Implemented Steps (Development)

These steps have basic implementation but need enhancement:

| Step | Status | Limitations |
|------|--------|-------------|
| `ci_status` | ⚠️ Basic | Queries workflows but needs project-specific adaptation |
| `image_tag` | ❌ Stub | Returns `{"status": "not_implemented"}` |
| `gitops_commit` | ❌ Stub | Returns `{"status": "not_implemented"}` |

### Not Yet Implemented

These step types are referenced in some workflow definitions but not yet implemented:

| Step | Status | Alternative |
|------|--------|-------------|
| `pod_logs` | ❌ Not implemented | Use `kubectl logs` directly |
| `argocd_events` | ❌ Not implemented | Check ArgoCD UI manually |
| `argocd_sync` | ❌ Deprecated alias | Use `argocd_sync_status` instead |

### Configuration Examples

**Working workflow (all implemented steps):**
```yaml
projects:
  pbx-web:
    cluster: ardenone-cluster
    namespace: pbx-web
    workflows:
      status:
        steps:
          - pod_status          # ✅ Works
          - deployment_info     # ✅ Works
          - argocd_apps         # ✅ Works
```

**Workflow with stub implementations:**
```yaml
projects:
  myapp:
    workflows:
      deploy:
        steps:
          - ci_status           # ⚠️ Basic implementation
          - image_tag           # ❌ Returns not_implemented
          - gitops_commit       # ❌ Returns not_implemented
          - argocd_sync_status  # ✅ Works
          - pod_status          # ✅ Works
```

**Note**: Workflows that include stub steps will execute but return `{"status": "not_implemented"}` for those steps. This is non-blocking - the workflow continues to subsequent steps.

## Quick Reference

### Step Categories

**Mutating Steps** (respect dry_run flag):
- `gitops_commit`: Edit declarative-config and commit
- `image_tag`: Resolve image tags from CI

**Gating Steps** (control workflow flow):
- `ci_status`: Block workflow until CI is green

**Verification Steps** (confirm deployment state):
- `argocd_sync_status`: Poll ArgoCD until sync complete
- `pod_status`: Verify pods are running
- `deployment_info`: Check rollout status

**Information Steps** (read-only queries):
- `git_log`: Show recent commits
- `argocd_apps`: List application status
- `open_beads`: Show open tracking beads

### Required Configuration Fields

**For `pod_status`, `deployment_info`:**
- `cluster`: Cluster name (must exist in `config/clusters.yaml`)
- `namespace`: Kubernetes namespace

**For `argocd_sync_status`, `argocd_apps`:**
- `argocd_app`: ArgoCD application name
- ArgoCD base URL in `config/registry.yaml`

**For `git_log`:**
- `repo_path`: Repository filesystem path

**For `open_beads`:**
- `repo_path`: Repository path (defaults to `/home/coding/aide-de-camp`)

**For `ci_status`:**
- `project_slug`: Used to filter workflows by label
- Kubeconfig at `/home/coding/.kube/iad-ci.kubeconfig`

### Common Workflow Patterns

**Health check:**
```yaml
steps: [pod_status, deployment_info, argocd_apps]
```

**Deployment with CI gate:**
```yaml
steps: [ci_status, image_tag, gitops_commit, argocd_sync_status, pod_status]
```

**Audit trail:**
```yaml
steps: [git_log, argocd_apps, open_beads]
```

**Quick status:**
```yaml
steps: [pod_status, argocd_apps]
```



### Workflow Execution Failures

#### Issue: Workflow fails at first step with "project not found"

**Symptoms:**
```
ValueError: Project 'myapp' not found in registry
```

**Causes:**
- Project slug not defined in `config/registry.yaml`
- Typo in project name
- Registry not loaded correctly

**Solutions:**
1. Check `config/registry.yaml` for project entry
2. Verify project slug matches exactly (case-sensitive)
3. Use aliases to find alternative names
4. Reload registry: `from src.action.registry import reload_registry(); reload_registry()`

#### Issue: Step fails with "no namespace configured"

**Symptoms:**
```
ValueError: Project 'myapp' has no namespace configured
```

**Causes:**
- Missing `namespace` field in project configuration
- Step requires namespace but project doesn't define it

**Solutions:**
1. Add `namespace` to project config in `config/registry.yaml`
2. Use workflows that don't require namespace (e.g., `git_log`, `open_beads`)
3. Verify required fields for each step type

#### Issue: CI status check times out

**Symptoms:**
```
RuntimeError: CI status check timed out
```

**Causes:**
- kubectl command hangs (>15 seconds)
- Cluster not accessible
- Network connectivity issues

**Solutions:**
1. Verify kubectl config exists: `/home/coding/.kube/iad-ci.kubeconfig`
2. Test kubectl manually: `kubectl --kubeconfig /home/coding/.kube/iad-ci.kubeconfig get workflows -n argo-workflows`
3. Check cluster connectivity via Tailscale
4. Increase timeout in `execute_ci_status_step()` if needed

#### Issue: ArgoCD API calls fail

**Symptoms:**
```
RuntimeError: Failed to get ArgoCD applications
httpx.HTTPError: Connection error
```

**Causes:**
- ArgoCD base URL not configured
- ArgoCD proxy not accessible
- SSL certificate verification failure

**Solutions:**
1. Check `config/registry.yaml` for `argocd.base_url`
2. Verify ArgoCD proxy accessible: `curl -k https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications`
3. Check Tailscale connectivity
4. Verify `verify=False` in httpx client (self-signed cert)

#### Issue: Pod status returns "unknown" state

**Symptoms:**
```python
{"status": "unknown", "sync_status": "Unknown", "health_status": "Unknown"}
```

**Causes:**
- Application not found in ArgoCD
- Application deleted or not yet created
- Wrong argocd_app name

**Solutions:**
1. Verify app exists: `curl -k https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications/{app-name}`
2. Check `argocd_app` field in project config
3. Verify application deployed in cluster
4. Check for typos in application name

### Configuration Issues

#### Issue: Cluster proxy not found

**Symptoms:**
```
ValueError: Cluster 'rs-manager' has no proxy configured
```

**Causes:**
- Cluster not defined in `config/clusters.yaml`
- Proxy URL missing for cluster

**Solutions:**
1. Check `config/clusters.yaml` for cluster entry
2. Add proxy URL: `proxy: http://traefik-rs-manager:8001`
3. Verify cluster name matches exactly
4. Test proxy manually: `curl http://traefik-rs-manager:8001/api/v1/namespaces`

#### Issue: Git operations fail

**Symptoms:**
```
RuntimeError: git log failed: fatal: not a git repository
RuntimeError: Repository path '/path/to/repo' does not exist
```

**Causes:**
- `repo_path` not configured or incorrect
- Repository not checked out on local machine
- Path typo or wrong filesystem location

**Solutions:**
1. Verify `repo_path` in project config
2. Check path exists: `ls -la /home/coding/declarative-config`
3. Verify it's a git repository: `git -C /home/coding/declarative-config status`
4. Update repo_path to correct location

### Step-Specific Issues

#### Issue: `ci_status` step returns "skipped"

**Symptoms:**
```python
{"status": "skipped", "reason": "CI cluster not accessible"}
```

**Causes:**
- Kubeconfig file doesn't exist
- CI cluster not accessible from current machine

**Solutions:**
1. Verify kubeconfig exists: `ls -la /home/coding/.kube/iad-ci.kubeconfig`
2. Check kubectl access manually
3. This is non-blocking - workflow continues, just skips CI gate

#### Issue: `argocd_sync_status` times out

**Symptoms:**
```python
{"status": "timeout", "reason": "Sync did not complete within timeout"}
```

**Causes:**
- ArgoCD sync takes longer than 5 minutes
- Application stuck in OutOfSync state
- Sync loop blocked by conflicts

**Solutions:**
1. Check ArgoCD UI for sync status: https://argocd-ro-ardenone-manager-ts.ardenone.com:8444
2. Look for sync errors in application status
3. Check for auto-sync disabled
4. Increase timeout in `execute_argocd_sync_status_step()` if needed
5. Manually sync in ArgoCD UI to unblock

#### Issue: `pod_status` returns no pods

**Symptoms:**
```python
{"total_pods": 0, "running": 0, "pending": 0, "failed": 0}
```

**Causes:**
- Namespace has no pods (scaled down)
- Wrong namespace configured
- Pods in different namespace

**Solutions:**
1. Verify namespace in project config
2. Check pods manually: `kubectl get pods -n {namespace}`
3. Verify application deployed
4. Check if deployment scaled to 0 replicas

#### Issue: `bf list` command fails

**Symptoms:**
```
RuntimeError: bf list failed: bf: command not found
```

**Causes:**
- `bf` CLI not installed or not in PATH
- Repository path doesn't contain beads

**Solutions:**
1. Verify `bf` installed: `which bf`
2. Check repo path is valid
3. Test manually: `bf list --status open --format json`
4. Ensure bead-forge is installed on system

### SSE Broadcasting Issues

#### Issue: Canvas not updating with step progress

**Symptoms:**
- Steps execute but UI doesn't update
- No step lifecycle events visible

**Causes:**
- SSE connection not established
- Session ID mismatch
- Broadcaster not initialized

**Solutions:**
1. Verify SSE connection in browser DevTools (Network tab)
2. Check session ID matches between frontend and backend
3. Verify broadcaster running: `from src.sse import get_broadcaster; get_broadcaster()`
4. Check for errors in server logs

#### Issue: Workflow completes but UI shows error

**Symptoms:**
- Workflow succeeds but UI shows failed state
- Error message doesn't match actual execution

**Causes:**
- SSE event type mismatch
- Failed to serialize result
- Exception during broadcast

**Solutions:**
1. Check server logs for broadcast errors
2. Verify `ActionResult.to_dict()` works correctly
3. Test SSE serialization manually
4. Check for exception handling in broadcast methods

### Performance Issues

#### Issue: Workflows execute slowly

**Symptoms:**
- Each step takes >10 seconds
- Total workflow time exceeds expectations

**Causes:**
- Network latency to clusters
- Sequential step execution
- External API timeouts

**Solutions:**
1. Check cluster connectivity via Tailscale
2. Optimize timeout values in step implementations
3. Consider parallel execution for independent steps (future)
4. Cache API responses where appropriate
5. Profile step execution times to identify bottlenecks

#### Issue: Memory usage grows over time

**Symptoms:**
- Server memory increases with each workflow execution
- Slow degradation over multiple runs

**Causes:**
- Result objects not garbage collected
- SSE connections not cleaned up
- Large result objects retained

**Solutions:**
1. Verify result objects go out of scope after workflow
2. Check SSE connection cleanup logic
3. Limit result size in step outputs
4. Monitor memory usage with workflow executions
5. Restart service if memory leak detected (systemd auto-restart handles this)

### Debugging Tips

#### Enable verbose logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### Test step execution directly

```python
from src.action.steps import execute_pod_status_step

result = await execute_pod_status_step(
    intent_id="test-123",
    session_id="test-session",
    project_slug="myapp",
    project_cfg={"namespace": "default", "cluster": "rs-manager"}
)
print(result)
```

#### Validate workflow definitions

```python
from src.action.registry import validate_all_workflows

errors = validate_all_workflows()
for error in errors:
    print(f"{error['project_slug']}/{error['workflow_name']}: {error['errors']}")
```

#### Manually test kubectl proxy access

```bash
# Test cluster proxy
curl http://traefik-rs-manager:8001/api/v1/namespaces/default/pods

# Test ArgoCD API
curl -k https://argocd-ro-ardenone-manager-ts.ardenone.com:8444/api/v1/applications
```

#### Check SSE events in browser

1. Open browser DevTools → Network tab
2. Filter by "EventStream"
3. Look for events with type: `ACTION_STEP_STARTED`, `ACTION_STEP_COMPLETED`
4. Verify event data structure matches expected format

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

## Step Naming Convention

Step names use snake_case and describe the operation:

- **Noun phrases for queries**: `ci_status`, `pod_status`, `deployment_info`
- **Verb phrases for actions**: `gitops_commit`, `argocd_sync_status`
- **Compound names for specificity**: `argocd_apps`, `open_beads`

---

## Adding New Step Types

When adding a new step type:

1. **Add to step vocabulary**: Document the step in this file
2. **Implement step executor**: Create execute function in `src/action/steps.py`
3. **Register in executor**: Add to `_step_executors` dict in `ActionExecutor.__init__()`
4. **Add to validation**: Add step type to `known_steps` set in `src/action/registry.py`
5. **Write tests**: Add unit tests in `tests/test_action_*.py`

---

## Configuration Files

Step implementations rely on configuration files:

### Cluster Configuration (`config/clusters.yaml`)

```yaml
clusters:
  rs-manager:
    proxy: "http://traefik-rs-manager:8001"
  
  apexalgo-iad:
    proxy: "http://traefik-apexalgo-iad:8001"
  
  ardenone-cluster:
    proxy: "http://traefik-ardenone-cluster:8001"
```

### Registry Configuration (`config/registry.yaml`)

```yaml
projects:
  myapp:
    cluster: rs-manager
    namespace: production
    repo_path: /home/coding/declarative-config
    argocd_app: myapp-deployment
    
argocd:
  base_url: "https://argocd-ro-ardenone-manager-ts.ardenone.com:8444"
```

---

## Related Documentation

- [Action Execution Model Plan](../../plan/plan.md#action-execution-model)
- [Project Registry](../../config/registry.yaml)
- [Mutating Step Types](mutating-step-types.md)
- [Read-Only Step Types](read-only-step-types.md)
- [Action Execution Data Structures](action-execution-data-structures.md)
- [Action Executor Implementation](../src/action/executor.py)
- [Action Models](../src/action/models.py)
- [Performance Analysis: Locking Strategy](performance-analysis-locking-strategy.md)