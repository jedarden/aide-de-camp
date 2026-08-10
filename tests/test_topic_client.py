"""Unit tests for the async test-topic injection client."""

import httpx
import pytest

from src.test.topic_injection import (
    IntentRoutingError,
    SynthesisError,
    TestTopicClient,
    TopicCreationError,
)


async def _client_for(handler):
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    topic_client = TestTopicClient(client=http_client)
    return topic_client, http_client


@pytest.mark.asyncio
async def test_create_topic_posts_required_dispatch_payload_and_returns_result():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"topic_id": "topic-1", "result": {"summary": "healthy"}},
            request=request,
        )

    client, http_client = await _client_for(handler)
    try:
        result = await client.create_topic("check status", "session-1", "surface-1")
    finally:
        await http_client.aclose()

    assert result == {"topic_id": "topic-1", "result": {"summary": "healthy"}}
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "http://localhost:8000/dispatch"
    assert requests[0].read() == (
        b'{"utterance":"check status","session_id":"session-1",'
        b'"surface_id":"surface-1"}'
    )


@pytest.mark.asyncio
async def test_create_topics_waits_for_each_request_and_preserves_order():
    utterances = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = httpx.Request(
            request.method, request.url, content=request.content
        ).read()
        utterances.append(httpx.Response(200, content=payload).json()["utterance"])
        topic_number = len(utterances)
        return httpx.Response(
            200,
            json={"topic_id": f"topic-{topic_number}", "result": topic_number},
            request=request,
        )

    client, http_client = await _client_for(handler)
    try:
        results = await client.create_topics(
            ["first", "second", "third"],
            session_id="session-1",
            surface_id="surface-1",
        )
    finally:
        await http_client.aclose()

    assert utterances == ["first", "second", "third"]
    assert [result["topic_id"] for result in results] == [
        "topic-1",
        "topic-2",
        "topic-3",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_text", "error_type"),
    [
        ("intent routing unavailable", IntentRoutingError),
        ("synthesis failed", SynthesisError),
    ],
)
async def test_create_topic_classifies_dispatch_errors(error_text, error_type):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": error_text}, request=request)

    client, http_client = await _client_for(handler)
    try:
        with pytest.raises(error_type, match=error_text):
            await client.create_topic("check status", "session-1", "surface-1")
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_create_topic_rejects_missing_response_fields():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"topic_id": "topic-1"}, request=request)

    client, http_client = await _client_for(handler)
    try:
        with pytest.raises(TopicCreationError, match="synthesis result"):
            await client.create_topic("check status", "session-1", "surface-1")
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_create_topic_requires_open_client():
    with pytest.raises(TopicCreationError, match="async context manager"):
        await TestTopicClient().create_topic("check status", "session-1", "surface-1")


@pytest.mark.asyncio
async def test_create_topic_resolves_background_dispatch_from_session_cards():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "message": "accepted",
                    "data": {"intent_ids": ["intent-1"]},
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "cards": [
                    {
                        "topic": {"id": "topic-1"},
                        "latest_result": {"id": "result-1", "summary": "healthy"},
                    }
                ]
            },
            request=request,
        )

    client, http_client = await _client_for(handler)
    try:
        result = await client.create_topic("check status", "session-1", "surface-1")
    finally:
        await http_client.aclose()

    assert result["topic_id"] == "topic-1"
    assert result["result"]["id"] == "result-1"
    assert [request.method for request in requests] == ["POST", "GET"]
