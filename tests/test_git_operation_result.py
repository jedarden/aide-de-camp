"""
Comprehensive tests for GitOperationResult creation and integration.

Tests cover:
- Creation for all status types (SUCCESS, FAILED, PARTIAL)
- Metadata correctness
- Integration: operation failure → rollback → clean state
- End-to-end cleanup and state management
"""

from dataclasses import fields, is_dataclass
from enum import Enum
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import shutil
import pytest

from src.action.steps.gitops import (
    GitOperationStatus,
    GitOperationResult,
    GitOpsCommitStep,
)


class TestGitOperationResultCreation:
    """Test GitOperationResult creation for all status types."""

    @pytest.mark.parametrize(
        ("status", "commit_sha", "branch", "manifest_path"),
        [
            (GitOperationStatus.SUCCESS, "abc123", "main", "k8s/test/deployment.yaml"),
            (GitOperationStatus.FAILED, None, None, "k8s/test/deployment.yaml"),
            (GitOperationStatus.PARTIAL, "def456", None, "k8s/test/deployment.yaml"),
        ],
    )
    def test_create_result_for_all_status_types(
        self,
        status: GitOperationStatus,
        commit_sha: str | None,
        branch: str | None,
        manifest_path: str,
    ) -> None:
        """Test result creation for all supported status types."""
        result = GitOperationResult(
            commit_sha=commit_sha,
            branch=branch,
            manifest_path=manifest_path,
            status=status,
            error="test error" if status != GitOperationStatus.SUCCESS else None,
            details={"key": "value"},
        )

        assert is_dataclass(result)
        assert result.status == status
        assert result.commit_sha == commit_sha
        assert result.branch == branch
        assert result.manifest_path == manifest_path
        assert (result.error == "test error") is (status != GitOperationStatus.SUCCESS)
        assert result.details == {"key": "value"}

    def test_create_success_with_all_metadata(self) -> None:
        """Test create_success class method includes all metadata."""
        result = GitOperationResult.create_success(
            commit_sha="abc123",
            branch="main",
            manifest_path="k8s/test/deployment.yaml",
            modifications=3,
            operation_type="update",
        )

        assert result.status == GitOperationStatus.SUCCESS
        assert result.commit_sha == "abc123"
        assert result.branch == "main"
        assert result.manifest_path == "k8s/test/deployment.yaml"
        assert result.success is True
        assert result.details["modifications"] == 3
        assert result.details["operation_type"] == "update"

    def test_create_failure_with_all_metadata(self) -> None:
        """Test create_failure class method includes error and details."""
        result = GitOperationResult.create_failure(
            manifest_path="k8s/test/deployment.yaml",
            error="commit failed",
            stage="commit",
            retry_count=3,
        )

        assert result.status == GitOperationStatus.FAILED
        assert result.commit_sha is None
        assert result.branch is None
        assert result.manifest_path == "k8s/test/deployment.yaml"
        assert result.success is False
        assert result.error == "commit failed"
        assert result.details["stage"] == "commit"
        assert result.details["retry_count"] == 3

    def test_create_partial_with_all_metadata(self) -> None:
        """Test create_partial class method includes commit and error."""
        result = GitOperationResult.create_partial(
            commit_sha="abc123",
            manifest_path="k8s/test/deployment.yaml",
            error="push failed",
            commit_locally=True,
            operation="push",
        )

        assert result.status == GitOperationStatus.PARTIAL
        assert result.commit_sha == "abc123"
        assert result.branch is None
        assert result.manifest_path == "k8s/test/deployment.yaml"
        assert result.success is False
        assert result.error == "push failed"
        assert result.details["commit_locally"] is True
        assert result.details["operation"] == "push"

    def test_result_carries_correct_metadata(self) -> None:
        """Test that result objects carry complete metadata."""
        result = GitOperationResult.create_success(
            commit_sha="abc123",
            branch="main",
            manifest_path="k8s/test/deployment.yaml",
            field1="value1",
            field2=42,
            field3={"nested": "data"},
        )

        # Check all fields are present
        payload = result.to_dict()
        assert payload["commit_sha"] == "abc123"
        assert payload["branch"] == "main"
        assert payload["manifest_path"] == "k8s/test/deployment.yaml"
        assert payload["status"] == "success"
        assert payload["field1"] == "value1"
        assert payload["field2"] == 42
        assert payload["field3"] == {"nested": "data"}

        # Check data property includes everything
        assert result.data["commit_sha"] == "abc123"
        assert result.data["field1"] == "value1"
        assert result.data["field2"] == 42
        assert result.data["field3"] == {"nested": "data"}

    def test_success_property_returns_correctly(self) -> None:
        """Test the success property for all status types."""
        success_result = GitOperationResult.create_success(
            commit_sha="abc123",
            branch="main",
            manifest_path="test.yaml",
        )
        assert success_result.success is True

        failed_result = GitOperationResult.create_failure(
            manifest_path="test.yaml",
            error="failed",
        )
        assert failed_result.success is False

        partial_result = GitOperationResult.create_partial(
            commit_sha="abc123",
            manifest_path="test.yaml",
            error="partial",
        )
        assert partial_result.success is False

    def test_string_status_converted_to_enum(self) -> None:
        """Test that string status values are converted to enum in __post_init__."""
        result = GitOperationResult(
            commit_sha="abc123",
            branch="main",
            manifest_path="test.yaml",
            status="success",  # String instead of enum
        )
        assert isinstance(result.status, GitOperationStatus)
        assert result.status == GitOperationStatus.SUCCESS

    def test_invalid_status_raises_value_error(self) -> None:
        """Test that invalid status values raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported Git operation status"):
            GitOperationResult(
                commit_sha="abc123",
                branch="main",
                manifest_path="test.yaml",
                status="invalid_status",  # Invalid status
            )


class TestGitOperationResultIntegration:
    """Test integration scenarios: failure → rollback → clean state."""

    @pytest.fixture
    def temp_repo(self) -> Path:
        """Create a temporary git repository for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        repo_path = temp_dir / "declarative-config"
        repo_path.mkdir(parents=True)

        # Initialize git repo
        import subprocess
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create initial commit
        (repo_path / "README.md").write_text("test")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        yield repo_path

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def gitops_step(self, temp_repo: Path) -> GitOpsCommitStep:
        """Create GitOpsCommitStep instance with temp repo."""
        return GitOpsCommitStep(
            declarative_config_path=str(temp_repo),
            timeout=10,
        )

    def test_full_operation_failure_creates_failed_result(self, gitops_step: GitOpsCommitStep) -> None:
        """Test that a full operation failure creates a FAILED result."""
        result = GitOperationResult.create_failure(
            manifest_path="k8s/test/deployment.yaml",
            error="commit failed",
            stage="commit",
        )

        assert result.status == GitOperationStatus.FAILED
        assert result.success is False
        assert result.commit_sha is None
        assert result.error == "commit failed"
        assert result.details["stage"] == "commit"

    def test_partial_operation_creates_partial_result(self) -> None:
        """Test that operation with local commit but push failure creates PARTIAL result."""
        result = GitOperationResult.create_partial(
            commit_sha="abc123",
            manifest_path="k8s/test/deployment.yaml",
            error="push failed - network error",
            commit_locally=True,
        )

        assert result.status == GitOperationStatus.PARTIAL
        assert result.success is False
        assert result.commit_sha == "abc123"
        assert result.error == "push failed - network error"
        assert result.details["commit_locally"] is True

    def test_successful_operation_creates_success_result(self) -> None:
        """Test that successful operation creates SUCCESS result."""
        result = GitOperationResult.create_success(
            commit_sha="abc123",
            branch="main",
            manifest_path="k8s/test/deployment.yaml",
            modifications=2,
        )

        assert result.status == GitOperationStatus.SUCCESS
        assert result.success is True
        assert result.commit_sha == "abc123"
        assert result.branch == "main"
        assert result.details["modifications"] == 2

    @pytest.mark.asyncio
    async def test_rollback_operation_creates_success_result(self, gitops_step: GitOpsCommitStep, temp_repo: Path) -> None:
        """Test that successful rollback creates SUCCESS result."""
        # Create a manifest file
        manifest_path = "k8s/test/deployment.yaml"
        manifest_file = temp_repo / manifest_path
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text("original content")

        # Commit the manifest
        import subprocess
        subprocess.run(
            ["git", "add", manifest_path],
            cwd=str(temp_repo),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add manifest"],
            cwd=str(temp_repo),
            capture_output=True,
            check=True,
        )

        # Modify the manifest
        manifest_file.write_text("modified content")
        subprocess.run(
            ["git", "add", manifest_path],
            cwd=str(temp_repo),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Modify manifest"],
            cwd=str(temp_repo),
            capture_output=True,
            check=True,
        )
        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(temp_repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Perform rollback with mocked validation and push
        with patch.object(gitops_step, "_validate_declarative_config_repo"), \
             patch.object(gitops_step, "_push_changes", return_value=GitOperationResult.create_success(
                 commit_sha="revert_sha",
                 branch="main",
                 manifest_path=manifest_path,
             )):
            rollback_result = await gitops_step.rollback(manifest_path, commit_sha)

        assert rollback_result.status == GitOperationStatus.SUCCESS
        assert rollback_result.success is True
        assert rollback_result.commit_sha == commit_sha
        assert rollback_result.details["reverted_commit"] == commit_sha

    @pytest.mark.asyncio
    async def test_rollback_failure_creates_failed_result(self, gitops_step: GitOpsCommitStep, temp_repo: Path) -> None:
        """Test that failed rollback creates FAILED result."""
        from src.action.steps.git_validation import GitStateError

        manifest_path = "k8s/test/deployment.yaml"

        # Test rollback failure before commit - use correct exception type
        with patch.object(
            gitops_step,
            "_validate_declarative_config_repo",
            side_effect=GitStateError("Repository validation failed"),
        ):
            result = await gitops_step.rollback(manifest_path, "abc123")

        assert result.status == GitOperationStatus.FAILED
        assert result.success is False
        assert result.error is not None
        assert "Repository validation failed" in result.error

    def test_result_to_dict_serialization(self) -> None:
        """Test that results serialize correctly for transport."""
        result = GitOperationResult.create_success(
            commit_sha="abc123",
            branch="main",
            manifest_path="k8s/test/deployment.yaml",
            custom_field="custom_value",
        )

        serialized = result.to_dict()
        assert serialized == {
            "commit_sha": "abc123",
            "branch": "main",
            "manifest_path": "k8s/test/deployment.yaml",
            "status": "success",
            "custom_field": "custom_value",
            "error": None,
        }

    def test_data_property_for_all_status_types(self) -> None:
        """Test that data property works correctly for all status types."""
        success = GitOperationResult.create_success(
            commit_sha="abc123",
            branch="main",
            manifest_path="test.yaml",
            key1="val1",
        )
        assert success.data["commit_sha"] == "abc123"
        assert success.data["status"] == "success"
        assert success.data["key1"] == "val1"

        failed = GitOperationResult.create_failure(
            manifest_path="test.yaml",
            error="failed",
            key2="val2",
        )
        assert failed.data["commit_sha"] is None
        assert failed.data["status"] == "failed"
        assert failed.data["key2"] == "val2"

        partial = GitOperationResult.create_partial(
            commit_sha="abc123",
            manifest_path="test.yaml",
            error="partial",
            key3="val3",
        )
        assert partial.data["commit_sha"] == "abc123"
        assert partial.data["status"] == "partial"
        assert partial.data["key3"] == "val3"

    @pytest.mark.asyncio
    async def test_cleanup_and_state_management(self, gitops_step: GitOpsCommitStep, temp_repo: Path) -> None:
        """Test that operations leave clean state after rollback."""
        from src.utils.git_cleanup import GitStateCleanup

        manifest_path = "k8s/test/deployment.yaml"
        manifest_file = temp_repo / manifest_path
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        original_content = "original content"
        manifest_file.write_text(original_content)

        # Commit original
        import subprocess
        subprocess.run(
            ["git", "add", manifest_path],
            cwd=str(temp_repo),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Original"],
            cwd=str(temp_repo),
            capture_output=True,
            check=True,
        )

        # Modify and commit
        manifest_file.write_text("modified content")
        subprocess.run(
            ["git", "add", manifest_path],
            cwd=str(temp_repo),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Modified"],
            cwd=str(temp_repo),
            capture_output=True,
            check=True,
        )

        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(temp_repo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Perform rollback with mocked validation and push
        with patch.object(gitops_step, "_validate_declarative_config_repo"), \
             patch.object(gitops_step, "_push_changes", return_value=GitOperationResult.create_success(
                 commit_sha="revert_sha",
                 branch="main",
                 manifest_path=manifest_path,
             )):
            rollback_result = await gitops_step.rollback(manifest_path, commit_sha)

        assert rollback_result.success is True

        # Verify clean state: no uncommitted changes
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(temp_repo),
            capture_output=True,
            text=True,
            check=True,
        )
        assert not status_result.stdout.strip(), "Repository should have no uncommitted changes"

        # Verify content was restored
        current_content = manifest_file.read_text()
        assert current_content == original_content, "Content should be restored to original"


class TestResultMetadataCarry:
    """Test that result objects carry correct metadata through operations."""

    def test_success_metadata_preserved(self) -> None:
        """Test that success result preserves all metadata."""
        result = GitOperationResult.create_success(
            commit_sha="abc123",
            branch="main",
            manifest_path="k8s/test/deployment.yaml",
            field1="value1",
            field2=42,
            field3=["list", "of", "values"],
            field4={"nested": "dict"},
        )

        payload = result.to_dict()
        assert payload["commit_sha"] == "abc123"
        assert payload["branch"] == "main"
        assert payload["manifest_path"] == "k8s/test/deployment.yaml"
        assert payload["status"] == "success"
        assert payload["field1"] == "value1"
        assert payload["field2"] == 42
        assert payload["field3"] == ["list", "of", "values"]
        assert payload["field4"] == {"nested": "dict"}

    def test_failure_metadata_preserved(self) -> None:
        """Test that failure result preserves error and details."""
        result = GitOperationResult.create_failure(
            manifest_path="k8s/test/deployment.yaml",
            error="Authentication failed",
            stage="push",
            retry_count=3,
            last_error="timeout",
        )

        payload = result.to_dict()
        assert payload["status"] == "failed"
        assert payload["commit_sha"] is None
        assert payload["branch"] is None
        assert payload["error"] == "Authentication failed"
        assert payload["stage"] == "push"
        assert payload["retry_count"] == 3
        assert payload["last_error"] == "timeout"

    def test_partial_metadata_preserved(self) -> None:
        """Test that partial result preserves commit SHA and error."""
        result = GitOperationResult.create_partial(
            commit_sha="abc123",
            manifest_path="k8s/test/deployment.yaml",
            error="Network timeout during push",
            commit_locally=True,
            operation="push",
            remote_url="https://github.com/test/repo.git",
        )

        payload = result.to_dict()
        assert payload["status"] == "partial"
        assert payload["commit_sha"] == "abc123"
        assert payload["error"] == "Network timeout during push"
        assert payload["commit_locally"] is True
        assert payload["operation"] == "push"
        assert payload["remote_url"] == "https://github.com/test/repo.git"
