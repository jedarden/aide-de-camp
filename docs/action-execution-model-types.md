# Action Execution Model - Type Definitions and Usage Guide

## Overview

The Action Execution Model is a comprehensive type system for defining and executing action workflows in the aide-de-camp system. This document provides complete type definitions, comprehensive examples, usage patterns, and best practices for all core types.

## Type System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Action Execution Model                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────┐         ┌─────────────────────────────┐ │
│  │     Step       │         │      ExecutionContext       │ │
│  │  (Base Model)  │         │  (Runtime Context)          │ │
│  └────────┬───────┘         └───────────┬─────────────────┘ │
│           │                            │                     │
│           │      ┌─────────────────────┴─────────────────┐  │
│           │      │                                       │  │
│           │      ▼                                       │  │
│           │  ┌───────────────────────────────────────┐ │  │
│           │  │        StepExecutor.execute()          │ │  │
│           │  │         (uses ExecutionContext)         │ │  │
│           │  └───────────────┬───────────────────────┘ │  │
│           │                  │                          │  │
│           │                  ▼                          │  │
│           │      ┌───────────────────────┐             │  │
│           │      │     StepResult        │             │  │
│           │      │  + StepStatus (Enum)  │             │  │
│           │      └───────────┬───────────┘             │  │
│           │                  │                          │  │
│           │                  │ collected into           │  │
│           │                  ▼                          │  │
│           │      ┌───────────────────────┐             │  │
│           └─────▶│     ActionResult       │◄────────────┘  │
│                   │  (Workflow Result)   │                │
│                   └───────────────────────┘                │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Complete Type Definitions

### 1. StepStatus Enum

**Purpose:** Enumeration defining all possible states of a workflow step execution.

```python
from enum import Enum

class StepStatus(str, Enum):
    """Status of a workflow step execution."""
    PENDING = "pending"          # Step created but not started
    IN_PROGRESS = "in_progress"   # Step actively executing
    COMPLETED = "completed"       # Step finished successfully
    FAILED = "failed"            # Step encountered an error
    SKIPPED = "skipped"           # Step not executed (conditional)
```

**Type Characteristics:**
- **Base Type:** String enumeration (inherits from `str` and `Enum`)
- **Serialization:** JSON-serializable (values are strings)
- **Module:** `src.action.models`
- **Usage:** Status field in `StepResult`, workflow state machines

**State Machine:**
```text
PENDING → IN_PROGRESS → COMPLETED
                 ↘        FAILED
                  ↘        SKIPPED
```

### 2. ExecutionContext Model

**Purpose:** Carries project configuration and runtime state through step execution pipeline.

```python
from typing import Any, Optional
from pydantic import BaseModel, Field

class ExecutionContext(BaseModel):
    """
    Context passed to all step executors.
    
    Contains project configuration and runtime context needed for step execution:
    - Project identification (slug, repo path)
    - Cluster configuration (cluster name, namespace)
    - Tracking identifiers (intent_id, session_id)
    - Execution flags (dry_run)
    """
    # Required tracking fields
    intent_id: str = Field(..., description="Intent ID for tracking and SSE targeting")
    session_id: str = Field(..., description="Session ID for SSE targeting")
    
    # Optional project context
    project_slug: Optional[str] = Field(None, description="Project slug for registry lookup")
    project_cfg: dict[str, Any] = Field(default_factory=dict, description="Project configuration from registry")
    
    # Execution control
    dry_run: bool = Field(default=False, description="If True, skip mutating operations")
    
    # Convenience properties (extracted from project_cfg)
    @property
    def cluster(self) -> Optional[str]:
        """Get cluster name from project configuration."""
        return self.project_cfg.get("cluster")
    
    @property
    def namespace(self) -> Optional[str]:
        """Get namespace from project configuration."""
        return self.project_cfg.get("namespace")
    
    @property
    def repo_path(self) -> Optional[str]:
        """Get repository path from project configuration."""
        return self.project_cfg.get("repo_path")
    
    @property
    def argocd_app(self) -> Optional[str]:
        """Get ArgoCD application name from project configuration."""
        return self.project_cfg.get("argocd_app")
```

**Type Characteristics:**
- **Base Type:** Pydantic `BaseModel`
- **Required Fields:** `intent_id`, `session_id`
- **Optional Fields:** `project_slug`, `project_cfg`, `dry_run`
- **Thread-Safety:** Immutable by default, safe for concurrent reads
- **Lifecycle:** Created at workflow start, discarded after completion

### 3. StepResult Model

**Purpose:** Represents the outcome of a single workflow step execution.

```python
class StepResult(BaseModel):
    """
    Result of a single workflow step execution.
    
    Contains the outcome of a step execution including status, output,
    error information, and timing metrics.
    """
    # Required identification and timing
    step_name: str = Field(..., description="Name of the step that was executed")
    status: StepStatus = Field(..., description="Execution status")
    started_at: float = Field(..., description="Unix timestamp when step started")
    
    # Optional execution details
    output: dict[str, Any] = Field(default_factory=dict, description="Step output data")
    error: Optional[str] = Field(None, description="Error message if step failed")
    completed_at: Optional[float] = Field(None, description="Unix timestamp when step completed")
    duration_ms: float = Field(default=0.0, description="Step execution duration in milliseconds")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for SSE broadcasting."""
        return {
            "step_name": self.step_name,
            "status": self.status.value,  # Converts enum to string
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }
```

**Type Characteristics:**
- **Base Type:** Pydantic `BaseModel`
- **Required Fields:** `step_name`, `status`, `started_at`
- **Optional Fields:** `output`, `error`, `completed_at`, `duration_ms`
- **Serialization:** `to_dict()` method converts enum values for JSON
- **Usage:** Collected into `ActionResult.steps` list

### 4. ActionResult Model

**Purpose:** Represents the complete execution result of an action workflow.

```python
class ActionResult(BaseModel):
    """
    Result of an action workflow execution.
    
    Contains the complete execution result for a workflow including all
    step results, timing information, and final status.
    """
    # Required identification and timing
    intent_id: str = Field(..., description="Intent ID for tracking")
    session_id: str = Field(..., description="Session ID for SSE targeting")
    workflow_name: str = Field(..., description="Name of the workflow that was executed")
    status: str = Field(..., description="Final workflow status: running, completed, failed, cancelled")
    started_at: float = Field(..., description="Unix timestamp when workflow started")
    
    # Optional workflow details
    project_slug: Optional[str] = Field(None, description="Project slug that was executed")
    steps: list[StepResult] = Field(default_factory=list, description="All step results in execution order")
    completed_at: Optional[float] = Field(None, description="Unix timestamp when workflow completed")
    duration_ms: float = Field(default=0.0, description="Workflow execution duration in milliseconds")
    error: Optional[str] = Field(None, description="Error message if workflow failed")
    
    def add_step(self, step: StepResult) -> None:
        """Add a step result to the action result."""
        self.steps.append(step)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for SSE broadcasting."""
        return {
            "intent_id": self.intent_id,
            "session_id": self.session_id,
            "project_slug": self.project_slug,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "steps": [step.to_dict() for step in self.steps],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }
```

**Type Characteristics:**
- **Base Type:** Pydantic `BaseModel`
- **Required Fields:** `intent_id`, `session_id`, `workflow_name`, `status`, `started_at`
- **Optional Fields:** `project_slug`, `steps`, `completed_at`, `duration_ms`, `error`
- **Aggregation:** Contains `list[StepResult]` of all executed steps
- **Serialization:** `to_dict()` recursively converts all steps for JSON

### 5. Step Base Model

**Purpose:** Base class for all workflow step definitions.

