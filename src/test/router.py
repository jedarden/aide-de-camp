"""
Test Router - FastAPI router for test endpoints.

Provides test endpoints that bypass the Web Speech API and directly
inject test utterances into the dispatch pipeline for end-to-end testing.

Also provides TTS/narration testing endpoints for capturing and verifying
narration events without actual audio output.
"""
from logging import getLogger

from fastapi import APIRouter
from pydantic import BaseModel, Field


logger = getLogger(__name__)

# FastAPI router instance for test endpoints
router = APIRouter()

# Import narration endpoints to register them
from .narration import (
    create_narration_session,
    inject_narration_event,
    inject_tts_capture,
    get_narration_session,
    verify_narration,
    delete_narration_session,
    list_narration_sessions,
    cleanup_all_sessions,
)


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
    from ..session.store import get_store
    from datetime import datetime, timedelta
    import uuid

    logger.info(f"[TEST] Creating test topic: {request.label}")

    try:
        # Get session store
        store = get_store()

        # Create or get session
        session = await store.get_session(request.session_id)
        if not session:
            await store.create_session()
            logger.info(f"[TEST] Created session: {request.session_id}")

        # Create topic
        topic_id = str(uuid.uuid4())

        # Calculate created_at based on staleness_seconds
        created_at = datetime.utcnow() - timedelta(seconds=request.staleness_seconds)

        # Create topic directly in database
        import aiosqlite
        async with aiosqlite.connect(store.db_path) as db:
            await db.execute(
                "INSERT INTO topics (id, session_id, label, type, project_slugs, created_at, last_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (topic_id, request.session_id, request.label, request.type, '["test-project"]', int(created_at.timestamp()), int(created_at.timestamp()))
            )

            # Create result for the topic
            result_id = str(uuid.uuid4())

            await db.execute(
                "INSERT INTO results (id, topic_id, summary, data, urgency, created_at, session_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (result_id, topic_id, request.summary, '{"test": true, "data": "test data"}', request.urgency, int(created_at.timestamp()), request.session_id)
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
