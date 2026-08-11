"""
Comprehensive tests for cleanup and rollback scenarios.

This test suite verifies:
1. Rollback on partial write failure
2. Atomic write with concurrent access
3. Cleanup of temp files after exception
4. GitOperationResult creation for all status types
5. Integration: full operation failure → rollback → clean state

Test Strategy:
- Use pytest fixtures for setup/teardown
- Verify repo is clean after failure scenarios
- Test concurrent access with proper locking
- Validate cleanup of all temporary artifacts
"""

import asyncio
import os
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.action.steps.gitops import (
    GitOperationResult,
    GitOperationStatus,
    GitOpsCommitStep,
)
from src.action.steps.git_validation import (
    GitConflictError,
    GitStateError,
    GitNetworkError,
)
from src.utils.atomic_write import (
    AtomicWriteRollbackError,
    atomic_write,
    atomic_write_rollback,
    cleanup_orphaned_temp_files,
)
from src.utils.git_cleanup import (
    GitCleanupError,
    GitStateCleanup,
    cleanup_all_temporary_state,
    cleanup_merge_state,
    cleanup_temporary_branches,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo with main as default branch
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Configure git identity
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
    test_file = repo_path / "test.txt"
    test_file.write_text("initial content")
    subprocess.run(
        ["git", "add", "test.txt"],
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


@pytest.fixture
def sample_manifest(tmp_path: Path) -> Path:
    """Create a sample YAML manifest for testing."""
    manifest_path = tmp_path / "deployment.yaml"
    manifest_data = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "test-app"},
        "spec": {
            "replicas": 3,
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "image": "app:v1.0.0",
                        }
                    ]
                }
            },
        },
    }
    manifest_path.write_text(yaml.dump(manifest_data))
    return manifest_path


@pytest.fixture
def declarative_config_repo(tmp_path: Path) -> Path:
    """Create a mock declarative-config repository structure."""
    config_path = tmp_path / "declarative-config"
    config_path.mkdir()

    # Initialize as git repo
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=config_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "github@jedarden.com"],
        cwd=config_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "jedarden"],
        cwd=config_path,
        capture_output=True,
        check=True,
    )

    # Create k8s directory structure
    k8s_path = config_path / "k8s" / "test-cluster" / "test-app"
    k8s_path.mkdir(parents=True)

    # Create deployment manifest
    deployment_data = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "test-app", "namespace": "default"},
        "spec": {
            "replicas": 2,
            "template": {
                "spec": {
                    "containers": [
                        {"name": "app", "image": "app:latest"}
                    ]
                }
            },
        },
    }
    deployment_path = k8s_path / "deployment.yaml"
    deployment_path.write_text(yaml.dump(deployment_data))

    # Initial commit
    subprocess.run(
        ["git", "add", "."],
        cwd=config_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=config_path,
        capture_output=True,
        check=True,
    )

    # Add a remote that matches the expected pattern
    subprocess.run(
        ["git", "remote", "add", "origin", "https://git.ardenone.com/jedarden/declarative-config.git"],
        cwd=config_path,
        capture_output=True,
        check=True,
    )

    yield config_path


# =============================================================================
# Test 1: Rollback on Partial Write Failure
# =============================================================================

