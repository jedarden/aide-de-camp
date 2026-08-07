# StepResult Type Documentation

## Overview

`StepResult` is a Pydantic model that captures the outcome of a single workflow step execution in the Action Execution Model. It serves as the primary data structure for communicating execution results between step executors and the ActionExecutor, providing rich context about step success, output data, error conditions, and timing metrics.

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
```

## Field Documentation

### Required Fields

| Field | Type | Description | Purpose |
|-------|------|-------------|---------|
| `step_name` | `str` | Name of the step that was executed | Identifies which step this result corresponds to (e.g., `"ci_status"`, `"gitops_commit"`). Must match the step definition in the workflow. |
| `status` | `StepStatus` | Execution status | Indicates the outcome of step execution using the `StepStatus` enumeration (PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED). |
| `started_at` | `float` | Unix timestamp when step started | Records when the step executor began executing this step. Used for timing analysis and correlation with logs. |

### Optional Fields

| Field | Type | Default | Description | Purpose |
|-------|------|---------|-------------|---------|
| `output` | `dict[str, Any]` | `{}` | Step output data | Contains the results produced by the step executor. Structure varies by step type (CI status, pod info, deployment details). Passed to subsequent steps and included in SSE events. |
| `error` | `Optional[str]` | `None` | Error message if step failed | Human-readable error description when `status == StepStatus.FAILED`. Provides context about what went wrong for debugging and user feedback. |
| `completed_at` | `Optional[float]` | `None` | Unix timestamp when step completed | Records when the step finished execution. `None` if the step is still running (IN_PROGRESS) or was skipped. |
| `duration_ms` | `float` | `0.0` | Step execution duration in milliseconds | Calculated timing metric for performance analysis. Should be `completed_at - started_at * 1000` for completed steps. |

## Status Handling

### StepStatus Enumeration

`StepStatus` is a string enumeration that defines all possible states of a workflow step:

```python
class StepStatus(str, Enum):
    """Status of a workflow step execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
```

### Status Lifecycle

```
PENDING → IN_PROGRESS → COMPLETED
                        → FAILED
                        → SKIPPED
```

### Status Meanings and Transitions

#### PENDING

- **Meaning:** Step has been created but not yet started execution
- **When set:** Initial state when a step is first instantiated in a workflow
- **Typical use:** Workflow planning phase, before ActionExecutor begins step execution
- **Transition:** Always transitions to `IN_PROGRESS` when execution begins

#### IN_PROGRESS

- **Meaning:** Step is currently executing (async operations in flight)
- **When set:** Immediately before the step executor's main logic runs
- **Typical use:** Long-running operations (kubectl queries, CI status checks, git operations)
- **Transition:** 
  - To `COMPLETED` on success
  - To `FAILED` on exception or error condition
  - To `SKIPPED` if a precondition is not met

#### COMPLETED

- **Meaning:** Step finished successfully with valid output
- **When set:** After step executor completes without errors and produces output
- **Typical use:** Successful CI checks, successful pod queries, successful GitOps commits
- **Characteristics:**
  - `output` field contains step-specific results
  - `error` field is `None`
  - `completed_at` and `duration_ms` are populated
- **Transition:** Terminal state — no further transitions

#### FAILED

- **Meaning:** Step execution encountered an error or exception
- **When set:** When step executor raises an exception or detects an error condition
- **Typical use:** CI failures, kubectl errors, git push failures, timeout conditions
- **Characteristics:**
  - `error` field contains error description
  - `output` may contain partial results or diagnostic data
  - Workflow may halt or continue depending on step configuration
- **Transition:** Terminal state — no further transitions

#### SKIPPED

- **Meaning:** Step was not executed due to preconditions or workflow logic
- **When set:** When a step's guard condition evaluates to false
- **Typical use:** Conditional steps that don't apply to the current context
- **Characteristics:**
  - `output` is typically empty or explains why the step was skipped
  - `error` is `None` (skipped steps are not failures)
  - `completed_at` may be set to the time the skip decision was made
- **Transition:** Terminal state — no further transitions

### Setting Status in Step Executors

**Pattern for successful execution:**
```python
async def execute_ci_status_step(ctx: ExecutionContext) -> StepResult:
    """Execute CI status check with proper status handling."""
    started_at = time.time()
    
    try:
        # Set initial status to IN_PROGRESS
        logger.info(f"CI status check starting for {ctx.project_slug}")
        
        # Execute step logic
        ci_result = await check_ci_status(ctx.project_slug)
        
        # Return COMPLETED status on success
        return StepResult(
            step_name="ci_status",
            status=StepStatus.COMPLETED,
            output=ci_result,
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
    except Exception as e:
        # Return FAILED status on error
        return StepResult(
            step_name="ci_status",
            status=StepStatus.FAILED,
            error=str(e),
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
```

**Pattern for conditional execution:**
```python
async def execute_gitops_commit_step(ctx: ExecutionContext) -> StepResult:
    """Execute GitOps commit with skip condition."""
    started_at = time.time()
    
    # Skip if dry_run is enabled
    if ctx.dry_run:
        return StepResult(
            step_name="gitops_commit",
            status=StepStatus.SKIPPED,
            output={"reason": "dry_run enabled, mutation skipped"},
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
    
    try:
        # Perform actual mutation
        await commit_gitops_changes(ctx)
        
        return StepResult(
            step_name="gitops_commit",
            status=StepStatus.COMPLETED,
            output={"committed": True},
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
    except Exception as e:
        return StepResult(
            step_name="gitops_commit",
            status=StepStatus.FAILED,
            error=str(e),
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
```

## Data Structure and Serialization

### Output Data Structure

The `output` field is a flexible dictionary that holds step-specific results. Each step type defines its own output schema:

```python
# CI Status Step Output
{
    "workflow_name": "mta-my-way-build",
    "status": "Succeeded",
    "build_number": 123,
    "timestamp": "2026-08-06T12:34:56Z"
}

# Pod Status Step Output
{
    "namespace": "production",
    "pod_count": 3,
    "ready_pods": 3,
    "pods": [
        {"name": "app-7d9f8c", "ready": True, "restarts": 0},
        {"name": "app-5k2m3n", "ready": True, "restarts": 0},
        {"name": "app-9x4p7q", "ready": True, "restarts": 0}
    ]
}

# Deployment Info Step Output
{
    "deployment_name": "mta-my-way",
    "replicas": 3,
    "updated_replicas": 3,
    "available_replicas": 3,
    "image": "ronaldraygun/mta-my-way:v1.2.3"
}

# GitOps Commit Step Output
{
    "commit": "abc123def456",
    "repo_path": "/path/to/repo",
    "files_modified": ["deployment.yaml"],
    "dry_run": False
}
```

### to_dict() Method

`StepResult` provides a `to_dict()` method that serializes the result to a plain dictionary for SSE broadcasting:

```python
def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for SSE broadcasting."""
    return {
        "step_name": self.step_name,
        "status": self.status.value,  # Enum converted to string
        "output": self.output,
        "error": self.error,
        "started_at": self.started_at,
        "completed_at": self.completed_at,
        "duration_ms": self.duration_ms,
    }
