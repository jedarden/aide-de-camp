"""
Test Router - FastAPI router for test endpoints.

Provides test endpoints that bypass the Web Speech API and directly
inject test utterances into the dispatch pipeline for end-to-end testing.

Also provides TTS/narration testing endpoints for capturing and verifying
narration events without actual audio output.

Session injection/cleanup endpoints (POST /sessions, DELETE /sessions/{id})
support canvas test-data injection: creating sessions with predictable IDs and
tearing them down cleanly after a test run.
"""
import uuid
from logging import getLogger
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..api.models import DispatchRequest, DispatchResponse

logger = getLogger(__name__)

# FastAPI router instance for test endpoints
router = APIRouter()

# Import narration endpoints to register them


class SessionCreateRequest(BaseModel):
    """Request body for creating a test session with a predictable ID."""
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Predictable session ID for test repeatability (e.g. 'test-inject-foo'). "
            "If omitted, a random 'test-inject-<hex>' ID is generated."
        ),
    )


@router.post("/sessions")
async def api_v1_create_session(request: SessionCreateRequest) -> dict:
    """
    Create a test session with an explicit, predictable ID.

    Mounted at ``POST /api/v1/sessions``. Used by canvas test-data injection
    utilities to set up a known session before injecting topics. Idempotent:
    if the session already exists it is returned with ``created: false``.

    Request body:
    ```
    {"session_id": "test-inject-my-scenario"}   # optional
    ```

    Returns:
    ```
    {"session_id": "test-inject-my-scenario", "created": true}
    ```
    """
    from ..session.store import get_store

    store = await get_store()
    session_id = request.session_id or f"test-inject-{uuid.uuid4().hex[:12]}"
    existing = await store.get_session(session_id)
    created = False
    if not existing:
        await store.create_session(session_id)
        created = True
    logger.info(f"[TEST] create_session id={session_id} created={created}")
    return {"session_id": session_id, "created": created}


@router.delete("/sessions/{session_id}")
async def api_v1_delete_session(session_id: str) -> dict:
    """
    Delete a test session and all data tied to it.

    Mounted at ``DELETE /api/v1/sessions/{session_id}``. Removes the session's
    topics, results, intents, utterances, surfaces, and feedback signals (see
    ``SessionStore.delete_session`` for the explicit cleanup order — SQLite FK
    CASCADE is not enforced here). Intended for test teardown.

    Returns:
    ```
    {"status": "deleted", "session_id": "...", "session_removed": 1, "topics_removed": 3}
    ```
    """
    from ..session.store import get_store

    store = await get_store()
    summary = await store.delete_session(session_id)
    logger.info(f"[TEST] delete_session {summary}")
    return {"status": "deleted", **summary}


class TestClassificationRequest(BaseModel):
    """Request model for test classification."""
    utterance: str = Field(..., description="The utterance text to classify")
    session_id: str = Field(default="test-session", description="Session ID for context")


class TestClassificationResponse(BaseModel):
    """Response model for test classification."""
    utterance: str
    session_id: str
    classifications: list[dict]
    message: str


class IntentClassifyRequest(BaseModel):
    """Request model for intent classification endpoint."""
    utterance: str = Field(..., description="The utterance text to classify")


class IntentClassifyResponse(BaseModel):
    """Response model for intent classification endpoint."""
    utterance: str
    classifications: list[dict]
    message: str


