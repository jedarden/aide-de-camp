"""
Client-side SSE reconnection — the browser ``EventSource`` state machine
(bead adc-2vto).

The companion server-side suite ``tests/e2e/test_canvas_sse_reconnect.py`` models
an SSE drop/reconnect by cancelling the *server-side* drain task wrapping
``broadcaster.event_generator()`` — it proves the *server* still delivers to a
reconnected stream, but it never drives the browser's own ``EventSource``.

This file is the client-side half. It runs the EXACT inline app script the
browser runs (``src/canvas/index.html``'s attribute-less ``<script>`` block —
the one defining ``connectSSE()`` / ``loadTopics()`` / ``init()``) under a
mock ``EventSource`` + mock ``fetch`` + minimal DOM shim, and drives a JSON test
plan of open / error / named-event / disconnect / close / reconnect steps,
asserting on the telemetry the harness prints. That covers the reconnection AC
half that needs JavaScript execution:

- **AC "simulate SSE connection drops by closing/reconnecting EventSource"** —
  the harness fires ``onopen`` (connect), ``onerror`` (transient drop),
  ``disconnect`` (server-initiated close → ``eventSource.close()``), an explicit
  ``close``, and a native auto-``reconnect`` (the same EventSource firing
  ``onopen`` again — faithful to real browser behavior).
- **AC "canvas re-renders correctly after SSE reconnection"** — on every
  ``onopen`` (including the reconnect one) the script calls ``loadTopics()``,
  which re-fetches ``GET /topics`` and re-renders. We assert the re-fetch
  happens and the new card set appears in the rendered container.
- **AC "new results appear after reconnection"** — a ``result_created`` (or
  ``topic_updated``) event arrives mid-stream and the canvas re-renders to show
  the new card; and after a reconnect the re-fetched card set (which may include
  results that arrived during the outage) is rendered.

All hermetic: no browser (Playwright's chromium is missing ~26 FHS libs on this
NixOS host), no live server — the mock fetch answers from an in-memory card list
the plan controls, and the mock EventSource is driven deterministically.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.canvas_render import NODE, node_available

# The headless mock-EventSource harness that runs the REAL inline canvas script.
ES_RUNNER = Path(__file__).resolve().parent / "e2e" / "canvas_eventsource_runner.js"

pytestmark = pytest.mark.skipif(
    not node_available(), reason="node not on PATH — cannot drive EventSource harness"
)


# --- plan runner + builders ---------------------------------------------------


def run_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Feed a JSON test plan to the mock-EventSource harness, return its telemetry.

    Mirrors ``tests.e2e.canvas_render.render_cards``: shells out to ``node``
    with the plan on stdin and parses the single JSON telemetry object the
    harness prints on stdout. Raises if node is missing or the harness exits
    non-zero (e.g. the inline script threw under the shim).
    """
    if NODE is None:
        raise RuntimeError("node not found on PATH — cannot drive EventSource harness")
    proc = subprocess.run(
        [NODE, str(ES_RUNNER)],
        input=json.dumps(plan),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"canvas_eventsource_runner exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return json.loads(proc.stdout)


def _card(
    label: str = "Pods",
    *,
    topic_id: str = "t-1",
    topic_type: str = "project",
    summary: str = "ok",
    urgency: str = "normal",
    seconds: int = 5,
) -> dict:
    """A card dict in the shape ``GET /topics`` returns under ``.cards`` (i.e. the
    shape ``loadTopics()`` hands to ``createTopicCard()``)."""
    level = "fresh" if seconds < 600 else ("stale" if seconds < 3600 else "very-stale")
    return {
        "topic": {"id": topic_id, "label": label, "type": topic_type},
        "staleness": {"seconds": seconds, "level": level},
        "latest_result": {"summary": summary, "urgency": urgency},
    }


def _plan(
    *,
    cards: list[dict] | None = None,
    steps: list[dict] | None = None,
    session_id: str = "sess-driver",
    surface_id: str = "surf-driver",
    version: str = "9.9.9",
) -> dict:
    """A harness plan. ``cards`` is the initial ``GET /topics`` response; steps
    drive the mock EventSource (open / error / event / disconnect / close /
    reconnect / setCards)."""
    return {
        "session_id": session_id,
        "register_surface_id": surface_id,
        "openapi_version": version,
        "cards": cards or [],
        "steps": steps or [],
    }


def _last_status(t: dict) -> dict:
    return t["statuses"][-1] if t["statuses"] else {}


# === init + connect ===========================================================


class TestInitAndConnect:
    """``init()`` registers a surface and opens exactly one ``EventSource``,
    transitioning the status indicator to "connecting" — the baseline a
    reconnect test starts from."""

    def test_init_creates_exactly_one_eventsource(self):
        t = run_plan(_plan(steps=[{"action": "wait"}]))
        assert t["initCompleted"] is True
        assert t["eventSourcesCreated"] == 1

    def test_eventsource_url_carries_surface_session_and_type(self):
        """The SSE URL the canvas opens carries the registered surface_id, the
        session_id, and surface_type=canvas — the targeting the server filters on."""
        t = run_plan(_plan(
            session_id="sess-42", surface_id="surf-42",
            steps=[{"action": "wait"}],
        ))
        url = t["currentEventSourceUrl"]
        assert url.startswith("/api/v1/sse?")
        assert "surface_id=surf-42" in url
        assert "session_id=sess-42" in url
        assert "surface_type=canvas" in url

    def test_status_is_connecting_before_open(self):
        """Before the stream's onopen fires, the dot shows "connecting"."""
        t = run_plan(_plan(steps=[{"action": "wait"}]))
        assert t["statuses"] == [{"status": "connecting", "text": "Connecting..."}]


# === onopen → loadTopics → connected ==========================================


class TestOnOpenLoadsTopics:
    """``onopen`` flips the status to "Connected" and re-fetches ``GET /topics``
    (``loadTopics()``), rendering the current card set — the re-render path a
    reconnect reuses."""

    def test_open_marks_connected_and_fetches_topics_once(self):
        t = run_plan(_plan(steps=[{"action": "open"}]))
        assert t["loadTopicsCalls"] == 1
        assert _last_status(t) == {"status": "", "text": "Connected"}

    def test_initial_cards_render_on_open(self):
        """The card set present at connect time renders into the container."""
        t = run_plan(_plan(
            cards=[_card("Alpha", topic_id="t-a")],
            steps=[{"action": "open"}],
        ))
        assert t["containerCardCount"] == 1
        assert "Alpha" in t["containerHTML"]
        assert t["containerCardLabels"] == ["Alpha"]

    def test_empty_card_set_renders_empty_state(self):
        t = run_plan(_plan(cards=[], steps=[{"action": "open"}]))
        assert t["containerCardCount"] == 0
        assert "No active topics" in t["containerHTML"]


# === named live events re-render ==============================================


class TestLiveEventsReRender:
    """A ``result_created`` or ``topic_updated`` event arriving mid-stream
    triggers a ``loadTopics()`` re-fetch and re-render — new results appear
    live, without a reconnect."""

    @pytest.mark.parametrize("event_name", ["result_created", "topic_updated"])
    def test_named_event_triggers_loadtopics_and_rerender(self, event_name):
        """Start connected with one card, swap the server's card set to two, then
        deliver the named event: the canvas re-fetches and renders both."""
        t = run_plan(_plan(
            cards=[_card("Alpha", topic_id="t-a")],
            steps=[
                {"action": "open"},
                {"action": "setCards", "cards": [
                    _card("Alpha", topic_id="t-a"),
                    _card("Beta", topic_id="t-b", topic_type="research", urgency="high"),
                ]},
                {"action": "event", "name": event_name,
                 "data": {"topic_id": "t-b", "result_id": "r-1"}},
            ],
        ))
        # open (1) + the named event (1).
        assert t["loadTopicsCalls"] == 2
        assert t["containerCardCount"] == 2
        assert {"Alpha", "Beta"} <= set(t["containerCardLabels"])

    def test_live_result_event_renders_the_new_card(self):
        """The new card from the event is actually in the rendered container."""
        t = run_plan(_plan(
            cards=[_card("Alpha", topic_id="t-a")],
            steps=[
                {"action": "open"},
                {"action": "setCards", "cards": [
                    _card("Gamma", topic_id="t-g", summary="build #7 green", urgency="high"),
                ]},
                {"action": "event", "name": "result_created", "data": {"result_id": "r-g"}},
            ],
        ))
        html = t["containerHTML"]
        assert "Gamma" in html
        assert "build #7 green" in html
        assert "urgency-badge high" in html


# === reconnect (the core AC) ==================================================


class TestReconnect:
    """Native browser ``EventSource`` auto-reconnect: on a transient drop the
    SAME object fires ``onopen`` again — no new connection is opened. That second
    ``onopen`` calls ``loadTopics()`` again, so the canvas re-renders with the
    freshest card set (including anything that arrived during the outage)."""

    def test_reconnect_does_not_open_a_new_eventsource(self):
        """A reconnect reuses the existing EventSource — exactly one was ever
        created, not two."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "reconnect"},
        ]))
        assert t["eventSourcesCreated"] == 1

    def test_reconnect_fires_loadtopics_again(self):
        """The reconnect onopen re-fetches topics — two onopens ⇒ two fetches."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "reconnect"},
        ]))
        assert t["loadTopicsCalls"] == 2
        # Both onopens marked the stream Connected.
        connected = [s for s in t["statuses"] if s["text"] == "Connected"]
        assert len(connected) == 2

    def test_new_results_appear_after_reconnect(self):
        """A result that arrived during the outage is visible after reconnect:
        the initial render shows one card; after the server's card set grows and
        the canvas reconnects, both render."""
        t = run_plan(_plan(
            cards=[_card("Alpha", topic_id="t-a")],
            steps=[
                {"action": "open"},
                # While "disconnected" the server gained a new result.
                {"action": "setCards", "cards": [
                    _card("Alpha", topic_id="t-a"),
                    _card("Delta", topic_id="t-d", summary="arrived during outage"),
                ]},
                # Reconnect → onopen → loadTopics() re-renders the new set.
                {"action": "reconnect"},
            ],
        ))
        assert t["loadTopicsCalls"] == 2
        assert t["containerCardCount"] == 2
        assert {"Alpha", "Delta"} <= set(t["containerCardLabels"])
        assert "arrived during outage" in t["containerHTML"]


