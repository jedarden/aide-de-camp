"""
Comprehensive tests for SSE broadcast functionality (bead adc-30on7).

Tests verify all aspects of the SSE broadcaster:
- Basic SSE broadcast functionality
- Surface ID targeting (target_surface_id, exclude_surface_id)
- Session ID targeting (target_session_id)
- Event types (especially "result_created")
- Broadcast timing and concurrent operations
- Connection registration/unregistration
- Broadcaster lifecycle (start/stop)
- Queue behavior and overflow handling
"""
import asyncio
import pytest
from uuid import uuid4

from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEEvent,
    EventType,
    get_broadcaster,
    _DROP,
    KEEPALIVE_INTERVAL_SECONDS,
)


# --- Test fixtures ----------------------------------------------------------------


@pytest.fixture
async def broadcaster():
    """Create a fresh broadcaster instance for each test."""
    b = SSEBroadcaster()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
async def global_broadcaster():
    """Reset the global broadcaster singleton for each test."""
    # Reset the global singleton
    import src.sse.broadcaster as sse_mod
    sse_mod._broadcaster = None
    b = get_broadcaster()
    await b.start()
    yield b
    await b.stop()
    sse_mod._broadcaster = None


# --- Basic broadcast tests ------------------------------------------------------


class TestBasicSSEBroadcast:
    """Test basic SSE broadcast functionality."""

    async def test_broadcast_to_single_connection(self, broadcaster):
        """Event is broadcast to a single registered connection."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "test result"}
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1

        # Verify event is in the queue
        queued_event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert queued_event.event_type == EventType.RESULT_CREATED
        assert queued_event.data == {"message": "test result"}

        broadcaster.unregister(conn.connection_id)

    async def test_broadcast_to_multiple_connections(self, broadcaster):
        """Event is broadcast to all registered connections."""
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id="surface-3",
            session_id="session-2",
            surface_type="terminal"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "broadcast to all"}
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 3

        # All connections should receive the event
        for conn in [conn1, conn2, conn3]:
            queued_event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
            assert queued_event.event_type == EventType.RESULT_CREATED

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)
        broadcaster.unregister(conn3.connection_id)

    async def test_no_connections_returns_zero(self, broadcaster):
        """Broadcast with no registered connections returns 0."""
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "no receivers"}
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 0

    async def test_event_type_result_created(self, broadcaster):
        """Test that event_type='result_created' works correctly."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type="result_created",  # Using the exact string
            data={"intent_id": "intent-1", "summary": "Test result"}
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1

        queued_event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert queued_event.event_type == "result_created"
        assert queued_event.data["intent_id"] == "intent-1"

        broadcaster.unregister(conn.connection_id)

    async def test_rendered_html_included_in_event(self, broadcaster):
        """rendered_html field is preserved in the queued event."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"summary": "test"},
            rendered_html="<div>Pre-rendered content</div>"
        )

        await broadcaster.broadcast(event)

        queued_event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert queued_event.rendered_html == "<div>Pre-rendered content</div>"

        broadcaster.unregister(conn.connection_id)


# --- Surface ID targeting tests -------------------------------------------------


class TestSurfaceIDTargeting:
    """Test surface ID targeting functionality."""

    async def test_target_surface_id_sends_only_to_target(self, broadcaster):
        """target_surface_id filters to only the specified surface."""
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id="surface-3",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "targeted"},
            target_surface_id="surface-2"
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1  # Only surface-2 receives

        # Only conn2 should have the event
        event_from_2 = await asyncio.wait_for(conn2.queue.get(), timeout=1.0)
        assert event_from_2.data["message"] == "targeted"

        # conn1 and conn3 queues should be empty
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn1.queue.get(), timeout=0.1)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn3.queue.get(), timeout=0.1)

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)
        broadcaster.unregister(conn3.connection_id)

    async def test_exclude_surface_id_excludes_target(self, broadcaster):
        """exclude_surface_id sends to all except the specified surface."""
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id="surface-3",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "broadcast except surface-2"},
            exclude_surface_id="surface-2"
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 2  # surface-1 and surface-3

        # conn1 and conn3 should receive
        await asyncio.wait_for(conn1.queue.get(), timeout=1.0)
        await asyncio.wait_for(conn3.queue.get(), timeout=1.0)

        # conn2 should not receive
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn2.queue.get(), timeout=0.1)

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)
        broadcaster.unregister(conn3.connection_id)

    async def test_target_and_exclude_combined(self, broadcaster):
        """exclude_surface_id takes precedence when both target same surface."""
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "excluded"},
            target_surface_id="surface-2",
            exclude_surface_id="surface-2"  # Exclude wins when both target same
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 0  # Exclude wins

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)


# --- Session ID targeting tests -------------------------------------------------


class TestSurfaceIDTargetingEdgeCases:
    """Test edge cases for surface ID targeting (bead adc-1cxul)."""

    async def test_target_nonexistent_surface_returns_zero(self, broadcaster):
        """Targeting a non-existent surface_id returns 0."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "should not send"},
            target_surface_id="nonexistent-surface"
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 0  # No surfaces match

        # Verify conn queue is empty
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn.queue.get(), timeout=0.1)

        broadcaster.unregister(conn.connection_id)

    async def test_target_with_rendered_html(self, broadcaster):
        """Targeted broadcast includes rendered_html field."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"summary": "test"},
            rendered_html="<div>Targeted content</div>",
            target_surface_id="surface-1"
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1

        queued = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert queued.rendered_html == "<div>Targeted content</div>"
        assert queued.data["summary"] == "test"

        broadcaster.unregister(conn.connection_id)

    async def test_concurrent_targeted_broadcasts(self, broadcaster):
        """Multiple concurrent broadcasts to different targets work correctly."""
        # Create multiple connections
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id="surface-3",
            session_id="session-1",
            surface_type="canvas"
        )

        # Create events targeting different surfaces
        events = [
            SSEEvent(
                event_type=EventType.RESULT_CREATED,
                data={"target": 1},
                target_surface_id="surface-1"
            ),
            SSEEvent(
                event_type=EventType.RESULT_CREATED,
                data={"target": 2},
                target_surface_id="surface-2"
            ),
            SSEEvent(
                event_type=EventType.RESULT_CREATED,
                data={"target": 3},
                target_surface_id="surface-3"
            ),
        ]

        # Broadcast all concurrently
        tasks = [broadcaster.broadcast(event) for event in events]
        results = await asyncio.gather(*tasks)

        # Each should reach exactly one surface
        assert all(count == 1 for count in results)

        # Verify each connection got its specific event
        event1 = await asyncio.wait_for(conn1.queue.get(), timeout=1.0)
        assert event1.data["target"] == 1

        event2 = await asyncio.wait_for(conn2.queue.get(), timeout=1.0)
        assert event2.data["target"] == 2

        event3 = await asyncio.wait_for(conn3.queue.get(), timeout=1.0)
        assert event3.data["target"] == 3

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)
        broadcaster.unregister(conn3.connection_id)

    async def test_target_surface_different_session(self, broadcaster):
        """target_surface_id only matches surface, regardless of session."""
        # Same surface_id in different sessions
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-1",  # Same surface_id
            session_id="session-2",  # Different session
            surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )

        # Target surface-1 without session filter
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "to both surface-1s"},
            target_surface_id="surface-1"
        )

        sent_count = await broadcaster.broadcast(event)
        # Both surface-1 connections should receive (different sessions)
        assert sent_count == 2

        # Both conn1 and conn2 should receive
        event1 = await asyncio.wait_for(conn1.queue.get(), timeout=1.0)
        assert event1.data["message"] == "to both surface-1s"

        event2 = await asyncio.wait_for(conn2.queue.get(), timeout=1.0)
        assert event2.data["message"] == "to both surface-1s"

        # conn3 should not receive
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn3.queue.get(), timeout=0.1)

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)
        broadcaster.unregister(conn3.connection_id)

    async def test_target_session_and_surface_intersection(self, broadcaster):
        """Combining target_session_id and target_surface_id filters to intersection."""
        # Setup: multiple surfaces across multiple sessions
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-2",
            surface_type="canvas"
        )
        conn4 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-2",
            surface_type="canvas"
        )

        # Target exact intersection: session-1 AND surface-2
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "exact match"},
            target_session_id="session-1",
            target_surface_id="surface-2"
        )

        sent_count = await broadcaster.broadcast(event)
        # Only conn2 matches both filters
        assert sent_count == 1

        # Verify only conn2 received
        event2 = await asyncio.wait_for(conn2.queue.get(), timeout=1.0)
        assert event2.data["message"] == "exact match"

        # Others should not receive
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn1.queue.get(), timeout=0.1)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn3.queue.get(), timeout=0.1)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn4.queue.get(), timeout=0.1)

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)
        broadcaster.unregister(conn3.connection_id)
        broadcaster.unregister(conn4.connection_id)


class TestSessionIDTargeting:
    """Test session ID targeting functionality."""

    async def test_target_session_id_filters_by_session(self, broadcaster):
        """target_session_id filters to only connections for that session."""
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id="surface-3",
            session_id="session-2",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "session-1 only"},
            target_session_id="session-1"
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 2  # Only session-1 connections

        # conn1 and conn2 should receive
        await asyncio.wait_for(conn1.queue.get(), timeout=1.0)
        await asyncio.wait_for(conn2.queue.get(), timeout=1.0)

        # conn3 should not receive
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn3.queue.get(), timeout=0.1)

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)
        broadcaster.unregister(conn3.connection_id)

    async def test_session_and_surface_filters_combined(self, broadcaster):
        """target_session_id and target_surface_id can be combined."""
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-2",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "exact match"},
            target_session_id="session-1",
            target_surface_id="surface-2"
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1  # Only conn2 matches both

        # Verify only conn2 received
        await asyncio.wait_for(conn2.queue.get(), timeout=1.0)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn1.queue.get(), timeout=0.1)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn3.queue.get(), timeout=0.1)

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)
        broadcaster.unregister(conn3.connection_id)


# --- Broadcast timing and concurrency tests -----------------------------------


class TestBroadcastTimingAndConcurrency:
    """Test broadcast timing and concurrent operations."""

    async def test_concurrent_broadcasts(self, broadcaster):
        """Multiple concurrent broadcasts are handled correctly."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        # Send multiple events concurrently
        events = [
            SSEEvent(event_type=f"event_{i}", data={"index": i})
            for i in range(10)
        ]

        # Broadcast all concurrently
        tasks = [broadcaster.broadcast(event) for event in events]
        results = await asyncio.gather(*tasks)

        assert all(count == 1 for count in results)

        # All events should be queued
        received = []
        for _ in range(10):
            event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
            received.append(event.event_type)

        assert set(received) == {f"event_{i}" for i in range(10)}

        broadcaster.unregister(conn.connection_id)

    async def test_broadcast_during_event_iteration(self, broadcaster):
        """Broadcasting while iterating over connections doesn't cause issues."""
        # Register many connections
        connections = [
            broadcaster.register(
                surface_id=f"surface-{i}",
                session_id="session-1",
                surface_type="canvas"
            )
            for i in range(20)
        ]

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "test"}
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 20

        # Verify all connections received
        for conn in connections:
            await asyncio.wait_for(conn.queue.get(), timeout=1.0)
            broadcaster.unregister(conn.connection_id)

    async def test_timing_multiple_connections_different_speeds(self, broadcaster):
        """Connections consuming events at different speeds don't interfere."""
        # Fast consumer
        fast_conn = broadcaster.register(
            surface_id="fast-surface",
            session_id="session-1",
            surface_type="canvas"
        )

        # Slow consumer (will process later)
        slow_conn = broadcaster.register(
            surface_id="slow-surface",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "timing test"}
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 2

        # Fast consumer processes immediately
        fast_event = await asyncio.wait_for(fast_conn.queue.get(), timeout=1.0)
        assert fast_event.event_type == EventType.RESULT_CREATED

        # Slow consumer still has the event queued
        slow_event = await asyncio.wait_for(slow_conn.queue.get(), timeout=1.0)
        assert slow_event.event_type == EventType.RESULT_CREATED

        broadcaster.unregister(fast_conn.connection_id)
        broadcaster.unregister(slow_conn.connection_id)


