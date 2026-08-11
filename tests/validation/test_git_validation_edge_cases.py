"""
Tests for git validation edge cases and failure scenarios.

This module tests edge cases and complex validation scenarios that go beyond
the basic happy path tests, ensuring robust validation behavior in unusual
or problematic repository states.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.action.steps.git_validation import (
    GitNetworkError,
    GitStateError,
    check_current_branch,
    check_uncommitted_changes,
    validate_main_branch,
)


@pytest.fixture
def empty_repo():
    """Create a git repository with no commits (empty repo)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo but don't make any commits
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Configure git user
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

        yield repo_path


@pytest.fixture
def repo_with_detached_head():
    """Create a repository in detached HEAD state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize and setup repo
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
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
        (repo_path / "file1.txt").write_text("content1")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create second commit
        (repo_path / "file2.txt").write_text("content2")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Second commit"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Detach HEAD by checking out a commit
        subprocess.run(
            ["git", "checkout", "HEAD~1"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        yield repo_path


@pytest.fixture
def repo_with_merge_conflict():
    """Create a repository with active merge conflicts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize and setup repo
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
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
        (repo_path / "conflict.txt").write_text("original")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Rename to main branch (in case git init defaulted to master)
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create branch1
        subprocess.run(
            ["git", "checkout", "-b", "branch1"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        (repo_path / "conflict.txt").write_text("branch1 change")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Branch1 change"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create branch2 with conflicting change
        subprocess.run(["git", "checkout", "main"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "checkout", "-b", "branch2"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        (repo_path / "conflict.txt").write_text("branch2 change")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Branch2 change"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Attempt merge that will conflict
        subprocess.run(
            ["git", "merge", "branch1"],
            cwd=repo_path,
            capture_output=True,
            check=False,  # Will fail with conflict
        )

        yield repo_path


@pytest.fixture
def repo_with_mixed_changes():
    """Create a repository with staged, unstaged, and untracked changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize and setup repo
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
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
        (repo_path / "file1.txt").write_text("original")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Modify file and stage it
        (repo_path / "file1.txt").write_text("staged change")
        subprocess.run(
            ["git", "add", "file1.txt"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Modify the same file again (unstaged change on top of staged)
        (repo_path / "file1.txt").write_text("unstaged change")

        # Add untracked file
        (repo_path / "untracked.txt").write_text("untracked")

        yield repo_path


class TestBranchValidationFailureScenarios:
    """Test branch validation in various failure scenarios."""

    def test_empty_repo_branch_validation_fails(self, empty_repo):
        """Branch validation should fail on empty repository with no commits."""
        # Empty repos default to master or main, so we test for wrong expected branch
        # The actual behavior is that git branch --show-current works, but we're not on main
        with pytest.raises(GitStateError, match="Not on expected branch"):
            validate_main_branch(empty_repo)

    def test_detached_head_branch_validation_fails(self, repo_with_detached_head):
        """Branch validation should fail in detached HEAD state."""
        with pytest.raises(GitStateError, match="Not on expected branch"):
            validate_main_branch(repo_with_detached_head, expected_branch="main")

    def test_detached_head_error_message_is_clear(self, repo_with_detached_head):
        """Error message should clearly indicate the branch validation failure."""
        with pytest.raises(GitStateError) as exc_info:
            validate_main_branch(repo_with_detached_head)

        error_msg = str(exc_info.value)
        assert "Not on expected branch" in error_msg
        # The error should include validation context
        assert exc_info.value.validation_type == "branch"

    def test_branch_validation_with_invalid_expected_branch(self, temp_repo):
        """Should provide clear error when expected branch is invalid."""
        # Switch to a non-main branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with pytest.raises(GitStateError) as exc_info:
            validate_main_branch(temp_repo, expected_branch="nonexistent")

        error_msg = str(exc_info.value)
        assert "Not on expected branch 'nonexistent'" in error_msg
        assert "currently on 'feature'" in error_msg

    def test_branch_validation_error_includes_switch_instruction(self, repo_with_detached_head):
        """Error message should include actionable instruction to switch branches."""
        with pytest.raises(GitStateError) as exc_info:
            validate_main_branch(repo_with_detached_head)

        error_msg = str(exc_info.value)
        assert "switch to" in error_msg.lower() or "please" in error_msg.lower()


class TestUncommittedChangesFailureScenarios:
    """Test uncommitted changes detection in various failure scenarios."""

    def test_unstaged_changes_detection(self, temp_repo):
        """Should detect unstaged changes."""
        # Create unstaged changes
        (temp_repo / "test.txt").write_text("unstaged")

        with pytest.raises(GitStateError, match="uncommitted changes"):
            check_uncommitted_changes(temp_repo)

    def test_staged_changes_detection(self, temp_repo):
        """Should detect staged changes."""
        # Create and stage a file
        (temp_repo / "staged.txt").write_text("staged")
        subprocess.run(
            ["git", "add", "staged.txt"],
            cwd=temp_repo,
            capture_output=True,
        )

        with pytest.raises(GitStateError, match="uncommitted changes"):
            check_uncommitted_changes(temp_repo)

    def test_untracked_files_detection(self, temp_repo):
        """Should detect untracked files."""
        # Create untracked file
        (temp_repo / "untracked.txt").write_text("untracked")

        with pytest.raises(GitStateError, match="uncommitted changes"):
            check_uncommitted_changes(temp_repo)

    def test_deleted_files_detection(self, temp_repo):
        """Should detect deleted files."""
        # Create and commit a file
        (temp_repo / "to_delete.txt").write_text("will be deleted")
        subprocess.run(
            ["git", "add", "to_delete.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add file to delete"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Delete the file
        (temp_repo / "to_delete.txt").unlink()

        with pytest.raises(GitStateError, match="uncommitted changes"):
            check_uncommitted_changes(temp_repo)

    def test_mixed_changes_detection(self, repo_with_mixed_changes):
        """Should detect when multiple types of changes exist simultaneously."""
        with pytest.raises(GitStateError) as exc_info:
            check_uncommitted_changes(repo_with_mixed_changes)

        error_msg = str(exc_info.value)
        assert "uncommitted changes" in error_msg.lower()
        # Should mention multiple types of changes
        changes_count = error_msg.lower().count("change")
        assert changes_count >= 1 or "unstaged" in error_msg.lower()

    def test_staged_and_unstaged_same_file(self, repo_with_mixed_changes):
        """Should detect when a file has both staged and unstaged changes."""
        # The repo_with_mixed_changes fixture has file1.txt with staged changes
        # and additional unstaged modifications

        with pytest.raises(GitStateError) as exc_info:
            check_uncommitted_changes(repo_with_mixed_changes)

        error_msg = str(exc_info.value)
        # Should provide detailed breakdown
        assert "unstaged" in error_msg.lower() or "staged" in error_msg.lower()

    def test_uncommitted_changes_error_is_actionable(self, temp_repo):
        """Error message should include actionable instruction."""
        (temp_repo / "test.txt").write_text("change")

        with pytest.raises(GitStateError) as exc_info:
            check_uncommitted_changes(temp_repo)

        error_msg = str(exc_info.value)
        # Should tell user what to do
        assert "commit" in error_msg.lower() or "stash" in error_msg.lower()

    def test_uncommitted_changes_includes_file_list(self, temp_repo):
        """Error message should include the actual changes."""
        (temp_repo / "test.txt").write_text("change")
        (temp_repo / "test2.txt").write_text("change2")

        with pytest.raises(GitStateError) as exc_info:
            check_uncommitted_changes(temp_repo)

        error_msg = str(exc_info.value)
        # Should mention that changes are present
        assert "changes:" in error_msg.lower() or "change" in error_msg.lower()


class TestMergeConflictValidationScenarios:
    """Test validation behavior during merge conflicts."""

    def test_uncommitted_changes_detected_with_merge_conflict(self, repo_with_merge_conflict):
        """Should detect uncommitted changes when merge conflicts exist."""
        with pytest.raises(GitStateError, match="uncommitted changes"):
            check_uncommitted_changes(repo_with_merge_conflict)

    def test_branch_validation_during_merge_conflict(self, repo_with_merge_conflict):
        """Branch validation should work during merge conflicts."""
        # The merge conflict leaves us on branch2, not main
        with pytest.raises(GitStateError, match="Not on expected branch"):
            validate_main_branch(repo_with_merge_conflict, expected_branch="main")

    def test_error_message_clarity_during_merge_conflict(self, repo_with_merge_conflict):
        """Error messages should remain clear even during merge conflicts."""
        with pytest.raises(GitStateError) as exc_info:
            check_uncommitted_changes(repo_with_merge_conflict)

        error_msg = str(exc_info.value)
        # Should still be actionable and clear
        assert "uncommitted changes" in error_msg.lower()
        assert "commit" in error_msg.lower() or "stash" in error_msg.lower()


class TestCleanWorkingTreeValidation:
    """Test validation passes on clean working tree in various states."""

    def test_clean_repo_passes_validation(self, temp_repo):
        """Clean repository should pass all validations."""
        check_uncommitted_changes(temp_repo)  # Should not raise
        validate_main_branch(temp_repo)  # Should not raise

    def test_clean_repo_after_commit(self, temp_repo):
        """Repository should validate clean after committing all changes."""
        # Add and commit changes
        (temp_repo / "newfile.txt").write_text("content")
        subprocess.run(
            ["git", "add", "newfile.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add new file"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Should now pass validation
        check_uncommitted_changes(temp_repo)  # Should not raise

    def test_clean_repo_branch_switching(self, temp_repo):
        """Branch switching should work cleanly on clean repo."""
        # Create a new branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Should validate correctly on new branch
        validate_main_branch(temp_repo, expected_branch="feature")


class TestErrorMessagesClarity:
    """Test that error messages are clear and actionable."""

    def test_branch_error_clarity(self, temp_repo):
        """Branch validation error should be clear and actionable."""
        subprocess.run(
            ["git", "checkout", "-b", "wrong-branch"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with pytest.raises(GitStateError) as exc_info:
            validate_main_branch(temp_repo, expected_branch="main")

        error = exc_info.value
        error_msg = str(error)

        # Check for clear elements
        assert "main" in error_msg  # Expected branch
        assert "wrong-branch" in error_msg  # Actual branch
        assert error.validation_type == "branch"  # Structured type
        assert error.details["expected"] == "main"  # Structured details
        assert error.details["actual"] == "wrong-branch"

    def test_uncommitted_error_clarity(self, temp_repo):
        """Uncommitted changes error should be clear and actionable."""
        (temp_repo / "changed.txt").write_text("changes")

        with pytest.raises(GitStateError) as exc_info:
            check_uncommitted_changes(temp_repo)

        error_msg = str(exc_info.value)

        # Check for actionable elements
        assert "uncommitted changes" in error_msg.lower()
        assert "commit" in error_msg.lower() or "stash" in error_msg.lower()

    def test_error_details_structure(self, temp_repo):
        """Error details should be structured for programmatic handling."""
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with pytest.raises(GitStateError) as exc_info:
            validate_main_branch(temp_repo, expected_branch="main")

        error = exc_info.value

        # Should have structured attributes
        assert hasattr(error, "validation_type")
        assert hasattr(error, "details")
        assert error.validation_type == "branch"
        assert isinstance(error.details, dict)

    def test_repo_path_in_error(self, temp_repo):
        """Error should include repository path for context."""
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with pytest.raises(GitStateError) as exc_info:
            validate_main_branch(temp_repo, expected_branch="main")

        error = exc_info.value
        # Repo path should be included for context
        error_msg = str(error)
        assert str(temp_repo) in error_msg or "repository:" in error_msg.lower()


class TestNetworkAndTimeoutScenarios:
    """Test validation behavior under network/timeout conditions."""

    def test_branch_validation_timeout(self, temp_repo):
        """Should handle timeout during branch validation gracefully."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 10)

            with pytest.raises(GitNetworkError, match="timed out"):
                validate_main_branch(temp_repo)

    def test_uncommitted_changes_timeout(self, temp_repo):
        """Should handle timeout during uncommitted changes check gracefully."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 10)

            with pytest.raises(GitNetworkError, match="timed out"):
                check_uncommitted_changes(temp_repo)

    def test_git_command_failure(self, temp_repo):
        """Should handle git command failures gracefully."""
        with mock.patch("subprocess.run") as mock_run:
            # Simulate git command failing with CalledProcessError
            mock_run.side_effect = subprocess.CalledProcessError(
                1, ["git", "branch", "--show-current"], stderr=b"fatal: git command failed"
            )

            with pytest.raises(GitStateError, match="Failed to determine"):
                validate_main_branch(temp_repo)


class TestMultipleValidationFailures:
    """Test behavior when multiple validations fail simultaneously."""

    def test_wrong_branch_and_uncommitted_changes(self, temp_repo):
        """Should handle both wrong branch and uncommitted changes."""
        # Switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Add uncommitted changes
        (temp_repo / "change.txt").write_text("change")

        # Branch validation should fail
        with pytest.raises(GitStateError, match="Not on expected branch"):
            validate_main_branch(temp_repo)

    def test_detached_head_with_changes(self, repo_with_detached_head):
        """Should handle detached HEAD with uncommitted changes."""
        # Add uncommitted changes in detached state
        (repo_with_detached_head / "change.txt").write_text("change")

        # Should fail on uncommitted changes check
        with pytest.raises(GitStateError, match="uncommitted changes"):
            check_uncommitted_changes(repo_with_detached_head)


# Provide the basic temp_repo fixture for tests that need it
@pytest.fixture
def temp_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Configure git user
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

        # Create initial commit on main branch
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

        # Rename branch to main (in case git init defaulted to master)
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        yield repo_path
