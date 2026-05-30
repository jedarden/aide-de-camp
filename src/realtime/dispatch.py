"""
ADC Dispatch Intent Tool Handler

Called by the voice session's dispatch_intent tool.
Routes utterance to the intent router, returns ack immediately.
Results arrive async via push_result on the voice session.
"""
import asyncio
import httpx
import json
import uuid
from logging import getLogger
from pathlib import Path
from typing import Any

from ..session.store import get_store


logger = getLogger(__name__)
ROUTER_API_URL = "http://localhost:8000/router"  # Local router endpoint


async def dispatch_intent(
    utterance: str,
    session_id: str,
    voice_session: Any,  # VoiceSession instance
) -> str:
    """
    Dispatch an utterance to the intent router.

    Tool-as-trigger: returns ack immediately, results arrive async.
    """
    logger.info(f"Dispatching utterance for session {session_id}: {utterance[:100]}...")

    # Store utterance
    store = get_store()
    utterance_id = await store.create_utterance(session_id, utterance)

    # Call router (this will spawn fetch+synthesize workers)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                ROUTER_API_URL,
                json={
                    "utterance": utterance,
                    "utterance_id": utterance_id,
                    "session_id": session_id,
                },
            )
            resp.raise_for_status()
            router_result = resp.json()

        # Log the routing result
        logger.info(f"Router result: {json.dumps(router_result, indent=2)}")

        # The router has dispatched intents to workers
        # Results will arrive via result queue and be narrated
        # Return ack for the tool call
        intent_count = len(router_result.get("intents", []))
        if intent_count == 0:
            return "I'm not sure what you're asking about. Could you clarify?"
        elif intent_count == 1:
            return "On it."
        else:
            return f"Working on {intent_count} things."

    except httpx.ConnectError:
        logger.error("Router not available")
        return "I'm having trouble routing that request right now."
    except httpx.HTTPStatusError as e:
        logger.error(f"Router error: {e}")
        return "Something went wrong with routing."
    except Exception as e:
        logger.error(f"Dispatch error: {e}", exc_info=True)
        return "I'm having trouble with that request."


async def result_listener(
    session_id: str,
    voice_session: Any,
) -> None:
    """
    Background task that listens for async results and pushes them to the voice session.

    Results arrive from the synthesize strand via SSE or direct call.
    This task polls the session store for new results and pushes them.
    """
    store = get_store()
    last_check_time = asyncio.get_event_loop().time()

    while True:
        try:
            # Check for new results
            unsurfed = await store.get_unsurfaced_results(session_id)

            for result in unsurfed:
                # Push to voice session for narration
                await voice_session.push_result({
                    "intent_id": result["intent_id"],
                    "topic_id": result["topic_id"],
                    "summary": result["summary"],
                    "urgency": result["urgency"],
                    "data": json.loads(result["data"]),
                })

                # Mark as surfaced (for canvas; audio will narrate)
                # Note: we don't mark acked_at here — that's after user acknowledges
                logger.info(f"Pushed result {result['id']} to voice session")

            if unsurfed:
                # Mark all as surfaced
                await store.mark_results_surfed(session_id)

            # Wait before next check
            await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Result listener error: {e}", exc_info=True)
            await asyncio.sleep(1)
