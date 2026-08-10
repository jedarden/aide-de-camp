"""End-to-end tests for the dispatch, persistence, and SSE pipeline.

The tests use the real ``/dispatch`` endpoint and ``IntentRouter``. Network
fetching, LLM synthesis, and card rendering are deterministic test doubles so
that the assertions cover the application's orchestration and storage/SSE
boundaries without contacting external services.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

import src.intent.router as intent_router_module
import src.main as main_module
from src.fetch.commands import FetchCoverage, FetchResult
from src.fetch.commands import IntentType as FetchIntentType
from src.intent.router import (
    IntentClassification,
    IntentRouter,
    RoutedIntent,
)
from src.intent.router import (
    IntentType as RouterIntentType,
)
from src.render.hot_path import RenderOutcome
from src.session.store import SessionStore
from src.sse.broadcaster import EventType, SSEBroadcaster, SSEEvent
from src.synthesize.strand import SynthesizeResult, Urgency
from src.topic.model import TopicManager


@pytest.fixture
async def pipeline(tmp_path, monkeypatch):
    """Create an isolated application pipeline for each test."""
    store = SessionStore(tmp_path / "session.db")
    await store.initialize()
    session_id = await store.create_session()
    surface_id = f"surface-{uuid4()}"

    broadcaster = SSEBroadcaster()
    connection = broadcaster.register(
        surface_id=surface_id,
        session_id=session_id,
        surface_type="canvas",
    )
    router = IntentRouter(store)

    # /dispatch launches stream_results() in the background, so expose the
    # isolated services through the same module globals used by the endpoint.
    monkeypatch.setattr(main_module, "_broadcaster", broadcaster)
    monkeypatch.setattr(main_module, "_topic_manager", TopicManager(store))
    monkeypatch.setattr(main_module, "get_store", AsyncMock(return_value=store))
    monkeypatch.setattr(main_module, "get_intent_router", lambda _store: router)

    # The router's result path still uses the historical synchronous call form
    # for get_store(), while the public store accessor is async. Keep this
    # compatibility shim local to the test; it prevents the test from touching
    # the production database while exercising the complete result path.
    monkeypatch.setattr(intent_router_module, "get_store", lambda: store)

    renderer = MagicMock()

    def render_result(**kwargs):
        return RenderOutcome(
            rendered_html=(
                f'<article data-result-id="{kwargs["result_id"]}">'
                f'{kwargs["summary"]}</article>'
            ),
            component_id="status-card",
            card_fallback=False,
            layout_bucket="default",
        )

    renderer.render.side_effect = render_result
    monkeypatch.setattr(intent_router_module, "get_renderer", lambda: renderer)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://test",
    ) as client:
        yield SimpleNamespace(
            client=client,
            connection=connection,
            broadcaster=broadcaster,
            router=router,
            session_id=session_id,
            store=store,
            surface_id=surface_id,
        )

    await store.close()


def _fetch_result(intent_id: str) -> FetchResult:
    """Return a successful, external-service-free fetch result."""
    return FetchResult(
        intent_id=intent_id,
        intent_type=FetchIntentType.STATUS,
        sources={},
        coverage=FetchCoverage(
            total_sources=0,
            succeeded=[],
            timed_out=[],
            failed=[],
            skipped=[],
        ),
        total_duration_ms=1,
    )


def _classification(fragment: str) -> IntentClassification:
    return IntentClassification(
        intent_type=RouterIntentType.STATUS,
        project_slug=None,
        urgency="normal",
        utterance_fragment=fragment,
    )


def _synthesized_result(intent_id: str, index: int = 0) -> SynthesizeResult:
    return SynthesizeResult(
        intent_id=intent_id,
        summary=f"Deployment {index} is healthy",
        data={"index": index, "status": "running", "replicas": index + 1},
        urgency=Urgency.NORMAL,
        coverage=["test-fetch"],
        caveats=[],
    )


async def _next_event(connection, timeout: float = 3.0) -> SSEEvent:
    event = await asyncio.wait_for(connection.queue.get(), timeout=timeout)
    assert isinstance(event, SSEEvent)
    return event


async def _dispatch(client, session_id: str, surface_id: str, utterance: str):
    response = await client.post(
        "/dispatch",
        json={
            "utterance": utterance,
            "session_id": session_id,
            "surface_id": surface_id,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    return body


async def _wait_for_result(store, intent_id: str, timeout: float = 3.0) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        results = await store.get_results_for_intent(intent_id)
        if results:
            return results[0]
        await asyncio.sleep(0.01)
    raise AssertionError(f"No persisted result for intent {intent_id}")


async def _wait_for_await(mock, timeout: float = 3.0) -> None:
    """Wait until a background task has awaited a mock."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if mock.await_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Background task did not await the expected mock")


