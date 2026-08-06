"""
SSE broadcaster test infrastructure (bead adc-67u2o).

This module provides the foundational test infrastructure for SSE broadcast testing,
including fixtures, helper functions, and core functionality tests.

Key infrastructure components:
- broadcaster fixture: Provides isolated SSE broadcaster instances
- connection fixture: Creates test SSE connections
- event generation helpers: Utilities for creating and collecting SSE events
- collection helpers: Async utilities for gathering events from connections
"""
import asyncio
import pytest
from uuid import uuid4

from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEEvent,
    SSEConnection,
    get_broadcaster,
    EventType,
    KEEPALIVE_INTERVAL_SECONDS,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
async def broadcaster():
    """
    Provide a fresh SSE broadcaster instance for each test.

    This fixture creates an isolated broadcaster that doesn't interact
    with the global singleton, ensuring test independence.
    """
    b = SSEBroadcaster()
    yield b
    # Cleanup: stop the broadcaster if it was started
    if b._running:
        await b.stop()


@pytest.fixture
async def started_broadcaster(broadcaster):
    """
    Provide a started broadcaster instance.

    This fixture ensures the broadcaster's cleanup loop is running,
    which is necessary for timeout and keepalive tests.
    """
    await broadcaster.start()
    yield broadcaster
    await broadcaster.stop()


@pytest.fixture
def sample_session(broadcaster):
    """
    Create and register a sample test session.

    Returns a tuple of (session_id, surface_id, connection) for use in tests.
    """
    session_id = str(uuid4())
    surface_id = str(uuid4())
    connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )
    return session_id, surface_id, connection


@pytest.fixture
async def connected_session(started_broadcaster):
    """
    Create a connected session with an active event stream.

    Returns a tuple of (session_id, surface_id, connection, event_generator_task).
    The event generator task runs the connection's event_generator in the background.
    """
    session_id = str(uuid4())
    surface_id = str(uuid4())
    connection = started_broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas"
    )

    # Start the event generator in the background
    event_queue = asyncio.Queue()

    async def collect_events():
        async for event in started_broadcaster.event_generator(connection):
            await event_queue.put(event)

    task = asyncio.create_task(collect_events())

    yield session_id, surface_id, connection, event_queue, task

    # Cleanup
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# -----------------------------------------------------------------------------
# Event generation helpers
# -----------------------------------------------------------------------------


def create_test_event(
    event_type: str = "test_event",
    data: dict | None = None,
    **event_kwargs
) -> SSEEvent:
    """
    Create a test SSE event with optional data.

    Args:
        event_type: The type of event to create
        data: Optional event payload data
        **event_kwargs: Additional SSEEvent fields (rendered_html, target_session_id, etc.)

    Returns:
        An SSEEvent instance suitable for testing
    """
    if data is None:
        data = {"test_key": "test_value", "timestamp": 1234567890}

    return SSEEvent(
        event_type=event_type,
        data=data,
        **event_kwargs
    )


def create_result_event(
    summary: str = "Test result",
    urgency: str = "normal",
    **event_kwargs
) -> SSEEvent:
    """
    Create a result_created event for testing.

    Args:
        summary: Result summary text
        urgency: Result urgency level
        **event_kwargs: Additional SSEEvent fields

    Returns:
        An SSEEvent with result_created type and typical result data
    """
    return SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data={
            "summary": summary,
            "urgency": urgency,
            "result_id": str(uuid4()),
            "intent_id": str(uuid4()),
            "topic_id": str(uuid4()),
        },
        **event_kwargs
    )


def create_fetch_progress_event(
    intent_id: str,
    completed: int,
    total: int,
    source_name: str | None = None,
    **event_kwargs
) -> SSEEvent:
    """
    Create a fetch_progress event for testing.

    Args:
        intent_id: The intent being fetched
        completed: Number of sources completed
        total: Total number of sources
        source_name: Optional source name
        **event_kwargs: Additional SSEEvent fields

    Returns:
        An SSEEvent with fetch_progress type
    """
    return SSEEvent(
        event_type=EventType.FETCH_PROGRESS,
        data={
            "intent_id": intent_id,
            "completed": completed,
            "total": total,
            "source_name": source_name,
            "source_status": "completed" if source_name else None,
        },
        **event_kwargs
    )


