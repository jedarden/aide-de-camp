"""
Tests for git cleanup utilities.

Verifies that the git cleanup module correctly:
- Captures original git state
- Cleans up temporary branches on failure
- Reverts to original branch if operation fails
- Cleans up merge state if conflicts occur
- Uses try/finally to guarantee cleanup
- Handles all cleanup operations safely
"""

import errno
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src.action.steps.git_validation import GitStateError
from src.utils.git_cleanup import (
    GitCleanupError,
    GitStateCleanup,
    cleanup_all_temporary_state,
    cleanup_merge_state,
    cleanup_temporary_branches,
    git_state_cleanup,
)


@pytest.fixture
def temp_repo(tmp_path: Path):
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

    # Cleanup is handled by tmp_path fixture


class TestGitStateCleanup:
    """Test GitStateCleanup context manager."""

    def test_capture_original_state(self, temp_repo: Path):
        """Test that original git state is captured on entry."""
        with GitStateCleanup(repo_path=temp_repo) as cleanup:
            assert cleanup.original_branch == "main"
            assert cleanup.created_branches == []
            assert not cleanup.had_conflicts

    def test_capture_original_state_custom_branch(self, temp_repo: Path):
        """Test capturing original state when on a different branch."""
        # Create a new branch and switch to it
        subprocess.run(
            ["git", "branch", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with GitStateCleanup(repo_path=temp_repo) as cleanup:
            assert cleanup.original_branch == "feature"

    def test_create_temporary_branch(self, temp_repo: Path):
        """Test creating a temporary branch."""
        with GitStateCleanup(repo_path=temp_repo) as cleanup:
            cleanup.create_temporary_branch("temp-test-branch")
            assert "temp-test-branch" in cleanup.created_branches

            # Verify branch exists
            result = subprocess.run(
                ["git", "branch", "--list", "temp-test-branch"],
                cwd=temp_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert "temp-test-branch" in result.stdout

    def test_create_temporary_branch_from_base(self, temp_repo: Path):
        """Test creating a temporary branch from a specific base."""
        # Create a base branch with some changes
        subprocess.run(
            ["git", "branch", "base-branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with GitStateCleanup(repo_path=temp_repo) as cleanup:
            cleanup.create_temporary_branch("temp-from-base", from_branch="base-branch")
            assert "temp-from-base" in cleanup.created_branches

    def test_switch_to_branch(self, temp_repo: Path):
        """Test switching to a different branch."""
        # Create a test branch
        subprocess.run(
            ["git", "branch", "other-branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with GitStateCleanup(repo_path=temp_repo, return_to_original_branch=True) as cleanup:
            assert cleanup.original_branch == "main"

            cleanup.switch_to_branch("other-branch")

            # Verify we're on the other branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=temp_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert result.stdout.strip() == "other-branch"

        # After context exit, should be back on main
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"

    def test_automatic_branch_cleanup_on_success(self, temp_repo: Path):
        """Test that temporary branches are cleaned up on successful exit."""
        with GitStateCleanup(repo_path=temp_repo, cleanup_branches=True) as cleanup:
            cleanup.create_temporary_branch("temp-success-branch")
            cleanup.switch_to_branch("temp-success-branch")

        # After context exit, temporary branch should be deleted
        result = subprocess.run(
            ["git", "branch", "--list", "temp-success-branch"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == ""

    def test_automatic_branch_cleanup_on_exception(self, temp_repo: Path):
        """Test that temporary branches are cleaned up even when exception occurs."""
        with pytest.raises(ValueError, match="Test exception"):
            with GitStateCleanup(repo_path=temp_repo, cleanup_branches=True) as cleanup:
                cleanup.create_temporary_branch("temp-fail-branch")
                cleanup.switch_to_branch("temp-fail-branch")
                raise ValueError("Test exception")

        # After context exit, temporary branch should be deleted despite exception
        result = subprocess.run(
            ["git", "branch", "--list", "temp-fail-branch"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == ""

    def test_return_to_original_branch_on_success(self, temp_repo: Path):
        """Test that we return to original branch on successful exit."""
        subprocess.run(
            ["git", "branch", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with GitStateCleanup(repo_path=temp_repo, return_to_original_branch=True) as cleanup:
            assert cleanup.original_branch == "main"
            cleanup.switch_to_branch("feature")

        # After context exit, should be back on main
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"

    def test_return_to_original_branch_on_exception(self, temp_repo: Path):
        """Test that we return to original branch even when exception occurs."""
        subprocess.run(
            ["git", "branch", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with pytest.raises(ValueError, match="Test error"):
            with GitStateCleanup(repo_path=temp_repo, return_to_original_branch=True) as cleanup:
                cleanup.switch_to_branch("feature")
                raise ValueError("Test error")

        # After context exit, should be back on main despite exception
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"

    def test_no_cleanup_branches_when_disabled(self, temp_repo: Path):
        """Test that branch cleanup can be disabled."""
        with GitStateCleanup(repo_path=temp_repo, cleanup_branches=False) as cleanup:
            cleanup.create_temporary_branch("temp-nocleanup")
            cleanup.switch_to_branch("temp-nocleanup")

        # Branch should still exist since cleanup was disabled
        result = subprocess.run(
            ["git", "branch", "--list", "temp-nocleanup"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "temp-nocleanup" in result.stdout

    def test_no_return_to_branch_when_disabled(self, temp_repo: Path):
        """Test that return to original branch can be disabled."""
        subprocess.run(
            ["git", "branch", "stay-branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with GitStateCleanup(repo_path=temp_repo, return_to_original_branch=False) as cleanup:
            cleanup.switch_to_branch("stay-branch")

        # Should still be on stay-branch since return was disabled
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "stay-branch"

    def test_cleanup_error_logged_but_exception_raised(self, temp_repo: Path):
        """Test that cleanup errors are logged but don't suppress original exception."""
        with pytest.raises(ValueError, match="Original exception"):
            with patch.object(GitStateCleanup, '_perform_cleanup', side_effect=RuntimeError("Cleanup failed")):
                with GitStateCleanup(repo_path=temp_repo):
                    raise ValueError("Original exception")

    def test_cleanup_error_raised_if_no_original_exception(self, temp_repo: Path):
        """Test that cleanup error is raised if no original exception."""
        # Switch to a temp branch
        subprocess.run(
            ["git", "branch", "temp-branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "temp-branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Move away from the original branch, then delete it externally.  The
        # cleanup step must report that it can no longer restore that branch.
        with pytest.raises(GitCleanupError):
            with GitStateCleanup(repo_path=temp_repo, return_to_original_branch=True) as cleanup:
                cleanup.switch_to_branch("main")
                subprocess.run(
                    ["git", "branch", "-D", "temp-branch"],
                    cwd=temp_repo,
                    capture_output=True,
                    check=True,
                )


class TestGitStateCleanupMergeConflicts:
    """Test merge conflict cleanup functionality."""

    def test_abort_merge(self, temp_repo: Path):
        """Test aborting a merge operation."""
        # Create a conflicting branch
        subprocess.run(
            ["git", "branch", "conflict-branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Modify file on main branch
        test_file = temp_repo / "test.txt"
        test_file.write_text("main branch content")
        subprocess.run(
            ["git", "commit", "-am", "Main branch change"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Switch and modify on conflict branch
        subprocess.run(
            ["git", "checkout", "conflict-branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        test_file.write_text("conflict branch content")
        subprocess.run(
            ["git", "commit", "-am", "Conflict branch change"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Try to merge (will create conflicts)
        subprocess.run(
            ["git", "merge", "main"],
            cwd=temp_repo,
            capture_output=True,
            check=False,
        )

        # Should have conflicts now
        with GitStateCleanup(repo_path=temp_repo, cleanup_merge_state=True) as cleanup:
            # Abort the merge
            cleanup.abort_merge()

        # Should be back to clean state on conflict-branch
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        # No merge conflicts should remain
        assert "UU" not in result.stdout

    def test_abort_merge_handles_modify_delete_conflict(self, temp_repo: Path):
        """Abort also handles unmerged status codes other than ``UU``."""
        conflict_branch = "modify-delete-conflict"
        test_file = temp_repo / "test.txt"

        subprocess.run(
            ["git", "branch", conflict_branch],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        test_file.write_text("main branch content")
        subprocess.run(
            ["git", "commit", "-am", "Main branch change"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", conflict_branch],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        test_file.unlink()
        subprocess.run(
            ["git", "commit", "-am", "Delete file on conflict branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "merge", "main"],
            cwd=temp_repo,
            capture_output=True,
            check=False,
        )

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert any(
            len(line) >= 2
            and ("U" in line[:2] or line[:2] in {"AA", "DD"})
            for line in status.splitlines()
        )

        with GitStateCleanup(repo_path=temp_repo, cleanup_merge_state=True):
            pass

        assert not (temp_repo / ".git" / "MERGE_HEAD").exists()
        assert subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip() == ""

    def test_automatic_merge_cleanup_on_exception(self, temp_repo: Path):
        """Test that merge conflicts are cleaned up even when exception occurs."""
        # Create a conflicting branch
        subprocess.run(
            ["git", "branch", "auto-conflict"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Modify file on main
        test_file = temp_repo / "test.txt"
        test_file.write_text("main content")
        subprocess.run(
            ["git", "commit", "-am", "Main change"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Switch and modify on auto-conflict
        subprocess.run(
            ["git", "checkout", "auto-conflict"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        test_file.write_text("conflict content")
        subprocess.run(
            ["git", "commit", "-am", "Conflict change"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Create merge conflicts
        subprocess.run(
            ["git", "merge", "main"],
            cwd=temp_repo,
            capture_output=True,
            check=False,
        )

        # Should have conflicts
        with pytest.raises(ValueError, match="Test error"):
            with GitStateCleanup(repo_path=temp_repo, cleanup_merge_state=True):
                # Verify we have conflicts
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=temp_repo,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                assert "UU" in result.stdout or result.stdout.strip() == ""
                raise ValueError("Test error")

        # After context exit, conflicts should be cleaned up
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "UU" not in result.stdout


class TestGitStateCleanupContextManager:
    """Test git_state_cleanup context manager wrapper."""

    def test_context_manager_basic_usage(self, temp_repo: Path):
        """Test basic usage of git_state_cleanup context manager."""
        with git_state_cleanup(repo_path=temp_repo) as cleanup:
            assert cleanup.original_branch == "main"
            cleanup.create_temporary_branch("ctx-temp-branch")

        # Branch should be cleaned up
        result = subprocess.run(
            ["git", "branch", "--list", "ctx-temp-branch"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == ""

    def test_context_manager_with_custom_options(self, temp_repo: Path):
        """Test context manager with custom cleanup options."""
        with git_state_cleanup(
            repo_path=temp_repo,
            cleanup_branches=False,
            return_to_original_branch=False,
        ) as cleanup:
            cleanup.create_temporary_branch("no-cleanup-branch")
            cleanup.switch_to_branch("no-cleanup-branch")

        # Branch should still exist and we should still be on it
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "no-cleanup-branch"

        branch_result = subprocess.run(
            ["git", "branch", "--list", "no-cleanup-branch"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "no-cleanup-branch" in branch_result.stdout


class TestCleanupTemporaryBranches:
    """Test cleanup_temporary_branches function."""

    def test_cleanup_branches_by_pattern(self, temp_repo: Path):
        """Test cleaning up branches matching a pattern."""
        # Create several temporary branches
        for i in range(3):
            subprocess.run(
                ["git", "branch", f"temp-test-{i}"],
                cwd=temp_repo,
                capture_output=True,
                check=True,
            )

        # Create a non-matching branch
        subprocess.run(
            ["git", "branch", "keep-branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Clean up temp-* branches
        deleted = cleanup_temporary_branches(temp_repo, branch_pattern="temp-*")

        assert len(deleted) == 3
        assert all(f"temp-test-{i}" in deleted for i in range(3))

        # Verify temp branches are gone
        result = subprocess.run(
            ["git", "branch", "--list", "temp-*"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == ""

        # Verify keep-branch still exists
        result = subprocess.run(
            ["git", "branch", "--list", "keep-branch"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "keep-branch" in result.stdout

    def test_cleanup_branches_without_pattern(self, temp_repo: Path):
        """Test cleaning up all branches when no pattern specified."""
        # This should delete all branches except the current one
        subprocess.run(
            ["git", "branch", "branch1"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "branch", "branch2"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Without pattern, function won't delete any (safety measure)
        deleted = cleanup_temporary_branches(temp_repo)
        assert len(deleted) == 0

    def test_cleanup_skips_current_branch(self, temp_repo: Path):
        """Test that cleanup doesn't delete the current branch."""
        # Create and switch to a temp branch
        subprocess.run(
            ["git", "branch", "temp-current"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "temp-current"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Try to delete temp-* branches
        deleted = cleanup_temporary_branches(temp_repo, branch_pattern="temp-*")

        # Current branch should be skipped
        assert "temp-current" not in deleted

        # Verify current branch still exists
        result = subprocess.run(
            ["git", "branch", "--list", "temp-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "temp-current" in result.stdout

    def test_cleanup_returns_successes_and_failures(self, temp_repo: Path, caplog):
        """Standalone cleanup exposes partial results instead of hiding them."""
        for branch_name in ("temp-locked", "temp-removable"):
            subprocess.run(
                ["git", "branch", branch_name],
                cwd=temp_repo,
                capture_output=True,
                check=True,
            )

        real_run = subprocess.run

        def fail_locked_branch(args, **kwargs):
            if args[-2:] == ["-D", "temp-locked"]:
                raise PermissionError(errno.EACCES, "branch is locked")
            return real_run(args, **kwargs)

        with patch("src.utils.git_cleanup.subprocess.run", side_effect=fail_locked_branch):
            result = cleanup_temporary_branches(
                temp_repo,
                branch_pattern="temp-*",
                return_details=True,
            )

        assert result["deleted"] == ["temp-removable"]
        assert len(result["failures"]) == 1
        assert "temp-locked" in result["failures"][0]
        assert any(
            "operation=temporary branch deletion" in record.message
            and "temp-locked" in record.message
            for record in caplog.records
        )


class TestCleanupMergeState:
    """Test cleanup_merge_state function."""

    def test_cleanup_merge_state_no_conflicts(self, temp_repo: Path):
        """Test cleanup when there are no conflicts."""
        result = cleanup_merge_state(temp_repo)
        assert result is True

    def test_cleanup_merge_state_with_conflicts(self, temp_repo: Path):
        """Test cleanup when there are merge conflicts."""
        # Create a conflicting branch
        subprocess.run(
            ["git", "branch", "conflict-test"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Modify file on main
        test_file = temp_repo / "test.txt"
        test_file.write_text("main branch content")
        subprocess.run(
            ["git", "commit", "-am", "Main change"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Switch and modify on conflict-test
        subprocess.run(
            ["git", "checkout", "conflict-test"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        test_file.write_text("conflict branch content")
        subprocess.run(
            ["git", "commit", "-am", "Conflict change"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Create merge conflicts
        subprocess.run(
            ["git", "merge", "main"],
            cwd=temp_repo,
            capture_output=True,
            check=False,
        )

        # Should have conflicts
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "UU" in result.stdout or result.stdout.strip() == ""

        # Clean up
        cleanup_result = cleanup_merge_state(temp_repo)
        assert cleanup_result is True

        # Verify conflicts are gone
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "UU" not in result.stdout


class TestCleanupAllTemporaryState:
    """Test cleanup_all_temporary_state function."""

    def test_comprehensive_cleanup(self, temp_repo: Path):
        """Test comprehensive cleanup of all temporary state."""
        # Create temporary branches
        subprocess.run(
            ["git", "branch", "temp-branch1"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "branch", "test-branch2"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Switch to a temp branch
        subprocess.run(
            ["git", "checkout", "temp-branch1"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Run comprehensive cleanup
        results = cleanup_all_temporary_state(temp_repo)

        # Verify results
        assert "merge_conflicts_cleaned" in results
        assert "temporary_branches_deleted" in results
        assert "returned_to_main" in results
        assert "errors" in results

        # Should have returned to main
        assert results["returned_to_main"] is True

        # Should have deleted temp branches
        assert len(results["temporary_branches_deleted"]) >= 2

        # Verify we're back on main
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"

    def test_cleanup_with_no_temporary_state(self, temp_repo: Path):
        """Test cleanup when repository is already clean."""
        results = cleanup_all_temporary_state(temp_repo)

        assert results["merge_conflicts_cleaned"] is True
        assert len(results["temporary_branches_deleted"]) == 0
        assert results["returned_to_main"] is False  # Already on main
        assert len(results["errors"]) == 0

    def test_cleanup_error_handling(self, temp_repo: Path):
        """Test that cleanup handles errors gracefully."""
        # Create a temporary branch
        subprocess.run(
            ["git", "branch", "temp-error-test"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Run cleanup - should handle any errors without crashing
        results = cleanup_all_temporary_state(temp_repo)

        # Should complete without crashing
        assert "errors" in results
        assert isinstance(results["errors"], list)


class TestTryFinallyGuarantee:
    """Test that cleanup is guaranteed even with exceptions."""

    def test_try_finally_with_exception(self, temp_repo: Path):
        """Test that cleanup runs in finally block even with exception."""
        subprocess.run(
            ["git", "branch", "finally-test"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        original_exception = None
        try:
            with GitStateCleanup(repo_path=temp_repo, cleanup_branches=True) as cleanup:
                cleanup.create_temporary_branch("temp-finally")
                cleanup.switch_to_branch("temp-finally")
                raise ValueError("Intentional exception")
        except ValueError as e:
            original_exception = e

        # Exception should have been raised
        assert original_exception is not None
        assert str(original_exception) == "Intentional exception"

        # But cleanup should have still run
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"  # Returned to original

        branch_result = subprocess.run(
            ["git", "branch", "--list", "temp-finally"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert branch_result.stdout.strip() == ""  # Branch deleted

    def test_try_finally_with_multiple_exceptions(self, temp_repo: Path):
        """Test cleanup with multiple potential failure points."""
        subprocess.run(
            ["git", "branch", "multi-exception"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        exception_count = 0
        try:
            with GitStateCleanup(repo_path=temp_repo, cleanup_branches=True, return_to_original_branch=True) as cleanup:
                cleanup.create_temporary_branch("temp-multi1")
                cleanup.switch_to_branch("temp-multi1")
                # Simulate failure
                raise RuntimeError("First failure")
        except RuntimeError:
            exception_count += 1

        # Exception should have been raised
        assert exception_count == 1

        # Cleanup should have run
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"

    def test_nested_context_managers(self, temp_repo: Path):
        """Test cleanup with nested context managers."""
        subprocess.run(
            ["git", "branch", "nested-outer"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with GitStateCleanup(repo_path=temp_repo) as outer:
            outer.create_temporary_branch("temp-outer")
            outer.switch_to_branch("temp-outer")

            # Nested context
            with GitStateCleanup(repo_path=temp_repo) as inner:
                inner.create_temporary_branch("temp-inner")
                inner.switch_to_branch("temp-inner")

            # Inner cleanup should have run
            result = subprocess.run(
                ["git", "branch", "--list", "temp-inner"],
                cwd=temp_repo,
                capture_output=True,
                text=True,
                check=True,
            )
            assert result.stdout.strip() == ""

        # Outer cleanup should have run
        result = subprocess.run(
            ["git", "branch", "--list", "temp-outer"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == ""

        # Should be back on main
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_cleanup_when_branch_already_deleted(self, temp_repo: Path):
        """Test cleanup when temporary branch was already deleted externally."""
        with GitStateCleanup(repo_path=temp_repo, cleanup_branches=True) as cleanup:
            cleanup.create_temporary_branch("temp-early-delete")

            # Externally delete the branch
            subprocess.run(
                ["git", "branch", "-D", "temp-early-delete"],
                cwd=temp_repo,
                capture_output=True,
                check=True,
            )

        # Should complete without error even though branch is already gone

    def test_cleanup_with_detached_head(self, temp_repo: Path):
        """Test cleanup when in detached HEAD state."""
        # Get a commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_sha = result.stdout.strip()

        # Go to detached HEAD
        subprocess.run(
            ["git", "checkout", commit_sha],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with GitStateCleanup(repo_path=temp_repo) as cleanup:
            # Should capture detached HEAD state
            assert cleanup.original_branch is not None

        # Should complete without error

    def test_cleanup_timeout_handling(self, temp_repo: Path):
        """Test that timeouts are handled gracefully."""
        with pytest.raises(GitStateError):
            with GitStateCleanup(repo_path=temp_repo, timeout=0.001) as cleanup:
                # Very short timeout should cause operations to fail
                cleanup.create_temporary_branch("timeout-test")

    def test_empty_repository(self, tmp_path: Path):
        """Test cleanup behavior on empty repository."""
        empty_repo = tmp_path / "empty_repo"
        empty_repo.mkdir()

        # Initialize empty git repo
        subprocess.run(
            ["git", "init"],
            cwd=empty_repo,
            capture_output=True,
            check=True,
        )

        # Should handle empty repo gracefully
        with GitStateCleanup(repo_path=empty_repo) as cleanup:
            assert cleanup.original_branch is not None  # Should capture even if no commits


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_complete_workflow_with_cleanup(self, temp_repo: Path):
        """Test a complete workflow with multiple operations and cleanup."""
        # Start on main
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"

        # Perform operations with cleanup
        with pytest.raises(RuntimeError, match="Workflow failed"):
            with GitStateCleanup(repo_path=temp_repo) as cleanup:
                # Create temporary branch for testing
                cleanup.create_temporary_branch("test-workflow")
                cleanup.switch_to_branch("test-workflow")

                # Make some changes
                test_file = temp_repo / "workflow.txt"
                test_file.write_text("workflow test")
                subprocess.run(
                    ["git", "add", "workflow.txt"],
                    cwd=temp_repo,
                    capture_output=True,
                    check=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", "Test commit"],
                    cwd=temp_repo,
                    capture_output=True,
                    check=True,
                )

                # Simulate operation failure
                raise RuntimeError("Workflow failed")

        # Despite exception, cleanup should have:
        # 1. Deleted temporary branch
        # 2. Returned to main
        # 3. Repository in clean state

        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"

        branch_result = subprocess.run(
            ["git", "branch", "--list", "test-workflow"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert branch_result.stdout.strip() == ""

    def test_partial_branch_cleanup_logs_target_and_continues(
        self, temp_repo: Path, caplog
    ):
        """A failed branch deletion is visible and does not stop later cleanup."""
        cleanup = GitStateCleanup(repo_path=temp_repo)
        cleanup.__enter__()
        cleanup.create_temporary_branch("temp-permission")
        cleanup.create_temporary_branch("temp-after-failure")

        real_run = subprocess.run

        def fail_one_branch(args, **kwargs):
            if args[-2:] == ["-D", "temp-permission"]:
                raise PermissionError(errno.EACCES, "branch is locked")
            return real_run(args, **kwargs)

        with patch("src.utils.git_cleanup.subprocess.run", side_effect=fail_one_branch):
            with pytest.raises(GitCleanupError, match="temp-permission"):
                cleanup._perform_cleanup()

        assert subprocess.run(
            ["git", "branch", "--list", "temp-after-failure"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip() == ""
        assert subprocess.run(
            ["git", "branch", "--list", "temp-permission"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert any(
            "operation=temporary branch cleanup" in record.message
            and "temp-permission" in record.message
            and "permission denied" in record.message
            for record in caplog.records
        )

    def test_disk_full_cleanup_failure_is_recorded(self, temp_repo: Path, caplog):
        """Filesystem failures are classified and never reported as success."""
        cleanup = GitStateCleanup(repo_path=temp_repo)
        cleanup.__enter__()
        cleanup.create_temporary_branch("temp-disk-full")
        real_run = subprocess.run

        def fail_delete(args, **kwargs):
            if args[-2:] == ["-D", "temp-disk-full"]:
                raise OSError(errno.ENOSPC, "no space left on device")
            return real_run(args, **kwargs)

        with patch("src.utils.git_cleanup.subprocess.run", side_effect=fail_delete):
            with pytest.raises(GitCleanupError, match="disk full"):
                cleanup._perform_cleanup()

        assert cleanup._cleanup_completed is False
        assert any(
            "disk full" in record.message and "temp-disk-full" in record.message
            for record in caplog.records
        )

    def test_parallel_branch_operations(self, temp_repo: Path):
        """Test cleanup with multiple branch operations."""
        with GitStateCleanup(repo_path=temp_repo) as cleanup:
            # Create multiple temporary branches
            for i in range(5):
                cleanup.create_temporary_branch(f"parallel-{i}")

            # Switch between them
            for i in range(5):
                cleanup.switch_to_branch(f"parallel-{i}")

        # All should be cleaned up
        result = subprocess.run(
            ["git", "branch", "--list", "parallel-*"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == ""

        # Should be back on main
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=temp_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "main"
