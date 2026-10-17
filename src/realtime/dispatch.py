"""
ADC Dispatch Intent Tool Handler

Called by the voice session's dispatch_intent tool.
Routes utterance to the intent router, returns ack immediately.
Results arrive async via push_result on the voice session.

Integrates conversation tracker, prefetcher, and diff engine for Phase 3 responsiveness.
"""
import asyncio
import json
import threading
import time
from logging import getLogger
from typing import Any

import httpx

from ..context.prefetch import get_prefetcher
from ..conversation.tracker import get_conversation_tracker
from ..session.store import get_store

logger = getLogger(__name__)
ROUTER_API_URL = "http://localhost:8000/router"  # Local router endpoint

# Intent correlation registry: session_id -> intent IDs dispatched by that
# session's dispatch_intent tool calls, most recent last. The result listener
# reads this to pick up results belonging to intents the voice session
# created, so only results produced by this session's own tool calls are
# narrated on that session. Results are persisted with surfaced_at already
# set, so the unsurfaced poll this registry replaces never matched anything.
_MAX_TRACKED_INTENTS_PER_SESSION = 64
_pending_intents: dict[str, list[str]] = {}
_pending_intents_lock = threading.Lock()


def register_session_intents(session_id: str, intent_ids: list[str]) -> None:
    """Record intent IDs produced by a session's dispatch_intent tool call."""
    with _pending_intents_lock:
        tracked = _pending_intents.setdefault(session_id, [])
        for intent_id in intent_ids:
            if intent_id and intent_id not in tracked:
                tracked.append(intent_id)
        # Bound memory for long-lived sessions: keep the most recent intents.
        del tracked[:-_MAX_TRACKED_INTENTS_PER_SESSION]


