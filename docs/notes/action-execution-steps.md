# Action Execution Model - Step Vocabulary

This document defines the complete step vocabulary for the Action Execution Model. Each step represents a deterministic operation that either reads cluster state or performs GitOps mutations through declarative-config edits.

## Step Categories

### Mutation Steps (GitOps)

These steps modify infrastructure by editing declarative-config and committing to Git. Never use direct kubectl mutations for these operations.

1. **`ci_status`** - Check CI/workflow status
   - Gates workflow execution if CI is not green
   - Queries Argo Workflows in iad-ci cluster
   - Returns workflow phase, message, and timestamp
   - Used as pre-deployment gate

2. **`image_tag`** - Resolve image tag/digest from CI
   - Extracts version tag from successful CI workflow name
   - Supports both semantic versions (v1.2.3) and digests (sha256:abc123)
   - Rejects :latest tag explicitly
   - Returns tag, digest (if present), and registry path

3. **`gitops_commit`** - Templated declarative-config edit
   - Authors declarative-config edits (never LLM-authored)
   - Template-based field substitution only
   - Commits and pushes to declarative-config repo
   - Returns commit SHA, message, and files changed
   - **CRITICAL**: This is the only sanctioned mutation pattern

4. **`argocd_sync_status`** - Poll ArgoCD until Synced/Healthy
   - Monitors ArgoCD application sync status
   - Polls until Synced and Healthy states achieved
   - Returns sync status, health status, and revision
   - Used post-commit to verify GitOps sync

5. **`pod_status`** - Post-sync pod verification
   - Queries pod status via kubectl proxy
   - Verifies pod health after deployment
   - Returns pod counts, phases, and ready ratios
   - Catches rollout failures early

### Read-Only Steps (No Mutation)

These steps query cluster state or external systems without making any changes.

6. **`deployment_info`** - Get deployment/statefulset information
   - Queries Deployment or StatefulSet resources
   - Returns replica counts, image versions, and update strategy
   - Read-only via kubectl proxy

7. **`git_log`** - Get recent git history
   - Queries git log for recent commits
   - Returns commit messages, authors, and timestamps
   - Used for change tracking and audit

8. **`argocd_apps`** - Get ArgoCD application status
   - Queries ArgoCD read-only API
   - Returns application sync and health status
   - No mutation, read-only proxy access

9. **`open_beads`** - Get open beads for project
   - Queries beadforge (bf) for open project beads
   - Returns bead IDs, titles, and status
   - Used for project tracking and context

## Step Execution Contract

All steps implement the same execution interface:

```python
async def execute_step(
    intent_id: str,
    session_id: str,
    project_slug: str,
    project_cfg: dict,
    workflow_name: str,
) -> dict[str, Any]:
    """Execute the step and return output data."""
```

### Input Parameters

- **`intent_id`**: Intent tracking ID for SSE targeting
- **`session_id`**: Session ID for SSE targeting
- **`project_slug`**: Project identifier for registry lookup
- **`project_cfg`**: Project configuration from registry (cluster, namespace, repo_path, argocd_app)
- **`workflow_name`**: Name of the workflow executing this step

### Return Format

All steps return a dictionary with step-specific data:

```python
{
    "status": "...",  # Step-specific status
    "...": "...",     # Additional step-specific fields
}
```

### Error Handling

Steps raise exceptions on failure:

- **`ValueError`**: Invalid parameters or configuration
- **`RuntimeError`**: Execution failures (kubectl, git, HTTP)
- **`TimeoutError`**: Step execution timeout

The executor catches these and converts to `StepResult` with `status=FAILED`.

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
