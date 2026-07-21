# adc-1rdt — DOM verification for canvas cards

## What

Added DOM verification for canvas topic cards, meeting the bead's acceptance
criteria: query cards by locator, assert data attributes, layout classes, text
content, all five topic types, and negative cases — with tests that pass when
cards render correctly and fail when they're missing or malformed.

Two complementary suites, because this NixOS host cannot launch a browser:

1. **`tests/test_canvas_dom_verify.py`** (26 tests, always-green here) — drives
   the REAL `src/canvas/canvas.js` through the Node DOM runner
   (`tests/e2e/canvas_dom_runner.js`, from adc-1l8w) with no browser/network,
   then queries the rendered `outerHTML` with a small stdlib `html.parser`-based
   selector engine. This is the floor of coverage that runs on this box and in CI.
2. **`tests/e2e/test_canvas_dom_verification.py`** (14 tests) — the Playwright
   counterpart the bead's AC names explicitly ("Use Playwright's expect() API",
   "query for card elements using Playwright's locators"). It injects topics via
   the adc-5unt `TestDataInjector`, opens the live canvas, and asserts on the
   rendered DOM with `page.locator(...)` + `expect()`. It imports Playwright
   lazily and skips cleanly when there is no server or no launchable browser, so
   it collects here and runs for real wherever a browser exists.

## Production change

`src/canvas/canvas.js` `createTopicCard()` now sets `card.dataset.topicType =
type || 'adhoc'`, exposing `data-topic-type` alongside the existing
`data-topic-id`. This gives cards a stable, class-name-independent selector
(`[data-topic-type="research"]`) — the "use data attributes over classes"
guidance. Both suites assert the attribute is present, on the root, and reflects
the type (defaulting to `adhoc` when the topic has no type).

## AC → suite mapping

| Acceptance criterion | Where covered |
|---|---|
| Query cards with Playwright locators | `tests/e2e/test_canvas_dom_verification.py` (`page.locator('[data-topic-id=...]')`) |
| Data attributes exist (`data-topic-id`, `data-topic-type`) | `TestDataAttributes` (both suites) |
| Text content matches injected data | `TestTextContent` (label, summary, type/urgency badge) |
| Layout classes present (card / card-header / card-body) | `TestLayoutClasses` — maps to `topic-card` / `topic-header` / `result-content`, the existing canvas idiom |
| Pass when correct, fail when missing/malformed | `TestNegative` + mutation check (below) |
| All topic types (project, research, personal, exception, compound) | `TestAllTopicTypes` (parametrized over all 5) |
| Negative tests (missing topics not rendered) | `TestNegative` (empty list → 0 cards; no card-body without a result; no unrelated type; id non-leak; malformed label) |

## Verification

- `tests/test_canvas_dom_verify.py` → **26 passed**.
- `tests/e2e/test_canvas_dom_verification.py` → **14 collected, 14 skipped**
  (no server/browser on this host; skips, never errors at import — unlike the
  older top-level-`import playwright` navigation test).
- No regression in suites sharing `canvas.js`/inject infra:
  `test_canvas_render.py`, `test_inject.py`, `test_canvas_sse_render.py` →
  **32 passed**.
- **Mutation proof of "fail when malformed"**: removing the new
  `card.dataset.topicType = typeClass` line fails 7 tests
  (`KeyError: 'data-topic-type'`); restoring returns to 26 green. The guard is
  real, not a tautology.

## Version

`pyproject.toml` 0.16.0 → **0.17.0** (MINOR — new card-selector feature + new
test suites). Tagged `v0.17.0`.