def get_session_intents(session_id: str) -> list[str]:
    """Return the intent IDs tracked for a session (oldest first)."""
    with _pending_intents_lock:
        return list(_pending_intents.get(session_id, []))


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
    - Uses pre-fetched data when available
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

    # Check for pre-fetched data if this is a follow-up
    prefetch_data = None
    if is_follow_up and suggested_topic_id:
        # Check if we have pre-fetched data for likely patterns
        prefetch_data = prefetcher.get_all_prefetch_data(suggested_topic_id)
        if prefetch_data:
            logger.info(f"Found pre-fetched data for topic {suggested_topic_id}: {list(prefetch_data.keys())}")

    # Store utterance
    store = await get_store()
    utterance_id = await store.create_utterance(session_id, utterance)

    # Call router (this will spawn fetch+synthesize workers)
    try:
        router_request = {
            "utterance": utterance,
            "utterance_id": utterance_id,
            "session_id": session_id,
        }

        # Include pre-fetched data if available (Phase 3)
        if prefetch_data:
            router_request["prefetch_data"] = prefetch_data
            router_request["is_follow_up"] = is_follow_up
            router_request["topic_id"] = suggested_topic_id

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                ROUTER_API_URL,
                json=router_request,
            )
            resp.raise_for_status()
            router_result = resp.json()

        # Log the routing result
        logger.info(f"Router result: {json.dumps(router_result, indent=2)}")

        # Correlate the router's intents with this session so the result
        # listener can pick up their results as they land in the store.
        intent_ids = [
            intent["intent_id"]
            for intent in router_result.get("intents", [])
            if isinstance(intent, dict) and intent.get("intent_id")
        ]
        if intent_ids:
            register_session_intents(session_id, intent_ids)

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
            # Fetch actual project slugs from the topic's registry entry
            topic = await store.get_topic(suggested_topic_id)
            project_slugs = topic.get("project_slugs", []) if topic else []

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

    Results are correlated by intent: dispatch_intent registers the intent IDs
    returned by the router, and this task polls the store for results belonging
    to those intents, pushing each to the voice session for narration. (Results
    are persisted with surfaced_at already set, so an unsurfaced poll would
    never match.)

    Phase 3 enhancements:
    - Tracks implicit feedback signals (ack speed, surface switches)

    If use_batching is True (default for audio mode), results go through the
    ResultBatcher which applies urgency-based batching rules for audio
    narration. Canvas delivery via SSE is never batched.

    Tracks successfully pushed result IDs individually to avoid duplicates
    even if some pushes fail.
    """
    from ..feedback.signals import get_feedback_tracker
    from .batching import get_result_batcher
    from .continuity import push_to_canvas

    store = await get_store()
    batcher = get_result_batcher() if use_batching else None
    feedback_tracker = get_feedback_tracker()
    pushed_ids = set()  # Track successfully pushed result IDs in this session

    # Set up batcher callback if using batching
    if batcher:
        async def narrate_batch(results: list) -> None:
            """Callback to narrate a batch of results (audio only).

            Canvas delivery already happened when the result was queued —
            the batcher only gates audio narration.
            """
            for r in results:
                try:
                    await voice_session.push_result({
                        "intent_id": r.intent_id,
                        "topic_id": r.topic_id,
                        "summary": r.summary,
                        "urgency": r.urgency.value,
                        "data": r.data,
                    })
                    logger.info(f"Narrated result {r.result_id} (batched)")
                except Exception as e:
                    logger.warning(f"Failed to narrate result {r.result_id}: {e}")

        batcher.set_narrate_callback(narrate_batch)

    async def deliver_result(result: dict) -> None:
        """Deliver one store row: audio narration (possibly batched) + canvas SSE."""
        topic_id = result.get("topic_id")
        result_data = {
            "intent_id": result["intent_id"],
            "topic_id": topic_id,
            "summary": result["summary"],
            "urgency": result["urgency"],
            "data": json.loads(result["data"]),
        }

        # Track implicit feedback: result created
        await feedback_tracker.track_result_created(
            result_id=result["id"],
            session_id=session_id,
            topic_id=topic_id,
        )

        if use_batching and batcher:
            # Queue with batcher for urgency-based audio narration
            await batcher.queue_result(
                result_id=result["id"],
                intent_id=result["intent_id"],
                topic_id=topic_id,
                summary=result["summary"],
                data=result_data["data"],
                urgency=result.get("urgency", "normal"),
            )
            logger.info(f"Queued result {result['id']} for batched audio narration")
        else:
            # Push directly to voice session (no batching)
            await voice_session.push_result(result_data)

        # Push to canvas immediately (canvas doesn't use batching)
        await push_to_canvas(session_id, result_data, audio_surface_id)

    while True:
        try:
            # Check for pending approvals awaiting narration (voice mode support)
            pending_approvals = await store.get_pending_approvals_for_session(session_id)
            for approval in pending_approvals:
                approval_id = approval["approval_id"]
                intent_id = approval["intent_id"]

                # Skip if already narrated (check against pushed_ids)
                if f"approval-{approval_id}" in pushed_ids:
                    continue

                try:
                    # Build narration from approval data
                    approval_narration = f"I need your approval before creating this {approval.get('bead_type', 'bead')}. "

                    # Add reason if available
                    if approval.get("validation_result"):
                        vr = approval["validation_result"]
                        if vr.get("approval_requirement", {}).get("reason"):
                            approval_narration += f"Reason: {vr['approval_requirement']['reason']}. "

                    # Add utterance preview
                    utterance = approval.get("utterance", "")
                    if utterance:
                        utterance_preview = utterance[:100]
                        if len(utterance) > 100:
                            utterance_preview += "..."
                        approval_narration += f"Request: {utterance_preview}. "

                    approval_narration += "Please approve or reject this request on the canvas."

                    # Push approval as a result for narration
                    approval_result = {
                        "intent_id": intent_id,
                        "summary": approval_narration,
                        "urgency": "high",  # Approvals are high priority
                        "data": {
                            "type": "approval_required",
                            "approval_id": approval_id,
                            "bead_type": approval.get("bead_type", "bead"),
                            "utterance": utterance,
                        },
                        "surfaced_at": time.time(),
                    }

                    if use_batching and batcher:
                        # Queue with batcher for immediate narration (high urgency)
                        await batcher.queue_result(
                            result_id=f"approval-{approval_id}",
                            intent_id=intent_id,
                            topic_id=approval.get("topic_id"),
                            summary=approval_narration,
                            data=approval_result["data"],
                            urgency="high",
                        )
                    else:
                        # Push directly to voice session
                        await voice_session.push_result(approval_result)

                    logger.info(f"Narrated approval requirement {approval_id} for intent {intent_id}")
                    pushed_ids.add(f"approval-{approval_id}")

                except Exception as e:
                    logger.warning(f"Failed to narrate approval {approval_id}: {e}")

            # Results for intents this session dispatched via dispatch_intent
            # (tool-call correlation)
            newly_pushed: list[str] = []
            for intent_id in get_session_intents(session_id):
                intent_results = await store.get_results_for_intent(intent_id)
                for result in reversed(intent_results):  # oldest first
                    result_id = result["id"]

                    # Skip if already pushed (e.g., from previous iteration after error)
                    if result_id in pushed_ids:
                        continue

                    try:
                        await deliver_result(result)
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
