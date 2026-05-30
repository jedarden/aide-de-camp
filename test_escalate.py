#!/usr/bin/env python3
"""Test Escalate Strand: task-profile intent → NEEDLE bead creation."""

import asyncio
import httpx
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the project root is in the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.escalate.llm import (
    ZAIClient,
    LLMRequest,
    LLMResponse,
    LLMError,
    LLMTimeoutError,
    LLMRateLimitError,
    ModelClass,
    get_zai_client,
)
from src.escalate.handler import (
    EscalateRequest,
    EscalateResult,
    EscalateHandler,
    EscalateError,
    BeadCreationError,
    escalate_intent,
    get_escalate_handler,
)
from src.session.store import SessionStore


async def test_llm_request_payload():
    """Test LLM request serialization."""
    print("Testing LLM Request payload serialization...")

    request = LLMRequest(
        system_prompt="You are a test assistant.",
        user_message="Hello, world!",
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        temperature=0.5,
    )

    payload = request.to_payload()

    assert payload["model"] == "claude-sonnet-4-20250514"
    assert payload["max_tokens"] == 2048
    assert payload["temperature"] == 0.5
    assert payload["system"] == "You are a test assistant."
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"] == "Hello, world!"

    print("  ✅ LLM Request payload serialization works")
    return True


async def test_llm_response_total_tokens():
    """Test LLM response total tokens calculation."""
    print("Testing LLM Response total tokens...")

    response = LLMResponse(
        content="Test response",
        model="claude-sonnet-4-20250514",
        input_tokens=100,
        output_tokens=50,
        finish_reason="end_turn",
    )

    assert response.total_tokens == 150

    print("  ✅ LLM Response total tokens calculation works")
    return True


async def test_escalate_request_serialization():
    """Test escalate request serialization."""
    print("Testing Escalate Request serialization...")

    request = EscalateRequest(
        intent_id="test-intent",
        session_id="test-session",
        utterance="Test utterance",
        intent_type="task-profile",
        project_slug="test-project",
        topic_id="test-topic",
        context={"key": "value"},
        metadata={"meta": "data"},
    )

    result = request.to_dict()

    assert result["intent_id"] == "test-intent"
    assert result["session_id"] == "test-session"
    assert result["utterance"] == "Test utterance"
    assert result["intent_type"] == "task-profile"
    assert result["project_slug"] == "test-project"
    assert result["topic_id"] == "test-topic"
    assert result["context"] == {"key": "value"}
    assert result["metadata"] == {"meta": "data"}

    print("  ✅ Escalate Request serialization works")
    return True


async def test_escalate_result_serialization():
    """Test escalate result serialization."""
    print("Testing Escalate Result serialization...")

    result = EscalateResult(
        bead_id="test-bead",
        intent_id="test-intent",
        pending_card={"type": "pending", "id": "card-1"},
        status="created",
    )

    data = result.to_dict()

    assert data["bead_id"] == "test-bead"
    assert data["intent_id"] == "test-intent"
    assert data["pending_card"] == {"type": "pending", "id": "card-1"}
    assert data["status"] == "created"

    print("  ✅ Escalate Result serialization works")
    return True


async def test_zai_client_call():
    """Test ZAI client call with mocked HTTP."""
    print("Testing ZAI Client call...")

    client = ZAIClient(timeout=5.0)
    request = LLMRequest(
        system_prompt="Test",
        user_message="Hello",
    )

    # Mock HTTP response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [{"text": "Test response"}],
        "model": "claude-sonnet-4-20250514",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
        },
        "stop_reason": "end_turn",
    }

    with patch("src.escalate.llm.httpx.AsyncClient") as mock_client_class:
        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_http_client

        response = await client.call(request)

        assert response.content == "Test response"
        assert response.input_tokens == 10
        assert response.output_tokens == 5

    print("  ✅ ZAI Client call works")
    return True


