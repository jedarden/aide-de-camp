"""
Error handling and degraded-state error events.

This module provides the DegradedStateHandler which broadcasts appropriate SSE
error events for various failure modes as defined in docs/plan/plan.md:
Degraded-State UX.

Also provides transient error detection for retry logic.
"""

from .degraded_state import (
    DegradedStateHandler,
    get_degraded_state_handler,
    broadcast_router_unavailable,
    broadcast_all_sources_failed,
    broadcast_degraded_raw_data,
    broadcast_clarification_card,
)

from .transient_errors import (
    is_transient,
    get_error_category,
)

__all__ = [
    "DegradedStateHandler",
    "get_degraded_state_handler",
    "broadcast_router_unavailable",
    "broadcast_all_sources_failed",
    "broadcast_degraded_raw_data",
    "broadcast_clarification_card",
    "is_transient",
    "get_error_category",
]
