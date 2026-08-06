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
from unittest.mock import AsyncMock, MagicMock, patch

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
def hot_reload_manager(temp_router_md, temp_urgency_md):
    """Hot-reload manager seeded with the temp router.md and urgency.md."""
    mgr = HotReloadManager()
    mgr.register_prompt("router", temp_router_md)
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


def patch_deterministic_router():
    """
    Context manager to disable deterministic router for testing.
    Forces all requests through LLM path.
    """
    from src.intent.deterministic_router import FastPathResult

    def mock_get_det_router():
        mock_router = MagicMock()
        mock_router.route_utterance.return_value = FastPathResult(
            success=False,
            intents=[],
            confidence=0.0,
            reasoning="LLM path forced for test"
        )
        mock_router.get_stats.return_value = {
            "total_calls": 0,
            "fast_path_hits": 0,
            "hit_rate": 0.0,
        }
        return mock_router

    return patch('src.intent.deterministic_router.get_deterministic_router', side_effect=mock_get_det_router)


@pytest.fixture
def router_with_det_disabled(temp_router_md, hot_reload_manager):
    """
    An IntentRouter with deterministic router disabled to force LLM path.
    Used for testing hot-reload behavior without fast-path interference.
    """
    from src.intent.deterministic_router import FastPathResult

    r = IntentRouter(prompt_path=Path(temp_router_md))
    r._reload_manager = hot_reload_manager
    store = MagicMock()
    store.get_session = AsyncMock(return_value=None)
    r.store = store

    # Mock get_deterministic_router to always return failure
    async def mock_get_det_router():
        mock_router = MagicMock()
        mock_router.route_utterance.return_value = FastPathResult(
            success=False,
            intents=[],
            confidence=0.0,
            reasoning="LLM path forced"
        )
        mock_router.get_stats.return_value = {
            "total_calls": 0,
            "fast_path_hits": 0,
            "hit_rate": 0.0,
        }
        return mock_router

    # Patch the import in router.py
    import src.intent.router as router_module
    with patch.object(router_module, 'get_deterministic_router', mock_get_det_router):
        yield r


@pytest.fixture
def mock_zai_client():
    """A ZAI client whose call_simple we can swap to capture the system prompt."""
    return AsyncMock()


def _intent_response():
    """A minimal valid router LLM response (single status intent)."""
    return {
        "content": json.dumps([
            {
                "intent_type": "status",
                "project_slug": None,
                "urgency": "normal",
                "utterance_fragment": "test utterance",
                "confidence": 0.9,
                "reasoning": "test",
            }
        ]),
        "timing_network_ms": 100,
        "timing_inference_ms": 200,
    }


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

        # Force reload to bypass throttle interval (simulating elapsed time)
        router._reload_manager.force_reload("router")

        second = router._load_router_prompt()
        assert "TEST CONTENT B - EDITED" in second
        assert "TEST CONTENT A" not in second

    def test_router_prompt_falls_back_when_file_missing(self, router):
        """If router.md vanishes, we get the fallback (no crash)."""
        # Set a non-existent path and bypass the hot_reload_manager
        router.prompt_path = Path("/nonexistent/path/router.md")
        router._reload_manager = None  # Force fallback behavior
        loaded = router._load_router_prompt()
        # Check that we got a fallback prompt (not empty, not error)
        assert loaded is not None
        assert len(loaded) > 0
        # The fallback should contain core routing keywords
        assert "Intent Router" in loaded or "intent" in loaded.lower()


# --- _build_system_prompt: segmentation + urgency splice --------------------

