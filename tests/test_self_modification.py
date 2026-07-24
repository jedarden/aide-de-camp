"""
Unit tests for the LLM-driven SelfModificationAgent.

These tests verify that `_parse_instruction` and `_generate_update` make real
ZAI proxy calls (via the injected client) instead of falling back to the old
keyword-heuristic stubs, and that a nontrivial instruction produces a
substantive, on-topic diff rather than the old generic
"# User feedback: ..." comment append.

The ZAI client is mocked so the tests are deterministic and network-free.
"""

import json
import subprocess
import tempfile
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.self_modification import (
    ArtifactDiff,
    ArtifactType,
    ModificationRequest,
    SelfModificationAgent,
    GitResult,
    run_git_command,
    git_status,
    git_add,
    git_commit,
    git_show,
    git_rev_parse,
)
from src.components.hot_reload import HotReloadManager
from src.escalate.llm import ModelClass

# A nontrivial instruction that does NOT match any of the four old hardcoded
# trigger phrases ("restart"+"count", "alias", "verbose"/"more detail"). Under
# the old heuristic engine it would fall through to the generic
# "# User feedback: ..." comment append.
NONTRIVIAL_INSTRUCTION = (
    "when a pod has more than 3 restarts, mark the result urgency as high "
    "instead of normal"
)