async def test_zai_client_rate_limit():
    """Test ZAI client rate limit handling."""
    print("Testing ZAI Client rate limit handling...")

    client = ZAIClient(timeout=5.0)
    request = LLMRequest(system_prompt="Test", user_message="Hello")

    # Create a proper HTTPStatusError mock
    mock_response = MagicMock()
    mock_response.status_code = 429

    mock_http_exception = httpx.HTTPStatusError(
        "Rate limited",
        request=MagicMock(),
        response=mock_response,
    )

    with patch("src.escalate.llm.httpx.AsyncClient") as mock_client_class:
        mock_http_client = AsyncMock()
        # Make post raise HTTPStatusError
        mock_http_client.post.side_effect = mock_http_exception
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_http_client

        try:
            await client.call(request)
            print("  ❌ Should have raised LLMRateLimitError")
            return False
        except LLMRateLimitError:
            print("  ✅ ZAI Client correctly raises LLMRateLimitError")
            return True


async def test_escalate_handler_formulate_bead_body():
    """Test escalate handler bead body formulation."""
    print("Testing Escalate Handler formulate bead body...")

    handler = EscalateHandler()

    sample_request = EscalateRequest(
        intent_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        utterance="Deploy the new version to production",
        intent_type="task-profile",
        project_slug="options-pipeline",
    )

    # Mock LLM client
    mock_llm = AsyncMock()
    mock_llm.call_simple.return_value = "# Deploy to Production\n\n## Overview\nDeploy the new version..."

    handler._zai_client = mock_llm

    body = await handler.formulate_bead_body(sample_request)

    assert "## Overview" in body
    mock_llm.call_simple.assert_called_once()

    print("  ✅ Escalate Handler formulate bead body works")
    return True


async def test_escalate_handler_generate_title():
    """Test escalate handler bead title generation."""
    print("Testing Escalate Handler generate bead title...")

    handler = EscalateHandler()

    sample_request = EscalateRequest(
        intent_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        utterance="Deploy the new version to production",
        intent_type="task-profile",
        project_slug="options-pipeline",
    )

    title = handler._generate_bead_title(sample_request)

    assert "options-pipeline" in title
    assert "Deploy" in title

    print("  ✅ Escalate Handler generate bead title works")
    return True


async def test_escalate_handler_extract_bead_id():
    """Test bead ID extraction from br output."""
    print("Testing Escalate Handler extract bead ID...")

    handler = EscalateHandler()

    # Test standard format
    id1 = handler._extract_bead_id("Created bead abc-123")
    assert id1 == "abc-123"

    # Test alternative format
    id2 = handler._extract_bead_id("bead xyz-789 created")
    assert id2 == "xyz-789"

    # Test fallback to UUID-like pattern (regex fallback)
    # Note: abc-123 matches the pattern [a-z]{3,}-[a-z0-9]{3,}
    id3 = handler._extract_bead_id("some-output-with-abc-123-def-in-it")
    assert "abc-123" in id3, f"Expected 'abc-123' in '{id3}'"

    print("  ✅ Escalate Handler extract bead ID works")
    return True


async def test_escalate_handler_build_pending_card():
    """Test pending card building."""
    print("Testing Escalate Handler build pending card...")

    handler = EscalateHandler()

    sample_request = EscalateRequest(
        intent_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        utterance="Deploy the new version to production",
        intent_type="task-profile",
        project_slug="options-pipeline",
        metadata={"surface_id": "audio-surface-1", "urgency": "high"},
    )

    card = handler.build_pending_card(sample_request, "test-bead-123")

    assert card["type"] == "pending"
    assert card["bead_id"] == "test-bead-123"
    assert card["intent_id"] == sample_request.intent_id
    assert card["urgency"] == "high"
    assert card["summary"] == "Working on: Deploy the new version to production"

    print("  ✅ Escalate Handler build pending card works")
    return True


