"""
SSE broadcaster: stream results to connected surfaces.

Manages SSE connections and broadcasts events to relevant surfaces.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Set
from uuid import uuid4

from fastapi import Request

logger = logging.getLogger(__name__)


@dataclass
class SSEConnection:
    """An active SSE connection."""
    connection_id: str
    surface_id: str
    session_id: str
    surface_type: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    connected_at: float = field(default_factory=lambda: datetime.now().timestamp())
    last_heartbeat: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class SSEEvent:
    """An SSE event to broadcast."""
    event_type: str
    data: dict
    target_session_id: str | None = None
    target_surface_id: str | None = None
    exclude_surface_id: str | None = None


class SSEBroadcaster:
    """
    Manages SSE connections and broadcasts events.

    Events are queued per-connection and sent via SSE.
    """

    def __init__(self):
        self.connections: Dict[str, SSEConnection] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the broadcaster and cleanup task."""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop the broadcaster and cleanup task."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    def register(
        self,
        surface_id: str,
        session_id: str,
        surface_type: str,
    ) -> SSEConnection:
        """Register a new SSE connection."""
        connection_id = str(uuid4())
        connection = SSEConnection(
            connection_id=connection_id,
            surface_id=surface_id,
            session_id=session_id,
            surface_type=surface_type,
        )
        self.connections[connection_id] = connection
        logger.info(f"Registered SSE connection {connection_id} for surface {surface_id}")
        return connection

    def unregister(self, connection_id: str) -> None:
        """Unregister an SSE connection."""
        if connection_id in self.connections:
            conn = self.connections[connection_id]
            logger.info(f"Unregistered SSE connection {connection_id} for surface {conn.surface_id}")
            del self.connections[connection_id]

    def heartbeat(self, connection_id: str) -> bool:
        """Update heartbeat for a connection. Returns True if connection exists."""
        if connection_id in self.connections:
            self.connections[connection_id].last_heartbeat = datetime.now().timestamp()
            return True
        return False

    async def broadcast(self, event: SSEEvent) -> int:
        """
        Broadcast an event to relevant connections.

        Returns the number of connections the event was sent to.
        """
        sent_count = 0

        for conn in list(self.connections.values()):
            # Filter by target
            if event.target_session_id and conn.session_id != event.target_session_id:
                continue
            if event.target_surface_id and conn.surface_id != event.target_surface_id:
                continue
            if event.exclude_surface_id and conn.surface_id == event.exclude_surface_id:
                continue

            # Queue the event
            try:
                conn.queue.put_nowait(event)
                sent_count += 1
            except asyncio.QueueFull:
                logger.warning(f"Queue full for connection {conn.connection_id}, dropping event")

        return sent_count

    async def event_generator(self, connection: SSEConnection):
        """
        Generate SSE events for a connection.

        Yields formatted SSE messages.
        """
        try:
            # Send initial connection event
            yield self._format_sse("connected", {
                "connection_id": connection.connection_id,
                "surface_id": connection.surface_id,
                "session_id": connection.session_id,
            })

            while True:
                event = await connection.queue.get()
                connection.last_heartbeat = datetime.now().timestamp()

                # Format and yield the event
                yield self._format_sse(event.event_type, event.data)

                # Special case: disconnect event ends the stream
                if event.event_type == "disconnect":
                    logger.info(f"Disconnect event for connection {connection.connection_id}")
                    break

        except asyncio.CancelledError:
            logger.info(f"Connection {connection.connection_id} cancelled")
            raise
        finally:
            self.unregister(connection.connection_id)

    def _format_sse(self, event_type: str, data: dict) -> str:
        """Format an event as SSE."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    async def _cleanup_loop(self):
        """Periodically clean up dead connections."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                now = datetime.now().timestamp()
                timeout = 300  # 5 minutes

                dead_connections = [
                    cid for cid, conn in self.connections.items()
                    if (now - conn.last_heartbeat) > timeout
                ]

                for cid in dead_connections:
                    logger.info(f"Cleaning up dead connection {cid}")
                    # Send disconnect event before removing
                    try:
                        conn = self.connections[cid]
                        conn.queue.put_nowait(SSEEvent(
                            event_type="disconnect",
                            data={"reason": "timeout"},
                        ))
                    except asyncio.QueueFull:
                        pass
                    self.unregister(cid)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")


# Global broadcaster instance
_broadcaster: SSEBroadcaster | None = None


def get_broadcaster() -> SSEBroadcaster:
    """Get or create the global SSE broadcaster."""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = SSEBroadcaster()
    return _broadcaster


# Event types
class EventType:
    """SSE event types."""

    # Connection lifecycle
    CONNECTED = "connected"
    DISCONNECT = "disconnect"
    HEARTBEAT = "heartbeat"

    # Result events
    RESULT_CREATED = "result_created"
    RESULT_UPDATED = "result_updated"

    # Intent events
    INTENT_PENDING = "intent_pending"
    INTENT_DISPATCHED = "intent_dispatched"
    INTENT_RESOLVED = "intent_resolved"

    # Topic events
    TOPIC_CREATED = "topic_created"
    TOPIC_UPDATED = "topic_updated"
    TOPIC_STALE = "topic_stale"

    # Workload events
    WORKLOAD_SUMMARY = "workload_summary"
    EXCEPTION_RAISED = "exception_raised"

    # Bead events
    BEAD_CLOSED = "bead_closed"
    BEAD_FAILED = "bead_failed"


async def broadcast_result(
    result: dict,
    session_id: str,
    target_surface_id: str | None = None,
) -> int:
    """
    Broadcast a result to relevant surfaces.

    Returns the number of connections the event was sent to.
    """
    broadcaster = get_broadcaster()
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data=result,
        target_session_id=session_id,
        target_surface_id=target_surface_id,
    )
    return await broadcaster.broadcast(event)


async def broadcast_intent_update(
    intent: dict,
    session_id: str,
    event_type: str = EventType.INTENT_RESOLVED,
) -> int:
    """Broadcast an intent status update."""
    broadcaster = get_broadcaster()
    event = SSEEvent(
        event_type=event_type,
        data=intent,
        target_session_id=session_id,
    )
    return await broadcaster.broadcast(event)


async def broadcast_workload_summary(
    session_id: str,
    summary: dict,
    surface_id: str | None = None,
) -> int:
    """Broadcast a workload summary (for reconnection)."""
    broadcaster = get_broadcaster()
    event = SSEEvent(
        event_type=EventType.WORKLOAD_SUMMARY,
        data=summary,
        target_session_id=session_id,
        target_surface_id=surface_id,
    )
    return await broadcaster.broadcast(event)
