"""
Degraded state error handler for SSE error events.

Implements the failure-mode matrix from docs/plan/plan.md: Degraded-State UX.
Every failure renders a designed fixed-template card; never a blank canvas,
spinner, or stack trace.

Broadcasts SSE error events that the client templates consume to render
appropriate error cards.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from ..sse.broadcaster import (
    EventType,
    SSEEvent,
    get_broadcaster,
)
from ..fetch.commands import FetchResult


logger = logging.getLogger(__name__)


@dataclass
class RouterUnavailableEvent:
    """Payload for router_unavailable error event.

    Client renders: "Router unavailable — LLM proxy unreachable"
    with the raw utterance shown so nothing is lost.
    """
    utterance: str
    intent_id: str
    session_id: str
    error_reason: str  # "timeout" | "quota_exhausted" | "proxy_down" | "unknown_error"
    timestamp: str
    retry_allowed: bool = True


@dataclass
class AllSourcesFailedEvent:
    """Payload for all_sources_failed error event.

    Client renders: "No data" error card with intent header +
    per-source failure list. Fixed template, no LLM call.
    """
    intent_id: str
    intent_type: str
    session_id: str
    utterance: str
    failed_sources: list[dict]  # Each: {source, status, error}
    timestamp: str
    retry_allowed: bool = True


@dataclass
class DegradedRawDataEvent:
    """Payload for degraded_raw_data error event.

    Client renders: Degraded "raw data" card with structured fetch
    output under a "summary unavailable" banner. Fetched data
    is never discarded.
    """
    intent_id: str
    intent_type: str
    session_id: str
    utterance: str
    fetched_context: dict  # Preserved fetch data for degraded rendering
    error_reason: str
    timestamp: str
    retry_allowed: bool = True  # Retry-synthesize action reuses fetched context


@dataclass
class ClarificationCardEvent:
    """Payload for clarification_card error event.

    Client renders: Clarification-style card showing the utterance
    with an edit-and-resend action. Raw model output goes to logs,
    never the canvas.
    """
    utterance: str
    intent_id: str
    session_id: str
    parse_error: str
    timestamp: str
    retry_count: int  # Number of retries attempted (max 1 corrective retry)
    raw_output_snippet: str | None = None  # First 200 chars of malformed output for logs


class DegradedStateHandler:
    """
    Handles degraded-state error events for the failure-mode matrix.

    Each failure mode broadcasts a specific SSE error event with a
    well-defined payload that the client templates consume to render
    appropriate error cards.
    """

    def __init__(self):
        self._broadcaster = None

    def _get_broadcaster(self):
        """Get or create the SSE broadcaster."""
        if self._broadcaster is None:
            self._broadcaster = get_broadcaster()
        return self._broadcaster

    async def broadcast_router_unavailable(
        self,
        utterance: str,
        intent_id: str,
        session_id: str,
        error_reason: str = "unknown_error",
    ) -> int:
        """
        Broadcast router_unavailable error event.

        Fired when ZAI proxy is down/timeout/quota at the router stage.
        Client renders dispatch-level error card showing raw utterance.

        Args:
            utterance: The original user utterance (preserved for retry)
            intent_id: Intent ID for tracking
            session_id: Session ID for targeting
            error_reason: "timeout" | "quota_exhausted" | "proxy_down" | "unknown_error"

        Returns:
            Number of connections the event was sent to
        """
        event_payload = RouterUnavailableEvent(
            utterance=utterance,
            intent_id=intent_id,
            session_id=session_id,
            error_reason=error_reason,
            timestamp=datetime.now().isoformat(),
            retry_allowed=True,
        )

        event = SSEEvent(
            event_type=EventType.ROUTER_UNAVAILABLE,
            data={
                "utterance": utterance,
                "intent_id": intent_id,
                "error_reason": error_reason,
                "timestamp": event_payload.timestamp,
                "retry_allowed": True,
                "message": "Router unavailable — LLM proxy unreachable",
            },
            target_session_id=session_id,
        )

        logger.info(
            f"Broadcasting router_unavailable for intent {intent_id}: {error_reason}"
        )

        return await self._get_broadcaster().broadcast(event)

    async def broadcast_all_sources_failed(
        self,
        intent_id: str,
        intent_type: str,
        session_id: str,
        utterance: str,
        failed_sources: list[dict],
    ) -> int:
        """
        Broadcast all_sources_failed error event.

        Fired when ALL fetch sources fail. Synthesize is skipped since
        there is nothing to synthesize. Client renders "No data" error card.

        Args:
            intent_id: Intent ID for tracking
            intent_type: Intent type string
            session_id: Session ID for targeting
            utterance: The original utterance
            failed_sources: List of {source, status, error} dicts

        Returns:
            Number of connections the event was sent to
        """
        event_payload = AllSourcesFailedEvent(
            intent_id=intent_id,
            intent_type=intent_type,
            session_id=session_id,
            utterance=utterance,
            failed_sources=failed_sources,
            timestamp=datetime.now().isoformat(),
            retry_allowed=True,
        )

        event = SSEEvent(
            event_type=EventType.ALL_SOURCES_FAILED,
            data={
                "intent_id": intent_id,
                "intent_type": intent_type,
                "utterance": utterance,
                "failed_sources": failed_sources,
                "timestamp": event_payload.timestamp,
                "retry_allowed": True,
                "message": "No data — all required sources failed",
            },
            target_session_id=session_id,
        )

        logger.info(
            f"Broadcasting all_sources_failed for intent {intent_id}: "
            f"{len(failed_sources)} sources failed"
        )

        return await self._get_broadcaster().broadcast(event)

    async def broadcast_degraded_raw_data(
        self,
        intent_id: str,
        intent_type: str,
        session_id: str,
        utterance: str,
        fetched_context: FetchResult,
        error_reason: str = "synthesize_failed",
    ) -> int:
        """
        Broadcast degraded_raw_data error event.

        Fired when ZAI fails at the synthesize stage. Fetched data is
        preserved and rendered under a "summary unavailable" banner.

        Args:
            intent_id: Intent ID for tracking
            intent_type: Intent type string
            session_id: Session ID for targeting
            utterance: The original utterance
            fetched_context: The FetchResult with preserved data
            error_reason: Reason for synthesize failure

        Returns:
            Number of connections the event was sent to
        """
        # Serialize fetch context for client rendering
        fetch_data = {
            "coverage": {
                "total_sources": fetched_context.coverage.total_sources,
                "succeeded": len(fetched_context.coverage.succeeded),
                "timed_out": len(fetched_context.coverage.timed_out),
                "failed": len(fetched_context.coverage.failed),
            },
            "caveats": fetched_context.caveats or [],
        }

        # Include successful source data for client-side raw rendering
        sources_data = {}
        for source, result in fetched_context.sources.items():
            if result.status == "success":
                sources_data[source.value] = result.data
            else:
                sources_data[source.value] = {
                    "status": result.status,
                    "error": result.error,
                }

        fetch_data["sources"] = sources_data

        event_payload = DegradedRawDataEvent(
            intent_id=intent_id,
            intent_type=intent_type,
            session_id=session_id,
            utterance=utterance,
            fetched_context=fetch_data,
            error_reason=error_reason,
            timestamp=datetime.now().isoformat(),
            retry_allowed=True,
        )

        event = SSEEvent(
            event_type=EventType.DEGRADED_RAW_DATA,
            data={
                "intent_id": intent_id,
                "intent_type": intent_type,
                "utterance": utterance,
                "fetched_context": fetch_data,
                "error_reason": error_reason,
                "timestamp": event_payload.timestamp,
                "retry_allowed": True,
                "message": "Summary unavailable — showing raw fetch data",
            },
            target_session_id=session_id,
        )

        logger.info(
            f"Broadcasting degraded_raw_data for intent {intent_id}: {error_reason}"
        )

        return await self._get_broadcaster().broadcast(event)

    async def broadcast_clarification_card(
        self,
        utterance: str,
        intent_id: str,
        session_id: str,
        parse_error: str,
        retry_count: int = 0,
        raw_output_snippet: str | None = None,
    ) -> int:
        """
        Broadcast clarification_card error event.

        Fired after one corrective retry fails on malformed router JSON.
        Client renders clarification-style card with edit-and-resend action.

        Args:
            utterance: The original utterance
            intent_id: Intent ID for tracking
            session_id: Session ID for targeting
            parse_error: Error message from JSON parsing
            retry_count: Number of retries attempted (max 1)
            raw_output_snippet: First 200 chars of malformed output

        Returns:
            Number of connections the event was sent to
        """
        # Limit raw output snippet for client payload
        snippet = None
        if raw_output_snippet:
            snippet = raw_output_snippet[:200] + "..." if len(raw_output_snippet) > 200 else raw_output_snippet

        event_payload = ClarificationCardEvent(
            utterance=utterance,
            intent_id=intent_id,
            session_id=session_id,
            parse_error=parse_error,
            timestamp=datetime.now().isoformat(),
            retry_count=retry_count,
            raw_output_snippet=snippet,
        )

        event = SSEEvent(
            event_type=EventType.CLARIFICATION_CARD,
            data={
                "utterance": utterance,
                "intent_id": intent_id,
                "parse_error": parse_error,
                "timestamp": event_payload.timestamp,
                "retry_count": retry_count,
                "raw_output_snippet": snippet,
                "message": "Couldn't parse that into intents",
            },
            target_session_id=session_id,
        )

        logger.info(
            f"Broadcasting clarification_card for intent {intent_id}: "
            f"retry_count={retry_count}"
        )

        return await self._get_broadcaster().broadcast(event)


# Global degraded state handler instance
_degraded_state_handler: Optional[DegradedStateHandler] = None


def get_degraded_state_handler() -> DegradedStateHandler:
    """Get or create the global degraded state handler instance."""
    global _degraded_state_handler
    if _degraded_state_handler is None:
        _degraded_state_handler = DegradedStateHandler()
    return _degraded_state_handler


# Convenience functions for broadcasting error events
async def broadcast_router_unavailable(
    utterance: str,
    intent_id: str,
    session_id: str,
    error_reason: str = "unknown_error",
) -> int:
    """Convenience function to broadcast router_unavailable error event."""
    handler = get_degraded_state_handler()
    return await handler.broadcast_router_unavailable(
        utterance=utterance,
        intent_id=intent_id,
        session_id=session_id,
        error_reason=error_reason,
    )


async def broadcast_all_sources_failed(
    intent_id: str,
    intent_type: str,
    session_id: str,
    utterance: str,
    failed_sources: list[dict],
) -> int:
    """Convenience function to broadcast all_sources_failed error event."""
    handler = get_degraded_state_handler()
    return await handler.broadcast_all_sources_failed(
        intent_id=intent_id,
        intent_type=intent_type,
        session_id=session_id,
        utterance=utterance,
        failed_sources=failed_sources,
    )


async def broadcast_degraded_raw_data(
    intent_id: str,
    intent_type: str,
    session_id: str,
    utterance: str,
    fetched_context: FetchResult,
    error_reason: str = "synthesize_failed",
) -> int:
    """Convenience function to broadcast degraded_raw_data error event."""
    handler = get_degraded_state_handler()
    return await handler.broadcast_degraded_raw_data(
        intent_id=intent_id,
        intent_type=intent_type,
        session_id=session_id,
        utterance=utterance,
        fetched_context=fetched_context,
        error_reason=error_reason,
    )


async def broadcast_clarification_card(
    utterance: str,
    intent_id: str,
    session_id: str,
    parse_error: str,
    retry_count: int = 0,
    raw_output_snippet: str | None = None,
) -> int:
    """Convenience function to broadcast clarification_card error event."""
    handler = get_degraded_state_handler()
    return await handler.broadcast_clarification_card(
        utterance=utterance,
        intent_id=intent_id,
        session_id=session_id,
        parse_error=parse_error,
        retry_count=retry_count,
        raw_output_snippet=raw_output_snippet,
    )
