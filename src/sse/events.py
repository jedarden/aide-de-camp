"""
SSE event types and manager for the Phase 2 self-improvement loop.

This module provides the higher-level SSE surface consumed by the component
library, UI-regen agent, and feedback processor. It defines a typed event
model (``SSEEventType`` + ``Event``) and an ``SSEManager`` that maintains a
registry of caller-provided ``asyncio`` queues and broadcasts typed events to
them.

Real canvas surfaces connect through the SSE stream endpoint in ``src.main``,
which registers them with the lower-level :class:`~src.sse.broadcaster.SSEBroadcaster`.
``broadcast_component_update`` therefore mirrors the event onto that shared
broadcaster so live canvases update in place whenever a component is versioned.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional
from uuid import uuid4

from .broadcaster import SSEEvent, get_broadcaster

logger = logging.getLogger(__name__)


class SSEEventType(Enum):
    """Typed SSE event names."""

    # Connection lifecycle
    CONNECTED = "connected"
    DISCONNECT = "disconnect"

    # Result events
    RESULT_CREATED = "result_created"
    RESULT_UPDATED = "result_updated"

    # Component events (Phase 2)
    COMPONENT_UPDATED = "component_updated"

    # Topic events
    TOPIC_CREATED = "topic_created"
    TOPIC_UPDATED = "topic_updated"


@dataclass
class Event:
    """A typed SSE event delivered to a registered subscriber queue."""

    type: SSEEventType
    data: dict = field(default_factory=dict)


class SSEManager:
    """
    Manage SSE subscribers for the Phase 2 event loop.

    Subscribers register an ``asyncio.Queue`` and receive typed :class:`Event`
    objects. Broadcasts are mirrored onto the global ``SSEBroadcaster`` so that
    canvas surfaces connected through the SSE stream endpoint receive the same
    events.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, asyncio.Queue] = {}

    async def register(self, queue: asyncio.Queue) -> str:
        """Register a subscriber queue and return its subscription id."""
        sub_id = str(uuid4())
        self._subscribers[sub_id] = queue
        logger.info("Registered SSE subscriber %s", sub_id)
        return sub_id

    async def unregister(self, sub_id: str) -> None:
        """Remove a previously registered subscriber queue."""
        if self._subscribers.pop(sub_id, None) is not None:
            logger.info("Unregistered SSE subscriber %s", sub_id)

    async def broadcast(self, event: Event) -> int:
        """
        Push ``event`` onto every registered subscriber queue.

        Returns the number of queues the event was delivered to.
        """
        sent = 0
        for queue in list(self._subscribers.values()):
            try:
                queue.put_nowait(event)
                sent += 1
            except asyncio.QueueFull:
                logger.warning("Queue full for subscriber, dropping event")
        return sent

    async def broadcast_component_update(
        self,
        component_id: str,
        version: int,
        change_note: Optional[str] = None,
    ) -> int:
        """
        Broadcast a ``component_updated`` event.

        Delivered to every registered subscriber (the Phase 2 event loop) and
        mirrored onto the global ``SSEBroadcaster`` so live canvas connections
        update in place when a component is versioned. Returns the number of
        subscriber queues the event was delivered to.
        """
        event = Event(
            type=SSEEventType.COMPONENT_UPDATED,
            data={
                "component_id": component_id,
                "version": version,
                "change_note": change_note,
            },
        )

        sent = await self.broadcast(event)

        # Mirror onto the broadcaster so real canvas surfaces receive the push.
        try:
            broadcaster = get_broadcaster()
            await broadcaster.broadcast(
                SSEEvent(
                    event_type=SSEEventType.COMPONENT_UPDATED.value,
                    data={
                        "component_id": component_id,
                        "version": version,
                    },
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to mirror component_updated to broadcaster: %s", exc)

        return sent


# Global SSE manager instance
_sse_manager: Optional[SSEManager] = None


def get_sse_manager() -> SSEManager:
    """Get or create the global SSE manager."""
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEManager()
    return _sse_manager
