# ExecutionContext Type Documentation

## Overview

`ExecutionContext` is a Pydantic model that provides configuration and runtime context needed for executing workflow steps in the Action Execution Model. It serves as the primary carrier of state through the action execution pipeline, ensuring that all step executors have access to the project configuration, cluster information, and tracking identifiers they need.

## Type Definition

```python
class ExecutionContext(BaseModel):
    """
    Context passed to all step executors.
    
    Contains project configuration and runtime context needed for step execution:
    - Project identification (slug, repo path)
    - Cluster configuration (cluster name, namespace)
    - Tracking identifiers (intent_id, session_id)
    - Execution flags (dry_run)
    """
    intent_id: str = Field(..., description="Intent ID for tracking and SSE targeting")
    session_id: str = Field(..., description="Session ID for SSE targeting")
    project_slug: Optional[str] = Field(None, description="Project slug for registry lookup")
    project_cfg: dict[str, Any] = Field(default_factory=dict, description="Project configuration from registry")
    dry_run: bool = Field(default=False, description="If True, skip mutating operations")
```

## Field Documentation

### Required Fields

| Field | Type | Description | Purpose |
|-------|------|-------------|---------|
| `intent_id` | `str` | Intent ID for tracking and SSE targeting | Uniquely identifies the intent that triggered this workflow. Used for log correlation and SSE event targeting. |
| `session_id` | `str` | Session ID for SSE targeting | Identifies the user session for Server-Sent Events broadcasting. Ensures workflow events are routed to the correct canvas surface. |

### Optional Fields

| Field | Type | Default | Description | Purpose |
|-------|------|---------|-------------|---------|
| `project_slug` | `Optional[str]` | `None` | Project slug for registry lookup | Identifies which project in the registry to use for configuration. If `None`, no project context is available. |
| `project_cfg` | `dict[str, Any]` | `{}` | Project configuration from registry | Contains the full project configuration loaded from `config/registry.yaml`, including cluster, namespace, repo_path, and workflow definitions. |
| `dry_run` | `bool` | `False` | If True, skip mutating operations | Controls whether step executors should perform mutations (GitOps commits, image updates) or only simulate them. Useful for testing and preview. |

## Convenience Properties

`ExecutionContext` provides computed properties for commonly accessed fields within `project_cfg`:

### `cluster`

```python
@property
def cluster(self) -> Optional[str]:
    """Get cluster name from project configuration."""
    return self.project_cfg.get("cluster")
```

**Purpose:** Provides direct access to the cluster name (e.g., `"apexalgo-iad"`, `"rs-manager"`) from the project configuration without requiring dictionary access.

**Example usage:**
```python
proxy_url = get_cluster_proxy(ctx.cluster)
```

### `namespace`

```python
@property
def namespace(self) -> Optional[str]:
    """Get namespace from project configuration."""
    return self.project_cfg.get("namespace")
```

**Purpose:** Provides direct access to the Kubernetes namespace where the project's workloads run.

**Example usage:**
```python
pods = await kubectl_get_pods(namespace=ctx.namespace)
```

### `repo_path`

```python
@property
def repo_path(self) -> Optional[str]:
    """Get repository path from project configuration."""
    return self.project_cfg.get("repo_path")
```

**Purpose:** Provides direct access to the local filesystem path where the project's Git repository is checked out.

**Example usage:**
```python
subprocess.run(["git", "-C", ctx.repo_path, "log", "-1"])
```

### `argocd_app`

```python
@property
def argocd_app(self) -> Optional[str]:
    """Get ArgoCD application name from project configuration."""
    return self.project_cfg.get("argocd_app")
```

**Purpose:** Provides direct access to the ArgoCD application name for the project, used for sync status checks and application queries.

**Example usage:**
```python
app_status = await argocd_get_app(ctx.argocd_app)
```

## Lifecycle

### Creation

`ExecutionContext` is typically created at the entry point of workflow execution, when an intent is routed to an action workflow:

```python
# In ActionExecutor.execute_workflow()
ctx = ExecutionContext(
    intent_id=intent_id,
    session_id=session_id,
    project_slug=project_slug,
    project_cfg=project_cfg,  # Loaded from registry
    dry_run=False,  # Or determined from user input
)
```

**Creation flow:**
1. User utterance arrives at `/dispatch` endpoint
2. Intent router classifies the utterance and extracts `project_slug`
3. Project configuration is loaded from registry via `get_project(project_slug)`
4. `ExecutionContext` is instantiated with tracking IDs and project config
5. Context is passed to each step executor as the workflow runs

### Updates

`ExecutionContext` is **immutable during workflow execution**. Once created, its fields do not change:

