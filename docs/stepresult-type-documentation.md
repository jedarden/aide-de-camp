# StepResult Type Documentation

**Document ID**: adc-1d24p  
**Date**: 2026-08-06  
**Status**: ✅ Complete  
**Module**: `src.action.models`

---

## Overview

`StepResult` is a Pydantic model that represents the outcome of a single workflow step execution in the Action Execution Model. It contains the execution status, output data, error information, and timing metrics for each step in an action workflow.

**Source**: `src/action/models.py` (lines 67-92)

---

## Type Definition

```python
class StepResult(BaseModel):
    """
    Result of a single workflow step execution.
    
    Contains the outcome of a step execution including status, output,
    error information, and timing metrics.
    """
    step_name: str = Field(..., description="Name of the step that was executed")
    status: StepStatus = Field(..., description="Execution status")
    output: dict[str, Any] = Field(default_factory=dict, description="Step output data")
    error: Optional[str] = Field(None, description="Error message if step failed")
    started_at: float = Field(..., description="Unix timestamp when step started")
    completed_at: Optional[float] = Field(None, description="Unix timestamp when step completed")
    duration_ms: float = Field(default=0.0, description="Step execution duration in milliseconds")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for SSE broadcasting."""
```

---

## Field Documentation

### Required Fields

#### `step_name: str`
- **Description**: Name of the step that was executed
- **Required**: Yes
- **Example**: `"ci_status"`, `"image_tag"`, `"pod_status"`
- **Usage**: Identifies which step produced this result, used for tracking and logging

#### `status: StepStatus`
- **Description**: Execution status
- **Required**: Yes
- **Type**: `StepStatus` enum (see Status Handling section)
- **Example**: `StepStatus.COMPLETED`, `StepStatus.FAILED`
- **Usage**: Indicates the outcome of the step execution

#### `started_at: float`
- **Description**: Unix timestamp when step started
- **Required**: Yes
- **Type**: `float` (Unix timestamp in seconds)
- **Example**: `1722987245.1234567`
- **Usage**: Records when step execution began, used for timing calculations

### Optional Fields

#### `output: dict[str, Any]`
- **Description**: Step output data
- **Required**: No (defaults to empty dict)
- **Type**: `dict[str, Any]`
- **Default**: `{}`
- **Example**: `{"workflow_name": "build-123", "phase": "Succeeded"}`
- **Usage**: Contains the results of the step execution, structure varies by step type

#### `error: Optional[str]`
- **Description**: Error message if step failed
- **Required**: No
- **Type**: `str` or `None`
- **Default**: `None`
- **Example**: `"CI cluster not accessible"`, `"Timeout after 15 seconds"`
- **Usage**: Provides error details when status is `FAILED`, `None` for successful steps

#### `completed_at: Optional[float]`
- **Description**: Unix timestamp when step completed
- **Required**: No
- **Type**: `float` or `None`
- **Default**: `None`
- **Example**: `1722987246.2345678`
- **Usage**: Records when step execution finished, used for duration calculation

#### `duration_ms: float`
- **Description**: Step execution duration in milliseconds
- **Required**: No
- **Type**: `float`
- **Default**: `0.0`
- **Example**: `1234.567`
- **Usage**: Provides execution time for performance monitoring and metrics

---

## Status Handling

### StepStatus Enum

The `status` field uses the `StepStatus` enumeration:

```python
class StepStatus(str, Enum):
    """Status of a workflow step execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
```

### Status Meanings

| Status | Meaning | Typical Use Case | Error Field |
|--------|---------|------------------|-------------|
| `PENDING` | Step has not started yet | Initial state before execution | `None` |
| `IN_PROGRESS` | Step is currently executing | Active execution state | `None` |
| `COMPLETED` | Step finished successfully | Normal successful completion | `None` |
| `FAILED` | Step execution failed | Error during execution | Error message |
| `SKIPPED` | Step was skipped | Conditional execution not met | Reason (optional) |

### Status Setting Patterns

**Successful Execution:**
```python
result = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={"workflow_name": "build-123", "phase": "Succeeded"},
    started_at=start_time,
    completed_at=end_time,
    duration_ms=1500.0,
)
```

**Failed Execution:**
```python
result = StepResult(
    step_name="ci_status",
    status=StepStatus.FAILED,
    output={"cluster": "iad-ci"},
    error="CI cluster not accessible",
    started_at=start_time,
    completed_at=end_time,
    duration_ms=100.0,
)
```

**Skipped Execution:**
```python
result = StepResult(
    step_name="image_tag",
    status=StepStatus.SKIPPED,
    output={"reason": "CI status failed"},
    started_at=start_time,
    completed_at=end_time,
    duration_ms=0.0,
)
```

---

## Data Structure and Serialization

### Internal Structure