async def test_escalate_handler_full_flow():
    """Test full escalate flow with mocked components."""
    print("Testing Escalate Handler full flow...")

    handler = EscalateHandler()

    sample_request = EscalateRequest(
        intent_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        utterance="Deploy the new version to production",
        intent_type="task-profile",
        project_slug="options-pipeline",
        metadata={"surface_id": "audio-surface-1", "urgency": "high"},
    )

    # Mock LLM client
    mock_llm = AsyncMock()
    mock_llm.call_simple.return_value = "# Task\n\nDescription of task to do."

    handler._zai_client = mock_llm

    # Mock br create subprocess
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"Created bead test-bead-456\n", b"")

    # Mock store
    mock_store = AsyncMock()
    mock_store.update_intent_status = AsyncMock()

    handler.store = mock_store

    with patch("src.escalate.handler.asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await handler.escalate_intent(sample_request)

    assert result.bead_id == "test-bead-456"
    assert result.status == "created"
    assert result.pending_card["bead_id"] == "test-bead-456"
    # The call uses keyword args
    mock_store.update_intent_status.assert_called_once_with(
        intent_id=sample_request.intent_id, status="dispatched"
    )

    print("  ✅ Escalate Handler full flow works")
    return True


async def test_global_singleton_functions():
    """Test global singleton functions."""
    print("Testing global singleton functions...")

    # Test ZAI client singleton
    client1 = get_zai_client()
    client2 = get_zai_client()
    assert client1 is client2

    # Test escalate handler singleton
    handler1 = get_escalate_handler()
    handler2 = get_escalate_handler()
    assert handler1 is handler2

    print("  ✅ Global singleton functions work")
    return True


async def test_escalate_with_real_store():
    """Test escalate with real session store."""
    print("Testing Escalate with real session store...")

    test_db_path = Path("/tmp/test_escalate_store.db")
    if test_db_path.exists():
        test_db_path.unlink()

    store = SessionStore(test_db_path)
    await store.initialize()

    handler = EscalateHandler(store=store)

    request = EscalateRequest(
        intent_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        utterance="Test task",
        intent_type="task-profile",
    )

    # Test that store integration works
    assert handler.store is store

    await store.close()
    test_db_path.unlink()

    print("  ✅ Escalate with real store works")
    return True


async def test_convenience_function():
    """Test escalate_intent convenience function."""
    print("Testing escalate_intent convenience function...")

    request = EscalateRequest(
        intent_id="test-intent",
        session_id="test-session",
        utterance="Test",
        intent_type="task-profile",
    )

    # Mock handler
    mock_handler = AsyncMock()
    mock_result = EscalateResult(
        bead_id="test-bead",
        intent_id="test-intent",
        pending_card={},
        status="created",
    )
    mock_handler.escalate_intent.return_value = mock_result

    with patch("src.escalate.handler.get_escalate_handler", return_value=mock_handler):
        result = await escalate_intent(request)

    assert result.bead_id == "test-bead"
    mock_handler.escalate_intent.assert_called_once_with(request)

    print("  ✅ escalate_intent convenience function works")
    return True


async def test_escalate_bead_creation_failure():
    """Test bead creation failure handling."""
    print("Testing Escalate Handler bead creation failure...")

    handler = EscalateHandler()

    sample_request = EscalateRequest(
        intent_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        utterance="Test task",
        intent_type="task-profile",
    )

    # Mock br create failure
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate.return_value = (b"", b"br: error: bead creation failed")

    with patch("src.escalate.handler.asyncio.create_subprocess_exec", return_value=mock_proc):
        try:
            await handler.create_bead(sample_request, "Test bead body")
            print("  ❌ Should have raised BeadCreationError")
            return False
        except BeadCreationError:
            print("  ✅ Escalate Handler correctly raises BeadCreationError")
            return True


async def main():
    """Run all escalate strand tests."""
    print("="*50)
    print("ESCALATE STRAND TEST SUITE")
    print("="*50)

    tests = [
        test_llm_request_payload,
        test_llm_response_total_tokens,
        test_escalate_request_serialization,
        test_escalate_result_serialization,
        test_zai_client_call,
        test_zai_client_rate_limit,
        test_escalate_handler_formulate_bead_body,
        test_escalate_handler_generate_title,
        test_escalate_handler_extract_bead_id,
        test_escalate_handler_build_pending_card,
        test_escalate_handler_full_flow,
        test_global_singleton_functions,
        test_escalate_with_real_store,
        test_convenience_function,
        test_escalate_bead_creation_failure,
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "="*50)
    if all(results):
        print("✅ ALL TESTS PASSED")
        print("="*50)
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("="*50)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