@router.post("/test/classify")
async def test_classify_intent(request: TestClassificationRequest) -> TestClassificationResponse:
    """
    Test endpoint for intent classification.

    Calls the intent router's classify_utterance() method and returns
    the classification results including intent type, confidence, reasoning,
    urgency, and project slug.

    This is a lightweight endpoint for testing the LLM classification logic
    without doing full routing and processing.

    Request body:
    {
        "utterance": "test query here",
        "session_id": "optional-session-id"
    }

    Returns:
    {
        "utterance": "...",
        "session_id": "...",
        "classifications": [
            {
                "intent_type": "status|action|brainstorm|lookup|reminder|self-modification|monitoring-config|task-profile|clarification",
                "project_slug": "project-id or null",
                "confidence": 0.0-1.0,
                "utterance_fragment": "the specific fragment this intent covers",
                "reasoning": "brief explanation of classification",
                "urgency": "critical|high|normal|low"
            }
        ],
        "message": "..."
    }
    """
    from ..intent.router import get_router

    logger.info(f"[TEST] Classifying utterance: {request.utterance[:100]}...")

    try:
        # Get router and classify
        router = get_router()
        classifications, _ = await router.classify_utterance(
            utterance=request.utterance,
            session_id=request.session_id,
        )

        # Convert classifications to dict format
        classification_dicts = []
        for classification in classifications:
            classification_dicts.append({
                "intent_type": classification.intent_type.value,
                "project_slug": classification.project_slug,
                "confidence": classification.confidence,
                "utterance_fragment": classification.utterance_fragment,
                "reasoning": classification.reasoning,
                "urgency": classification.urgency,
            })

        return TestClassificationResponse(
            utterance=request.utterance,
            session_id=request.session_id,
            classifications=classification_dicts,
            message=f"Classified into {len(classifications)} intent(s)",
        )

    except Exception as e:
        logger.error(f"[TEST] Classification error: {e}", exc_info=True)
        raise


@router.post("/test/intent-classify")
async def test_intent_classify(request: IntentClassifyRequest) -> IntentClassifyResponse:
    """
    Test intent classification endpoint without audio processing.

    Mounted at ``POST /api/v1/test/intent-classify``. This endpoint accepts
    test utterances directly into the intent classification pipeline without
    requiring audio processing or microphone dependencies. Returns classification
    results in the same format as /dispatch would produce.

    Request body:
    ```
    {
        "utterance": "test utterance here"
    }
    ```

    Returns:
    ```
    {
        "utterance": "...",
        "classifications": [
            {
                "intent_type": "status|action|brainstorm|lookup|reminder|self-modification|monitoring-config|task-profile|clarification",
                "project_slug": "project-id or null",
                "confidence": 0.0-1.0,
                "utterance_fragment": "the specific fragment this intent covers",
                "reasoning": "brief explanation of classification",
                "urgency": "critical|high|normal|low",
                "lookup_kind": "logs|config|docs or null"
            }
        ],
        "message": "Classified into N intent(s)"
    }
    ```

    Error responses:
        422: Validation error (missing or invalid utterance field)
        500: Classification processing error
    """
    from ..intent.router import get_router

    logger.info(f"[TEST] Classifying intent: {request.utterance[:100]}...")

    try:
        # Get router and classify
        router = get_router()
        classifications, _ = await router.classify_utterance(
            utterance=request.utterance,
            session_id="test-session",  # Default session for classification
        )

        # Convert classifications to dict format (same as /dispatch would produce)
        classification_dicts = []
        for classification in classifications:
            classification_dict = {
                "intent_type": classification.intent_type.value,
                "project_slug": classification.project_slug,
                "confidence": classification.confidence,
                "utterance_fragment": classification.utterance_fragment,
                "reasoning": classification.reasoning,
                "urgency": classification.urgency,
            }
            # Add lookup_kind only if present (optional field for lookup intents)
            if classification.lookup_kind is not None:
                classification_dict["lookup_kind"] = classification.lookup_kind
            classification_dicts.append(classification_dict)

        return IntentClassifyResponse(
            utterance=request.utterance,
            classifications=classification_dicts,
            message=f"Classified into {len(classifications)} intent(s)",
        )

    except Exception as e:
        logger.error(f"[TEST] Intent classification error: {e}", exc_info=True)
        raise


class TestCreateTopicRequest(BaseModel):
    """Request model for creating test topics."""
    session_id: str = Field(..., description="Session ID to create topic in")
    label: str = Field(..., description="Topic label")
    type: str = Field(default="project", description="Topic type (project, research, personal, exception, compound)")
    summary: str = Field(default="Test result summary", description="Result summary text")
    urgency: str = Field(default="normal", description="Urgency level (critical, high, normal, low)")
    staleness_seconds: int = Field(default=0, description="How old the result is in seconds")


