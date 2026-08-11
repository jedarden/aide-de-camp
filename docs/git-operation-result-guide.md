# GitOperationResult Structure and Cleanup Behavior

This guide documents the `GitOperationResult` structure and cleanup guarantees provided by the GitOps operations in the action system.

## Overview

The GitOps operations (`GitOpsCommitStep`, rollback, and other git operations) return structured results via the `GitOperationResult` dataclass. This structure provides:

- Clear operation status (`SUCCESS`, `FAILED`, `PARTIAL`)
- Commit tracking (commit SHA, branch, manifest path)
- Error context with actionable messages
- Automatic cleanup guarantees

## GitOperationResult Structure

### Fields

```python
@dataclass
class GitOperationResult:
    """Structured outcome of a GitOps operation."""

    commit_sha: str | None = None           # Git commit SHA (if successful)
    branch: str | None = None               # Branch name (typically "main")
    manifest_path: str | None = None        # Path to modified manifest
    status: GitOperationStatus              # SUCCESS, FAILED, or PARTIAL
    error: str | None = None                # Error description (if failed)
    details: dict[str, Any]                  # Additional operation metadata
```

### Status Values

The `GitOperationStatus` enum defines three states:

- **`SUCCESS`**: Complete operation succeeded (commit + push)
- **`FAILED`**: Operation failed before any persistent change
- **`PARTIAL`**: Local commit succeeded, but push failed (commit SHA is preserved for recovery)

## Creation Methods

### `create_success()`

Create a successful operation result:

```python
result = GitOperationResult.create_success(
    commit_sha="abc123",
    branch="main",
    manifest_path="k8s/cluster/app/deployment.yaml",
    modifications=3,  # Additional metadata
)
```

**Usage**: Returned when both commit and push operations complete successfully.

### `create_failure()`

Create a failed operation result:

```python
result = GitOperationResult.create_failure(
    manifest_path="k8s/cluster/app/deployment.yaml",
    error="Authentication failed: Invalid credentials",
    operation="push",  # Additional metadata
)
```

**Usage**: Returned when an operation fails before making persistent changes. The repository is left in a clean state.

### `create_partial()`

Create a partial success result:

```python
result = GitOperationResult.create_partial(
    commit_sha="abc123",
    manifest_path="k8s/cluster/app/deployment.yaml",
    error="Network timeout during push",
    commit_locally=True,
)
```

**Usage**: Returned when the local commit succeeds but a subsequent operation (typically push) fails. The commit SHA is preserved for recovery/retry.

## Property Accessors

### `success` (boolean)

```python
if result.success:
    # Operation completed successfully
    logger.info(f"Committed {result.commit_sha}")
```

Returns `True` only when `status == GitOperationStatus.SUCCESS`.

### `data` (dictionary)

```python
payload = result.data
# Returns:
# {
#     "commit_sha": "abc123",
#     "branch": "main",
#     "manifest_path": "k8s/cluster/app/deployment.yaml",
#     "status": "success",
#     **other_details,
# }
```

Exposes structured fields through the legacy step-result interface for backward compatibility.

### `to_dict()` (dictionary)

```python
serialized = result.to_dict()
# Returns complete result including error field
```

Serializes the full result for action/executor boundaries. Includes all fields from `data` plus the `error` field.

## Cleanup Guarantees

The GitOps operations provide automatic cleanup through the `GitStateCleanup` context manager. This ensures that:

1. **Merge conflicts are cleaned up** on failure
2. **Original branch is restored** if switched
3. **Temporary branches are deleted** if created
4. **Manifest changes are rolled back** on commit failure

### Cleanup Manager Usage

```python
with GitStateCleanup(
    repo_path=declarative_config_path,
    cleanup_branches=False,        # We're on main, not creating temp branches
    cleanup_merge_state=True,     # Clean up merge conflicts on failure
    return_to_original_branch=True,  # Return to main if somehow switched
    timeout=30,
) as cleanup_mgr:
    # Perform git operations
    # Automatic cleanup on exit (success or exception)
    pass
# Repository is guaranteed to be in a clean state here
```

### What Gets Cleaned Up

