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
    audio_surface_id: str | None = None,
    use_batching: bool = True,
) -> None:
    """
    Background task that listens for async results and pushes them to the voice session.

    Results arrive from the synthesize strand via SSE or direct call.
    This task polls the session store for new results and pushes them.

    If use_batching is True (default for audio mode), results go through the
    ResultBatcher which applies urgency-based batching rules.
    Otherwise, results are pushed immediately.

    Tracks successfully pushed result IDs individually to avoid duplicates
    even if some pushes fail.
    """
    from .continuity import push_to_canvas
    from .batching import get_result_batcher

    store = get_store()
    batcher = get_result_batcher() if use_batching else None
    pushed_ids = set()  # Track successfully pushed result IDs in this session

    # Set up batcher callback if using batching
    if batcher:
        async def narrate_batch(results: list) -> None:
            """Callback to narrate a batch of results."""
            for r in results:
                try:
                    result_data = {
                        "intent_id": r.intent_id,
                        "topic_id": r.topic_id,
                        "summary": r.summary,
                        "urgency": r.urgency.value,
                        "data": r.data,
                    }
                    await voice_session.push_result(result_data)
                    await push_to_canvas(session_id, result_data, audio_surface_id)
                    logger.info(f"Narrated result {r.result_id} (batched)")
                except Exception as e:
                    logger.warning(f"Failed to narrate result {r.result_id}: {e}")

        batcher.set_narrate_callback(narrate_batch)

    while True:
        try:
            # Check for new results
            unsurfed = await store.get_unsurfaced_results(session_id)

            newly_pushed = []
            for result in unsurfed:
                result_id = result["id"]

                # Skip if already pushed (e.g., from previous iteration after error)
                if result_id in pushed_ids:
                    continue

                try:
                    result_data = {
                        "intent_id": result["intent_id"],
                        "topic_id": result["topic_id"],
                        "summary": result["summary"],
                        "urgency": result["urgency"],
                        "data": json.loads(result["data"]),
                    }

                    if use_batching and batcher:
                        # Queue with batcher for urgency-based narration
                        await batcher.queue_result(
                            result_id=result["id"],
                            intent_id=result["intent_id"],
                            topic_id=result["topic_id"],
                            summary=result["summary"],
                            data=json.loads(result["data"]),
                            urgency=result.get("urgency", "normal"),
                        )
                        # Push to canvas immediately (canvas doesn't use batching)
                        await push_to_canvas(session_id, result_data, audio_surface_id)
                        logger.info(f"Queued result {result_id} for batched audio narration")
                    else:
                        # Push directly to voice session (no batching)
                        await voice_session.push_result(result_data)
                        await push_to_canvas(session_id, result_data, audio_surface_id)

                    pushed_ids.add(result_id)
                    newly_pushed.append(result_id)

                except Exception as e:
                    # Failed to push this result - will retry on next iteration
                    logger.warning(f"Failed to push result {result_id}: {e}")

            if newly_pushed:
                # Mark successfully pushed results as surfaced
                await store.mark_results_surfed_by_ids(session_id, newly_pushed)

            # Wait before next check
            await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Result listener error: {e}", exc_info=True)
            await asyncio.sleep(1)