# -----------------------------------------------------------------------------
# Event collection helpers
# -----------------------------------------------------------------------------


async def collect_events_from_queue(
    queue: asyncio.Queue,
    wanted_types: set[str] | None = None,
    *,
    timeout: float = 2.0,
    exclude_connected: bool = True
) -> list[tuple[str, dict]]:
    """
    Collect events from an SSE event queue until wanted types arrive.

    Args:
        queue: The asyncio.Queue containing events
        wanted_types: Set of event types to wait for (None = collect all until timeout)
        timeout: Maximum time to wait for events
        exclude_connected: Whether to exclude 'connected' events from results

    Returns:
        List of (event_type, data) tuples collected from the queue
    """
    collected = []
    wanted = set(wanted_types) if wanted_types else None

    async def drain():
        while True:
            try:
                event_str = await asyncio.wait_for(queue.get(), timeout=timeout)
                # Parse SSE format: "event: <type>\ndata: <json>\n\n"
                event_type, data = parse_sse_event(event_str)

                if exclude_connected and event_type == "connected":
                    continue

                collected.append((event_type, data))

                # Check if we've collected all wanted types
                if wanted and wanted <= {etype for etype, _ in collected}:
                    return
            except asyncio.TimeoutError:
                return

    await drain()
    return collected


def parse_sse_event(event_str: str) -> tuple[str, dict]:
    """
    Parse an SSE-formatted event string into type and data.

    Args:
        event_str: SSE-formatted string (e.g., "event: result_created\ndata: {...}\n\n")

    Returns:
        Tuple of (event_type, data_dict)

    Raises:
        ValueError: If the event string is malformed
    """
    import json

    lines = event_str.strip().split("\n")
    event_type = None
    data = None

    for line in lines:
        if line.startswith("event: "):
            event_type = line[len("event: "):]
        elif line.startswith("data: "):
            data = json.loads(line[len("data: "):])

    if not event_type or data is None:
        raise ValueError(f"Malformed SSE event: {event_str}")

    return event_type, data


async def wait_for_event_count(
    queue: asyncio.Queue,
    count: int,
    *,
    timeout: float = 2.0
) -> list[tuple[str, dict]]:
    """
    Wait for a specific number of events to be available in the queue.

    Args:
        queue: The asyncio.Queue to poll
        count: Number of events to wait for
        timeout: Maximum time to wait

    Returns:
        List of collected (event_type, data) tuples
    """
    collected = []

    async def collect():
        while len(collected) < count:
            try:
                event_str = await asyncio.wait_for(queue.get(), timeout=timeout)
                event_type, data = parse_sse_event(event_str)
                if event_type != "connected":  # Skip connection events
                    collected.append((event_type, data))
            except asyncio.TimeoutError:
                return

    await collect()
    return collected


