# adc-3h9q — Starvation alert: beads invisible to worker

**Date:** 2026-07-20
**Workspace:** /home/coding/aide-de-camp
**Verdict:** False-positive alert. Not a configuration error. Root cause was a stale,
already-implemented bead that Pluck correctly excluded — closing it unblocked healthy work.

## Alert as received

> Open beads exist but Pluck found none — possible configuration error.
> Total beads: 122 · Open: 1 · In-progress: 0 · Claimed by: (none)
> Check exclude_labels, workspace path, and filter configuration.

## Root cause

The single open bead was `adc-blg1` ("Add test dispatch endpoint"). Pluck skipped it for
**three** valid reasons, all of which are correct behavior — not misconfiguration:

1. **`deferred` label** — listed in `strands.pluck.exclude_labels: [deferred, human, blocked]`
   in `~/.config/needle/config.yaml`. This is the primary, intended exclusion.
2. **`failure-count:5` label** — auto-applied after repeated worker failures.
3. **Unmet blocker chain** — `adc-blg1` → `adc-1dbu` → `adc-1sey` → `adc-5khx` → `adc-1p7p`
   → `adc-3qy2`, all of which were `blocked`/`closed`. It could not be worked anyway.

So `exclude_labels`, the workspace path, and filter config are all correct. The alert's
"possible configuration error" hint was a red herring.

## Deeper finding: the work was already done

The entire `adc-blg1` split-child chain described the **test-dispatch feature**, which is
fully implemented and live in the codebase:

- `src/test/dispatch.py` — `POST /test/dispatch` (line 307) and
  `POST /test/dispatch/{utterance_name}` (line 343), Pydantic-validated
  `{utterance, session_id, surface_id, ...}`.
- Router registered in `src/main.py:53` (import) and `:200`
  (`app.include_router(test_router, prefix="/api/v1")`) → effective `/api/v1/test/dispatch`.
- Wires into the full pipeline: `get_router` (intent), `get_store` (session),
  `get_broadcaster` (SSE) — bypasses Web Speech API transcription as specified.

**Live verification** — `POST /api/v1/test/dispatch` on the running server (health=200):

```json
{"status":"dispatched","utterance_id":"5dd6e8c4-...","session_id":"probe-3h9q",
 "intent_count":1,"intent_ids":["a84948f5-..."],"message":"Test dispatch initiated for 1 intents"}
```

The intent router classified the probe utterance (`intent_count:1`), confirming end-to-end
function. Every acceptance criterion across the chain was met.

## Resolution

Closed the 5 stale beads whose work was verifiably complete, each with cited evidence:

| Bead | Title | Evidence |
|------|-------|----------|
| `adc-blg1` | Add test dispatch endpoint | live HTTP 200, dispatch.py:307, main.py:53/200 |
| `adc-1dbu` | Verify endpoint response format | live response matches /dispatch envelope |
| `adc-1sey` | Add API route registration | main.py:53 import, :200 include_router |
| `adc-5khx` | Wire intent router integration | get_router import, live intent_count:1 |
| `adc-1p7p` | Implement test dispatch endpoint | dispatch.py:307 + Pydantic request model |

(`adc-3qy2` "Add test router module" was already closed — `src/test/router.py` exists.)

Closing the chain unblocked `adc-1jxz` ("Add intent classification test cases"), which is now
**ready** (open, unblocked, no exclude labels) — so Pluck can dispatch it and the starvation is
genuinely over. `adc-1jxz` was left open: its fixtures (`src/test/fixtures/utterances.json`,
6 utterances) and `/test/classify` endpoint (`src/test/router.py:48`) exist, but explicit
expected-intent test assertions are ambiguous, so it is legitimate work for a worker to
evaluate rather than something to preemptively close.

## What was NOT changed

- `exclude_labels`, workspace path, filter config — all verified correct, left untouched.
- No source-code changes (the feature was already implemented).

## Lesson for the fleet

A starvation alert with `Open > 0` but `Pluck found none` is expected whenever the only open
beads carry an `exclude_labels` entry (typically `deferred`) or are blocked. Before treating it
as a config bug, check whether the open bead's work is already done — stale split-child chains
are the more common culprit in this workspace.
