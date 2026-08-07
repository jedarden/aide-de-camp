"""
Tests for git merge conflict detection functionality.

Tests the enhanced GitConflictError class and conflict detection functions
to ensure merge conflicts are properly detected, reported, and surfaced
with helpful error messages and conflict details.
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from src.action.steps.git_validation import (
    GitConflictError,
    detect_merge_conflicts,
    GitStateError,
    GitNetworkError,
    GitError,
)


class TestGitConflictError:
    """Test enhanced GitConflictError with conflict details."""

    def test_conflict_error_with_message_only(self):
        """GitConflictError can be created with just a message."""
        error = GitConflictError("Simple conflict message")
        assert str(error) == "Simple conflict message"
        assert error.conflict_files == []
        assert error.conflict_type == "merge"
        assert error.details == {}

    def test_conflict_error_with_conflict_files(self):
        """GitConflictError includes conflict files in error message."""
        error = GitConflictError(
            "Merge conflicts detected",
            conflict_files=["file1.txt", "file2.py", "file3.yaml"]
        )
        error_msg = str(error)
        assert "Merge conflicts detected" in error_msg
        assert "Conflicting files (3)" in error_msg
        assert "file1.txt" in error_msg
        assert "file2.py" in error_msg
        assert "file3.yaml" in error_msg

    def test_conflict_error_limits_files_display(self):
        """GitConflictError limits displayed files to first 5 when many conflicts."""
        many_files = [f"file{i}.txt" for i in range(10)]
        error = GitConflictError(
            "Many conflicts",
            conflict_files=many_files
        )
        error_msg = str(error)
        assert "Conflicting files (10)" in error_msg
        assert "file0.txt" in error_msg
        assert "file4.txt" in error_msg  # 5th file (0-indexed)
        assert "... and 5 more" in error_msg
        assert "file9.txt" not in error_msg  # Should not be displayed

    def test_conflict_error_with_custom_type(self):
        """GitConflictError supports custom conflict types."""
        error = GitConflictError(
            "Push rejected",
            conflict_type="push_rejection",
            details={"hint": "pull first"}
        )
        assert error.conflict_type == "push_rejection"
        assert error.details == {"hint": "pull first"}

    def test_conflict_error_with_details(self):
        """GitConflictError includes additional details in error message."""
        error = GitConflictError(
            "Non-fast-forward push",
            conflict_type="push_rejection",
            details={
                "reason": "non_fast_forward",
                "hint": "pull remote changes first",
                "remote_commit": "abc123"
            }
        )
        error_msg = str(error)
        assert "Non-fast-forward push" in error_msg
        assert "Details:" in error_msg
        assert "reason=non_fast_forward" in error_msg
        assert "hint=pull remote changes first" in error_msg
        assert "remote_commit=abc123" in error_msg

    def test_conflict_error_attributes_accessible(self):
        """GitConflictError attributes are accessible for programmatic handling."""
        error = GitConflictError(
            "Test conflict",
            conflict_files=["src/app.py"],
            conflict_type="merge",
            details={"operation": "commit"}
        )
        assert error.conflict_files == ["src/app.py"]
        assert error.conflict_type == "merge"
        assert error.details == {"operation": "commit"}

    def test_conflict_error_inherits_from_git_error(self):
        """GitConflictError inherits from GitError base class."""
        error = GitConflictError("Test")
        assert isinstance(error, GitError)

    def test_conflict_error_can_be_raised_and_caught(self):
        """GitConflictError can be raised and caught as GitConflictError."""
        with pytest.raises(GitConflictError, match="Test conflict"):
            raise GitConflictError("Test conflict")

    def test_conflict_error_caught_as_git_error(self):
        """GitConflictError can be caught as GitError."""
        with pytest.raises(GitError):
            raise GitConflictError("Test conflict")


class TestDetectMergeConflicts:
    """Test active merge conflict detection in repository."""

    @patch("subprocess.run")
    def test_no_conflicts_when_not_in_merge_state(self, mock_run, tmp_path):
        """No conflicts detected when repository is not in merge state."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Mock git grep to return nothing (no conflicts)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        conflicts = detect_merge_conflicts(repo_path)

        assert conflicts == []
        assert mock_run.call_count == 0  # Early return, no grep needed

    @patch("subprocess.run")
    def test_detects_conflicts_in_merge_state(self, mock_run, tmp_path):
        """Conflicts detected when MERGE_HEAD exists and files have markers."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Create MERGE_HEAD to simulate merge state
        merge_head = git_dir / "MERGE_HEAD"
        merge_head.write_text("abc123\n")

        # Mock git grep to return conflicting files
        mock_run.side_effect = [
            Mock(returncode=0, stdout="file1.txt\nfile2.py\n", stderr=""),  # cached
            Mock(returncode=0, stdout="file3.yaml\n", stderr=""),  # working
        ]

        conflicts = detect_merge_conflicts(repo_path)

        assert len(conflicts) == 3
        assert "file1.txt" in conflicts
        assert "file2.py" in conflicts
        assert "file3.yaml" in conflicts

    @patch("subprocess.run")
    def test_detects_conflicts_deduplicates_files(self, mock_run, tmp_path):
        """Conflict detection deduplicates files appearing in multiple sources."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Create MERGE_HEAD to simulate merge state
        merge_head = git_dir / "MERGE_HEAD"
        merge_head.write_text("abc123\n")

        # Mock git grep to return overlapping files
        mock_run.side_effect = [
            Mock(returncode=0, stdout="file.txt\n", stderr=""),  # cached
            Mock(returncode=0, stdout="file.txt\nother.py\n", stderr=""),  # working
        ]

        conflicts = detect_merge_conflicts(repo_path)

        assert len(conflicts) == 2  # file.txt should be deduplicated
        assert "file.txt" in conflicts
        assert "other.py" in conflicts

    @patch("subprocess.run")
    def test_detects_conflicts_during_rebase(self, mock_run, tmp_path):
        """Conflicts detected during rebase (rebase-merge directory exists)."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Create rebase-merge directory to simulate rebase state
        rebase_dir = git_dir / "rebase"
        rebase_dir.mkdir()
        merge_dir = rebase_dir / "merge"
        merge_dir.mkdir()

        # Mock git grep to return conflicting files
        mock_run.side_effect = [
            Mock(returncode=0, stdout="conflicted.py\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
        ]

        conflicts = detect_merge_conflicts(repo_path)

        assert len(conflicts) == 1
        assert "conflicted.py" in conflicts

    @patch("subprocess.run")
    def test_detects_conflicts_during_cherry_pick(self, mock_run, tmp_path):
        """Conflicts detected during cherry-pick (CHERRY_PICK_HEAD exists)."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Create CHERRY_PICK_HEAD to simulate cherry-pick state
        cherry_head = git_dir / "CHERRY_PICK_HEAD"
        cherry_head.write_text("def456\n")

        # Mock git grep to return conflicting files
        mock_run.side_effect = [
            Mock(returncode=0, stdout="cherry_conflict.py\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
        ]

        conflicts = detect_merge_conflicts(repo_path)

        assert len(conflicts) == 1
        assert "cherry_conflict.py" in conflicts

    @patch("subprocess.run")
    def test_conflict_detection_timeout_raises_network_error(self, mock_run, tmp_path):
        """Conflict detection timeout raises GitNetworkError."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Create MERGE_HEAD to simulate merge state
        merge_head = git_dir / "MERGE_HEAD"
        merge_head.write_text("abc123\n")

        # Mock git grep to timeout
        mock_run.side_effect = subprocess.TimeoutExpired("grep", 5)

        with pytest.raises(GitNetworkError, match="timed out"):
            detect_merge_conflicts(repo_path)

    @patch("subprocess.run")
    def test_conflict_detection_handles_git_not_found(self, mock_run, tmp_path):
        """Conflict detection handles git command not found gracefully."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Create MERGE_HEAD to simulate merge state
        merge_head = git_dir / "MERGE_HEAD"
        merge_head.write_text("abc123\n")

        # Mock git grep to raise FileNotFoundError
        mock_run.side_effect = FileNotFoundError("git not found")

        with pytest.raises(GitStateError, match="Git command not found"):
            detect_merge_conflicts(repo_path)

    @patch("subprocess.run")
    def test_conflict_detection_handles_unexpected_errors(self, mock_run, tmp_path):
        """Conflict detection handles unexpected errors gracefully (returns empty list)."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Create MERGE_HEAD to simulate merge state
        merge_head = git_dir / "MERGE_HEAD"
        merge_head.write_text("abc123\n")

        # Mock git grep to raise unexpected error
        mock_run.side_effect = RuntimeError("Unexpected error")

        # Should log error but return empty list (best-effort)
        conflicts = detect_merge_conflicts(repo_path)
        assert conflicts == []

    @patch("subprocess.run")
    def test_conflict_detection_sorts_files(self, mock_run, tmp_path):
        """Conflict detection returns sorted list of conflicting files."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Create MERGE_HEAD to simulate merge state
        merge_head = git_dir / "MERGE_HEAD"
        merge_head.write_text("abc123\n")

        # Mock git grep to return unsorted files
        mock_run.side_effect = [
            Mock(returncode=0, stdout="z.py\na.txt\nm.yaml\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
        ]

        conflicts = detect_merge_conflicts(repo_path)

        # Should be sorted alphabetically
        assert conflicts == ["a.txt", "m.yaml", "z.py"]


class TestConflictDetectionIntegration:
    """Integration tests for conflict detection with actual git state."""

    def test_real_git_repo_no_conflicts(self, tmp_path):
        """Conflict detection works with real git repo (no conflicts)."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize real git repo
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True
        )

        conflicts = detect_merge_conflicts(repo_path)
        assert conflicts == []

    def test_real_git_repo_with_conflict_markers(self, tmp_path):
        """Conflict detection finds real conflict markers in files."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize real git repo
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True
        )

        # Create and commit a base file
        base_file = repo_path / "conflict.txt"
        base_file.write_text("base content\n")
        subprocess.run(
            ["git", "add", "conflict.txt"],
            cwd=repo_path,
            capture_output=True,
            check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "base commit"],
            cwd=repo_path,
            capture_output=True,
            check=True
        )

        # Create a file with conflict markers in working directory
        conflicted_file = repo_path / "conflict.txt"
        conflicted_file.write_text("""before
<<<<<<< HEAD
local version
=======
remote version
>>>>>>> origin/main
after
""")

        # Stage the file with conflicts
        subprocess.run(
            ["git", "add", "conflict.txt"],
            cwd=repo_path,
            capture_output=True,
            check=True
        )

        # Create MERGE_HEAD to simulate merge state
        merge_head = repo_path / ".git" / "MERGE_HEAD"
        merge_head.write_text("abc123\n")

        conflicts = detect_merge_conflicts(repo_path)

        # Should find the conflicted file
        assert len(conflicts) >= 1
        assert any("conflict.txt" in f for f in conflicts)


