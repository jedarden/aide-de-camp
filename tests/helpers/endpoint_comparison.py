"""
Endpoint Comparison Test Utilities

Provides helper functions for sending identical requests to both /test/intent-classify
and /dispatch endpoints and collecting their responses for comparison.

Usage:
    from tests.helpers.endpoint_comparison import send_to_both_endpoints

    dispatch_result, test_result = await send_to_both_endpoints(
        utterance="how are the pods doing",
        session_id="test-session"
    )

    # Compare results
    if dispatch_result["intent_count"] != len(test_result["classifications"]):
        print(f"Mismatch: dispatch returned {dispatch_result['intent_count']} intents, "
              f"test returned {len(test_result['classifications'])} classifications")
"""
import asyncio
import uuid
from typing import Dict, Any, Tuple, Optional, List
from httpx import AsyncClient, ASGITransport, HTTPError
import logging

logger = logging.getLogger(__name__)


class EndpointComparisonError(Exception):
    """Base exception for endpoint comparison errors."""
    pass


class DispatchEndpointError(EndpointComparisonError):
    """Exception raised when /dispatch endpoint fails."""
    pass


class TestEndpointError(EndpointComparisonError):
    """Exception raised when /test/intent-classify endpoint fails."""
    pass


class RequestValidationError(EndpointComparisonError):
    """Exception raised when request validation fails."""
    pass


