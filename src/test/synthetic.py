"""
Synthetic Result Generation - Bypass intent routing for testing.

Provides POST /api/v1/test/dispatch/synthetic endpoint that generates
synthetic results matching the /dispatch structure without going through
the full intent routing pipeline (no LLM calls, no fetch operations).

This provides a controlled way to verify:
- Storage behavior (utterance, intent, topic, result creation)
- SSE broadcast behavior (result_created events)
- Canvas rendering (topic loading and card display)
"""
import asyncio
import uuid
from datetime import datetime
from logging import getLogger
from typing import Optional

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from ..session.store import get_store
from ..sse.broadcaster import get_broadcaster, SSEEvent


logger = getLogger(__name__)


class SyntheticDispatchRequest(BaseModel):
    """Request model for synthetic dispatch."""
    session_id: Optional[str] = Field(default=None, description="Session ID (generated if omitted)")
    surface_id: Optional[str] = Field(default=None, description="Surface ID for SSE targeting")
    utterance: str = Field(default="Synthetic test utterance", description="Test utterance text")
    project_slug: Optional[str] = Field(default="test-project", description="Project slug for result")
    intent_type: str = Field(default="status", description="Intent type for result")
    topic_type: str = Field(default="research", description="Topic type (project, research, personal, exception, compound)")
    summary: str = Field(default="Synthetic test result summary", description="Result summary text")
    urgency: str = Field(default="normal", description="Urgency level (critical, high, normal, low)")
    result_data: Optional[dict] = Field(default=None, description="Custom result data (synthesized if omitted)")
    test_metadata: Optional[dict] = Field(default=None, description="Additional test metadata")


class SyntheticDispatchResponse(BaseModel):
    """Response model matching /dispatch structure."""
    utterance_id: str
    session_id: str
    intent_count: int
    intent_ids: list[str]
    status: str
    message: str
    synthetic_results: list[dict]  # Synthetic result details


async def api_v1_synthetic_dispatch(request: SyntheticDispatchRequest) -> SyntheticDispatchResponse:
    """
    Generate synthetic results matching /dispatch structure.

    This endpoint bypasses the full intent routing pipeline (no LLM calls,
    no fetch operations) and creates synthetic data directly in the store.
    Used for testing storage and SSE behavior in isolation.

    Request body:
    {
        "session_id": "optional-session-id",
        "surface_id": "optional-surface-id",
        "utterance": "Test utterance text",
        "project_slug": "test-project",
        "intent_type": "status",
        "topic_type": "research",
        "summary": "Test result summary",
        "urgency": "normal",
        "result_data": {...},  // Optional, synthesized if omitted
        "test_metadata": {...}  // Optional test metadata
    }

    Returns:
    {
        "utterance_id": "...",
        "session_id": "...",
        "intent_count": 1,
        "intent_ids": ["..."],
        "status": "synthetic",
        "message": "...",
        "synthetic_results": [
            {
                "intent_id": "...",
                "topic_id": "...",
                "result_id": "...",
                "summary": "...",
                "urgency": "normal",
                "project_slug": "test-project",
                "intent_type": "status",
                "test_metadata": {...}
            }
        ]
    }

    Error responses:
        500: Storage or SSE broadcast error
    """
    # Generate IDs
    utterance_id = str(uuid.uuid4())
    intent_id = str(uuid.uuid4())
    session_id = request.session_id or f"synthetic-test-{uuid.uuid4().hex[:12]}"

    logger.info(f"[SYNTHETIC] Generating synthetic result for session {session_id}")

    try:
        # Initialize store and broadcaster
        store = await get_store()
        broadcaster = get_broadcaster()

        # Create session if needed (pass session_id so sessions.id PK matches)
        session = await store.get_session(session_id)
        if not session:
            await store.create_session(session_id)
            logger.info(f"[SYNTHETIC] Created session: {session_id}")

        # Create utterance record
        await store.create_utterance(session_id, request.utterance, utterance_id)

        # Create intent record
        await store.create_intent(
            utterance_id=utterance_id,
            session_id=session_id,
            project_slug=request.project_slug,
            intent_type=request.intent_type,
        )

        # Create topic
        topic_id, _ = await store.find_or_create_topic(
            label=request.utterance[:80],
            topic_type=request.topic_type,
            project_slugs=[request.project_slug] if request.project_slug else [],
            session_id=session_id,
        )

        # Link intent to topic
        await store.link_intent_to_topic(intent_id, topic_id)

        # Synthesize result data if not provided
        if request.result_data is None:
            result_data = {
                "synthetic": True,
                "test_type": "synthetic_dispatch",
                "project_slug": request.project_slug,
                "intent_type": request.intent_type,
                "generated_at": datetime.now().isoformat(),
                "test_fields": {
                    "status_check": "All systems operational",
                    "deployment_status": "No active deployments",
                    "recent_logs": "Synthetic log entries for testing",
                    "cluster_health": "Healthy",
                }
            }
        else:
            result_data = request.result_data

        # Create result
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=session_id,
            summary=request.summary,
            data=result_data,
            urgency=request.urgency,
        )

        # Broadcast result_created via SSE if surface_id provided
        if broadcaster and request.surface_id:
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    target_surface_id=request.surface_id,
                    data={
                        "intent_id": intent_id,
                        "topic_id": topic_id,
                        "summary": request.summary,
                        "urgency": request.urgency,
                    }
                )
            )
            logger.info(f"[SYNTHETIC] Broadcast result_created to surface {request.surface_id}")

        # Build synthetic result details
        synthetic_result = {
            "intent_id": intent_id,
            "topic_id": topic_id,
            "result_id": result_id,
            "summary": request.summary,
            "urgency": request.urgency,
            "project_slug": request.project_slug,
            "intent_type": request.intent_type,
            "topic_type": request.topic_type,
            "synthetic": True,
        }

        # Add test_metadata if provided
        if request.test_metadata:
            synthetic_result["test_metadata"] = request.test_metadata

        logger.info(f"[SYNTHETIC] Created synthetic result {result_id} for intent {intent_id}")

        return SyntheticDispatchResponse(
            utterance_id=utterance_id,
            session_id=session_id,
            intent_count=1,
            intent_ids=[intent_id],
            status="synthetic",
            message=f"Synthetic result generated for intent {intent_id}",
            synthetic_results=[synthetic_result],
        )

    except Exception as e:
        logger.error(f"[SYNTHETIC] Generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Synthetic generation error: {str(e)}")


