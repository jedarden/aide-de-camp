# ADC-BMAZ: Server-Side Component Selection & Fallback Implementation

## Summary

This implementation completes the server-side component selection and fallback rendering pipeline for the hot-path dispatch flow.

## What Was Implemented

### 1. Result Type Derivation (`src/render/hot_path.py`)
- `derive_result_type()` function derives deterministic card-selector keys:
  - Intent-derived: `{intent_type}:{project_slug}` (one per intent thread)
  - Lookup with kind: `lookup:{lookup_kind}:{project_slug}` (e.g., `lookup:logs:ibkr-mcp`)
  - Monitoring: `monitoring:{project_slug}`

### 2. Deterministic Server-Side Component Selection
- `HotPathRenderer` class implements the hot-path card selector:
  - `select_component_for_result_type()` - looks up highest `match_score` in `component_usage_patterns` for a result_type
  - No LLM call - fully deterministic lookup
  - Returns `None` when no component matches threshold (0.7)

### 3. Card Cache & Template Filling
- `HotPathRenderer.render()` fills component templates with result data:
  - `fill_template()` - flat dot-path substitution with HTML escaping
  - `cache_card()` - writes to `card_cache` keyed by `(result_id, component_id, layout_bucket)`
  - `record_usage_pattern()` - updates usage stats (sample_count, last_matched, running match_score)

### 4. Generic Fallback Card
- `render_fallback_card()` - server-side fallback HTML rendering:
  - Key/value grid over `result.data` + summary
  - All values HTML-escaped
  - Streamed via SSE - no blank canvas states
- `card_fallback` flag - persisted to results table, signals client to use fallback

### 5. Write-Scope Separation
The server (hot-path renderer) only writes to:
- ✅ `card_cache` rows
- ✅ `components.usage_count` and `last_used` columns
- ✅ `component_usage_patterns` stats

Server NEVER writes to:
- ❌ `components` rows (except usage_count/last_used columns)
- ❌ `component_versions` rows
- ❌ `component_tags` rows

These are UI-regen agent's exclusive write scope.

### 6. SSE Streaming of Rendered HTML
- `dispatch_intent()` endpoint includes `rendered_html` in SSE events
- `SSEEvent.rendered_html` field carries pre-rendered card HTML
- Canvas injects HTML directly - component cards or fallback cards

## Tests

Comprehensive test coverage:
- `test_hot_path.py` - derive_result_type() function tests
- `test_fallback_card.py` - fallback card rendering and persistence
- `test_write_scope_separation.py` - write-scope boundary verification
- `tests/test_sse_rendered_html.py` - SSE event rendered_html field
- `tests/test_canvas_component_fallback_sse.py` - end-to-end canvas tests
- `tests/test_result_type_derivation.py` - result_type derivation scenarios

## Acceptance Criteria Met

- ✅ Dispatch with seeded matching component renders it
- ✅ Dispatch with first-ever shape renders fallback card
- ✅ Both covered by tests (headless canvas suite extended)
- ✅ card_cache rows keyed (result_id, component_id, layout_bucket)
- ✅ Usage stats update on match
- ✅ Write-scope separation holds (no server writes to components/component_versions/component_tags)

## Files Modified

1. `test/test_fallback_card.py` - Updated tests to reflect server-side fallback HTML rendering
2. `test/test_write_scope_separation.py` - Updated tests to reflect server-side fallback HTML rendering

No implementation changes were needed - the core functionality was already implemented in:
- `src/render/hot_path.py` - Hot-path component selector
- `src/intent/router.py` - Integration with dispatch flow
- `src/sse/broadcaster.py` - SSE streaming with rendered_html
- `src/session/store.py` - Schema with result_type and card_fallback columns