```

**Key serialization behavior:**
- `status` enum is converted to its string value (`"completed"` not `StepStatus.COMPLETED`)
- All other fields are copied as-is
- Result is JSON-serializable for SSE event payload
- Pydantic's `model_dump()` could be used alternatively, but `to_dict()` makes the enum conversion explicit

### SSE Broadcasting

Serialized `StepResult` objects are included in SSE events sent to the canvas:

```python
# In ActionExecutor after step completion
step_result = await executor.execute(ctx)
await broadcaster.broadcast(
    SSEEvent(
        event_type="step_completed",
        data=step_result.to_dict(),  # Serialized for SSE
        target_session_id=ctx.session_id,
    )
)
```

**Canvas receives:**
```json
{
    "event_type": "step_completed",
    "data": {
        "step_name": "ci_status",
        "status": "completed",
        "output": {"workflow_name": "mta-my-way-build", "status": "Succeeded"},
        "error": null,
        "started_at": 1722939296.123,
        "completed_at": 1722939298.456,
        "duration_ms": 2333.0
    }
}
```

## Usage Examples

### Successful Step Result

```python
import time

# A successful CI status check
result = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={
        "workflow_name": "mta-my-way-build",
        "status": "Succeeded",
        "build_number": 123,
        "timestamp": "2026-08-06T12:34:56Z"
    },
    error=None,  # No error for successful steps
    started_at=time.time() - 2.5,  # Started 2.5 seconds ago
    completed_at=time.time(),  # Just completed
    duration_ms=2500.0,  # 2.5 seconds in milliseconds
)

# Access result data
print(f"Step: {result.step_name}")  # "ci_status"
print(f"Status: {result.status}")  # StepStatus.COMPLETED
print(f"Workflow: {result.output['workflow_name']}")  # "mta-my-way-build"
print(f"Duration: {result.duration_ms}ms")  # 2500.0

# Serialize for SSE
sse_data = result.to_dict()
print(sse_data["status"])  # "completed" (string, not enum)
```

### Failed Step Result

```python
# A failed deployment step
result = StepResult(
    step_name="pod_status",
    status=StepStatus.FAILED,
    output={"namespace": "production"},  # Partial output
    error="Timeout waiting for pods to become ready",
    started_at=time.time() - 30.0,  # Started 30 seconds ago
    completed_at=time.time(),  # Just failed
    duration_ms=30000.0,  # 30 seconds
)

# Check failure condition
if result.status == StepStatus.FAILED:
    print(f"Step failed: {result.step_name}")
    print(f"Error: {result.error}")  # "Timeout waiting for pods to become ready"
    print(f"Partial output: {result.output}")  # {"namespace": "production"}
```

### Skipped Step Result

```python
# A step skipped due to dry_run
result = StepResult(
    step_name="gitops_commit",
    status=StepStatus.SKIPPED,
    output={"reason": "dry_run enabled"},
    error=None,  # No error — skip is not a failure
    started_at=time.time() - 0.1,
    completed_at=time.time(),
    duration_ms=100.0,  # Fast skip decision
)

# Check if step was executed
if result.status == StepStatus.SKIPPED:
    print(f"Step skipped: {result.output.get('reason')}")  # "dry_run enabled"
```

### Step Result in ActionExecutor

```python
async def execute_workflow(ctx: ExecutionContext) -> ActionResult:
    """Execute workflow and collect step results."""
    results = []
    
    # Execute step 1
    step1 = await execute_ci_status_step(ctx)
    results.append(step1)
    
    # Check if step 1 succeeded before continuing
    if step1.status == StepStatus.COMPLETED:
        step2 = await execute_image_tag_step(ctx)
        results.append(step2)
    else:
        # Step 1 failed, workflow may halt
        logger.error(f"CI check failed: {step1.error}")
    
    # Build ActionResult with all step results
    return ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="deploy",
        status="completed",
        steps=results,  # List of StepResult objects
        started_at=start_time,
        completed_at=time.time(),
        duration_ms=(time.time() - start_time) * 1000,
    )
```

## Result Chaining and Error Propagation

### Output Chaining

Step results can pass data to subsequent steps through the `output` field:

```python
# Step 1: CI Status Check
step1 = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={
        "workflow_name": "mta-my-way-build",
        "build_number": 123,
        "image_tag": "v1.2.3"  # This tag is needed by step 2
    },
    started_at=t1,
    completed_at=t2,
    duration_ms=1000.0,
)

# Step 2: GitOps Commit (uses output from step 1)
image_tag = step1.output.get("image_tag")
step2 = StepResult(
    step_name="gitops_commit",
    status=StepStatus.COMPLETED,
    output={
        "tag": image_tag,  # Chained from step 1
        "repo_path": "/path/to/repo",
        "commit": "abc123"
    },
    started_at=t2,
    completed_at=t3,
    duration_ms=2000.0,
)
```

### Error Propagation Patterns

#### **Fail-Fast Pattern**

Workflow halts immediately when a critical step fails:

```python
result = await execute_ci_status_step(ctx)
if result.status == StepStatus.FAILED:
    # Don't execute remaining steps
    return ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="deploy",
        status="failed",
        steps=[result],
        error=f"CI check failed: {result.error}",
        started_at=start_time,
        completed_at=time.time(),
        duration_ms=(time.time() - start_time) * 1000,
    )
```

#### **Continue-On-Error Pattern**

Workflow continues through non-critical failures:

```python
results = []
all_succeeded = True

# Execute all steps even if some fail
for step_def in workflow.steps:
    result = await execute_step(step_def, ctx)
    results.append(result)
    
    if result.status == StepStatus.FAILED:
        # Track failure but continue
        all_succeeded = False
        logger.warning(f"Step failed but continuing: {result.step_name}")

# Return overall result
return ActionResult(
    intent_id=ctx.intent_id,
    session_id=ctx.session_id,
    workflow_name="monitor",
    status="completed" if all_succeeded else "partial_failure",
    steps=results,
    started_at=start_time,
    completed_at=time.time(),
    duration_ms=(time.time() - start_time) * 1000,
)
```

#### **Conditional Execution Pattern**

Subsequent steps use previous step results to decide execution:

```python
# Step 1: Check if deployment exists
check_result = await execute_deployment_info_step(ctx)

if check_result.status == StepStatus.COMPLETED:
    deployment_exists = check_result.output.get("exists", False)
    
    if deployment_exists:
        # Step 2a: Update existing deployment
        result = await execute_update_deployment_step(ctx)
    else:
        # Step 2b: Create new deployment
        result = await execute_create_deployment_step(ctx)
