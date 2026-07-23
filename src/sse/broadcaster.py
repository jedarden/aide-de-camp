"""
SSE broadcaster: stream results to connected surfaces.

Manages SSE connections and broadcasts events to relevant surfaces.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict
from uuid import uuid4

# Idle-stream keepalive. An SSE connection that sends nothing while it waits for
# events is indistinguishable from a dead one: the browser's EventSource only
# fires ``onerror`` when there is I/O to fail, so a *silent* network drop on an
# idle stream leaves the surface showing "Connected" indefinitely (until the
# OS-level TCP keepalive times out, many minutes later). Emitting a comment
# line (``": ping\n\n"``) every few seconds keeps traffic flowing, so:
#
#   - proxies/load balancers won't reap the connection as idle, and
#   - the next ping after a real network drop fails to arrive, the client read
#     errors, ``onerror`` fires, and the native EventSource reconnects — which
#     is exactly the resync path the canvas relies on.
#
# Comment lines are ignored by EventSource (they never surface as messages), so
# this adds no client-visible events. ``5s`` is frequent enough that a drop is
# surfaced well inside any realistic reconnect budget, and quiet enough not to
# be chatty. Lower it (e.g. via ADC_SSE_KEEPALIVE_SECONDS) for faster
# reconnection tests.
KEEPALIVE_INTERVAL_SECONDS = float(
    os.environ.get("ADC_SSE_KEEPALIVE_SECONDS", "5")
)

# Sentinel pushed onto a connection's queue by :meth:`SSEBroadcaster.drop_session`
# to make that connection's :meth:`event_generator` return ABRUPTLY — i.e. without
# emitting a ``disconnect`` event. An abrupt end of the response body is what the
# browser's ``EventSource`` treats as a dropped connection: it fires ``onerror``
# and performs its NATIVE auto-reconnect. (The graceful ``disconnect`` event, by
# contrast, makes the client call ``close()`` and stay down.) This is the only
# way to faithfully simulate a real proxy/server connection drop from a test
# against a loopback server — Playwright ``context.set_offline`` cannot break an
# already-established loopback SSE stream (see tests/e2e/_probe_offline.py).
_DROP = object()


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
    """An SSE event to broadcast.

    Attributes:
        event_type: The type of SSE event (e.g., 'result_created', 'topic_updated')
        data: The event payload data
        rendered_html: Optional rendered HTML for canvas injection (e.g., pre-rendered card)
        target_session_id: Optional filter to only send to connections for this session
        target_surface_id: Optional filter to only send to this specific surface
        exclude_surface_id: Optional filter to exclude this surface from receiving the event
    """
    event_type: str
    data: dict
    rendered_html: str | None = None
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

    def drop_session(self, session_id: str) -> int:
        """Abruptly drop every live SSE stream for ``session_id``.

        Pushes the ``_DROP`` sentinel onto each matching connection's queue so
        its :meth:`event_generator` returns without emitting a ``disconnect``
        event — the browser's ``EventSource`` then sees the stream end abruptly,
        fires ``onerror``, and performs its native auto-reconnect. Returns the
        number of streams signalled. Used by ``POST /api/v1/test/drop-sse`` to
        faithfully simulate a real proxy/server connection drop, which
        ``context.set_offline`` cannot reproduce against a loopback server
        (loopback connections are exempt from offline emulation — see
        tests/e2e/_probe_offline.py).
        """
        count = 0
        for conn in self.connections.values():
            if conn.session_id == session_id:
                conn.queue.put_nowait(_DROP)
                count += 1
        if count:
            logger.info(f"Drop requested for session {session_id}: {count} stream(s)")
        return count

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
                # Block on the next event, but no longer than the keepalive
                # interval: if nothing arrives, emit a comment-line ping so the
                # stream is never silent. A silent idle stream is indistinguish-
                # able from a dead one to the browser — EventSource only fires
                # ``onerror`` when there is I/O to fail — so without these pings
                # a real network drop on an idle surface leaves it showing
                # "Connected" until the OS TCP keepalive times out (minutes
                # later). The ping is a comment line (``": ping\n\n"``), which
                # EventSource ignores — it surfaces no message to the client.
                try:
                    event = await asyncio.wait_for(
                        connection.queue.get(),
                        timeout=KEEPALIVE_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                # Abrupt drop sentinel (see _DROP): end the stream WITHOUT a
                # disconnect event so the browser EventSource onerrors + reconnects.
                if event is _DROP:
                    logger.info(f"Drop sentinel on connection {connection.connection_id}")
                    return

                connection.last_heartbeat = datetime.now().timestamp()

                # Format and yield the event
                payload = dict(event.data)
                if event.rendered_html is not None:
                    payload["rendered_html"] = event.rendered_html
                yield self._format_sse(event.event_type, payload)

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

    # Component events (Phase 2)
    COMPONENT_UPDATED = "component_updated"

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

    # Circuit breaker events
    TASK_STUCK = "task_stuck"
    TASK_FAILED = "task_failed"

    # Degraded-state error events (see docs/plan/plan.md: Degraded-State UX)
    ROUTER_UNAVAILABLE = "router_unavailable"
    ALL_SOURCES_FAILED = "all_sources_failed"
    DEGRADED_RAW_DATA = "degraded_raw_data"
    CLARIFICATION_CARD = "clarification_card"
    MALFORMED_RESPONSE = "malformed_response"


async def broadcast_result(
    result: dict,
    session_id: str,
    target_surface_id: str | None = None,
    rendered_html: str | None = None,
) -> int:
    """
    Broadcast a result to relevant surfaces.

    Args:
        result: The result data payload
        session_id: The session ID to target
        target_surface_id: Optional specific surface to target
        rendered_html: Optional pre-rendered HTML for canvas injection

    Returns the number of connections the event was sent to.
    """
    broadcaster = get_broadcaster()
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data=result,
        rendered_html=rendered_html,
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
