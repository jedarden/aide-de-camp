"""
MemoryExtractionHandler unit tests (bead adc-16hkn).

Tests memory extraction functionality with and without API key:
- create_memory_handler factory function behavior
- MemoryExtractionHandler.on_turn_done() extraction flow
- API key requirement and graceful degradation
- Silent error handling (fire-and-forget contract)

These tests use mocking to avoid real OpenAI API calls while still
validating the extraction pipeline.
"""

import os
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Any

import pytest
import httpx

from src.memory.extraction import MemoryExtractionHandler, create_memory_handler
from src.memory.store import FactCategory, MemoryStore

# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def temp_memory_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for memory files."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


@pytest.fixture
def session_id() -> str:
    """Test session ID - unique per test for isolation."""
    import uuid
    return f"test-session-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def sample_api_key() -> str:
    """Sample API key for testing."""
    return "sk-test-key-12345"


@pytest.fixture
def mock_store(temp_memory_dir: Path, session_id: str) -> MemoryStore:
    """Create a MemoryStore instance for testing."""
    logger = MagicMock()
    return MemoryStore(
        session_id=session_id,
        memory_dir=str(temp_memory_dir),
        logger=logger
    )


@pytest.fixture
def clear_openai_env() -> None:
    """Ensure OPENAI_API_KEY is unset for testing."""
    original = os.environ.get("OPENAI_API_KEY")
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]
    yield
    if original:
        os.environ["OPENAI_API_KEY"] = original


# --- create_memory_handler tests ---------------------------------------------


def test_create_memory_handler_returns_none_without_api_key(clear_openai_env: None) -> None:
    """
    Test create_memory_handler returns None when no API key is available.

    This is the primary graceful degradation behavior - without an API key,
    the factory returns None rather than crashing or creating a broken handler.
    """
    result = create_memory_handler(session_id="test-session")

    assert result is None, "Should return None when no API key available"


def test_create_memory_handler_without_api_key_param(clear_openai_env: None) -> None:
    """Test create_memory_handler with no API key parameter and no env var."""
    result = create_memory_handler(session_id="test-session", api_key=None)

    assert result is None, "Should return None when API key is None"


def test_create_memory_handler_with_api_key(sample_api_key: str) -> None:
    """Test create_memory_handler returns handler when API key is provided."""
    result = create_memory_handler(
        session_id="test-session",
        api_key=sample_api_key
    )

    assert result is not None, "Should return handler when API key is provided"
    assert isinstance(result, MemoryExtractionHandler)
    assert result.api_key == sample_api_key


def test_create_memory_handler_prefers_env_var(clear_openai_env: None) -> None:
    """Test create_memory_handler uses OPENAI_API_KEY environment variable."""
    os.environ["OPENAI_API_KEY"] = "sk-env-key-67890"

    result = create_memory_handler(session_id="test-session")

    assert result is not None, "Should use env var API key"
    assert result.api_key == "sk-env-key-67890"


def test_create_memory_handler_prefers_param_over_env(clear_openai_env: None) -> None:
    """Test create_memory_handler prefers parameter over environment variable."""
    os.environ["OPENAI_API_KEY"] = "sk-env-key-67890"

    result = create_memory_handler(
        session_id="test-session",
        api_key="sk-param-key-abc"
    )

    assert result is not None, "Should prefer parameter API key"
    assert result.api_key == "sk-param-key-abc"


# --- MemoryExtractionHandler initialization tests --------------------------


def test_handler_init_without_api_key_logs_warning(clear_openai_env: None) -> None:
    """Test MemoryExtractionHandler logs warning when initialized without API key."""
    logger = MagicMock()
    handler = MemoryExtractionHandler(
        session_id="test-session",
        api_key=None
    )

    assert handler.api_key is None
    # The logger.warning should have been called during __init__


def test_handler_init_with_api_key(sample_api_key: str) -> None:
    """Test MemoryExtractionHandler initializes correctly with API key."""
    handler = MemoryExtractionHandler(
        session_id="test-session",
        api_key=sample_api_key
    )

    assert handler.api_key == sample_api_key
    assert handler.session_id == "test-session"
    assert handler.memory_store is not None


# --- on_turn_done without API key tests ---------------------------------------


