# GitOperationResult Structure

This document describes the structured result format returned by GitOps operations in aide-de-camp.

## Overview

`GitOperationResult` is a structured dataclass that provides comprehensive outcome information for GitOps operations. It ensures that all operations return consistent, predictable results that include success status, metadata, and error information.

## Structure

```python
@dataclass
class GitOperationResult:
    """Structured outcome of a GitOps operation."""
    
    commit_sha: str | None = None        # Git commit SHA if operation created/committed changes
    branch: str | None = None            # Branch name (typically "main")
    manifest_path: str | None = None     # Path to the manifest file within declarative-config
    status: GitOperationStatus = "failed" # Operation outcome: "success", "failed", or "partial"
    error: str | None = None             # Error message if operation failed
    details: dict[str, Any]             # Additional operation-specific metadata
```

## Status Values

### `success`
Operation completed successfully. All requested changes were committed and pushed to origin.

**Example:**
```python
GitOperationResult(
    commit_sha="abc123def456",
    branch="main",
    manifest_path="k8s/ardenone-cluster/botburrow/deployment.yaml",
    status="success",
    details={"modifications": 2}
)
```

### `failed`
Operation failed completely. No changes were committed or pushed.

**Example:**
```python
GitOperationResult(
    commit_sha=None,
    branch="main",
    manifest_path="k8s/test-cluster/deployment.yaml",
    status="failed",
    error="Manifest file not found: /path/to/manifest.yaml"
)
```

### `partial`
Local commit succeeded but a later operation (typically push) failed. The commit SHA is retained to allow recovery or retry without losing the local change.

**Example:**
```python
GitOperationResult(
    commit_sha="abc123def456",
    branch="main",
    manifest_path="k8s/test-cluster/deployment.yaml",
    status="partial",
    error="Failed to push changes: network timeout",
    details={"commit_locally": True}
)
```

## Accessor Methods

### `success: bool`
Returns `True` if status is `"success"`, `False` otherwise.

```python
result = GitOperationResult(status="success", ...)
assert result.success is True

failed_result = GitOperationResult(status="failed", ...)
assert failed_result.success is False
```

### `data: dict[str, Any]`
Returns structured fields through the legacy result payload interface.

```python
result = GitOperationResult(
    commit_sha="abc123",
    branch="main",
    manifest_path="deployment.yaml",
    status="success"
)

payload = result.data
# {
#     "commit_sha": "abc123",
#     "branch": "main",
#     "manifest_path": "deployment.yaml",
#     "status": "success"
# }
```

### `to_dict() -> dict[str, Any]`
Serializes the result for action/executor boundaries, including error information.

```python
result = GitOperationResult(
    commit_sha="abc123",
    status="partial",
    error="Network timeout during push"
)

serialized = result.to_dict()
# {
#     "commit_sha": "abc123",
#     "branch": "main",
#     "manifest_path": None,
#     "status": "partial",
#     "error": "Network timeout during push"
# }
```

## Usage Patterns

### Checking Operation Success

```python
result = await gitops_step.execute(
    manifest_path="k8s/cluster/deployment.yaml",
    template_fields=[...],
    project_cfg={...}
)

if result.success:
    logger.info(f"Operation succeeded: {result.commit_sha}")
else:
    logger.error(f"Operation failed: {result.error}")
```

### Handling Partial Success

```python
result = await gitops_step.execute(...)

if result.status == "partial":
    # Local commit succeeded but push failed
    # Can retry push or notify user
    logger.warning(
        f"Local commit {result.commit_sha} succeeded but push failed: "
        f"{result.error}"
    )
    # Implement retry logic or manual intervention
```

### Extracting Metadata

```python
result = await gitops_step.execute(...)

# Access structured fields
commit_info = {
    "sha": result.commit_sha,
    "branch": result.branch,
    "manifest": result.manifest_path,
    "modifications": result.details.get("modifications", 0)
}
```

## Error Handling

### Validation

The result validates that status is one of the allowed values:

```python
# This raises ValueError
invalid_result = GitOperationResult(status="unknown")
# ValueError: Unsupported Git operation status: unknown
```

### Error Information

Error information is always preserved in the result:

```python
result = GitOperationResult(
    status="failed",
    error="Authentication failed: invalid credentials"
)

# Error is accessible via multiple interfaces
assert result.error == "Authentication failed: invalid credentials"
assert result.to_dict()["error"] == "Authentication failed: invalid credentials"
```

## Integration with Cleanup

`GitOperationResult` is designed to work seamlessly with cleanup operations:

1. **On Success**: Result contains commit SHA and manifest path for verification
2. **On Failure**: Result contains error details and cleanup has already run
3. **On Partial**: Result contains local commit SHA for recovery, cleanup has preserved git state

```python
with GitStateCleanup(repo_path=repo) as cleanup:
    result = await gitops_step.execute(...)
    
    if result.success:
        # Cleanup runs automatically on context exit
        logger.info(f"Committed {result.commit_sha}")
    else:
        # Cleanup has already rolled back partial changes
        logger.error(f"Failed: {result.error}")
        # Repository is in clean state
```

## Testing

### Example Test

```python
def test_git_operation_result_success():
    """Test successful operation result structure."""
    result = GitOperationResult(
        commit_sha="abc123",
        branch="main",
        manifest_path="k8s/test/deployment.yaml",
        status="success"
    )
    
    assert result.success is True
    assert result.commit_sha == "abc123"
    assert result.branch == "main"
    assert result.manifest_path == "k8s/test/deployment.yaml"
    
    serialized = result.to_dict()
    assert serialized["commit_sha"] == "abc123"
    assert serialized["status"] == "success"

def test_git_operation_result_partial_with_commit():
    """Test partial result preserves local commit for recovery."""
    result = GitOperationResult(
        commit_sha="abc123",
        branch="main",
        manifest_path="deployment.yaml",
        status="partial",
        error="Push failed: network timeout"
    )
    
    assert result.success is False
    assert result.commit_sha == "abc123"  # Local commit preserved
    assert result.status == "partial"
    assert result.error is not None
```

## Related Documentation

- [Cleanup Operations Reference](cleanup-operations-reference.md) - Detailed cleanup patterns and guarantees
- [Atomic Write Guide](atomic_write_guide.md) - File operation guarantees and rollback behavior
- `src/action/steps/gitops.py` - Implementation of GitOps step with cleanup
- `tests/test_git_operation_result.py` - Comprehensive test coverage
