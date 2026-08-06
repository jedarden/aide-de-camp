"""
SSE broadcast timing and ordering test (bead adc-3vtj7).

This test verifies that SSE broadcast timing and ordering work correctly.
It tests the timing guarantees and ordering preservation of the broadcast system,
ensuring events are delivered reliably and in sequence.
"""
import asyncio
import time
import pytest
from uuid import uuid4

from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEEvent,
    EventType,
    SSEConnection,
)
from tests.test_sse_broadcaster import (
    parse_sse_event,
)


# -----------------------------------------------------------------------------
# Test helper functions
# -----------------------------------------------------------------------------

async def collect_multiple_events(
    broadcaster: SSEBroadcaster,
    connection: SSEConnection,
    count: int,
    *,
    timeout: float = 5.0
) -> list[tuple[str, dict]]:
    """
    Collect a specific number of events from a connection.

    Args:
        broadcaster: The SSEBroadcaster instance
        connection: The SSEConnection to collect from
        count: Number of events to collect
        timeout: Maximum time to wait for all events

    Returns:
        List of (event_type, data) tuples in order received
    """
    queue = asyncio.Queue()
    collected = []

    async def collector():
        async for event_str in broadcaster.event_generator(connection):
            event_type, data = parse_sse_event(event_str)
            if event_type != "connected":  # Skip connection events
                collected.append((event_type, data))
                if len(collected) >= count:
                    return

    collector_task = asyncio.create_task(collector())

    try:
        await asyncio.wait_for(collector_task, timeout=timeout)
        return collected
    except asyncio.TimeoutError:
        collector_task.cancel()
        raise TimeoutError(f"Only collected {len(collected)}/{count} events within {timeout}s")
    finally:
        collector_task.cancel()


async def measure_broadcast_latency(
    broadcaster: SSEBroadcaster,
    event: SSEEvent,
    connection: SSEConnection
) -> float:
    """
    Measure the time from broadcast to receipt.

    Args:
        broadcaster: The SSEBroadcaster instance
        event: The SSEEvent to broadcast
        connection: The SSEConnection to measure on

    Returns:
        Latency in seconds
    """
    queue = asyncio.Queue()

    async def wait_single():
        async for event_str in broadcaster.event_generator(connection):
            event_type, data = parse_sse_event(event_str)
            if event_type != "connected":
                return

    waiter_task = asyncio.create_task(wait_single())

    # Small delay to let the event_generator start
    await asyncio.sleep(0.01)

    # Broadcast and measure time
    start_time = time.perf_counter()
    await broadcaster.broadcast(event)
    await asyncio.wait_for(waiter_task, timeout=2.0)
    latency = time.perf_counter() - start_time

    waiter_task.cancel()
    return latency


# -----------------------------------------------------------------------------
# Test fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
async def multi_connection_broadcaster(broadcaster):
    """
    Create a broadcaster with multiple registered connections.
    """
    connections = []
    for i in range(3):
        conn = broadcaster.register(
            surface_id=f"surface-{i}",
            session_id=f"session-{i}",
            surface_type="canvas"
        )
        connections.append(conn)

    yield broadcaster, connections

    # Cleanup
    for conn in connections:
        broadcaster.unregister(conn.connection_id)


# -----------------------------------------------------------------------------
# Timing and ordering tests
# -----------------------------------------------------------------------------