else:
    # Check failed, can't proceed
    result = check_result
```

### Error Aggregation in ActionResult

When a workflow fails, the `ActionResult` aggregates both step-level and workflow-level errors:

```python
# Multiple step failures
step1_failed = StepResult(
    step_name="ci_status",
    status=StepStatus.FAILED,
    error="CI workflow still running",
    started_at=t1,
    completed_at=t2,
    duration_ms=5000.0,
)

step2_failed = StepResult(
    step_name="image_tag",
    status=StepStatus.FAILED,
    error="Cannot resolve image without completed CI",
    started_at=t2,
    completed_at=t2 + 0.1,
    duration_ms=100.0,
)

# Workflow result aggregates all failures
workflow_result = ActionResult(
    intent_id=ctx.intent_id,
    session_id=ctx.session_id,
    workflow_name="deploy",
    status="failed",
    steps=[step1_failed, step2_failed],
    error="Workflow failed: 2 of 4 steps failed",  # Summary error
    started_at=start_time,
    completed_at=time.time(),
    duration_ms=(time.time() - start_time) * 1000,
)

# Caller can inspect individual step errors
for step in workflow_result.steps:
    if step.status == StepStatus.FAILED:
        print(f"Step {step.step_name} failed: {step.error}")
```

## Timing and Performance Monitoring

### Duration Calculation

Step duration is calculated from Unix timestamps:

```python
# Correct duration calculation
started_at = time.time()
# ... execute step logic ...
completed_at = time.time()
duration_ms = (completed_at - started_at) * 1000

result = StepResult(
    step_name="pod_status",
    status=StepStatus.COMPLETED,
    output={"pods": pods},
    started_at=started_at,
    completed_at=completed_at,
    duration_ms=duration_ms,  # Always positive, in milliseconds
)
```

### In-Flight Steps

For steps with status `IN_PROGRESS`, `completed_at` and `duration_ms` may be zero:

```python
# Result for a step that's currently running
in_flight = StepResult(
    step_name="long_running_step",
    status=StepStatus.IN_PROGRESS,
    output={},  # No output yet
    started_at=time.time(),
    completed_at=None,  # Not completed yet
    duration_ms=0.0,  # Not calculated yet
)
```

### Performance Analysis

Step results enable workflow performance analysis:

```python
def analyze_workflow_performance(steps: list[StepResult]) -> dict[str, Any]:
    """Analyze timing across all workflow steps."""
    total_duration = sum(step.duration_ms for step in steps)
    
    slowest_step = max(steps, key=lambda s: s.duration_ms)
    fastest_step = min(steps, key=lambda s: s.duration_ms)
    
    failed_steps = [s for s in steps if s.status == StepStatus.FAILED]
    
    return {
        "total_duration_ms": total_duration,
        "step_count": len(steps),
        "slowest_step": {
            "name": slowest_step.step_name,
            "duration_ms": slowest_step.duration_ms
        },
        "fastest_step": {
            "name": fastest_step.step_name,
            "duration_ms": fastest_step.duration_ms
        },
        "failed_count": len(failed_steps),
        "success_rate": (len(steps) - len(failed_steps)) / len(steps),
    }
```

## Best Practices

1. **Always set timestamps accurately:** Use `time.time()` at the exact moment a step starts and completes to ensure accurate duration calculations.

2. **Populate duration_ms for completed steps:** Calculate `duration_ms` as `(completed_at - started_at) * 1000` for better debugging and performance analysis.

3. **Use descriptive error messages:** When `status == StepStatus.FAILED`, the `error` field should contain actionable information about what went wrong.

4. **Structure output consistently:** Each step type should document its output schema so downstream steps can reliably access data.

5. **Return SKIPPED for conditional execution:** Don't return `COMPLETED` with a "skipped" message — use the `SKIPPED` status to make intent explicit.

6. **Include partial output in failed steps:** Even when a step fails, include whatever data was gathered in the `output` field to aid debugging.

7. **Use to_dict() for SSE:** Always use the `to_dict()` method when broadcasting step results to ensure proper enum serialization.

8. **Check status before accessing output:** Verify a step completed successfully before using its output in subsequent steps.

## Type Summary

- **Type:** Pydantic `BaseModel`
- **Required fields:** `step_name`, `status`, `started_at`
- **Optional fields:** `output`, `error`, `completed_at`, `duration_ms`
- **Status values:** PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED
- **Serialization:** `to_dict()` method for SSE broadcasting
- **Purpose:** Capture outcome of single workflow step execution with timing, output, and error context
- **Integration:** Collected into `ActionResult.steps` for workflow-level results
