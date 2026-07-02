"""
Unit tests for urgency.md hot-reload in router and synthesize strand.

Tests that:
1. prompts/urgency.md is loaded and included in the LLM system prompt
2. Editing prompts/urgency.md changes the urgency prompt sent to the LLM without server restart
3. The urgency rules influence the urgency field of results
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.synthesize.strand import SynthesizeStrand, SynthesizeRequest, Urgency
from src.fetch.commands import FetchResult, IntentType
from src.intent.router import IntentRouter
from src.components.hot_reload import HotReloadManager


# Fixtures
@pytest.fixture
def temp_urgency_md():
    """Create a temporary urgency.md file for testing."""
    content = """# Urgency Classifier Test

## Urgency Tiers

### Critical (urgency: "critical")
Test content for critical urgency.

### Normal (urgency: "normal")
Test content for normal urgency.
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def temp_synthesize_md():
    """Create a temporary synthesize.md file for testing."""
    content = """# Synthesize Strand Test Prompt

Output JSON with urgency field.
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def mock_zai_client():
    """Create a mock ZAI client."""
    client = AsyncMock()
    return client


@pytest.fixture
def hot_reload_manager(temp_synthesize_md, temp_urgency_md):
    """Create a HotReloadManager with temp files."""
    manager = HotReloadManager()
    manager.register_prompt('synthesize', temp_synthesize_md)
    manager.register_prompt('urgency', temp_urgency_md)
    return manager


@pytest.fixture
def synthesize_strand(temp_synthesize_md, hot_reload_manager):
    """Create a SynthesizeStrand with temp files."""
    strand = SynthesizeStrand(prompt_path=Path(temp_synthesize_md))
    strand._zai_client = MagicMock()
    strand._reload_manager = hot_reload_manager

    return strand


@pytest.fixture
def intent_router(hot_reload_manager):
    """Create an IntentRouter with hot_reload_manager."""
    router = IntentRouter()
    router._reload_manager = hot_reload_manager
    return router


@pytest.fixture
def fetch_result():
    """Create a sample FetchResult."""
    # Create FetchCoverage object
    from src.fetch.commands import FetchCoverage
    coverage = FetchCoverage(
        total_sources=1,
        succeeded=[],
        timed_out=[],
        failed=[],
        skipped=[],
    )

    # Create FetchResult object (dataclass requires positional args)
    result = FetchResult(
        intent_id="test-intent",
        intent_type=IntentType.STATUS,
        sources={},
        coverage=coverage,
        total_duration_ms=100,
        caveats=[],
    )
    return result


class TestUrgencyHotReload:
    """Tests for urgency.md hot-reload functionality."""

    @pytest.mark.asyncio
    async def test_urgency_prompt_loaded_in_system_prompt(
        self, synthesize_strand, mock_zai_client, temp_urgency_md, temp_synthesize_md, fetch_result
    ):
        """Test that urgency.md content is loaded and included in the LLM system prompt."""
        # Setup mock to capture the system prompt
        captured_system_prompt = None

        async def capture_call_simple(system_prompt, user_message, **kwargs):
            nonlocal captured_system_prompt
            captured_system_prompt = system_prompt
            return json.dumps({
                "data": {"type": "test"},
                "summary": "Test summary",
                "urgency": "normal"
            })

        mock_zai_client.call_simple = capture_call_simple
        synthesize_strand._zai_client = mock_zai_client

        # Create a synthesize request
        request = SynthesizeRequest(
            intent_id="test-1",
            intent_type=IntentType.STATUS,
            utterance="test utterance",
            fetched_context=fetch_result,
            urgency="normal",
        )

        # Synthesize
        await synthesize_strand.synthesize(request)

        # Verify that urgency rules are in the system prompt
        assert captured_system_prompt is not None
        assert "Urgency Classifier Test" in captured_system_prompt
        assert "Test content for critical urgency" in captured_system_prompt
        assert "Test content for normal urgency" in captured_system_prompt

    @pytest.mark.asyncio
    async def test_urgency_hot_reload_detects_changes(
        self, synthesize_strand, mock_zai_client, temp_urgency_md, temp_synthesize_md, fetch_result, hot_reload_manager
    ):
        """Test that editing urgency.md changes the LLM system prompt without restart."""
        # First call
        captured_prompts = []

        async def capture_first(system_prompt, user_message, **kwargs):
            nonlocal captured_prompts
            captured_prompts.append(system_prompt)
            return json.dumps({
                "data": {"type": "test"},
                "summary": "Test summary",
                "urgency": "normal"
            })

        mock_zai_client.call_simple = capture_first
        synthesize_strand._zai_client = mock_zai_client

        request = SynthesizeRequest(
            intent_id="test-1",
            intent_type=IntentType.STATUS,
            utterance="test utterance",
            fetched_context=fetch_result,
            urgency="normal",
        )

        await synthesize_strand.synthesize(request)

        # Modify the urgency file
        new_content = """# Urgency Classifier Modified

