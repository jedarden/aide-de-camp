"""
Basic SSE broadcast functionality test (bead adc-15qni).

This test verifies the fundamental SSE broadcast mechanism:
- Creating and broadcasting a simple SSEEvent
- Receiving the event on a registered connection
- Verifying event data integrity

This is the simplest possible broadcast test and serves as the foundation
for more complex SSE testing.
"""
import pytest
from uuid import uuid4

from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEEvent,
    get_broadcaster,
)
from tests.test_sse_broadcaster import (
    create_test_event,
    broadcast_and_collect,
)


class TestBasicSSEBroadcast:
    """Test basic SSE broadcast functionality."""

    async def test_broadcast_simple_event(self, broadcaster):
        """Test broadcasting a simple event is received by a registered connection.

        This is the fundamental broadcast test: create an event, broadcast it,
        and verify it arrives intact at the registered connection.
        """
        # Arrange: Register a test connection
        session_id = str(uuid4())
        surface_id = str(uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        # Create a simple test event
        test_event = create_test_event(
            event_type="test_broadcast",
            data={"message": "hello", "count": 42}
        )

        # Act: Broadcast and collect
        received_type, received_data = await broadcast_and_collect(
            broadcaster,
            test_event,
            connection
        )

        # Assert: Event was received with correct type and data
        assert received_type == "test_broadcast"
        assert received_data["message"] == "hello"
        assert received_data["count"] == 42

    async def test_broadcast_with_sseevent_and_get_broadcaster(self):
        """Test broadcast using SSEEvent and get_broadcaster() directly.

        This test uses the public API exactly as application code would:
        - Create an SSEEvent instance
        - Use get_broadcaster() singleton
        - Register a connection
        - Broadcast and verify
        """
        # Arrange: Use the global broadcaster via get_broadcaster()
        broadcaster = get_broadcaster()

        session_id = str(uuid4())
        surface_id = str(uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        # Create an SSEEvent directly (not using helper)
        event = SSEEvent(
            event_type="custom_event",
            data={"custom": "data", "id": str(uuid4())}
        )

        # Act: Broadcast
        sent_count = await broadcaster.broadcast(event)

        # Collect the event from the connection
        received_type, received_data = await broadcast_and_collect(
            broadcaster,
            event,
            connection
        )

        # Assert: Event was sent and received correctly
        assert sent_count == 1  # Sent to exactly one connection
        assert received_type == "custom_event"
        assert received_data["custom"] == "data"
        assert "id" in received_data

    async def test_broadcast_to_multiple_connections(self, broadcaster):
        """Test that broadcasting reaches all registered connections.

        Verifies the broadcast mechanism sends to multiple connections
        in the same session.
        """
        # Arrange: Register multiple connections for same session
        session_id = str(uuid4())
        surface_1 = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=session_id,
            surface_type="canvas"
        )
        surface_2 = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=session_id,
            surface_type="canvas"
        )

        event = create_test_event(event_type="multi_cast")

        # Act: Broadcast
        sent_count = await broadcaster.broadcast(event)

        # Assert: Event sent to both connections
        assert sent_count == 2

    async def test_event_data_integrity_through_broadcast(self, broadcaster):
        """Test that complex event data survives broadcast unchanged.

        Verifies data structures, nested objects, and special values
        pass through the broadcast pipeline correctly.
        """
        # Arrange
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        complex_data = {
            "string": "test",
            "number": 123,
            "float": 45.67,
            "bool": True,
            "null": None,
            "array": [1, 2, 3],
            "nested": {"key": "value", "nested_again": {"deep": "data"}},
            "uuid": str(uuid4()),
        }

        event = SSEEvent(event_type="complex_test", data=complex_data)

        # Act
        received_type, received_data = await broadcast_and_collect(
            broadcaster,
            event,
            connection
        )

        # Assert: All data preserved
        assert received_type == "complex_test"
        assert received_data == complex_data
        assert received_data["nested"]["nested_again"]["deep"] == "data"

    async def test_broadcast_with_target_session_filter(self, broadcaster):
        """Test that target_session_id filters correctly.

        Events should only reach connections matching the target session.
        """
        # Arrange: Create two sessions
        session_a = str(uuid4())
        session_b = str(uuid4())

        conn_a = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=session_a,
            surface_type="canvas"
        )
        broadcaster.register(
            surface_id=str(uuid4()),
            session_id=session_b,
            surface_type="canvas"
        )

        # Event targeting only session_a
        event = SSEEvent(
            event_type="filtered",
            data={"msg": "only for A"},
            target_session_id=session_a
        )

        # Act
        sent_count = await broadcaster.broadcast(event)

        # Assert: Only sent to session_a's connection
        assert sent_count == 1


# Test execution verification
if __name__ == "__main__":
    print("Basic SSE Broadcast Test")
    print("=" * 50)
    print("✓ Test class: TestBasicSSEBroadcast")
    print("✓ Tests cover:")
    print("  - Simple event broadcast and reception")
    print("  - Direct SSEEvent + get_broadcaster() usage")
    print("  - Multi-connection broadcast")
    print("  - Complex data integrity")
    print("  - Target session filtering")
    print("=" * 50)
    print("Run with: pytest tests/test_sse_broadcast_basic.py -v")