@router.post("/test/create-topic")
async def test_create_topic(request: TestCreateTopicRequest) -> dict:
    """
    Test endpoint for creating topics directly in the session store.

    This bypasses the full dispatch pipeline and creates a topic with a result
    directly in the database. Used for canvas verification testing.

    Request body:
    {
        "session_id": "test-session-id",
        "label": "Test Topic",
        "type": "project",
        "summary": "Test result summary",
        "urgency": "normal",
        "staleness_seconds": 0
    }

    Returns:
        {
            "status": "created",
            "topic_id": "...",
            "label": "Test Topic",
            "type": "project"
        }
    """
    import uuid
    from datetime import datetime

    import aiosqlite

    from ..session.store import get_store
    from ..sse.broadcaster import SSEEvent, get_broadcaster

    logger.info(f"[TEST] Creating test topic: {request.label}")

    try:
        # Get session store
        store = await get_store()

        # Create or get session (pass session_id so sessions.id PK matches the
        # topic/session_id below — otherwise create_session() mints an unrelated id).
        session = await store.get_session(request.session_id)
        if not session:
            await store.create_session(request.session_id)
            logger.info(f"[TEST] Created session: {request.session_id}")

        # results.intent_id is NOT NULL (and references intents.id), and
        # intents.utterance_id is NOT NULL — so anchor the result on a real
        # utterance → intent pair via the store methods rather than a raw insert
        # with a dangling id.
        utterance_id = str(uuid.uuid4())
        await store.create_utterance(
            request.session_id, f"[test-inject] {request.label}", utterance_id
        )
        intent_id = await store.create_intent(
            utterance_id=utterance_id,
            session_id=request.session_id,
            project_slug="test-project",
            intent_type="test",
        )

        topic_id = await store.create_topic(
            label=request.label,
            topic_type=request.type,
            project_slugs=["test-project"],
            scope="session",
            session_id=request.session_id,
        )
        result_id = await store.create_result(
            intent_id=intent_id,
            topic_id=topic_id,
            session_id=request.session_id,
            summary=request.summary,
            data={"test": True, "data": "test data"},
            urgency=request.urgency,
        )

        # Optionally backdate the topic + result so staleness-driven canvas
        # tests can simulate an aged card.
        if request.staleness_seconds > 0:
            # Backdate in epoch seconds using the codebase's standard
            # `datetime.now().timestamp()` (local-naive → correct epoch on this
            # host). Do NOT use `datetime.utcnow().timestamp()`: utcnow() is
            # naive-UTC but .timestamp() reads it as local time, so on a box
            # whose TZ ≠ UTC (this one is EDT/UTC-4) the result lands 4h in the
            # FUTURE, making `now - last_active` negative and every backdated
            # card render "fresh". Caught by the real-browser staleness suite
            # (bead adc-jr35); the headless shim suite never hit live backdating.
            created_ts = int(datetime.now().timestamp()) - request.staleness_seconds
            async with aiosqlite.connect(store.db_path) as db:
                await db.execute(
                    "UPDATE topics SET created_at = ?, last_active = ? WHERE id = ?",
                    (created_ts, created_ts, topic_id),
                )
                await db.execute(
                    "UPDATE results SET created_at = ? WHERE id = ?",
                    (created_ts, result_id),
                )
                await db.commit()

        # Broadcast result_created so any already-connected canvas surface for
        # this session reloads its topics and renders the new card LIVE — matching
        # the real dispatch pipeline's behaviour. Targets the session (not a
        # specific surface), so every open surface for it refreshes; if none is
        # connected (e.g. an inject-then-navigate test) this is a no-op and the
        # card is picked up by loadTopics() on the next page load / reconnect.
        broadcaster = get_broadcaster()
        if broadcaster:
            await broadcaster.broadcast(
                SSEEvent(
                    event_type="result_created",
                    target_session_id=request.session_id,
                    data={
                        "topic_id": topic_id,
                        "result_id": result_id,
                        "summary": request.summary,
                        "urgency": request.urgency,
                    },
                )
            )

        logger.info(f"[TEST] Created topic {topic_id} with result {result_id}")

        return {
            "status": "created",
            "topic_id": topic_id,
            "result_id": result_id,
            "label": request.label,
            "type": request.type,
            "urgency": request.urgency,
            "staleness_seconds": request.staleness_seconds,
        }

    except Exception as e:
        logger.error(f"[TEST] Create topic error: {e}", exc_info=True)
        raise


