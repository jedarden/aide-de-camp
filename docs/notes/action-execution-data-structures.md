# Action Execution Data Structures

This document describes the core data structures for the Action Execution Model (AEM) used in aide-de-camp's workflow execution system.

## Overview

The Action Execution Model defines the data structures used to execute and track workflows:

- **ExecutionContext** - Context passed to all step executors
- **StepResult** - Result of a single workflow step execution
- **ActionResult** - Complete workflow execution result
- **StepStatus** - Status enumeration for step execution
- **Step** - Base class for all workflow step types

## ExecutionContext

The `ExecutionContext` contains project configuration and runtime context needed for step execution. It's passed to every step executor in the workflow.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `intent_id` | `str` | Intent ID for tracking and SSE targeting. Links execution to the original user intent. |
| `session_id` | `str` | Session ID for SSE targeting. Identifies the user session for real-time updates. |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `project_slug` | `Optional[str]` | `None` | Project slug for registry lookup. Used to fetch project configuration. |
| `project_cfg` | `dict[str, Any]` | `{}` | Project configuration from registry. Contains cluster, namespace, repo_path, etc. |
| `dry_run` | `bool` | `False` | If `True`, skip mutating operations. Useful for validation without execution. |

### Convenience Properties

These properties extract commonly-used values from `project_cfg`:

| Property | Type | Returns | Description |
|----------|------|---------|-------------|
| `cluster` | `Optional[str]` | `project_cfg.get("cluster")` | Cluster name (e.g., `"rs-manager"`, `"apexalgo-iad"`) |
| `namespace` | `Optional[str]` | `project_cfg.get("namespace")` | Kubernetes namespace for operations |
| `repo_path` | `Optional[str]` | `project_cfg.get("repo_path")` | Repository path (e.g., `"jedarten/declarative-config"`) |
| `argocd_app` | `Optional[str]` | `project_cfg.get("argocd_app")` | ArgoCD application name |

### Example Usage

```python
from src.action.models import ExecutionContext

# Basic context
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

### Minimal Example

```python
# Minimal context for non-project operations
ctx = ExecutionContext(
    intent_id="int-12345",
    session_id="sess-67890"
)
```

## StepResult

The `StepResult` contains the outcome of a single workflow step execution, including status, output, errors, and timing metrics.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `step_name` | `str` | Name of the step that was executed (e.g., `"ci_status"`, `"gitops_commit"`) |
| `status` | `StepStatus` | Execution status (see StepStatus enumeration) |
| `output` | `dict[str, Any]` | Step output data (varies by step type) |
| `error` | `Optional[str]` | Error message if step failed |
| `started_at` | `float` | Unix timestamp when step started |
| `completed_at` | `Optional[float]` | Unix timestamp when step completed (None if in progress) |
| `duration_ms` | `float` | Step execution duration in milliseconds |

### Output Examples by Step Type

**ci_status step:**
```python
{
    "workflow_name": "mta-my-way-build",
    "phase": "Succeeded",
    "status": "workflowcompleted",
    "message": "Workflow completed successfully"
}
```

**gitops_commit step:**
```python
{
    "commit": "abc123def456",
    "repo": "ardent/declarative-config",
    "branch": "main"
}
```

### Example

```python
from src.action.models import StepResult, StepStatus
import time

result = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={
        "workflow_name": "mta-my-way-build",
        "phase": "Succeeded"
    },
    error=None,
    started_at=time.time(),
    completed_at=time.time(),
    duration_ms=1234.5
)
```

## StepStatus

Enumeration of possible states for workflow step execution.

### Values

| Value | String | Description |
|-------|--------|-------------|
| `PENDING` | `"pending"` | Step is queued but not yet started |
| `IN_PROGRESS` | `"in_progress"` | Step is currently executing |
| `COMPLETED` | `"completed"` | Step completed successfully |
| `FAILED` | `"failed"` | Step failed with an error |
| `SKIPPED` | `"skipped"` | Step was skipped (e.g., due to condition or dry_run) |

### Status Transitions

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

## ActionResult

The `ActionResult` contains the complete execution result for an entire workflow, including all step results, timing information, and final status.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `intent_id` | `str` | Intent ID for tracking |
| `session_id` | `str` | Session ID for SSE targeting |
| `project_slug` | `Optional[str]` | Project slug that was executed |
| `workflow_name` | `str` | Name of the workflow that was executed (e.g., `"mta-my-way"`) |
| `status` | `str` | Final workflow status (see below) |
| `steps` | `list[StepResult]` | All step results in execution order |
| `started_at` | `float` | Unix timestamp when workflow started |
| `completed_at` | `Optional[float]` | Unix timestamp when workflow completed |
| `duration_ms` | `float` | Workflow execution duration in milliseconds |
| `error` | `Optional[str]` | Error message if workflow failed |

### Workflow Status Values

| Status | Description |
|--------|-------------|
| `"running"` | Workflow is currently executing |
| `"completed"` | All steps completed successfully |
| `"failed"` | One or more steps failed |
| `"cancelled"` | Workflow was cancelled before completion |

### Methods

#### `add_step(step: StepResult) -> None`

Add a step result to the action result. Appends to the `steps` list in execution order.

#### `to_dict() -> dict[str, Any]`

Convert the action result to a dictionary for SSE broadcasting. Includes all fields and converts step results via `StepResult.to_dict()`.

### Example

```python
from src.action.models import ActionResult, StepResult, StepStatus
import time

action_result = ActionResult(
    intent_id="int-12345",
    session_id="sess-67890",
    project_slug="mta-my-way",
    workflow_name="mta-my-way",
    status="running",
    steps=[],
    started_at=time.time(),
    completed_at=None,
    duration_ms=0.0,
    error=None
)

# Add a completed step
step = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={"phase": "Succeeded"},
    error=None,
    started_at=time.time() - 1.0,
    completed_at=time.time(),
    duration_ms=1000.0
)
action_result.add_step(step)

# Update final status
action_result.status = "completed"
action_result.completed_at = time.time()
action_result.duration_ms = action_result.completed_at - action_result.started_at
```

## Data Flow

```
User Intent
  ↓
ExecutionContext (intent_id, session_id, project_slug, project_cfg)
  ↓
Step Execution (each step receives ExecutionContext)
  ↓
StepResult (status, output, error, timing)
  ↓
ActionResult (accumulates all StepResults)
  ↓
SSE Broadcast (ActionResult.to_dict())
  ↓
Canvas Update (real-time UI feedback)
```

## Best Practices

### ExecutionContext

1. **Always provide tracking IDs** - `intent_id` and `session_id` are required for proper SSE targeting
2. **Validate project_cfg** - Ensure cluster, namespace, and repo_path are present before cluster operations
3. **Use dry_run for validation** - Set `dry_run=True` to test workflows without side effects

### StepResult

1. **Populate output consistently** - Each step type should document its output structure
2. **Include meaningful error messages** - Error messages should explain what failed and why
3. **Track timing accurately** - Use high-resolution timestamps for performance monitoring

### ActionResult

1. **Add steps in execution order** - The `steps` list preserves chronological order
2. **Update status atomically** - Change workflow status only after all steps complete
3. **Use to_dict() for SSE** - Always use the `to_dict()` method for broadcasting to ensure consistent serialization

## Related Files

- `src/action/models.py` - Core data structure implementations
- `src/action/executor.py` - ExecutionContext and StepResult usage
- `src/sse/broadcaster.py` - SSE broadcasting of ActionResult

## Next Steps

For documentation on specific step types and their execution patterns, see:
- [Step Types and Execution Patterns](./step-types-and-execution-patterns.md) - Step vocabulary, execution logic, and output formats