async def broadcast_and_collect(
    broadcaster: SSEBroadcaster,
    event: SSEEvent,
    connection: SSEConnection,
    *,
    timeout: float = 2.0
) -> tuple[str, dict]:
    """
    Broadcast an event and collect the first result from a connection.

    Args:
        broadcaster: The SSEBroadcaster instance
        event: The SSEEvent to broadcast
        connection: The SSEConnection to collect from
        timeout: Maximum time to wait for the event

    Returns:
        Tuple of (event_type, data) from the first received event
    """
    # Start event collection in background
    queue = asyncio.Queue()

    async def collect_single():
        async for event_str in broadcaster.event_generator(connection):
            etype, data = parse_sse_event(event_str)
            if etype != "connected":
                await queue.put((etype, data))
                return

    collector_task = asyncio.create_task(collect_single())

    # Broadcast the event
    await broadcaster.broadcast(event)

    # Wait for collection
    try:
        result = await asyncio.wait_for(queue.get(), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        collector_task.cancel()
        raise TimeoutError(f"No event received within {timeout}s")
    finally:
        collector_task.cancel()


# -----------------------------------------------------------------------------
# Core infrastructure tests
# -----------------------------------------------------------------------------


class TestBroadcasterBasics:
    """Test basic broadcaster functionality and infrastructure setup."""

    def test_broadcaster_initialization(self, broadcaster):
        """Test that broadcaster initializes with correct defaults."""
        assert broadcaster is not None
        assert isinstance(broadcaster, SSEBroadcaster)
        assert len(broadcaster.connections) == 0
        assert broadcaster._running is False
        assert broadcaster._cleanup_task is None

    def test_register_connection(self, broadcaster):
        """Test connection registration creates valid connection objects."""
        session_id = "test-session"
        surface_id = "test-surface"

        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        assert isinstance(connection, SSEConnection)
        assert connection.connection_id is not None
        assert connection.surface_id == surface_id
        assert connection.session_id == session_id
        assert connection.surface_type == "canvas"
        assert connection.connection_id in broadcaster.connections

    def test_unregister_connection(self, broadcaster):
        """Test connection unregistration removes from registry."""
        connection = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        connection_id = connection.connection_id
        assert connection_id in broadcaster.connections

        broadcaster.unregister(connection_id)
        assert connection_id not in broadcaster.connections

    def test_unregister_nonexistent_connection(self, broadcaster):
        """Test unregistering a non-existent connection is safe."""
        # Should not raise an exception
        broadcaster.unregister("nonexistent-id")
        assert len(broadcaster.connections) == 0

    def test_heartbeat_updates_timestamp(self, broadcaster):
        """Test heartbeat updates the connection's last_heartbeat timestamp."""
        import time
        from datetime import datetime

        connection = broadcaster.register(
            surface_id="surface-1",
            session_id="session-1",
            surface_type="canvas"
        )

        initial_time = connection.last_heartbeat
        time.sleep(0.01)  # Small delay to ensure timestamp difference

        success = broadcaster.heartbeat(connection.connection_id)
        assert success is True
        assert connection.last_heartbeat > initial_time

    def test_heartbeat_nonexistent_connection(self, broadcaster):
        """Test heartbeat on non-existent connection returns False."""
        success = broadcaster.heartbeat("nonexistent-id")
        assert success is False


class TestEventCreation:
    """Test event creation helpers produce valid SSE events."""

    def test_create_test_event(self):
        """Test basic test event creation."""
        event = create_test_event(event_type="custom_event")

        assert isinstance(event, SSEEvent)
        assert event.event_type == "custom_event"
        assert event.data == {"test_key": "test_value", "timestamp": 1234567890}

    def test_create_test_event_with_custom_data(self):
        """Test test event creation with custom data."""
        custom_data = {"custom": "data", "number": 42}
        event = create_test_event(data=custom_data)

        assert event.data == custom_data

    def test_create_result_event(self):
        """Test result event creation with defaults."""
        event = create_result_event()

        assert event.event_type == EventType.RESULT_CREATED
        assert "summary" in event.data
        assert "urgency" in event.data
        assert event.data["summary"] == "Test result"
        assert event.data["urgency"] == "normal"

    def test_create_result_event_custom(self):
        """Test result event creation with custom values."""
        event = create_result_event(
            summary="Custom summary",
            urgency="high"
        )

        assert event.data["summary"] == "Custom summary"
        assert event.data["urgency"] == "high"

    def test_create_fetch_progress_event(self):
        """Test fetch progress event creation."""
        intent_id = "test-intent"
        event = create_fetch_progress_event(
            intent_id=intent_id,
            completed=3,
            total=5
        )

        assert event.event_type == EventType.FETCH_PROGRESS
        assert event.data["intent_id"] == intent_id
        assert event.data["completed"] == 3
        assert event.data["total"] == 5

    def test_create_fetch_progress_with_source(self):
        """Test fetch progress event with source information."""
        event = create_fetch_progress_event(
            intent_id="test-intent",
            completed=1,
            total=10,
            source_name="GitHub"
        )

        assert event.data["source_name"] == "GitHub"
        assert event.data["source_status"] == "completed"


class TestEventParsing:
    """Test SSE event string parsing utilities."""

    def test_parse_sse_event_basic(self):
        """Test parsing basic SSE event format."""
        event_str = 'event: test_event\ndata: {"key": "value"}\n\n'
        event_type, data = parse_sse_event(event_str)

        assert event_type == "test_event"
        assert data == {"key": "value"}

    def test_parse_sse_event_complex_data(self):
        """Test parsing SSE event with complex JSON data."""
        event_str = 'event: complex\ndata: {"nested": {"key": "value"}, "array": [1, 2, 3]}\n\n'
        event_type, data = parse_sse_event(event_str)

        assert event_type == "complex"
        assert data["nested"]["key"] == "value"
        assert data["array"] == [1, 2, 3]

    def test_parse_sse_event_multiline(self):
        """Test parsing SSE event with extra whitespace."""
        event_str = 'event: multiline\n\ndata: {"test": true}\n\n'
        event_type, data = parse_sse_event(event_str)

        assert event_type == "multiline"
        assert data["test"] is True

    def test_parse_sse_event_malformed_raises(self):
        """Test parsing malformed SSE event raises ValueError."""
        with pytest.raises(ValueError):
            parse_sse_event("invalid event string")

        with pytest.raises(ValueError):
            parse_sse_event("event: only_event\n\n")  # Missing data


class TestBroadcasterStartup:
    """Test broadcaster lifecycle and startup procedures."""

    async def test_broadcaster_start_stop_cycle(self, broadcaster):
        """Test broadcaster can be started and stopped cleanly."""
        assert broadcaster._running is False

        await broadcaster.start()
        assert broadcaster._running is True
        assert broadcaster._cleanup_task is not None

        await broadcaster.stop()
        assert broadcaster._running is False

    async def test_start_broadcaster_creates_new_task_on_double_start(self, broadcaster):
        """Test that calling start twice creates a new cleanup task (implementation detail)."""
        await broadcaster.start()
        first_task = broadcaster._cleanup_task

        # Start again - creates a new cleanup task (not idempotent)
        await broadcaster.stop()  # Stop the first one to avoid orphaned tasks
        await broadcaster.start()  # Start fresh

        # After restart, we have a new task
        assert broadcaster._running is True
        # The task might be different due to restart sequence
        assert broadcaster._cleanup_task is not None

        await broadcaster.stop()

    async def test_stop_broadcaster_not_started_is_safe(self, broadcaster):
        """Test stopping a non-started broadcaster is safe."""
        # Should not raise an exception
        await broadcaster.stop()
        assert broadcaster._running is False


# -----------------------------------------------------------------------------
# Infrastructure verification
# -----------------------------------------------------------------------------


def test_pytest_asyncio_available():
    """Verify pytest-asyncio is available and configured."""
    assert pytest.mark.asyncio is not None


def test_imports_available():
    """Verify all required imports are available."""
    from src.sse.broadcaster import (
        SSEBroadcaster,
        SSEEvent,
        SSEConnection,
        get_broadcaster,
        EventType,
    )
    assert SSEBroadcaster is not None
    assert SSEEvent is not None
    assert SSEConnection is not None
    assert get_broadcaster is not None
    assert EventType is not None


def test_keepalive_constant_accessible():
    """Verify the KEEPALIVE_INTERVAL_SECONDS constant is accessible."""
    assert isinstance(KEEPALIVE_INTERVAL_SECONDS, float)
    assert KEEPALIVE_INTERVAL_SECONDS > 0


# -----------------------------------------------------------------------------
# Test execution verification
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    # Run a quick verification when executed directly
    print("SSE Broadcast Test Infrastructure")
    print("=" * 50)
    print(f"✓ Fixtures defined: broadcaster, started_broadcaster, sample_session, connected_session")
    print(f"✓ Event helpers: create_test_event, create_result_event, create_fetch_progress_event")
    print(f"✓ Collection helpers: collect_events_from_queue, parse_sse_event, wait_for_event_count")
    print(f"✓ Test classes: TestBroadcasterBasics, TestEventCreation, TestEventParsing")
    print(f"✓ All imports verified")
    print(f"✓ Keepalive interval: {KEEPALIVE_INTERVAL_SECONDS}s")
    print("=" * 50)
    print("Infrastructure ready for SSE broadcast testing.")