class TestDropSSERequest(BaseModel):
    """Request body for dropping every live SSE stream for a session."""
    session_id: str = Field(
        ..., description="Session whose live SSE streams should be dropped."
    )


@router.post("/test/drop-sse")
async def api_v1_test_drop_sse(request: TestDropSSERequest) -> dict:
    """
    Abruptly drop every live SSE stream for a session.

    Mounted at ``POST /api/v1/test/drop-sse``. Pushes the broadcaster's drop
    sentinel onto each matching connection so its event generator returns
    WITHOUT emitting a ``disconnect`` event — the browser's ``EventSource``
    then sees the stream end abruptly, fires ``onerror``, and performs its
    native auto-reconnect. This faithfully simulates a real proxy/server
    connection drop, which Playwright ``context.set_offline`` CANNOT reproduce
    against a loopback server: Chromium exempts loopback connections from its
    offline emulation, so an established ``localhost`` SSE stream is never cut
    (proven by ``tests/e2e/_probe_offline.py`` — statusText stays "Connected"
    for 25s after ``set_offline(True)``).

    Returns the number of live streams that were signalled:

    ```
    {"session_id": "...", "dropped_streams": 1}
    ```

    A count of 0 means no live stream existed for that session at drop time
    (the canvas surface was not connected, or had already dropped).
    """
    from ..sse.broadcaster import get_broadcaster

    broadcaster = get_broadcaster()
    dropped = broadcaster.drop_session(request.session_id)
    logger.info(
        f"[TEST] drop-sse session={request.session_id} streams_dropped={dropped}"
    )
    return {"session_id": request.session_id, "dropped_streams": dropped}


class TestSSEBroadcastRequest(BaseModel):
    """Request model for test SSE broadcast."""
    surface_id: Optional[str] = Field(
        default=None,
        description="Optional surface ID to target with the broadcast"
    )
    event_type: str = Field(
        default="test",
        description="SSE event type to broadcast"
    )
    test_data: dict = Field(
        default_factory=dict,
        description="Test data to include in the broadcast payload"
    )


@router.post("/test/sse-broadcast")
async def api_v1_test_sse_broadcast(request: TestSSEBroadcastRequest) -> dict:
    """
    Test endpoint for SSE broadcast functionality.

    Mounted at ``POST /api/v1/test/sse-broadcast``. This endpoint accepts
    test SSE broadcast requests and returns 200 OK. Currently provides
    only the skeleton without actual SSE broadcasting (future enhancement).

    Request body:
    ```
    {
        "surface_id": "optional-surface-id",
        "event_type": "test",
        "test_data": {"key": "value"}
    }
    ```

    Returns:
    ```
    {
        "status": "ok",
        "message": "Test SSE broadcast endpoint received request",
        "surface_id": "...",
        "event_type": "test"
    }
    ```

    Future enhancement: Actual SSE broadcast to connected surfaces when
    surface_id is provided.
    """
    logger.info(
        f"[TEST] SSE broadcast request received - "
        f"surface_id: {request.surface_id}, event_type: {request.event_type}"
    )

    # TODO: Future enhancement - implement actual SSE broadcast
    # if request.surface_id:
    #     broadcaster = get_broadcaster()
    #     await broadcaster.broadcast(
    #         SSEEvent(
    #             event_type=request.event_type,
    #             target_surface_id=request.surface_id,
    #             data=request.test_data,
    #         )
    #     )

    return {
        "status": "ok",
        "message": "Test SSE broadcast endpoint received request",
        "surface_id": request.surface_id,
        "event_type": request.event_type,
    }


