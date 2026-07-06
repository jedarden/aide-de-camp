"""
Test Module - Testing endpoints for aide-de-camp.

Provides test endpoints that bypass the Web Speech API and directly
inject test utterances into the dispatch pipeline for end-to-end testing.

Also provides TTS/narration testing endpoints for capturing and verifying
narration events without actual audio output.
"""
from .router import router
from .dispatch import (
    TestDispatchRequest,
    TestDispatchResponse,
    TestUtterance,
    TEST_UTTERANCES,
    dispatch_test_utterance,
)
from .narration import (
    NarrationSession,
    NarrationEvent,
    TTSCapture,
    get_test_session,
    cleanup_test_session,
)

__all__ = [
    "router",
    "TestDispatchRequest",
    "TestDispatchResponse",
    "TestUtterance",
    "TEST_UTTERANCES",
    "dispatch_test_utterance",
    "NarrationSession",
    "NarrationEvent",
    "TTSCapture",
    "get_test_session",
    "cleanup_test_session",
]