# --- Connection management tests ----------------------------------------------


class TestConnectionManagement:
    """Test connection registration and lifecycle."""

    async def test_register_creates_connection_with_unique_id(self, broadcaster):
        """Each registration creates a unique connection."""
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-1",  # Same surface
            session_id="session-1",  # Same session
            surface_type="canvas"
        )

        # Different connection IDs
        assert conn1.connection_id != conn2.connection_id
        assert conn1.surface_id == conn2.surface_id
        assert conn1.session_id == conn2.session_id

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)

    async def test_unregister_removes_connection(self, broadcaster):
        """Unregistering removes connection from broadcaster."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        assert conn.connection_id in broadcaster.connections
        broadcaster.unregister(conn.connection_id)
        assert conn.connection_id not in broadcaster.connections

    async def test_unregister_nonexistent_is_safe(self, broadcaster):
        """Unregistering a non-existent connection doesn't raise."""
        # Should not raise
        broadcaster.unregister("nonexistent-id")

    async def test_heartbeat_updates_timestamp(self, broadcaster):
        """heartbeat() updates last_heartbeat timestamp."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        initial_heartbeat = conn.last_heartbeat

        # Wait a bit
        await asyncio.sleep(0.1)

        # Update heartbeat
        success = broadcaster.heartbeat(conn.connection_id)
        assert success is True
        assert conn.last_heartbeat > initial_heartbeat

        broadcaster.unregister(conn.connection_id)

    async def test_heartbeat_nonexistent_returns_false(self, broadcaster):
        """heartbeat() returns False for nonexistent connection."""
        success = broadcaster.heartbeat("nonexistent-id")
        assert success is False

    async def test_connection_queue_is_asyncio_queue(self, broadcaster):
        """Connection queue is an asyncio.Queue for async operations."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        # Should be able to use async queue operations
        import asyncio
        assert isinstance(conn.queue, asyncio.Queue)

        # Should be empty initially
        assert conn.queue.empty()

        broadcaster.unregister(conn.connection_id)


# --- Broadcaster lifecycle tests ----------------------------------------------


class TestBroadcasterLifecycle:
    """Test broadcaster start/stop lifecycle."""

    async def test_start_sets_running_flag(self):
        """start() sets the _running flag."""
        b = SSEBroadcaster()
        assert b._running is False

        await b.start()
        assert b._running is True

        await b.stop()

    async def test_start_creates_cleanup_task(self):
        """start() creates the cleanup task."""
        b = SSEBroadcaster()
        assert b._cleanup_task is None

        await b.start()
        assert b._cleanup_task is not None
        assert isinstance(b._cleanup_task, asyncio.Task)

        await b.stop()

    async def test_stop_clears_running_flag(self):
        """stop() clears the _running flag."""
        b = SSEBroadcaster()
        await b.start()
        assert b._running is True

        await b.stop()
        assert b._running is False

    async def test_stop_cancels_cleanup_task(self):
        """stop() cancels the cleanup task gracefully."""
        b = SSEBroadcaster()
        await b.start()
        task = b._cleanup_task

        await b.stop()

        # Task should be done
        assert task.done()

    async def test_multiple_starts_safe(self):
        """Calling start() multiple times is safe."""
        b = SSEBroadcaster()
        await b.start()
        await b.start()  # Should not raise

        assert b._running is True
        await b.stop()

    async def test_multiple_stops_safe(self):
        """Calling stop() multiple times is safe."""
        b = SSEBroadcaster()
        await b.start()
        await b.stop()
        await b.stop()  # Should not raise

        assert b._running is False