class TestRollbackOnPartialWriteFailure:
    """Test rollback behavior when write operations fail partially."""

    @pytest.mark.asyncio
    async def test_rollback_manifest_after_commit_failure(
        self, declarative_config_repo: Path, caplog
    ):
        """Test that manifest is rolled back when commit fails."""
        step = GitOpsCommitStep(declarative_config_path=str(declarative_config_repo))

        manifest_path = "k8s/test-cluster/test-app/deployment.yaml"
        template_fields = [{"path": "/spec/replicas", "value": 5}]
        project_cfg = {"project_slug": "test-app", "cluster": "test-cluster"}

        # Mock commit to fail after manifest write
        original_content = (declarative_config_repo / manifest_path).read_text()

        # Create a proper function to handle different git commands
        def mock_subprocess_run(*args, **kwargs):
            """Mock subprocess.run to handle different git commands."""
            cmd_args = args[0] if args else []
            if "branch" in cmd_args and "--show-current" in cmd_args:
                return MagicMock(returncode=0, stdout="main", stderr="")
            elif "status" in cmd_args and "--porcelain" in cmd_args:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "add" in cmd_args:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "commit" in cmd_args:
                # Commit fails
                return MagicMock(returncode=1, stdout="", stderr="commit failed")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("src.action.steps.gitops.subprocess.run", side_effect=mock_subprocess_run):
            result = await step.execute(
                manifest_path=manifest_path,
                template_fields=template_fields,
                project_cfg=project_cfg,
            )

        assert result.success is False
        if result.error:
            assert "commit" in result.error.lower() or "branch" in result.error.lower()

        # Verify manifest was rolled back to original content
        current_content = (declarative_config_repo / manifest_path).read_text()
        assert current_content == original_content

    @pytest.mark.asyncio
    async def test_rollback_preserves_repo_state_on_error(
        self, declarative_config_repo: Path
    ):
        """Test that repository state is preserved after rollback."""
        step = GitOpsCommitStep(declarative_config_path=str(declarative_config_repo))

        manifest_path = "k8s/test-cluster/test-app/deployment.yaml"
        template_fields = [{"path": "/spec/replicas", "value": 5}]
        project_cfg = {"project_slug": "test-app", "cluster": "test-cluster"}

        # Get original git state
        original_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=declarative_config_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        with patch("src.action.steps.gitops.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=1, stdout="", stderr="commit failed"),
            ]

            result = await step.execute(
                manifest_path=manifest_path,
                template_fields=template_fields,
                project_cfg=project_cfg,
            )

        # Verify we're still on the original branch
        current_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=declarative_config_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        assert current_branch == original_branch
        assert result.success is False

    def test_rollback_cleanup_after_exception(self, tmp_path: Path):
        """Test that temp files are cleaned up after rollback exception."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")

        # Simulate write failure and rollback
        try:
            with atomic_write_rollback(test_file) as temp_path:
                temp_path.write_text("new content")
                # Simulate failure after write
                raise RuntimeError("Simulated failure after write")
        except RuntimeError:
            pass

        # Verify original file is preserved
        assert test_file.read_text() == "original"

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0


# =============================================================================
# Test 2: Atomic Write with Concurrent Access
# =============================================================================

class TestAtomicWriteConcurrentAccess:
    """Test atomic write operations under concurrent access."""

    def test_concurrent_writes_to_same_file(self, tmp_path: Path):
        """Test that concurrent writes to the same file are serialized."""
        test_file = tmp_path / "concurrent_test.txt"
        test_file.write_text("initial")

        num_writers = 10
        errors = []
        successful_writes = []

        def write_worker(worker_id: int) -> None:
            """Worker function that writes to the shared file."""
            try:
                content = f"worker-{worker_id}"
                atomic_write(test_file, content)
                successful_writes.append(worker_id)
            except Exception as e:
                errors.append((worker_id, e))

        # Run concurrent writes
        with ThreadPoolExecutor(max_workers=num_writers) as executor:
            futures = [
                executor.submit(write_worker, i) for i in range(num_writers)
            ]
            for future in as_completed(futures):
                future.result()

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all writes succeeded
        assert len(successful_writes) == num_writers

        # Verify file has complete content (not corrupted)
        final_content = test_file.read_text()
        assert final_content.startswith("worker-")
        assert len(final_content.split("-")) == 2

    def test_concurrent_reads_during_write(self, tmp_path: Path):
        """Test that reads during writes see consistent state."""
        test_file = tmp_path / "read_write_test.txt"
        original_content = "x" * 10000  # Large content
        test_file.write_text(original_content)

        num_operations = 20
        errors = []
        read_results = []

        def operation_worker(op_id: int) -> None:
            """Worker that performs both reads and writes."""
            try:
                if op_id % 2 == 0:
                    # Write operation
                    new_content = f"content-{op_id}" + "y" * 1000
                    atomic_write(test_file, new_content)
                else:
                    # Read operation
                    content = test_file.read_text()
                    read_results.append((op_id, len(content)))
            except Exception as e:
                errors.append((op_id, e))

        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=num_operations) as executor:
            futures = [
                executor.submit(operation_worker, i) for i in range(num_operations)
            ]
            for future in as_completed(futures):
                future.result()

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all reads returned valid content lengths
        assert len(read_results) > 0
        for op_id, length in read_results:
            assert length > 0, f"Read {op_id} returned empty content"

    def test_concurrent_writes_with_failures(self, tmp_path: Path):
        """Test that concurrent write failures are handled gracefully."""
        test_file = tmp_path / "failure_test.txt"
        test_file.write_text("initial")

        num_writers = 5
        errors = []

        def write_worker(worker_id: int) -> None:
            """Worker that writes, some will fail."""
            try:
                content = f"worker-{worker_id}"
                if worker_id % 2 == 0:
                    # Every other worker fails
                    raise IOError("Simulated write failure")
                atomic_write(test_file, content)
            except Exception as e:
                errors.append((worker_id, e))

        with ThreadPoolExecutor(max_workers=num_writers) as executor:
            futures = [
                executor.submit(write_worker, i) for i in range(num_writers)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass

        # Verify expected failures occurred (workers 0, 2, 4 should fail)
        assert len(errors) == 3
        failed_worker_ids = [worker_id for worker_id, _ in errors]
        assert failed_worker_ids == [0, 2, 4]

        # Verify file is not corrupted
        final_content = test_file.read_text()
        assert "worker-" in final_content or final_content == "initial"


# =============================================================================
# Test 3: Cleanup of Temp Files After Exception
# =============================================================================

class TestTempFileCleanup:
    """Test cleanup of temporary files after exceptions."""

    def test_cleanup_temp_files_after_write_error(self, tmp_path: Path):
        """Test that temp files are cleaned up after write error."""
        test_file = tmp_path / "cleanup_test.txt"

        # Mock a write error that leaves temp files
        with patch("src.utils.atomic_write.os.replace") as mock_replace:
            mock_replace.side_effect = OSError("Disk full")

            with pytest.raises(OSError):
                atomic_write(test_file, "content")

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0, f"Temp files remain: {temp_files}"

    def test_cleanup_orphaned_temp_files_on_startup(self, tmp_path: Path):
        """Test cleanup of orphaned temp files from previous runs."""
        # Create some orphaned temp files
        for i in range(5):
            temp_file = tmp_path / f"orphan_{i}.tmp"
            temp_file.write_text(f"orphan content {i}")

        # Create a non-temp file (should not be deleted)
        regular_file = tmp_path / "regular.txt"
        regular_file.write_text("regular content")

        # Cleanup orphaned temp files
        result = cleanup_orphaned_temp_files(tmp_path, pattern="*.tmp")

        # Verify temp files were cleaned up
        assert result >= 5

        # Verify regular file was not deleted
        assert regular_file.exists()
        assert regular_file.read_text() == "regular content"

    def test_cleanup_respects_missing_ok(self, tmp_path: Path):
        """Test that cleanup is idempotent when files are already deleted."""
        temp_file = tmp_path / "already_deleted.tmp"

        # File doesn't exist, cleanup should not fail
        result = cleanup_orphaned_temp_files(tmp_path, pattern="already_deleted*.tmp")

        # Should succeed even though file doesn't exist
        assert result == 0

    def test_atomic_write_rollback_cleanup_on_exception(self, tmp_path: Path):
        """Test that atomic_write_rollback cleans up on exception."""
        test_file = tmp_path / "rollback_test.txt"
        test_file.write_text("original")

        # Write and raise exception
        try:
            with atomic_write_rollback(test_file) as temp_path:
                temp_path.write_text("new content")
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Verify original file is unchanged
        assert test_file.read_text() == "original"

        # Verify no temp files remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0


# =============================================================================
# Test 4: GitOperationResult Creation for All Status Types
# =============================================================================

class TestGitOperationResultCreation:
    """Test GitOperationResult creation for all status types."""

    def test_create_success_result(self):
        """Test creating a SUCCESS status result."""
        result = GitOperationResult.create_success(
            commit_sha="abc123",
            branch="main",
            manifest_path="k8s/test/deployment.yaml",
            modifications=3,
        )

        assert result.status == GitOperationStatus.SUCCESS
        assert result.success is True
        assert result.commit_sha == "abc123"
        assert result.branch == "main"
        assert result.manifest_path == "k8s/test/deployment.yaml"
        assert result.error is None
        assert result.details["modifications"] == 3

    def test_create_failure_result(self):
        """Test creating a FAILED status result."""
        result = GitOperationResult.create_failure(
            manifest_path="k8s/test/deployment.yaml",
            error="Commit failed due to conflict",
            conflict_files=["deployment.yaml"],
        )

        assert result.status == GitOperationStatus.FAILED
        assert result.success is False
        assert result.commit_sha is None
        assert result.branch is None
        assert result.manifest_path == "k8s/test/deployment.yaml"
        assert "Commit failed" in result.error
        assert result.details["conflict_files"] == ["deployment.yaml"]

    def test_create_partial_result(self):
        """Test creating a PARTIAL status result."""
        result = GitOperationResult.create_partial(
            commit_sha="abc123",
            manifest_path="k8s/test/deployment.yaml",
            error="Push failed: network unreachable",
            commit_locally=True,
        )

        assert result.status == GitOperationStatus.PARTIAL
        assert result.success is False
        assert result.commit_sha == "abc123"
        assert result.branch is None  # Not set for partial
        assert result.manifest_path == "k8s/test/deployment.yaml"
        assert "Push failed" in result.error
        assert result.details["commit_locally"] is True

    def test_result_to_dict_serialization(self):
        """Test that to_dict() correctly serializes all fields."""
        result = GitOperationResult.create_success(
            commit_sha="def456",
            branch="main",
            manifest_path="k8s/prod/service.yaml",
            replicas=5,
            image_tag="v2.0",
        )

        serialized = result.to_dict()

        assert serialized["commit_sha"] == "def456"
        assert serialized["branch"] == "main"
        assert serialized["manifest_path"] == "k8s/prod/service.yaml"
        assert serialized["status"] == "success"
        assert serialized["replicas"] == 5
        assert serialized["image_tag"] == "v2.0"
        assert serialized["error"] is None

    def test_result_legacy_data_property(self):
        """Test that data property maintains legacy interface."""
        result = GitOperationResult.create_success(
            commit_sha="ghi789",
            branch="main",
            manifest_path="k8s/test/configmap.yaml",
        )

        data = result.data
        assert data["commit_sha"] == "ghi789"
        assert data["branch"] == "main"
        assert data["status"] == "success"
        assert data["manifest_path"] == "k8s/test/configmap.yaml"

    def test_result_status_enum_validation(self):
        """Test that invalid status strings are rejected."""
        with pytest.raises(ValueError, match="Unsupported Git operation status"):
            GitOperationResult(
                commit_sha="abc",
                branch="main",
                manifest_path="test.yaml",
                status="invalid_status",  # type: ignore
            )


# =============================================================================
# Test 5: Integration - Full Operation Failure → Rollback → Clean State
# =============================================================================

class TestFullOperationFailureRollback:
    """Integration tests for complete failure → rollback → clean state flow."""

    @pytest.mark.asyncio
    async def test_git_operation_failure_rolls_back_clean_state(
        self, declarative_config_repo: Path
    ):
        """Test that a failed git operation rolls back to clean state."""
        step = GitOpsCommitStep(declarative_config_path=str(declarative_config_repo))

        manifest_path = "k8s/test-cluster/test-app/deployment.yaml"
        template_fields = [{"path": "/spec/replicas", "value": 10}]
        project_cfg = {"project_slug": "test-app", "cluster": "test-cluster"}

        # Get original state
        original_manifest = (declarative_config_repo / manifest_path).read_text()
        original_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=declarative_config_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        # Create a proper function to handle different git commands
        def mock_subprocess_run(*args, **kwargs):
            """Mock subprocess.run to handle different git commands."""
            cmd_args = args[0] if args else []
            if "branch" in cmd_args and "--show-current" in cmd_args:
                return MagicMock(returncode=0, stdout="main", stderr="")
            elif "status" in cmd_args and "--porcelain" in cmd_args:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "add" in cmd_args:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "commit" in cmd_args:
                return MagicMock(returncode=0, stdout="abc123", stderr="")
            elif "rev-parse" in cmd_args:
                return MagicMock(returncode=0, stdout="abc123", stderr="")
            elif "push" in cmd_args:
                # Push fails (network error)
                return MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="ssh: connect to host failed: Network unreachable",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("src.action.steps.gitops.subprocess.run", side_effect=mock_subprocess_run):
            result = await step.execute(
                manifest_path=manifest_path,
                template_fields=template_fields,
                project_cfg=project_cfg,
            )

        # Result should be PARTIAL (local commit succeeded, push failed)
        assert result.status == GitOperationStatus.PARTIAL
        assert result.commit_sha == "abc123"
        if result.error:
            assert "network" in result.error.lower()

        # Verify repository is in a clean state (no uncommitted changes)
        final_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=declarative_config_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        # Should have no uncommitted changes (only the new commit)
        uncommitted = [line for line in final_status.split("\n") if line and not line.startswith("##")]
        assert len(uncommitted) == 0, f"Uncommitted changes found: {uncommitted}"

    @pytest.mark.asyncio
    async def test_git_cleanup_after_conflict_and_rollback(
        self, temp_git_repo: Path
    ):
        """Test git cleanup after conflict and rollback."""
        cleanup_results = []

        with GitStateCleanup(repo_path=temp_git_repo) as cleanup:
            # Create a conflicting state
            cleanup.create_temporary_branch("conflict-branch")

            # Simulate a merge conflict by creating MERGE_HEAD
            merge_head = temp_git_repo / ".git" / "MERGE_HEAD"
            merge_head.write_text("abc123")

            # Create a conflicted file
            conflicted_file = temp_git_repo / "test.txt"
            conflicted_file.write_text("<<<<<<< HEAD\noriginal\n=======\nconflict\n>>>>>>> conflict-branch\n")

            cleanup_results.append(cleanup.cleanup_failures)

        # After context exit, cleanup should have:
        # 1. Aborted the merge (removed MERGE_HEAD)
        # 2. Deleted temporary branch
        # 3. Returned to original branch

        assert not merge_head.exists()
        assert "conflict-branch" not in subprocess.run(
            ["git", "branch"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        # Verify we're back on main
        current_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert current_branch == "main"

    @pytest.mark.asyncio
    async def test_comprehensive_cleanup_state_after_exception(
        self, temp_git_repo: Path
    ):
        """Test comprehensive cleanup ensures clean state after any exception."""
        # Create multiple temporary branches
        for i in range(3):
            subprocess.run(
                ["git", "branch", f"temp-{i}"],
                cwd=temp_git_repo,
                capture_output=True,
                check=True,
            )

        # Simulate conflict state
        merge_head = temp_git_repo / ".git" / "MERGE_HEAD"
        merge_head.parent.mkdir(exist_ok=True)
        merge_head.write_text("abc123")

        try:
            with GitStateCleanup(repo_path=temp_git_repo) as cleanup:
                cleanup.created_branches = ["temp-0", "temp-1", "temp-2"]
                # Raise exception to trigger cleanup
                raise RuntimeError("Simulated operation failure")
        except RuntimeError:
            pass

        # Verify comprehensive cleanup
        result = cleanup_all_temporary_state(temp_git_repo)

        # All cleanup should have already happened
        assert result["temporary_branches_deleted"] == []
        assert result["returned_to_main"] is False  # Already on main
        assert result["merge_conflicts_cleaned"] is True

        # Final verification: clean state
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        # No uncommitted changes, no merge state
        assert "MERGE_HEAD" not in status
        assert not merge_head.exists()

    def test_cleanup_idempotency_on_repeated_calls(self, temp_git_repo: Path):
        """Test that cleanup operations are idempotent."""
        # First cleanup
        result1 = cleanup_all_temporary_state(temp_git_repo)

        # Second cleanup should also succeed without errors
        result2 = cleanup_all_temporary_state(temp_git_repo)

        # Both should succeed
        assert result1["cleanup_complete"] is True
        assert result2["cleanup_complete"] is True

        # No branches should be deleted in second call
        assert len(result2["temporary_branches_deleted"]) == 0


# =============================================================================
# Test Helper Functions
# =============================================================================

def count_temp_files(directory: Path) -> int:
    """Helper to count temporary files in a directory."""
    return len(list(directory.glob("*.tmp")))


def get_git_status(repo_path: Path) -> str:
    """Helper to get git status output."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def get_current_branch(repo_path: Path) -> str:
    """Helper to get current git branch."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def list_branches(repo_path: Path) -> list[str]:
    """Helper to list all git branches."""
    result = subprocess.run(
        ["git", "branch", "--format=%(refname:short)"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return [b for b in result.stdout.strip().split("\n") if b]
