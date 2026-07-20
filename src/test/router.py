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
from pydantic import BaseModel, Field

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

    store = get_store()
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

    store = get_store()
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
        classifications = await router.classify_utterance(
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
    from datetime import datetime, timedelta

    import aiosqlite

    from ..session.store import get_store

    logger.info(f"[TEST] Creating test topic: {request.label}")

    try:
        # Get session store
        store = get_store()

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
            created_ts = int(
                (datetime.utcnow() - timedelta(seconds=request.staleness_seconds)).timestamp()
            )
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