```python
from pydantic import ConfigDict

class Step(BaseModel):
    """
    Base class for all workflow step types.
    
    A step represents a single unit of work in an action workflow.
    Concrete step types (e.g., CiStatusStep, GitOpsCommitStep) inherit
    from this base and implement execution logic.
    
    Step vocabulary:
    - ci_status: Check CI/workflow status (gates workflow if not green)
    - image_tag: Resolve image tag/digest from CI
    - gitops_commit: Templated declarative-config edit
    - argocd_sync_status: Poll ArgoCD until Synced/Healthy
    - pod_status: Post-sync pod verification
    
    Read-only steps (no mutation):
    - deployment_info: Get deployment/statefulset information
    - git_log: Get recent git history
    - argocd_apps: Get ArgoCD application status
    - open_beads: Get open beads for project
    """
    step_type: str = Field(..., description="Type of step (e.g., 'ci_status', 'gitops_commit')")
    description: Optional[str] = Field(None, description="Human-readable step description")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional step metadata")
    
    model_config = ConfigDict(use_enum_values=True)
```

**Type Characteristics:**
- **Base Type:** Pydantic `BaseModel`
- **Required Fields:** `step_type`
- **Optional Fields:** `description`, `metadata`
- **Extensibility:** Intended to be subclassed for concrete step types
- **Configuration:** `use_enum_values=True` ensures enum values serialize as strings

## Practical Single-Step Usage Examples

### Example 1: Direct Step Function Execution

```python
from src.action.steps import execute_ci_status_step, execute_pod_status_step

# Execute CI status check directly
ci_result = await execute_ci_status_step(
    intent_id="intent-abc123",
    session_id="session-def456",
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "iad-ci",
        "namespace": "production",
    },
)

# Handle the dict result directly
if ci_result.get("status") == "success":
    print(f"CI passed: {ci_result['workflow_name']}")
elif ci_result.get("status") == "skipped":
    print(f"CI check skipped: {ci_result['reason']}")
else:
    print(f"CI failed: {ci_result.get('phase', 'Unknown')}")

# Execute pod status check
pod_result = await execute_pod_status_step(
    intent_id="intent-abc123",
    session_id="session-def456", 
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "apexalgo-iad",
        "namespace": "production",
    },
)

# Check pod health
running = pod_result.get("running", 0)
total = pod_result.get("total_pods", 0)
print(f"Pods: {running}/{total} running")
```

### Example 2: Step Class Usage

```python
from src.action.steps.read import CIStatusStep, PodStatusStep

# Create and execute CI status step
ci_step = CIStatusStep(
    kubectl_config="/home/coding/.kube/iad-ci.kubeconfig",
    timeout=15,
)

ci_result = await ci_step.execute(project_slug="mta-my-way")

# Handle dataclass result
if ci_result.success:
    print(f"CI Status: {ci_result.data.get('status')}")
    print(f"Workflow: {ci_result.data.get('workflow_name')}")
else:
    print(f"CI check failed: {ci_result.error}")

# Create and execute pod status step
pod_step = PodStatusStep(
    proxy_url=None,  # Auto-detect from cluster config
    timeout=10.0,
)

pod_result = await pod_step.execute(
    namespace="production",
    cluster="apexalgo-iad",
)

# Check pod phases
if pod_result.success:
    total_pods = pod_result.data.get("total_pods", 0)
    phase_counts = pod_result.data.get("phase_counts", {})
    print(f"Total pods: {total_pods}")
    print(f"Phase distribution: {phase_counts}")
else:
    print(f"Pod status check failed: {pod_result.error}")
```

### Example 3: Sequential Step Execution

```python
from src.action.steps import (
    execute_ci_status_step,
    execute_pod_status_step,
    execute_git_log_step,
)

async def diagnostic_check(project_slug: str, project_cfg: dict):
    """Execute diagnostic checks sequentially."""
    
    results = {}
    
    # Step 1: Check CI status
    try:
        ci_result = await execute_ci_status_step(
            intent_id="diagnostic-1",
            session_id="session-123",
            project_slug=project_slug,
            project_cfg=project_cfg,
        )
        results["ci_status"] = ci_result
        print(f"✓ CI status: {ci_result.get('status')}")
    except Exception as e:
        print(f"✗ CI check failed: {e}")
        results["ci_status"] = {"error": str(e)}
    
    # Step 2: Check pod status
    try:
        pod_result = await execute_pod_status_step(
            intent_id="diagnostic-1",
            session_id="session-123",
            project_slug=project_slug,
            project_cfg=project_cfg,
        )
        results["pod_status"] = pod_result
        print(f"✓ Pod status: {pod_result.get('running')}/{pod_result.get('total_pods')} running")
    except Exception as e:
        print(f"✗ Pod check failed: {e}")
        results["pod_status"] = {"error": str(e)}
    
    # Step 3: Get git history
    try:
        git_result = await execute_git_log_step(
            intent_id="diagnostic-1",
            session_id="session-123",
            project_slug=project_slug,
            project_cfg=project_cfg,
        )
        results["git_log"] = git_result
        print(f"✓ Recent commits: {git_result.get('count', 0)}")
    except Exception as e:
        print(f"✗ Git log failed: {e}")
        results["git_log"] = {"error": str(e)}
    
    return results

# Usage
results = await diagnostic_check(
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "apexalgo-iad",
        "namespace": "production",
        "repo_path": "/home/coding/mta-my-way",
    }
)
```

### Example 4: Parallel Step Execution

```python
import asyncio
from src.action.steps import (
    execute_deployment_info_step,
    execute_pod_status_step,
    execute_argocd_apps_step,
)

async def parallel_cluster_check(project_slug: str, project_cfg: dict):
    """Execute independent cluster checks in parallel."""
    
    # Create parallel tasks
    tasks = [
        execute_deployment_info_step(
            intent_id="parallel-1",
            session_id="session-123",
            project_slug=project_slug,
            project_cfg=project_cfg,
        ),
        execute_pod_status_step(
            intent_id="parallel-1",
            session_id="session-123",
            project_slug=project_slug,
            project_cfg=project_cfg,
        ),
        execute_argocd_apps_step(
            intent_id="parallel-1",
            session_id="session-123",
            project_slug=project_slug,
            project_cfg=project_cfg,
        ),
    ]
    
    # Execute all tasks in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    deployment_info, pod_info, argocd_info = results
    
    print(f"Deployments: {len(deployment_info.get('deployments', []))}")
    print(f"Pods: {pod_info.get('running', 0)}/{pod_info.get('total_pods', 0)} running")
    print(f"ArgoCD Apps: {len(argocd_info.get('applications', []))}")
    
    return {
        "deployment_info": deployment_info,
        "pod_status": pod_info,
        "argocd_apps": argocd_info,
    }

# Usage
cluster_status = await parallel_cluster_check(
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "apexalgo-iad",
        "namespace": "production",
    }
)
```

## Comprehensive Usage Examples

### Example 5: Complete Workflow Execution