# === connection drops: onerror / disconnect / close ==========================


class TestConnectionDrops:
    """The other half of "simulate SSE connection drops by closing/reconnecting
    EventSource": the transient ``onerror`` and the server-initiated
    ``disconnect`` event, plus an explicit client ``close()``."""

    def test_onerror_sets_status_disconnected_without_closing(self):
        """A transient onerror marks the stream disconnected but does NOT close
        the EventSource — the browser keeps it for auto-reconnect."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "error"},
        ]))
        assert _last_status(t) == {"status": "disconnected", "text": "Disconnected"}
        assert t["closeCalls"] == 0
        assert t["eventSourcesCreated"] == 1

    def test_server_disconnect_event_closes_the_eventsource(self):
        """A server ``disconnect`` event marks disconnected AND closes the
        EventSource (the script's explicit ``eventSource.close()``)."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "event", "name": "disconnect", "data": {"reason": "timeout"}},
        ]))
        assert _last_status(t) == {"status": "disconnected", "text": "Disconnected"}
        assert t["closeCalls"] == 1

    def test_explicit_close_does_not_spawn_new_eventsource(self):
        """A client-side close() ends the stream without opening a new one."""
        t = run_plan(_plan(steps=[
            {"action": "open"},
            {"action": "close"},
        ]))
        assert t["closeCalls"] == 1
        assert t["eventSourcesCreated"] == 1


