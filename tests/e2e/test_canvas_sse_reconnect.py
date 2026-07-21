"""
Canvas SSE reconnection — wire-level verification (bead adc-2vto).

This is the server-side half of the reconnection AC. It proves that when a
canvas ``EventSource`` stream *drops* and a *new* one reconnects to the same
surface, live delivery and re-render still work — using the REAL production
pipeline (the broadcaster singleton the ``/api/v1/sse`` endpoint wraps, the
real ``GET /api/v1/sessions/{id}/topics`` endpoint ``loadTopics()`` calls, and
the real ``src/canvas/canvas.js`` renderer), with no browser and no live server.

What "drop" and "reconnect" map to here:

- **drop** — the browser ``EventSource`` closes (network blip, ``onerror``, or a
  server ``disconnect`` event). On the server, the ``StreamingResponse`` that
  wraps ``broadcaster.event_generator(conn)`` is cancelled, whose ``finally``
  calls ``unregister(conn)``. We model that by cancelling the drain task
  consuming ``event_generator`` (which runs the same ``finally`` → unregister).
- **reconnect** — the browser opens a NEW ``EventSource`` to the same surface.
  We model that with a second ``b.register(surface_id, ...)`` + a fresh drain.
  ``connectSSE()`` in src/canvas/index.html assigns exactly such a fresh
  ``new EventSource(url)`` on reconnect, and its ``onopen`` calls
  ``loadTopics()`` — the re-fetch we exercise through GET /topics here.

The client-side ``EventSource`` state machine itself (onopen / onerror /
addEventListener → loadTopics) is covered headlessly in
``tests/test_canvas_eventsource_reconnect.py`` via a mock-EventSource harness
that runs the real inline canvas script.

All hermetic: FastAPI runs in-process via httpx's ASGITransport against an
isolated tmp SQLite DB (never ``data/session.db``), and SSE delivery is
exercised through the broadcaster singleton the real dispatch path uses.
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
from tests.e2e.canvas_render import node_available, parse_sse_stream, render_cards
from tests.e2e.inject import TestDataInjector

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive canvas DOM runner"
)


# --- fixtures -----------------------------------------------------------------


@pytest.fixture
async def inj(tmp_path, monkeypatch):
    """In-process TestDataInjector against an ISOLATED tmp DB.

    Mirrors tests/e2e/test_canvas_sse_render.py: points the store at a tmp file
    (never ``data/session.db``), wires ``main._topic_manager`` so GET /topics
    works without the app lifespan, and restores the real singletons + env on
    teardown.
    """
    tmp_db = tmp_path / "test-canvas-sse-reconnect.db"
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

    Idempotently started. Not stopped on teardown — other code may hold the
    singleton (mirrors test_persistence_sse_verification.py)."""
    b = get_broadcaster()
    if not getattr(b, "_running", False):
        await b.start()
    return b


# --- connection drain helpers -------------------------------------------------


async def _drain(broadcaster, conn, sink: list, *, duration: float = 2.0):
    """Consume ``event_generator(conn)`` (the SSE stream the endpoint serves)
    for up to ``duration`` seconds, appending parsed events to ``sink``.

    Returns the task; the caller cancels it to model an EventSource drop (the
    generator's ``finally`` unregisters the connection, exactly as a cancelled
    StreamingResponse would). The initial ``connected`` event is included so
    callers can confirm a stream actually opened.
    """

    async def run():
        try:
            async for wire in broadcaster.event_generator(conn):
                for etype, data in parse_sse_stream(wire):
                    sink.append((etype, data))
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(run())
    # Let the generator emit its initial 'connected' event + settle.
    await asyncio.sleep(0)
    return task


def _events_of(sink, etype: str) -> list[tuple[str, dict]]:
    return [e for e in sink if e[0] == etype]


# === drop → reconnect delivers new results ====================================