#### 1. Merge Conflicts

When a merge conflict occurs during operations, the cleanup manager automatically aborts the merge:

```python
# Before cleanup:
# $ git status
# UU k8s/cluster/app/deployment.yaml

# After cleanup (automatic):
# $ git status
# (clean state)
```

#### 2. Branch Restoration

If an operation switches branches and fails, the cleanup manager returns to the original branch:

```python
# Original branch: main
# Operation switches to: test-branch
# Operation fails

# After cleanup (automatic):
# $ git branch --show-current
# main
```

#### 3. Manifest Rollback

If a commit fails after modifying the manifest, the original content is restored:

```python
# Operation modifies deployment.yaml
# Commit fails (conflict, auth error, etc.)

# After rollback (automatic):
# $ deployment.yaml contains original content
```

### Cleanup State Validation

The cleanup manager validates its own work by capturing state before and after cleanup:

```python
# State captured before cleanup:
cleanup_state_before = {
    "current_branch": "main",
    "conflict_files": ["deployment.yaml"],
    "branches": {},
}

# Cleanup operations run...

# State captured after cleanup:
cleanup_state_after = {
    "current_branch": "main",  # ✅ Still on main
    "conflict_files": [],      # ✅ Conflicts resolved
    "branches": {},
}

# Validation passes if post-cleanup state matches expectations
```

If cleanup fails to reach the desired state, a `GitCleanupError` is raised with detailed context:

```python
GitCleanupError: Git cleanup incomplete for /path/to/repo: \
    merge conflict cleanup (deployment.yaml): conflicts remain after cleanup; \
    return to original branch (main): post-cleanup branch is 'test-branch'
```

## Error Handling Examples

### Example 1: Authentication Failure

```python
result = await gitops_step.execute(
    manifest_path="k8s/cluster/app/deployment.yaml",
    template_fields=[{"path": "/spec/replicas", "value": 3}],
    project_cfg={"project_slug": "app", "cluster": "prod"},
)

# Result:
GitOperationResult(
    commit_sha=None,
    branch=None,
    manifest_path="k8s/cluster/app/deployment.yaml",
    status=GitOperationStatus.FAILED,
    error="Git authentication failed: Invalid credentials",
    details={},
)

# Repository state: CLEAN (no changes made)
# Cleanup: No cleanup needed (no modifications)
```

### Example 2: Network Timeout During Push (Partial Success)

```python
result = await gitops_step.execute(
    manifest_path="k8s/cluster/app/deployment.yaml",
    template_fields=[{"path": "/spec/replicas", "value": 3}],
    project_cfg={"project_slug": "app", "cluster": "prod"},
)

# Result:
GitOperationResult(
    commit_sha="abc123",
    branch=None,
    manifest_path="k8s/cluster/app/deployment.yaml",
    status=GitOperationStatus.PARTIAL,
    error="Network timeout during git push",
    details={"commit_locally": True},
)

# Repository state: COMMITTED LOCALLY (commit abc123 exists, not pushed)
# Cleanup: Merge state cleaned up, commit SHA preserved for retry
# Recovery: Retry push, or push commit_sha manually
```

### Example 3: Merge Conflict During Commit

```python
result = await gitops_step.execute(
    manifest_path="k8s/cluster/app/deployment.yaml",
    template_fields=[{"path": "/spec/replicas", "value": 3}],
    project_cfg={"project_slug": "app", "cluster": "prod"},
)

# Result:
GitOperationResult(
    commit_sha=None,
    branch=None,
    manifest_path="k8s/cluster/app/deployment.yaml",
    status=GitOperationStatus.FAILED,
    error="Merge conflict detected: deployment.yaml has conflicts",
    details={"conflict_files": ["deployment.yaml"]},
)

# Repository state: CLEAN (manifest rolled back, merge aborted)
# Cleanup: 
#   - Manifest restored to original content
#   - Merge conflict state aborted
#   - No partial commit left behind
```

### Example 4: Success Path

