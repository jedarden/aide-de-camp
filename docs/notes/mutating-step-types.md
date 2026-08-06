# Mutating Step Types

This document describes the 3 mutating step types in the Action Execution Model. These steps modify infrastructure or git state through GitOps patterns.

## Overview

Mutating steps are used for:
- **CI gating** - Check CI/workflow status before proceeding
- **Image resolution** - Resolve image tags/digests from CI builds
- **GitOps mutations** - Templated declarative-config edits with commit + push

All mutating steps follow these principles:
1. **Deterministic** - No LLM calls in execution (template-based only)
2. **GitOps pattern** - All mutations go through git commit + push
3. **Dry-run safe** - Respect `ExecutionContext.dry_run` flag
4. **Atomic operations** - Each step is a single logical mutation

---

## 1. ci_status

### Purpose
Check CI/workflow status and gate the workflow if CI is not green. This is a read-only gate that can block workflow execution based on external CI state.

### Parameters
- `project_slug` (optional) - Project identifier for workflow label filtering
- `project_cfg.cluster` - Cluster name for logging/context
- `kubectl_config` - Path to CI cluster kubeconfig (default: `/home/coding/.kube/iad-ci.kubeconfig`)
- `timeout` - Command timeout (default: 15 seconds)

### Output Format
```python
# Success case
{
    "status": "success",                    # "success" or "failed"
    "phase": "Succeeded",                   # Argo workflow phase
    "workflow_name": "mta-my-way-build-abc123",  # Workflow name
    "cluster": "iad-ci"
}

# CI not accessible
{
    "status": "skipped",
    "reason": "CI cluster not accessible",
    "cluster": "iad-ci"
}

# No workflows found
{
    "status": "no_workflows",
    "reason": "No CI workflows found",
    "cluster": "iad-ci"
}
```

### Mutation Behavior
This step does **not mutate state** - it's a read-only gate. However, it's categorized as mutating because it controls workflow execution flow based on external CI state.

### Gate Behavior
- **`phase == "Succeeded"`** → Workflow proceeds
- **`phase != "Succeeded"`** → Workflow fails/blocks
- **CI cluster not accessible** → Returns `status: "skipped"` (non-blocking)
- **No workflows found** → Returns `status: "no_workflows"` (non-blocking)

### Usage Example
```python
from src.action.steps import execute_ci_status_step

result = await execute_ci_status_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={"cluster": "rs-manager"}
)

if result["status"] == "success":
    print(f"CI workflow {result['workflow_name']} succeeded")
elif result["status"] == "failed":
    raise RuntimeError(f"CI workflow {result['workflow_name']} failed: {result['phase']}")
```

### Error Cases
- **Kubeconfig not found** - Returns `status: "skipped"` with warning (non-blocking)
- **kubectl timeout** - RuntimeError after 15 seconds
- **kubectl failure** - RuntimeError from stderr
- **Workflow parse error** - RuntimeError during JSON parsing

### Implementation
- **Source**: `src/action/steps.py:execute_ci_status_step()`
- **Command**: `kubectl --kubeconfig {kubectl_config} get workflows -n argo-workflows -l project={project_slug}`
- **API**: Argo Workflows Kubernetes API in `iad-ci` cluster
- **Filtering**: Most recent workflow by `metadata.creationTimestamp`
- **Gate logic**: Checks `status.phase == "Succeeded"`

### Dry Run Handling
In dry-run mode (`ctx.dry_run == True`), this step:
- Still executes the CI status check (read-only)
- Returns the same result as normal mode
- Does NOT gate or block the workflow (CI check is informational only)

---

## 2. image_tag

### Purpose
Resolve image tag/digest from CI build output. This step queries CI systems to find the published image reference for a given project build.

### Parameters
- `project_slug` (optional) - Project identifier for image lookup
- `project_cfg.cluster` - Cluster name for logging
- `image_name` - Container image name (e.g., `ronaldraygun/mta-my-way`)
- `build_id` - Optional specific CI build ID to query

### Output Format
```python
# Success case (not yet implemented)
{
    "status": "success",
    "image": "ronaldraygun/mta-my-way:v1.2.3",
    "digest": "sha256:abc123...",
    "tag": "v1.2.3",
    "build_id": "mta-my-way-build-abc123"
}

# Not implemented (current state)
{
    "status": "not_implemented",
    "reason": "Image tag resolution needs CI-specific implementation",
    "project_slug": "mta-my-way"
}
```

### Mutation Behavior
This step does **not mutate state** - it's a read-only resolution step. It queries CI systems to find image references, which are then used by `gitops_commit` for templated edits.

