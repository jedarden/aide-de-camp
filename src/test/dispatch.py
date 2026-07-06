"""
Test Dispatch Module - Bypass Web Speech API for testing.

Provides POST /api/v1/test/dispatch endpoint that accepts pre-defined
test utterances directly into the dispatch pipeline.
"""
import asyncio
import uuid
from logging import getLogger
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, field_validator

from ..intent.router import get_router
from ..session.store import get_store
from ..sse.broadcaster import get_broadcaster, SSEEvent
from .router import router


logger = getLogger(__name__)


class TestDispatchRequest(BaseModel):
    """Request model for test dispatch."""
    utterance: str
    session_id: Optional[str] = None
    surface_id: Optional[str] = None
    wait_for_results: bool = False  # If True, wait for results and return them
    timeout_seconds: int = 30  # Max time to wait for results

    @field_validator('utterance')
    @classmethod
    def utterance_must_be_non_empty(cls, v: str) -> str:
        """Validate that utterance is a non-empty string."""
        stripped = v.strip()
        if not stripped:
            raise ValueError('utterance must be a non-empty string')
        return stripped


class TestDispatchResponse(BaseModel):
    """Response model for test dispatch."""
    status: str
    utterance_id: str
    session_id: str
    intent_count: int
    intent_ids: list[str]
    message: str
    results: Optional[list[dict]] = None  # Only if wait_for_results=True