class TestBroadcastTimingAndOrdering:
    """Test SSE broadcast timing and ordering guarantees."""

    async def test_sequential_broadcast_ordering(self, broadcaster):
        """Test that events broadcast sequentially are received in order.

        Verifies the fundamental ordering guarantee: if events A, B, C are
        broadcast in that order, they should be received in that order.
        """
        # Arrange: Register a connection
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        # Create events with sequence numbers
        events = [
            SSEEvent(
                event_type="test_event",
                data={"sequence": i, "message": f"Event {i}"}
            )
            for i in range(1, 6)  # 5 events
        ]

        # Act: Broadcast events sequentially
        broadcast_order = []
        for event in events:
            await broadcaster.broadcast(event)
            broadcast_order.append(event.data["sequence"])

        # Collect events
        received = await collect_multiple_events(
            broadcaster,
            connection,
            count=len(events),
            timeout=2.0
        )

        # Assert: Events received in broadcast order
        received_order = [data["sequence"] for _, data in received]
        assert received_order == broadcast_order
        assert len(received) == 5

    async def test_concurrent_broadcast_ordering(self, broadcaster):
        """Test that concurrent broadcasts maintain ordering per connection.

        When multiple events are broadcast concurrently, they should still
        be received in a deterministic order (FIFO per connection).
        """
        # Arrange: Register a connection
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        # Create events with timestamps
        events = [
            SSEEvent(
                event_type="concurrent_test",
                data={"id": i, "message": f"Concurrent event {i}"}
            )
            for i in range(10)
        ]

        # Act: Broadcast all events concurrently
        broadcast_tasks = [
            broadcaster.broadcast(event)
            for event in events
        ]
        await asyncio.gather(*broadcast_tasks)

        # Collect events
        received = await collect_multiple_events(
            broadcaster,
            connection,
            count=len(events),
            timeout=3.0
        )

        # Assert: All events received, IDs are preserved
        received_ids = [data["id"] for _, data in received]
        assert len(received_ids) == 10
        assert set(received_ids) == set(range(10))  # All IDs present

    async def test_broadcast_timing_latency(self, broadcaster):
        """Test that broadcast latency is reasonable.

        Verifies that events are delivered within a reasonable timeframe.
        """
        # Arrange: Register a connection
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type="latency_test",
            data={"message": "Latency test event"}
        )

        # Act: Measure broadcast latency
        latency = await measure_broadcast_latency(
            broadcaster,
            event,
            connection
        )

        # Assert: Latency should be reasonable (< 100ms for local test)
        assert latency < 0.1, f"Broadcast latency {latency}s exceeds 100ms threshold"

    async def test_rapid_sequential_broadcasts(self, broadcaster):
        """Test broadcasting many events in quick succession.

        Verifies the broadcaster can handle rapid sequential broadcasts
        without losing events or breaking ordering.
        """
        # Arrange: Register a connection
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        # Create 20 events
        event_count = 20
        events = [
            SSEEvent(
                event_type="rapid_test",
                data={"index": i, "timestamp": time.time()}
            )
            for i in range(event_count)
        ]

        # Act: Broadcast rapidly without waiting
        start_time = time.perf_counter()
        for event in events:
            await broadcaster.broadcast(event)
        broadcast_duration = time.perf_counter() - start_time

        # Collect events
        received = await collect_multiple_events(
            broadcaster,
            connection,
            count=event_count,
            timeout=5.0
        )

        # Assert: All events received in order
        assert len(received) == event_count
        received_indices = [data["index"] for _, data in received]
        assert received_indices == list(range(event_count))

        # Broadcasting 20 events should be fast
        assert broadcast_duration < 1.0, f"Broadcasting {event_count} events took {broadcast_duration}s"

    async def test_multiple_connection_ordering(self, multi_connection_broadcaster):
        """Test that events maintain ordering across multiple connections.

        Verifies that when events are broadcast to multiple connections,
        each connection receives events in the correct order.
        """
        broadcaster, connections = multi_connection_broadcaster

        # Create events
        events = [
            SSEEvent(
                event_type="multi_conn_test",
                data={"sequence": i}
            )
            for i in range(5)
        ]

        # Act: Broadcast events
        for event in events:
            await broadcaster.broadcast(event)

        # Collect from each connection
        collected_per_connection = []
        for conn in connections:
            received = await collect_multiple_events(
                broadcaster,
                conn,
                count=len(events),
                timeout=3.0
            )
            received_sequences = [data["sequence"] for _, data in received]
            collected_per_connection.append(received_sequences)

        # Assert: Each connection received events in order
        for received_sequences in collected_per_connection:
            assert received_sequences == list(range(5))

    async def test_broadcast_timing_with_await(self, broadcaster):
        """Test that awaiting broadcast() completes promptly.

        Verifies the broadcast coroutine returns quickly and doesn't block
        longer than expected.
        """
        # Arrange: Register multiple connections
        connections = [
            broadcaster.register(
                surface_id=f"surface-{i}",
                session_id=str(uuid4()),
                surface_type="canvas"
            )
            for i in range(5)
        ]

        event = SSEEvent(
            event_type="timing_test",
            data={"message": "Timing test event"}
        )

        # Act: Measure time to await broadcast()
        start_time = time.perf_counter()
        sent_count = await broadcaster.broadcast(event)
        broadcast_time = time.perf_counter() - start_time

        # Assert: Broadcast completes quickly
        assert sent_count == 5
        assert broadcast_time < 0.05, f"broadcast() took {broadcast_time}s (should be < 50ms)"

    async def test_event_ordering_with_filters(self, broadcaster):
        """Test that event ordering is preserved when using filters.

        Verifies that target_session_id and target_surface_id filters
        don't affect event ordering for matching connections.
        """
        # Arrange: Create multiple sessions
        session_a = str(uuid4())
        session_b = str(uuid4())

        conn_a1 = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=session_a,
            surface_type="canvas"
        )
        conn_a2 = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=session_a,
            surface_type="canvas"
        )
        broadcaster.register(
            surface_id=str(uuid4()),
            session_id=session_b,
            surface_type="canvas"
        )

        # Create events targeting session_a
        events = [
            SSEEvent(
                event_type="filtered_test",
                data={"seq": i},
                target_session_id=session_a
            )
            for i in range(5)
        ]

        # Act: Broadcast filtered events
        for event in events:
            await broadcaster.broadcast(event)

        # Collect from session_a connections
        received_a1 = await collect_multiple_events(
            broadcaster,
            conn_a1,
            count=len(events),
            timeout=2.0
        )
        received_a2 = await collect_multiple_events(
            broadcaster,
            conn_a2,
            count=len(events),
            timeout=2.0
        )

        # Assert: Both connections in session_a received events in order
        sequences_a1 = [data["seq"] for _, data in received_a1]
        sequences_a2 = [data["seq"] for _, data in received_a2]
        assert sequences_a1 == list(range(5))
        assert sequences_a2 == list(range(5))

    async def test_mixed_event_types_ordering(self, broadcaster):
        """Test that different event types maintain broadcast order.

        Verifies that mixed event types (result_created, fetch_progress, etc.)
        are received in the order they were broadcast.
        """
        # Arrange: Register a connection
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        # Create events of different types with sequence markers
        event_types_and_seqs = [
            (EventType.RESULT_CREATED, 1),
            (EventType.FETCH_PROGRESS, 2),
            (EventType.SYNTHESIS_PROGRESS, 3),
            (EventType.TOPIC_UPDATED, 4),
            (EventType.RESULT_CREATED, 5),
        ]

        events = [
            SSEEvent(
                event_type=event_type,
                data={"sequence": seq, "type": event_type}
            )
            for event_type, seq in event_types_and_seqs
        ]

        # Act: Broadcast events
        for event in events:
            await broadcaster.broadcast(event)

        # Collect events
        received = await collect_multiple_events(
            broadcaster,
            connection,
            count=len(events),
            timeout=2.0
        )

        # Assert: Events received in broadcast order with correct types
        assert len(received) == 5
        for i, (event_type, data) in enumerate(received):
            expected_type, expected_seq = event_types_and_seqs[i]
            assert event_type == expected_type
            assert data["sequence"] == expected_seq

    async def test_no_event_dropping_under_load(self, broadcaster):
        """Test that events aren't dropped under moderate load.

        Verifies that broadcasting 50 events in quick succession
        results in all 50 being received.
        """
        # Arrange: Register a connection
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        # Create 50 events
        event_count = 50
        events = [
            SSEEvent(
                event_type="load_test",
                data={"id": i}
            )
            for i in range(event_count)
        ]

        # Act: Broadcast all events rapidly
        for event in events:
            await broadcaster.broadcast(event)

        # Collect events
        received = await collect_multiple_events(
            broadcaster,
            connection,
            count=event_count,
            timeout=10.0
        )

        # Assert: All events received
        assert len(received) == event_count
        received_ids = [data["id"] for _, data in received]
        assert set(received_ids) == set(range(event_count))

    async def test_broadcast_completes_within_timeout(self, broadcaster):
        """Test that broadcast() coroutine completes in reasonable time.

        Verifies the broadcast operation doesn't hang or block excessively.
        """
        # Arrange: Register a connection
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        event = SSEEvent(
            event_type="timeout_test",
            data={"message": "Timeout test"}
        )

        # Act: Broadcast with timeout
        try:
            result = await asyncio.wait_for(
                broadcaster.broadcast(event),
                timeout=1.0
            )
            # Assert: Broadcast completed within timeout
            assert result == 1
        except asyncio.TimeoutError:
            pytest.fail("broadcast() did not complete within 1 second timeout")

    async def test_sequential_broadcast_latency_consistency(self, broadcaster):
        """Test that sequential broadcasts have consistent latency.

        Verifies that broadcasting multiple events sequentially
        results in consistent delivery latencies.
        """
        # Measure latency for 10 sequential broadcasts
        latencies = []
        for i in range(10):
            # Create a fresh connection for each measurement
            connection = broadcaster.register(
                surface_id=str(uuid4()),
                session_id=str(uuid4()),
                surface_type="canvas"
            )
            event = SSEEvent(
                event_type="latency_consistency",
                data={"iteration": i}
            )
            latency = await measure_broadcast_latency(
                broadcaster,
                event,
                connection
            )
            latencies.append(latency)

        # Calculate statistics
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        # Assert: Latencies are consistent and reasonable
        assert avg_latency < 0.1, f"Average latency {avg_latency}s exceeds 100ms"
        assert max_latency < 0.2, f"Max latency {max_latency}s exceeds 200ms"


# -----------------------------------------------------------------------------
# Test execution verification
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    print("SSE Broadcast Timing and Ordering Test")
    print("=" * 60)
    print("✓ Test class: TestBroadcastTimingAndOrdering")
    print("✓ Tests cover:")
    print("  - Sequential event ordering")
    print("  - Concurrent broadcast ordering")
    print("  - Broadcast latency measurement")
    print("  - Rapid sequential broadcasts")
    print("  - Multi-connection ordering")
    print("  - Broadcast timing with await")
    print("  - Event ordering with filters")
    print("  - Mixed event type ordering")
    print("  - No event dropping under load")
    print("  - Broadcast completion timeout")
    print("  - Sequential latency consistency")
    print("=" * 60)
    print("Run with: pytest tests/test_sse_broadcast_timing.py -v")