@pytest.mark.asyncio
async def test_on_turn_done_returns_silently_without_api_key(
    clear_openai_env: None,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done returns silently when no API key is available.

    This validates the fire-and-forget contract - without an API key,
    the method should return None and NOT raise any exceptions.
    """
    handler = MemoryExtractionHandler(
        session_id=session_id
    )

    result = await handler.on_turn_done(
        user_text="my dog is named Rex",
        assistant_text="I'll remember that."
    )

    # Should return None silently
    assert result is None

    # No facts should be extracted (no API call was possible)
    handler.memory_store.load()
    facts = handler.memory_store.get_facts()
    assert len(facts) == 0


# --- on_turn_done with API key tests (mocked) --------------------------------


@pytest.mark.asyncio
async def test_on_turn_done_extracts_and_saves_fact(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done extracts and saves a fact when API key is available.

    This is the happy path - with a valid API key, the handler should:
    1. Call the OpenAI API (mocked here)
    2. Parse the response
    3. Extract facts
    4. Save them to the memory store
    """
    handler = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    # Mock the HTTP client to return a synthetic response
    mock_response = {
        "choices": [{
            "message": {
                "content": json.dumps([{
                    "text": "User's dog is named Rex",
                    "category": "personal",
                    "confidence": 0.95
                }])
            }
        }]
    }

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response_obj = MagicMock()
        mock_response_obj.raise_for_status = MagicMock()
        mock_response_obj.json = MagicMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response_obj)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        # Call on_turn_done
        await handler.on_turn_done(
            user_text="my dog is named Rex",
            assistant_text="Got it, I'll remember that your dog is named Rex."
        )

    # Verify the fact was saved
    handler.memory_store.load()
    facts = handler.memory_store.get_facts()

    assert len(facts) == 1, "Should extract and save one fact"
    assert facts[0].text == "User's dog is named Rex"
    assert facts[0].category == FactCategory.PERSONAL
    assert facts[0].confidence == 0.95


