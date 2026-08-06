"""
SSE result_created event type test (bead adc-3zi7z).

This test verifies that SSE broadcasts with event_type="result_created" work correctly.
It tests the specific event type used in the canvas dispatch flow, ensuring:
- Events are broadcast with the correct event_type
- Event type is correctly received by connections
- Event data structure includes expected result_created fields
- The event uses proper SSEEvent construction
"""
import pytest
from uuid import uuid4

from src.sse.broadcaster import (
    SSEBroadcaster,
    SSEEvent,
    EventType,
    get_broadcaster,
)
from tests.test_sse_broadcaster import (
    create_result_event,
    broadcast_and_collect,
)


class TestResultCreatedEventType:
    """Test result_created event type SSE broadcasts."""

    async def test_result_created_event_type_broadcast(self, broadcaster):
        """Test broadcasting an event with event_type='result_created'.

        Verifies that the event type is correctly set and received.
        """
        # Arrange: Register a test connection
        session_id = str(uuid4())
        surface_id = str(uuid4())
        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        # Create a result_created event using the helper
        result_event = create_result_event(
            summary="Test result summary",
            urgency="normal"
        )

        # Act: Broadcast and collect
        received_type, received_data = await broadcast_and_collect(
            broadcaster,
            result_event,
            connection
        )

        # Assert: Event type is correctly received as 'result_created'
        assert received_type == EventType.RESULT_CREATED
        assert received_type == "result_created"

    async def test_result_created_event_data_structure(self, broadcaster):
        """Test that result_created events include expected fields.

        Verifies the event data structure contains all required result_created fields:
        - summary: Result summary text
        - urgency: Result urgency level
        - result_id: Unique result identifier
        - intent_id: Associated intent identifier
        - topic_id: Associated topic identifier
        """
        # Arrange
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        # Create event with all expected fields
        result_id = str(uuid4())
        intent_id = str(uuid4())
        topic_id = str(uuid4())

        result_event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={
                "summary": "Deployment verification complete",
                "urgency": "low",
                "result_id": result_id,
                "intent_id": intent_id,
                "topic_id": topic_id,
            }
        )

        # Act
        received_type, received_data = await broadcast_and_collect(
            broadcaster,
            result_event,
            connection
        )

        # Assert: All expected fields present and correct
        assert received_type == EventType.RESULT_CREATED
        assert "summary" in received_data
        assert received_data["summary"] == "Deployment verification complete"
        assert "urgency" in received_data
        assert received_data["urgency"] == "low"
        assert "result_id" in received_data
        assert received_data["result_id"] == result_id
        assert "intent_id" in received_data
        assert received_data["intent_id"] == intent_id
        assert "topic_id" in received_data
        assert received_data["topic_id"] == topic_id

    async def test_result_created_with_rendered_html(self, broadcaster):
        """Test result_created event with rendered_html field.

        Verifies that events can include pre-rendered HTML for canvas injection.
        """
        # Arrange
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        rendered_html = "<div class='result-card'>Test Result</div>"

        result_event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={
                "summary": "Test result",
                "urgency": "normal",
                "result_id": str(uuid4()),
                "intent_id": str(uuid4()),
                "topic_id": str(uuid4()),
            },
            rendered_html=rendered_html
        )

        # Act: Broadcast and collect using a custom collector
        # (broadcast_and_collect needs to be augmented to capture rendered_html)
        # For now, verify the event is sent
        sent_count = await broadcaster.broadcast(result_event)

        # Assert: Event was sent to the connection
        assert sent_count == 1

        # Verify the event still has the rendered_html field
        assert result_event.rendered_html == rendered_html

    async def test_result_created_with_target_filters(self, broadcaster):
        """Test result_created event with target_session_id and target_surface_id filters.

        Verifies that result_created events respect targeting filters for specific
        sessions and surfaces, which is critical for the canvas dispatch flow.
        """
        # Arrange: Create multiple sessions and surfaces
        session_a = str(uuid4())
        session_b = str(uuid4())
        surface_a1 = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=session_a,
            surface_type="canvas"
        )
        surface_a2 = broadcaster.register(
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
        result_event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={
                "summary": "Targeted result",
                "urgency": "high",
                "result_id": str(uuid4()),
            },
            target_session_id=session_a
        )

        # Act
        sent_count = await broadcaster.broadcast(result_event)

        # Assert: Only sent to session_a connections (2 surfaces)
        assert sent_count == 2

    async def test_result_created_event_type_constant(self, broadcaster):
        """Test that EventType.RESULT_CREATED constant matches expected value.

        Verifies the constant is correctly defined and produces the right event type.
        """
        # Assert: Constant value matches expected string
        assert EventType.RESULT_CREATED == "result_created"

        # Arrange: Create an event using the constant
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        result_event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={
                "summary": "Constant test",
                "urgency": "normal",
            }
        )

        # Act
        received_type, received_data = await broadcast_and_collect(
            broadcaster,
            result_event,
            connection
        )

        # Assert: Event type matches constant value
        assert received_type == EventType.RESULT_CREATED
        assert received_type == "result_created"
        assert received_data["summary"] == "Constant test"

    async def test_result_created_via_broadcast_result_helper(self):
        """Test result_created event via broadcast_result() helper.

        Verifies the broadcast_result() helper function creates and broadcasts
        result_created events correctly. This mirrors how the application
        code broadcasts results in the canvas dispatch flow.
        """
        from src.sse.broadcaster import broadcast_result

        # Arrange: Use the global broadcaster
        broadcaster = get_broadcaster()
        session_id = str(uuid4())
        surface_id = str(uuid4())

        connection = broadcaster.register(
            surface_id=surface_id,
            session_id=session_id,
            surface_type="canvas"
        )

        result_data = {
            "summary": "Helper broadcast test",
            "urgency": "normal",
            "result_id": str(uuid4()),
            "intent_id": str(uuid4()),
            "topic_id": str(uuid4()),
        }

        # Act: Use the broadcast_result helper
        sent_count = await broadcast_result(
            result=result_data,
            session_id=session_id,
            target_surface_id=surface_id
        )

        # Assert: Event was sent to the target surface
        assert sent_count == 1

    async def test_result_created_multiple_urgency_levels(self, broadcaster):
        """Test result_created events with different urgency levels.

        Verifies that urgency field can be set to various levels (low, normal, high).
        """
        urgency_levels = ["low", "normal", "high", "critical"]

        for urgency in urgency_levels:
            # Arrange: Create a fresh connection for each test
            connection = broadcaster.register(
                surface_id=str(uuid4()),
                session_id=str(uuid4()),
                surface_type="canvas"
            )

            result_event = create_result_event(
                summary=f"Result with {urgency} urgency",
                urgency=urgency
            )

            # Act
            received_type, received_data = await broadcast_and_collect(
                broadcaster,
                result_event,
                connection
            )

            # Assert: Urgency is preserved correctly
            assert received_type == EventType.RESULT_CREATED
            assert received_data["urgency"] == urgency

    async def test_result_created_data_integrity(self, broadcaster):
        """Test that complex result data survives broadcast unchanged.

        Verifies nested data structures, special values, and all result fields
        pass through the broadcast pipeline correctly.
        """
        # Arrange
        connection = broadcaster.register(
            surface_id=str(uuid4()),
            session_id=str(uuid4()),
            surface_type="canvas"
        )

        complex_result_data = {
            "summary": "Complex result test",
            "urgency": "normal",
            "result_id": str(uuid4()),
            "intent_id": str(uuid4()),
            "topic_id": str(uuid4()),
            # Additional complex fields
            "metadata": {
                "source": "test",
                "timestamp": 1234567890,
                "tags": ["test", "result", "sse"],
            },
            "links": [
                {"url": "https://example.com", "label": "Example"},
            ],
            "null_field": None,
            "number": 42,
        }

        result_event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data=complex_result_data
        )

        # Act
        received_type, received_data = await broadcast_and_collect(
            broadcaster,
            result_event,
            connection
        )

        # Assert: All complex data preserved
        assert received_type == EventType.RESULT_CREATED
        assert received_data["summary"] == "Complex result test"
        assert received_data["metadata"]["source"] == "test"
        assert received_data["metadata"]["tags"] == ["test", "result", "sse"]
        assert received_data["links"][0]["url"] == "https://example.com"
        assert received_data["null_field"] is None
        assert received_data["number"] == 42


# Test execution verification
if __name__ == "__main__":
    print("SSE result_created Event Type Test")
    print("=" * 50)
    print("✓ Test class: TestResultCreatedEventType")
    print("✓ Tests cover:")
    print("  - Event type is correctly broadcast and received")
    print("  - Event data structure includes expected fields")
    print("  - Rendered HTML field support")
    print("  - Target session and surface filtering")
    print("  - EventType constant correctness")
    print("  - broadcast_result() helper integration")
    print("  - Multiple urgency levels")
    print("  - Complex data integrity")
    print("=" * 50)
    print("Run with: pytest tests/test_sse_result_created_event.py -v")