async def dispatch_test_utterance(request: TestDispatchRequest) -> TestDispatchResponse:
    """
    Dispatch a test utterance directly into the pipeline.

    This bypasses the Web Speech API and WebSocket layer, injecting
    the utterance text directly into the intent router.

    Args:
        request: TestDispatchRequest with utterance and optional parameters

    Returns:
        TestDispatchResponse with dispatch confirmation and optional results
    """
    # Generate IDs
    utterance_id = str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())

    logger.info(f"[TEST] Dispatching utterance: {request.utterance[:100]}...")

    # Initialize store and router
    store = get_store()
    router = get_router(store)

    # Create session if needed
    session = await store.get_session(session_id)
    if not session:
        await store.create_session()
        logger.info(f"[TEST] Created new session: {session_id}")

    # Create utterance record
    await store.create_utterance(session_id, request.utterance, utterance_id)

    # Route the utterance
    try:
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
                name=f"test_process_{routed_intent.intent_id[:8]}"
            )
            intent_tasks.append((routed_intent.intent_id, task))

        logger.info(f"[TEST] Dispatched {len(intent_ids)} intents for processing")

        # If wait_for_results, collect and return results
        if request.wait_for_results:
            results = await _collect_results(intent_tasks, request.timeout_seconds)

            return TestDispatchResponse(
                status="completed",
                utterance_id=utterance_id,
                session_id=session_id,
                intent_count=len(intent_ids),
                intent_ids=intent_ids,
                message=f"Test dispatch completed with {len(results)} results",
                results=results,
            )
        else:
            # Start parallel processing in background and broadcast via SSE
            broadcaster = get_broadcaster()

            async def stream_results():
                """Process intents and stream results to SSE."""
                for intent_id, task in intent_tasks:
                    try:
                        result = await task

                        # Broadcast result_created so canvas reloads topics
                        if broadcaster and request.surface_id:
                            await broadcaster.broadcast(
                                SSEEvent(
                                    event_type="result_created",
                                    target_surface_id=request.surface_id,
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

            return TestDispatchResponse(
                status="dispatched",
                utterance_id=utterance_id,
                session_id=session_id,
                intent_count=len(intent_ids),
                intent_ids=intent_ids,
                message=f"Test dispatch initiated for {len(intent_ids)} intents",
            )

    except Exception as e:
        logger.error(f"[TEST] Dispatch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dispatch error: {str(e)}")


async def _collect_results(intent_tasks, timeout_seconds: int) -> list[dict]:
    """
    Collect results from intent processing tasks with timeout.

    Args:
        intent_tasks: List of (intent_id, task) tuples
        timeout_seconds: Maximum time to wait

    Returns:
        List of result dictionaries
    """
    results = []

    try:
        # Wait for all tasks with timeout
        done, pending = await asyncio.wait(
            [task for _, task in intent_tasks],
            timeout=timeout_seconds
        )

        # Cancel any pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Collect results from completed tasks
        for intent_id, task in intent_tasks:
            if task in done:
                try:
                    result = await task
                    results.append(result)
                except Exception as e:
                    logger.error(f"[TEST] Error collecting result for {intent_id}: {e}")
                    results.append({
                        "intent_id": intent_id,
                        "status": "error",
                        "error": str(e),
                    })
            else:
                results.append({
                    "intent_id": intent_id,
                    "status": "timeout",
                    "error": f"Processing timed out after {timeout_seconds}s",
                })

    except Exception as e:
        logger.error(f"[TEST] Error collecting results: {e}")
        # Return whatever we have
        return results

    return results


# Pydantic model for pre-canned test utterances
class TestUtterance(BaseModel):
    """A pre-canned test utterance."""
    name: str
    utterance: str
    expected_intent_type: Optional[str] = None
    expected_project_slug: Optional[str] = None
    description: str = ""


# Pre-canned test utterances for common scenarios
TEST_UTTERANCES = [
    TestUtterance(
        name="status_query",
        utterance="how are the pods doing",
        expected_intent_type="status",
        description="Simple status query without project context",
    ),
    TestUtterance(
        name="project_status",
        utterance="check the options pipeline status",
        expected_intent_type="status",
        expected_project_slug="options-pipeline",
        description="Status query for specific project",
    ),
    TestUtterance(
        name="action_request",
        utterance="deploy the latest version of nap-api",
        expected_intent_type="action",
        expected_project_slug="iad-native-ads",
        description="Action request to deploy a service",
    ),
    TestUtterance(
        name="lookup_request",
        utterance="find the recent logs for the nap-api container",
        expected_intent_type="lookup",
        expected_project_slug="iad-native-ads",
        description="Lookup request for logs",
    ),
    TestUtterance(
        name="brainstorm",
        utterance="let's brainstorm ways to optimize the pipeline performance",
        expected_intent_type="brainstorm",
        description="Brainstorming request",
    ),
    TestUtterance(
        name="task_profile",
        utterance="create a bead for implementing the new monitoring feature",
        expected_intent_type="task-profile",
        description="Task profile that should escalate to NEEDLE bead",
    ),
    TestUtterance(
        name="multi_intent",
        utterance="how's the pipeline and also check the ibkr mcp status",
        description="Multi-intent utterance that should split into multiple intents",
    ),
]


@router.get("/test/utterances")
async def list_test_utterances():
    """List available pre-canned test utterances."""
    return {
        "utterances": [
            {
                "name": u.name,
                "utterance": u.utterance,
                "expected_intent_type": u.expected_intent_type,
                "expected_project_slug": u.expected_project_slug,
                "description": u.description,
            }
            for u in TEST_UTTERANCES
        ]
    }


@router.post("/test/dispatch")
async def api_v1_test_dispatch(request: TestDispatchRequest) -> TestDispatchResponse:
    """
    Test dispatch endpoint - bypass Web Speech API.

    Accepts pre-defined test utterances directly into the dispatch pipeline.
    Verifies intent classification, fetch execution, result storage, SSE broadcast,
    and canvas rendering.

    Request body:
    {
        "utterance": "test query here",
        "session_id": "optional-session-id",
        "surface_id": "optional-surface-id",
        "wait_for_results": false,  // If true, waits for results and returns them
        "timeout_seconds": 30  // Max wait time if wait_for_results=true
    }

    Returns:
        {
            "status": "dispatched" | "completed",
            "utterance_id": "...",
            "session_id": "...",
            "intent_count": 2,
            "intent_ids": ["...", "..."],
            "message": "...",
            "results": [...]  // Only if wait_for_results=true
        }

    Error responses:
        400: Missing or invalid utterance text
        500: Dispatch processing error
    """
    return await dispatch_test_utterance(request)


@router.post("/test/dispatch/{utterance_name}")
async def api_v1_test_dispatch_named(
    utterance_name: str,
    wait_for_results: bool = False,
    timeout_seconds: int = 30,
) -> TestDispatchResponse:
    """
    Test dispatch using a pre-canned utterance by name.

    Path parameters:
        utterance_name: Name of the pre-canned utterance (see GET /test/utterances)

    Query parameters:
        wait_for_results: If true, wait for results before returning
        timeout_seconds: Max time to wait for results

    Returns:
        TestDispatchResponse with dispatch confirmation and optional results
    """
    # Find the named utterance
    utterance = next((u for u in TEST_UTTERANCES if u.name == utterance_name), None)

    if not utterance:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown utterance name: {utterance_name}. "
                   f"See GET /test/utterances for available names."
        )

    request = TestDispatchRequest(
        utterance=utterance.utterance,
        wait_for_results=wait_for_results,
        timeout_seconds=timeout_seconds,
    )

    return await dispatch_test_utterance(request)


@router.post("/test/run_suite")
async def api_v1_test_run_suite(
    wait_for_results: bool = True,
    timeout_seconds: int = 30,
) -> dict:
    """
    Run a test suite with all pre-canned utterances.

    Executes each test utterance sequentially and collects results.

    Query parameters:
        wait_for_results: If true, wait for results before returning
        timeout_seconds: Max time to wait for results per utterance

    Returns:
        {
            "total_tests": 7,
            "passed": 6,
            "failed": 1,
            "results": [...]
        }
    """
    results = []

    for utterance in TEST_UTTERANCES:
        logger.info(f"[TEST SUITE] Running test: {utterance.name}")

        try:
            response = await dispatch_test_utterance(
                TestDispatchRequest(
                    utterance=utterance.utterance,
                    wait_for_results=wait_for_results,
                    timeout_seconds=timeout_seconds,
                )
            )

            test_result = {
                "name": utterance.name,
                "utterance": utterance.utterance,
                "status": "passed",
                "response": {
                    "intent_count": response.intent_count,
                    "intent_ids": response.intent_ids,
                    "message": response.message,
                },
            }

            # Check if results match expectations
            if wait_for_results and response.results:
                for result in response.results:
                    intent_type = result.get("intent_type")
                    project_slug = result.get("project_slug")

                    if utterance.expected_intent_type and intent_type != utterance.expected_intent_type:
                        test_result["status"] = "failed"
                        test_result["reason"] = (
                            f"Expected intent_type '{utterance.expected_intent_type}', "
                            f"got '{intent_type}'"
                        )

                    if utterance.expected_project_slug and project_slug != utterance.expected_project_slug:
                        test_result["status"] = "failed"
                        test_result["reason"] = (
                            f"Expected project_slug '{utterance.expected_project_slug}', "
                            f"got '{project_slug}'"
                        )

            results.append(test_result)

        except Exception as e:
            logger.error(f"[TEST SUITE] Test failed: {utterance.name} - {e}")
            results.append({
                "name": utterance.name,
                "utterance": utterance.utterance,
                "status": "error",
                "error": str(e),
            })

    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] in ("failed", "error"))

    return {
        "total_tests": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }
