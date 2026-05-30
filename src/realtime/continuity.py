"""
Audio-to-Canvas Session Continuity

Handles surface switch events from audio to canvas.
Ensures pending results are rendered to canvas on switch.
"""
import asyncio
import logging
from typing import Any

from ..sse.broadcaster import get_broadcaster, SSEEvent, EventType


logger = logging.getLogger(__name__)


async def handle_surface_switch(
    surface_type: str,
    session_id: str,
    voice_session: Any,
) -> dict:
    """
    Handle surface switch event.

    When user switches from audio to canvas:
    1. Get pending results from voice session
    2. Return them for canvas rendering
    3. Voice model acknowledges the switch

    Returns:
    {
        "pending_results": list[dict],
        "catch_up_summary": str
    }
    """
    logger.info(f"Surface switch to {surface_type} for session {session_id}")

    # Get pending results from voice session
    pending = await voice_session.get_pending_results()

    # Build catch-up summary
    result_count = len(pending)
    if result_count == 0:
        catch_up_summary = "All caught up — nothing new on the canvas."
    elif result_count == 1:
        catch_up_summary = "I've got one result waiting — I'll put it on your canvas."
    else:
        catch_up_summary = f"I've got {result_count} results waiting — I'll put them on your canvas."

    logger.info(f"Surface switch: {result_count} pending results")

    return {
        "pending_results": pending,
        "catch_up_summary": catch_up_summary,
    }


async def push_to_canvas(
    session_id: str,
    result: dict,
    exclude_audio_surface_id: str | None = None,
) -> None:
    """
    Push a result to the canvas via SSE.

    This is called when a result arrives while the user is on canvas.
    The result is broadcast to all canvas surfaces for the session.
    """
    broadcaster = get_broadcaster()

    # Create SSE event for the result
    event = SSEEvent(
        event_type=EventType.RESULT_CREATED,
        data=result,
        target_session_id=session_id,
        # Exclude the audio surface from receiving canvas updates
        exclude_surface_id=exclude_audio_surface_id,
    )

    # Broadcast to canvas surfaces
    sent_count = await broadcaster.broadcast(event)
    logger.info(f"Pushed result {result.get('intent_id')} to {sent_count} canvas surfaces")
