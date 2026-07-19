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
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.self_modification import (
    ArtifactType,
    ModificationRequest,
    SelfModificationAgent,
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