# === full lifecycle: drop → reconnect → live event converges ==================


class TestFullLifecycle:
    """The whole sequence a flapping canvas survives: connect, take a transient
    error, reconnect, then receive a live result — all on one EventSource."""

    def test_drop_reconnect_then_live_event_all_on_one_eventsource(self):
        t = run_plan(_plan(
            cards=[_card("Alpha", topic_id="t-a")],
            steps=[
                {"action": "open"},                       # connect
                {"action": "error"},                      # transient drop
                {"action": "reconnect"},                  # auto-reconnect
                {"action": "setCards", "cards": [         # new result lands
                    _card("Alpha", topic_id="t-a"),
                    _card("Epsilon", topic_id="t-e"),
                ]},
                {"action": "event", "name": "result_created", "data": {"result_id": "r-e"}},
            ],
        ))
        # Still the single original EventSource throughout.
        assert t["eventSourcesCreated"] == 1
        # open + reconnect + result_created ⇒ three topic fetches.
        assert t["loadTopicsCalls"] == 3
        # Final render reflects the post-reconnect, post-event card set.
        assert t["containerCardCount"] == 2
        assert {"Alpha", "Epsilon"} <= set(t["containerCardLabels"])
        # The status indicator ended back on Connected after the drop.
        assert _last_status(t) == {"status": "", "text": "Connected"}