# --- Global broadcaster tests --------------------------------------------------


class TestGlobalBroadcaster:
    """Test the global broadcaster singleton."""

    def test_get_broadcaster_returns_singleton(self, global_broadcaster):
        """get_broadcaster() returns the same instance."""
        b1 = get_broadcaster()
        b2 = get_broadcaster()
        assert b1 is b2

    def test_get_broadcaster_creates_instance_if_none(self):
        """get_broadcaster() creates instance if called first time."""
        # Reset
        import src.sse.broadcaster as sse_mod
        sse_mod._broadcaster = None

        b = get_broadcaster()
        assert b is not None
        assert isinstance(b, SSEBroadcaster)


# --- Event generator tests -----------------------------------------------------


class TestEventGenerator:
    """Test the SSE event generator."""

    async def test_event_generator_emits_connected_event(self, broadcaster):
        """event_generator emits initial 'connected' event."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        events = []
        async for event in broadcaster.event_generator(conn):
            events.append(event)
            if len(events) >= 1:  # Just get the connected event
                await broadcaster.broadcast(SSEEvent(
                    event_type=EventType.DISCONNECT,
                    data={"reason": "test complete"}
                ))
                break

        assert len(events) == 1
        assert "event: connected" in events[0]
        assert "connection_id" in events[0]
        assert "surface-1" in events[0]

    async def test_event_generator_emits_queued_events(self, broadcaster):
        """event_generator emits queued events as SSE."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        # Queue an event before consuming
        await broadcaster.broadcast(
            SSEEvent(
                event_type=EventType.RESULT_CREATED,
                data={"message": "test"},
                target_surface_id="surface-1"
            )
        )

        events = []
        async for event in broadcaster.event_generator(conn):
            events.append(event)

            # Collect until we get our result
            if "result_created" in event:
                await broadcaster.broadcast(SSEEvent(
                    event_type=EventType.DISCONNECT,
                    data={"reason": "test complete"}
                ))
                break

        # Should have: connected, result_created
        assert len(events) >= 2
        assert any("result_created" in e for e in events)

    async def test_event_generator_sends_keepalive_pings(self, broadcaster):
        """event_generator sends keepalive comment lines when idle."""
        # Use a very short keepalive for testing
        import os
        original_keepalive = os.environ.get("ADC_SSE_KEEPALIVE_SECONDS")
        os.environ["ADC_SSE_KEEPALIVE_SECONDS"] = "0.1"  # 100ms

        try:
            # Recreate broadcaster to pick up new env var
            b = SSEBroadcaster()
            await b.start()

            conn = b.register(
                surface_id="surface-1",
                session_id="session-1",
                surface_type="canvas"
            )

            events = []
            start_time = asyncio.get_event_loop().time()

            async for event in b.event_generator(conn):
                events.append(event)
                elapsed = asyncio.get_event_loop().time() - start_time

                # Collect for at least 0.3 seconds to get multiple pings
                if elapsed > 0.3:
                    await b.broadcast(SSEEvent(
                        event_type=EventType.DISCONNECT,
                        data={"reason": "test complete"}
                    ))
                    break

            # Should have received at least one keepalive ping
            assert any(": ping" in e for e in events)

            await b.stop()
        finally:
            if original_keepalive is None:
                os.environ.pop("ADC_SSE_KEEPALIVE_SECONDS", None)
            else:
                os.environ["ADC_SSE_KEEPALIVE_SECONDS"] = original_keepalive

    async def test_disconnect_event_ends_stream(self, broadcaster):
        """Disconnect event ends the event generator stream."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        event_count = 0
        async for event in broadcaster.event_generator(conn):
            event_count += 1

            # Send disconnect after first event
            if event_count >= 2:  # After connected event
                await broadcaster.broadcast(SSEEvent(
                    event_type=EventType.DISCONNECT,
                    data={"reason": "test"}
                ))

        # Stream should have ended
        assert event_count >= 2  # connected + disconnect

    async def test_event_generator_unregister_on_completion(self, broadcaster):
        """event_generator unregisters connection when disconnect event ends stream."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        assert conn.connection_id in broadcaster.connections

        # Run the generator to completion by consuming until disconnect
        gen = broadcaster.event_generator(conn)
        async for _ in gen:
            # Send disconnect to end the stream
            await broadcaster.broadcast(SSEEvent(
                event_type=EventType.DISCONNECT,
                data={"reason": "test"}
            ))

        # After the generator completes, connection should be unregistered
        # (The finally block in event_generator calls unregister)
        assert conn.connection_id not in broadcaster.connections


# --- Drop session tests --------------------------------------------------------


class TestDropSession:
    """Test session dropping functionality."""

    async def test_drop_session_sends_drop_sentinel(self, broadcaster):
        """drop_session() sends _DROP sentinel to matching connections."""
        conn1 = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )
        conn2 = broadcaster.register(
            surface_id="surface-2",
            session_id="session-1",
            surface_type="canvas"
        )
        conn3 = broadcaster.register(
            surface_id="surface-3",
            session_id="session-2",
            surface_type="canvas"
        )

        count = broadcaster.drop_session("session-1")
        assert count == 2  # Two connections in session-1

        # Verify the sentinel was queued
        item1 = await asyncio.wait_for(conn1.queue.get(), timeout=1.0)
        item2 = await asyncio.wait_for(conn2.queue.get(), timeout=1.0)

        assert item1 is _DROP
        assert item2 is _DROP

        # conn3 queue should be empty
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(conn3.queue.get(), timeout=0.1)

        broadcaster.unregister(conn1.connection_id)
        broadcaster.unregister(conn2.connection_id)
        broadcaster.unregister(conn3.connection_id)

    async def test_drop_session_nonexistent_returns_zero(self, broadcaster):
        """drop_session() returns 0 for nonexistent session."""
        count = broadcaster.drop_session("nonexistent-session")
        assert count == 0