```python
result = await gitops_step.execute(
    manifest_path="k8s/cluster/app/deployment.yaml",
    template_fields=[{"path": "/spec/replicas", "value": 3}],
    project_cfg={"project_slug": "app", "cluster": "prod"},
)

# Result:
GitOperationResult(
    commit_sha="abc123",
    branch="main",
    manifest_path="k8s/cluster/app/deployment.yaml",
    status=GitOperationStatus.SUCCESS,
    error=None,
    details={"modifications": 1},
)

# Repository state: COMMITTED AND PUSHED (abc123 on origin/main)
# Cleanup: No cleanup needed (operation succeeded)
```

## Rollback Behavior

The `rollback()` method provides atomic rollback of a commit:

### Rollback Guarantees

1. **Atomic writes**: Manifest content is restored atomically (no partial writes)
2. **Separate stage and commit**: Staging is separate from file publication to allow rollback
3. **Failure recovery**: If the rollback commit fails, the original manifest is restored
4. **Cleanup on failure**: Merge state is cleaned up if the rollback fails

### Rollback Example

```python
result = await gitops_step.rollback(
    manifest_path="k8s/cluster/app/deployment.yaml",
    commit_sha="abc123",
)

# Success result:
GitOperationResult(
    commit_sha="abc123",
    branch="main",
    manifest_path="k8s/cluster/app/deployment.yaml",
    status=GitOperationStatus.SUCCESS,
    error=None,
    details={"reverted_commit": "abc123"},
)

# Failure result (if git operations fail):
GitOperationResult(
    commit_sha=None,
    branch=None,
    manifest_path="k8s/cluster/app/deployment.yaml",
    status=GitOperationStatus.FAILED,
    error="Rollback failed: Could not read parent commit",
    details={"commit_sha": "abc123"},
)

# Repository state after failed rollback:
# - Manifest restored to original content (atomic)
# - No partial revert committed
# - Cleanup run on exit
```

## Best Practices

### 1. Always Check Status

```python
result = await gitops_step.execute(...)

if result.status == GitOperationStatus.SUCCESS:
    logger.info(f"Committed {result.commit_sha}")
elif result.status == GitOperationStatus.PARTIAL:
    # Local commit succeeded, push failed
    logger.warning(f"Commit {result.commit_sha} created locally, push failed: {result.error}")
    # Retry or manual recovery
else:
    # Complete failure
    logger.error(f"Git operation failed: {result.error}")
```

### 2. Use Partial Results for Recovery

```python
if result.status == GitOperationStatus.PARTIAL:
    # We have a local commit that didn't push
    commit_sha = result.commit_sha

    # Option 1: Retry the push
    await retry_push(commit_sha)

    # Option 2: Inform user for manual recovery
    logger.info(f"Manual recovery needed: git push origin {commit_sha}")
```

### 3. Trust Cleanup Guarantees

```python
# Don't add manual cleanup code
# ❌ BAD:
try:
    result = await gitops_step.execute(...)
except Exception as e:
    # Manual cleanup is redundant and error-prone
    subprocess.run(["git", "merge", "--abort"])
    subprocess.run(["git", "checkout", "main"])
    raise

# ✅ GOOD:
# Cleanup is automatic - just handle the result
result = await gitops_step.execute(...)
if not result.success:
    logger.error(f"Operation failed: {result.error}")
    # Repository is already clean
```

### 4. Serialize Results for Logging

```python
result = await gitops_step.execute(...)
logger.info(f"Git operation result: {json.dumps(result.to_dict())}")

# Output:
# {
#     "commit_sha": "abc123",
#     "branch": "main",
#     "manifest_path": "k8s/cluster/app/deployment.yaml",
#     "status": "success",
#     "error": null,
#     "modifications": 3
# }
```

## Testing

See the comprehensive test suites for validation:

- **`tests/test_git_operation_result.py`**: Result creation and field validation
- **`tests/test_cleanup_rollback_comprehensive.py`**: Cleanup and rollback behavior
- **`tests/test_git_operation_result.py`**: Integration tests with GitOpsCommitStep

## Related Documentation

- **`docs/atomic_write_guide.md`**: Atomic write operations for file safety
- **`src/action/steps/gitops.py`**: Implementation of GitOps operations
- **`src/utils/git_cleanup.py`**: Cleanup implementation details