- The `dry_run` flag cannot be toggled mid-workflow
- Project configuration cannot be modified after creation
- Tracking IDs (`intent_id`, `session_id`) remain constant throughout execution

**Why immutable?**
- Predictable execution: step executors see consistent context
- Easier debugging: context doesn't change between steps
- Simpler logging: intent_id and session_id are stable for correlation

### Finalization

`ExecutionContext` does not require explicit cleanup. As a Pydantic model, it is garbage-collected when:

1. The workflow completes successfully (ActionResult is returned)
2. The workflow fails (ActionResult with error status)
3. The workflow is cancelled

**No finalization logic** is needed because:
- No file handles or network connections are held by the context itself
- All resources (kubectl sessions, HTTP clients) are managed by individual step executors
- The context is purely a data carrier

## Usage Examples

### Basic Usage in Step Executor

```python
async def execute_pod_status_step(ctx: ExecutionContext) -> dict[str, Any]:
    """Execute pod status check using context."""
    
    # Access cluster configuration via properties
    namespace = ctx.namespace
    cluster = ctx.cluster
    
    # Use tracking identifiers for logging
    logger.info(
        f"Checking pods for intent {ctx.intent_id[:8]} "
        f"in namespace={namespace} on cluster={cluster}"
    )
    
    # Execute kubectl query
    proxy_url = get_cluster_proxy(cluster)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{proxy_url}/api/v1/namespaces/{namespace}/pods"
        )
    
    return {"pods": response.json().get("items", [])}
```

### Dry Run Pattern

```python
async def execute_gitops_commit_step(ctx: ExecutionContext) -> dict[str, Any]:
    """Execute GitOps commit, respecting dry_run flag."""
    
    repo_path = ctx.repo_path
    
    if ctx.dry_run:
        # Skip mutations in dry run mode
        return {
            "status": "dry_run",
            "message": "Would commit: update image tag to v1.2.3",
            "repo_path": repo_path,
        }
    
    # Perform actual GitOps mutation
    subprocess.run(
        ["git", "-C", repo_path, "commit", "-am", "chore: update image"],
        check=True
    )
    subprocess.run(
        ["git", "-C", repo_path, "push"],
        check=True
    )
    
    return {"status": "committed", "repo_path": repo_path}
```

### SSE Targeting with Session ID

```python
async def execute_deployment_info_step(ctx: ExecutionContext) -> dict[str, Any]:
    """Execute deployment info step with SSE broadcasting."""
    
    # Execute step logic
    deployments = await get_deployments(ctx.namespace, ctx.cluster)
    
    # Broadcast result to canvas using session_id from context
    broadcaster = get_broadcaster()
    await broadcaster.broadcast(
        SSEEvent(
            event_type="deployment_info_completed",
            data={"deployments": deployments},
            target_session_id=ctx.session_id,  # Route to correct canvas
        )
    )
    
    return {"deployments": deployments}
```

### Validation Pattern

```python
class PodStatusExecutor(StepExecutor):
    """Executor with context validation."""
    
    def validate(self, ctx: ExecutionContext) -> None:
        """Validate context before execution."""
        if not ctx.namespace:
            raise ValueError("namespace required in context")
        if not ctx.cluster:
            raise ValueError("cluster required in context")
        
        # Check if cluster has proxy configured
        proxy_url = get_cluster_proxy(ctx.cluster)
        if not proxy_url:
            raise ValueError(f"cluster '{ctx.cluster}' has no proxy configured")
    
    async def execute(self, ctx: ExecutionContext) -> StepResult:
        """Execute with validated context."""
        # Context is guaranteed to have namespace and cluster here
        pods = await get_pods(ctx.namespace, ctx.cluster)
        return StepResult(status=StepStatus.COMPLETED, output={"pods": pods})
```

### Context Flow Through Multi-Step Workflow

```python
# Step 1: CI Status Check
step1_result = await execute_ci_status_step(ctx)
# ctx.intent_id == "abc123", ctx.project_slug == "mta-my-way"

# Step 2: Image Tag Resolution (uses same context)
step2_result = await execute_image_tag_step(ctx)
# Same tracking IDs, same project config

# Step 3: GitOps Commit (uses same context)
step3_result = await execute_gitops_commit_step(ctx)
# If ctx.dry_run == True, this step skips mutations

# Step 4: ArgoCD Sync Check (uses same context)
step4_result = await execute_argocd_sync_status_step(ctx)
# Uses ctx.argocd_app property derived from project_cfg
```

## Thread-Safety and Immutability Considerations

### Thread-Safety

`ExecutionContext` is **thread-safe for read-only operations** because:

1. **Pydantic models are immutable by default** — Once instantiated, field values cannot be reassued
2. **No shared mutable state** — The context does not hold references to mutable objects that could be modified concurrently
3. **No internal locking required** — Read operations (property access, field access) are atomic

