"""Unit tests for the test-session API client."""

import httpx
import pytest

from src.test.utilities import SessionCreationError
from src.test.utilities import TestSessionClient as SessionClient


async def _client_for(handler) -> tuple[SessionClient, httpx.AsyncClient]:
    """Build a session client backed by an in-memory HTTP transport."""
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    session_client = SessionClient()
    session_client.client = http_client
    return session_client, http_client


@pytest.mark.asyncio
async def test_create_session_posts_predictable_id_and_returns_schema():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "session_id": "test-session-123",
                "created_at": "2026-08-10T16:00:00Z",
            },
            request=request,
        )

    client, http_client = await _client_for(handler)
    try:
        result = await client.create_session("test-session-123")
    finally:
        await http_client.aclose()

    assert result == {
        "session_id": "test-session-123",
        "created_at": "2026-08-10T16:00:00Z",
    }
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "http://localhost:8000/api/v1/sessions"
    assert requests[0].read() == b'{"session_id":"test-session-123"}'


@pytest.mark.asyncio
async def test_create_session_generates_id_when_omitted():
    async def handler(request: httpx.Request) -> httpx.Response:
        request_payload = request.content.decode()
        assert request_payload.startswith('{"session_id":"test-inject-')
        return httpx.Response(
            200,
            json={
                "session_id": "generated-by-server",
                "created_at": "2026-08-10T16:00:00Z",
            },
            request=request,
        )

    client, http_client = await _client_for(handler)
    try:
        result = await client.create_session()
    finally:
        await http_client.aclose()

    assert result["session_id"] == "generated-by-server"
    assert result["created_at"].endswith("Z")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, message",
    [
        ({"session_id": "only-id"}, "created_at"),
        ({"created_at": "2026-08-10T16:00:00Z"}, "session_id"),
        ({"session_id": "id", "created_at": None}, "created_at"),
    ],
)
async def test_create_session_rejects_invalid_response(payload, message):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    client, http_client = await _client_for(handler)
    try:
        with pytest.raises(SessionCreationError, match=message):
            await client.create_session("test-session-123")
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_create_session_wraps_http_failures():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"}, request=request)

    client, http_client = await _client_for(handler)
    try:
        with pytest.raises(SessionCreationError, match="HTTP 503"):
            await client.create_session("test-session-123")
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_create_session_requires_open_client():
    with pytest.raises(SessionCreationError, match="async context manager"):
        await SessionClient().create_session("test-session-123")
