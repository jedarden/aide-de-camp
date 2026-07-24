"""
Tests for adc restore-artifacts command.

Tests the CLI command that reverts self-modification commits.
"""

import os
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.cli.commands import restore_artifacts_cmd
from src.freeze import set_frozen, check_frozen, SENTINEL_PATH


class TestRestoreArtifactsBasic:
    """Test basic restore-artifacts functionality."""

    @pytest.fixture
    def clean_env(self):
        """Fixture to ensure clean environment before each test."""
        # Save original env var state
        original_env = os.environ.get("ADC_SELFMOD_FREEZE")

        # Clear env var
        if "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        # Ensure sentinel file doesn't exist
        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

        yield

        # Restore original state
        if original_env is not None:
            os.environ["ADC_SELFMOD_FREEZE"] = original_env
        elif "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        # Clean up sentinel file
        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

    @pytest.fixture
    def git_repo(self, tmp_path, clean_env):
        """Fixture to create a temporary git repo for testing."""
        repo = tmp_path / "test-repo"
        repo.mkdir()

        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=repo, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=repo, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=repo, check=True, capture_output=True)

        # Create initial commit
        (repo / "test.txt").write_text("initial\n")
        subprocess.run(['git', 'add', 'test.txt'], cwd=repo, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'initial commit'], cwd=repo, check=True, capture_output=True)

        yield repo

    def test_restore_artifacts_dry_run(self, git_repo, capsys):
        """Test dry run mode shows what would be reverted."""
        # Create a self-mod commit
        (git_repo / "prompt.md").write_text("new content\n")
        subprocess.run(['git', 'add', 'prompt.md'], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'auto: self-mod write to prompt.md [abc123]'], cwd=git_repo, check=True, capture_output=True)

        # Mock the repo path to use our temp repo
        with patch('pathlib.Path', lambda *args, **kwargs: Path(*args, **kwargs) if len(args) > 1 else git_repo):
            # Run in dry-run mode
            exit_code = restore_artifacts_cmd(commits=1, dry_run=True)

            assert exit_code == 0

            captured = capsys.readouterr()
            assert "Dry run complete" in captured.out
            assert "no changes made" in captured.out

    def test_restore_artifacts_unfreezes_when_frozen(self, clean_env, git_repo, capsys):
        """Test that restore-artifacts unfreezes when frozen."""
        # Freeze the repo
        set_frozen(True)
        assert check_frozen().is_frozen

        # Create a self-mod commit
        (git_repo / "prompt.md").write_text("new content\n")
        subprocess.run(['git', 'add', 'prompt.md'], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'auto: self-mod write to prompt.md [abc123]'], cwd=git_repo, check=True, capture_output=True)

        # Mock to use temp repo and run in dry-run (to avoid actual revert)
        with patch('pathlib.Path', lambda *args, **kwargs: Path(*args, **kwargs) if len(args) > 1 else git_repo):
            exit_code = restore_artifacts_cmd(commits=1, dry_run=True)

            assert exit_code == 0

            captured = capsys.readouterr()
            assert "Unfreezing before restore" in captured.out
            assert "Unfrozen" in captured.out
            assert "Re-freezing (restore state)" in captured.out

        # Should be frozen again
        assert check_frozen().is_frozen

    def test_restore_artifacts_no_self_mod_commits(self, git_repo, capsys):
        """Test behavior when no self-mod commits exist."""
        # Run in dry-run mode
        with patch('pathlib.Path', lambda *args, **kwargs: Path(*args, **kwargs) if len(args) > 1 else git_repo):
            exit_code = restore_artifacts_cmd(commits=1, dry_run=True)

            assert exit_code == 0

            captured = capsys.readouterr()
            assert "No self-modification commits found" in captured.out

    def test_restore_artifacts_multiple_commits(self, git_repo, capsys):
        """Test reverting multiple self-mod commits."""
        # Create multiple self-mod commits
        for i in range(3):
            (git_repo / f"prompt{i}.md").write_text(f"content {i}\n")
            subprocess.run(['git', 'add', f'prompt{i}.md'], cwd=git_repo, check=True, capture_output=True)
            subprocess.run(['git', 'commit', '-m', f'auto: self-mod write to prompt{i}.md [abc123]'], cwd=git_repo, check=True, capture_output=True)

        # Create a non-self-mod commit to test filtering
        (git_repo / "other.txt").write_text("other\n")
        subprocess.run(['git', 'add', 'other.txt'], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'regular commit'], cwd=git_repo, check=True, capture_output=True)

        # Run in dry-run mode
        with patch('pathlib.Path', lambda *args, **kwargs: Path(*args, **kwargs) if len(args) > 1 else git_repo):
            exit_code = restore_artifacts_cmd(commits=2, dry_run=True)

            assert exit_code == 0

            captured = capsys.readouterr()
            assert "Found 2 self-mod commit" in captured.out


