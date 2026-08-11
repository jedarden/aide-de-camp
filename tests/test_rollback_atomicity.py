"""Regression tests for atomic file publication during rollback operations."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.action.steps.gitops import GitOpsCommitStep
from src.agents.self_modification import ArtifactType, SelfModificationAgent
from src.utils.atomic_write import atomic_write


@pytest.mark.asyncio
async def test_gitops_rollback_restores_parent_with_atomic_write(tmp_path, caplog):
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text("current manifest\n")
    step = GitOpsCommitStep(declarative_config_path=str(tmp_path))

    git_results = [
        SimpleNamespace(returncode=0, stdout="parent manifest\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
    ]

    with patch("src.action.steps.gitops.subprocess.run", side_effect=git_results) as run, \
         patch.object(step, "_validate_declarative_config_repo"), \
         patch.object(step, "_push_changes"), \
         patch("src.action.steps.gitops.atomic_write", wraps=atomic_write) as write, \
         caplog.at_level("INFO"):
        result = await step.rollback("deployment.yaml", "abc123")

    assert result.success is True
    assert manifest.read_text() == "parent manifest\n"
    assert write.call_args.args == (manifest, "parent manifest\n")
    assert all("revert" not in call.args[0] for call in run.call_args_list)
    assert "Rollback atomic write" in caplog.text


@pytest.mark.asyncio
async def test_gitops_rollback_commit_failure_restores_original_atomically(tmp_path):
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text("original manifest\n")
    step = GitOpsCommitStep(declarative_config_path=str(tmp_path))

    git_results = [
        SimpleNamespace(returncode=0, stdout="rollback manifest\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=1, stdout="", stderr="commit failed\n"),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
    ]

    with patch("src.action.steps.gitops.subprocess.run", side_effect=git_results), \
         patch.object(step, "_validate_declarative_config_repo"), \
         patch("src.action.steps.gitops.atomic_write", wraps=atomic_write) as write:
        result = await step.rollback("deployment.yaml", "abc123")

    assert result.success is False
    assert manifest.read_text() == "original manifest\n"
    assert [call.args[1] for call in write.call_args_list] == [
        "rollback manifest\n",
        "original manifest\n",
    ]


def test_self_modification_rollback_logs_and_writes_atomically(tmp_path, caplog):
    artifact_path = tmp_path / "prompt.md"
    artifact_path.write_text("current prompt\n")
    artifact = SimpleNamespace(path=artifact_path)

    agent = SelfModificationAgent()
    agent.reload_mgr = MagicMock()
    agent.reload_mgr._artifacts = {"prompt": artifact}

    git_result = SimpleNamespace(returncode=0, stdout="previous prompt\n", stderr="")
    with patch("src.agents.self_modification.subprocess.run", return_value=git_result), \
         patch("src.agents.self_modification.atomic_write", wraps=atomic_write) as write, \
         caplog.at_level("INFO"):
        result = agent.rollback("prompt", ArtifactType.PROMPT)

    assert result is True
    assert artifact_path.read_text() == "previous prompt\n"
    write.assert_called_once_with(artifact_path, "previous prompt\n")
    assert "Rollback atomic write" in caplog.text


def test_restore_artifacts_cli_publishes_parent_with_atomic_write(tmp_path):
    from src.cli import commands

    artifact_path = tmp_path / "prompts" / "prompt.md"
    artifact_path.parent.mkdir()
    artifact_path.write_text("current prompt\n")

    git_results = [
        SimpleNamespace(
            returncode=0,
            stdout="abc123 auto: self-mod write to prompts/prompt.md [base]\n",
            stderr="",
        ),
        SimpleNamespace(returncode=0, stdout="previous prompt\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
    ]

    def fake_path(value):
        if value == "/home/coding/aide-de-camp":
            return tmp_path
        return Path(value)

    frozen = SimpleNamespace(is_frozen=False, reason=None)
    with patch("src.cli.commands.Path", side_effect=fake_path), \
         patch("src.cli.commands.atomic_write", wraps=atomic_write) as write, \
         patch("subprocess.run", side_effect=git_results) as run, \
         patch("src.freeze.check_frozen", return_value=frozen), \
         patch("src.freeze.set_frozen"):
        result = commands.restore_artifacts_cmd(commits=1)

    assert result == 0
    assert artifact_path.read_text() == "previous prompt\n"
    write.assert_called_once_with(artifact_path, "previous prompt\n")
    assert all("revert" not in call.args[0] for call in run.call_args_list)


class TestRollbackValidation:
    """Tests for pre-operation validation in rollback method."""


@pytest.mark.asyncio
async def test_rollback_fails_on_uncommitted_changes(tmp_path):
    """Rollback should fail when repository has uncommitted changes."""
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text("current manifest\n")
    step = GitOpsCommitStep(declarative_config_path=str(tmp_path))

    # Mock validation to raise GitStateError for uncommitted changes
    with patch.object(step, "_validate_declarative_config_repo") as mock_validate:
        from src.action.steps.git_validation import GitStateError
        mock_validate.side_effect = GitStateError(
            "Repository has uncommitted changes (1 unstaged change(s)). "
            "Please commit or stash them first."
        )

        result = await step.rollback("deployment.yaml", "abc123")

        assert result.success is False
        assert result.status == "failed"
        assert "validation failed" in result.error.lower()
        assert "uncommitted changes" in result.error.lower()


@pytest.mark.asyncio
async def test_rollback_fails_on_wrong_branch(tmp_path):
    """Rollback should fail when not on expected main branch."""
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text("current manifest\n")
    step = GitOpsCommitStep(declarative_config_path=str(tmp_path))

    # Mock validation to raise GitStateError for wrong branch
    with patch.object(step, "_validate_declarative_config_repo") as mock_validate:
        from src.action.steps.git_validation import GitStateError
        mock_validate.side_effect = GitStateError(
            "Not on expected branch 'main': currently on 'feature'. "
            "Please switch to main branch first."
        )

        result = await step.rollback("deployment.yaml", "abc123")

        assert result.success is False
        assert result.status == "failed"
        assert "validation failed" in result.error.lower()
        assert "branch" in result.error.lower()


@pytest.mark.asyncio
async def test_rollback_fails_on_git_network_error(tmp_path):
    """Rollback should fail when git operations timeout."""
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text("current manifest\n")
    step = GitOpsCommitStep(declarative_config_path=str(tmp_path))

    # Mock validation to raise GitNetworkError
    with patch.object(step, "_validate_declarative_config_repo") as mock_validate:
        from src.action.steps.git_validation import GitNetworkError
        mock_validate.side_effect = GitNetworkError("Git repository check timed out")

        result = await step.rollback("deployment.yaml", "abc123")

        assert result.success is False
        assert result.status == "failed"
        assert "validation failed" in result.error.lower()
        assert "timed out" in result.error.lower()


@pytest.mark.asyncio
async def test_rollback_fails_on_git_authentication_error(tmp_path):
    """Rollback should fail when git authentication fails."""
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text("current manifest\n")
    step = GitOpsCommitStep(declarative_config_path=str(tmp_path))

    # Mock validation to raise GitAuthenticationError
    with patch.object(step, "_validate_declarative_config_repo") as mock_validate:
        from src.action.steps.git_validation import GitAuthenticationError
        mock_validate.side_effect = GitAuthenticationError(
            "Git authentication failed: credentials invalid"
        )

        result = await step.rollback("deployment.yaml", "abc123")

        assert result.success is False
        assert result.status == "failed"
        assert "validation failed" in result.error.lower()
        assert "authentication" in result.error.lower()


@pytest.mark.asyncio
async def test_rollback_succeeds_after_validation_passes(tmp_path, caplog):
    """Rollback should proceed when validation passes."""
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text("current manifest\n")
    step = GitOpsCommitStep(declarative_config_path=str(tmp_path))

    # Mock validation to pass (no exception)
    with patch.object(step, "_validate_declarative_config_repo"), \
         patch("src.action.steps.gitops.subprocess.run") as run:
        run.side_effect = [
            SimpleNamespace(returncode=0, stdout="parent manifest\n", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]
        with patch.object(step, "_push_changes"):
            result = await step.rollback("deployment.yaml", "abc123")

            assert result.success is True
            assert manifest.read_text() == "parent manifest\n"
