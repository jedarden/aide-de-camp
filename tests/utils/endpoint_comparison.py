"""
Endpoint Comparison Utilities - Helper functions for comparing /dispatch and /test endpoints.

This module provides utilities for sending identical requests to both the main /dispatch
endpoint and the test /test/intent-classify endpoint, then collecting and comparing
their responses for validation purposes.

Usage:
    from tests.utils.endpoint_comparison import send_to_both_endpoints, compare_endpoint_responses

    # Send to both endpoints
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance="how are the pods doing",
        session_id="test-session-123",
        surface_id="test-surface-456"
    )

    # Compare the results
    comparison = compare_endpoint_responses(dispatch_result, test_result)
    if not comparison["match"]:
        print(f"Differences found: {comparison['differences']}")
"""
import asyncio
import logging
from typing import Dict, Any, Tuple, Optional, List
from httpx import AsyncClient, ASGITransport, Response as HTTPXResponse
from datetime import datetime

logger = logging.getLogger(__name__)


# Default test session and surface IDs
DEFAULT_TEST_SESSION_ID = "endpoint-comparison-test"
DEFAULT_TEST_SURFACE_ID = "endpoint-comparison-surface"


class EndpointResult:
    """
    Structured result from an endpoint call.

    Attributes:
        success: Whether the call succeeded (HTTP 2xx)
        status_code: HTTP status code
        data: Response JSON data (if successful)
        error: Error message (if failed)
        endpoint_name: Name of the endpoint called
        timestamp: When the response was received
    """

    def __init__(
        self,
        success: bool,
        status_code: int,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        endpoint_name: str = "",
    ):
        self.success = success
        self.status_code = status_code
        self.data = data or {}
        self.error = error
        self.endpoint_name = endpoint_name
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for easy serialization."""
        return {
            "success": self.success,
            "status_code": self.status_code,
            "data": self.data,
            "error": self.error,
            "endpoint_name": self.endpoint_name,
            "timestamp": self.timestamp,
        }


async def send_to_test_intent_classify(
    utterance: str,
    client: AsyncClient,
) -> EndpointResult:
    """
    Send a request to the /test/intent-classify endpoint.

    Args:
        utterance: The utterance text to classify
        client: HTTPX async client for making requests

    Returns:
        EndpointResult with the response data or error information
    """
    endpoint_name = "/test/intent-classify"

    try:
        response = await client.post(
            "/api/v1/test/intent-classify",
            json={"utterance": utterance},
        )

        if response.status_code == 200:
            return EndpointResult(
                success=True,
                status_code=response.status_code,
                data=response.json(),
                endpoint_name=endpoint_name,
            )
        else:
            return EndpointResult(
                success=False,
                status_code=response.status_code,
                error=f"HTTP {response.status_code}: {response.text}",
                endpoint_name=endpoint_name,
            )

    except Exception as e:
        logger.error(f"Error calling {endpoint_name}: {e}")
        return EndpointResult(
            success=False,
            status_code=0,
            error=str(e),
            endpoint_name=endpoint_name,
        )


async def send_to_dispatch(
    utterance: str,
    session_id: str,
    surface_id: str,
    client: AsyncClient,
) -> EndpointResult:
    """
    Send a request to the /dispatch endpoint.

    Args:
        utterance: The utterance text to dispatch
        session_id: Session ID for the dispatch
        surface_id: Surface ID for SSE targeting
        client: HTTPX async client for making requests

    Returns:
        EndpointResult with the response data or error information
    """
    endpoint_name = "/dispatch"

    try:
        response = await client.post(
            "/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "surface_id": surface_id,
            },
        )

        if response.status_code == 200:
            return EndpointResult(
                success=True,
                status_code=response.status_code,
                data=response.json(),
                endpoint_name=endpoint_name,
            )
        else:
            return EndpointResult(
                success=False,
                status_code=response.status_code,
                error=f"HTTP {response.status_code}: {response.text}",
                endpoint_name=endpoint_name,
            )

    except Exception as e:
        logger.error(f"Error calling {endpoint_name}: {e}")
        return EndpointResult(
            success=False,
            status_code=0,
            error=str(e),
            endpoint_name=endpoint_name,
        )


async def send_to_both_endpoints(
    utterance: str,
    session_id: str = DEFAULT_TEST_SESSION_ID,
    surface_id: str = DEFAULT_TEST_SURFACE_ID,
    app=None,
) -> Tuple[EndpointResult, EndpointResult]:
    """
    Send identical utterance requests to both /dispatch and /test/intent-classify endpoints.

    This helper function sends the same utterance to both endpoints and returns
    structured results for comparison. The /test/intent-classify endpoint only
    requires the utterance, while /dispatch requires session_id and surface_id.

    Args:
        utterance: The utterance text to send to both endpoints
        session_id: Session ID for /dispatch endpoint (default: auto-generated)
        surface_id: Surface ID for /dispatch endpoint (default: auto-generated)
        app: FastAPI app instance (if None, will import from src.main)

    Returns:
        Tuple of (dispatch_result, test_result) as EndpointResult objects

    Example:
        >>> dispatch_result, test_result = await send_to_both_endpoints(
        ...     utterance="how are the pods doing",
        ...     session_id="test-session-123",
        ...     surface_id="test-surface-456"
        ... )
        >>> print(dispatch_result.success, test_result.success)
        True True
    """
    # Import app if not provided
    if app is None:
        from src.main import app
    else:
        app = app

    # Create HTTPX transport for FastAPI app
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Send requests concurrently for efficiency
        dispatch_task = send_to_dispatch(utterance, session_id, surface_id, client)
        test_task = send_to_test_intent_classify(utterance, client)

        dispatch_result, test_result = await asyncio.gather(
            dispatch_task, test_task
        )

        logger.info(
            f"Sent '{utterance[:50]}...' to both endpoints: "
            f"dispatch={dispatch_result.success}, test={test_result.success}"
        )

        return dispatch_result, test_result


def extract_classifications_from_test_result(test_result: EndpointResult) -> List[Dict[str, Any]]:
    """
    Extract classifications from a /test/intent-classify endpoint result.

    Args:
        test_result: EndpointResult from /test/intent-classify

    Returns:
        List of classification dictionaries
    """
    if not test_result.success or not test_result.data:
        return []

    return test_result.data.get("classifications", [])


def extract_classifications_from_dispatch_result(
    dispatch_result: EndpointResult,
    store=None,
) -> List[Dict[str, Any]]:
    """
    Extract classifications from a /dispatch endpoint result.

    Since /dispatch returns intent_ids but not the full classifications,
    we need to query the database to get the actual intent records.

    Args:
        dispatch_result: EndpointResult from /dispatch
        store: Session store instance (if None, will create a new one)

    Returns:
        List of classification dictionaries extracted from stored intents
    """
    import asyncio
    import aiosqlite
    from src.session.store import get_store

    if not dispatch_result.success or not dispatch_result.data:
        return []

    # Get the utterance_id from the dispatch response
    utterance_id = dispatch_result.data.get("utterance_id")
    if not utterance_id:
        logger.warning("No utterance_id in dispatch result")
        return []

    # Get the session store
    if store is None:
        store = get_store()

    # Query the intents for this utterance
    try:
        # Run the async database query
        async def get_intents():
            db_path = store.db_path
            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute(
                    """SELECT id, intent_type, project_slug, session_id, utterance_id
                       FROM intents
                       WHERE utterance_id = ?""",
                    (utterance_id,)
                )
                rows = await cursor.fetchall()
                return [
                    {
                        "intent_id": row[0],
                        "intent_type": row[1],
                        "project_slug": row[2],
                        "session_id": row[3],
                        "utterance_id": row[4],
                    }
                    for row in rows
                ]

        # Run the async function
        intents = asyncio.get_event_loop().run_until_complete(get_intents())
        return intents

    except Exception as e:
        logger.error(f"Error extracting classifications from dispatch result: {e}")
        return []


def compare_classifications(
    test_classifications: List[Dict[str, Any]],
    dispatch_intents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compare classification results between /test/intent-classify and /dispatch.

    Args:
        test_classifications: Classifications from /test/intent-classify endpoint
        dispatch_intents: Intent records extracted from database after /dispatch

    Returns:
        Dictionary with comparison results:
        {
            "match": bool,  # True if all classifications match
            "differences": list,  # List of difference descriptions
            "test_count": int,  # Number of test classifications
            "dispatch_count": int,  # Number of dispatch intents
        }
    """
    result = {
        "match": True,
        "differences": [],
        "test_count": len(test_classifications),
        "dispatch_count": len(dispatch_intents),
    }

    # Check count match
    if len(test_classifications) != len(dispatch_intents):
        result["match"] = False
        result["differences"].append({
            "field": "count",
            "test_value": len(test_classifications),
            "dispatch_value": len(dispatch_intents),
            "message": (
                f"Different number of intents: "
                f"test={len(test_classifications)}, dispatch={len(dispatch_intents)}"
            )
        })
        # Can't compare further if counts don't match
        return result

    # Compare each classification/intent pair
    for i, (test_cls, dispatch_intent) in enumerate(zip(test_classifications, dispatch_intents)):
        # Compare intent_type
        test_intent_type = test_cls.get("intent_type")
        dispatch_intent_type = dispatch_intent.get("intent_type")
        if test_intent_type != dispatch_intent_type:
            result["match"] = False
            result["differences"].append({
                "field": "intent_type",
                "index": i,
                "test_value": test_intent_type,
                "dispatch_value": dispatch_intent_type,
                "message": (
                    f"Intent {i}: intent_type mismatch - "
                    f"test={test_intent_type}, dispatch={dispatch_intent_type}"
                )
            })

        # Compare project_slug
        test_project = test_cls.get("project_slug")
        dispatch_project = dispatch_intent.get("project_slug")
        if test_project != dispatch_project:
            result["match"] = False
            result["differences"].append({
                "field": "project_slug",
                "index": i,
                "test_value": test_project,
                "dispatch_value": dispatch_project,
                "message": (
                    f"Intent {i}: project_slug mismatch - "
                    f"test={test_project}, dispatch={dispatch_project}"
                )
            })

    return result


