"""
Tests for git validation utilities.

These tests verify the pre-flight git validation checks that ensure
the repository is in a clean state before operations.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.action.steps.git_validation import (
    GitStateError,
    GitNetworkError,
    GitAuthenticationError,
    GitValidationError,
    check_git_repository,
    check_current_branch,
    check_uncommitted_changes,
    check_remote_configuration,
    check_disk_space,
    check_file_permissions,
    check_and_clean_git_locks,
    PreflightGitValidation,
    validate_git_state,
)


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


@pytest.fixture
def repo_with_changes(temp_repo):
    """Create a repo with uncommitted changes."""
    # Add uncommitted changes
    (temp_repo / "test.txt").write_text("uncommitted")
    return temp_repo


@pytest.fixture
def repo_on_different_branch(temp_repo):
    """Create a repo on a non-main branch."""
    subprocess.run(
        ["git", "checkout", "-b", "feature"],
        cwd=temp_repo,
        capture_output=True,
        check=True,
    )
    return temp_repo


class TestCheckGitRepository:
    """Tests for check_git_repository function."""

    def test_valid_repository(self, temp_repo):
        """Should pass for a valid git repository."""
        check_git_repository(temp_repo)  # Should not raise

    def test_non_existent_path(self):
        """Should raise GitStateError for non-existent path."""
        with pytest.raises(GitStateError, match="Repository path does not exist"):
            check_git_repository("/non/existent/path")

    def test_not_a_git_repository(self, tmpdir):
        """Should raise GitStateError for non-git directory."""
        not_repo = Path(tmpdir) / "not_a_repo"
        not_repo.mkdir()

        with pytest.raises(GitStateError, match="Not a git repository"):
            check_git_repository(not_repo)

    def test_timeout(self, temp_repo):
        """Should raise GitNetworkError on timeout."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 10)

            with pytest.raises(GitNetworkError, match="timed out"):
                check_git_repository(temp_repo)


class TestCheckCurrentBranch:
    """Tests for check_current_branch function."""

    def test_on_main_branch(self, temp_repo):
        """Should pass when on expected main branch."""
        branch = check_current_branch(temp_repo, "main")
        assert branch == "main"

    def test_on_different_branch(self, repo_on_different_branch):
        """Should raise GitStateError when not on expected branch."""
        with pytest.raises(GitStateError, match="Not on expected branch 'main'"):
            check_current_branch(repo_on_different_branch, "main")

    def test_returns_current_branch(self, temp_repo):
        """Should return the current branch name."""
        branch = check_current_branch(temp_repo, "main")
        assert isinstance(branch, str)
        assert branch == "main"

    def test_timeout(self, temp_repo):
        """Should raise GitNetworkError on timeout."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 10)

            with pytest.raises(GitNetworkError, match="timed out"):
                check_current_branch(temp_repo, "main")


class TestCheckUncommittedChanges:
    """Tests for check_uncommitted_changes function."""

    def test_clean_repository(self, temp_repo):
        """Should pass for clean repository."""
        check_uncommitted_changes(temp_repo)  # Should not raise

    def test_uncommitted_changes(self, repo_with_changes):
        """Should raise GitStateError when uncommitted changes exist."""
        with pytest.raises(GitStateError, match="Repository has uncommitted changes"):
            check_uncommitted_changes(repo_with_changes)

    def test_uncommitted_changes_message_details(self, repo_with_changes):
        """Error message should include change details."""
        with pytest.raises(GitStateError) as exc_info:
            check_uncommitted_changes(repo_with_changes)

        error_msg = str(exc_info.value)
        assert "uncommitted changes" in error_msg.lower()
        assert "unstaged" in error_msg.lower()

    def test_staged_changes(self, temp_repo):
        """Should detect staged changes."""
        # Create and stage a file
        (temp_repo / "staged.txt").write_text("staged")
        subprocess.run(
            ["git", "add", "staged.txt"],
            cwd=temp_repo,
            capture_output=True,
        )

        with pytest.raises(GitStateError, match="Repository has uncommitted changes"):
            check_uncommitted_changes(temp_repo)

    def test_timeout(self, temp_repo):
        """Should raise GitNetworkError on timeout."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 10)

            with pytest.raises(GitNetworkError, match="timed out"):
                check_uncommitted_changes(temp_repo)