class TestBuildSystemPrompt:
    """The assembled system prompt contains router.md *and* urgency.md."""

    def test_build_includes_router_md_content(self, router):
        prompt = router._build_system_prompt()
        assert "TEST CONTENT A" in prompt

    def test_build_includes_router_md_content(self, router):
        """_build_system_prompt returns the router.md content."""
        prompt = router._build_system_prompt()
        assert "TEST CONTENT A" in prompt

    def test_build_reflects_router_md_edit(self, router, temp_router_md):
        Path(temp_router_md).write_text(ROUTER_MD_EDITED)

        # Force reload to bypass throttle interval
        router._reload_manager.force_reload("router")

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
        router._router_zai_client = mock_zai_client

        await router.classify_utterance("test utterance", "session-123")

        assert "TEST CONTENT A" in captured.get("system_prompt", "")

    @pytest.mark.asyncio
    async def test_router_md_edit_reaches_llm_without_restart(
        self, router, mock_zai_client, temp_router_md
    ):
        captured = []

        async def capture(system_prompt, user_message, **kwargs):
            captured.append(system_prompt)
            return _intent_response()

        mock_zai_client.call_simple = capture
        router._router_zai_client = mock_zai_client

        # First call: on-disk router.md is the initial version.
        await router.classify_utterance("test utterance", "session-123")

        # Self-mod agent edits router.md while the server keeps running.
        Path(temp_router_md).write_text(ROUTER_MD_EDITED)

        # Force reload to bypass throttle interval
        router._reload_manager.force_reload("router")

        # Clear the router cache to allow re-classification of same utterance
        router._clear_cache()

        # Second call: must pick up the edit -- no restart, no reload flag.
        await router.classify_utterance("test utterance", "session-123")

        assert len(captured) == 2
        first, second = captured
        assert "TEST CONTENT A" in first
        assert "TEST CONTENT B - EDITED" in second
        assert "TEST CONTENT A" not in second


# --- integration: routing behavior changes with prompt edits --------------------

