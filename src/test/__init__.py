"""
Test Module - Testing endpoints for aide-de-camp.

Provides test endpoints that bypass the Web Speech API and directly
inject test utterances into the dispatch pipeline for end-to-end testing.
"""
from .router import router
from .dispatch import (
    TestDispatchRequest,
    TestDispatchResponse,
    TestUtterance,
    TEST_UTTERANCES,
    dispatch_test_utterance,
)

__all__ = [
    "router",
    "TestDispatchRequest",
    "TestDispatchResponse",
    "TestUtterance",
    "TEST_UTTERANCES",
    "dispatch_test_utterance",
]