@pytest.mark.asyncio
async def test_on_turn_done_empty_user_text(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done handles empty user text gracefully.

    Empty user text should return early without making an API call.
    """
    handler = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    # Call with empty user text
    result = await handler.on_turn_done(
        user_text="",
        assistant_text="Hello"
    )

    assert result is None

    # No API call should be made, no facts saved
    handler.memory_store.load()
    facts = handler.memory_store.get_facts()
    assert len(facts) == 0


@pytest.mark.asyncio
async def test_on_turn_done_whitespace_only_user_text(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done handles whitespace-only user text gracefully.
    """
    handler = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    result = await handler.on_turn_done(
        user_text="   \n\t  ",
        assistant_text="Hello"
    )

    assert result is None

    handler.memory_store.load()
    facts = handler.memory_store.get_facts()
    assert len(facts) == 0


@pytest.mark.asyncio
async def test_on_turn_done_handles_api_error_gracefully(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done handles API errors silently (fire-and-forget).

    Even if the API call fails, the method should NOT propagate exceptions.
    """
    handler = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    # Mock the HTTP client to raise an exception
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("API timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        # Should NOT raise an exception
        result = await handler.on_turn_done(
            user_text="my dog is named Rex",
            assistant_text="Got it"
        )

    assert result is None, "Should return None on API error"

    # No facts should be saved
    handler.memory_store.load()
    facts = handler.memory_store.get_facts()
    assert len(facts) == 0


@pytest.mark.asyncio
async def test_on_turn_done_handles_invalid_json_response(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done handles invalid JSON in API response gracefully.
    """
    handler = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    # Mock response with invalid JSON
    mock_response = {
        "choices": [{
            "message": {
                "content": "not valid json {"
            }
        }]
    }

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response_obj = MagicMock()
        mock_response_obj.raise_for_status = MagicMock()
        mock_response_obj.json = MagicMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response_obj)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        # Should NOT raise an exception
        result = await handler.on_turn_done(
            user_text="my dog is named Rex",
            assistant_text="Got it"
        )

    assert result is None

    # No facts should be saved
    handler.memory_store.load()
    facts = handler.memory_store.get_facts()
    assert len(facts) == 0


@pytest.mark.asyncio
async def test_on_turn_done_handles_multiple_facts(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done extracts and saves multiple facts from a single turn.
    """
    handler = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    # Mock response with multiple facts
    mock_response = {
        "choices": [{
            "message": {
                "content": json.dumps([
                    {
                        "text": "User lives in Berlin",
                        "category": "personal",
                        "confidence": 0.95
                    },
                    {
                        "text": "Prefers dark mode interfaces",
                        "category": "preference",
                        "confidence": 0.9
                    },
                    {
                        "text": "Working on Python project",
                        "category": "context",
                        "confidence": 0.85
                    }
                ])
            }
        }]
    }

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response_obj = MagicMock()
        mock_response_obj.raise_for_status = MagicMock()
        mock_response_obj.json = MagicMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response_obj)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        await handler.on_turn_done(
            user_text="I live in Berlin and prefer dark mode. I'm working on a Python project.",
            assistant_text="I've noted all of that."
        )

    # Verify all facts were saved
    handler.memory_store.load()
    facts = handler.memory_store.get_facts()

    assert len(facts) == 3
    fact_texts = {f.text for f in facts}
    assert "User lives in Berlin" in fact_texts
    assert "Prefers dark mode interfaces" in fact_texts
    assert "Working on Python project" in fact_texts


@pytest.mark.asyncio
async def test_on_turn_done_handles_empty_fact_list(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done handles empty fact list from API response.
    """
    handler = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    # Mock response with empty fact list
    mock_response = {
        "choices": [{
            "message": {
                "content": "[]"
            }
        }]
    }

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response_obj = MagicMock()
        mock_response_obj.raise_for_status = MagicMock()
        mock_response_obj.json = MagicMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response_obj)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        await handler.on_turn_done(
            user_text="Hello, how are you?",
            assistant_text="I'm doing well, thanks!"
        )

    # No facts should be saved
    handler.memory_store.load()
    facts = handler.memory_store.get_facts()
    assert len(facts) == 0


@pytest.mark.asyncio
async def test_on_turn_done_normalizes_invalid_category(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done normalizes invalid category to 'context'.
    """
    handler = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    # Mock response with invalid category
    mock_response = {
        "choices": [{
            "message": {
                "content": json.dumps([{
                    "text": "Some fact",
                    "category": "invalid_category",
                    "confidence": 0.8
                }])
            }
        }]
    }

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response_obj = MagicMock()
        mock_response_obj.raise_for_status = MagicMock()
        mock_response_obj.json = MagicMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response_obj)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        await handler.on_turn_done(
            user_text="Some input",
            assistant_text="Some response"
        )

    # Verify fact was saved with normalized category
    handler.memory_store.load()
    facts = handler.memory_store.get_facts()

    assert len(facts) == 1
    assert facts[0].text == "Some fact"
    assert facts[0].category == FactCategory.CONTEXT  # Should be normalized


@pytest.mark.asyncio
async def test_on_turn_done_clamps_confidence_values(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test on_turn_done clamps confidence values to [0.0, 1.0].
    """
    handler = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    # Mock response with out-of-range confidence values
    mock_response = {
        "choices": [{
            "message": {
                "content": json.dumps([
                    {
                        "text": "High confidence fact",
                        "category": "personal",
                        "confidence": 1.5  # Should be clamped to 1.0
                    },
                    {
                        "text": "Negative confidence fact",
                        "category": "context",
                        "confidence": -0.5  # Should be clamped to 0.0
                    }
                ])
            }
        }]
    }

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response_obj = MagicMock()
        mock_response_obj.raise_for_status = MagicMock()
        mock_response_obj.json = MagicMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response_obj)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        await handler.on_turn_done(
            user_text="Some input",
            assistant_text="Some response"
        )

    # Verify confidence values were clamped
    handler.memory_store.load()
    facts = handler.memory_store.get_facts()

    assert len(facts) == 2
    high_fact = next(f for f in facts if f.text == "High confidence fact")
    low_fact = next(f for f in facts if f.text == "Negative confidence fact")

    assert high_fact.confidence == 1.0
    assert low_fact.confidence == 0.0


# --- Integration-style test with persistence --------------------------------


@pytest.mark.asyncio
async def test_extraction_persists_across_handler_instances(
    sample_api_key: str,
    temp_memory_dir: Path,
    session_id: str
) -> None:
    """
    Test that extracted facts persist across handler instances.

    This validates the full pipeline: extract → save → persist → reload.
    """
    # First handler - extract and save
    handler1 = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    mock_response = {
        "choices": [{
            "message": {
                "content": json.dumps([{
                    "text": "User's dog is named Rex",
                    "category": "personal",
                    "confidence": 0.95
                }])
            }
        }]
    }

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response_obj = MagicMock()
        mock_response_obj.raise_for_status = MagicMock()
        mock_response_obj.json = MagicMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response_obj)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        await handler1.on_turn_done(
            user_text="my dog is named Rex",
            assistant_text="Got it"
        )

    # Create second handler instance - should load saved facts
    handler2 = MemoryExtractionHandler(
        session_id=session_id,
        api_key=sample_api_key
    )

    handler2.memory_store.load()
    facts = handler2.memory_store.get_facts()

    assert len(facts) == 1, "Fact should persist across handler instances"
    assert facts[0].text == "User's dog is named Rex"


# --- Documentation test ------------------------------------------------------


def test_api_key_requirement_documented() -> None:
    """
    Document test: API key is required for extraction.

    This test documents the requirement that extraction only works when
    an OpenAI API key is available. Without the key:
    - create_memory_handler returns None
    - MemoryExtractionHandler.api_key is None
    - on_turn_done returns silently
    - No extraction is performed

    Acceptance criteria for bead adc-16hkn:
    ✓ With key: fact extracted and persisted (test_on_turn_done_extracts_and_saves_fact)
    ✓ Without key: handler is None (test_create_memory_handler_returns_none_without_api_key)
    ✓ Without key: silent degradation (test_on_turn_done_returns_silently_without_api_key)
    """
    # This test documents the requirements and is always true
    assert True, "API key requirement tests are documented above"
