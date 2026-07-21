"""
Canvas SSE → loadTopics → render verification (bead adc-1l8w).

Locks down the part of the dispatch pipeline the *canvas* depends on, end to
end, without a browser or a live server:

1. **Canvas receives SSE events** — a canvas surface registered exactly as
   ``/api/v1/sse`` registers it receives ``result_created`` / ``topic_updated``
   events through the SAME SSE stream generator (``event_generator``) the
   endpoint serves, formatted as the ``text/event-stream`` wire text the
   browser ``EventSource`` parses. These are the two event types the canvas
   wires to ``loadTopics()`` in src/canvas/index.html — so receiving them is the
   trigger that makes the canvas re-fetch and re-render topics.

2. **loadTopics() fetches + renders** — after a topic is injected, the endpoint
   ``loadTopics()`` calls (``GET /api/v1/sessions/{id}/topics``) returns cards
   that the REAL canvas.js renders correctly headlessly.

3. **Cards appear after a test dispatch** — injecting a topic via the
   deterministic, no-LLM "test dispatch" path and rendering the cards the canvas
   would reload produces a card carrying the injected label + summary.

All hermetic: the FastAPI app runs in-process via httpx's ASGITransport against
an isolated tmp SQLite DB (never production data/session.db), and SSE delivery
is exercised through the broadcaster singleton the real dispatch path uses.

Note on the SSE wire test: the ``/api/v1/sse`` StreamingResponse can't be
streamed over httpx's ASGITransport (it buffers the whole body, and an SSE
stream blocks forever on ``queue.get()``). So we drive
``broadcaster.event_generator`` directly — that is the exact generator the
endpoint wraps (``async for event_data in broadcaster.event_generator(conn):
yield event_data``), so the wire text produced here is byte-for-byte what the
endpoint would emit to a real EventSource.
"""
import asyncio

import pytest

import src.main as main_mod
import src.session.store as store_mod
from src.sse.broadcaster import (
    EventType,
    SSEEvent,
    broadcast_result,
    get_broadcaster,
)
from src.topic.model import TopicManager
from tests.e2e.canvas_render import node_available, parse_sse_stream, render_card, render_cards
from tests.e2e.inject import TestDataInjector

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- fixtures -----------------------------------------------------------------


@pytest.fixture
async def inj(tmp_path, monkeypatch):
    """In-process TestDataInjector against an ISOLATED tmp DB.

    Mirrors tests/e2e/test_inject.py: points the store at a tmp file (never
    ``data/session.db``), wires ``main._topic_manager`` so GET /topics works
    without the app lifespan (ASGITransport skips lifespan startup), and
    restores the real singletons + env on teardown.
    """
    tmp_db = tmp_path / "test-canvas-sse.db"
    monkeypatch.setenv("ADC_DB_PATH", str(tmp_db))

    saved_store = store_mod._store
    saved_main_store = main_mod._store
    saved_tm = main_mod._topic_manager

    store_mod._store = None
    main_mod._store = None
    main_mod._topic_manager = None

    store = store_mod.get_store()
    await store.initialize()
    main_mod._topic_manager = TopicManager(store)

    async with TestDataInjector(app=main_mod.app) as injector:
        yield injector, store

    main_mod._topic_manager = saved_tm
    main_mod._store = saved_main_store
    store_mod._store = saved_store


async def _started_broadcaster():
    """The process-wide singleton broadcaster the dispatch path broadcasts on.

    Idempotently started (avoids spawning a second cleanup task if a prior test
    or the app already started it). Not stopped on teardown — other code may
    hold the singleton (mirrors test_persistence_sse_verification.py).
    """
    b = get_broadcaster()
    if not getattr(b, "_running", False):
        await b.start()
    return b


async def _collect_until(broadcaster, conn, wanted_types, *, timeout=2.0):
    """Drain ``event_generator`` (the SSE stream the endpoint serves) until it
    has emitted all ``wanted_types`` (after the initial ``connected``), then
    return the parsed ``(event_type, data)`` pairs (excluding ``connected``)."""
    wanted = set(wanted_types)
    collected: list[tuple[str, dict]] = []

    async def drain():
        async for wire in broadcaster.event_generator(conn):
            for etype, data in parse_sse_stream(wire):
                if etype == "connected":
                    continue
                collected.append((etype, data))
                if wanted <= {e for e, _ in collected}:
                    return

    task = asyncio.create_task(drain())
    try:
        await asyncio.wait_for(task, timeout=timeout)
    except asyncio.TimeoutError:
        task.cancel()
        raise
    return collected


# --- 1. canvas receives SSE events --------------------------------------------