@pytest.fixture
def temp_urgency_md():
    """Create a temporary urgency.md for the agent to target."""
    content = (
        "# Urgency Classifier\n\n"
        "## Tiers\n\n"
        "### Normal\nPods running normally.\n\n"
        "### High\nPods restarting repeatedly.\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def agent(temp_urgency_md):
    """A SelfModificationAgent wired to an isolated HotReloadManager.

    `_zai_client` is left None so each test can inject a mock; `_get_zai_client`
    returns `self._zai_client` directly when it is set.
    """
    a = SelfModificationAgent()
    mgr = HotReloadManager()
    mgr.register_prompt("urgency", temp_urgency_md)
    a.reload_mgr = mgr
    a._zai_client = None
    return a


class TestParseInstruction:
    """`_parse_instruction` must classify via an LLM call, not substring matching."""

    @pytest.mark.asyncio
    async def test_calls_llm_and_classifies_target(self, agent):
        captured = {}

        async def fake_call_simple(system_prompt, user_message, **kwargs):
            captured["system_prompt"] = system_prompt
            captured["user_message"] = user_message
            captured["model"] = kwargs.get("model")
            return json.dumps(
                {
                    "artifact_type": "prompt",
                    "artifact_name": "urgency",
                    "reasoning": "instruction concerns urgency classification",
                }
            )

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        request = await agent._parse_instruction(NONTRIVIAL_INSTRUCTION)

        # A real LLM call was made with the parse system prompt.
        assert captured["model"] == ModelClass.HAIKU.value
        assert "Registered Artifacts" in captured["user_message"]
        assert NONTRIVIAL_INSTRUCTION in captured["user_message"]

        # Classification reflects the LLM response, not keyword matching.
        assert request.artifact_type == ArtifactType.PROMPT
        assert request.artifact_name == "urgency"
        assert request.instruction == NONTRIVIAL_INSTRUCTION

    @pytest.mark.asyncio
    async def test_unregistered_name_falls_back_to_router(self, agent):
        async def fake_call_simple(system_prompt, user_message, **kwargs):
            return json.dumps(
                {
                    "artifact_type": "prompt",
                    "artifact_name": "does-not-exist",
                    "reasoning": "n/a",
                }
            )

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        request = await agent._parse_instruction(NONTRIVIAL_INSTRUCTION)

        # The agent must not target a non-existent artifact.
        assert request.artifact_name in agent.reload_mgr.list_artifacts()

    @pytest.mark.asyncio
    async def test_malformed_llm_response_degrades_gracefully(self, agent):
        async def fake_call_simple(system_prompt, user_message, **kwargs):
            return "this is not JSON at all"

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        request = await agent._parse_instruction(NONTRIVIAL_INSTRUCTION)

        # Should fall back to the router prompt rather than raise.
        assert request.artifact_type == ArtifactType.PROMPT
        assert request.artifact_name == "router"
        assert request.context.get("fallback") is True


class TestGenerateUpdate:
    """`_generate_update` must rewrite content via an LLM call."""

    @pytest.mark.asyncio
    async def test_produces_substantive_diff_not_boilerplate(self, agent, temp_urgency_md):
        original = agent.reload_mgr.get_prompt("urgency")

        # Simulate the LLM making a real, on-topic edit to the prompt body.
        modified = original.replace(
            "Pods restarting repeatedly.",
            "Pods restarting repeatedly. If a pod has more than 3 restarts, "
            "classify urgency as high.",
        )

        captured = {}

        async def fake_call_simple(system_prompt, user_message, **kwargs):
            captured["model"] = kwargs.get("model")
            captured["user_message"] = user_message
            return json.dumps(
                {
                    "updated_content": modified,
                    "change_summary": "Treat pods with >3 restarts as high urgency",
                }
            )

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        request = ModificationRequest(
            instruction=NONTRIVIAL_INSTRUCTION,
            artifact_name="urgency",
            artifact_type=ArtifactType.PROMPT,
            context={},
        )
        updated, summary = await agent._generate_update(request, original)

        # A real LLM call was made (SONNET for rewriting) carrying the current
        # content and the instruction.
        assert captured["model"] == ModelClass.SONNET.value
        assert NONTRIVIAL_INSTRUCTION in captured["user_message"]
        assert original in captured["user_message"]

        # The returned content is the substantive rewrite...
        assert updated == modified
        assert "3 restarts" in updated

        # ...and explicitly NOT the old boilerplate comment append.
        assert updated != original + f"\n\n# User feedback: {NONTRIVIAL_INSTRUCTION}"
        assert "# User feedback:" not in updated
        assert "high" in summary.lower()

    @pytest.mark.asyncio
    async def test_empty_updated_content_leaves_artifact_unchanged(self, agent, temp_urgency_md):
        original = agent.reload_mgr.get_prompt("urgency")

        async def fake_call_simple(system_prompt, user_message, **kwargs):
            # LLM returned valid JSON but no usable content.
            return json.dumps({"updated_content": "", "change_summary": "no-op"})

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        request = ModificationRequest(
            instruction=NONTRIVIAL_INSTRUCTION,
            artifact_name="urgency",
            artifact_type=ArtifactType.PROMPT,
            context={},
        )
        updated, _ = await agent._generate_update(request, original)

        # Should not fabricate a change.
        assert updated == original


class TestProcessInstructionEndToEnd:
    """The full instruction → diff pipeline uses two real LLM calls."""

    @pytest.mark.asyncio
    async def test_nontrivial_instruction_yields_on_topic_diff(self, agent, temp_urgency_md):
        original = agent.reload_mgr.get_prompt("urgency")
        modified = original.replace(
            "Pods restarting repeatedly.",
            "Pods restarting repeatedly. If a pod has more than 3 restarts, "
            "classify urgency as high.",
        )

        calls = []

        async def fake_call_simple(system_prompt, user_message, **kwargs):
            calls.append(kwargs.get("model"))
            if kwargs.get("model") == ModelClass.HAIKU.value:
                # Parse call
                return json.dumps(
                    {
                        "artifact_type": "prompt",
                        "artifact_name": "urgency",
                        "reasoning": "urgency-related",
                    }
                )
            # Generate call
            return json.dumps(
                {
                    "updated_content": modified,
                    "change_summary": "Added high-urgency rule for pods with >3 restarts",
                }
            )

        agent._zai_client = MagicMock()
        agent._zai_client.call_simple = fake_call_simple

        diff = await agent.process_instruction(NONTRIVIAL_INSTRUCTION)

        # Two distinct LLM calls: one to parse, one to generate.
        assert calls == [ModelClass.HAIKU.value, ModelClass.SONNET.value]

        assert diff.artifact_type == ArtifactType.PROMPT
        assert diff.artifact_name == "urgency"
        assert diff.before == original
        assert diff.after == modified
        assert diff.after != original

        # Defining regression check: the result is a substantive, on-topic diff,
        # NOT the old generic "# User feedback: ..." comment append that the
        # heuristic stub would have produced for this instruction.
        assert "# User feedback:" not in diff.after
        assert "3 restarts" in diff.after


class TestGitCommits:
    """Git commits are created for prompt and config writes."""

    @pytest.fixture
    def test_prompt_file(self):
        """Create a test prompt file in the prompts directory."""
        test_prompt_path = Path("/home/coding/aide-de-camp/prompts/test_git_commit_prompt.md")
        original_content = test_prompt_path.read_text() if test_prompt_path.exists() else None

        yield test_prompt_path

        # Cleanup: remove the test file (git keeps it in history)
        if test_prompt_path.exists():
            test_prompt_path.unlink()

    @pytest.fixture
    def test_config_file(self):
        """Create a test config file in the config directory."""
        test_config_path = Path("/home/coding/aide-de-camp/config/test_git_commit_config.yaml")
        original_content = test_config_path.read_text() if test_config_path.exists() else None

        yield test_config_path

        # Cleanup: remove the test file (git keeps it in history)
        if test_config_path.exists():
            test_config_path.unlink()

    def test_write_prompt_creates_git_commit(self, test_prompt_file):
        """Writing a prompt file creates a git commit."""
        # Create initial content
        test_prompt_file.write_text("# Test Prompt\n\nInitial content.")

        # Create agent and register the prompt
        agent = SelfModificationAgent()
        mgr = HotReloadManager()
        mgr.register_prompt("test_git_commit_prompt", str(test_prompt_file))
        agent.reload_mgr = mgr

        # Track subprocess calls
        subprocess_calls = []
        original_run = subprocess.run

        def mock_run(cmd, *args, **kwargs):
            subprocess_calls.append((cmd, kwargs.get('cwd')))
            # Mock successful git operations
            if 'git' in cmd and 'commit' in cmd:
                result = MagicMock(returncode=0, stdout=b"", stderr=b"")
            elif 'git' in cmd and 'rev-parse' in cmd:
                result = MagicMock(returncode=0, stdout=b"abc1234\n", stderr=b"")
            else:
                result = MagicMock(returncode=0, stdout=b"", stderr=b"")
            return result

        # Create a diff representing a change
        diff = ArtifactDiff(
            artifact_name="test_git_commit_prompt",
            artifact_type=ArtifactType.PROMPT,
            before="# Test Prompt\n\nInitial content.",
            after="# Test Prompt\n\nUpdated content for git commit test.",
            change_summary="Update test prompt for git commit",
            confidence=0.9
        )

        with unittest.mock.patch('subprocess.run', side_effect=mock_run):
            result = agent._write_prompt(diff)

        # Verify the write was successful
        assert result is True

        # Verify git commands were called
        git_commands = [call[0] for call in subprocess_calls if 'git' in call[0]]
        assert len(git_commands) >= 2  # At minimum: git add and git commit

        # Verify git commit was called with a message
        commit_calls = [call for call in git_commands if 'commit' in call]
        assert len(commit_calls) >= 1

    def test_write_config_creates_git_commit(self, test_config_file):
        """Writing a config file creates a git commit."""
        # Create initial content
        test_config_file.write_text("key: value\noriginal: true")

        # Create agent and register the config
        agent = SelfModificationAgent()
        mgr = HotReloadManager()
        mgr.register_prompt("test_git_commit_config", str(test_config_file))
        agent.reload_mgr = mgr

        # Track subprocess calls
        subprocess_calls = []

        def mock_run(cmd, *args, **kwargs):
            subprocess_calls.append((cmd, kwargs.get('cwd')))
            # Mock successful git operations
            if 'git' in cmd and 'commit' in cmd:
                result = MagicMock(returncode=0, stdout=b"", stderr=b"")
            elif 'git' in cmd and 'rev-parse' in cmd:
                result = MagicMock(returncode=0, stdout=b"abc1234\n", stderr=b"")
            else:
                result = MagicMock(returncode=0, stdout=b"", stderr=b"")
            return result

        # Create a diff representing a change
        diff = ArtifactDiff(
            artifact_name="test_git_commit_config",
            artifact_type=ArtifactType.CONFIG,
            before="key: value\noriginal: true",
            after="key: new_value\noriginal: false",
            change_summary="Update test config for git commit",
            confidence=0.8
        )

        with unittest.mock.patch('subprocess.run', side_effect=mock_run):
            result = agent._write_config(diff)

        # Verify the write was successful
        assert result is True

        # Verify git commands were called
        git_commands = [call[0] for call in subprocess_calls if 'git' in call[0]]
        assert len(git_commands) >= 2  # At minimum: git add and git commit

        # Verify git commit was called
        commit_calls = [call for call in git_commands if 'commit' in call]
        assert len(commit_calls) >= 1

    def test_failed_write_does_not_create_commit(self, test_prompt_file):
        """A failed write operation should NOT create a git commit."""
        # Create initial content
        test_prompt_file.write_text("# Test Prompt\n\nInitial content.")

        # Create agent and register the prompt
        agent = SelfModificationAgent()
        mgr = HotReloadManager()
        mgr.register_prompt("test_git_commit_prompt", str(test_prompt_file))
        agent.reload_mgr = mgr

        # Track subprocess calls - should NOT see git commit
        subprocess_calls = []

        def mock_run(cmd, *args, **kwargs):
            subprocess_calls.append((cmd, kwargs.get('cwd')))
            result = MagicMock(returncode=0, stdout=b"", stderr=b"")
            return result

        # Create a diff for a NON-EXISTENT artifact (this should fail)
        diff = ArtifactDiff(
            artifact_name="nonexistent_artifact",
            artifact_type=ArtifactType.PROMPT,
            before="some content",
            after="updated content",
            change_summary="This should fail",
            confidence=0.9
        )

        with unittest.mock.patch('subprocess.run', side_effect=mock_run):
            result = agent.apply_diff(diff)

        # Verify the write failed
        assert result is False

        # Verify NO git commit was called
        git_commands = [call[0] for call in subprocess_calls if 'git' in call[0]]
        commit_calls = [call for call in git_commands if 'commit' in call]
        assert len(commit_calls) == 0

    def test_commit_message_format_with_sha(self, test_prompt_file):
        """Git commit messages include the correct format with previous SHA."""
        # Create initial content
        test_prompt_file.write_text("# Test Prompt\n\nInitial content.")

        # Create agent and register the prompt
        agent = SelfModificationAgent()
        mgr = HotReloadManager()
        mgr.register_prompt("test_git_commit_prompt", str(test_prompt_file))
        agent.reload_mgr = mgr

        # Track the commit message
        captured_commit_msg = []

        def mock_run(cmd, *args, **kwargs):
            # Capture git commit command with message
            if 'git' in cmd and 'commit' in cmd and '-m' in cmd:
                msg_idx = cmd.index('-m') + 1
                if msg_idx < len(cmd):
                    captured_commit_msg.append(cmd[msg_idx])

            if 'git' in cmd and 'commit' in cmd:
                from subprocess import CompletedProcess
                result = CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            elif 'git' in cmd and 'rev-parse' in cmd:
                # Return a fake previous SHA (as string, since text=True is used)
                from subprocess import CompletedProcess
                result = CompletedProcess(cmd, returncode=0, stdout="prev123\n", stderr="")
            else:
                from subprocess import CompletedProcess
                result = CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            return result

        # Create a diff
        diff = ArtifactDiff(
            artifact_name="test_git_commit_prompt",
            artifact_type=ArtifactType.PROMPT,
            before="# Test Prompt\n\nInitial content.",
            after="# Test Prompt\n\nUpdated content for format test.",
            change_summary="Test commit message format",
            confidence=0.9
        )

        with unittest.mock.patch('subprocess.run', side_effect=mock_run):
            result = agent._write_prompt(diff)
            assert result is True

        # Verify commit message was captured
        assert len(captured_commit_msg) >= 1
        message = captured_commit_msg[0]

        # Verify commit message format: "auto: self-mod write to <path> [<prev-sha>]"
        assert message.startswith("auto: self-mod write to")
        assert "prompts/test_git_commit_prompt.md" in message
        # Should include a SHA in brackets (the previous commit SHA)
        assert "[prev123]" in message


class TestGitUtilityFunctions:
    """Git subprocess utility functions are testable in isolation."""

    def test_run_git_command_success(self):
        """run_git_command executes successfully and returns structured output."""
        result = run_git_command(['status', '--short'])

        assert result.success is True
        assert result.returncode == 0
        assert result.timed_out is False
        assert isinstance(result.stdout, str)
        assert isinstance(result.stderr, str)

    def test_run_git_command_non_zero_exit(self):
        """run_git_command handles non-zero exit codes gracefully."""
        # 'git' with no arguments should fail
        result = run_git_command(['invalid-subcommand'])

        assert result.success is False
        assert result.returncode != 0
        assert result.timed_out is False

    def test_run_git_command_timeout(self):
        """run_git_command handles timeouts."""
        # Use a very short timeout; git operations shouldn't normally timeout
        result = run_git_command(['status'], timeout=0.001)

        assert result.success is False
        assert result.timed_out is True

    def test_git_status_executes_and_returns_output(self):
        """git_status executes 'git status' and returns output."""
        result = git_status(short=True)

        assert result.success is True
        assert result.returncode == 0
        assert isinstance(result.stdout, str)

    def test_git_status_long_format(self):
        """git_status supports long format output."""
        result = git_status(short=False)

        assert result.success is True
        assert result.returncode == 0
        # Long format should have more verbose output
        assert len(result.stdout) > 0

    def test_git_add_files(self, tmp_path):
        """git_add stages files for commit."""
        # Initialize a git repo first
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=tmp_path, capture_output=True)

        # Create a test file
        test_file = tmp_path / "test_add.txt"
        test_file.write_text("test content")

        result = git_add([str(test_file)], cwd=tmp_path)

        assert result.success is True
        assert result.returncode == 0

    def test_git_commit_creates_commit(self, tmp_path):
        """git_commit creates a commit with a message."""
        # Initialize a git repo
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=tmp_path, capture_output=True)

        # Create and stage a file
        test_file = tmp_path / "test_commit.txt"
        test_file.write_text("test content")
        git_add([str(test_file)], cwd=tmp_path)

        # Create commit
        result = git_commit("Test commit message", cwd=tmp_path)

        assert result.success is True
        assert result.returncode == 0

    def test_git_commit_with_specific_paths(self, tmp_path):
        """git_commit can commit specific paths."""
        # Initialize a git repo
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=tmp_path, capture_output=True)

        # Create and stage multiple files
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content 1")
        file2.write_text("content 2")

        git_add([str(file1), str(file2)], cwd=tmp_path)

        # Commit only file1
        result = git_commit("Commit file1", paths=["file1.txt"], cwd=tmp_path)

        assert result.success is True
        assert result.returncode == 0

    def test_git_rev_parse_short_sha(self, tmp_path):
        """git_rev_parse returns short SHA."""
        # Initialize a git repo with a commit
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=tmp_path, capture_output=True)

        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        git_add([str(test_file)], cwd=tmp_path)
        git_commit("Initial commit", cwd=tmp_path)

        result = git_rev_parse('HEAD', short=True, cwd=tmp_path)

        assert result.success is True
        assert result.returncode == 0
        # Short SHA should be 7 characters
        assert len(result.stdout.strip()) == 7

    def test_git_show_file_content(self, tmp_path):
        """git_show returns file content from a reference."""
        # Initialize a git repo with a file
        subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=tmp_path, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=tmp_path, capture_output=True)

        test_file = tmp_path / "test.txt"
        test_content = "test content for git show"
        test_file.write_text(test_content)
        git_add([str(test_file)], cwd=tmp_path)
        git_commit("Add test file", cwd=tmp_path)

        result = git_show('HEAD:test.txt', cwd=tmp_path)

        assert result.success is True
        assert result.returncode == 0
        assert test_content in result.stdout

    def test_git_result_dataclass(self):
        """GitResult dataclass correctly stores all fields."""
        result = GitResult(
            success=True,
            stdout="test output",
            stderr="test error",
            returncode=0,
            timed_out=False
        )

        assert result.success is True
        assert result.stdout == "test output"
        assert result.stderr == "test error"
        assert result.returncode == 0
        assert result.timed_out is False