```python
import time
from src.action.models import (
    ExecutionContext, ActionResult, StepResult, StepStatus
)

# 1. Create execution context
ctx = ExecutionContext(
    intent_id="intent-abc123",
    session_id="session-def456",
    project_slug="mta-my-way",
    project_cfg={
        "cluster": "apexalgo-iad",
        "namespace": "production",
        "repo_path": "/home/coding/mta-my-way",
        "argocd_app": "mta-my-way-prod",
    },
    dry_run=False,
)

# 2. Create workflow result container
start_time = time.time()
workflow_result = ActionResult(
    intent_id=ctx.intent_id,
    session_id=ctx.session_id,
    project_slug=ctx.project_slug,
    workflow_name="deploy_application",
    status="running",
    started_at=start_time,
)

# 3. Execute Step 1: CI Status Check
step1_start = time.time()
try:
    ci_data = await check_ci_status(ctx.project_slug)
    step1 = StepResult(
        step_name="ci_status",
        status=StepStatus.COMPLETED,
        output=ci_data,
        started_at=step1_start,
        completed_at=time.time(),
        duration_ms=(time.time() - step1_start) * 1000,
    )
except Exception as e:
    step1 = StepResult(
        step_name="ci_status",
        status=StepStatus.FAILED,
        output={"cluster": ctx.cluster},
        error=str(e),
        started_at=step1_start,
        completed_at=time.time(),
        duration_ms=(time.time() - step1_start) * 1000,
    )

workflow_result.add_step(step1)

# 4. Check if workflow should continue (fail-fast pattern)
if step1.status == StepStatus.COMPLETED:
    # Step 2: Image Tag Resolution
    step2_start = time.time()
    step2 = StepResult(
        step_name="image_tag",
        status=StepStatus.COMPLETED,
        output={"tag": "v1.2.3", "registry_path": "ronaldraygun/mta-my-way:v1.2.3"},
        started_at=step2_start,
        completed_at=time.time(),
        duration_ms=500.0,
    )
    workflow_result.add_step(step2)
    
    # Step 3: GitOps Commit (respects dry_run)
    step3_start = time.time()
    if ctx.dry_run:
        step3 = StepResult(
            step_name="gitops_commit",
            status=StepStatus.SKIPPED,
            output={"reason": "dry_run enabled"},
            started_at=step3_start,
            completed_at=time.time(),
            duration_ms=10.0,
        )
    else:
        step3 = StepResult(
            step_name="gitops_commit",
            status=StepStatus.COMPLETED,
            output={"commit_sha": "abc123def456"},
            started_at=step3_start,
            completed_at=time.time(),
            duration_ms=2000.0,
        )
    workflow_result.add_step(step3)
    
    workflow_result.status = "completed"
else:
    # CI check failed, workflow terminates
    workflow_result.status = "failed"
    workflow_result.error = f"CI status check failed: {step1.error}"

# 5. Finalize workflow result
workflow_result.completed_at = time.time()
workflow_result.duration_ms = (workflow_result.completed_at - workflow_result.started_at) * 1000

# 6. Broadcast to canvas via SSE
broadcaster = get_broadcaster()
await broadcaster.broadcast(
    SSEEvent(
        event_type="workflow_completed",
        target_session_id=ctx.session_id,
        data=workflow_result.to_dict(),
    )
)
```

### Example 6: Types Working Together - Error Handling

```python
from src.action.models import ExecutionContext, StepResult, StepStatus

async def execute_deployment_workflow(ctx: ExecutionContext) -> ActionResult:
    """Execute deployment workflow with comprehensive error handling."""
    
    start_time = time.time()
    workflow_result = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="deploy",
        status="running",
        started_at=start_time,
    )
    
    # Step 1: Check deployment exists
    check_result = await execute_deployment_exists_step(ctx)
    workflow_result.add_step(check_result)
    
    # Handle different terminal states
    if check_result.status == StepStatus.FAILED:
        # Check failed - can't proceed
        workflow_result.status = "failed"
        workflow_result.error = check_result.error
        return finalize_workflow(workflow_result)
    
    if check_result.status == StepStatus.SKIPPED:
        # Check was skipped - use default behavior
        deployment_exists = False
    else:
        # Check completed successfully
        deployment_exists = check_result.output.get("exists", False)
    
    # Step 2: Conditional execution based on step 1 result
    if deployment_exists:
        # Update existing deployment
        update_result = await execute_update_deployment_step(ctx)
    else:
        # Create new deployment
        update_result = await execute_create_deployment_step(ctx)
    
    workflow_result.add_step(update_result)
    
    # Step 3: Verify deployment
    if update_result.status == StepStatus.COMPLETED:
        verify_result = await execute_verify_pods_step(ctx)
        workflow_result.add_step(verify_result)
        
        if verify_result.status == StepStatus.COMPLETED:
            workflow_result.status = "completed"
        else:
            workflow_result.status = "partial_failure"
            workflow_result.error = "Deployment updated but verification failed"
    else:
        workflow_result.status = "failed"
        workflow_result.error = update_result.error
    
    return finalize_workflow(workflow_result)

def finalize_workflow(workflow: ActionResult) -> ActionResult:
    """Finalize workflow result with timing."""
    workflow.completed_at = time.time()
    workflow.duration_ms = (workflow.completed_at - workflow.started_at) * 1000
    return workflow
```

### Example 7: Creating and Manipulating Instances

```python
import time
from src.action.models import ExecutionContext, StepResult, StepStatus, ActionResult

# Creating ExecutionContext instances
minimal_context = ExecutionContext(
    intent_id="intent-123",
    session_id="session-456",
)

full_context = ExecutionContext(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="spaxel",
    project_cfg={
        "cluster": "iad-ci",
        "namespace": "argo-workflows",
        "repo_path": "/home/coding/spaxel",
        "argocd_app": "spaxel-ci",
    },
    dry_run=True,
)

# Accessing context properties
cluster = full_context.cluster  # "iad-ci"
namespace = full_context.namespace  # "argo-workflows"
repo_path = full_context.repo_path  # "/home/coding/spaxel"

# Creating StepResult instances
success_result = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={"workflow_name": "spaxel-build-123", "status": "Succeeded"},
    started_at=time.time(),
    completed_at=time.time() + 1.5,
    duration_ms=1500.0,
)

failure_result = StepResult(
    step_name="pod_status",
    status=StepStatus.FAILED,
    output={"namespace": "production"},
    error="Timeout querying pod status",
    started_at=time.time(),
    completed_at=time.time() + 10.0,
    duration_ms=10000.0,
)

skipped_result = StepResult(
    step_name="gitops_commit",
    status=StepStatus.SKIPPED,
    output={"reason": "dry_run enabled"},
    started_at=time.time(),
    completed_at=time.time(),
    duration_ms=50.0,
)

# Creating ActionResult and adding steps
workflow = ActionResult(
    intent_id="intent-123",
    session_id="session-456",
    workflow_name="deploy",
    status="running",
    started_at=time.time(),
)

# Add steps using the add_step method
workflow.add_step(success_result)
workflow.add_step(failure_result)
workflow.add_step(skipped_result)

# Access step results
for step in workflow.steps:
    print(f"{step.step_name}: {step.status.value}")

# Converting to dict for SSE/JSON
workflow_dict = workflow.to_dict()
step_dict = success_result.to_dict()

# Creating Step instances
step_definition = Step(
    step_type="ci_status",
    description="Check CI workflow status",
    metadata={"timeout": 30, "retry_count": 3},
)
```

### Example 8: Serialization and SSE Broadcasting

```python
import json
from src.action.models import ActionResult, StepResult, StepStatus
from src.sse import get_broadcaster, SSEEvent

# Create step result
step = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={"workflow_name": "build-123"},
    started_at=1722987245.123,
    completed_at=1722987246.456,
    duration_ms=1333.0,
)

# Convert to dictionary for JSON serialization
step_dict = step.to_dict()
json_string = json.dumps(step_dict)
# '{"step_name": "ci_status", "status": "completed", ...}'

# Create workflow result
workflow = ActionResult(
    intent_id="intent-abc",
    session_id="session-123",
    workflow_name="deploy",
    status="completed",
    steps=[step],
    started_at=1722987245.0,
    completed_at=1722987250.0,
    duration_ms=5000.0,
)

# Broadcast via SSE
broadcaster = get_broadcaster()
await broadcaster.broadcast(
    SSEEvent(
        event_type="workflow_completed",
        target_session_id=workflow.session_id,
        data=workflow.to_dict(),
    )
)

# Broadcast individual step completion
await broadcaster.broadcast(
    SSEEvent(
        event_type="step_completed",
        target_session_id=workflow.session_id,
        data=step.to_dict(),
    )
)
```

### Example 9: Type Safety and Validation

