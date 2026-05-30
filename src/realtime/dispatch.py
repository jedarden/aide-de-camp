"""
ADC Dispatch Intent Tool Handler

Called by the voice session's dispatch_intent tool.
Routes utterance to the intent router, returns ack immediately.
Results arrive async via push_result on the voice session.

Integrates conversation tracker, prefetcher, and diff engine for Phase 3 responsiveness.
"""
import asyncio
import httpx
import json
import uuid
from logging import getLogger
from pathlib import Path
from typing import Any

from ..session.store import get_store
from ..conversation.tracker import get_conversation_tracker
from ..context.prefetch import get_prefetcher, FollowUpPattern
from ..diff.engine import get_diff_engine


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

    Phase 3 enhancements:
    - Detects follow-up questions via conversation tracker
    - Triggers prefetch for likely follow-up patterns
    - Tracks implicit feedback signals
    """
    logger.info(f"Dispatching utterance for session {session_id}: {utterance[:100]}...")

    # Get Phase 3 services
    conversation_tracker = get_conversation_tracker()
    prefetcher = get_prefetcher()

    # Detect if this is a follow-up question
    detected_topics = []  # Would be populated by router in full implementation
    is_follow_up, suggested_topic_id = await conversation_tracker.detect_follow_up(
        session_id, utterance, detected_topics
    )

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

        # Track conversation turn
        await conversation_tracker.record_turn(
            session_id=session_id,
            utterance=utterance,
            primary_topic_id=suggested_topic_id if is_follow_up else None,
            is_follow_up=is_follow_up,
        )

        # Trigger prefetch for likely follow-up patterns
        if suggested_topic_id:
            # Get project slugs for the topic (simplified - in practice, would fetch from topic)
            project_slugs = detected_topics  # Placeholder
            if project_slugs:
                predictions = await prefetcher.analyze_utterance(
                    session_id=session_id,
                    utterance=utterance,
                    topic_id=suggested_topic_id,
                    project_slugs=project_slugs,
                    intent_type="status",  # Simplified
                )
                # Prefetch for high-confidence predictions
                if predictions:
                    await prefetcher.prefetch_for_predictions(predictions)

        # Return acknowledgment for the tool call
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

    Phase 3 enhancements:
    - Computes diffs between consecutive results using diff engine
    - Includes diff data in result payload for canvas rendering
    - Tracks implicit feedback signals (ack speed, surface switches)

    If use_batching is True (default for audio mode), results go through the
    ResultBatcher which applies urgency-based batching rules.
    Otherwise, results are pushed immediately.

    Tracks successfully pushed result IDs individually to avoid duplicates
    even if some pushes fail.
    """
    from .continuity import push_to_canvas
    from .batching import get_result_batcher
    from ..feedback.signals import get_feedback_tracker

    store = get_store()
    batcher = get_result_batcher() if use_batching else None
    diff_engine = get_diff_engine()
    feedback_tracker = get_feedback_tracker()
    pushed_ids = set()  # Track successfully pushed result IDs in this session

    # Track previous results per topic for diff computation
    previous_results: dict[str, dict] = {}

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
                    topic_id = result.get("topic_id")
                    result_data = {
                        "intent_id": result["intent_id"],
                        "topic_id": topic_id,
                        "summary": result["summary"],
                        "urgency": result["urgency"],
                        "data": json.loads(result["data"]),
                    }

                    # Compute diff with previous result for this topic (Phase 3)
                    if topic_id and topic_id in previous_results:
                        previous_result = previous_results[topic_id]
                        diff_result = await diff_engine.compute_diff(
                            topic_id=topic_id,
                            previous_result=previous_result,
                            current_result=result,
                        )
                        # Include diff in result data
                        if diff_result.has_changes:
                            result_data["diff"] = {
                                "has_changes": True,
                                "change_summary": diff_result.change_summary,
                                "fields": [
                                    {
                                        "field_name": f.field_name,
                                        "old_value": f.old_value,
                                        "new_value": f.new_value,
                                        "change_type": f.change_type,
                                    }
                                    for f in diff_result.fields
                                ],
                            }
                            logger.info(f"Computed diff for result {result_id}: {diff_result.change_summary}")

                    # Track previous result for diff computation
                    if topic_id:
                        previous_results[topic_id] = result

                    # Track implicit feedback: result created
                    await feedback_tracker.track_result_created(
                        result_id=result_id,
                        session_id=session_id,
                        topic_id=topic_id,
                    )

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
