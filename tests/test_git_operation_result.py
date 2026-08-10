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
    assert result.status == "success"
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

    assert result.status == status
    assert result.success is success
    assert result.data["commit_locally"] is (status == "partial")
    assert result.to_dict()["error"] == "push failed"


def test_git_operation_result_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="Unsupported Git operation status"):
        GitOperationResult(status="unknown")  # type: ignore[arg-type]