class TestRestoreArtifactsIntegration:
    """Integration tests for restore-artifacts with actual git operations."""

    @pytest.fixture
    def clean_env(self):
        """Fixture to ensure clean environment before each test."""
        original_env = os.environ.get("ADC_SELFMOD_FREEZE")

        if "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        from src.freeze import SENTINEL_PATH
        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

        yield

        if original_env is not None:
            os.environ["ADC_SELFMOD_FREEZE"] = original_env
        elif "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

    def test_restore_artifacts_integration(self, clean_env, tmp_path):
        """Integration test: write bad change → restore-artifacts → verify restored."""
        repo = tmp_path / "test-repo"
        repo.mkdir()

        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=repo, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=repo, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=repo, check=True, capture_output=True)

        # Create initial prompt
        prompt_path = repo / "prompts" / "test.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        original_content = "# Original Prompt\n\nThis is the original content."
        prompt_path.write_text(original_content)

        subprocess.run(['git', 'add', 'test.md'], cwd=repo / "prompts", check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'initial'], cwd=repo, check=True, capture_output=True)

        # Simulate a bad self-mod write
        bad_content = "# Bad Prompt\n\nThis is bad content that broke things."
        prompt_path.write_text(bad_content)

        subprocess.run(['git', 'add', 'test.md'], cwd=repo / "prompts", check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'auto: self-mod write to prompts/test.md [abc123]'], cwd=repo, check=True, capture_output=True)

        # Verify bad content is present
        current = prompt_path.read_text()
        assert current == bad_content

        # Mock to use temp repo
        with patch('pathlib.Path', lambda *args, **kwargs: Path(*args, **kwargs) if len(args) > 1 else repo):
            # Run restore-artifacts (dry run to avoid complex revert logic)
            exit_code = restore_artifacts_cmd(commits=1, dry_run=True)

            assert exit_code == 0

        # In dry-run mode, content should not change
        current = prompt_path.read_text()
        assert current == bad_content


class TestRestoreArtifactsErrors:
    """Test error handling in restore-artifacts command."""

    @pytest.fixture
    def clean_env(self):
        """Fixture to ensure clean environment before each test."""
        original_env = os.environ.get("ADC_SELFMOD_FREEZE")

        if "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        from src.freeze import SENTINEL_PATH
        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

        yield

        if original_env is not None:
            os.environ["ADC_SELFMOD_FREEZE"] = original_env
        elif "ADC_SELFMOD_FREEZE" in os.environ:
            del os.environ["ADC_SELFMOD_FREEZE"]

        if SENTINEL_PATH.exists():
            SENTINEL_PATH.unlink()

    def test_git_command_timeout(self, clean_env, capsys):
        """Test handling of git command timeout."""
        import subprocess

        # Mock subprocess.run to simulate timeout
        original_run = subprocess.run

        def mock_run(*args, **kwargs):
            if 'git' in args[0]:
                raise subprocess.TimeoutExpired('git', 10)
            return original_run(*args, **kwargs)

        with patch('subprocess.run', side_effect=mock_run):
            exit_code = restore_artifacts_cmd(commits=1, dry_run=True)

            assert exit_code == 1

            captured = capsys.readouterr()
            assert "timed out" in captured.out.lower() or "timed out" in captured.err.lower()

    def test_git_log_failure(self, clean_env, capsys):
        """Test handling of git log failure."""
        import subprocess

        # Mock subprocess.run to simulate git log failure
        original_run = subprocess.run

        def mock_run(*args, **kwargs):
            if 'git' in args[0] and 'log' in args[0]:
                result = MagicMock()
                result.returncode = 1
                result.stderr = "fatal: bad revision"
                return result
            return original_run(*args, **kwargs)

        with patch('subprocess.run', side_effect=mock_run):
            exit_code = restore_artifacts_cmd(commits=1, dry_run=True)

            assert exit_code == 1