async def send_to_both_endpoints(
    utterance: str,
    session_id: Optional[str] = None,
    surface_id: Optional[str] = None,
    app: Any = None,
    client: Optional[AsyncClient] = None,
    timeout: float = 30.0,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Send identical utterance to both /dispatch and /test/intent-classify endpoints.

    This helper function sends the same utterance to both endpoints and returns
    their responses for comparison. Both calls are made sequentially to ensure
    identical input conditions.

    Args:
        utterance: The utterance text to send to both endpoints
        session_id: Optional session ID (generated if not provided)
        surface_id: Optional surface ID for SSE targeting (generated if not provided)
        app: FastAPI app instance (required if client not provided)
        client: Optional httpx AsyncClient (created from app if not provided)
        timeout: Request timeout in seconds (default 30.0)

    Returns:
        Tuple of (dispatch_result, test_result) where:
        - dispatch_result: Response from /dispatch endpoint
        - test_result: Response from /test/intent-classify endpoint

    Raises:
        RequestValidationError: If utterance is invalid
        DispatchEndpointError: If /dispatch call fails
        TestEndpointError: If /test/intent-classify call fails
        EndpointComparisonError: For general comparison errors

    Example:
        from src.main import app
        from tests.helpers.endpoint_comparison import send_to_both_endpoints

        dispatch_result, test_result = await send_to_both_endpoints(
            utterance="how are the pods doing",
            session_id="test-session",
            app=app
        )

        # Access results
        print(f"Dispatch: {dispatch_result['intent_count']} intents")
        print(f"Test: {len(test_result['classifications'])} classifications")
    """
    # Validate utterance
    if not utterance or not utterance.strip():
        raise RequestValidationError("Utterance must be a non-empty string")

    # Generate IDs if not provided
    if session_id is None:
        session_id = f"test-session-{uuid.uuid4().hex[:12]}"
    if surface_id is None:
        surface_id = f"test-surface-{uuid.uuid4().hex[:12]}"

    # Create client if not provided
    should_close_client = False
    if client is None:
        if app is None:
            raise RequestValidationError(
                "Either 'app' or 'client' must be provided"
            )
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test", timeout=timeout)
        should_close_client = True

    try:
        # Call /test/intent-classify endpoint first (lighter, no side effects)
        test_result = await _call_test_endpoint(client, utterance, timeout)

        # Call /dispatch endpoint second (creates database records)
        dispatch_result = await _call_dispatch_endpoint(
            client, utterance, session_id, surface_id, timeout
        )

        return dispatch_result, test_result

    finally:
        # Close client if we created it
        if should_close_client:
            await client.aclose()


async def _call_test_endpoint(
    client: AsyncClient,
    utterance: str,
    timeout: float
) -> Dict[str, Any]:
    """
    Call the /test/intent-classify endpoint.

    Args:
        client: httpx AsyncClient
        utterance: Utterance text to classify
        timeout: Request timeout in seconds

    Returns:
        Response JSON as dictionary

    Raises:
        TestEndpointError: If endpoint call fails
    """
    try:
        response = await client.post(
            "/api/v1/test/intent-classify",
            json={"utterance": utterance},
            timeout=timeout
        )

        if response.status_code != 200:
            raise TestEndpointError(
                f"Test endpoint returned status {response.status_code}: {response.text}"
            )

        data = response.json()
        logger.info(f"[TEST ENDPOINT] Classified '{utterance[:50]}...' into "
                    f"{len(data.get('classifications', []))} intent(s)")

        return data

    except HTTPError as e:
        raise TestEndpointError(f"HTTP error calling test endpoint: {e}")
    except Exception as e:
        raise TestEndpointError(f"Error calling test endpoint: {e}")


async def _call_dispatch_endpoint(
    client: AsyncClient,
    utterance: str,
    session_id: str,
    surface_id: str,
    timeout: float
) -> Dict[str, Any]:
    """
    Call the /dispatch endpoint.

    Args:
        client: httpx AsyncClient
        utterance: Utterance text to dispatch
        session_id: Session ID for dispatch
        surface_id: Surface ID for SSE targeting
        timeout: Request timeout in seconds

    Returns:
        Response JSON as dictionary

    Raises:
        DispatchEndpointError: If endpoint call fails
    """
    try:
        response = await client.post(
            "/dispatch",
            json={
                "utterance": utterance,
                "session_id": session_id,
                "surface_id": surface_id,
            },
            timeout=timeout
        )

        if response.status_code != 200:
            raise DispatchEndpointError(
                f"Dispatch endpoint returned status {response.status_code}: {response.text}"
            )

        data = response.json()
        logger.info(f"[DISPATCH ENDPOINT] Dispatched '{utterance[:50]}...' -> "
                    f"{data.get('intent_count', 0)} intent(s)")

        return data

    except HTTPError as e:
        raise DispatchEndpointError(f"HTTP error calling dispatch endpoint: {e}")
    except Exception as e:
        raise DispatchEndpointError(f"Error calling dispatch endpoint: {e}")


def compare_classification_counts(
    dispatch_result: Dict[str, Any],
    test_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compare the number of intents/classifications returned by each endpoint.

    Args:
        dispatch_result: Response from /dispatch endpoint
        test_result: Response from /test/intent-classify endpoint

    Returns:
        Dict with comparison results:
        {
            "match": bool,
            "dispatch_count": int,
            "test_count": int,
            "difference": int or None
        }
    """
    dispatch_count = dispatch_result.get("intent_count", 0)
    test_count = len(test_result.get("classifications", []))

    return {
        "match": dispatch_count == test_count,
        "dispatch_count": dispatch_count,
        "test_count": test_count,
        "difference": dispatch_count - test_count if dispatch_count != test_count else None
    }


def compare_intent_types(
    dispatch_result: Dict[str, Any],
    test_result: Dict[str, Any],
    store: Any = None
) -> Dict[str, Any]:
    """
    Compare intent types between endpoints by querying stored intents.

    This requires querying the database to retrieve the intent types that
    /dispatch stored, since the dispatch response only returns intent IDs.

    Args:
        dispatch_result: Response from /dispatch endpoint
        test_result: Response from /test/intent-classify endpoint
        store: Optional session store instance (will be created if not provided)

    Returns:
        Dict with comparison results:
        {
            "match": bool,
            "dispatch_intent_types": List[str],
            "test_intent_types": List[str],
            "differences": List[str]
        }
    """
    import aiosqlite
    from src.session.store import get_store

    # Get test intent types from response
    test_classifications = test_result.get("classifications", [])
    test_intent_types = [cls.get("intent_type") for cls in test_classifications]

    # Get dispatch intent types from database
    dispatch_intent_types = []
    utterance_id = dispatch_result.get("utterance_id")

    if utterance_id:
        # Use provided store or get default
        store_instance = store or get_store()
        db_path = store_instance.db_path

        # Query stored intents
        async def _get_intent_types():
            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute(
                    "SELECT intent_type FROM intents WHERE utterance_id = ?",
                    (utterance_id,)
                )
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

        # Run the async query
        try:
            dispatch_intent_types = asyncio.run(_get_intent_types())
        except Exception as e:
            logger.error(f"Error querying intent types from database: {e}")
            dispatch_intent_types = []

    # Compare
    differences = []
    if test_intent_types != dispatch_intent_types:
        differences.append(
            f"Intent types differ: test={test_intent_types}, dispatch={dispatch_intent_types}"
        )

    return {
        "match": len(differences) == 0,
        "dispatch_intent_types": dispatch_intent_types,
        "test_intent_types": test_intent_types,
        "differences": differences
    }


def format_comparison_summary(
    dispatch_result: Dict[str, Any],
    test_result: Dict[str, Any],
    count_comparison: Dict[str, Any],
    intent_comparison: Optional[Dict[str, Any]] = None
) -> str:
    """
    Format a human-readable summary of the endpoint comparison.

    Args:
        dispatch_result: Response from /dispatch endpoint
        test_result: Response from /test/intent-classify endpoint
        count_comparison: Result from compare_classification_counts()
        intent_comparison: Optional result from compare_intent_types()

    Returns:
        Formatted summary string
    """
    lines = [
        "=" * 70,
        "ENDPOINT COMPARISON SUMMARY",
        "=" * 70,
        "",
        f"Utterance: {dispatch_result.get('utterance', 'N/A')}",
        f"Session ID: {dispatch_result.get('session_id', 'N/A')}",
        "",
        "DISPATCH ENDPOINT",
        "-" * 70,
        f"Intent Count: {dispatch_result.get('intent_count', 'N/A')}",
        f"Intent IDs: {dispatch_result.get('intent_ids', [])}",
        f"Message: {dispatch_result.get('message', 'N/A')}",
        "",
        "TEST ENDPOINT (/test/intent-classify)",
        "-" * 70,
        f"Classification Count: {len(test_result.get('classifications', []))}",
        f"Message: {test_result.get('message', 'N/A')}",
        "",
        "COMPARISON RESULTS",
        "-" * 70,
    ]

    # Add count comparison
    if count_comparison["match"]:
        lines.append(f"✅ Count Match: {count_comparison['dispatch_count']} intents/classifications")
    else:
        lines.append(f"❌ Count Mismatch:")
        lines.append(f"   Dispatch: {count_comparison['dispatch_count']}")
        lines.append(f"   Test: {count_comparison['test_count']}")
        lines.append(f"   Difference: {count_comparison['difference']}")

    # Add intent type comparison if available
    if intent_comparison:
        if intent_comparison["match"]:
            lines.append(f"✅ Intent Types Match: {intent_comparison['test_intent_types']}")
        else:
            lines.append(f"❌ Intent Types Differ:")
            lines.append(f"   Dispatch: {intent_comparison['dispatch_intent_types']}")
            lines.append(f"   Test: {intent_comparison['test_intent_types']}")
            for diff in intent_comparison.get("differences", []):
                lines.append(f"   {diff}")

    lines.append("=" * 70)

    return "\n".join(lines)


async def send_and_compare(
    utterance: str,
    session_id: Optional[str] = None,
    surface_id: Optional[str] = None,
    app: Any = None,
    client: Optional[AsyncClient] = None,
    timeout: float = 30.0,
    compare_intents: bool = True,
) -> Dict[str, Any]:
    """
    Send to both endpoints and return a comprehensive comparison.

    This is a convenience function that combines send_to_both_endpoints
    with the comparison utilities.

    Args:
        utterance: The utterance text to send
        session_id: Optional session ID
        surface_id: Optional surface ID
        app: FastAPI app instance
        client: Optional httpx AsyncClient
        timeout: Request timeout in seconds
        compare_intents: Whether to compare intent types (requires DB query)

    Returns:
        Dict with complete comparison results:
        {
            "dispatch_result": {...},
            "test_result": {...},
            "count_comparison": {...},
            "intent_comparison": {...}  # if compare_intents=True
            "summary": "..."  # formatted summary string
        }
    """
    # Send to both endpoints
    dispatch_result, test_result = await send_to_both_endpoints(
        utterance=utterance,
        session_id=session_id,
        surface_id=surface_id,
        app=app,
        client=client,
        timeout=timeout,
    )

    # Compare counts
    count_comparison = compare_classification_counts(dispatch_result, test_result)

    # Compare intent types if requested
    intent_comparison = None
    if compare_intents:
        try:
            intent_comparison = compare_intent_types(dispatch_result, test_result)
        except Exception as e:
            logger.warning(f"Failed to compare intent types: {e}")
            intent_comparison = {
                "match": False,
                "error": str(e)
            }

    # Format summary
    summary = format_comparison_summary(
        dispatch_result,
        test_result,
        count_comparison,
        intent_comparison
    )

    return {
        "dispatch_result": dispatch_result,
        "test_result": test_result,
        "count_comparison": count_comparison,
        "intent_comparison": intent_comparison,
        "summary": summary
    }