class TestReconnectDeliversNewResults:
    """The core AC: after a canvas stream drops and reconnects, new results
    arrive on the *reconnected* stream and render."""

    async def test_dropped_stream_receives_nothing_then_reconnect_gets_new_result(self):
        """A result broadcast during the outage goes nowhere (no live stream);
        after reconnect, a new result lands on the new stream."""
        b = await _started_broadcaster()
        session_id = "sess-reconnect-1"
        surface_id = "surf-reconnect-1"

        conn_a = b.register(surface_id, session_id, "canvas")
        sink_a: list[tuple[str, dict]] = []
        task_a = await _drain(b, conn_a, sink_a)

        try:
            # --- DROP the EventSource (cancel the stream → unregister) ------
            task_a.cancel()
            with contextlib_suppress():
                await task_a
            # conn_a is now unregistered (event_generator finally ran).
            assert conn_a.connection_id not in b.connections

            # Broadcast WHILE disconnected: nobody is listening.
            sent = await broadcast_result(
                {"result_id": "r-dropped", "summary": "during outage",
                 "topic_id": "t-x"},
                session_id=session_id, target_surface_id=surface_id,
            )
            assert sent == 0
            assert _events_of(sink_a, "result_created") == []

            # --- RECONNECT: a fresh EventSource to the same surface ---------
            conn_b = b.register(surface_id, session_id, "canvas")
            sink_b: list[tuple[str, dict]] = []
            task_b = await _drain(b, conn_b, sink_b)
            try:
                # New result AFTER reconnect → delivered to the new stream.
                sent = await broadcast_result(
                    {"result_id": "r-after", "summary": "after reconnect",
                     "topic_id": "t-y"},
                    session_id=session_id, target_surface_id=surface_id,
                )
                assert sent == 1

                # Drain settles: the event lands on B, never on A.
                await asyncio.sleep(0.05)
                rc_a = _events_of(sink_a, "result_created")
                rc_b = _events_of(sink_b, "result_created")
                assert rc_a == []                       # dropped stream stayed dead
                assert len(rc_b) == 1                   # reconnected stream got it
                assert rc_b[0][1]["result_id"] == "r-after"
            finally:
                task_b.cancel()
                with contextlib_suppress():
                    await task_b
        finally:
            # Defensive cleanup in case a cancel above raced.
            b.unregister(conn_a.connection_id)

    async def test_old_stream_does_not_receive_post_reconnect_events(self):
        """After reconnect, events targeted at the surface are NOT also queued
        for the dead connection — there is no lingering ghost stream."""
        b = await _started_broadcaster()
        conn_a = b.register("surf-old", "sess-old", "canvas")
        sink_a: list[tuple[str, dict]] = []
        task_a = await _drain(b, conn_a, sink_a)
        try:
            task_a.cancel()
            with contextlib_suppress():
                await task_a
        finally:
            b.unregister(conn_a.connection_id)

        # Reconnect + send.
        conn_b = b.register("surf-old", "sess-old", "canvas")
        sink_b: list[tuple[str, dict]] = []
        task_b = await _drain(b, conn_b, sink_b)
        try:
            await b.broadcast(SSEEvent(
                event_type=EventType.TOPIC_UPDATED,
                data={"topic_id": "t-9", "label": "updated post-reconnect"},
                target_session_id="sess-old", target_surface_id="surf-old",
            ))
            await asyncio.sleep(0.05)
            assert _events_of(sink_a, "topic_updated") == []
            assert len(_events_of(sink_b, "topic_updated")) == 1
        finally:
            task_b.cancel()
            with contextlib_suppress():
                await task_b


# === multiple drop/reconnect cycles converge ==================================


