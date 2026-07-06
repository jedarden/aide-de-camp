"""
Test Router - FastAPI router for test endpoints.

Provides test endpoints that bypass the Web Speech API and directly
inject test utterances into the dispatch pipeline for end-to-end testing.
"""
from logging import getLogger

from fastapi import APIRouter
from pydantic import BaseModel, Field


logger = getLogger(__name__)

# FastAPI router instance for test endpoints
router = APIRouter()

# Router is ready for endpoint registration
# Endpoints will be registered in dispatch.py and imported here


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