async def api_v1_batch_synthetic_dispatch(
    session_id: Optional[str] = Query(default=None, description="Session ID"),
    surface_id: Optional[str] = Query(default=None, description="Surface ID for SSE targeting"),
    count: int = Query(default=3, ge=1, le=10, description="Number of synthetic results to generate"),
    delay_ms: int = Query(default=100, ge=0, le=1000, description="Delay between results in milliseconds"),
) -> dict:
    """
    Generate multiple synthetic results with streaming SSE updates.

    This endpoint creates several synthetic results sequentially and streams
    each via SSE as it's created, simulating a multi-intent dispatch scenario.

    Query parameters:
        session_id: Session ID (generated if omitted)
        surface_id: Surface ID for SSE targeting
        count: Number of results to generate (1-10, default 3)
        delay_ms: Delay between results in ms (0-1000, default 100)

    Returns:
    {
        "utterance_id": "...",
        "session_id": "...",
        "intent_count": 3,
        "intent_ids": ["...", "...", "..."],
        "status": "batch_synthetic",
        "message": "...",
        "synthetic_results": [...]
    }
    """
    # Generate IDs
    utterance_id = str(uuid.uuid4())
    session_id = session_id or f"batch-synthetic-{uuid.uuid4().hex[:12]}"

    logger.info(f"[BATCH SYNTHETIC] Generating {count} results for session {session_id}")

    try:
        store = await get_store()
        broadcaster = get_broadcaster()

        # Create session if needed
        session = await store.get_session(session_id)
        if not session:
            await store.create_session(session_id)

        # Create utterance record
        await store.create_utterance(
            session_id,
            f"Batch synthetic test ({count} results)",
            utterance_id
        )

        intent_ids = []
        synthetic_results = []

        # Generate results sequentially with delay
        for i in range(count):
            intent_id = str(uuid.uuid4())
            intent_ids.append(intent_id)

            # Create intent record
            await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug=f"test-project-{i+1}",
                intent_type="status",
            )

            # Create topic
            topic_id, _ = await store.find_or_create_topic(
                label=f"Batch test result {i+1}",
                topic_type="research",
                project_slugs=[f"test-project-{i+1}"],
                session_id=session_id,
            )

            # Link intent to topic
            await store.link_intent_to_topic(intent_id, topic_id)

            # Create result
            result_data = {
                "synthetic": True,
                "test_type": "batch_synthetic",
                "batch_index": i,
                "batch_total": count,
                "generated_at": datetime.now().isoformat(),
            }

            result_id = await store.create_result(
                intent_id=intent_id,
                topic_id=topic_id,
                session_id=session_id,
                summary=f"Batch synthetic result {i+1} of {count}",
                data=result_data,
                urgency="normal",
            )

            # Broadcast via SSE
            if broadcaster and surface_id:
                await broadcaster.broadcast(
                    SSEEvent(
                        event_type="result_created",
                        target_surface_id=surface_id,
                        data={
                            "intent_id": intent_id,
                            "topic_id": topic_id,
                            "summary": f"Batch synthetic result {i+1} of {count}",
                            "urgency": "normal",
                        }
                    )
                )

            synthetic_results.append({
                "intent_id": intent_id,
                "topic_id": topic_id,
                "result_id": result_id,
                "summary": f"Batch synthetic result {i+1} of {count}",
                "urgency": "normal",
                "project_slug": f"test-project-{i+1}",
                "intent_type": "status",
                "synthetic": True,
                "batch_index": i,
            })

            # Delay between results (except after the last one)
            if i < count - 1 and delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)

        logger.info(f"[BATCH SYNTHETIC] Generated {count} synthetic results")

        return {
            "utterance_id": utterance_id,
            "session_id": session_id,
            "intent_count": count,
            "intent_ids": intent_ids,
            "status": "batch_synthetic",
            "message": f"Generated {count} synthetic results with streaming SSE",
            "synthetic_results": synthetic_results,
        }

    except Exception as e:
        logger.error(f"[BATCH SYNTHETIC] Generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch synthetic error: {str(e)}")