def compare_endpoint_responses(
    dispatch_result: EndpointResult,
    test_result: EndpointResult,
    store=None,
) -> Dict[str, Any]:
    """
    Compare responses from both /dispatch and /test/intent-classify endpoints.

    This is a high-level comparison that checks:
    1. Both endpoints succeeded
    2. Both endpoints returned the same number of intents
    3. Intent types match between endpoints

    Args:
        dispatch_result: EndpointResult from /dispatch
        test_result: EndpointResult from /test/intent-classify
        store: Optional session store for database queries

    Returns:
        Dictionary with comparison results
    """
    comparison = {
        "dispatch_success": dispatch_result.success,
        "test_success": test_result.success,
        "match": False,
        "differences": [],
        "dispatch_status": dispatch_result.status_code,
        "test_status": test_result.status_code,
    }

    # Both must succeed
    if not dispatch_result.success or not test_result.success:
        comparison["differences"].append({
            "field": "success",
            "message": (
                f"One or both endpoints failed: "
                f"dispatch={dispatch_result.success}, test={test_result.success}"
            )
        })
        if dispatch_result.error:
            comparison["differences"].append({
                "field": "dispatch_error",
                "message": dispatch_result.error
            })
        if test_result.error:
            comparison["differences"].append({
                "field": "test_error",
                "message": test_result.error
            })
        return comparison

    # Extract classifications from both results
    test_classifications = extract_classifications_from_test_result(test_result)
    dispatch_intents = extract_classifications_from_dispatch_result(dispatch_result, store)

    # Compare classifications
    classification_comparison = compare_classifications(test_classifications, dispatch_intents)

    comparison.update({
        "match": classification_comparison["match"],
        "test_count": classification_comparison["test_count"],
        "dispatch_count": classification_comparison["dispatch_count"],
        "differences": comparison["differences"] + classification_comparison["differences"],
    })

    return comparison