`StepResult` is a Pydantic `BaseModel` that provides:
- **Automatic validation**: Field types are validated on construction
- **JSON serialization**: Built-in `model_dump()` and `model_dump_json()` methods
- **Immutability by default**: Fields are frozen unless explicitly modified
- **Type safety**: All fields are type-annotated and validated

### Serialization for SSE Broadcasting

The `to_dict()` method converts the result to a dictionary for SSE (Server-Sent Events) broadcasting:

```python
def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for SSE broadcasting."""
    return {
        "step_name": self.step_name,
        "status": self.status.value,  # Converts enum to string value
        "output": self.output,
        "error": self.error,
        "started_at": self.started_at,
        "completed_at": self.completed_at,
        "duration_ms": self.duration_ms,
    }
```

**Key conversion behavior:**
- `status` enum is converted to its string value (e.g., `StepStatus.COMPLETED` → `"completed"`)
- All other fields are passed through as-is
- Returns a plain `dict[str, Any]` suitable for JSON serialization

### JSON Serialization Example

```python
import json

result = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={"workflow_name": "build-123"},
    started_at=1722987245.123,
    completed_at=1722987246.456,
    duration_ms=1333.0,
)

# Convert to JSON
json_data = json.dumps(result.to_dict())
# '{"step_name": "ci_status", "status": "completed", "output": {"workflow_name": "build-123"}, ...}'
```

---

## Examples

### Minimal Successful Result

```python
import time

result = StepResult(
    step_name="test_step",
    status=StepStatus.COMPLETED,
    started_at=time.time(),
)
# Minimal result with only required fields
```

### Full Successful Result

```python
import time

started = time.time()
completed = started + 1.5

result = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={
        "workflow_name": "spaxel-build-abc123",
        "phase": "Succeeded",
        "created_at": "2026-08-06T10:30:00Z",
        "cluster": "iad-ci",
    },
    started_at=started,
    completed_at=completed,
    duration_ms=1500.0,
)
```

### Failed Result with Error

```python
import time

started = time.time()
completed = started + 0.5

result = StepResult(
    step_name="ci_status",
    status=StepStatus.FAILED,
    output={"cluster": "iad-ci"},
    error="Kubeconfig not found at /home/coding/.kube/iad-ci.kubeconfig",
    started_at=started,
    completed_at=completed,
    duration_ms=500.0,
)
```

### Timeout Failure

```python
import time

result = StepResult(
    step_name="pod_status",
    status=StepStatus.FAILED,
    output={"namespace": "production", "cluster": "ardenone-cluster"},
    error="kubectl proxy request timed out after 10.0 seconds",
    started_at=time.time(),
    completed_at=time.time() + 10.0,
    duration_ms=10000.0,
)
```

### Result with Complex Output Data

```python
result = StepResult(
    step_name="pod_status",
    status=StepStatus.COMPLETED,
    output={
        "total_pods": 5,
        "phase_counts": {
            "Running": 3,
            "Pending": 1,
            "Failed": 1,
        },
        "pods": [
            {
                "name": "app-deployment-abc123",
                "phase": "Running",
                "ready": 1,
                "total": 1,
                "ready_ratio": "1/1",
            },
            # ... more pods
        ],
        "namespace": "production",
        "cluster": "ardenone-cluster",
    },
    started_at=time.time(),
    completed_at=time.time() + 2.3,
    duration_ms=2300.0,
)
```

---

## Result Chaining and Error Propagation

### Result Chaining in Workflows

`StepResult` objects are chained together in `ActionResult` to form workflow execution traces:

```python
from src.action.models import ActionResult, StepResult, StepStatus

# Create workflow result
workflow_result = ActionResult(
    intent_id="intent-123",
    session_id="session-456",
    workflow_name="deploy_application",
    status="running",
    started_at=time.time(),
)

# Chain multiple step results
workflow_result.add_step(StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={"workflow_name": "build-123"},
    started_at=time.time(),
    completed_at=time.time() + 1.0,
    duration_ms=1000.0,
))

workflow_result.add_step(StepResult(
    step_name="image_tag",
    status=StepStatus.COMPLETED,
    output={"tag": "v1.2.3", "registry_path": "ronaldraygun/app:v1.2.3"},
    started_at=time.time() + 1.0,
    completed_at=time.time() + 1.5,
    duration_ms=500.0,
))
```

### Error Propagation Patterns

**Fail-fast workflow:**
```python
# Step 1 succeeds
workflow_result.add_step(StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={"workflow_name": "build-123"},
    started_at=time.time(),
    completed_at=time.time() + 1.0,
    duration_ms=1000.0,
))

# Step 2 fails - workflow stops here
workflow_result.add_step(StepResult(
    step_name="image_tag",
    status=StepStatus.FAILED,
    output={},
    error="Failed to extract image tag from CI workflow",
    started_at=time.time() + 1.0,
    completed_at=time.time() + 1.5,
    duration_ms=500.0,
))

# Remaining steps are skipped or not executed
workflow_result.status = "failed"
workflow_result.error = "Step image_tag failed"
```

