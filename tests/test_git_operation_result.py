"""Tests for structured GitOps operation results."""

from dataclasses import fields, is_dataclass

import pytest

from src.action.steps.gitops import GitOperationResult


def test_git_operation_result_has_structured_git_metadata() -> None:
    """A successful result exposes every field needed for operation tracking."""
    result = GitOperationResult(
        commit_sha="abc123",
        branch="main",
        manifest_path="k8s/test-cluster/deployment.yaml",
        status="success",
    )

    assert is_dataclass(result)
    assert {field.name for field in fields(result)} >= {
        "commit_sha",
        "branch",
        "manifest_path",
        "status",
    }
    assert result.commit_sha == "abc123"
    assert result.branch == "main"
    assert result.manifest_path == "k8s/test-cluster/deployment.yaml"
    assert result.status.value == "success"
    assert result.success is True

    payload = result.to_dict()
    assert payload["commit_sha"] == "abc123"
    assert payload["branch"] == "main"
    assert payload["manifest_path"] == "k8s/test-cluster/deployment.yaml"
    assert payload["status"] == "success"


@pytest.mark.parametrize(
    ("status", "success"),
    [("failed", False), ("partial", False)],
)
def test_git_operation_result_represents_incomplete_operations(
    status: str,
    success: bool,
) -> None:
    """Failed and partial operations retain their metadata and error."""
    result = GitOperationResult(
        commit_sha="abc123" if status == "partial" else None,
        branch="main",
        manifest_path="deployment.yaml",
        status=status,  # type: ignore[arg-type]
        error="push failed",
        details={"commit_locally": status == "partial"},
    )

    assert result.status.value == status
    assert result.success is success
    assert result.data["commit_locally"] is (status == "partial")
    assert result.to_dict()["error"] == "push failed"


def test_git_operation_result_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="Unsupported Git operation status"):
        GitOperationResult(status="unknown")  # type: ignore[arg-type]


def test_git_operation_result_success_helper() -> None:
    """The create_success() helper creates a successful result with all required metadata."""
    result = GitOperationResult.create_success(
        commit_sha="abc123",
        branch="main",
        manifest_path="k8s/test/deployment.yaml",
        commit_count=1,
    )

    assert result.status.value == "success"
    assert result.commit_sha == "abc123"
    assert result.branch == "main"
    assert result.manifest_path == "k8s/test/deployment.yaml"
    assert result.success is True
    assert result.error is None
    assert result.details["commit_count"] == 1
    assert result.to_dict()["commit_count"] == 1


def test_git_operation_result_failure_helper() -> None:
    """The create_failure() helper creates a failed result with error details."""
    result = GitOperationResult.create_failure(
        manifest_path="k8s/test/deployment.yaml",
        error="Authentication failed",
        attempt=3,
    )

    assert result.status.value == "failed"
    assert result.commit_sha is None
    assert result.branch is None
    assert result.manifest_path == "k8s/test/deployment.yaml"
    assert result.success is False
    assert result.error == "Authentication failed"
    assert result.details["attempt"] == 3
    assert result.to_dict()["error"] == "Authentication failed"


def test_git_operation_result_partial_helper() -> None:
    """The create_partial() helper creates a partial result for commits that couldn't push."""
    result = GitOperationResult.create_partial(
        commit_sha="abc123",
        manifest_path="k8s/test/deployment.yaml",
        error="Network timeout during push",
        retryable=True,
    )

    assert result.status.value == "partial"
    assert result.commit_sha == "abc123"
    assert result.branch is None
    assert result.manifest_path == "k8s/test/deployment.yaml"
    assert result.success is False
    assert result.error == "Network timeout during push"
    assert result.details["retryable"] is True
    assert result.to_dict()["error"] == "Network timeout during push"


def test_git_operation_result_partial_without_optional_args() -> None:
    """The create_partial() helper works with minimal required arguments."""
    result = GitOperationResult.create_partial(commit_sha="abc123")

    assert result.status.value == "partial"
    assert result.commit_sha == "abc123"
    assert result.manifest_path is None
    assert result.error is None
    # Partial results always include commit_locally: True since the local commit succeeded
    assert result.details == {"commit_locally": True}