## Urgency Tiers

### Critical (urgency: "critical")
MODIFIED: New content for critical urgency.

### Normal (urgency: "normal")
MODIFIED: New content for normal urgency.
"""
        Path(temp_urgency_md).write_text(new_content)

        # Force reload to bypass the CHECK_INTERVAL throttle
        hot_reload_manager.force_reload('urgency')

        # Second call (should use updated content)
        async def capture_second(system_prompt, user_message, **kwargs):
            nonlocal captured_prompts
            captured_prompts.append(system_prompt)
            return json.dumps({
                "data": {"type": "test"},
                "summary": "Test summary",
                "urgency": "normal"
            })

        mock_zai_client.call_simple = capture_second

        await synthesize_strand.synthesize(request)

        # Verify that the prompts are different
        assert len(captured_prompts) == 2
        first_prompt, second_prompt = captured_prompts

        # First prompt should have original content
        assert "Urgency Classifier Test" in first_prompt
        assert "Test content for critical urgency" in first_prompt

        # Second prompt should have modified content
        assert "Urgency Classifier Modified" in second_prompt
        assert "MODIFIED: New content for critical urgency" in second_prompt

        # Second prompt should NOT have original content
        assert "Urgency Classifier Test" not in second_prompt
        assert "Test content for critical urgency" not in second_prompt

    @pytest.mark.asyncio
    async def test_urgency_rules_influence_result(
        self, synthesize_strand, mock_zai_client, temp_urgency_md, temp_synthesize_md, fetch_result
    ):
        """Test that urgency rules influence the urgency field of results."""
        # Setup mock to return high urgency based on the prompt
        async def return_high_urgency(system_prompt, user_message, **kwargs):
            # Verify that urgency rules are present
            assert "Urgency Classifier Test" in system_prompt or "Urgency Classifier" in system_prompt
            return json.dumps({
                "data": {"type": "test"},
                "summary": "Test summary",
                "urgency": "high"
            })

        mock_zai_client.call_simple = return_high_urgency
        synthesize_strand._zai_client = mock_zai_client

        request = SynthesizeRequest(
            intent_id="test-1",
            intent_type=IntentType.STATUS,
            utterance="production pods are crashing",
            fetched_context=fetch_result,
            urgency="normal",  # Initial classification
        )

        # Synthesize
        result = await synthesize_strand.synthesize(request)

        # Verify that the urgency from LLM response is used
        assert result.urgency == Urgency.HIGH

    @pytest.mark.asyncio
    async def test_urgency_defaults_to_request_urgency_if_not_in_response(
        self, synthesize_strand, mock_zai_client, temp_urgency_md, temp_synthesize_md, fetch_result
    ):
        """Test that urgency defaults to request.urgency if not in LLM response."""
        async def return_no_urgency(system_prompt, user_message, **kwargs):
            return json.dumps({
                "data": {"type": "test"},
                "summary": "Test summary"
            })

        mock_zai_client.call_simple = return_no_urgency
        synthesize_strand._zai_client = mock_zai_client

        request = SynthesizeRequest(
            intent_id="test-1",
            intent_type=IntentType.STATUS,
            utterance="test utterance",
            fetched_context=fetch_result,
            urgency="critical",  # Set critical as default
        )

        # Synthesize
        result = await synthesize_strand.synthesize(request)

        # Verify that the default urgency is used
        assert result.urgency == Urgency.CRITICAL


class TestUrgencyInSynthesizeStrand:
    """Tests for urgency integration in SynthesizeStrand."""

    @pytest.mark.asyncio
    async def test_urgency_prompt_included_in_combined_prompt(
        self, synthesize_strand, temp_urgency_md, temp_synthesize_md
    ):
        """Test that urgency prompt is appended to synthesize prompt."""
        # Load the prompts directly
        synthesize_prompt = synthesize_strand._load_prompt()
        urgency_prompt = synthesize_strand._load_urgency_prompt()

        # Build the combined prompt (mimicking what synthesize() does)
        combined_prompt = f"{synthesize_prompt}\n\n## Urgency Classification Rules\n\n{urgency_prompt}"

        # Verify structure
        assert "Synthesize Strand Test Prompt" in combined_prompt
        assert "## Urgency Classification Rules" in combined_prompt
        assert "Urgency Classifier Test" in combined_prompt

    def test_hot_reload_manager_refreshes_urgency_prompt(
        self, hot_reload_manager, temp_urgency_md
    ):
        """Test that hot_reload manager refreshes urgency prompt."""
        # First load
        first_content = hot_reload_manager.get_prompt('urgency')
        assert "Urgency Classifier Test" in first_content

        # Modify the file
        Path(temp_urgency_md).write_text("# Modified urgency content")

        # Force reload
        hot_reload_manager.force_reload('urgency')

        # Second load should get new content
        second_content = hot_reload_manager.get_prompt('urgency')
        assert "Modified urgency content" in second_content
        assert "Urgency Classifier Test" not in second_content


class TestUrgencyInRouter:
    """Tests for urgency.md integration in IntentRouter."""

    @pytest.mark.asyncio
    async def test_urgency_rules_in_router_system_prompt(
        self, intent_router, mock_zai_client, temp_urgency_md, hot_reload_manager
    ):
        """Test that urgency.md content is included in router's system prompt."""
        captured_system_prompt = None

        async def capture_call_simple(system_prompt, user_message, **kwargs):
            nonlocal captured_system_prompt
            captured_system_prompt = system_prompt
            return json.dumps([
                {
                    "intent_type": "status",
                    "project_slug": None,
                    "urgency": "normal",
                    "utterance_fragment": "test utterance",
                    "confidence": 0.9,
                    "reasoning": "test"
                }
            ])

        mock_zai_client.call_simple = capture_call_simple
        intent_router._zai_client = mock_zai_client

        await intent_router.classify_utterance("test utterance", "session-123")

        # Verify that urgency rules are in the system prompt
        assert captured_system_prompt is not None
        assert "Urgency Classifier Test" in captured_system_prompt
        assert "Test content for critical urgency" in captured_system_prompt

    @pytest.mark.asyncio
    async def test_urgency_hot_reload_in_router(
        self, intent_router, mock_zai_client, temp_urgency_md, hot_reload_manager
    ):
        """Test that editing urgency.md changes router's system prompt without restart."""
        captured_prompts = []

        async def capture_first(system_prompt, user_message, **kwargs):
            nonlocal captured_prompts
            captured_prompts.append(system_prompt)
            return json.dumps([
                {
                    "intent_type": "status",
                    "project_slug": None,
                    "urgency": "normal",
                    "utterance_fragment": "test utterance",
                    "confidence": 0.9,
                    "reasoning": "test"
                }
            ])

        mock_zai_client.call_simple = capture_first
        intent_router._zai_client = mock_zai_client

        await intent_router.classify_utterance("test utterance", "session-123")

        # Modify the urgency file
        Path(temp_urgency_md).write_text("# Modified urgency content for router")

        # Force reload
        hot_reload_manager.force_reload('urgency')

        # Second call
        async def capture_second(system_prompt, user_message, **kwargs):
            nonlocal captured_prompts
            captured_prompts.append(system_prompt)
            return json.dumps([
                {
                    "intent_type": "status",
                    "project_slug": None,
                    "urgency": "normal",
                    "utterance_fragment": "test utterance",
                    "confidence": 0.9,
                    "reasoning": "test"
                }
            ])

        mock_zai_client.call_simple = capture_second

        await intent_router.classify_utterance("test utterance", "session-123")

        # Verify that the prompts are different
        assert len(captured_prompts) == 2
        first_prompt, second_prompt = captured_prompts

        # First prompt should have original content
        assert "Urgency Classifier Test" in first_prompt

        # Second prompt should have modified content
        assert "Modified urgency content for router" in second_prompt
        assert "Urgency Classifier Test" not in second_prompt