class TestCheckRemoteConfiguration:
    """Tests for check_remote_configuration function."""

    def test_no_remote(self, temp_repo):
        """Should raise GitStateError when no remote configured and required."""
        with pytest.raises(GitStateError, match="No git remotes configured"):
            check_remote_configuration(temp_repo, require_remote=True)

    def test_with_remote(self, temp_repo):
        """Should pass with valid remote configuration."""
        # Add a remote
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.com/repo.git"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        remotes = check_remote_configuration(temp_repo)
        assert "origin" in remotes
        assert remotes["origin"] == "https://example.com/repo.git"

    def test_expected_remote_pattern_match(self, temp_repo):
        """Should pass when remote matches expected pattern."""
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/user/repo.git"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        remotes = check_remote_configuration(
            temp_repo,
            expected_remote_pattern="github.com"
        )
        assert "origin" in remotes

    def test_expected_remote_pattern_mismatch(self, temp_repo):
        """Should raise GitStateError when remote doesn't match pattern."""
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.com/repo.git"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with pytest.raises(GitStateError, match="does not match expected pattern"):
            check_remote_configuration(
                temp_repo,
                expected_remote_pattern="github.com"
            )

    def test_authentication_error(self, temp_repo):
        """Should raise GitAuthenticationError on auth failure."""
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.com/repo.git"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stderr="fatal: authentication failed"
            )

            with pytest.raises(GitAuthenticationError, match="authentication failed"):
                check_remote_configuration(temp_repo)

    def test_timeout(self, temp_repo):
        """Should raise GitNetworkError on timeout."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 10)

            with pytest.raises(GitNetworkError, match="timed out"):
                check_remote_configuration(temp_repo)


class TestCheckDiskSpace:
    """Tests for check_disk_space function."""

    def test_sufficient_disk_space(self, temp_repo):
        """Should pass when sufficient disk space available."""
        check_disk_space(temp_repo, min_free_mb=1)  # Should not raise

    def test_insufficient_disk_space(self, temp_repo, monkeypatch):
        """Should raise GitStateError when insufficient disk space."""
        # Mock statvfs to report low disk space
        def mock_statvfs(path):
            mock_result = mock.MagicMock()
            mock_result.f_bavail = 10  # 10 blocks free
            mock_result.f_frsize = 1024  # 1KB block size = 10KB total free
            return mock_result

        monkeypatch.setattr("os.statvfs", mock_statvfs)

        with pytest.raises(GitStateError, match="Insufficient disk space"):
            check_disk_space(temp_repo, min_free_mb=100)


class TestCheckFilePermissions:
    """Tests for check_file_permissions function."""

    def test_write_permission(self, temp_repo):
        """Should pass when write permission available."""
        check_file_permissions(temp_repo)  # Should not raise

    def test_no_write_permission(self, temp_repo, monkeypatch):
        """Should raise GitStateError when no write permission."""
        def mock_touch(self):
            raise PermissionError("Permission denied")

        monkeypatch.setattr(Path, "touch", mock_touch)

        with pytest.raises(GitStateError, match="No write permission"):
            check_file_permissions(temp_repo)


class TestCheckAndCleanGitLocks:
    """Tests for check_and_clean_git_locks function."""

    def test_no_locks(self, temp_repo):
        """Should return empty list when no locks present."""
        locks = check_and_clean_git_locks(temp_repo)
        assert locks == []

    def test_clean_index_lock(self, temp_repo):
        """Should clean index.lock file."""
        lock_file = temp_repo / ".git" / "index.lock"
        lock_file.write_text("lock")

        locks = check_and_clean_git_locks(temp_repo)

        assert "index.lock" in locks
        assert not lock_file.exists()

    def test_clean_merge_head(self, temp_repo):
        """Should clean MERGE_HEAD file."""
        lock_file = temp_repo / ".git" / "MERGE_HEAD"
        lock_file.write_text("merge state")

        locks = check_and_clean_git_locks(temp_repo)

        assert "MERGE_HEAD" in locks
        assert not lock_file.exists()

    def test_multiple_locks(self, temp_repo):
        """Should clean multiple lock files."""
        (temp_repo / ".git" / "index.lock").write_text("lock")
        (temp_repo / ".git" / "MERGE_HEAD").write_text("merge")
        (temp_repo / ".git" / "CHERRY_PICK_HEAD").write_text("cherry")

        locks = check_and_clean_git_locks(temp_repo)

        assert len(locks) == 3
        assert "index.lock" in locks
        assert "MERGE_HEAD" in locks
        assert "CHERRY_PICK_HEAD" in locks


class TestPreflightGitValidation:
    """Tests for PreflightGitValidation class."""

    def test_successful_validation(self, temp_repo):
        """Should pass all validations in strict mode."""
        validator = PreflightGitValidation(
            repo_path=temp_repo,
            expected_branch="main",
            expected_remote_pattern=None,  # Don't require remotes for test repos
            strict=True,
        )

        result = validator.validate_all()
        assert result is True
        assert len(validator.errors) == 0

    def test_uncommitted_changes_detection(self, repo_with_changes):
        """Should detect uncommitted changes in strict mode."""
        validator = PreflightGitValidation(
            repo_path=repo_with_changes,
            expected_branch="main",
            strict=True,
        )

        with pytest.raises(GitStateError, match="uncommitted changes"):
            validator.validate_all()

    def test_wrong_branch_detection(self, repo_on_different_branch):
        """Should detect wrong branch in strict mode."""
        validator = PreflightGitValidation(
            repo_path=repo_on_different_branch,
            expected_branch="main",
            strict=True,
        )

        with pytest.raises(GitStateError, match="Not on expected branch"):
            validator.validate_all()

    def test_non_strict_mode_continues_validation(self, repo_with_changes):
        """Should continue validation in non-strict mode."""
        validator = PreflightGitValidation(
            repo_path=repo_with_changes,
            expected_branch="main",
            strict=False,
        )

        result = validator.validate_all()

        # Should return False due to errors
        assert result is False
        # Should have collected errors
        assert len(validator.errors) > 0
        # Should have results for all checks
        assert len(validator.results) > 0

    def test_get_summary(self, temp_repo):
        """Should provide validation summary."""
        validator = PreflightGitValidation(
            repo_path=temp_repo,
            expected_branch="main",
            strict=False,
        )
        validator.validate_all()

        summary = validator.get_summary()

        assert "repo_path" in summary
        assert "expected_branch" in summary
        assert "total_checks" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "results" in summary
        assert "errors" in summary

    def test_summary_includes_check_details(self, temp_repo):
        """Summary should include individual check results."""
        validator = PreflightGitValidation(
            repo_path=temp_repo,
            expected_branch="main",
            strict=False,
        )
        validator.validate_all()

        summary = validator.get_summary()

        # Check that results have expected fields
        for result in summary["results"]:
            assert "check" in result
            assert "status" in result
            assert "message" in result


class TestValidateGitState:
    """Tests for validate_git_state convenience function."""

    def test_successful_validation(self, temp_repo):
        """Should pass and return summary."""
        summary = validate_git_state(temp_repo, expected_remote_pattern=None)

        assert summary["passed"] > 0
        assert summary["failed"] == 0
        assert "results" in summary

    def test_strict_mode_raises_on_error(self, repo_with_changes):
        """Should raise error in strict mode."""
        with pytest.raises(GitStateError, match="uncommitted changes"):
            validate_git_state(repo_with_changes, strict=True)

    def test_non_strict_mode_returns_summary_with_errors(self, repo_with_changes):
        """Should return summary with errors in non-strict mode."""
        summary = validate_git_state(repo_with_changes, strict=False)

        assert summary["failed"] > 0
        assert len(summary["errors"]) > 0

    def test_custom_branch_expectation(self, repo_on_different_branch):
        """Should validate against custom branch expectation."""
        summary = validate_git_state(
            repo_on_different_branch,
            expected_branch="feature",
            strict=False,
        )

        # Should pass since we're on feature branch
        assert summary["failed"] == 0

    def test_custom_remote_pattern(self, temp_repo):
        """Should validate against custom remote pattern."""
        # Add a remote
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/user/repo.git"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # This should pass even without remote pattern check
        # (since we don't require remote by default)
        summary = validate_git_state(temp_repo, strict=False)
        assert summary["passed"] > 0


class TestValidationIntegration:
    """Integration tests for validation workflow."""

    def test_full_validation_workflow(self, temp_repo):
        """Test complete validation workflow from clean state."""
        # Start with clean repo
        summary = validate_git_state(temp_repo, expected_remote_pattern=None)
        assert summary["failed"] == 0

        # Add uncommitted changes
        (temp_repo / "change.txt").write_text("change")
        summary = validate_git_state(temp_repo, strict=False, expected_remote_pattern=None)
        assert summary["failed"] > 0
        assert "uncommitted" in str(summary["errors"]).lower()

    def test_branch_switching_validation(self, temp_repo):
        """Test validation after branch switching."""
        # Start on main
        validate_git_state(temp_repo, expected_branch="main", expected_remote_pattern=None)

        # Switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Should fail if expecting main
        with pytest.raises(GitStateError):
            validate_git_state(temp_repo, expected_branch="main", expected_remote_pattern=None)

        # Should pass if expecting feature
        validate_git_state(temp_repo, expected_branch="feature", expected_remote_pattern=None)

    def test_commit_resolves_uncommitted_check(self, temp_repo):
        """Test that committing changes resolves validation."""
        # Add uncommitted changes
        (temp_repo / "file.txt").write_text("content")

        # Should fail
        with pytest.raises(GitStateError):
            validate_git_state(temp_repo, expected_remote_pattern=None)

        # Commit changes
        subprocess.run(
            ["git", "add", "file.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Should now pass
        validate_git_state(temp_repo, expected_remote_pattern=None)
