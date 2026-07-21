# adc-1l8w — Verify canvas renders test results

## Outcome

**Complete.** The canvas SSE + render verification suite was already
implemented, committed (`6a52192`), and pushed to `origin/main` by a prior run
of this bead. This pass re-verified every acceptance criterion and closed the
bead (the prior run committed/pushed but never closed it).

## Acceptance criteria — all met

| Criterion | Covered by | Status |
|-----------|-----------|--------|
| Canvas receives SSE events | `TestCanvasReceivesSSEEvents` | ✅ |
| `loadTopics()` fetches + renders new topics | `TestLoadTopicsRenders` | ✅ |
| Cards appear after test dispatch | `TestCardAppearsAfterTestDispatch` | ✅ |
| All tests pass | 17/17 across both canvas files | ✅ |

## Test files

- `tests/test_canvas_render.py` — card-rendering unit tests (HTML escaping,
  topic-type / staleness / urgency badges, batch rendering, and a guard that
  the DOM runner targets the real `src/canvas/canvas.js` module).
- `tests/e2e/test_canvas_sse_render.py` — hermetic end-to-end verification
  (no browser, no live server). Key guarantees locked down:

  - **Canvas receives SSE events** — drives the *same* `event_generator` the
    `/api/v1/sse` endpoint serves, asserting `result_created` and
    `topic_updated` (the two event types `index.html` wires to `loadTopics()`)
    arrive as parseable `text/event-stream` wire text; `target_surface_id`
    narrows delivery to one surface and excludes the other.
  - **`loadTopics()` fetches + renders** — `GET /api/v1/sessions/{id}/topics`
    returns cards the *real* `canvas.js` renders into a `.topic-card`.
  - **Cards appear after test dispatch** — injecting a topic via the
    deterministic no-LLM test-dispatch path and rendering the reloaded cards
    yields a card carrying label + summary + urgency badge; multiple
    dispatched topics each render as their own card.

The render helpers (`createTopicCard`/`escapeHtml`/`formatStaleness`/
`getStalenessLevel`) were extracted from `index.html` into
`src/canvas/canvas.js` (served via a new `GET /canvas.js` `FileResponse`),
so the tests assert against real rendered `outerHTML` via
`tests/e2e/canvas_dom_runner.js` under a minimal DOM shim — headlessly, no
browser. `index.html` loads it as a blocking `<script src="/canvas.js">`,
keeping the helpers as globals.

## Verification run (this pass)

```
$ .venv/bin/pytest tests/test_canvas_render.py tests/e2e/test_canvas_sse_render.py -v
.................                                                        [100%]

========================= 17 passed, 4 warnings in 1.11s =========================
```

## Pre-existing, unrelated failures (not a regression from this bead)

- `tests/test_exceptions_routing.py` — 5 failures, all stemming from
  `'SurfaceRouter' object has no attribute '_get_no_canvas_timeout'` (escalate
  handler / exceptions surface routing). Outside this bead's canvas scope; same
  5 failures the prior commit noted on a clean tree. Tracked separately.
- `tests/e2e/test_canvas_navigation.py` and `tests/e2e/test_canvas_rendering.py`
  — 2 collection errors from a broken playwright install (greenlet's
  `libstdc++.so.6` load failure on NixOS). These are the browser-based e2e
  tests, distinct from this bead's hermetic `test_canvas_sse_render.py`, which
  collects and passes. Unrelated.

## Dependency

`adc-18as` (verify persistence + SSE broadcast) is **closed** — the blocking
dependency this bead required is satisfied.
