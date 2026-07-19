# adc-3a3d — Router prompt externalized to prompts/router.md (regression lock)

## Outcome

All four acceptance criteria for this bead are satisfied in the codebase:

1. **No hardcoded prompt** — `src/intent/router.py` contains no multi-line
   `ROUTER_SYSTEM_PROMPT` constant. It defines `ROUTER_PROMPT_PATH` and reads
   the file per call via `_load_router_prompt()` → `_build_system_prompt()`,
   mirroring `src/synthesize/strand.py` (`SYNTHESIZE_PROMPT_PATH`).
2. **Hot-reload** — `_load_router_prompt()` calls `self.prompt_path.read_text()`
   on every `classify_utterance()`, so editing `prompts/router.md` takes effect
   on the next call without a server restart.
3. **urgency.md wired up** — `_load_urgency_prompt()` reads
   `prompts/urgency.md` through the hot-reload manager (`get_prompt("urgency")`)
   and splices it under a `## Urgency Classification Rules` heading. The
   `urgency` registration in `src/components/hot_reload.py` is therefore live,
   not vestigial.
4. **Regression check** — added in this bead (see below).

## Important context: the core fix landed under adc-1sb

The refactor that replaced the hardcoded `ROUTER_SYSTEM_PROMPT` with a per-call
disk read was committed in **`5a01c1f`** ("refactor(router): externalize router
prompt to disk + splice urgency rules"), tagged **Bead-Id: adc-1sb**. By the
time adc-3a3d was dispatched, the bug it describes ("router.py line 61 defines
`ROUTER_SYSTEM_PROMPT = """..."""`") no longer existed in `main`.

adc-3a3d's evidence describes the **pre-`5a01c1f`** state. The two beads target
the same defect; adc-1sb landed first and resolved items 1–3.

## What this bead (adc-3a3d) contributes

The one deliverable from adc-3a3d's task list **not** covered by `5a01c1f` was
**task item #4 — the regression check**. `tests/test_urgency_hotreload.py`
exists but only mutates `urgency.md` (its `intent_router` fixture even points at
the production `prompts/router.md` and never edits it). So nothing locked down
the "router.md is read per call" behavior — the exact regression that would let
a hardcoded prompt silently reappear and no-op the self-modification agent's
edits to `router.md`.

Added **`tests/test_router_prompt_hotreload.py`** (9 tests, all passing) covering:

- `_load_router_prompt()` returns on-disk `router.md` content (not the
  `_ROUTER_PROMPT_FALLBACK` constant), and falls back gracefully when the file
  is missing.
- Editing `router.md` and re-invoking the loader returns the new content.
- `_build_system_prompt()` includes both `router.md` content and the urgency
  splice, and reflects a `router.md` edit.
- End-to-end: `classify_utterance()` (with a mocked ZAI client, **no live LLM**)
  sends the `router.md`-derived system prompt to the client, and editing
  `router.md` between two calls changes what is sent — the literal acceptance
  criterion.

### Mutation check (teeth confirmed)

Temporarily reverted `_load_router_prompt()` to return a hardcoded constant
(simulating the original bug). **8 of 9** new tests failed; only
`test_build_includes_urgency_splice` survived (correctly — it only asserts
urgency splicing). Restoring `router.py` returned all 9 to green. The suite
genuinely catches a re-hardcoded prompt.

## Test status

- `tests/test_router_prompt_hotreload.py`: **9 passed**
- `tests/test_urgency_hotreload.py`: **8 passed**
- `tests/test_exceptions_routing.py`: 5 pre-existing failures
  (`SurfaceRouter._get_no_canvas_timeout` AttributeError + escalate auto-approve)
  — unrelated to this change (telegram/exception-routing API drift); present on
  `main` independent of this bead.
