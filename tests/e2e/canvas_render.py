"""
Headless canvas-render helpers shared by the verification suites (bead adc-1l8w).

Two thin utilities used by both the pure render-contract test
(``tests/test_canvas_render.py``) and the SSE+render integration test
(``tests/e2e/test_canvas_sse_render.py``):

- :func:`render_cards` drives the REAL production canvas render module
  (``src/canvas/canvas.js``) under ``tests/e2e/canvas_dom_runner.js`` and
  returns the rendered ``{outerHTML, className, dataset}`` per card. No browser,
  no network — just ``node``.

- :func:`parse_sse_stream` parses the raw ``text/event-stream`` wire text the
  canvas ``EventSource`` consumes (``event: <type>\\ndata: <json>\\n\\n``) into a
  list of ``(event_type, data)`` tuples, mirroring how the browser dispatches
  ``addEventListener`` handlers — the same handlers ``loadTopics()`` hangs off
  of ``result_created`` and ``topic_updated`` in src/canvas/index.html.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Path to the headless DOM runner that loads src/canvas/canvas.js.
DOM_RUNNER = Path(__file__).parent / "canvas_dom_runner.js"
# Path to the production canvas render module the runner loads (for assertions).
CANVAS_JS = Path(__file__).parents[2] / "src" / "canvas" / "canvas.js"

# node is required to drive the DOM runner; tests skip cleanly when absent.
NODE = shutil.which("node")


def node_available() -> bool:
    """True iff a ``node`` binary is on PATH (the DOM runner needs it)."""
    return NODE is not None


def render_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Render card dicts through the REAL canvas.js via the headless DOM runner.

    Feeds ``cards`` (the exact shape ``GET /api/v1/sessions/{id}/topics``
    returns under ``.cards`` — i.e. what ``loadTopics()`` hands to
    ``createTopicCard()``) to ``canvas_dom_runner.js`` on stdin and returns its
    JSON output: one ``{outerHTML, className, dataset}`` per card.

    Raises ``RuntimeError`` if node is missing or the runner exits non-zero.
    """
    if NODE is None:
        raise RuntimeError("node not found on PATH — cannot drive canvas DOM runner")
    proc = subprocess.run(
        [NODE, str(DOM_RUNNER)],
        input=json.dumps(cards),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"canvas_dom_runner exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return json.loads(proc.stdout)


def render_card(card: dict[str, Any]) -> dict[str, Any]:
    """Render a single card dict; returns its ``{outerHTML, className, dataset}``."""
    return render_cards([card])[0]


def parse_sse_stream(text: str) -> list[tuple[str, dict]]:
    """Parse raw SSE wire text into ``(event_type, data)`` pairs.

    Mirrors the browser ``EventSource`` contract: blocks separated by a blank
    line, each block an ``event:`` line and a ``data:`` JSON line. The canvas
    wires ``result_created`` and ``topic_updated`` blocks to ``loadTopics()``.
    """
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        etype = ""
        data: dict = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                etype = line[len("event:"):].strip()
            elif line.startswith("data:"):
                payload = line[len("data:"):].strip()
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    # Non-JSON data line — preserve raw so callers can still see it.
                    data = {"_raw": payload}
        if etype:
            events.append((etype, data))
    return events
