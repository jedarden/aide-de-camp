"""
Shared fixtures and test data for flag check (confidence threshold) tests.

Test cases reference: notes/adc-1dj-flag-check-test-cases.md
"""
import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@dataclass
class LLMResponseMock:
    """Mock LLM response for testing."""
    json_data: list[dict[str, Any]] | dict[str, Any]
    raw_response: str | None = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.json_data)

    def to_raw_response(self) -> str:
        """Get raw response string."""
        return self.raw_response or self.to_json()


# High confidence fixtures (>= 0.9)
HIGH_CONFIDENCE_095 = LLMResponseMock(
    json_data=[{
        "intent_type": "status",
        "confidence": 0.95,
        "project_slug": "options-pipeline",
        "urgency": "normal",
        "utterance_fragment": "check the pods",
        "reasoning": "User wants to check status"
    }]
)

HIGH_CONFIDENCE_100 = LLMResponseMock(
    json_data=[{
        "intent_type": "action",
        "confidence": 1.0,
        "project_slug": None,
        "urgency": "normal",
        "utterance_fragment": "restart the service",
        "reasoning": "User wants to take action"
    }]
)

HIGH_CONFIDENCE_090 = LLMResponseMock(
    json_data=[{
        "intent_type": "lookup",
        "confidence": 0.9,
        "project_slug": "kalshi-tape",
        "urgency": "high",
        "utterance_fragment": "find recent errors",
        "reasoning": "User wants to look up information"
    }]
)

# Medium confidence fixtures (0.7 - 0.9)
MEDIUM_CONFIDENCE_080 = LLMResponseMock(
    json_data=[{
        "intent_type": "status",
        "confidence": 0.8,
        "project_slug": None,
        "urgency": "normal",
        "utterance_fragment": "how's it going",
        "reasoning": "Ambiguous status request"
    }]
)

MEDIUM_CONFIDENCE_075 = LLMResponseMock(
    json_data=[{
        "intent_type": "brainstorm",
        "confidence": 0.75,
        "project_slug": None,
        "urgency": "normal",
        "utterance_fragment": "maybe we could",
        "reasoning": "Possible brainstorming"
    }]
)

MEDIUM_CONFIDENCE_070 = LLMResponseMock(
    json_data=[{
        "intent_type": "action",
        "confidence": 0.7,
        "project_slug": None,
        "urgency": "normal",
        "utterance_fragment": "do something",
        "reasoning": "Unclear action"
    }]
)

# Low confidence fixtures (< 0.7)
LOW_CONFIDENCE_060 = LLMResponseMock(
    json_data=[{
        "intent_type": "clarification",
        "confidence": 0.6,
        "project_slug": None,
        "urgency": "normal",
        "utterance_fragment": "check the pods",
        "reasoning": "Unclear intent, needs clarification"
    }]
)

LOW_CONFIDENCE_030 = LLMResponseMock(
    json_data=[{
        "intent_type": "clarification",
        "confidence": 0.3,
        "project_slug": None,
        "urgency": "normal",
        "utterance_fragment": "something something",
        "reasoning": "Very unclear"
    }]
)

LOW_CONFIDENCE_000 = LLMResponseMock(
    json_data=[{
        "intent_type": "clarification",
        "confidence": 0.0,
        "project_slug": None,
        "urgency": "normal",
        "utterance_fragment": "???",
        "reasoning": "No confidence"
    }]
)

# Edge case fixtures
MISSING_CONFIDENCE = LLMResponseMock(
    json_data=[{
        "intent_type": "status",
        "project_slug": "test",
        "urgency": "normal",
        "utterance_fragment": "check status",
        "reasoning": "No confidence field"
    }]
)

# TC-FC-011: Invalid confidence type (string instead of float)
INVALID_CONFIDENCE_STRING = LLMResponseMock(
    json_data=[{
        "intent_type": "status",
        "confidence": "high",  # String instead of float
        "project_slug": "options-pipeline",
        "urgency": "normal",
        "utterance_fragment": "check the pods",
        "reasoning": "Confidence as string"
    }]
)

# TC-FC-012: Negative confidence value
NEGATIVE_CONFIDENCE = LLMResponseMock(
    json_data=[{
        "intent_type": "action",
        "confidence": -0.1,
        "project_slug": None,
        "urgency": "normal",
        "utterance_fragment": "restart the service",
        "reasoning": "Negative confidence"
    }]
)