class TestCanvasReceivesSSEEvents:
    """The two event types the canvas wires to loadTopics() actually arrive over
    the SSE wire to a registered canvas surface."""

    async def test_result_created_event_arrives_over_sse_wire(self):
        """A result_created event is delivered to the canvas surface as parseable
        SSE wire text. (result_created → loadTopics() in index.html.)"""
        b = await _started_broadcaster()
        conn = b.register(
            surface_id="surf-rc", session_id="sess-rc", surface_type="canvas"
        )
        try:
            sent = await broadcast_result(
                {"result_id": "r-1", "summary": "3 pods running", "topic_id": "t-1"},
                session_id="sess-rc",
                target_surface_id="surf-rc",
            )
            assert sent == 1  # exactly this canvas surface received it

            events = await _collect_until(b, conn, ["result_created"])
            assert len(events) >= 1
            etype, data = events[0]
            assert etype == "result_created"
            assert data["result_id"] == "r-1"
            assert data["summary"] == "3 pods running"
            assert data["topic_id"] == "t-1"
        finally:
            b.unregister(conn.connection_id)

    async def test_result_created_not_delivered_to_other_surface(self):
        """surface_id targeting: a different canvas in the same session does not
        receive an event targeted at another surface."""
        b = await _started_broadcaster()
        target = b.register(
            surface_id="surf-a", session_id="sess-tgt", surface_type="canvas"
        )
        other = b.register(
            surface_id="surf-b", session_id="sess-tgt", surface_type="canvas"
        )
        try:
            sent = await broadcast_result(
                {"result_id": "r-2", "summary": "only surf-a"},
                session_id="sess-tgt",
                target_surface_id="surf-a",
            )
            assert sent == 1  # only the targeted surface

            events = await _collect_until(b, target, ["result_created"])
            assert events[0][1]["result_id"] == "r-2"

            # surf-b must remain empty (no event queued).
            with pytest.raises(asyncio.TimeoutError):
                await _collect_until(b, other, ["result_created"], timeout=0.3)
        finally:
            b.unregister(target.connection_id)
            b.unregister(other.connection_id)

    async def test_topic_updated_event_arrives_over_sse_wire(self):
        """topic_updated — the other event the canvas wires to loadTopics()."""
        b = await _started_broadcaster()
        conn = b.register(
            surface_id="surf-tu", session_id="sess-tu", surface_type="canvas"
        )
        try:
            sent = await b.broadcast(
                SSEEvent(
                    event_type=EventType.TOPIC_UPDATED,
                    data={"topic_id": "t-9", "label": "Updated Topic"},
                    target_session_id="sess-tu",
                    target_surface_id="surf-tu",
                )
            )
            assert sent == 1

            events = await _collect_until(b, conn, ["topic_updated"])
            etype, data = events[0]
            assert etype == "topic_updated"
            assert data["topic_id"] == "t-9"
            assert data["label"] == "Updated Topic"
        finally:
            b.unregister(conn.connection_id)


# --- 2. loadTopics() fetches + renders ----------------------------------------


class TestLoadTopicsRenders:
    async def test_loadtopics_endpoint_returns_renderable_card(self, inj):
        """GET /api/v1/sessions/{id}/topics (what loadTopics() calls) returns
        cards the REAL canvas.js renders into a .topic-card with the label."""
        injector, _ = inj
        await injector.inject_session_with_topics(
            "test-inject-render",
            [
                {
                    "label": "Pod Status",
                    "topic_type": "project",
                    "summary": "3 pods running",
                }
            ],
        )
        cards = await injector.get_topics("test-inject-render")
        assert len(cards) == 1

        card = cards[0]
        # The exact shape loadTopics()/createTopicCard() consume.
        assert card["topic"]["label"] == "Pod Status"
        assert card["latest_result"]["summary"] == "3 pods running"
        assert "seconds" in card["staleness"]

        rendered = render_cards(cards)
        html = rendered[0]["outerHTML"]
        assert "topic-card" in html
        assert "Pod Status" in html
        assert "3 pods running" in html


# --- 3. cards appear after a test dispatch ------------------------------------


class TestCardAppearsAfterTestDispatch:
    async def test_card_renders_after_test_dispatch(self, inj):
        """End-to-end: inject a topic via the deterministic no-LLM 'test
        dispatch' path, reload the cards loadTopics() would fetch, and assert
        the rendered card carries the injected label + summary + urgency badge
        — i.e. the card 'appears in the canvas UI'."""
        injector, _ = inj
        await injector.create_session("test-inject-e2e")
        await injector.inject_topic(
            "test-inject-e2e",
            label="Build Status",
            summary="build #42 green",
            urgency="high",
        )

        cards = await injector.get_topics("test-inject-e2e")
        assert any(c["topic"]["label"] == "Build Status" for c in cards)

        target = next(c for c in cards if c["topic"]["label"] == "Build Status")
        rendered = render_card(target)
        html = rendered["outerHTML"]
        assert "topic-card" in html
        assert "Build Status" in html
        assert "build #42 green" in html
        assert "urgency-badge high" in html

    async def test_multiple_dispatched_topics_all_render(self, inj):
        """Several injected topics each render their own card."""
        injector, _ = inj
        await injector.inject_session_with_topics(
            "test-inject-multi-render",
            [
                {"label": "Pods", "summary": "3 running"},
                {"label": "Builds", "summary": "green"},
                {"label": "Weather", "summary": "rain", "topic_type": "research"},
            ],
        )
        cards = await injector.get_topics("test-inject-multi-render")
        rendered = render_cards(cards)
        labels = {c["topic"]["label"] for c in cards}
        assert {"Pods", "Builds", "Weather"} <= labels

        htmls = [r["outerHTML"] for r in rendered]
        assert any("Pods" in h and "3 running" in h for h in htmls)
        assert any("Builds" in h and "green" in h for h in htmls)
        assert any("Weather" in h and "rain" in h for h in htmls)