```python
from src.action.models import ExecutionContext, StepResult, StepStatus
from pydantic import ValidationError

# Type validation - correct usage
try:
    valid_context = ExecutionContext(
        intent_id="intent-123",
        session_id="session-456",
        project_slug="spaxel",
    )
    print("✓ Valid context created")
except ValidationError as e:
    print(f"✗ Validation failed: {e}")

# Type validation - missing required fields
try:
    invalid_context = ExecutionContext(
        intent_id="intent-123",
        # session_id is required but missing
    )
    print("✗ Should have failed validation")
except ValidationError as e:
    print(f"✓ Correctly rejected invalid context: {e}")

# Type-safe status checking
result = StepResult(
    step_name="test",
    status=StepStatus.COMPLETED,
    started_at=time.time(),
)

# Type-safe comparison (works with enum)
if result.status == StepStatus.COMPLETED:
    print("✓ Step completed successfully")

# Type-safe comparison (works with string value)
if result.status == "completed":
    print("✓ Step completed successfully")

# Creating result with all optional fields
full_result = StepResult(
    step_name="comprehensive_step",
    status=StepStatus.COMPLETED,
    output={"key": "value", "nested": {"data": 123}},
    error=None,
    started_at=time.time(),
    completed_at=time.time() + 2.5,
    duration_ms=2500.0,
)

# Pydantic provides automatic type conversion
result_from_dict = StepResult(**{
    "step_name": "from_dict",
    "status": "completed",  # String converted to StepStatus enum
    "started_at": 1722987245.0,
})
```

## Usage Patterns

### Pattern 1: Fail-Fast Workflow Execution

```python
async def execute_fail_fast_workflow(ctx: ExecutionContext) -> ActionResult:
    """Execute workflow that stops immediately on any failure."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="critical_deploy",
        status="running",
        started_at=time.time(),
    )
    
    steps_to_execute = [
        ("ci_status", execute_ci_status_step),
        ("image_tag", execute_image_tag_step),
        ("gitops_commit", execute_gitops_commit_step),
        ("argocd_sync", execute_argocd_sync_step),
    ]
    
    for step_name, step_executor in steps_to_execute:
        result = await step_executor(ctx)
        workflow.add_step(result)
        
        # Fail-fast: stop on first failure
        if result.status == StepStatus.FAILED:
            workflow.status = "failed"
            workflow.error = f"Critical step {step_name} failed"
            break
        
        # Broadcast progress after each step
        await broadcast_step_completion(ctx.session_id, result)
    
    # Finalize workflow
    if workflow.status == "running":
        workflow.status = "completed"
    
    workflow.completed_at = time.time()
    workflow.duration_ms = (workflow.completed_at - workflow.started_at) * 1000
    return workflow
```

### Pattern 2: Continue-On-Error Workflow Execution

```python
async def execute_continue_on_error_workflow(ctx: ExecutionContext) -> ActionResult:
    """Execute workflow that continues through non-critical failures."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="diagnostic_check",
        status="running",
        started_at=time.time(),
    )
    
    diagnostic_steps = [
        ("pod_status", execute_pod_status_step),
        ("deployment_info", execute_deployment_info_step),
        ("service_status", execute_service_status_step),
        ("configmap_status", execute_configmap_status_step),
    ]
    
    failed_steps = []
    
    for step_name, step_executor in diagnostic_steps:
        try:
            result = await step_executor(ctx)
            workflow.add_step(result)
            
            if result.status == StepStatus.FAILED:
                failed_steps.append(step_name)
                
        except Exception as e:
            # Catch unexpected errors and continue
            error_result = StepResult(
                step_name=step_name,
                status=StepStatus.FAILED,
                error=f"Unexpected error: {str(e)}",
                started_at=time.time(),
                completed_at=time.time(),
                duration_ms=0.0,
            )
            workflow.add_step(error_result)
            failed_steps.append(step_name)
    
    # Determine final status based on collected results
    if not failed_steps:
        workflow.status = "completed"
    elif len(failed_steps) < len(diagnostic_steps):
        workflow.status = "partial_failure"
        workflow.error = f"Some diagnostic steps failed: {', '.join(failed_steps)}"
    else:
        workflow.status = "failed"
        workflow.error = "All diagnostic steps failed"
    
    workflow.completed_at = time.time()
    workflow.duration_ms = (workflow.completed_at - workflow.started_at) * 1000
    return workflow
```

### Pattern 3: Conditional Workflow Execution

```python
async def execute_conditional_workflow(ctx: ExecutionContext) -> ActionResult:
    """Execute workflow with conditional step execution."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="smart_deploy",
        status="running",
        started_at=time.time(),
    )
    
    # Step 1: Check current state
    state_check = await execute_deployment_state_step(ctx)
    workflow.add_step(state_check)
    
    if state_check.status != StepStatus.COMPLETED:
        workflow.status = "failed"
        workflow.error = "Could not determine deployment state"
        return finalize_workflow(workflow)
    
    deployment_state = state_check.output.get("state")
    
    # Step 2: Conditional execution based on state
    if deployment_state == "not_deployed":
        # Fresh deployment path
        create_result = await execute_create_deployment_step(ctx)
        workflow.add_step(create_result)
        
    elif deployment_state == "deployed":
        # Update deployment path
        update_result = await execute_update_deployment_step(ctx)
        workflow.add_step(update_result)
        
    elif deployment_state == "error":
        # Recovery path
        recover_result = await execute_recovery_step(ctx)
        workflow.add_step(recover_result)
        
    else:
        # Unknown state - skip deployment
        skip_result = StepResult(
            step_name="deployment",
            status=StepStatus.SKIPPED,
            output={"reason": f"Unknown deployment state: {deployment_state}"},
            started_at=time.time(),
            completed_at=time.time(),
            duration_ms=0.0,
        )
        workflow.add_step(skip_result)
    
    # Step 3: Verification (only if deployment executed)
    last_step = workflow.steps[-1]
    if last_step.status == StepStatus.COMPLETED:
        verify_result = await execute_verification_step(ctx)
        workflow.add_step(verify_result)
        
        workflow.status = "completed" if verify_result.status == StepStatus.COMPLETED else "partial_failure"
    else:
        workflow.status = "failed"
        workflow.error = last_step.error
    
    return finalize_workflow(workflow)
```

### Pattern 4: Dry Run Execution Pattern

```python
async def execute_with_dry_run_support(ctx: ExecutionContext) -> ActionResult:
    """Execute workflow with dry-run support for mutating operations."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="safe_deploy",
        status="running",
        started_at=time.time(),
    )
    
    # Read-only steps always execute
    read_only_steps = [
        ("ci_status", execute_ci_status_step),
        ("current_image", execute_current_image_step),
    ]
    
    for step_name, executor in read_only_steps:
        result = await executor(ctx)
        workflow.add_step(result)
        
        if result.status == StepStatus.FAILED:
            workflow.status = "failed"
            workflow.error = f"Read-only step {step_name} failed"
            return finalize_workflow(workflow)
    
    # Mutating steps respect dry_run flag
    mutating_steps = [
        ("update_image_tag", execute_update_image_tag_step),
        ("gitops_commit", execute_gitops_commit_step),
        ("argocd_sync", execute_argocd_sync_step),
    ]
    
    for step_name, executor in mutating_steps:
        if ctx.dry_run:
            # Create synthetic SKIPPED result for dry run
            result = StepResult(
                step_name=step_name,
                status=StepStatus.SKIPPED,
                output={
                    "reason": "dry_run enabled",
                    "would_execute": True,
                },
                started_at=time.time(),
                completed_at=time.time(),
                duration_ms=1.0,
            )
        else:
            # Execute the actual mutating step
            result = await executor(ctx)
        
        workflow.add_step(result)
        
        # In dry run mode, we don't fail on skipped steps
        if not ctx.dry_run and result.status == StepStatus.FAILED:
            workflow.status = "failed"
            workflow.error = f"Mutating step {step_name} failed"
            return finalize_workflow(workflow)
    
    workflow.status = "completed"
    if ctx.dry_run:
        # Add dry run indicator to workflow output
        workflow.status = "dry_run"
    
    return finalize_workflow(workflow)
```

### Pattern 5: Parallel Step Execution with Result Collection