### Usage Example
```python
from src.action.steps import execute_image_tag_step

result = await execute_image_tag_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={"cluster": "rs-manager"}
)

if result["status"] == "success":
    image_ref = result["image"]  # e.g., "ronaldraygun/mta-my-way:v1.2.3"
    # Use this in gitops_commit step
```

### Error Cases
- **Build not found** - Returns error if build_id doesn't exist
- **CI API timeout** - RuntimeError after timeout
- **No image published** - RuntimeError if build completed but no image pushed
- **Not implemented** - Returns `status: "not_implemented"` (current state)

### Implementation
- **Source**: `src/action/steps.py:execute_image_tag_step()`
- **Current State**: Returns `not_implemented` placeholder
- **Planned Implementation**: Query Argo Workflows or container registry to resolve image references
- **Integration**: Works with `gitops_commit` to provide resolved image tags for declarative-config edits

### Dry Run Handling
In dry-run mode (`ctx.dry_run == True`), this step:
- Executes normally (read-only query)
- Returns the same result as normal mode
- No special handling needed (no mutations)

---

## 3. gitops_commit

### Purpose
Apply templated declarative-config edits with automated git commit + push. This is the primary GitOps mutation step for infrastructure changes.

### Parameters
- `project_slug` (optional) - Project identifier
- `project_cfg.repo_path` (required) - Path to declarative-config repo
- `template_file` - Path to manifest template within declarative-config
- `substitutions` - Key-value pairs for template substitution
- `commit_message` - Git commit message following project conventions

### Output Format
```python
# Success case (not yet implemented)
{
    "status": "success",
    "commit": "abc123def456",
    "repo": "ardent/declarative-config",
    "branch": "main",
    "files_changed": ["k8s/rs-manager/mta-my-way/deployment.yaml"],
    "message": "chore: update mta-my-way image to v1.2.3"
}

# Not implemented (current state)
{
    "status": "not_implemented",
    "reason": "GitOps commit needs declarative-config-specific implementation",
    "repo_path": "/home/coding/declarative-config"
}
```

### Mutation Behavior
This step **DOES mutate state** through GitOps pattern:
1. Checkout target branch (default: `main`)
2. Apply template substitutions to manifest file
3. Stage changes with `git add`
4. Commit with standard git identity (`github@jedarden.com`)
5. Push to Forgejo `origin` (GitHub mirror syncs automatically)

### Template Substitution
The step uses field-level substitution (never structural edits):
- **Image tags**: `image: ronaldraygun/app:v1.0.0` → `image: ronaldraygun/app:v1.2.3`
- **Replica counts**: `replicas: 3` → `replicas: 5`
- **Resource limits**: `memory: "256Mi"` → `memory: "512Mi"`
- **ConfigMap values**: `value: "prod"` → `value: "staging"`

### Usage Example
```python
from src.action.steps import execute_gitops_commit_step

result = await execute_gitops_commit_step(
    intent_id="intent-123",
    session_id="session-456",
    project_slug="mta-my-way",
    project_cfg={
        "repo_path": "/home/coding/declarative-config",
        "cluster": "rs-manager"
    }
)

if result["status"] == "success":
    print(f"Committed {result['commit']} to {result['repo']}")
```

### Error Cases
- **repo_path not configured** - ValueError if `project_cfg.repo_path` is None
- **Repository path does not exist** - RuntimeError if path not on disk
- **Template file not found** - RuntimeError if template_file doesn't exist
- **Git operation timeout** - RuntimeError during git operations
- **Push rejected** - RuntimeError if git push fails
- **Not implemented** - Returns `status: "not_implemented"` (current state)

### Implementation
- **Source**: `src/action/steps.py:execute_gitops_commit_step()`
- **Current State**: Returns `not_implemented` placeholder
- **Planned Implementation**: 
  1. Checkout branch
  2. Apply template substitutions (YAML field edits)
  3. `git add` changed files
  4. `git commit` with standard identity
  5. `git push` to Forgejo origin
- **Git Identity**: Uses `github@jedarden.com` / `jedarden` per CLAUDE.md
- **Repo Access**: Forgejo primary, GitHub mirror (automatic sync)

### Dry Run Handling
In dry-run mode (`ctx.dry_run == True`), this step:
- Skips all git operations (no checkout, no edit, no commit, no push)
- Returns `status: "skipped"` with planned changes in output
- Shows what WOULD be committed without executing mutations

### Template Safety Constraints
The executor authors the edit (never LLM-authored):
- **Field substitution only** - No structural YAML changes
- **Type-preserving** - Numbers stay numbers, strings stay strings
- **No LLM involvement** - Deterministic template engine
- **File-scoped** - Edits only specified files, never multi-file refactors

---

## GitOps Mutation Conventions

### Commit + Push Workflow

All GitOps mutations follow the standard pattern:

```bash
# 1. Ensure clean checkout
git -C {repo_path} checkout main
git -C {repo_path} pull origin main

# 2. Apply templated edits (field substitution only)
# Edit deployment.yaml image tag from v1.0.0 → v1.2.3

# 3. Stage changes
git -C {repo_path} add k8s/rs-manager/app/deployment.yaml

# 4. Commit with standard identity
git -C {repo_path} -c "user.email=github@jedarden.com" \
                    -c "user.name=jedarden" \
                    commit -m "chore: update app image to v1.2.3"

# 5. Push to Forgejo origin
git -C {repo_path} push origin main
```

### Git Identity Standards

All GitOps commits use the standard identity per CLAUDE.md:
- **Email**: `github@jedarden.com`
- **Name**: `jedarden`

### Commit Message Conventions

Follow conventional commit format:
- **chore**: Update image tags, replica counts, resource limits
- **fix**: Correct configuration errors
- **feat**: Add new configuration (rare, usually done manually)

Examples:
- `chore: update pbx-web image to v1.2.3`
- `chore: scale mta-my-way to 3 replicas`
- `fix: correct memory limit in deployment`

### ArgoCD Sync Flow

After `gitops_commit`, the typical flow is:

1. **`gitops_commit`** pushes to Forgejo `origin/main`
2. **GitHub mirror** syncs automatically (server-side)
3. **ArgoCD** detects git change in `declarative-config`
4. **ArgoCD** syncs manifests to cluster
5. **`argocd_sync_status`** polls until `Synced` + `Healthy`

### Forgejo Primary, GitHub Mirror

All GitOps mutations target Forgejo as the source of truth:
- **Push target**: `git.ardenone.com` (Forgejo)
- **Mirror**: `github.com/jedarden` (automatic, read-only)
- **Never force-push**: Reconcile with merge commits if needed
- **Never dual-push**: Push to Forgejo only, let mirror sync

### Error Recovery

If `git push` fails:
- **Network timeout**: Retry with exponential backoff
- **Non-fast-forward**: Pull + merge commit, then push
- **Permission denied**: Check Forgejo token validity
- **Repository not found**: Verify repo_path configuration

---

## Common Patterns

### StepResult Structure

All mutating steps return a dict with:
- `status: str` - `"success"`, `"failed"`, `"skipped"`, or `"not_implemented"`
- `data: dict` - Step-specific output data
- Error cases raise `RuntimeError` or `ValueError`

### Dry Run Convention

All mutating steps respect `ExecutionContext.dry_run`:
- **`ci_status`**: Executes normally (read-only gate)
- **`image_tag`**: Executes normally (read-only resolution)
- **`gitops_commit`**: Skips mutations, returns `status: "skipped"`

### Configuration Sources

- **Repository paths**: `project_cfg.repo_path`
- **CI cluster kubeconfig**: `/home/coding/.kube/iad-ci.kubeconfig`
- **Project context**: `project_cfg` dict from action intent metadata

### Timeouts

- **kubectl commands**: 15 seconds (ci_status)
- **Git operations**: 30 seconds (gitops_commit, not yet implemented)
- **CI API calls**: 10 seconds (image_tag, not yet implemented)

### Error Handling

All mutating steps follow consistent error patterns:
1. **Missing required config** - ValueError (e.g., no repo_path)
2. **External system timeout** - RuntimeError with context
3. **Operation failure** - RuntimeError with stderr/details
4. **Not implemented** - Returns `status: "not_implemented"` (current state for image_tag, gitops_commit)

---

## Mutation Safety Constraints

### No LLM Involvement in Execution

All mutating steps are **deterministic** - no LLM calls during execution:
- Templates are predefined (not LLM-generated)
- Substitutions are key-value based (not prose)
- Edits are field-level (not structural)

### Atomic Operations

Each mutating step is a single logical mutation:
- **`ci_status`**: Single workflow status check
- **`image_tag`**: Single image resolution
- **`gitops_commit`**: Single manifest edit + commit + push

### Idempotent Where Possible

- **`ci_status`**: Idempotent (read-only)
- **`image_tag`**: Idempotent (read-only)
- **`gitops_commit`**: NOT idempotent (each push creates a new commit)

### Reversible

All mutations are reversible through GitOps:
- **`gitops_commit`**: Revert with `git revert` or new commit
- **`ci_status`**: No mutation (gate only)
- **`image_tag`**: No mutation (resolution only)

---

## See Also

- [Read-Only Step Types](read-only-step-types.md) - Non-mutating step types
- [Action Execution Data Structures](action-execution-data-structures.md) - ExecutionContext, StepResult models
- [Action Execution Steps](action-execution-steps.md) - Complete step vocabulary
- `src/action/steps.py` - All step implementations
- `CLAUDE.md` - Git identity, GitOps patterns, hard prohibitions