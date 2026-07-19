"""
Regression tests for prompts/router.md hot-reload in the IntentRouter.

These lock down the core fix for bead adc-3a3d: the router must NOT hardcode its
segmentation system prompt -- it must read prompts/router.md on each
classify_utterance() call so edits take effect without a server restart.

The sibling file tests/test_urgency_hotreload.py covers the *urgency.md* splicing
path (and even uses the production prompts/router.md without ever mutating it).
These tests cover the orthogonal concern -- the router's own segmentation prompt
file -- which previously lived as a hardcoded ROUTER_SYSTEM_PROMPT constant and
silently no-op'd the self-modification agent's edits to prompts/router.md.

No live LLM calls: the ZAI client is mocked and we assert on the system_prompt
string that the router *would* have sent.
"""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.hot_reload import HotReloadManager
from src.intent.router import IntentRouter, _ROUTER_PROMPT_FALLBACK


# --- fixtures ---------------------------------------------------------------

ROUTER_MD_INITIAL = """\
# Intent Router System Prompt (test)

You are the Intent Router for aide-de-camp (TEST CONTENT A).

Return ONLY a JSON array of intent objects.
"""

ROUTER_MD_EDITED = """\
# Intent Router System Prompt (test, edited)

You are the Intent Router for aide-de-camp (TEST CONTENT B - EDITED ON DISK).

Segmentation rules have changed. Return ONLY a JSON array.
"""

URGENCY_MD = """\
# Urgency Classifier Test

### Critical (urgency: "critical")
Test content for critical urgency.
"""


@pytest.fixture
def temp_router_md():
    """A throwaway router.md the IntentRouter reads from."""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(ROUTER_MD_INITIAL)
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def temp_urgency_md():
    """A throwaway urgency.md so _build_system_prompt stays hermetic."""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(URGENCY_MD)
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def hot_reload_manager(temp_urgency_md):
    """Hot-reload manager seeded only with the temp urgency.md."""
    mgr = HotReloadManager()
    mgr.register_prompt("urgency", temp_urgency_md)
    return mgr


@pytest.fixture
def router(temp_router_md, hot_reload_manager):
    """
    An IntentRouter pointed at the temp router.md, with a mock store so
    classify_utterance() never touches the real session.db.
    """
    r = IntentRouter(prompt_path=Path(temp_router_md))
    r._reload_manager = hot_reload_manager
    # Hermetic store: get_session -> None so no session context is appended.
    store = MagicMock()
    store.get_session = AsyncMock(return_value=None)
    r.store = store
    return r


@pytest.fixture
def mock_zai_client():
    """A ZAI client whose call_simple we can swap to capture the system prompt."""
    return AsyncMock()


def _intent_response():
    """A minimal valid router LLM response (single status intent)."""
    return json.dumps([
        {
            "intent_type": "status",
            "project_slug": None,
            "urgency": "normal",
            "utterance_fragment": "test utterance",
            "confidence": 0.9,
            "reasoning": "test",
        }
    ])


# --- _load_router_prompt: per-call disk read --------------------------------

class TestRouterPromptReadPerCall:
    """The segmentation prompt comes from prompts/router.md, not a constant."""

    def test_load_router_prompt_reads_file_content(self, router, temp_router_md):
        """_load_router_prompt returns the on-disk router.md content verbatim."""
        loaded = router._load_router_prompt()
        assert "Intent Router for aide-de-camp (TEST CONTENT A)" in loaded
        assert "Return ONLY a JSON array" in loaded

    def test_router_prompt_not_hardcoded_fallback(self, router):
        """
        The loaded prompt is the full on-disk content, not the short
        _ROUTER_PROMPT_FALLBACK constant -- proving we read the file, not a
        hardcoded string.
        """
        loaded = router._load_router_prompt()
        assert "TEST CONTENT A" in loaded
        # The marker lives only in the temp file, never in the fallback constant,
        # so its presence proves we read the file -- and the loaded string is
        # structurally different from the fallback.
        assert "TEST CONTENT A" not in _ROUTER_PROMPT_FALLBACK
        assert loaded != _ROUTER_PROMPT_FALLBACK

    def test_router_prompt_hot_reload_detects_disk_change(
        self, router, temp_router_md
    ):
        """
        THE core regression for adc-3a3d: editing prompts/router.md and
        re-invoking the loader returns the new content (no server restart).
        """
        first = router._load_router_prompt()
        assert "TEST CONTENT A" in first
        assert "TEST CONTENT B - EDITED" not in first

        # Simulate the self-modification agent writing a new router.md.
        Path(temp_router_md).write_text(ROUTER_MD_EDITED)

        second = router._load_router_prompt()
        assert "TEST CONTENT B - EDITED" in second
        assert "TEST CONTENT A" not in second

    def test_router_prompt_falls_back_when_file_missing(self, router):
        """If router.md vanishes, we get the fallback (no crash)."""
        router.prompt_path = Path("/nonexistent/path/router.md")
        loaded = router._load_router_prompt()
        assert loaded == _ROUTER_PROMPT_FALLBACK


# --- _build_system_prompt: segmentation + urgency splice --------------------

class TestBuildSystemPrompt:
    """The assembled system prompt contains router.md *and* urgency.md."""

    def test_build_includes_router_md_content(self, router):
        prompt = router._build_system_prompt()
        assert "TEST CONTENT A" in prompt

    def test_build_includes_urgency_splice(self, router):
        prompt = router._build_system_prompt()
        assert "## Urgency Classification Rules" in prompt
        assert "Urgency Classifier Test" in prompt

    def test_build_reflects_router_md_edit(self, router, temp_router_md):
        Path(temp_router_md).write_text(ROUTER_MD_EDITED)
        prompt = router._build_system_prompt()
        assert "TEST CONTENT B - EDITED" in prompt
        assert "TEST CONTENT A" not in prompt


# --- end-to-end: the prompt actually reaches the LLM call -------------------

class TestRouterMdReachesLLM:
    """
    classify_utterance() sends the router.md-derived system prompt to the ZAI
    client, and editing router.md between two calls changes what is sent
    (acceptance criterion: hot-reload without restart).
    """

    @pytest.mark.asyncio
    async def test_router_md_content_sent_to_llm(self, router, mock_zai_client):
        captured = {}

        async def capture(system_prompt, user_message, **kwargs):
            captured["system_prompt"] = system_prompt
            return _intent_response()

        mock_zai_client.call_simple = capture
        router._zai_client = mock_zai_client

        await router.classify_utterance("test utterance", "session-123")

        assert "TEST CONTENT A" in captured["system_prompt"]

    @pytest.mark.asyncio
    async def test_router_md_edit_reaches_llm_without_restart(
        self, router, mock_zai_client, temp_router_md
    ):
        captured = []

        async def capture(system_prompt, user_message, **kwargs):
            captured.append(system_prompt)
            return _intent_response()

        mock_zai_client.call_simple = capture
        router._zai_client = mock_zai_client

        # First call: on-disk router.md is the initial version.
        await router.classify_utterance("test utterance", "session-123")

        # Self-mod agent edits router.md while the server keeps running.
        Path(temp_router_md).write_text(ROUTER_MD_EDITED)

        # Second call: must pick up the edit -- no restart, no reload flag.
        await router.classify_utterance("test utterance", "session-123")

        assert len(captured) == 2
        first, second = captured
        assert "TEST CONTENT A" in first
        assert "TEST CONTENT B - EDITED" in second
        assert "TEST CONTENT A" not in second
