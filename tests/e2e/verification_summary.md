# Storage and SSE Broadcast Verification Summary

**Date:** 2026-07-19
**Bead:** adc-3mc5 (child of adc-50m6)
**Purpose:** Verify storage and SSE broadcast via the test endpoint `POST /api/v1/test/dispatch`

## Acceptance Criteria Status — ALL MET

### ✅ 1. Result stored in data/session.db
**Status:** PASSED — `test_dispatch_storage_in_database`
- utterances row stored with correct `session_id` + `raw_text`
- intents row stored with FK to utterance, `intent_type`, `status`
- results row stored with `topic_id`, `summary`, `data`
- result → topic → session linkage confirmed via JOIN

### ✅ 2. SSE event with type='result_created' broadcast
**Status:** PASSED — `test_dispatch_sse_broadcast`, `test_result_created_event_payload`
- SSE connection established for the surface_id
- `result_created` event received on that surface
- payload carries `intent_id`, `topic_id`, `summary`, `urgency`

### ✅ 3. Canvas receives event at surface_id
**Status:** PASSED
- events routed to the specific `surface_id` (broadcaster filters on `target_surface_id`)
- a dedicated listener on that surface_id receives the event; non-targeted surfaces do not
- multiple concurrent SSE connections supported

### ✅ 4. Storage payload matches /dispatch payload
**Status:** PASSED — `test_dispatch_matches_main_endpoint`
- both endpoints surface identical ack fields (`utterance_id`, `session_id`, `intent_count`, `intent_ids`)
- intent row schema identical across `/test/dispatch` and `/dispatch`

### ✅ (bonus) Broadcast timing matches /dispatch
**Status:** PASSED — `test_broadcast_timing_matches_dispatch`
- `/test/dispatch` acks near-instantly (<5s; observed ~1.7s)
- processing + `result_created` broadcast happen in the background, arriving after the ack

## How to reproduce

Server must be running (`nohup .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &`),
with network access to the ZAI proxy (real LLM classification + synthesis):

```bash
.venv/bin/python -m pytest tests/e2e/test_storage_sse_verification.py -v -s
```

Last run: **5 passed in 35.97s** (2026-07-19).

An independent manual trace (`~/scratch/adc-3mc5-verify.py`) drives the same flow outside
pytest — opens an SSE listener on a fresh surface_id, POSTs to `/api/v1/test/dispatch`,
confirms the `result_created` event arrived, and inspects the real SQLite rows for the
session. It passed: session/utterance/intent/result rows all persisted and the event
reached the exact surface_id.

## Fixes made during verification

These were real bugs found while verifying; both are included in this bead's commit.

1. **`src/test/dispatch.py`** — `create_session()` was called with no argument, minting an
   unrelated `sessions.id` and leaving an orphan row. The utterance/intent/result rows used
   the *passed* `session_id` while the sessions row used a *different* generated id. Fixed
   to `create_session(session_id)` so the sessions PK matches.

2. **`tests/e2e/test_storage_sse_verification.py`** — rewritten to fix three test-harness
   bugs that produced spurious failures (not product bugs): (a) located DB rows by
   `session_id`/`utterance_id` instead of the router-internal correlation `intent_id`
   (which is **not** the `intents.id` PK); (b) used a dedicated httpx client for the
   in-stream POST to avoid `httpx.StreamConsumed`; (c) pre-created the session row so `/sse`
   does not remap `session_id`. The earlier version's 3/5 failures were all harness artifacts.

3. **`tests/e2e/conftest.py`** — made the `playwright` import optional (try/except) so
   collection of `tests/e2e/` does not fail when playwright is not installed.

## Conclusion

The test endpoint `/api/v1/test/dispatch` correctly stores results to the SQLite session
store and broadcasts `result_created` SSE events to the surface_id given by the canvas,
matching the storage + broadcast behavior of the main `/dispatch` endpoint.
