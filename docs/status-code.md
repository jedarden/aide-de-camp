# StatusCode (StepStatus) Enum Documentation

## Overview

The `StepStatus` enumeration (referred to as StatusCode in workflow execution contexts) defines all possible states of a workflow step execution in the Action Execution Model. Each step in an action workflow progresses through these states during its lifecycle, providing visibility into execution progress and enabling proper error handling and state management.

## Enum Definition

```python
class StepStatus(str, Enum):
    """Status of a workflow step execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
```

**Type:** String enumeration (enum values are strings for JSON serialization)  
**Module:** `src.action.models`  
**Used by:** `StepResult`, `ActionResult`, step executors

## Status Code Reference

| Name | Value | Semantics | State Type |
|------|-------|-----------|------------|
| `PENDING` | `"pending"` | Step has been created but not yet started execution | Intermediate |
| `IN_PROGRESS` | `"in_progress"` | Step is currently executing with async operations in flight | Intermediate |
| `COMPLETED` | `"completed"` | Step finished successfully with valid output | Terminal |
| `FAILED` | `"failed"` | Step execution encountered an error or exception | Terminal |
| `SKIPPED` | `"skipped"` | Step was not executed due to preconditions or workflow logic | Terminal |

## State Transitions

### Transition Graph

```
                    ┌─────────────────┐
                    │    PENDING      │
                    │  (created but   │
                    │  not started)   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  IN_PROGRESS    │
                    │   (executing)   │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
    │  COMPLETED    │ │   FAILED      │ │   SKIPPED     │
    │  (success)    │ │  (error)      │ │ (not run)     │
    └───────────────┘ └───────────────┘ └───────────────┘
         (terminal)        (terminal)        (terminal)
```

### Transition Rules

| From State | To State | Condition | Description |
|------------|----------|-----------|-------------|
| `PENDING` | `IN_PROGRESS` | Step executor starts | Always transitions when execution begins |
| `IN_PROGRESS` | `COMPLETED` | Step executes successfully | All logic completes without error, output produced |
| `IN_PROGRESS` | `FAILED` | Exception or error detected | Uncaught exception, timeout, validation failure |
| `IN_PROGRESS` | `SKIPPED` | Precondition not met | Guard condition evaluates to false during execution |
| `COMPLETED` | — | — | Terminal state — no further transitions |
| `FAILED` | — | — | Terminal state — no further transitions |
| `SKIPPED` | — | — | Terminal state — no further transitions |

### Invalid Transitions

These transitions **never** occur in normal operation:

- `PENDING` → `COMPLETED` (must pass through `IN_PROGRESS`)
- `PENDING` → `FAILED` (must pass through `IN_PROGRESS`)
- `PENDING` → `SKIPPED` (must pass through `IN_PROGRESS`)
- `IN_PROGRESS` → `PENDING` (cannot go back)
- `COMPLETED` → `FAILED` (terminal states don't transition)
- `FAILED` → `COMPLETED` (terminal states don't transition)
- Any transition from a terminal state

## Decision Tree for Status Progression

```
                    START (step created)
                            │
                            ▼
                    ┌───────────────┐
                    │   PENDING     │
                    └───────┬───────┘
                            │
                ┌───────────▼───────────┐
                │ Step executor starts? │
                └───────────┬───────────┘
                            │ YES
                            ▼
                    ┌───────────────┐
                    │ IN_PROGRESS   │
                    └───────┬───────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ Success       │ │ Error/Exception│ │ Guard condition│
│ (no errors)   │ │ (raised)       │ │ (false)        │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  COMPLETED    │ │   FAILED      │ │   SKIPPED     │
│  (output set, │ │  (error set,  │ │ (reason set,  │
│  error=None)  │ │  output may   │ │  error=None)  │
└───────────────┘ └───────────────┘ └───────────────┘
```

## Terminal vs Intermediate States

### Intermediate States
These states represent **in-progress** execution and are **not final**:

- **`PENDING`**: Initial state, step is queued but not yet executing
- **`IN_PROGRESS`**: Step is actively executing, waiting for completion

**Characteristics:**
- May have incomplete `output` field
- `completed_at` timestamp may be `None`
- `duration_ms` may be zero or still counting
- Can transition to multiple terminal states

### Terminal States
These states represent **final outcomes** and **do not transition further**:

- **`COMPLETED`**: Successful completion with valid output
- **`FAILED`**: Failure with error condition
- **`SKIPPED`**: Not executed due to workflow logic

**Characteristics:**
- `completed_at` timestamp is set
- `duration_ms` is finalized
- No further state changes occur
- Workflow logic determines next steps based on terminal state

## Status Semantics in Detail

### PENDING
**Meaning:** Step has been instantiated in a workflow but execution has not yet begun.

**When set:**
- Initial state when a step is created in a workflow definition
- Step is waiting in the execution queue

**Field characteristics:**
- `output`: Empty dict `{}`
- `error`: `None`
- `started_at`: Set to creation time or `None` if not yet scheduled
- `completed_at`: `None`
- `duration_ms`: `0.0`

**Use case:** Workflow planning and queuing phase.

**Example:**
```python
step = Step(
    step_type="ci_status",
    description="Check CI workflow status"
)
# StepResult would be PENDING here if created before execution
```

### IN_PROGRESS
**Meaning:** Step is currently executing with async operations (kubectl queries, HTTP requests, git operations) in flight.

**When set:**
- Immediately before step executor's main logic runs
- Long-running operations are active

**Field characteristics:**
- `output`: Partial or empty (still being populated)
- `error`: `None`
- `started_at`: Set to execution start time
- `completed_at`: `None` (not yet completed)
- `duration_ms`: `0.0` or still counting

**Use case:** Active execution phase for long-running steps.

**Example:**
```python
async def execute_ci_status_step(ctx: ExecutionContext) -> StepResult:
    started_at = time.time()
    
    # Status would be IN_PROGRESS here
    logger.info(f"Starting CI status check for {ctx.project_slug}")
    
    ci_result = await check_ci_status(ctx.project_slug)  # Async operation
    
    # Continue to COMPLETED or FAILED after this
```

### COMPLETED
**Meaning:** Step finished successfully and produced valid output data.

**When set:**
- After step executor completes without errors
- Output data has been populated successfully

**Field characteristics:**
- `output`: Contains step-specific results
- `error`: `None` (successful steps have no error)
- `started_at`: Set
- `completed_at`: Set to completion time
- `duration_ms`: Calculated as `(completed_at - started_at) * 1000`

**Use case:** Successful CI checks, pod queries, GitOps commits.

**Example:**
```python
return StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={
        "workflow_name": "mta-my-way-build",
        "status": "Succeeded",
        "build_number": 123,
        "image_tag": "v1.2.3"
    },
    error=None,
    started_at=started_at,
    completed_at=time.time(),
    duration_ms=2500.0,
)
```

### FAILED
**Meaning:** Step execution encountered an error, exception, or timeout condition.

**When set:**
- When step executor raises an uncaught exception
- When a timeout condition is detected
- When validation or precondition checks fail

**Field characteristics:**
- `output`: May contain partial results or diagnostic data
- `error`: Contains error message (required for failed steps)
- `started_at`: Set
- `completed_at`: Set to failure time
- `duration_ms`: Calculated up to failure point

**Use case:** CI failures, kubectl errors, git push failures, timeouts.

**Example:**
```python
try:
    ci_result = await check_ci_status(ctx.project_slug)
    if ci_result["status"] == "Failed":
        raise ValueError("CI workflow failed")
except Exception as e:
    return StepResult(
        step_name="ci_status",
        status=StepStatus.FAILED,
        output={"attempted_workflow": "mta-my-way-build"},
        error=f"CI check failed: {str(e)}",
        started_at=started_at,
        completed_at=time.time(),
        duration_ms=5000.0,
    )
```

### SKIPPED
**Meaning:** Step was not executed due to guard conditions, dry_run mode, or workflow logic that determined the step was unnecessary.

**When set:**
- When `ctx.dry_run == True` for mutating steps
- When guard condition evaluates to false
- When workflow logic determines step is not applicable

**Field characteristics:**
- `output`: Typically contains skip reason explanation
- `error`: `None` (skipped steps are not failures)
- `started_at`: Set
- `completed_at`: Set to skip decision time
- `duration_ms`: Fast (near-zero)

**Use case:** Conditional steps that don't apply to current context.

**Example:**
```python
# Skip if dry_run is enabled
if ctx.dry_run:
    return StepResult(
        step_name="gitops_commit",
        status=StepStatus.SKIPPED,
        output={"reason": "dry_run enabled, mutation skipped"},
        error=None,  # Not a failure
        started_at=time.time(),
        completed_at=time.time(),
        duration_ms=50.0,  # Fast decision
    )
```

## Workflow Execution Patterns

### Fail-Fast Pattern
Workflow halts immediately when a critical step fails:

```python
step1 = await execute_ci_status_step(ctx)

# Check for FAILED terminal state before proceeding
if step1.status == StepStatus.FAILED:
    return ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="deploy",
        status="failed",
        steps=[step1],
        error=f"CI check failed: {step1.error}",
        started_at=start_time,
        completed_at=time.time(),
        duration_ms=(time.time() - start_time) * 1000,
    )

# Only proceed if step1 is COMPLETED
step2 = await execute_gitops_commit_step(ctx)
```

### Continue-On-Error Pattern
Workflow continues through non-critical failures:

```python
results = []
all_succeeded = True

for step_def in workflow.steps:
    result = await execute_step(step_def, ctx)
    results.append(result)
    
    # Track terminal FAILED states but continue
    if result.status == StepStatus.FAILED:
        all_succeeded = False
        logger.warning(f"Step failed but continuing: {result.step_name}")

# Overall result depends on step results
final_status = "completed" if all_succeeded else "partial_failure"
```

### Conditional Execution Pattern
Subsequent steps use previous step results to decide execution:

```python
check_result = await execute_deployment_exists_step(ctx)

if check_result.status == StepStatus.COMPLETED:
    deployment_exists = check_result.output.get("exists", False)
    
    if deployment_exists:
        # Branch A: Update existing deployment
        result = await execute_update_deployment_step(ctx)
    else:
        # Branch B: Create new deployment
        result = await execute_create_deployment_step(ctx)
else:
    # Check failed, can't proceed
    result = check_result
```

## Usage in Step Executors

### Standard Execution Template
```python
async def execute_step_template(ctx: ExecutionContext) -> StepResult:
    """Template showing proper status handling."""
    started_at = time.time()
    
    try:
        # IN_PROGRESS phase
        logger.info(f"Starting {step_name}")
        
        # Execute step logic
        result_data = await perform_step_operation(ctx)
        
        # Transition to COMPLETED terminal state
        return StepResult(
            step_name=step_name,
            status=StepStatus.COMPLETED,
            output=result_data,
            error=None,
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
        
    except Exception as e:
        # Transition to FAILED terminal state
        logger.error(f"Step failed: {str(e)}")
        return StepResult(
            step_name=step_name,
            status=StepStatus.FAILED,
            output={},
            error=str(e),
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
```

### Conditional Execution Template
```python
async def execute_conditional_step(ctx: ExecutionContext) -> StepResult:
    """Template showing skip conditions."""
    started_at = time.time()
    
    # Check guard condition before execution
    if not should_execute_step(ctx):
        # Direct transition to SKIPPED terminal state
        return StepResult(
            step_name=step_name,
            status=StepStatus.SKIPPED,
            output={"reason": "Guard condition not met"},
            error=None,
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
    
    # Proceed with normal execution
    try:
        result_data = await perform_step_operation(ctx)
        return StepResult(
            step_name=step_name,
            status=StepStatus.COMPLETED,
            output=result_data,
            error=None,
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
    except Exception as e:
        return StepResult(
            step_name=step_name,
            status=StepStatus.FAILED,
            output={},
            error=str(e),
            started_at=started_at,
            completed_at=time.time(),
            duration_ms=(time.time() - started_at) * 1000,
        )
```

## Status Checking Patterns

### Checking for Success
```python
if step_result.status == StepStatus.COMPLETED:
    logger.info(f"Step succeeded: {step_result.step_name}")
    output_data = step_result.output
    # Process output
```

### Checking for Failure
```python
if step_result.status == StepStatus.FAILED:
    logger.error(f"Step failed: {step_result.step_name} - {step_result.error}")
    # Handle error or halt workflow
```

### Checking for Skip
```python
if step_result.status == StepStatus.SKIPPED:
    logger.info(f"Step skipped: {step_result.step_name}")
    reason = step_result.output.get("reason", "unknown")
    # Use default values or alternative logic
```

### Comprehensive Success Check
```python
# Consider both COMPLETED and SKIPPED as "not failed"
if step_result.status in (StepStatus.COMPLETED, StepStatus.SKIPPED):
    # Step didn't fail
    pass
elif step_result.status == StepStatus.FAILED:
    # Handle failure
    pass
```

## Integration with ActionResult

Workflow-level status aggregates step statuses:

```python
# In ActionExecutor after collecting step results
def determine_workflow_status(steps: list[StepResult]) -> str:
    """Determine overall workflow status from step results."""
    
    # Check for any failures
    if any(s.status == StepStatus.FAILED for s in steps):
        return "failed"
    
    # Check if any steps are still running
    if any(s.status == StepStatus.IN_PROGRESS for s in steps):
        return "running"
    
    # All steps completed successfully or were skipped
    return "completed"
```

## Best Practices

1. **Always transition through intermediate states:** Never jump directly from `PENDING` to a terminal state — always use `IN_PROGRESS` as the bridge.

2. **Set timestamps accurately:** Use `time.time()` at exact moments for `started_at` and `completed_at` to ensure accurate `duration_ms` calculations.

3. **Use descriptive error messages:** When setting `FAILED` status, provide actionable error context in the `error` field.

4. **Distinguish skip from failure:** Use `SKIPPED` for conditional non-execution (not a failure) and `FAILED` only for errors.

5. **Include partial output in failed steps:** Even when a step fails, include whatever data was gathered to aid debugging.

6. **Check status before using output:** Verify a step reached `COMPLETED` status before accessing its output in subsequent steps.

7. **Document terminal state meanings:** Each terminal state (`COMPLETED`, `FAILED`, `SKIPPED`) should have clear semantics in your workflow context.

8. **Use status checks in workflow logic:** Branch workflow execution based on step terminal states to implement robust error handling.

## Summary

The `StepStatus` enumeration provides a clear, well-defined state machine for workflow step execution:

- **5 states**: 2 intermediate (`PENDING`, `IN_PROGRESS`), 3 terminal (`COMPLETED`, `FAILED`, `SKIPPED`)
- **Unidirectional transitions**: Progress flows forward only, never backwards
- **Terminal state semantics**: Each terminal state has distinct meaning and characteristics
- **Workflow integration**: Status values drive workflow branching and error handling
- **Serialization**: String enum values for easy JSON serialization in SSE events

This status model enables robust workflow execution with clear failure modes, conditional execution support, and comprehensive progress tracking via SSE events to the canvas UI.
