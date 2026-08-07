"""
Test suite for endpoint comparison utilities.

Verifies that the endpoint comparison helper functions work correctly:
- send_to_both_endpoints() sends to both endpoints and returns results
- Error handling works for both endpoints
- Comparison functions produce correct results
"""
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport

from tests.helpers.endpoint_comparison import (
    send_to_both_endpoints,
    compare_classification_counts,
    format_comparison_summary,
    send_and_compare,
    RequestValidationError,
    DispatchEndpointError,
    TestEndpointError,
)


@pytest.mark.asyncio
async def test_send_to_both_endpoints_basic():
    """Test basic functionality of send_to_both_endpoints."""
    from src.main import app

    dispatch_result, test_result = await send_to_both_endpoints(
        utterance="how are the pods doing",
        session_id="test-session-basic",
        app=app,
    )

    # Verify dispatch result structure
    assert dispatch_result is not None
    assert "utterance_id" in dispatch_result
    assert "intent_count" in dispatch_result
    assert "intent_ids" in dispatch_result
    assert "session_id" in dispatch_result
    assert dispatch_result["session_id"] == "test-session-basic"

    # Verify test result structure
    assert test_result is not None
    assert "classifications" in test_result
    assert "utterance" in test_result
    assert isinstance(test_result["classifications"], list)

    print("✅ send_to_both_endpoints basic test passed")


@pytest.mark.asyncio
async def test_send_to_both_endpoints_error_handling_empty_utterance():
    """Test that empty utterance raises RequestValidationError."""
    from src.main import app

    with pytest.raises(RequestValidationError) as exc_info:
        await send_to_both_endpoints(
            utterance="",
            app=app,
        )

    assert "non-empty string" in str(exc_info.value)
    print("✅ Empty utterance validation test passed")


@pytest.mark.asyncio
async def test_send_to_both_endpoints_error_handling_whitespace_only():
    """Test that whitespace-only utterance raises RequestValidationError."""
    from src.main import app

    with pytest.raises(RequestValidationError) as exc_info:
        await send_to_both_endpoints(
            utterance="   \n\t  ",
            app=app,
        )

    assert "non-empty string" in str(exc_info.value)
    print("✅ Whitespace-only utterance validation test passed")


@pytest.mark.asyncio
async def test_send_to_both_endpoints_auto_generates_ids():
    """Test that session_id and surface_id are auto-generated if not provided."""
    from src.main import app

    dispatch_result, test_result = await send_to_both_endpoints(
        utterance="check the logs",
        app=app,
    )

    # Verify IDs were generated
    assert dispatch_result["session_id"].startswith("test-session-")
    print("✅ Auto-generated IDs test passed")


@pytest.mark.asyncio
async def test_send_to_both_endpoints_with_client():
    """Test that a provided client is used and not closed."""
    from src.main import app

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    try:
        dispatch_result, test_result = await send_to_both_endpoints(
            utterance="what's the weather",
            session_id="test-client-reuse",
            client=client,
        )

        assert dispatch_result is not None
        assert test_result is not None

        # Client should still be usable
        assert client.is_closed is False

        print("✅ Client reuse test passed")
    finally:
        await client.aclose()


def test_compare_classification_counts_match():
    """Test compare_classification_counts with matching counts."""
    dispatch_result = {"intent_count": 2}
    test_result = {"classifications": [{}, {}]}

    result = compare_classification_counts(dispatch_result, test_result)

    assert result["match"] is True
    assert result["dispatch_count"] == 2
    assert result["test_count"] == 2
    assert result["difference"] is None
    print("✅ Count comparison match test passed")


def test_compare_classification_counts_mismatch():
    """Test compare_classification_counts with mismatched counts."""
    dispatch_result = {"intent_count": 3}
    test_result = {"classifications": [{}, {}]}

    result = compare_classification_counts(dispatch_result, test_result)

    assert result["match"] is False
    assert result["dispatch_count"] == 3
    assert result["test_count"] == 2
    assert result["difference"] == 1
    print("✅ Count comparison mismatch test passed")


def test_format_comparison_summary():
    """Test format_comparison_summary produces readable output."""
    dispatch_result = {
        "utterance": "test utterance",
        "session_id": "test-123",
        "intent_count": 2,
        "intent_ids": ["id1", "id2"],
        "message": "Dispatched 2 intents"
    }
    test_result = {
        "utterance": "test utterance",
        "classifications": [
            {"intent_type": "status"},
            {"intent_type": "lookup"}
        ],
        "message": "Classified into 2 intents"
    }
    count_comparison = {
        "match": True,
        "dispatch_count": 2,
        "test_count": 2,
        "difference": None
    }

    summary = format_comparison_summary(
        dispatch_result,
        test_result,
        count_comparison,
        intent_comparison=None
    )

    assert "ENDPOINT COMPARISON SUMMARY" in summary
    assert "test utterance" in summary
    assert "test-123" in summary
    assert "✅ Count Match" in summary
    print("✅ Summary formatting test passed")


@pytest.mark.asyncio
async def test_send_and_compare_convenience():
    """Test the convenience function send_and_compare."""
    from src.main import app

    result = await send_and_compare(
        utterance="check the pipeline status",
        session_id="test-convenience",
        app=app,
        compare_intents=False,  # Skip DB query for this test
    )

    # Verify result structure
    assert "dispatch_result" in result
    assert "test_result" in result
    assert "count_comparison" in result
    assert "summary" in result

    # Verify dispatch_result
    assert result["dispatch_result"]["intent_count"] >= 0

    # Verify test_result
    assert isinstance(result["test_result"]["classifications"], list)

    # Verify comparison
    assert "match" in result["count_comparison"]

    # Verify summary contains key sections
    assert "ENDPOINT COMPARISON SUMMARY" in result["summary"]
    assert "DISPATCH ENDPOINT" in result["summary"]
    assert "TEST ENDPOINT" in result["summary"]

    print("✅ send_and_compare convenience function test passed")


@pytest.mark.asyncio
async def test_multiple_utterances_comparison():
    """Test comparison with multiple different utterances."""
    from src.main import app

    test_utterances = [
        "how are the pods doing",
        "check the options pipeline status",
        "find the recent logs for nap-api",
        "what is the weather",
    ]

    for utterance in test_utterances:
        dispatch_result, test_result = await send_to_both_endpoints(
            utterance=utterance,
            session_id=f"test-multi-{hash(utterance) % 1000}",
            app=app,
        )

        # Both should succeed
        assert dispatch_result is not None
        assert test_result is not None
        assert isinstance(dispatch_result["intent_count"], int)
        assert isinstance(test_result["classifications"], list)

    print(f"✅ Multiple utterances comparison test passed ({len(test_utterances)} utterances)")


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "-s"])
