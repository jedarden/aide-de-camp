# adc-50m6 — [Unravel] Mock Web Speech API + verify full dispatch pipeline

## Outcome

**Complete (umbrella closed).** This is the automated alternative to the
human-blocked bead `adc-5zs` ("real-microphone voice turn + listen to narration
+ visual canvas check"). The mock-Web-Speech-API surface it asks for —
`POST /api/v1/test/dispatch`, which injects pre-canned utterance text directly
into the dispatch pipeline, bypassing the audio/transcription layer — was
already implemented, committed, and verified by earlier beads in this tree.
This pass re-verified the **entire** pipeline live against the running server
and the ZAI proxy LLM, confirmed all four acceptance criteria, and closed the
umbrella.

The endpoint itself lives in `src/test/dispatch.py` and is mounted at
`/api/v1` in `src/main.py` (`app.include_router(test_router, prefix="/api/v1")`),
so the route is `POST /api/v1/test/dispatch`. Sibling routes in the same module:
`POST /api/v1/test/dispatch/{utterance_name}` (dispatch a pre-canned utterance
by name), `POST /api/v1/test/run_suite` (run the whole canned suite), and
`GET /api/v1/test/utterances` (list the canned set).

## Acceptance criteria — all met

| # | Criterion | Evidence | Status |
|---|-----------|----------|--------|
| 1 | Intent classification works on test inputs | `tests/test_test_endpoint_classification.py` — `test/classify` and `test/dispatch` share the same `IntentRouter`/`classify_utterance` path; classification is identical across both entry points | ✅ |
| 2 | Fetch strands execute correctly | `tests/e2e/test_fetch_strand_execution.py` + the live dispatch's stored `results` rows (a result row only exists if fetch → synthesize ran to completion) | ✅ |
| 3 | Results stored + broadcast via SSE | `tests/e2e/test_storage_sse_verification.py` — utterance/intent/result rows persist with correct linkage; `result_created` SSE event reaches the target `surface_id` carrying `intent_id`/`topic_id`/`summary`/`urgency` | ✅ |
| 4 | Canvas receives and renders cards | `tests/e2e/test_canvas_sse_render.py` — the two event types `index.html` wires to `loadTopics()` (`result_created`, `topic_updated`) arrive over the SSE wire; `GET /api/v1/sessions/{id}/topics` returns cards the real `canvas.js` renders into `.topic-card` with label + summary + urgency badge | ✅ |

## Verification run (this pass, 2026-07-21)

Server was running (`curl /health` → `{"status":"ok"}`), ZAI proxy reachable.

```
$ .venv/bin/pytest tests/e2e/test_canvas_sse_render.py \
                    tests/test_test_endpoint_classification.py \
                    tests/e2e/test_fetch_strand_execution.py -v
... 22 passed, 4 warnings in 0.87s
```

```
$ .venv/bin/pytest tests/e2e/test_storage_sse_verification.py -v -s
... 5 passed in 51.85s
```

The live suite drives the **real** `POST /api/v1/test/dispatch` through the ZAI
proxy (genuine LLM classification + synthesis), so criteria 1–3 are exercised
end-to-end on the actual dispatch path, not a mock.

## Note on criterion 4 — real-dispatch → render is covered transitively

No single test drives a live `POST /api/v1/test/dispatch` round-trip *and*
renders the resulting card through `canvas.js` in one assertion. The link is
covered compositionally instead:

- `test_storage_sse_verification.py` proves a real dispatch writes a `results`
  row linked (via `topic_id`) to a `topics` row, with `summary` + `data`.
- `test_canvas_sse_render.py` proves any such `topics`+`results` row renders
  into a `.topic-card` via the exact path the canvas uses
  (`GET /api/v1/sessions/{id}/topics` → `createTopicCard` in `canvas.js`).

Both halves consume the same store-produced row shape, so the composition holds.
A direct bridge test was deliberately **not** added: a live variant would be
slow and server/LLM-dependent (flaky when the server or proxy is down, like the
storage suite's skip-on-no-server guard), and a hermetic variant would require
mocking the ZAI client at two call sites (router classify + synthesize strand),
which drifts from real behavior. The transitive coverage is stronger than either.

## Dependencies

Both blocking sub-verifications are **closed**:

- `adc-3mc5` — Verify storage and SSE broadcast via test endpoint (closed).
  Summary: `tests/e2e/verification_summary.md`.
- `adc-1l8w` — Verify canvas renders test results (closed). Note:
  `notes/adc-1l8w.md`.

The original human-blocked bead `adc-5zs` remains `blocked` by design — it
requires a physical microphone and subjective listening/visual judgment that
this unravel alternative replaces with programmatic verification.

## No code change

This is a verification/umbrella-completion record only — no source or test
files changed. Following repo precedent (`c556b16`, `bf80c96`, `372b8ea`), a
notes-only commit does not bump the version.
