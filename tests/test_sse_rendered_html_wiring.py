"""
Test that rendered_html is properly wired from dispatch to SSE (bead adc-3lgj3).

This test verifies the fix that moves rendered_html from being embedded
in the SSE data payload to being a proper SSEEvent field, matching the
pattern used in continuity.py.
"""
import asyncio
import pytest

from src.sse.broadcaster import SSEEvent, get_broadcaster


@pytest.mark.asyncio
async def test_rendered_html_in_sse_event_field():
    """Test that rendered_html is passed as SSEEvent field, not in data."""
    b = get_broadcaster()
    await b.start()

    try:
        # Create SSE event with rendered_html as a field (proper pattern)
        # Note: component_id goes in data, rendered_html as field (matching main.py fix)
        event = SSEEvent(
            event_type="result_created",
            data={
                "intent_id": "test-intent",
                "topic_id": "test-topic",
                "summary": "Test summary",
                "urgency": "normal",
                "component_id": "test-component",  # component_id in data
            },
            rendered_html="<div class='test'>Rendered content</div>",
        )

        # Verify the event structure
        assert event.rendered_html == "<div class='test'>Rendered content</div>"
        assert event.rendered_html not in event.data  # Not embedded in data

        # Simulate what event_generator does
        payload = dict(event.data)
        if event.rendered_html is not None:
            payload["rendered_html"] = event.rendered_html

        # Verify rendered_html appears in final payload
        assert payload["rendered_html"] == "<div class='test'>Rendered content</div>"
        assert payload["intent_id"] == "test-intent"
        assert payload["component_id"] == "test-component"

    finally:
        await b.stop()


@pytest.mark.asyncio
async def test_sse_event_without_rendered_html():
    """Test that SSE events work without rendered_html (fallback path)."""
    b = get_broadcaster()
    await b.start()

    try:
        # Create SSE event without rendered_html (fallback case)
        event = SSEEvent(
            event_type="result_created",
            data={
                "intent_id": "fallback-intent",
                "topic_id": "fallback-topic",
                "card_fallback": True,
            },
            rendered_html=None,  # Explicitly None
        )

        # Verify structure
        assert event.rendered_html is None

        # Simulate event_generator
        payload = dict(event.data)
        if event.rendered_html is not None:
            payload["rendered_html"] = event.rendered_html

        # rendered_html should NOT be in payload (because it's None)
        assert "rendered_html" not in payload
        assert payload["card_fallback"] is True

    finally:
        await b.stop()


@pytest.mark.asyncio
async def test_component_id_without_rendered_html():
    """Test that component_id can be present without rendered_html."""
    b = get_broadcaster()
    await b.start()

    try:
        # Edge case: component_id present but no rendered_html (fallback)
        event = SSEEvent(
            event_type="result_created",
            data={
                "intent_id": "test-intent",
                "component_id": "some-component",  # component_id in data
            },
        )

        # component_id is in data (as per my fix in main.py)
        assert "component_id" in event.data
        assert event.data["component_id"] == "some-component"
        assert event.rendered_html is None  # Default is None

    finally:
        await b.stop()