class TestDispatchPersistenceAndSSE:
    async def test_dispatch_persists_result_before_broadcast(self, pipeline, monkeypatch):
        """A dispatch result is stored and then delivered as result_created."""
        classification = _classification("deployment status")
        pipeline.router.classify_utterance = AsyncMock(
            return_value=([classification], {"json_parse_ms": 0})
        )

        persistence_finished = asyncio.Event()
        original_create_result = pipeline.store.create_result
        original_broadcast = pipeline.broadcaster.broadcast

        async def tracked_create_result(*args, **kwargs):
            result_id = await original_create_result(*args, **kwargs)
            persistence_finished.set()
            return result_id

        async def broadcast_only_after_persistence(event):
            assert persistence_finished.is_set()
            return await original_broadcast(event)

        monkeypatch.setattr(pipeline.store, "create_result", tracked_create_result)
        monkeypatch.setattr(
            pipeline.broadcaster,
            "broadcast",
            broadcast_only_after_persistence,
        )

        async def fake_fetch(request, _on_progress):
            assert request.intent_type == FetchIntentType.STATUS
            return _fetch_result(request.intent_id)

        async def fake_synthesize(request):
            return _synthesized_result(request.intent_id)

        monkeypatch.setattr(intent_router_module, "execute_fetch", fake_fetch)
        monkeypatch.setattr(intent_router_module, "synthesize_intent", fake_synthesize)

        body = await _dispatch(
            pipeline.client,
            pipeline.session_id,
            pipeline.surface_id,
            "Check deployment status",
        )
        intent_id = body["data"]["intent_ids"][0]
        stored = await _wait_for_result(pipeline.store, intent_id)
        event = await _next_event(pipeline.connection)

        assert event.event_type == EventType.RESULT_CREATED
        assert event.target_surface_id == pipeline.surface_id
        assert event.data["intent_id"] == intent_id
        assert event.data["topic_id"] == stored["topic_id"]
        assert event.data["summary"] == stored["summary"] == "Deployment 0 is healthy"
        assert event.data["urgency"] == stored["urgency"] == "normal"
        assert event.rendered_html is not None
        assert json.loads(stored["data"]) == {
            "index": 0,
            "status": "running",
            "replicas": 1,
        }

    async def test_result_created_event_is_followed_by_canvas_topic_data(
        self, pipeline, monkeypatch
    ):
        """Canvas topic loading sees the result identified by the SSE topic."""
        classification = _classification("service health")
        pipeline.router.classify_utterance = AsyncMock(
            return_value=([classification], {"json_parse_ms": 0})
        )

        async def fake_fetch(request, _on_progress):
            return _fetch_result(request.intent_id)

        async def fake_synthesize(request):
            return _synthesized_result(request.intent_id, index=7)

        monkeypatch.setattr(intent_router_module, "execute_fetch", fake_fetch)
        monkeypatch.setattr(intent_router_module, "synthesize_intent", fake_synthesize)

        body = await _dispatch(
            pipeline.client,
            pipeline.session_id,
            pipeline.surface_id,
            "Check service health",
        )
        intent_id = body["data"]["intent_ids"][0]
        event = await _next_event(pipeline.connection)
        stored = await _wait_for_result(pipeline.store, intent_id)

        # This is the HTTP data load performed by canvas loadTopics() after the
        # result_created event. It must expose the same topic/result pair.
        response = await pipeline.client.get(
            f"/api/v1/sessions/{pipeline.session_id}/topics"
        )
        assert response.status_code == 200, response.text
        cards = response.json()["cards"]
        card = next(
            card for card in cards if card["topic"]["id"] == event.data["topic_id"]
        )

        assert card["latest_result"]["id"] == stored["id"]
        assert card["latest_result"]["summary"] == "Deployment 7 is healthy"
        assert card["latest_result"]["data"] == {
            "index": 7,
            "status": "running",
            "replicas": 8,
        }
        assert card["topic"]["id"] == stored["topic_id"]

    async def test_parallel_dispatch_results_remain_isolated(self, pipeline, monkeypatch):
        """Concurrent intent tasks persist and broadcast their own payloads."""
        routed_intents = [
            RoutedIntent(
                intent_id=f"intent-{index}-{uuid4()}",
                classification=_classification(f"service {index}"),
                session_id=pipeline.session_id,
                utterance=f"service {index}",
            )
            for index in range(5)
        ]
        pipeline.router.route_utterance = AsyncMock(return_value=routed_intents)
        index_by_intent = {item.intent_id: index for index, item in enumerate(routed_intents)}

        async def fake_fetch(request, _on_progress):
            index = index_by_intent[request.intent_id]
            await asyncio.sleep((4 - index) * 0.005)
            return _fetch_result(request.intent_id)

        async def fake_synthesize(request):
            index = index_by_intent[request.intent_id]
            await asyncio.sleep(index * 0.003)
            return _synthesized_result(request.intent_id, index=index)

        monkeypatch.setattr(intent_router_module, "execute_fetch", fake_fetch)
        monkeypatch.setattr(intent_router_module, "synthesize_intent", fake_synthesize)

        body = await _dispatch(
            pipeline.client,
            pipeline.session_id,
            pipeline.surface_id,
            "Check all services",
        )
        assert body["data"]["intent_ids"] == [item.intent_id for item in routed_intents]

        events = [await _next_event(pipeline.connection) for _ in routed_intents]
        events_by_intent = {event.data["intent_id"]: event for event in events}
        assert set(events_by_intent) == set(index_by_intent)

        stored_by_intent = {}
        for intent_id, index in index_by_intent.items():
            results = await pipeline.store.get_results_for_intent(intent_id)
            assert len(results) == 1
            stored = results[0]
            stored_by_intent[intent_id] = stored
            assert stored["summary"] == f"Deployment {index} is healthy"
            assert json.loads(stored["data"])["index"] == index
            assert events_by_intent[intent_id].data["topic_id"] == stored["topic_id"]

        assert len({result["id"] for result in stored_by_intent.values()}) == 5
        topics = await pipeline.store.get_active_topics(pipeline.session_id)
        assert {topic["id"] for topic in topics} == {
            result["topic_id"] for result in stored_by_intent.values()
        }

    async def test_sse_failure_does_not_block_result_persistence(self, pipeline, monkeypatch):
        """A failed result broadcast leaves the already-persisted result readable."""
        classification = _classification("deployment status after disconnect")
        pipeline.router.classify_utterance = AsyncMock(
            return_value=([classification], {"json_parse_ms": 0})
        )

        async def fake_fetch(request, _on_progress):
            return _fetch_result(request.intent_id)

        async def fake_synthesize(request):
            return _synthesized_result(request.intent_id, index=9)

        monkeypatch.setattr(intent_router_module, "execute_fetch", fake_fetch)
        monkeypatch.setattr(intent_router_module, "synthesize_intent", fake_synthesize)
        failed_broadcast = AsyncMock(side_effect=RuntimeError("SSE socket closed"))
        monkeypatch.setattr(pipeline.broadcaster, "broadcast", failed_broadcast)

        body = await _dispatch(
            pipeline.client,
            pipeline.session_id,
            pipeline.surface_id,
            "Check deployment status after disconnect",
        )
        intent_id = body["data"]["intent_ids"][0]
        stored = await _wait_for_result(pipeline.store, intent_id)
        await _wait_for_await(failed_broadcast)

        assert failed_broadcast.await_count == 1
        assert stored["summary"] == "Deployment 9 is healthy"
        assert json.loads(stored["data"])["replicas"] == 10
        assert pipeline.connection.queue.empty()
