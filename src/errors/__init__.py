"""
Error handling and degraded-state error events.

This module provides the DegradedStateHandler which broadcasts appropriate SSE
error events for various failure modes as defined in docs/plan/plan.md:
Degraded-State UX.
"""

from .degraded_state import (
    DegradedStateHandler,
    get_degraded_state_handler,
    broadcast_router_unavailable,
    broadcast_all_sources_failed,
    broadcast_degraded_raw_data,
    broadcast_clarification_card,
)

__all__ = [
    "DegradedStateHandler",
    "get_degraded_state_handler",
    "broadcast_router_unavailable",
    "broadcast_all_sources_failed",
    "broadcast_degraded_raw_data",
    "broadcast_clarification_card",
]
