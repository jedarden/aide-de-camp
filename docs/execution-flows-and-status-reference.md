# Execution Flows and Status Code Reference

## Overview

This document provides comprehensive execution flow diagrams and detailed status code reference tables for the Action Execution Model in aide-de-camp. It serves as a visual guide to understanding how workflows execute, steps transition through states, and errors propagate through the system.

## Table of Contents

1. [Step Lifecycle Execution Flow](#step-lifecycle-execution-flow)
2. [Parallel vs Sequential Execution Flows](#parallel-vs-sequential-execution-flows)
3. [Comprehensive Status Code Reference](#comprehensive-status-code-reference)
4. [Error Propagation and Retry Logic](#error-propagation-and-retry-logic)
5. [Decision Tree Diagrams for Common Scenarios](#decision-tree-diagrams-for-common-scenarios)

---

## Step Lifecycle Execution Flow

### Complete Step Lifecycle Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STEP CREATION & INITIALIZATION                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PENDING STATE                                   │
│  • Step created in workflow definition                                      │
│  • Waiting in execution queue                                               │
│  • No active operations                                                    │
│  • Characteristics: output={}, error=None, started_at=set, completed_at=None│
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Step executor starts
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            IN_PROGRESS STATE                                 │
│  • Step actively executing                                                 │
│  • Async operations in flight (kubectl, HTTP, git)                         │
│  • Logging and monitoring active                                          │
│  • Characteristics: output populating, error=None, completed_at=None       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                │ Success           │ Error/Exception   │ Guard Condition
                │ (no errors)       │ (raised)          │ (false)
                │                   │                   │
                ▼                   ▼                   ▼
┌───────────────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│      COMPLETED STATE       │ │    FAILED STATE    │ │   SKIPPED STATE    │
│ • Step finished successfully│ • Step encountered │ • Step not executed │
│ • Valid output data        │   error/exception   │   due to logic      │
│ • error=None               │ • error set         │ • error=None        │
│ • Terminal state           │ • Terminal state    │ • Terminal state    │
└───────────────────────────┘ └───────────────────┘ └───────────────────┘
```

### Step Lifecycle Detailed Timeline

```
TIME ──────────────────────────────────────────────────────────────────────>

     t0                     t1                    t2                    t3
     │                      │                     │                     │
     ▼                      ▼                     ▼                     ▼
┌─────────┐          ┌──────────┐          ┌──────────┐          ┌──────────┐
│ PENDING │─────────▶│IN_PROGRESS│─────────▶│COMPLETED │─────────▶│ CLEANUP  │
│         │          │          │          │          │          │          │
│ • Queue │          │ • Active │          │ • Output │          │ • Persist│
│ • Ready │          │ • Async  │          │ • Timing │          │ • SSE    │
└─────────┘          └──────────┘          └──────────┘          └──────────┘

FAILED PATH:
     t0                     t1                    t2
     │                      │                     │
     ▼                      ▼                     ▼
┌─────────┐          ┌──────────┐          ┌──────────┐
│ PENDING │─────────▶│IN_PROGRESS│─────────▶│  FAILED  │
│         │          │          │          │          │
│ • Queue │          │ • Active │          │ • Error  │
│ • Ready │          │ • Async  │          │ • Partial│
└─────────┘          └──────────┘          └──────────┘
```

### Step State Transition Matrix

| Current State | Can Transition To | Transition Condition | Required Fields Set |
|---------------|-------------------|---------------------|---------------------|
| `PENDING` | `IN_PROGRESS` | Step executor begins execution | `started_at` |
| `IN_PROGRESS` | `COMPLETED` | Step logic completes without errors | `output`, `completed_at`, `duration_ms` |
| `IN_PROGRESS` | `FAILED` | Exception raised or error detected | `error`, `completed_at`, `duration_ms` |
| `IN_PROGRESS` | `SKIPPED` | Guard condition evaluates to false | `output`, `completed_at`, `duration_ms` |
| `COMPLETED` | *(none)* | Terminal state - no transitions | All fields finalized |
| `FAILED` | *(none)* | Terminal state - no transitions | All fields finalized |
| `SKIPPED` | *(none)* | Terminal state - no transitions | All fields finalized |

---

## Parallel vs Sequential Execution Flows

### Sequential Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SEQUENTIAL WORKFLOW EXECUTION                          │
└─────────────────────────────────────────────────────────────────────────────┘

User Utterance "Deploy mta-my-way to production"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INTENT ROUTER                                       │
│  Classifies utterance → project_slug="mta-my-way", workflow="deploy"       │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXECUTION CONTEXT CREATED                                │
│  intent_id="abc123", session_id="sess456", project_cfg loaded              │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STEP 1: CI_STATUS                                   │
│  • Status: PENDING → IN_PROGRESS → COMPLETED                               │
│  • Duration: 2.5s                                                           │
│  • Output: {workflow_name: "mta-my-way-build", status: "Succeeded"}       │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    │ (Step 1 succeeded)
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STEP 2: IMAGE_TAG                                   │
│  • Status: PENDING → IN_PROGRESS → COMPLETED                               │
│  • Duration: 0.8s                                                           │
│  • Output: {image_tag: "v1.2.3"}                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    │ (Step 2 succeeded)
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STEP 3: GITOPS_COMMIT                               │
│  • Status: PENDING → IN_PROGRESS → COMPLETED                               │
│  • Duration: 3.2s                                                           │
│  • Output: {commit: "abc123def", repo_path: "/path/to/repo"}               │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    │ (Step 3 succeeded)
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STEP 4: ARGOCD_SYNC                                 │
│  • Status: PENDING → IN_PROGRESS → COMPLETED                               │
│  • Duration: 15.0s                                                          │
│  • Output: {sync_status: "Synced", application: "mta-my-way"}               │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ACTION RESULT (COMPLETED)                                │
│  • Total duration: 21.5s                                                    │
│  • All steps: COMPLETED                                                    │
│  • Workflow status: "completed"                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TOTAL TIME: 21.5 seconds (sum of all step durations)
```

### Parallel Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PARALLEL WORKFLOW EXECUTION                           │
└─────────────────────────────────────────────────────────────────────────────┘

User Utterance "Check status of all production services"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INTENT ROUTER                                       │
│  Classifies utterance → intent_type="status_monitor", parallel=true        │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXECUTION CONTEXT CREATED                                │
│  intent_id="xyz789", session_id="sess456", project_cfg loaded              │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
        ┌───────────┴───────────┐
        │   PARALLEL DISPATCH  │
        └───────────┬───────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
    ▼               ▼               ▼
┌─────────┐   ┌─────────┐   ┌─────────┐
│ STEP 1  │   │ STEP 2  │   │ STEP 3  │
│CI_STATUS│   │POD_STATUS│   │DEPLOY   │
│         │   │         │   │INFO     │
│PENDING  │   │PENDING  │   │PENDING  │
→ IN     │   → IN     │   → IN     │
→ PROG   │   → PROG   │   → PROG   │
→ COMP   │   → COMP   │   → COMP   │
(2.5s)   │   (8.0s)   │   (4.0s)   │
└─────────┘   └─────────┘   └─────────┘
    │               │               │
    └───────────────┼───────────────┘
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RESULTS AGGREGATION                                      │
│  • Collect all StepResult objects                                          │
│  • Check for any failures                                                   │
│  • Determine overall workflow status                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ACTION RESULT (COMPLETED)                                │
│  • Total duration: 8.0s (longest step, not sum)                            │
│  • All steps: COMPLETED                                                    │
│  • Workflow status: "completed"                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TOTAL TIME: 8.0 seconds (longest step duration)
```

### Parallel vs Sequential Comparison Table

| Aspect | Sequential Execution | Parallel Execution |
|--------|---------------------|-------------------|
| **Total Duration** | Sum of all step durations | Longest step duration |
| **Dependencies** | Steps can depend on previous outputs | Steps are independent |
| **Error Handling** | Fail-fast: stops on first error | Continue-on-error: completes all steps |
| **Memory Usage** | Lower: one step active at a time | Higher: multiple steps active |
| **Complexity** | Simpler: linear execution | Complex: requires coordination |
| **Use Cases** | Workflows with dependencies | Monitoring, status checks |
| **Example Duration** | 21.5s (4 steps × 5.4s avg) | 8.0s (longest step) |

### Hybrid Execution Flow (Mixed Parallel + Sequential)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      HYBRID WORKFLOW EXECUTION                              │
└─────────────────────────────────────────────────────────────────────────────┘

User Utterance "Deploy and monitor all services"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE 1: PARALLEL CHECKS                            │
│  (Independent steps run concurrently)                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
    ┌───────┐ ┌─────────┐ ┌──────────┐
    │ STEP 1│ │ STEP 2  │ │  STEP 3  │
    │ CI_   │ │ POD_    │ │ DEPLOY_  │
    │ STATUS│ │ STATUS  │ │  INFO    │
    │ 2.5s  │ │ 8.0s    │ │  4.0s    │
    └───────┘ └─────────┘ └──────────┘
        │           │           │
        └───────────┼───────────┘
                    ▼ (8.0s elapsed)
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE 2: SEQUENCE DEPLOY                             │
│  (Sequential steps using outputs from Phase 1)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STEP 4: GITOPS_COMMIT                               │
│  • Uses output from Step 1 (image_tag)                                       │
│  • Duration: 3.2s                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STEP 5: ARGOCD_SYNC                                 │
│  • Uses output from Step 4 (commit SHA)                                      │
│  • Duration: 15.0s                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ACTION RESULT (COMPLETED)                                │
│  • Total duration: 26.2s (8.0s + 3.2s + 15.0s)                              │
│  • Phase 1: Parallel (8.0s)                                                 │
│  • Phase 2: Sequential (18.2s)                                              │
└─────────────────────────────────────────────────────────────────────────────┘

TOTAL TIME: 26.2 seconds (vs 40.7s if fully sequential)
```

---

## Comprehensive Status Code Reference

### Status Code Quick Reference

| Status Code | Value | State Type | Description | Terminal? |
|-------------|-------|-----------|-------------|----------|
| `PENDING` | `"pending"` | Intermediate | Step created but not yet started | No |
| `IN_PROGRESS` | `"in_progress"` | Intermediate | Step actively executing | No |
| `COMPLETED` | `"completed"` | Terminal | Step finished successfully | Yes |
| `FAILED` | `"failed"` | Terminal | Step encountered error | Yes |
| `SKIPPED` | `"skipped"` | Terminal | Step not executed due to logic | Yes |

### Detailed Status Code Reference

#### PENDING
- **Value:** `"pending"`
- **Type:** Intermediate State
- **Description:** Step has been instantiated in a workflow but execution has not yet begun.
- **When Used:** 
  - Initial state when a step is created in a workflow definition
  - Step is waiting in the execution queue
  - Pre-execution validation phase
- **Field Characteristics:**
  - `output`: Empty dict `{}`
  - `error`: `None`
  - `started_at`: Set to creation time or `None`
  - `completed_at`: `None`
  - `duration_ms`: `0.0`
- **Example Usage:**
  ```python
  step = Step(
      step_type="ci_status",
      description="Check CI workflow status"
  )
  # StepResult would be PENDING here if created before execution
  ```
- **Transition:** Always transitions to `IN_PROGRESS` when execution begins.

#### IN_PROGRESS
- **Value:** `"in_progress"`
- **Type:** Intermediate State
- **Description:** Step is currently executing with async operations (kubectl queries, HTTP requests, git operations) in flight.
- **When Used:**
  - Immediately before step executor's main logic runs
  - Long-running operations are active
  - Logging and monitoring are in progress
- **Field Characteristics:**
  - `output`: Partial or empty (still being populated)
  - `error`: `None`
  - `started_at`: Set to execution start time
  - `completed_at`: `None` (not yet completed)
  - `duration_ms`: `0.0` or still counting
- **Example Usage:**
  ```python
  async def execute_ci_status_step(ctx: ExecutionContext) -> StepResult:
      started_at = time.time()
      
      # Status would be IN_PROGRESS here
      logger.info(f"Starting CI status check for {ctx.project_slug}")
      
      ci_result = await check_ci_status(ctx.project_slug)  # Async operation
      
      # Continue to COMPLETED or FAILED after this
  ```
- **Transitions:** 
  - To `COMPLETED` on success
  - To `FAILED` on exception or error condition
  - To `SKIPPED` if precondition is not met

#### COMPLETED
- **Value:** `"completed"`
- **Type:** Terminal State
- **Description:** Step finished successfully and produced valid output data.
- **When Used:**
  - After step executor completes without errors
  - Output data has been populated successfully
  - All validations passed
- **Field Characteristics:**
  - `output`: Contains step-specific results
  - `error`: `None` (successful steps have no error)
  - `started_at`: Set
  - `completed_at`: Set to completion time
  - `duration_ms`: Calculated as `(completed_at - started_at) * 1000`
- **Example Usage:**
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
- **Transition:** Terminal state — no further transitions.

#### FAILED
- **Value:** `"failed"`
- **Type:** Terminal State
- **Description:** Step execution encountered an error, exception, or timeout condition.
- **When Used:**
  - When step executor raises an uncaught exception
  - When a timeout condition is detected
  - When validation or precondition checks fail critically
- **Field Characteristics:**
  - `output`: May contain partial results or diagnostic data
  - `error`: Contains error message (required for failed steps)
  - `started_at`: Set
  - `completed_at`: Set to failure time
  - `duration_ms`: Calculated up to failure point
- **Example Usage:**
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
- **Transition:** Terminal state — no further transitions.

#### SKIPPED
- **Value:** `"skipped"`
- **Type:** Terminal State
- **Description:** Step was not executed due to guard conditions, dry_run mode, or workflow logic that determined the step was unnecessary.
- **When Used:**
  - When `ctx.dry_run == True` for mutating steps
  - When guard condition evaluates to false
  - When workflow logic determines step is not applicable
- **Field Characteristics:**
  - `output`: Typically contains skip reason explanation
  - `error`: `None` (skipped steps are not failures)
  - `started_at`: Set
  - `completed_at`: Set to skip decision time
  - `duration_ms`: Fast (near-zero)
- **Example Usage:**
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
- **Transition:** Terminal state — no further transitions.

### Status Code Decision Matrix

| Scenario | Status to Use | Error Field Set? | Output Contains? | Reason |
|----------|--------------|------------------|------------------|---------|
| Step not started yet | `PENDING` | No | No | Initial state |
| Step actively running | `IN_PROGRESS` | No | Partial/Maybe | Active execution |
| Step succeeded | `COMPLETED` | No | Yes | Successful completion |
| Exception raised | `FAILED` | Yes | Partial/Maybe | Error occurred |
| Timeout exceeded | `FAILED` | Yes | Partial/Maybe | Timeout error |
| Validation failed | `FAILED` | Yes | Maybe | Invalid state |
| Guard condition false | `SKIPPED` | No | Yes (reason) | Conditional skip |
| dry_run mode active | `SKIPPED` | No | Yes (dry_run) | Safety skip |
| Step not applicable | `SKIPPED` | No | Yes (not_applicable) | Context skip |

### Status Code Validation Rules

```python
# Valid status transitions
VALID_TRANSITIONS = {
    "PENDING": ["IN_PROGRESS"],
    "IN_PROGRESS": ["COMPLETED", "FAILED", "SKIPPED"],
    "COMPLETED": [],  # Terminal
    "FAILED": [],     # Terminal
    "SKIPPED": [],    # Terminal
}

# Status field requirements
STATUS_FIELD_REQUIREMENTS = {
    "PENDING": {
        "required": ["started_at"],
        "optional": ["step_name"],
        "prohibited": ["completed_at", "duration_ms", "error"],
    },
    "IN_PROGRESS": {
        "required": ["started_at"],
        "optional": ["step_name", "output"],
        "prohibited": ["completed_at", "error"],
    },
    "COMPLETED": {
        "required": ["started_at", "completed_at", "duration_ms", "output"],
        "optional": ["step_name"],
        "prohibited": ["error"],
    },
    "FAILED": {
        "required": ["started_at", "completed_at", "duration_ms", "error"],
        "optional": ["step_name", "output"],
        "prohibited": [],
    },
    "SKIPPED": {
        "required": ["started_at", "completed_at", "duration_ms", "output"],
        "optional": ["step_name"],
        "prohibited": ["error"],
    },
}

# Terminal state check
def is_terminal_status(status: StepStatus) -> bool:
    return status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED)

# Intermediate state check
def is_intermediate_status(status: StepStatus) -> bool:
    return status in (StepStatus.PENDING, StepStatus.IN_PROGRESS)
```

---

## Error Propagation and Retry Logic

### Error Propagation Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ERROR PROPAGATION THROUGH WORKFLOW                       │
└─────────────────────────────────────────────────────────────────────────────┘

User Utterance → Intent Router → ExecutionContext → ActionExecutor
                                                    │
                                                    ▼
                                    ┌─────────────────────────────────┐
                                    │      STEP 1: CI_STATUS          │
                                    │      PENDING → IN_PROGRESS      │
                                    └────────────┬────────────────────┘
                                                 │
                                    ┌────────────▼────────────────────┐
                                    │    ERROR: CI workflow failed     │
                                    │    Exception raised             │
                                    └────────────┬────────────────────┘
                                                 │
                                    ┌────────────▼────────────────────┐
                                    │      STEP 1: FAILED             │
                                    │      error="CI workflow failed"  │
                                    │      output={attempted: "..."}  │
                                    └────────────┬────────────────────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    │                            │                            │
                    ▼                            ▼                            ▼
        ┌───────────────────┐      ┌────────────────────┐      ┌───────────────────┐
        │  FAIL-FAST MODE   │      │ CONTINUE-ON-ERROR  │      │  RETRY LOGIC      │
        │                   │      │                    │      │                   │
        │ Workflow halts   │      │ Step 2 executes    │      │ Retry with backoff│
        │ Remaining steps   │      │ despite step 1     │      │ up to N attempts  │
        │ marked SKIPPED   │      │ failure            │      │ with exponential  │
        └───────────────────┘      └────────────────────┘      │ backoff           │
                                                           └───────────────────┘
```

### Error Handling Patterns

#### Fail-Fast Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FAIL-FAST ERROR HANDLING                           │
└─────────────────────────────────────────────────────────────────────────────┘

STEP 1 (CI_STATUS)          STEP 2 (IMAGE_TAG)        STEP 3 (GITOPS_COMMIT)
┌─────────────────┐         ┌─────────────────┐       ┌─────────────────┐
│ PENDING         │         │ NOT EXECUTED    │       │ NOT EXECUTED    │
│ ↓               │         │ (skipped)       │       │ (skipped)       │
│ IN_PROGRESS     │         │ due to step 1   │       │ due to step 1   │
│ ↓               │         │ failure         │       │ failure         │
│ FAILED          │         │                 │       │                 │
│ error: "CI      │         │                 │       │                 │
│  workflow       │         │                 │       │                 │
│  failed"        │         │                 │       │                 │
└─────────────────┘         └─────────────────┘       └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ACTION RESULT (FAILED)                                   │
│  • status: "failed"                                                         │
│  • error: "Workflow failed at step 1: CI workflow failed"                 │
│  • steps: [StepResult(FAILED), StepResult(SKIPPED), StepResult(SKIPPED)] │
│  • Total duration: 2.5s (only step 1 executed)                             │
└─────────────────────────────────────────────────────────────────────────────┘

CHARACTERISTICS:
• Immediate workflow halt on first failure
• Remaining steps marked SKIPPED with reason
• Fast failure detection
• Clear error attribution
• Used for critical workflows where all steps must succeed
```

#### Continue-On-Error Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CONTINUE-ON-ERROR HANDLING                            │
└─────────────────────────────────────────────────────────────────────────────┘

STEP 1 (CI_STATUS)          STEP 2 (IMAGE_TAG)        STEP 3 (GITOPS_COMMIT)
┌─────────────────┐         ┌─────────────────┐       ┌─────────────────┐
│ PENDING         │         │ PENDING          │       │ PENDING          │
│ ↓               │         │ ↓                │       │ ↓                │
│ IN_PROGRESS     │         │ IN_PROGRESS      │       │ IN_PROGRESS      │
│ ↓               │         │ ↓                │       │ ↓                │
│ FAILED          │         │ COMPLETED        │       │ FAILED           │
│ error: "CI      │         │ output: {tag:    │       │ error: "Cannot   │
│  workflow       │         │   "v1.2.3"}      │       │  commit without   │
│  failed"        │         │ duration: 0.8s   │       │  completed CI"   │
│ duration: 2.5s  │         │                 │       │ duration: 0.5s    │
└─────────────────┘         └─────────────────┘       └─────────────────┘
         │                            │                         │
         └────────────────────────────┼─────────────────────────┘
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ACTION RESULT (PARTIAL_FAILURE)                          │
│  • status: "partial_failure"                                                │
│  • error: "2 of 3 steps failed: CI_STATUS, GITOPS_COMMIT"                  │
│  • steps: [FAILED, COMPLETED, FAILED]                                       │
│  • Total duration: 3.8s (all steps executed)                                │
└─────────────────────────────────────────────────────────────────────────────┘

CHARACTERISTICS:
• All steps execute regardless of failures
• Complete error visibility
• Maximum diagnostic information
• Used for monitoring, diagnostic workflows
• Aggregates all failures for comprehensive reporting
```

### Retry Logic Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RETRY LOGIC WITH EXPONENTIAL BACKOFF                 │
└─────────────────────────────────────────────────────────────────────────────┘

STEP: CI_STATUS (with retry on transient failures)
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ATTEMPT 1 (t=0s)                                         │
│  • PENDING → IN_PROGRESS → FAILED                                          │
│  • Error: "Connection timeout"                                            │
│  • Transient error detected → scheduling retry                            │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    │ Wait: 2^0 × 1s = 1s
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ATTEMPT 2 (t=1s)                                         │
│  • PENDING → IN_PROGRESS → FAILED                                          │
│  • Error: "Connection timeout"                                            │
│  • Still transient → scheduling retry                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    │ Wait: 2^1 × 1s = 2s
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ATTEMPT 3 (t=3s)                                         │
│  • PENDING → IN_PROGRESS → COMPLETED                                       │
│  • Success: CI workflow found                                             │
│  • Step succeeded after 2 retries                                          │
└─────────────────────────────────────────────────────────────────────────────┘

RETRY CONFIGURATION:
max_retries: 3
backoff_base: 1s
backoff_multiplier: 2
transient_errors: ["timeout", "connection", "temporary"]

TOTAL TIME: 3s (vs immediate failure if no retry)
```

### Error Recovery Decision Tree

```
                        ERROR DETECTED IN STEP
                                │
                ┌───────────────┼───────────────┐
                │               │               │
            TRANSIENT      PERMANENT      VALIDATION
            ERROR?         ERROR?         ERROR?
                │               │               │
                ▼               ▼               ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │  RETRY WITH   │  │  FAIL FAST   │  │  USER ACTION │
        │  BACKOFF      │  │  HALT WORKFLOW│  │  REQUIRED    │
        └──────────────┘  └──────────────┘  └──────────────┘
                │               │               │
                ▼               ▼               ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │ MAX RETRIES  │  │ MARK FAILED │  │ REQUEST USER │
        │ REACHED?     │  │ RETURN ERROR│  │ INPUT/CONFIG │
        └──────┬───────┘  └──────────────┘  └──────────────┘
               │               │               │
        ┌──────┴──────┐        │               │
        │            │        │               │
       YES          NO        │               │
        │            │        │               │
        ▼            ▼        ▼               ▼
    ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ GIVE   │ │ RETRY    │ │ PROPAGATE│ │ PROMPT  │
    │ UP     │ │ AGAIN    │ │ TO       │ │ USER    │
    │ FAILED │ │ WITH     │ │ WORKFLOW │ │ FOR    │
    │ STATE  │ │ LONGER   │ │ RESULT   │ │ FIX    │
    └────────┘ │ WAIT     │ └──────────┘ └──────────┘
               └──────────┘
```

### Error Aggregation Patterns

#### Step-Level Error Aggregation

```python
# Error aggregation from multiple steps
def aggregate_step_errors(steps: list[StepResult]) -> dict[str, Any]:
    """Aggregate errors from all failed steps."""
    failed_steps = [s for s in steps if s.status == StepStatus.FAILED]
    
    errors_by_step = {}
    for step in failed_steps:
        errors_by_step[step.step_name] = {
            "error": step.error,
            "duration_ms": step.duration_ms,
            "partial_output": step.output,
        }
    
    return {
        "total_failed": len(failed_steps),
        "total_steps": len(steps),
        "failure_rate": len(failed_steps) / len(steps),
        "errors_by_step": errors_by_step,
        "first_failure": failed_steps[0].step_name if failed_steps else None,
    }
```

#### Workflow-Level Error Summary

```python
# Workflow-level error aggregation
def create_workflow_error_summary(step_results: list[StepResult]) -> str:
    """Create human-readable error summary."""
    failed = [s for s in step_results if s.status == StepStatus.FAILED]
    skipped = [s for s in step_results if s.status == StepStatus.SKIPPED]
    
    summary_parts = []
    
    if failed:
        failed_names = [s.step_name for s in failed]
        summary_parts.append(f"Failed steps: {', '.join(failed_names)}")
    
    if skipped:
        skipped_names = [s.step_name for s in skipped]
        summary_parts.append(f"Skipped steps: {', '.join(skipped_names)}")
    
    return "; ".join(summary_parts) if summary_parts else "All steps completed"
```

---

## Decision Tree Diagrams for Common Scenarios

### Scenario 1: Deployment Workflow Decision Tree

```
                        USER: "Deploy mta-my-way to production"
                                │
                                ▼
                    ┌───────────────────────────┐
                    │    INTENT CLASSIFICATION   │
                    │  Intent: deploy            │
                    │  Project: mta-my-way       │
                    │  Environment: production    │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │    CONTEXT VALIDATION      │
                    │  Project exists?           │
                    │  Cluster accessible?       │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                   YES                          NO
                    │                           │
                    ▼                           ▼
        ┌───────────────────┐        ┌───────────────────┐
        │ STEP 1: CI_STATUS │        │ RETURN ERROR      │
        │ Check CI status  │        │ "Project not      │
        └─────────┬─────────┘        │  found or cluster │
                  │                  │  inaccessible"    │
                  ▼                  └───────────────────┘
        ┌───────────────────┐
        │ CI SUCCEEDED?     │
        └─────────┬─────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
       YES                  NO
        │                   │
        ▼                   ▼
┌───────────────────┐ ┌───────────────────┐
│ STEP 2: IMAGE_TAG │ │ RETURN ERROR      │
│ Get image tag     │ │ "CI workflow      │
└─────────┬─────────┘ │  failed, cannot   │
          │           │  deploy"          │
          ▼           └───────────────────┘
┌───────────────────┐
│ STEP 3: DRY_RUN?   │
└─────────┬─────────┘
          │
  ┌───────┴───────┐
  │               │
 YES              NO
  │               │
  ▼               ▼
┌─────────────┐ ┌───────────────────┐
│ SKIP TO     │ │ STEP 4:          │
│ STEP 5      │ │ GITOPS_COMMIT    │
└──────┬──────┘ │ Update manifest  │
       │        └─────────┬─────────┘
       │                  │
       │                  ▼
       │        ┌───────────────────┐
       │        │ COMMIT SUCCESS?  │
       │        └─────────┬─────────┘
       │                  │
       │        ┌─────────┴─────────┐
       │        │                   │
       │       YES                  NO
       │        │                   │
       │        ▼                   ▼
       │┌───────────────┐ ┌───────────────────┐
       ││ STEP 5:      │ │ RETURN ERROR      │
       ││ ARGOCD_SYNC  │ │ "Commit failed,   │
       ││ Sync app     │ │  cannot deploy"   │
       │└───────┬───────┘ └───────────────────┘
       │        │
       └────────┼────────┐
                │        │
                ▼        ▼
        ┌───────────────────┐
        │ RETURN SUCCESS   │
        │ "Deployed        │
        │  successfully"  │
        └───────────────────┘
```

### Scenario 2: Status Monitoring Decision Tree

```
                    USER: "Check status of all services"
                            │
                            ▼
                ┌───────────────────────────┐
                │    INTENT CLASSIFICATION   │
                │  Intent: status_monitor    │
                │  Parallel: true           │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │   IDENTIFY ALL SERVICES   │
                │  • mta-my-way             │
                │  • pbx-web                │
                │  • whisper-stt            │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │  PARALLEL STEP DISPATCH   │
                │  All services checked     │
                │  concurrently             │
                └─────────────┬─────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
     ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
     │ SERVICE 1   │ │ SERVICE 2   │ │ SERVICE 3   │
     │ mta-my-way  │ │ pbx-web     │ │ whisper-stt │
     │ ┌─────────┐ │ │ ┌─────────┐ │ │ ┌─────────┐ │
     │ │ CI      │ │ │ │ POD     │ │ │ │ DEPLOY  │ │
     │ │ STATUS  │ │ │ │ STATUS  │ │ │ │ INFO    │ │
     │ └────┬────┘ │ │ └────┬────┘ │ │ └────┬────┘ │
     │      │       │ │      │       │ │      │       │
     │  ┌───┴───┐   │ │  ┌───┴───┐   │ │  ┌───┴───┐   │
     │  │       │   │ │  │       │   │ │  │       │   │
     │  ▼       ▼   │ │  ▼       ▼   │ │  ▼       ▼   │
     │SUCCESS  FAIL │ │SUCCESS  FAIL │ │SUCCESS  FAIL │
     └─────┬───┬───┘─┘ └─────┬───┬───┘─┘ └─────┬───┬───┘─┘
           │   │             │   │             │   │
           └───┼─────────────┼───┼─────────────┼───┘
               │             │   │             │
               ▼             ▼   ▼             ▼
        ┌─────────────────────────────────────────┐
        │      AGGREGATE RESULTS                  │
        │  • Success count: 2/3                   │
        │  • Failure count: 1/3                    │
        │  • Partial failure state                │
        └────────────────┬────────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────────┐
        │      RETURN PARTIAL_SUCCESS             │
        │  • 2 services operational               │
        │  • 1 service failed (pbx-web)            │
        │  • Error details provided               │
        └─────────────────────────────────────────┘
```

### Scenario 3: Dry Run Execution Decision Tree

```
                    USER: "Preview deployment (dry run)"
                            │
                            ▼
                ┌───────────────────────────┐
                │    INTENT CLASSIFICATION   │
                │  Intent: deploy_preview    │
                │  dry_run: true             │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │  CREATE EXECUTION CONTEXT  │
                │  dry_run = True           │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │      STEP 1: CI_STATUS     │
                │  (read-only, executes)     │
                │  Status: COMPLETED         │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │      STEP 2: IMAGE_TAG    │
                │  (read-only, executes)    │
                │  Status: COMPLETED         │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │   STEP 3: GITOPS_COMMIT    │
                │  (mutating, checks dry_run)│
                └─────────────┬─────────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
          ctx.dry_run                  ctx.dry_run
          == True                      == False
                │                           │
                ▼                           ▼
    ┌───────────────────┐       ┌───────────────────┐
    │ STEP 3: SKIPPED   │       │ STEP 3: EXECUTE   │
    │ Status: SKIPPED   │       │ Status: COMPLETED  │
    │ Reason: "dry_run  │       │ Commit performed   │
    │  enabled"         │       └───────────────────┘
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │ STEP 4: ARGOCD    │
    │  SYNC (skipped)   │
    │ Status: SKIPPED   │
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │ RETURN PREVIEW    │
    │ • "Would deploy   │
    │   mta-my-way      │
    │   v1.2.3"         │
    │ • Skipped 2       │
    │   mutating steps  │
    └───────────────────┘
```

### Scenario 4: Error Recovery Decision Tree

```
                    ERROR DETECTED IN WORKFLOW
                            │
                            ▼
                ┌───────────────────────────┐
                │   ERROR CLASSIFICATION    │
                └─────────────┬─────────────┘
                              │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │ TRANSIENT   │   │ PERMANENT   │   │ VALIDATION  │
    │ ERROR       │   │ ERROR       │   │ ERROR       │
    └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
           │                 │                 │
           ▼                 ▼                 ▼
 ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
 │ RETRY WITH      │ │ FAIL IMMEDIATELY│ │ REQUEST USER    │
 │ EXPONENTIAL     │ │ HALT WORKFLOW   │ │ ACTION/INPUT    │
 │ BACKOFF         │ │ RETURN FAILED   │ │ BLOCK UNTIL     │
 └────────┬────────┘ └─────────────────┘ │ FIXED           │
          │                            └─────────────────┘
          ▼
 ┌─────────────────┐
 │ RETRY ATTEMPT   │
 │ COUNT < MAX?    │
 └────────┬────────┘
          │
  ┌───────┴────────┐
  │                │
 YES               NO
  │                │
  ▼                ▼
┌──────────────┐ ┌──────────────┐
│ RETRY AGAIN  │ │ GIVE UP      │
│ WITH LONGER  │ │ MARK FAILED  │
│ WAIT TIME    │ │ RETURN ERROR │
└──────────────┘ └──────────────┘
```

### Scenario 5: Conditional Step Execution

```
                    WORKFLOW WITH CONDITIONAL STEPS
                            │
                            ▼
                ┌───────────────────────────┐
                │   STEP 1: CHECK_CONDITION  │
                │   COMPLETED                │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │   EVALUATE CONDITION      │
                │   output["needs_action"]  │
                └─────────────┬─────────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
             TRUE                        FALSE
                │                           │
                ▼                           ▼
    ┌───────────────────┐       ┌───────────────────┐
    │ STEP 2A: EXECUTE  │       │ STEP 2B: SKIP     │
    │ ACTION            │       │ ALTERNATIVE       │
    │ Status: PENDING   │       │ Status: SKIPPED   │
    └─────────┬─────────┘       └─────────┬─────────┘
              │                            │
              ▼                            ▼
    ┌───────────────────┐       ┌───────────────────┐
    │ IN_PROGRESS       │       │ STEP 3: DEFAULT   │
    │ executing action  │       │ FALLBACK          │
    └─────────┬─────────┘       └─────────┬─────────┘
              │                            │
              ▼                            ▼
    ┌───────────────────┐       ┌───────────────────┐
    │ COMPLETED         │       │ COMPLETED         │
    │ action performed │       │ fallback executed │
    └─────────┬─────────┘       └─────────┬─────────┘
              │                            │
              └────────────┬───────────────┘
                           ▼
              ┌───────────────────┐
              │ STEP 4: CONTINUE   │
              │ (both paths merge) │
              │ Status: PENDING    │
              └─────────┬─────────┘
                        │
                        ▼
              ┌───────────────────┐
              │ IN_PROGRESS       │
              │ continuing workflow│
              └─────────┬─────────┘
                        │
                        ▼
              ┌───────────────────┐
              │ COMPLETED         │
              │ workflow complete │
              └───────────────────┘
```

---

## Summary and Best Practices

### Status Code Usage Best Practices

1. **Always transition through intermediate states:** Never jump directly from `PENDING` to a terminal state — always use `IN_PROGRESS` as the bridge.

2. **Set timestamps accurately:** Use `time.time()` at exact moments for `started_at` and `completed_at` to ensure accurate `duration_ms` calculations.

3. **Use descriptive error messages:** When setting `FAILED` status, provide actionable error context in the `error` field.

4. **Distinguish skip from failure:** Use `SKIPPED` for conditional non-execution (not a failure) and `FAILED` only for errors.

5. **Include partial output in failed steps:** Even when a step fails, include whatever data was gathered to aid debugging.

6. **Check status before using output:** Verify a step reached `COMPLETED` status before accessing its output in subsequent steps.

### Flow Diagram Usage Guidelines

1. **Use sequential execution** for workflows with dependencies between steps where later steps need output from earlier steps.

2. **Use parallel execution** for independent operations (monitoring, status checks) to reduce total execution time.

3. **Use hybrid execution** to combine parallel independent checks with sequential dependent operations for optimal performance.

4. **Implement fail-fast** for critical workflows where all steps must succeed.

5. **Implement continue-on-error** for monitoring and diagnostic workflows where complete visibility is more important than immediate failure.

### Error Handling Best Practices

1. **Classify errors appropriately** as transient, permanent, or validation errors to determine retry strategy.

2. **Use exponential backoff** for retry logic to avoid overwhelming services.

3. **Aggregate errors** from multiple steps to provide comprehensive diagnostic information.

4. **Provide clear error messages** that indicate what went wrong and potential remediation steps.

5. **Use status codes consistently** to represent the true state of step execution.

These execution flow diagrams and status code references provide a comprehensive foundation for understanding and working with the Action Execution Model in aide-de-camp.