**Conditional execution based on previous step:**
```python
# Check if previous step succeeded before executing next step
previous_result = workflow_result.steps[-1]

if previous_result.status == StepStatus.COMPLETED:
    # Execute next step with data from previous step
    next_result = await execute_next_step(
        ci_status_result=previous_result.output
    )
    workflow_result.add_step(next_result)
else:
    # Skip this step or execute alternative path
    workflow_result.add_step(StepResult(
        step_name="image_tag",
        status=StepStatus.SKIPPED,
        output={"reason": "Previous step failed"},
        started_at=time.time(),
        completed_at=time.time(),
        duration_ms=0.0,
    ))
```

### Error Context Accumulation

Results maintain error context throughout the workflow:

```python
# Each failed step preserves its error context
failed_ci_status = StepResult(
    step_name="ci_status",
    status=StepStatus.FAILED,
    output={"cluster": "iad-ci"},
    error="Kubeconfig not found",
    started_at=time.time(),
    completed_at=time.time() + 0.1,
    duration_ms=100.0,
)

# Downstream steps can reference upstream errors
dependent_step = StepResult(
    step_name="image_tag",
    status=StepStatus.FAILED,
    output={"upstream_error": failed_ci_status.error},
    error="Cannot extract image tag: CI status step failed",
    started_at=time.time() + 0.1,
    completed_at=time.time() + 0.15,
    duration_ms=50.0,
)
```

---

## Usage Patterns

### Creating Results in Step Executors

```python
class CIStatusStep:
    async def execute(self, project_slug: str, **kwargs) -> StepResult:
        started_at = time.time()
        
        try:
            # Execute step logic
            workflow_data = await self.query_workflow(project_slug)
            
            return StepResult(
                step_name="ci_status",
                status=StepStatus.COMPLETED,
                output=workflow_data,
                started_at=started_at,
                completed_at=time.time(),
                duration_ms=(time.time() - started_at) * 1000,
            )
        except Exception as e:
            return StepResult(
                step_name="ci_status",
                status=StepStatus.FAILED,
                output={"project_slug": project_slug},
                error=str(e),
                started_at=started_at,
                completed_at=time.time(),
                duration_ms=(time.time() - started_at) * 1000,
            )
```

### Broadcasting Results via SSE

```python
from src.sse import get_broadcaster, SSEEvent

# After step execution completes
result = await step.execute(context)

# Broadcast to canvas
broadcaster = get_broadcaster()
await broadcaster.broadcast(
    SSEEvent(
        event_type="step_completed",
        target_session_id=context.session_id,
        data=result.to_dict(),  # Serialized form
    )
)
```

---

## Testing

### Unit Test Example

```python
def test_step_result_creation():
    """Test creating a step result with all fields."""
    started = time.time() - 1.0
    completed = time.time()
    
    result = StepResult(
        step_name="deploy_step",
        status=StepStatus.FAILED,
        output={"deployed": False},
        error="Deployment failed",
        started_at=started,
        completed_at=completed,
        duration_ms=1000.0,
    )
    
    assert result.step_name == "deploy_step"
    assert result.status == StepStatus.FAILED
    assert result.output == {"deployed": False}
    assert result.error == "Deployment failed"
    assert result.started_at == started
    assert result.completed_at == completed
    assert result.duration_ms == 1000.0
```

### Serialization Test

```python
def test_step_result_to_dict():
    """Test to_dict conversion for SSE broadcasting."""
    now = time.time()
    result = StepResult(
        step_name="test_step",
        status=StepStatus.COMPLETED,
        output={"key": "value"},
        started_at=now,
        completed_at=now + 0.5,
        duration_ms=500.0,
    )
    
    data = result.to_dict()
    
    assert data["step_name"] == "test_step"
    assert data["status"] == "completed"  # Enum converted to string
    assert data["output"] == {"key": "value"}
    assert data["error"] is None
    assert data["started_at"] == now
    assert data["completed_at"] == now + 0.5
    assert data["duration_ms"] == 500.0
```

---

## Related Types

- **`StepStatus`**: Enum for step execution status values
- **`ActionResult`**: Workflow-level result containing multiple `StepResult` objects
- **`ExecutionContext`**: Context passed to step executors
- **`Step`**: Base class for workflow step definitions

---

## References

- **Source**: `src/action/models.py` (lines 67-92)
- **Tests**: `tests/test_action_models.py` (TestStepResult class)
- **Usage Examples**: `tests/test_action_read_steps.py`
- **SSE Broadcasting**: `src/sse/broadcaster.py`

---

**Document Version**: 1.0  
**Last Updated**: 2026-08-06  
**Maintained By**: aide-de-camp project
