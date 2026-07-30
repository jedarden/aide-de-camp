"""
Test the new rendered_html field on SSE events.

Verifies that the SSEEvent structure includes rendered_html and that it
is properly included in the SSE payload when present.
"""
import pytest
import asyncio
from src.sse.broadcaster import SSEEvent, SSEBroadcaster, EventType


class TestSSEEventRenderedHtml:
    """Test the rendered_html field on SSEEvent."""

    def test_sse_event_defaults_rendered_html_to_none(self):
        """SSEEvent should default rendered_html to None."""
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"test": "data"}
        )
        assert event.rendered_html is None
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data == {"test": "data"}

    def test_sse_event_accepts_rendered_html(self):
        """SSEEvent should accept rendered_html as an optional field."""
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"test": "data"},
            rendered_html="<div>Test HTML</div>"
        )
        assert event.rendered_html == "<div>Test HTML</div>"
        assert event.event_type == EventType.RESULT_CREATED
        assert event.data == {"test": "data"}

    def test_sse_event_with_all_fields(self):
        """SSEEvent should accept all fields including rendered_html."""
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"result": "value"},
            rendered_html="<div class='card'>Result</div>",
            target_session_id="session-123",
            target_surface_id="surface-456",
            exclude_surface_id="surface-789"
        )
        assert event.rendered_html == "<div class='card'>Result</div>"
        assert event.target_session_id == "session-123"
        assert event.target_surface_id == "surface-456"
        assert event.exclude_surface_id == "surface-789"


class TestSSEBroadcasterRenderedHtml:
    """Test that the broadcaster includes rendered_html in SSE output."""

    @pytest.mark.asyncio
    async def test_format_sse_includes_rendered_html_when_present(self):
        """The _format_sse output should include rendered_html when present."""
        broadcaster = SSEBroadcaster()

        # Create an event with rendered_html
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"result": "value"},
            rendered_html="<div>Rendered card</div>"
        )

        # Get the formatted SSE output
        formatted = broadcaster._format_sse(event.event_type, {
            **event.data,
            "rendered_html": event.rendered_html
        })

        # Check that the formatted output includes rendered_html
        assert "event: result_created" in formatted
        assert '"result": "value"' in formatted
        assert '"rendered_html": "<div>Rendered card</div>"' in formatted

    @pytest.mark.asyncio
    async def test_format_sse_omits_rendered_html_when_none(self):
        """The _format_sse output should omit rendered_html when None."""
        broadcaster = SSEBroadcaster()

        # Create an event without rendered_html (default None)
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"result": "value"}
        )

        # Get the formatted SSE output (without rendered_html)
        formatted = broadcaster._format_sse(event.event_type, event.data)

        # Check that the formatted output does not include rendered_html
        assert "event: result_created" in formatted
        assert '"result": "value"' in formatted
        assert "rendered_html" not in formatted

    @pytest.mark.asyncio
    async def test_broadcast_delivers_rendered_html_to_queue(self):
        """Broadcasting an event with rendered_html should include it in the queue."""
        broadcaster = SSEBroadcaster()
        await broadcaster.start()

        # Register a test connection
        conn = broadcaster.register(
            surface_id="test-surface",
            session_id="test-session",
            surface_type="canvas"
        )

        # Create an event with rendered_html
        event = SSEEvent(
            event_type=EventType.RESULT_CREATED,
            data={"result": "value"},
            rendered_html="<div>Card HTML</div>",
            target_session_id="test-session"
        )

        # Broadcast the event
        sent = await broadcaster.broadcast(event)
        assert sent == 1

        # Verify the event was queued
        queued_event = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
        assert queued_event.event_type == EventType.RESULT_CREATED
        assert queued_event.data == {"result": "value"}
        assert queued_event.rendered_html == "<div>Card HTML</div>"

        await broadcaster.stop()