# TC-FC-013: Over-unity confidence (> 1.0)
OVER_UNITY_CONFIDENCE = LLMResponseMock(
    json_data=[{
        "intent_type": "lookup",
        "confidence": 1.5,
        "project_slug": "kalshi-tape",
        "urgency": "normal",
        "utterance_fragment": "find recent errors",
        "reasoning": "Confidence exceeds 1.0"
    }]
)

# TC-FC-014: Unknown intent type
UNKNOWN_INTENT_TYPE = LLMResponseMock(
    json_data=[{
        "intent_type": "unknown_type",  # Not a recognized intent type
        "confidence": 0.9,
        "project_slug": None,
        "urgency": "normal",
        "utterance_fragment": "some utterance",
        "reasoning": "Unknown intent type"
    }]
)

# TC-FC-015: Empty JSON array
EMPTY_JSON_ARRAY = LLMResponseMock(
    json_data=[]
)

# TC-FC-016: Mixed confidence multi-intent (high status, low action, medium lookup)
MIXED_CONFIDENCE_MULTI = LLMResponseMock(
    json_data=[
        {
            "intent_type": "status",
            "confidence": 0.95,
            "project_slug": "options-pipeline",
            "urgency": "normal",
            "utterance_fragment": "check the pods",
            "reasoning": "High confidence status"
        },
        {
            "intent_type": "action",
            "confidence": 0.4,
            "project_slug": None,
            "urgency": "low",
            "utterance_fragment": "maybe restart it",
            "reasoning": "Low confidence action"
        },
        {
            "intent_type": "lookup",
            "confidence": 0.75,
            "project_slug": "kalshi-tape",
            "urgency": "normal",
            "utterance_fragment": "find recent errors",
            "reasoning": "Medium confidence lookup"
        }
    ]
)

# TC-FC-017: Non-JSON response from LLM
NON_JSON_RESPONSE = LLMResponseMock(
    json_data=[],
    raw_response="I cannot understand that request"
)

# TC-FC-018: Invalid JSON structure (dict instead of list)
INVALID_JSON_STRUCTURE = LLMResponseMock(
    json_data={  # Dict instead of list
        "intent_type": "status",
        "confidence": 0.9,
        "project_slug": "test",
        "urgency": "normal",
        "utterance_fragment": "check status",
        "reasoning": "Wrapped as dict not list"
    }
)

# Legacy fixtures for backward compatibility
MALFORMED_JSON = LLMResponseMock(
    json_data=[],
    raw_response="This is not JSON"
)

INCOMPLETE_JSON = LLMResponseMock(
    json_data=[],
    raw_response='{"intent_type": "status", "confidence": }'
)

EMPTY_INTENTS_ARRAY = EMPTY_JSON_ARRAY

MULTIPLE_MIXED_CONFIDENCE = MIXED_CONFIDENCE_MULTI


@pytest.fixture
def mock_zai_client():
    """Mock ZAI LLM client."""
    client = AsyncMock()
    client.call_simple = AsyncMock(return_value=HIGH_CONFIDENCE_095.to_raw_response())
    return client


@pytest.fixture
def mock_session_store():
    """Mock session store."""
    store = AsyncMock()
    store.get_session = AsyncMock(return_value=None)
    store.get_recent_intents = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_router_with_mocks(mock_zai_client, mock_session_store):
    """
    Mock router with all external dependencies replaced.

    Returns a tuple of (router_instance, mock_client, mock_store) where
    mock_client.call_simple can be dynamically configured per test.
    """
    from src.intent.router import IntentRouter

    router = IntentRouter()

    # Replace the internal client and store methods
    router._zai_client = None  # Reset to force re-fetch
    router._store = None

    # Create function wrappers that return our mocks
    async def mock_get_client():
        return mock_zai_client

    async def mock_get_store():
        return mock_session_store

    # Monkey-patch the private methods
    router._get_zai_client = mock_get_client
    router._get_store = mock_get_store

    return router, mock_zai_client, mock_session_store


@pytest.fixture
def sample_utterance():
    """Sample utterance for testing."""
    return "check the pods in options-pipeline"


@pytest.fixture
def sample_session_id():
    """Sample session ID for testing."""
    return "test-session-123"


@pytest.fixture
def sample_utterance_id():
    """Sample utterance ID for testing."""
    return "test-utterance-456"