**Multi-threading scenario:**
```python
# Multiple step executors can read the same context concurrently
ctx = ExecutionContext(intent_id="abc", session_id="session1", ...)

# Thread 1: Reading namespace
namespace_1 = ctx.namespace  # Safe

# Thread 2: Reading cluster (concurrently)
cluster_2 = ctx.cluster  # Safe, no race condition
```

### Immutability

**Do not mutate `ExecutionContext` after creation.** The model is designed to be immutable:

```python
# ❌ WRONG: Attempting to modify fields
ctx.dry_run = True  # Pydantic may raise ValidationError
ctx.project_cfg["cluster"] = "new-cluster"  # Modifies dict, but breaks immutability contract

# ✅ CORRECT: Create new context with updated values
new_ctx = ctx.model_copy(update={"dry_run": True})
```

**Why enforce immutability?**
1. **Predictability** — Step executors can rely on context values not changing mid-execution
2. **Debugging** — Easier to trace execution when context is stable
3. **Concurrency** — No need for locks when multiple steps read the same context
4. **Testing** — Easier to write deterministic tests when state doesn't change

### Safe Patterns for Mutable project_cfg

The `project_cfg` field is a `dict[str, Any]`, which is mutable. To maintain immutability guarantees:

**For step executors:** Read-only access is safe
```python
# ✅ SAFE: Reading from project_cfg
cluster = ctx.project_cfg.get("cluster")

# ❌ UNSAFE: Modifying project_cfg
ctx.project_cfg["cluster"] = "new-cluster"  # Breaks immutability
```

**For context creation:** Make a copy if you need to modify
```python
# ✅ SAFE: Create new context with modified config
new_cfg = ctx.project_cfg.copy()
new_cfg["cluster"] = "new-cluster"
new_ctx = ctx.model_copy(update={"project_cfg": new_cfg})
```

### Pydantic Validation

`ExecutionContext` uses Pydantic validation, which provides additional safety:

```python
# ✅ Valid creation
ctx = ExecutionContext(
    intent_id="abc123",
    session_id="session1",
    project_slug="mta-my-way",
    project_cfg={"cluster": "apexalgo-iad"},
    dry_run=False
)

# ❌ ValidationError: Missing required fields
ctx = ExecutionContext(
    intent_id="abc123",
    # session_id is required but missing
)
```

## Integration with Action Execution Model

`ExecutionContext` fits into the Action Execution Model as follows:

```
User Utterance
    ↓
Intent Router (classifies utterance → project_slug, workflow_name)
    ↓
Project Registry Lookup (loads project config)
    ↓
ExecutionContext Creation (intent_id, session_id, project_slug, project_cfg)
    ↓
ActionExecutor.execute_workflow(ctx)
    ↓
For each step in workflow:
    StepExecutor.execute(ctx)  ← Context flows to every step
        ↓
    StepResult (status, output, error)
        ↓
    SSE Broadcast (using ctx.session_id for targeting)
    ↓
ActionResult (final workflow result)
```

**Key integration points:**
1. **Intent Router** — Creates `ExecutionContext` with tracking IDs
2. **ActionExecutor** — Passes context to each step executor sequentially
3. **Step Executors** — Use context for cluster, namespace, repo access
4. **SSE Broadcaster** — Uses `ctx.session_id` to route events to canvas

## Best Practices

1. **Always validate context** in step executors before using required fields:
   ```python
   if not ctx.namespace:
       raise ValueError("namespace required")
   ```

2. **Use convenience properties** instead of direct `project_cfg` access:
   ```python
   # ✅ Good
   cluster = ctx.cluster
   
   # ❌ Avoid
   cluster = ctx.project_cfg.get("cluster")
   ```

3. **Respect the dry_run flag** in all mutating operations:
   ```python
   if ctx.dry_run:
       return {"status": "dry_run", "would_mutate": "..."}
   ```

4. **Use tracking IDs for logging** to enable correlation:
   ```python
   logger.info(f"Step executing for intent {ctx.intent_id[:8]}")
   ```

5. **Do not modify context after creation** — Create a new instance if needed:
   ```python
   new_ctx = ctx.model_copy(update={"dry_run": True})
   ```

## Type Summary

- **Type:** Pydantic `BaseModel`
- **Required fields:** `intent_id`, `session_id`
- **Optional fields:** `project_slug`, `project_cfg`, `dry_run`
- **Thread-safety:** Safe for concurrent reads, immutable after creation
- **Lifecycle:** Created at workflow start, discarded after workflow completion
- **Purpose:** Carry project config and tracking state through step execution pipeline