class TestRoutingBehaviorHotReload:
    """
    Integration tests that verify routing BEHAVIOR changes when router.md is edited.

    These are the true acceptance criteria for hot-reload: not only does the prompt
    content change, but the routing decisions themselves change based on the new
    instructions.
    """

    @pytest.mark.asyncio
    async def test_routing_changes_with_prompt_edit_without_restart(
        self, router, mock_zai_client, temp_router_md
    ):
        """
        THE core integration test for hot-reload:

        1. Dispatch an utterance → gets classification based on original prompt
        2. Edit router.md to change routing rules
        3. Re-dispatch the SAME utterance → gets different classification
        4. Revert the edit

        This proves hot-reload affects routing behavior, not just prompt text.
        """
        # Use patch_deterministic_router to disable fast-path
        with patch_deterministic_router():
            ROUTER_MD_STATUS_BIASED = """\
# Intent Router System Prompt (status-biased test)

You are the Intent Router for aide-de-camp.

BIAS: Classify ALL status-check utterances as intent_type="status".

Types: status|action|brainstorm|lookup|reminder|task-profile

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>"}
"""

            ROUTER_MD_ACTION_BIASED = """\
# Intent Router System Prompt (action-biased test)

You are the Intent Router for aide-de-camp.

BIAS: Classify ALL status-check utterances as intent_type="action".

Types: status|action|brainstorm|lookup|reminder|task-profile

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>"}
"""

            # Track all LLM calls and their responses
            llm_calls = []
            response_sequence = []

            async def mock_llm_call(system_prompt, user_message, **kwargs):
                """Mock that returns different classifications based on prompt content."""
                llm_calls.append({"system_prompt": system_prompt, "user_message": user_message})

                # Check which bias is in the prompt and return corresponding classification
                if "status-biased" in system_prompt:
                    response_sequence.append("status")
                    return {
                        "content": json.dumps([{
                            "intent_type": "status",
                            "project_slug": None,
                            "urgency": "normal",
                            "utterance_fragment": "check the pods",
                            "confidence": 0.9,
                            "reasoning": "Status-biased prompt routed to status",
                        }]),
                        "timing_network_ms": 100,
                        "timing_inference_ms": 200,
                    }
                elif "action-biased" in system_prompt:
                    response_sequence.append("action")
                    return {
                        "content": json.dumps([{
                            "intent_type": "action",
                            "project_slug": None,
                            "urgency": "normal",
                            "utterance_fragment": "check the pods",
                            "confidence": 0.9,
                            "reasoning": "Action-biased prompt routed to action",
                        }]),
                        "timing_network_ms": 100,
                        "timing_inference_ms": 200,
                    }
                else:
                    # Fallback
                    response_sequence.append("status")
                    return {
                        "content": json.dumps([{
                            "intent_type": "status",
                            "project_slug": None,
                            "urgency": "normal",
                            "utterance_fragment": "check the pods",
                            "confidence": 0.9,
                            "reasoning": "Default routing",
                        }]),
                        "timing_network_ms": 100,
                        "timing_inference_ms": 200,
                    }

            mock_zai_client.call_simple = mock_llm_call
            router._router_zai_client = mock_zai_client

            # Step 1: Initial dispatch with status-biased prompt
            Path(temp_router_md).write_text(ROUTER_MD_STATUS_BIASED)
            router._reload_manager.force_reload("router")

            classifications1, _ = await router.classify_utterance(
                "check the pods", "session-123"
            )

            assert len(classifications1) == 1
            assert classifications1[0].intent_type.value == "status"
            assert response_sequence == ["status"]

            # Step 2: Edit router.md to action-biased (simulating hot-reload edit)
            Path(temp_router_md).write_text(ROUTER_MD_ACTION_BIASED)

            # Force reload to bypass throttle interval
            router._reload_manager.force_reload("router")

            # Clear cache to allow re-classification
            router._clear_cache()

            # Step 3: Re-dispatch the SAME utterance
            classifications2, _ = await router.classify_utterance(
                "check the pods", "session-123"
            )

            assert len(classifications2) == 1
            assert classifications2[0].intent_type.value == "action"
            assert response_sequence == ["status", "action"]

            # Step 4: Revert to original (status-biased)
            Path(temp_router_md).write_text(ROUTER_MD_STATUS_BIASED)

            # Force reload to bypass throttle interval
            router._reload_manager.force_reload("router")

            # Clear cache to allow re-classification
            router._clear_cache()

            # Step 5: Third dispatch confirms revert worked
            classifications3, _ = await router.classify_utterance(
                "check the pods", "session-123"
            )

            assert len(classifications3) == 1
            assert classifications3[0].intent_type.value == "status"
            assert response_sequence == ["status", "action", "status"]

            # Verify we made exactly 3 LLM calls (no caching interference)
            assert len(llm_calls) == 3

            # Verify all three calls used the SAME utterance
            assert all(call["user_message"] == "Classify this utterance:\n\ncheck the pods"
                       for call in llm_calls)

            # Verify the system prompts changed
            assert "status-biased" in llm_calls[0]["system_prompt"]
            assert "action-biased" in llm_calls[1]["system_prompt"]
            assert "status-biased" in llm_calls[2]["system_prompt"]

    @pytest.mark.asyncio
    async def test_hot_reload_with_cache_invalidation(
        self, router, mock_zai_client, temp_router_md
    ):
        """
        Verify that hot-reload works even when the router cache is active.

        This ensures that prompt edits are detected even when classification
        results might be cached.
        """
        # Use patch_deterministic_router to disable fast-path
        with patch_deterministic_router():
            ROUTER_V1 = """\
# Router v1
Classify "check logs" as lookup.
"""
            ROUTER_V2 = """\
# Router v2
Classify "check logs" as status.
"""

            call_count = [0]

            async def mock_llm_call(system_prompt, user_message, **kwargs):
                call_count[0] += 1
                if "Router v1" in system_prompt:
                    return {
                        "content": json.dumps([{
                            "intent_type": "lookup",
                            "lookup_kind": "logs",
                            "project_slug": None,
                            "urgency": "normal",
                            "utterance_fragment": "check logs",
                        }]),
                        "timing_network_ms": 100,
                        "timing_inference_ms": 200,
                    }
                else:
                    return {
                        "content": json.dumps([{
                            "intent_type": "status",
                            "project_slug": None,
                            "urgency": "normal",
                            "utterance_fragment": "check logs",
                        }]),
                        "timing_network_ms": 100,
                        "timing_inference_ms": 200,
                    }

            mock_zai_client.call_simple = mock_llm_call
            router._router_zai_client = mock_zai_client

            # Initial state
            Path(temp_router_md).write_text(ROUTER_V1)
            router._reload_manager.force_reload("router")

            # First call - caches the result
            classifications1, _ = await router.classify_utterance("check logs", "session-1")
            assert classifications1[0].intent_type.value == "lookup"
            assert call_count[0] == 1

            # Cache hit - should not call LLM
            classifications2, _ = await router.classify_utterance("check logs", "session-1")
            assert classifications2[0].intent_type.value == "lookup"
            # Note: cache hit means no LLM call, so call_count stays at 1

            # Edit the prompt
            Path(temp_router_md).write_text(ROUTER_V2)

            # Force reload to pick up the new prompt
            router._reload_manager.force_reload("router")

            # Wait for hot-reload throttle interval
            import asyncio
            await asyncio.sleep(1.5)

            # Different session - cache miss, should pick up new prompt
            classifications3, _ = await router.classify_utterance("check logs", "session-2")
            assert classifications3[0].intent_type.value == "status"
            assert call_count[0] == 2  # New LLM call with new prompt

            # Verify cache isolation - session-1 still has cached result
            classifications4, _ = await router.classify_utterance("check logs", "session-1")
            assert classifications4[0].intent_type.value == "lookup"
            # Cache hit for session-1, no new LLM call

    @pytest.mark.asyncio
    async def test_multiple_prompt_edits_in_sequence(
        self, router, mock_zai_client, temp_router_md
    ):
        """
        Test that multiple rapid edits to router.md are all picked up correctly.

        This simulates a self-modification agent making several iterative edits
        to refine routing behavior.
        """
        # Use patch_deterministic_router to disable fast-path
        with patch_deterministic_router():
            # Map iteration index to valid intent types
            intent_type_sequence = ["status", "action", "brainstorm", "lookup", "reminder"]
            prompts = [
                f"# Router v{i}\nClassify as intent_type={intent_type_sequence[i]}."
                for i in range(5)
            ]

            call_count = [0]

            async def mock_llm_call(system_prompt, user_message, **kwargs):
                call_count[0] += 1
                # Extract version number from prompt
                for i in range(5):
                    if f"Router v{i}" in system_prompt:
                        return {
                            "content": json.dumps([{
                                "intent_type": intent_type_sequence[i],
                                "project_slug": None,
                                "urgency": "normal",
                                "utterance_fragment": "test",
                            }]),
                            "timing_network_ms": 100,
                            "timing_inference_ms": 200,
                        }
                return {
                    "content": json.dumps([{
                        "intent_type": "status",
                        "project_slug": None,
                        "urgency": "normal",
                        "utterance_fragment": "test",
                    }]),
                    "timing_network_ms": 100,
                    "timing_inference_ms": 200,
                }

            mock_zai_client.call_simple = mock_llm_call
            router._router_zai_client = mock_zai_client

            results = []
            for i, prompt_content in enumerate(prompts):
                # Edit the prompt
                Path(temp_router_md).write_text(prompt_content)

                # Force reload to pick up the new prompt
                router._reload_manager.force_reload("router")

                # Wait for hot-reload throttle interval
                import asyncio
                await asyncio.sleep(1.5)

                # Clear cache for each iteration to allow re-classification
                router._clear_cache()

                # Classify with new prompt
                classifications, _ = await router.classify_utterance("test", "session-1")

                results.append(classifications[0].intent_type.value)
                assert classifications[0].intent_type.value == intent_type_sequence[i]

            # Verify all 5 versions were detected
            assert results == intent_type_sequence
            assert call_count[0] == 5