class TestGitConflictErrorScenarios:
    """Test common conflict scenarios with enhanced error reporting."""

    def test_merge_conflict_with_multiple_files(self):
        """Merge conflict error with multiple files formats correctly."""
        error = GitConflictError(
            "Merge conflict detected during commit",
            conflict_files=["src/main.py", "src/utils.py", "config.yaml"],
            conflict_type="merge",
            details={"operation": "commit", "hint": "resolve conflicts and continue"}
        )
        error_msg = str(error)

        assert "Merge conflict detected during commit" in error_msg
        assert "Conflicting files (3)" in error_msg
        assert "src/main.py" in error_msg
        assert "src/utils.py" in error_msg
        assert "config.yaml" in error_msg
        assert "Details:" in error_msg
        assert "operation=commit" in error_msg

    def test_push_rejection_non_fast_forward(self):
        """Push rejection error provides helpful hints."""
        error = GitConflictError(
            "Non-fast-forward push rejected",
            conflict_files=[],
            conflict_type="push_rejection",
            details={"reason": "non_fast_forward", "hint": "pull remote changes first"}
        )
        error_msg = str(error)

        assert "Non-fast-forward push rejected" in error_msg
        assert "Details:" in error_msg
        assert "reason=non_fast_forward" in error_msg
        assert "hint=pull remote changes first" in error_msg

    def test_push_rejection_diverged_branches(self):
        """Push rejection for diverged branches provides clear error."""
        error = GitConflictError(
            "Push rejected: local and remote have diverged",
            conflict_files=[],
            conflict_type="push_rejection",
            details={"reason": "diverged", "hint": "reconcile branches and try again"}
        )
        error_msg = str(error)

        assert "diverged" in error_msg.lower()
        assert "reconcile" in error_msg.lower()

    def test_large_conflict_set_displays_summary(self):
        """Large conflict sets display summary with truncated file list."""
        many_files = [f"src/module{i}/file.py" for i in range(20)]
        error = GitConflictError(
            "Large-scale merge conflict",
            conflict_files=many_files,
            conflict_type="merge",
            details={"total_files": 20, "affected_modules": 10}
        )
        error_msg = str(error)

        assert "Large-scale merge conflict" in error_msg
        assert "Conflicting files (20)" in error_msg
        assert "... and 15 more" in error_msg
        assert "src/module0/file.py" in error_msg
        assert "src/module4/file.py" in error_msg
        assert "src/module19/file.py" not in error_msg  # Beyond display limit
        assert "total_files=20" in error_msg
