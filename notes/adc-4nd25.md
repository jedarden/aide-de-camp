# adc-4nd25 — Wire welcome card into fresh-session loadTopics + headless render test

**Parent:** adc-3l5r (built-in card set). **Chain position:** child 1 of 5
(independent foundation — shared canvas render path).

## What this bead delivers

- **`src/canvas/index.html`** — `loadTopics()` no longer renders the bare
  "No active topics" empty-state on a fresh session. On the zero-card branch it
  fetches the registry project list via the new `loadWelcomeProjects()` (cached),
  then calls `buildContainerChildren(cards, projects)` which renders
  `createWelcomeCard()` for an empty card set. The welcome card is dropped — not
  duplicated — the moment the first real result lands (the next
  `result_created` → `loadTopics()` reload yields a non-empty set, so
  `buildContainerChildren` returns topic cards only).
- **`src/canvas/canvas.js`** — `buildContainerChildren(cards, projects,
  description)` is the headlessly-testable core of `loadTopics()` (empty cards →
  welcome card; any card → topic cards only).
- **`tests/e2e/canvas_dom_runner.js`** — `--container` mode drives
  `buildContainerChildren()` under the existing DOM shim.
- **`tests/e2e/canvas_render.py`** — `render_container()` Python driver for the
  `--container` mode (mirrors `render_cards`).
- **`tests/e2e/test_canvas_welcome_card.py`** — headless assertion suite (10
  tests) covering the acceptance criteria.

## Acceptance — verified

- Fresh (zero-card) session renders the welcome card with the project list and
  ≥2 example utterances (derived from the projects' supported intents).
- No DB dependence — the welcome card is built from the registry project list
  only; `get_registry()` returns 39 projects (YAML + discovery), verified
  directly. The served static frontend (`/canvas.js`, `/`) already reflects the
  wiring (confirmed via curl — `buildContainerChildren` + `loadWelcomeProjects`
  present; the old "No active topics" empty-state is gone).
- Welcome card is replaced (not duplicated) once the first real result lands.
- All interpolated values are text nodes via `escapeHtml`/`el()` (escaping
  contract adc-3ixa) — markup in a slug/description surfaces as visible text,
  never injected HTML.
- Headless suite passes: `pytest tests/e2e/test_canvas_welcome_card.py` → 10
  passed; the broader canvas suite (`test_canvas_dom_verify`, `test_canvas_render`,
  `test_canvas_staleness`) → 81 passed total.

## Scope notes (important for gap review)

- **`src/canvas/canvas.js` ships the whole built-in card module**, not just the
  welcome path. `buildContainerChildren` (this bead) + `createWelcomeCard` (its
  dependency) are committed alongside the sibling builders — pending/ack,
  error/clarification, and generic-fallback card families — that belong to
  sibling beads 2–5. Those builders are **inert**: they are exported but never
  called by `loadTopics()`/`dispatch()` until their own wiring beads land, so
  shipping them here changes no runtime behavior. They are committed (rather
  than trimmed) to **preserve the prior runs' in-progress work for the sibling
  beads**; trimming would have destroyed ~340 lines of their work from disk.
- **`src/main.py` is intentionally NOT committed by this bead.** Its working-tree
  diff is purely additive (97 lines, 0 removed) but mixes the welcome card's
  `/api/v1/registry` endpoint with the Latency-Budget bead's
  `/api/v1/timings` + `/api/v1/timings/percentiles` endpoints and SSE-emit
  instrumentation. The registry endpoint is the welcome card's live project-list
  source; it ships with the backend bundle that owns the rest of main.py's diff.
- **`config/registry.yaml` is NOT committed** — its diff adds `argocd_app`
  fields to two projects (unrelated backend data).

## Live-server caveat

The running uvicorn process was started ~16h before these changes. Static files
(`/canvas.js`, `/`) are served from disk per-request, so the welcome card wiring
is already live. The `/api/v1/registry` **route**, however, is loaded only at
startup, so the stale server 404s on it until a restart — at which point
`loadWelcomeProjects()` returns the 39-project list. A restart was not done here
to avoid loading the unrelated Latency-Budget backend changes into the shared
dev server mid-umbrella.