```python
import asyncio
from typing import list

async def execute_parallel_workflow(ctx: ExecutionContext) -> ActionResult:
    """Execute independent steps in parallel and collect results."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="parallel_diagnostics",
        status="running",
        started_at=time.time(),
    )
    
    # Define independent steps that can run in parallel
    parallel_tasks = [
        execute_pod_status_step(ctx),
        execute_service_status_step(ctx),
        execute_configmap_status_step(ctx),
        execute_secret_status_step(ctx),
        execute_ingress_status_step(ctx),
    ]
    
    # Execute all steps in parallel
    results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
    
    # Process results, handling both StepResult and Exception
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # Convert exception to failed StepResult
            error_result = StepResult(
                step_name=f"parallel_step_{i}",
                status=StepStatus.FAILED,
                error=f"Task raised exception: {str(result)}",
                started_at=time.time(),
                completed_at=time.time(),
                duration_ms=0.0,
            )
            workflow.add_step(error_result)
        else:
            workflow.add_step(result)
    
    # Analyze collective results
    failed_count = sum(1 for s in workflow.steps if s.status == StepStatus.FAILED)
    completed_count = sum(1 for s in workflow.steps if s.status == StepStatus.COMPLETED)
    
    if failed_count == 0:
        workflow.status = "completed"
    elif completed_count > 0:
        workflow.status = "partial_failure"
        workflow.error = f"{failed_count} of {len(workflow.steps)} parallel steps failed"
    else:
        workflow.status = "failed"
        workflow.error = "All parallel steps failed"
    
    return finalize_workflow(workflow)
```

### Pattern 6: Retry Pattern with StepResult

```python
async def execute_with_retry(
    ctx: ExecutionContext,
    step_name: str,
    executor: callable,
    max_retries: int = 3,
    retry_delay_ms: float = 1000.0,
) -> StepResult:
    """Execute a step with retry logic."""
    
    last_result = None
    
    for attempt in range(max_retries):
        step_start = time.time()
        
        try:
            result_data = await executor(ctx)
            
            return StepResult(
                step_name=step_name,
                status=StepStatus.COMPLETED,
                output=result_data,
                started_at=step_start,
                completed_at=time.time(),
                duration_ms=(time.time() - step_start) * 1000,
                metadata={"attempts": attempt + 1},
            )
            
        except Exception as e:
            last_result = StepResult(
                step_name=step_name,
                status=StepStatus.FAILED,
                error=f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}",
                started_at=step_start,
                completed_at=time.time(),
                duration_ms=(time.time() - step_start) * 1000,
                metadata={"attempts": attempt + 1},
            )
            
            if attempt < max_retries - 1:
                # Wait before retry
                await asyncio.sleep(retry_delay_ms / 1000.0)
    
    # All retries exhausted
    return last_result

# Usage in workflow
async def execute_resilient_workflow(ctx: ExecutionContext) -> ActionResult:
    """Execute workflow with retry support for flaky steps."""
    
    workflow = ActionResult(
        intent_id=ctx.intent_id,
        session_id=ctx.session_id,
        workflow_name="resilient_deploy",
        status="running",
        started_at=time.time(),
    )
    
    # Step with retry
    ci_result = await execute_with_retry(
        ctx=ctx,
        step_name="ci_status",
        executor=execute_ci_status_step,
        max_retries=3,
        retry_delay_ms=2000.0,
    )
    workflow.add_step(ci_result)
    
    if ci_result.status == StepStatus.FAILED:
        workflow.status = "failed"
        workflow.error = f"CI check failed after {ci_result.metadata.get('attempts')} attempts"
        return finalize_workflow(workflow)
    
    # Continue with other steps...
    workflow.status = "completed"
    return finalize_workflow(workflow)
```

## Best Practices

### 1. Context Management

**DO:**
- Always validate required context fields before use
- Use convenience properties (`ctx.cluster`, `ctx.namespace`) instead of direct dict access
- Create context at workflow entry point and pass unchanged to all steps
- Use tracking IDs (`intent_id`, `session_id`) for log correlation

**DON'T:**
- Don't modify context after creation (use `model_copy()` if needed)
- Don't store mutable state in context that changes during execution
- Don't bypass validation by accessing `project_cfg` directly

### 2. Result Creation and Timing

**DO:**
- Always capture `started_at` timestamp immediately before step execution
- Calculate `duration_ms` accurately: `(completed_at - started_at) * 1000`
- Set both `started_at` and `completed_at` for completed steps
- Include partial output data in failed steps for debugging

**DON'T:**
- Don't use hardcoded durations (always measure actual execution time)
- Don't forget to set `completed_at` for terminal state steps
- Don't leave `error` field `None` for failed steps
- Don't create results without `started_at` timestamp

### 3. Status Handling

**DO:**
- Always transition through `IN_PROGRESS` (never jump from `PENDING` to terminal)
- Use `SKIPPED` for conditional non-execution (not failure)
- Check status before accessing output data in workflow logic
- Use descriptive error messages in failed results

**DON'T:**
- Don't use `SKIPPED` for failures (use `FAILED` instead)
- Don't transition from terminal states back to intermediate
- Don't ignore failed steps in fail-fast workflows
- Don't use generic error messages like "failed"

### 4. Workflow Aggregation

**DO:**
- Add every step result to workflow using `add_step()` method
- Broadcast step completions via SSE for real-time progress
- Set workflow status based on step results (not just last step)
- Finalize workflow with `completed_at` and `duration_ms`

**DON'T:**
- Don't forget to add steps to workflow before checking results
- Don't modify step results after adding them to workflow
- Don't leave workflow status as "running" after completion
- Don't create workflows without `started_at` timestamp

### 5. Serialization and SSE

**DO:**
- Use `to_dict()` method before JSON serialization (converts enums to strings)
- Broadcast individual step completions for real-time feedback
- Broadcast final workflow completion with all steps included
- Include `target_session_id` in SSE events for proper routing

**DON'T:**
- Don't serialize Pydantic models directly (use `to_dict()` first)
- Don't forget to handle enum conversion for JSON
- Don't broadcast events without proper session targeting
- Don't send events without proper error handling

### 6. Error Handling and Recovery

**DO:**
- Convert all exceptions to `StepResult` with `FAILED` status
- Include exception details in `error` field
- Use continue-on-error pattern for non-critical diagnostic steps
- Implement retry logic for transient failures (network, timeouts)

**DON'T:**
- Don't let exceptions escape step executors unhandled
- Don't use bare `except:` clauses (catch specific exceptions)
- Don't implement retry for permanent errors (validation, auth)
- Don't retry indefinitely without max attempt limit

### 7. Type Safety and Validation

**DO:**
- Use Pydantic's automatic validation for type safety
- Create results with proper type annotations
- Validate required fields before using optional fields
- Use type checkers (mypy) with these models

**DON'T:**
- Don't bypass Pydantic validation by creating models with `**dict` expansion
- Don't ignore `ValidationError` exceptions during model creation
- Don't assume optional fields are present without checking
- Don't use string values where enums are expected

### 8. Performance and Concurrency

**DO:**
- Use parallel execution for independent steps
- Implement proper timeout handling for long-running steps
- Use async/await properly for I/O operations
- Profile step execution times to identify bottlenecks

**DON'T:**
- Don't run parallel steps that depend on each other's results
- Don't implement blocking operations in async step executors
- Don't create steps without timeout limits
- Don't ignore performance degradation over time

## Common Gotchas and Solutions

### ⚠️ CRITICAL: Missing EventType Constants

**Problem:** The executor code references `EventType.ACTION_*` constants that don't exist in the `EventType` class, causing runtime `AttributeError`.

```python
# ❌ BROKEN - These constants don't exist in EventType
EventType.ACTION_WORKFLOW_STARTED    # AttributeError
EventType.ACTION_STEP_STARTED        # AttributeError
EventType.ACTION_STEP_COMPLETED      # AttributeError
EventType.ACTION_WORKFLOW_COMPLETED  # AttributeError
EventType.ACTION_WORKFLOW_FAILED     # AttributeError
EventType.ACTION_WORKFLOW_CANCELLED  # AttributeError
```

**Impact:** Any attempt to execute workflows will fail with `AttributeError: type object 'EventType' has no attribute 'ACTION_WORKFLOW_STARTED'`.

**Solution:** Add the missing event type constants to `src/sse/broadcaster.py`:

```python
# Add to EventType class in src/sse/broadcaster.py
class EventType:
    # ... existing event types ...
    
    # Action workflow events (MISSING - need to be added)
    ACTION_WORKFLOW_STARTED = "action_workflow_started"
    ACTION_STEP_STARTED = "action_step_started"
    ACTION_STEP_COMPLETED = "action_step_completed"
    ACTION_WORKFLOW_COMPLETED = "action_workflow_completed"
    ACTION_WORKFLOW_FAILED = "action_workflow_failed"
    ACTION_WORKFLOW_CANCELLED = "action_workflow_cancelled"
```

**Status:** ✅ FIXED - All action workflow event types have been added to `src/sse/broadcaster.py` (2026-08-06). Workflows can now execute without `AttributeError`.

### ⚠️ CRITICAL: Dual StepResult Type System

**Problem:** There are TWO different `StepResult` types in the codebase that serve different purposes:

```python
# Type 1: Pydantic model in src/action/models.py (for workflow execution)
from src.action.models import StepResult, StepStatus
result1 = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,  # Uses StepStatus enum
    started_at=time.time(),
    completed_at=time.time(),
    duration_ms=1000.0,
)

# Type 2: Dataclass in src/action/steps/read.py (for individual steps)
from src.action.steps.read import StepResult
result2 = StepResult(
    success=True,  # Uses boolean success field
    data={"key": "value"},
    error=None,
)

# Type 3: Dict return from step functions in src/action/steps.py
result3 = await execute_ci_status_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={...},
)
# Returns: dict[str, Any] with direct data fields
```

**Impact:** Mixing these types causes type errors and field access confusion:

```python
# ❌ WRONG - Trying to use Pydantic methods on dict/StepResult dataclass
result.status  # AttributeError: dict has no 'status'
result.to_dict()  # AttributeError: dataclass has no 'to_dict'

# ❌ WRONG - Wrong field names for type
result.success  # Pydantic StepResult doesn't have 'success' field
result.status  # Dataclass StepResult doesn't have 'status' field
```

**Solution:** Use the correct type for each context:

```python
# ✅ CORRECT - For workflow execution results (Pydantic model)
from src.action.models import StepResult, StepStatus, ActionResult
workflow_result = ActionResult(...)
step_result = StepResult(
    step_name="ci_status",
    status=StepStatus.COMPLETED,
    output={"data": "..."},
    started_at=time.time(),
)
workflow_result.add_step(step_result)  # For workflow aggregation

# ✅ CORRECT - For direct step execution (dict returns)
from src.action.steps import execute_ci_status_step
ci_data = await execute_ci_status_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={...},
)
# ci_data is dict[str, Any], access directly: ci_data["status"], ci_data["workflow_name"]

# ✅ CORRECT - For step class instances (dataclass)
from src.action.steps.read import CIStatusStep
step = CIStatusStep()
result = await step.execute(project_slug="mta-my-way")
# result is StepResult dataclass, access: result.success, result.data
```

**Usage Guide:**
- **Workflow Execution**: Use `src.action.models.StepResult` (Pydantic) - for `ActionExecutor` and workflow aggregation
- **Step Functions**: Use `src.action.steps.execute_*_step()` functions - return `dict[str, Any]`
- **Step Classes**: Use `src.action.steps.read.*Step` classes - return dataclass `StepResult`

**Status:** ⚠️ BY DESIGN - The dual-type system is intentional: Pydantic models for workflow orchestration, dict returns for step functions, dataclass for step classes.

### Gotcha 1: Enum Serialization

**Problem:** `StepStatus` enum values aren't JSON-serializable by default.

```python
# ❌ WRONG
json.dumps(result)  # TypeError: Object of type StepStatus is not JSON serializable

# ✅ CORRECT
json.dumps(result.to_dict())  # to_dict() converts enum to string value
```

### Gotcha 2: Mutable project_cfg

**Problem:** `project_cfg` is a dict that can be modified, breaking immutability.

```python
# ❌ WRONG
ctx.project_cfg["cluster"] = "new-cluster"  # Breaks immutability

# ✅ CORRECT
new_ctx = ctx.model_copy(update={"project_cfg": {**ctx.project_cfg, "cluster": "new-cluster"}})
```

### Gotcha 3: Missing completed_at Timestamp

**Problem:** Terminal state steps without `completed_at` break timing calculations.

```python
# ❌ WRONG
failed_result = StepResult(
    step_name="step",
    status=StepStatus.FAILED,
    error="Failed",
    started_at=time.time(),
    # Missing completed_at
)

# ✅ CORRECT
failed_result = StepResult(
    step_name="step",
    status=StepStatus.FAILED,
    error="Failed",
    started_at=time.time(),
    completed_at=time.time(),  # Always set for terminal states
)
```

### Gotcha 4: Workflow Status Not Updated

**Problem:** Forgetting to update workflow status after collecting all steps.

```python
# ❌ WRONG
workflow.add_step(step1)
workflow.add_step(step2)
# Forgot to set workflow.status
return workflow  # Status still "running"

# ✅ CORRECT
workflow.add_step(step1)
workflow.add_step(step2)
workflow.status = "completed"  # Always update before returning
workflow.completed_at = time.time()
return workflow
```

### Gotcha 5: Dry Run Logic in Executors

**Problem:** Step executors don't respect `ctx.dry_run` flag.

```python
# ❌ WRONG
async def execute_gitops_commit_step(ctx: ExecutionContext) -> StepResult:
    # Always commits, ignoring dry_run
    subprocess.run(["git", "commit", "-am", "update"])
    return StepResult(...)

# ✅ CORRECT
async def execute_gitops_commit_step(ctx: ExecutionContext) -> StepResult:
    if ctx.dry_run:
        return StepResult(
            status=StepStatus.SKIPPED,
            output={"reason": "dry_run enabled"},
            ...
        )
    # Only commit when not in dry_run mode
    subprocess.run(["git", "commit", "-am", "update"])
    return StepResult(...)
```

### Gotcha 6: Exception Handling in Step Executors

**Problem:** Letting exceptions escape without creating failed StepResult.

```python
# ❌ WRONG
async def execute_step(ctx: ExecutionContext) -> StepResult:
    # If this raises, workflow breaks
    result = await risky_operation()
    return StepResult(status=StepStatus.COMPLETED, output=result, ...)

# ✅ CORRECT
async def execute_step(ctx: ExecutionContext) -> StepResult:
    started_at = time.time()
    try:
        result = await risky_operation()
        return StepResult(
            status=StepStatus.COMPLETED,
            output=result,
            started_at=started_at,
            completed_at=time.time(),
            ...
        )
    except Exception as e:
        return StepResult(
            status=StepStatus.FAILED,
            error=str(e),
            started_at=started_at,
            completed_at=time.time(),
            ...
        )
```

### Gotcha 7: Type Coercion in Status Comparison

**Problem:** Mixing enum and string comparisons leads to unexpected behavior.

```python
# ❌ CONFUSING (but works)
if result.status == "completed":  # String comparison
    print("Step completed")

# ✅ CLEAR (preferred)
if result.status == StepStatus.COMPLETED:  # Enum comparison
    print("Step completed")

# ❌ BREAKS (strict type checking)
if result.status == completed:  # Undefined variable
    print("Step completed")
```

### Gotcha 8: SSE Event Targeting

**Problem:** Broadcasting events without proper session targeting.

```python
# ❌ WRONG (broadcasts to all clients)
await broadcaster.broadcast(
    SSEEvent(
        event_type="step_completed",
        data=result.to_dict(),
        # Missing target_session_id
    )
)

# ✅ CORRECT (targets specific session)
await broadcaster.broadcast(
    SSEEvent(
        event_type="step_completed",
        target_session_id=ctx.session_id,  # Always include
        data=result.to_dict(),
    )
)
```