class TestRepeatedReconnect:
    """A canvas that flaps (drop → reconnect → drop → reconnect) still ends up
    live and receiving on its final connection."""

    async def test_third_connection_is_the_live_one(self):
        b = await _started_broadcaster()
        surface_id, session_id = "surf-flap", "sess-flap"

        sinks: list[list] = []
        conns = []
        try:
            for _ in range(3):
                conn = b.register(surface_id, session_id, "canvas")
                conns.append(conn)
                sink: list[tuple[str, dict]] = []
                sinks.append(sink)
                task = await _drain(b, conn, sink)
                # Drop immediately (except after the last connect).
                task.cancel()
                with contextlib_suppress():
                    await task

            # Final reconnect stays up.
            conn_final = b.register(surface_id, session_id, "canvas")
            conns.append(conn_final)
            sink_final: list[tuple[str, dict]] = []
            task_final = await _drain(b, conn_final, sink_final)

            try:
                sent = await broadcast_result(
                    {"result_id": "r-final", "summary": "after flapping",
                     "topic_id": "t-z"},
                    session_id=session_id, target_surface_id=surface_id,
                )
                assert sent == 1
                await asyncio.sleep(0.05)
                # Only the final, still-live stream received it.
                assert all(_events_of(s, "result_created") == [] for s in sinks)
                rc = _events_of(sink_final, "result_created")
                assert len(rc) == 1 and rc[0][1]["result_id"] == "r-final"
            finally:
                task_final.cancel()
                with contextlib_suppress():
                    await task_final
        finally:
            for c in conns:
                b.unregister(c.connection_id)


# === canvas re-renders after reconnect (loadTopics path) ======================


class TestReconnectReRenders:
    """On reconnect, the canvas's ``onopen`` calls ``loadTopics()``, which
    re-fetches GET /topics and re-renders. We model the re-fetch through the
    real endpoint + real canvas.js and assert a result that arrived during the
    outage is now visible in the rendered cards after reconnect."""

    async def test_result_that_arrived_during_outage_renders_after_reconnect(self, inj):
        injector, _ = inj
        session_id = "sess-rerender"
        surface_id = "surf-rerender"
        b = await _started_broadcaster()

        # Baseline: one topic exists before anything drops.
        await injector.create_session(session_id)
        await injector.inject_topic(session_id, label="Baseline",
                                    summary="1 pod", urgency="normal")

        conn_a = b.register(surface_id, session_id, "canvas")
        sink_a: list[tuple[str, dict]] = []
        task_a = await _drain(b, conn_a, sink_a)
        try:
            task_a.cancel()
            with contextlib_suppress():
                await task_a
        finally:
            b.unregister(conn_a.connection_id)

        # While disconnected, a NEW result lands in the store (the pipeline
        # keeps working even though no canvas is watching).
        await injector.inject_topic(session_id, label="New Result",
                                    summary="build #7 green", urgency="high")

        # Reconnect. onopen → loadTopics() re-fetches and re-renders.
        conn_b = b.register(surface_id, session_id, "canvas")
        sink_b: list[tuple[str, dict]] = []
        task_b = await _drain(b, conn_b, sink_b)
        try:
            # The reconnected stream's result_created (if any) is irrelevant to
            # re-render; what matters is GET /topics now reflects the new card.
            cards = await injector.get_topics(session_id)
            labels = {c["topic"]["label"] for c in cards}
            assert {"Baseline", "New Result"} <= labels

            # And the REAL canvas.js renders the new card (post-reconnect view).
            rendered = render_cards(cards)
            target = next(c for c in cards if c["topic"]["label"] == "New Result")
            html = next(r["outerHTML"] for r in rendered
                        if r["dataset"].get("topicId") == target["topic"]["id"])
            assert "topic-card" in html
            assert "New Result" in html
            assert "build #7 green" in html
            assert "urgency-badge high" in html
        finally:
            task_b.cancel()
            with contextlib_suppress():
                await task_b


# --- tiny compat shim ---------------------------------------------------------
# ``contextlib.suppress`` wrapper so the cancel/await idiom reads cleanly at the
# call sites above without a second import line each time.

def contextlib_suppress():
    from contextlib import suppress
    return suppress(asyncio.CancelledError)
