# Built-in Card Implementation - Complete (Bead adc-3l5r)

## Status: COMPLETE ✅

All four built-in card families are fully implemented and verified via headless test suite.

## Implementation Summary

The built-in cards were implemented across child beads that completed under this parent bead:

### 1. Welcome Card (adc-22b1g)
- **File:** `src/canvas/canvas.js` - `createWelcomeCard()`
- Renders on fresh session (zero cards)
- Shows registered projects from `/api/v1/registry`
- Displays 2-3 example utterances derived from project intents
- Zero DB dependence - drops when first real result arrives

### 2. Pending/Ack Cards (adc-351xo, adc-o7icd)
- **Files:** `src/canvas/canvas.js` and `src/canvas/index.html`
- Submit-time placeholder created locally BEFORE server response
- Survives hung/wedged server (no SSE dependency)
- Splits into per-thread pending cards on dispatch ack
- Per-source progress tracking ("3/5 sources in")
- Elapsed time footer updated every second

### 3. Aged-Pending Treatment (adc-3wgko)
- **File:** `src/canvas/canvas.js` - `applyAgedTreatment()`
- 30-second threshold (`PENDING_AGE_THRESHOLD_MS = 30000`)
- Pure client-side timer (survives server failure)
- Visual feedback: red border animation, aged note, retry button

### 4. Error/Clarification Family (adc-22b1g)
- **File:** `src/canvas/canvas.js` - `createErrorCard()`
- Five variants from Degraded-State UX matrix:
  1. `router_unavailable` - LLM proxy unreachable
  2. `all_sources_failed` - All fetch sources failed
  3. `synthesis_failed` - Summary unavailable, shows raw data
  4. `malformed_router_output` - Couldn't parse intents
  5. `no_match` - No matching project, shows registered projects

## Test Coverage

All tests pass (39 passed, 1 skipped):
- `test_canvas_builtin_families.py` - Cross-family suite (14 tests)
- `test_canvas_aged_pending.py` - Aged-pending treatment (6 tests)
- `test_canvas_error_cards.py` - Error card variants (10 tests)
- `test_canvas_welcome_card.py` - Welcome card behavior (10 tests)

## Acceptance Criteria Met

✅ **Placeholder at submit with server stopped** - Card exists and ages to 30s flag via mock clock
✅ **Welcome card on fresh session** - Zero cards → welcome, one card → topics only
✅ **Each error card template renders** - All 5 variants tested with synthetic SSE events
✅ **Pending splits per-thread on ack** - Placeholder → N thread cards (one per intent_id)
✅ **All values as text nodes** - Escaping contract verified via cross-family audit

## Escaping Contract

All dynamic values are inserted as text nodes via `escapeHtml()` or `el()` helper:
- Project descriptions, slugs, intent labels
- Utterance text
- Error details, source names, failure reasons
- Raw data display
- No raw HTML splicing into innerHTML

## Server Independence

The pending placeholder and aged-pending treatment work with zero server dependency:
- Placeholder created locally at dispatch submit time (before fetch)
- Aging uses client-side clock (`setInterval` in index.html)
- Survives complete server failure - tested with mock clock

## Files Modified

- `src/canvas/canvas.js` - Render helpers for all four card families
- `src/canvas/index.html` - SSE handlers, dispatch logic, aging ticker
- `tests/e2e/test_canvas_builtin_families.py` - Cross-family suite
- `tests/e2e/test_canvas_aged_pending.py` - Aged-pending tests
- `tests/e2e/test_canvas_error_cards.py` - Error card tests
- `tests/e2e/test_canvas_welcome_card.py` - Welcome card tests

## Child Beads Completed

- adc-351xo: Pending placeholder at submit time
- adc-1wp26: SSE result_created replaces pending cards
- adc-o7icd: Pending placeholder split to per-thread cards
- adc-3wgko: Aged-pending treatment with 30s threshold
- adc-22b1g: Welcome card and error card families