### Gotcha 9: Sequential vs Parallel Execution Mismatch

**Problem:** Documentation shows parallel execution examples, but the actual `ActionExecutor` only executes steps sequentially.

```python
# ❌ DOCUMENTATION MISMATCH - Pattern 5 shows parallel execution
# The documentation shows this pattern:
parallel_tasks = [
    execute_pod_status_step(ctx),
    execute_service_status_step(ctx),
    execute_configmap_status_step(ctx),
]
results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

# ✅ ACTUAL IMPLEMENTATION - Steps execute sequentially only
# The ActionExecutor.execute_workflow() method runs steps one at a time:
for i, step_name in enumerate(steps):
    step_result = await self._execute_step(...)  # Sequential, not parallel
    result.add_step(step_result)
```

**Impact:** If you design workflows assuming parallel execution, they will run sequentially, potentially taking longer than expected.

**Solution:** 
- For now, assume all steps in a workflow execute sequentially
- If parallel execution is needed, it must be implemented within individual step executors
- Future versions may add parallel step execution capabilities

**Status:** Documentation needs clarification that `ActionExecutor` currently supports sequential execution only. Parallel execution patterns shown are aspirational/design patterns, not current implementation behavior.

```python
# ❌ WRONG (broadcasts to all clients)
await broadcaster.broadcast(
    SSEEvent(
        event_type="step_completed",
        data=result.to_dict(),
        # Missing target_session_id
    )
)

# ✅ CORRECT (targets specific session)
await broadcaster.broadcast(
    SSEEvent(
        event_type="step_completed",
        target_session_id=ctx.session_id,  # Always include
        data=result.to_dict(),
    )
)
```

## Troubleshooting Guide

This section provides practical solutions for common issues encountered when using the Action Execution Model.

### Issue: AttributeError when executing workflows

**Symptoms:**
```
AttributeError: type object 'EventType' has no attribute 'ACTION_WORKFLOW_STARTED'
```

**Root Cause:** Missing event type constants in `src/sse/broadcaster.py`.

**Solution:** ✅ Already fixed in the current codebase. All action workflow event types are now defined in the `EventType` class.

**Verification:**
```python
from src.sse.broadcaster import EventType

# These should all work without AttributeError
assert EventType.ACTION_WORKFLOW_STARTED == "action_workflow_started"
assert EventType.ACTION_STEP_STARTED == "action_step_started"
assert EventType.ACTION_STEP_COMPLETED == "action_step_completed"
```

---

### Issue: Workflow status remains "running" after completion

**Symptoms:**
- Workflow executes successfully but status never changes from "running"
- Canvas UI shows workflow as in-progress indefinitely
- SSE events show workflow started but never completed

**Root Cause:** Forgetting to finalize workflow status and timing fields.

**Solution:** Always finalize workflow before returning:
```python
def finalize_workflow(workflow: ActionResult) -> ActionResult:
    """Finalize workflow result with timing."""
    workflow.completed_at = time.time()
    workflow.duration_ms = (workflow.completed_at - workflow.started_at) * 1000
    
    # Update status based on step results
    if workflow.status == "running":
        failed_steps = [s for s in workflow.steps if s.status == StepStatus.FAILED]
        if failed_steps:
            workflow.status = "failed"
            workflow.error = f"Failed steps: {[s.step_name for s in failed_steps]}"
        else:
            workflow.status = "completed"
    
    return workflow
```

---

### Issue: Steps execute but no SSE events received

**Symptoms:**
- Workflow executes correctly
- Canvas UI doesn't show progress updates
- No step completion events visible

**Root Cause:** Missing SSE event broadcasts or incorrect event targeting.

**Solution:** Ensure proper SSE broadcasting with session targeting:
```python
# After each step completion
await broadcaster.broadcast(
    SSEEvent(
        event_type=EventType.ACTION_STEP_COMPLETED,
        data=step_result.to_dict(),
        target_session_id=ctx.session_id,  # CRITICAL: must include session targeting
    )
)

# For final workflow result
await broadcaster.broadcast(
    SSEEvent(
        event_type=EventType.ACTION_WORKFLOW_COMPLETED,
        data=workflow_result.to_dict(),
        target_session_id=ctx.session_id,
    )
)
```

---

### Issue: TypeError when serializing StepResult to JSON

**Symptoms:**
```
TypeError: Object of type StepStatus is not JSON serializable
```

**Root Cause:** Attempting to serialize Pydantic models with enum values directly.

**Solution:** Always use `to_dict()` method before JSON serialization:
```python
# ❌ WRONG
json.dumps(step_result)  # TypeError

# ✅ CORRECT
json.dumps(step_result.to_dict())  # Converts enum to string

# ❌ WRONG
json.dumps(workflow_result)  # TypeError

# ✅ CORRECT  
json.dumps(workflow_result.to_dict())  # Recursively converts all enums
```

---

### Issue: Dry-run mode commits actual changes

**Symptoms:**
- Workflow with `dry_run=True` still commits changes
- Git history shows unexpected commits
- Declarative-config modified despite dry-run flag

**Root Cause:** Step executors not respecting `ctx.dry_run` flag.

**Solution:** Check dry-run flag in all mutating steps:
```python
async def execute_gitops_commit_step(ctx: ExecutionContext) -> dict[str, Any]:
    """Execute gitops_commit step with dry-run support."""
    
    if ctx.dry_run:
        return {
            "status": "skipped",
            "reason": "dry_run enabled - no commits made",
            "would_commit": True,
        }
    
    # Only proceed with actual commit when dry_run is False
    # ... actual commit logic ...
```

---

### Issue: Project not found in registry errors

**Symptoms:**
```
ValueError: Project 'my-project' not found in registry
```

**Root Cause:** Project slug not registered in `config/registry.yaml`.

**Solution:** Register project in registry configuration:
```yaml
# config/registry.yaml
projects:
  my-project:
    cluster: "iad-ci"
    namespace: "production"
    repo_path: "/path/to/project/repo"
    argocd_app: "my-project-app"
    
    workflows:
      deploy:
        description: "Deploy my-project"
        steps:
          - ci_status
          - gitops_commit
          - argocd_sync_status
```

**Verification:**
```python
from src.action.registry import list_workflows

# Should return dict of workflows
workflows = list_workflows("my-project")
print(f"Available workflows: {list(workflows.keys())}")
```

---

### Issue: Step executor timing out

**Symptoms:**
- Step hangs indefinitely
- No step completion event
- Workflow appears stuck

**Root Cause:** Long-running operations without timeout handling.

**Solution:** Implement proper timeout handling:
```python
import asyncio

async def execute_with_timeout(
    coro,
    timeout_seconds: float = 60.0,
    step_name: str = "unknown",
) -> Any:
    """Execute coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        raise RuntimeError(f"Step '{step_name}' timed out after {timeout_seconds}s")

# Usage in step executor
async def execute_slow_step(ctx: ExecutionContext) -> dict[str, Any]:
    result = await execute_with_timeout(
        slow_operation(),
        timeout_seconds=30.0,
        step_name="slow_step",
    )
    return result
```

---

### Issue: Kubectl proxy connection refused

**Symptoms:**
```
RuntimeError: Failed to get pod status: Connection refused
httpx.ConnectError: [Errno 111] Connection refused
```

**Root Cause:** Kubectl proxy not running or incorrect proxy URL in cluster config.

**Solution:** 
1. Check proxy is running:
```bash
# Check if proxy endpoint is accessible
curl -s http://kubectl-proxy-<cluster>:8001/api/v1/namespaces/default/pods
```

2. Verify cluster configuration:
```yaml
# config/clusters.yaml
clusters:
  my-cluster:
    proxy: "http://kubectl-proxy-my-cluster:8001"
```

3. Check proxy availability:
```python
from src.action.steps import _get_cluster_proxy

proxy_url = _get_cluster_proxy("my-cluster")
print(f"Proxy URL: {proxy_url}")  # Should not be None
```

---

### Issue: ArgoCD sync status polling times out

**Symptoms:**
```
RuntimeError: Failed to poll ArgoCD sync status: timeout
```

**Root Cause:** ArgoCD sync takes longer than the 5-minute timeout.

**Solution:** Adjust timeout or investigate sync issues:
```python
# In execute_argocd_sync_status_step
timeout = 300  # 5 minutes - increase if needed
poll_interval = 5  # 5 seconds between polls

# Check ArgoCD app status directly
kubectl get applications <app-name> -n argocd -o json
```

---

### Issue: Git operations fail in step executors

**Symptoms:**
```
RuntimeError: git log failed: fatal: not a git repository
RuntimeError: Failed to get git log: [Errno 2] No such file or directory
```

**Root Cause:** Incorrect `repo_path` in project configuration or path doesn't exist.

**Solution:** Verify repository path configuration:
```python
from pathlib import Path

repo_path = project_cfg.get("repo_path")
if not Path(repo_path).exists():
    raise RuntimeError(f"Repository path '{repo_path}' does not exist")

# Verify it's a git repository
git_dir = Path(repo_path) / ".git"
if not git_dir.exists():
    raise RuntimeError(f"Path '{repo_path}' is not a git repository")
```

---

### Issue: Bead workflow execution errors

**Symptoms:**
```
RuntimeError: bf list failed: bf: command not found
RuntimeError: bf list failed: [Errno 2] No such file or directory
```

**Root Cause:** `bf` CLI not installed or not in PATH.

**Solution:** 
1. Check `bf` installation:
```bash
which bf  # Should show path to bf executable
bf --version  # Should show version
```

2. Verify repo path for bead operations:
```python
repo_path = project_cfg.get("repo_path")
if not repo_path:
    # Fall back to aide-de-camp workspace
    repo_path = "/home/coding/aide-de-camp"
```

---

## Quick Diagnostic Checklist

When troubleshooting Action Execution Model issues, check these items in order:

1. **Event Types Defined?**
   ```python
   from src.sse.broadcaster import EventType
   assert hasattr(EventType, 'ACTION_WORKFLOW_STARTED')
   ```

2. **Project Registered?**
   ```python
   from src.action.registry import list_workflows
   workflows = list_workflows("my-project")
   ```

3. **Context Valid?**
   ```python
   ctx = ExecutionContext(intent_id="test", session_id="test")
   assert ctx.intent_id and ctx.session_id
   ```

4. **SSE Broadcaster Running?**
   ```python
   from src.sse import get_broadcaster
   broadcaster = get_broadcaster()
   assert broadcaster is not None
   ```

5. **Step Executors Registered?**
   ```python
   from src.action.executor import get_action_executor
   executor = get_action_executor()
   assert "ci_status" in executor._step_executors
   ```

6. **Cluster Config Valid?**
   ```python
   # Check config/clusters.yaml exists
   # Check proxy URLs are accessible
   ```

7. **ArgoCD Accessible?**
   ```python
   # Check ArgoCD base URL in config/registry.yaml
   # Verify API endpoint is reachable
   ```

## Type Reference Summary

| Type | Purpose | Required Fields | Key Methods |
|------|---------|-----------------|-------------|
| `StepStatus` | Step execution state enum | N/A (enum) | N/A |
| `ExecutionContext` | Runtime context carrier | `intent_id`, `session_id` | `cluster`, `namespace`, `repo_path`, `argocd_app` properties |
| `StepResult` | Single step execution result | `step_name`, `status`, `started_at` | `to_dict()` |
| `ActionResult` | Complete workflow result | `intent_id`, `session_id`, `workflow_name`, `status`, `started_at` | `add_step()`, `to_dict()` |
| `Step` | Base class for step definitions | `step_type` | N/A |

## Implementation Verification Notes

### ✅ Fixed Issues (2026-08-06)

1. **Missing EventType Constants** (FIXED)
   - Previously: `executor.py` referenced `EventType.ACTION_*` constants that didn't exist
   - Fixed: Added all action workflow event types to `src/sse/broadcaster.py` EventType class
   - Events added: `ACTION_WORKFLOW_STARTED`, `ACTION_STEP_STARTED`, `ACTION_STEP_COMPLETED`, `ACTION_WORKFLOW_COMPLETED`, `ACTION_WORKFLOW_FAILED`, `ACTION_WORKFLOW_CANCELLED`

### ⚠️ Known Limitations

1. **Sequential Execution Only** (By Design)
   - Current `ActionExecutor` executes steps sequentially (not in parallel)
   - Parallel execution patterns shown in Pattern 5 are aspirational/design patterns
   - Parallel execution must be implemented within individual step executors if needed
   - Future versions may add native parallel step execution support

### ✅ Verified Correct

The following aspects of the documentation match the implementation accurately:

- All type definitions exactly match `src/action/models.py`
- Step vocabulary matches registered step types in `ActionExecutor.__init__`
- Method signatures and return types are accurate
- Best practices and gotchas are based on real implementation issues
- SSE broadcasting patterns are correct (except for missing constants)
- ExecutionContext convenience properties work as documented

### Implementation Details Verified

**Step Executor Registry** (from `executor.py` line 249-261):
```python
self._step_executors = {
    "ci_status": self._execute_ci_status,
    "image_tag": self._execute_image_tag, 
    "gitops_commit": self._execute_gitops_commit,
    "argocd_sync_status": self._execute_argocd_sync_status,
    "pod_status": self._execute_pod_status,
    "deployment_info": self._execute_deployment_info,
    "git_log": self._execute_git_log,
    "argocd_apps": self._execute_argocd_apps,
    "open_beads": self._execute_open_beads,
}
```

**Execution Flow** (from `executor.py` line 334-362):
- Workflows execute steps sequentially (not in parallel)
- Failed steps halt the workflow immediately (fail-fast pattern)
- Each step result is added to `ActionResult.steps` list
- Progress broadcasts after each step completion

**SSE Event Flow** (from `executor.py` line 637-716):
- `ACTION_WORKFLOW_STARTED`: Broadcast when workflow begins
- `ACTION_STEP_STARTED`: Broadcast before each step executes
- `ACTION_STEP_COMPLETED`: Broadcast after each step finishes
- `ACTION_WORKFLOW_COMPLETED/FAILED/CANCELLED`: Final workflow status

✅ All event types are now properly defined in `src/sse/broadcaster.py` EventType class.

## Quick Reference Card

```python
# Creating ExecutionContext
ctx = ExecutionContext(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="my-project",
    project_cfg={"cluster": "iad-ci", "namespace": "prod"},
    dry_run=False,
)

# Accessing context
cluster = ctx.cluster        # Property access
namespace = ctx.namespace   # Property access

# Creating StepResult
result = StepResult(
    step_name="my_step",
    status=StepStatus.COMPLETED,
    output={"key": "value"},
    started_at=time.time(),
    completed_at=time.time(),
    duration_ms=1000.0,
)

# Creating ActionResult
workflow = ActionResult(
    intent_id=ctx.intent_id,
    session_id=ctx.session_id,
    workflow_name="deploy",
    status="running",
    started_at=time.time(),
)

# Adding steps to workflow
workflow.add_step(result)

# Serializing for SSE/JSON
dict_result = result.to_dict()
dict_workflow = workflow.to_dict()

# Broadcasting via SSE
await broadcaster.broadcast(
    SSEEvent(
        event_type="step_completed",
        target_session_id=ctx.session_id,
        data=result.to_dict(),
    )
)
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-08-07  
**Maintained By:** aide-de-camp project  
**Related Documents:** 
- `docs/status-code.md` (StepStatus detailed documentation)
- `docs/stepresult-type-documentation.md` (StepResult detailed documentation)  
- `docs/execution-context.md` (ExecutionContext detailed documentation)