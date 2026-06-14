"""
SSE (Server-Sent Events) for aide-de-camp.

Handles streaming events to connected clients, including component updates.
"""

import json
import time
import asyncio
from typing import Dict, Set, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of SSE events."""
    RESULT = "result"
    RESULT_CREATED = "result_created"
    TOPIC_UPDATED = "topic_updated"
    COMPONENT_UPDATED = "component_updated"
    INTENT_DISPATCHED = "intent_dispatched"
    ACKNOWLEDGMENT = "acknowledgment"
    ERROR = "error"


@dataclass
class SSEEvent:
    """A server-sent event."""
    type: EventType
    data: Dict[str, Any]
    id: Optional[str] = None
    retry: Optional[int] = None

    def to_sse_format(self) -> str:
        """Convert to SSE format."""
        lines = []

        if self.id:
            lines.append(f"id: {self.id}")

        if self.retry:
            lines.append(f"retry: {self.retry}")

        lines.append(f"event: {self.type.value}")
        lines.append(f"data: {json.dumps(self.data)}")
        lines.append("")  # Blank line to end event

        return "\n".join(lines) + "\n"


class SSEConnection:
    """Represents a single SSE client connection."""

    def __init__(self, connection_id: str, queue: asyncio.Queue):
        self.connection_id = connection_id
        self.queue = queue
        self.created_at = time.time()
        self.last_active = time.time()

    async def send(self, event: SSEEvent):
        """Send an event to this connection."""
        await self.queue.put(event)

    def is_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if connection is stale (no activity for timeout)."""
        return (time.time() - self.last_active) > timeout_seconds

    def keepalive(self):
        """Update last active time."""
        self.last_active = time.time()


class SSEManager:
    """
    Manages SSE connections and broadcasts events.

    Usage:
        manager = SSEManager()

        # Register a connection
        queue = asyncio.Queue()
        conn_id = manager.register(queue)

        # Send events to all or specific connections
        await manager.broadcast_to_all(SSEEvent(...))
        await manager.send_to_connection(conn_id, SSEEvent(...))

        # Unregister when done
        manager.unregister(conn_id)
    """

    def __init__(self):
        self._connections: Dict[str, SSEConnection] = {}
        self._connection_counter = 0
        self._lock = asyncio.Lock()

    def generate_connection_id(self) -> str:
        """Generate a unique connection ID."""
        self._connection_counter += 1
        return f"conn-{self._connection_counter}-{int(time.time())}"

    async def register(self, queue: asyncio.Queue) -> str:
        """
        Register a new SSE connection.

        Args:
            queue: The asyncio.Queue for sending events to this client

        Returns:
            The connection ID
        """
        async with self._lock:
            conn_id = self.generate_connection_id()
            self._connections[conn_id] = SSEConnection(conn_id, queue)
            logger.info(f"Registered SSE connection: {conn_id}")
            return conn_id

    async def unregister(self, conn_id: str):
        """Unregister a connection."""
        async with self._lock:
            if conn_id in self._connections:
                del self._connections[conn_id]
                logger.info(f"Unregistered SSE connection: {conn_id}")

    async def send_to_connection(self, conn_id: str, event: SSEEvent):
        """Send an event to a specific connection."""
        async with self._lock:
            connection = self._connections.get(conn_id)
            if connection:
                await connection.send(event)
                connection.keepalive()

    async def broadcast_to_all(self, event: SSEEvent):
        """Broadcast an event to all active connections."""
        async with self._lock:
            stale_connections = []

            for conn_id, connection in self._connections.items():
                try:
                    await connection.send(event)
                    connection.keepalive()
                except Exception as e:
                    logger.error(f"Failed to send to {conn_id}: {e}")
                    stale_connections.append(conn_id)

            # Clean up stale connections
            for conn_id in stale_connections:
                await self.unregister(conn_id)

    async def broadcast_component_update(
        self,
        component_id: str,
        version: int,
        change_note: str
    ):
        """
        Broadcast a component update event.

        This triggers canvas re-render for cards using this component.

        Args:
            component_id: The component that was updated
            version: The new version
            change_note: What changed
        """
        event = SSEEvent(
            type=EventType.COMPONENT_UPDATED,
            data={
                "component_id": component_id,
                "version": version,
                "change_note": change_note,
                "timestamp": int(time.time())
            }
        )
        await self.broadcast_to_all(event)

    async def broadcast_result(
        self,
        result_id: str,
        intent_id: str,
        summary: str,
        data: Dict[str, Any],
        urgency: str
    ):
        """
        Broadcast a result event.

        Args:
            result_id: The result ID
            intent_id: The intent that produced this result
            summary: Result summary
            data: Result data
            urgency: Urgency level
        """
        event = SSEEvent(
            type=EventType.RESULT,
            data={
                "result_id": result_id,
                "intent_id": intent_id,
                "summary": summary,
                "data": data,
                "urgency": urgency,
                "timestamp": int(time.time())
            }
        )
        await self.broadcast_to_all(event)

    async def send_acknowledgment(self, conn_id: str, message: str):
        """Send an acknowledgment to a specific connection."""
        event = SSEEvent(
            type=EventType.ACKNOWLEDGMENT,
            data={
                "message": message,
                "timestamp": int(time.time())
            }
        )
        await self.send_to_connection(conn_id, event)

    async def send_error(self, conn_id: str, error: str, details: Optional[str] = None):
        """Send an error to a specific connection."""
        event = SSEEvent(
            type=EventType.ERROR,
            data={
                "error": error,
                "details": details,
                "timestamp": int(time.time())
            }
        )
        await self.send_to_connection(conn_id, event)

    async def cleanup_stale_connections(self, timeout_seconds: int = 300):
        """Remove stale connections (no activity for timeout)."""
        async with self._lock:
            stale = [
                conn_id
                for conn_id, conn in self._connections.items()
                if conn.is_stale(timeout_seconds)
            ]

            for conn_id in stale:
                await self.unregister(conn_id)

        if stale:
            logger.info(f"Cleaned up {len(stale)} stale SSE connections")

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self._connections)


# Singleton instance
_manager: Optional[SSEManager] = None


def get_sse_manager() -> SSEManager:
    """Get or create the SSE manager singleton."""
    global _manager
    if _manager is None:
        _manager = SSEManager()
    return _manager


# Event handlers that can be registered for specific event types
class EventBus:
    """
    In-memory event bus for component updates.

    Allows different parts of the system to react to component changes.
    """

    def __init__(self):
        self._listeners: Dict[EventType, Set[Callable]] = {}

    def subscribe(self, event_type: EventType, callback: Callable):
        """Subscribe to an event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = set()
        self._listeners[event_type].add(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable):
        """Unsubscribe from an event type."""
        if event_type in self._listeners:
            self._listeners[event_type].discard(callback)

    async def publish(self, event: SSEEvent):
        """Publish an event to all subscribers."""
        listeners = self._listeners.get(event.type, set())
        for callback in listeners:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Event listener error: {e}")


# Singleton event bus
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the event bus singleton."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