@router.post("/dispatch")
async def dispatch(request: DispatchRequest) -> DispatchResponse:
    """
    Test dispatch endpoint - connect to intent router and fetch/synthesize pipeline.

    Mounted at ``POST /api/v1/test/dispatch``. This endpoint accepts test
    dispatch requests with utterance, session_id, and surface_id, validates
    the input, routes through the intent router, executes fetch/synthesize,
    and returns a structured response.

    Bypasses Web Speech API transcription - takes utterance text directly.

    Request body:
    ```
    {
        "utterance": "test utterance here",
        "session_id": "test-session-id",
        "surface_id": "test-surface-id"
    }
    ```

    Returns the same ``DispatchResponse`` envelope as ``POST /dispatch``.

    Error responses:
        400: Validation error (missing or invalid fields)
        500: Router or processing error
    """
    import asyncio

    from ..intent.router import get_router
    from ..session.store import get_store
    from ..sse.broadcaster import SSEEvent, get_broadcaster

    logger.info(
        f"[TEST] Dispatch request received - "
        f"utterance: {request.utterance[:50]}..., "
        f"session_id: {request.session_id}, "
        f"surface_id: {request.surface_id}"
    )

    # Generate utterance ID
    utterance_id = request.utterance_id or str(__import__('uuid').uuid4())
    session_id = request.session_id
    surface_id = request.surface_id

    try:
        # Initialize store and router
        store = await get_store()
        router = get_router(store)

        # Create session if needed (pass session_id so sessions.id PK matches)
        session = await store.get_session(session_id)
        if not session:
            await store.create_session(session_id)
            logger.info(f"[TEST] Created new session: {session_id}")

        # Create utterance record
        await store.create_utterance(session_id, request.utterance, utterance_id)

        # Route the utterance through intent router
        routed_intents = await router.route_utterance(
            utterance=request.utterance,
            utterance_id=utterance_id,
            session_id=session_id,
        )

        # Create intent records and process in parallel
        intent_tasks = []
        intent_ids = []

        for routed_intent in routed_intents:
            classification = routed_intent.classification
            await store.create_intent(
                utterance_id=utterance_id,
                session_id=session_id,
                project_slug=classification.project_slug,
                intent_type=classification.intent_type.value,
            )
            intent_ids.append(routed_intent.intent_id)

            # Create task for parallel processing
            task = asyncio.create_task(
                router.process_intent(routed_intent),
                name=f"dispatch_process_{routed_intent.intent_id[:8]}"
            )
            intent_tasks.append((routed_intent.intent_id, task))

        logger.info(f"[TEST] Dispatched {len(intent_ids)} intents for parallel processing")

        # Broadcast results via SSE in background
        broadcaster = get_broadcaster()

        async def stream_results():
            """Process intents and stream results to SSE."""
            for intent_id, task in intent_tasks:
                try:
                    result = await task

                    # Broadcast result_created so canvas reloads topics
                    if broadcaster and surface_id:
                        await broadcaster.broadcast(
                            SSEEvent(
                                event_type="result_created",
                                target_surface_id=surface_id,
                                data={
                                    "intent_id": intent_id,
                                    "topic_id": result.get("topic_id"),
                                    "summary": result.get("summary"),
                                    "urgency": result.get("urgency"),
                                }
                            )
                        )
                except Exception as e:
                    logger.error(f"[TEST] Intent processing failed: {e}")

        # Start background processing
        asyncio.create_task(stream_results())

        return DispatchResponse(
            success=True,
            message=f"Dispatched {len(intent_ids)} intents for parallel processing",
            data={
                "utterance_id": utterance_id,
                "session_id": session_id,
                "intent_count": len(intent_ids),
                "intent_ids": intent_ids,
                "status": "dispatched",
                "utterance_confirmation": request.utterance[:100] + (
                    "..." if len(request.utterance) > 100 else ""
                ),
            },
        )

    except Exception as e:
        logger.error(f"[TEST] Dispatch error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Dispatch error: {str(e)}"},
        )