# --- Integration tests with helper functions -----------------------------------


class TestBroadcastHelperFunctions:
    """Test the helper broadcast functions in the module."""

    async def test_broadcast_result_function(self, global_broadcaster):
        """broadcast_result() helper works correctly."""
        from src.sse.broadcaster import broadcast_result

        conn = global_broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        result = {
            "intent_id": "intent-1",
            "summary": "Test result"
        }

        sent_count = await broadcast_result(
            result=result,
            session_id="session-1",
            target_surface_id="surface-1"
        )

        assert sent_count == 1

        event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data["intent_id"] == "intent-1"

        global_broadcaster.unregister(conn.connection_id)

    async def test_broadcast_result_with_rendered_html(self, global_broadcaster):
        """broadcast_result() passes through rendered_html."""
        from src.sse.broadcaster import broadcast_result

        conn = global_broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        sent_count = await broadcast_result(
            result={"summary": "test"},
            session_id="session-1",
            target_surface_id="surface-1",
            rendered_html="<div>Pre-rendered</div>"
        )

        assert sent_count == 1

        event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert event.rendered_html == "<div>Pre-rendered</div>"

        global_broadcaster.unregister(conn.connection_id)

    async def test_broadcast_fetch_progress_function(self, global_broadcaster):
        """broadcast_fetch_progress() helper works correctly."""
        from src.sse.broadcaster import broadcast_fetch_progress

        conn = global_broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        sent_count = await broadcast_fetch_progress(
            intent_id="intent-1",
            session_id="session-1",
            completed=3,
            total=5,
            source_name="test-source",
            source_status="complete"
        )

        assert sent_count == 1

        event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert event.event_type == EventType.FETCH_PROGRESS
        assert event.data["completed"] == 3
        assert event.data["total"] == 5

        global_broadcaster.unregister(conn.connection_id)

    async def test_broadcast_synthesis_progress_function(self, global_broadcaster):
        """broadcast_synthesis_progress() helper works correctly."""
        from src.sse.broadcaster import broadcast_synthesis_progress

        conn = global_broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        sent_count = await broadcast_synthesis_progress(
            intent_id="intent-1",
            session_id="session-1",
            text_chunk="Another chunk of text"
        )

        assert sent_count == 1

        event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert event.event_type == EventType.SYNTHESIS_PROGRESS
        assert event.data["text_chunk"] == "Another chunk of text"

        global_broadcaster.unregister(conn.connection_id)


# --- Edge case tests ----------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_empty_event_data(self, broadcaster):
        """Event with empty data dict is handled correctly."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={}
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1

        queued = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert queued.data == {}

        broadcaster.unregister(conn.connection_id)

    async def test_large_event_data(self, broadcaster):
        """Large event data is handled correctly."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        large_data = {"items": [f"item-{i}" for i in range(1000)]}

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data=large_data
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1

        queued = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert len(queued.data["items"]) == 1000

        broadcaster.unregister(conn.connection_id)

    async def test_unicode_in_event_data(self, broadcaster):
        """Unicode characters in event data are preserved."""
        conn = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"message": "Hello 世界 🌍"}
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1

        queued = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert queued.data["message"] == "Hello 世界 🌍"

        broadcaster.unregister(conn.connection_id)

    async def test_special_characters_in_surface_session_ids(self, broadcaster):
        """Special characters in IDs are handled correctly."""
        # Use IDs with special characters
        conn = broadcaster.register(
            surface_id="surface-with-dashes_and_underscores",
            session_id="session.with.dots",
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"test": "data"},
            target_surface_id="surface-with-dashes_and_underscores"
        )

        sent_count = await broadcaster.broadcast(event)
        assert sent_count == 1

        queued = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert queued.event_type == EventType.RESULT_CREATED

        broadcaster.unregister(conn.connection_id)
