"""
Test utilities package for aide-de-camp testing.

This package provides reusable test utilities for endpoint comparison,
session management, and other common testing tasks.
"""
from .endpoint_comparison import (
    EndpointResult,
    send_to_test_intent_classify,
    send_to_dispatch,
    send_to_both_endpoints,
    extract_classifications_from_test_result,
    extract_classifications_from_dispatch_result,
    compare_classifications,
    compare_endpoint_responses,
    compare_endpoints_for_utterance,
    format_comparison_report,
    DEFAULT_TEST_SESSION_ID,
    DEFAULT_TEST_SURFACE_ID,
)

__all__ = [
    "EndpointResult",
    "send_to_test_intent_classify",
    "send_to_dispatch",
    "send_to_both_endpoints",
    "extract_classifications_from_test_result",
    "extract_classifications_from_dispatch_result",
    "compare_classifications",
    "compare_endpoint_responses",
    "compare_endpoints_for_utterance",
    "format_comparison_report",
    "DEFAULT_TEST_SESSION_ID",
    "DEFAULT_TEST_SURFACE_ID",
]