async def compare_endpoints_for_utterance(
    utterance: str,
    session_id: str = DEFAULT_TEST_SESSION_ID,
    surface_id: str = DEFAULT_TEST_SURFACE_ID,
    app=None,
) -> Dict[str, Any]:
    """
    Complete comparison workflow: send to both endpoints and compare results.

    This is a convenience function that combines send_to_both_endpoints and
    compare_endpoint_responses for a one-shot comparison.

    Args:
        utterance: The utterance to test
        session_id: Session ID for /dispatch endpoint
        surface_id: Surface ID for /dispatch endpoint
        app: FastAPI app instance

    Returns:
        Dictionary with complete comparison results

    Example:
        >>> result = await compare_endpoints_for_utterance("how are the pods doing")
        >>> print(result["match"], result["differences"])
        True []
    """
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id=session_id,
        surface_id=surface_id,
        app=app,
    )

    comparison = compare_endpoint_responses(dispatch_result, test_result)

    # Add utterance to result for context
    comparison["utterance"] = utterance
    comparison["timestamp"] = datetime.utcnow().isoformat()

    return comparison


def format_comparison_report(comparison: Dict[str, Any]) -> str:
    """
    Format a comparison result into a human-readable report.

    Args:
        comparison: Comparison result dictionary from compare_endpoint_responses

    Returns:
        Formatted string report
    """
    lines = [
        "=" * 60,
        "Endpoint Comparison Report",
        "=" * 60,
        f"Utterance: {comparison.get('utterance', 'N/A')}",
        f"Timestamp: {comparison.get('timestamp', 'N/A')}",
        "",
        f"Dispatch Success: {comparison.get('dispatch_success', False)}",
        f"Test Success: {comparison.get('test_success', False)}",
        f"Overall Match: {comparison.get('match', False)}",
        "",
        f"Intent Counts: test={comparison.get('test_count', 0)}, "
        f"dispatch={comparison.get('dispatch_count', 0)}",
        "",
    ]

    if comparison.get("differences"):
        lines.append("Differences:")
        for diff in comparison["differences"]:
            lines.append(f"  - {diff.get('field', 'unknown')}: {diff.get('message', 'No message')}")
    else:
        lines.append("✅ No differences found - endpoints returned identical results")

    lines.append("=" * 60)

    return "\n".join(lines)
