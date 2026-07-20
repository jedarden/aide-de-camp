# adc-492b — Verify intent classification works via test endpoint

**Status:** Verified. No source changes were needed — the deliverable test suite
(`tests/test_test_endpoint_classification.py`) was already committed and pushed
(concurrent run; `e1b4861` on `origin/main`, content-identical to the local twin
`36cd49c`). This note records the independent verification performed in this session.

## What was verified

The bead requires that the test endpoints route utterances through the **same**
intent classifier as `POST /dispatch`, producing identical classifications for
identical inputs, with no audio/microphone layer. Confirmed against the source:

| Handler | Router source | Entry point |
|---|---|---|
| `POST /dispatch`, `POST /router` (`src/main.py`) | `get_router(store)` — imported **as** `get_intent_router` (`src/main.py:51`) | `route_utterance()` |
| `POST /api/v1/test/dispatch` (`src/test/dispatch.py:307`) | `get_router(store)` (`src/test/dispatch.py:74`) | `route_utterance()` |
| `POST /api/v1/test/classify` (`src/test/router.py`) | `get_router()` | `classify_utterance()` directly |

- `route_utterance` delegates to `classify_utterance` (`src/intent/router.py:258`), so
  the dispatch and test-dispatch paths cannot diverge from the classify path in *how*
  they classify.
- `get_router()` is a process-wide singleton (`_router` cached at
  `src/intent/router.py:482-490`), so every handler shares one `IntentRouter` — a
  hot-reload of the prompt reaches all paths equally.

## On the acceptance criteria's "weather"/"research" intents

Those are not `IntentType` values in this codebase. `research` is a **topic type** —
the default for any intent that isn't `ACTION`/`TASK_PROFILE`
(`_topic_type_map` in `IntentRouter._fetch_and_synthesize`, `src/intent/router.py:366`):
an open-ended information-seeking utterance segments to a `LOOKUP` intent that lands on
the `research` topic type. "weather" exists as no type at all. The test suite verifies
the real contract (identical classification across paths) using actual `IntentType`
values and documents this mapping.

## Tests

`tests/test_test_endpoint_classification.py` — **16 passed** (0.28s). Pins down:
1. Shared `get_router()` singleton identity.
2. `route_utterance` → `classify_utterance` delegation; request schemas carry no
   audio/microphone/STT field.
3. Identical inputs → identical classifications across the classify and dispatch paths.
4. The `research`-as-topic-type mapping (ACTION/TASK_PROFILE → "project", else → "research").

## Note on working-tree state

Uncommitted modifications to `src/main.py`, `src/session/store.py`, `src/test/router.py`
(additional `/sessions` test-injection/teardown endpoints) and untracked `tests/e2e/*`
belong to a **separate bead** and were intentionally left out of this commit.
