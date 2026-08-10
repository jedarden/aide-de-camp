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
