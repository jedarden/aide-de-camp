# adc-35eq: Stream rendered card HTML via SSE and extend headless canvas tests

## Completion Status: COMPLETE

This bead was completed via its split-child bead **adc-30pud** (commit `69b2917`).

## Acceptance Criteria - All Met ✓

### ✓ Component match renders via SSE
- Dispatch with a seeded matching component renders the real component card via SSE
- Component HTML is injected into canvas.js via `rendered_html` field
- Asserted by headless browser tests (`test_component_match_includes_rendered_html_in_sse`)

### ✓ Fallback renders via SSE
- Dispatch with a first-ever shape (no component match) renders the generic fallback card via SSE
- Fallback HTML is generated server-side and streamed via SSE
- Asserted by headless browser tests (`test_no_component_match_includes_rendered_html_in_sse`)

### ✓ Both paths covered in automated tests
- All 9 tests in `test_canvas_component_fallback_sse.py` passing
- Tests cover component path, fallback path, and mixed scenarios
- Tests verify canvas never blanks for either path

### ✓ Novel shape never blanks canvas
- `test_component_path_never_blanks_canvas` - component path invariant
- `test_fallback_path_never_blanks_canvas` - fallback path invariant
- `test_mixed_cards_never_blank_canvas` - both paths coexist

## Implementation Details

### SSE Render Path (Component)
1. Hot-path renderer generates component HTML and stores in `rendered_html` field
2. `/dispatch` endpoint extracts `rendered_html` and passes to `SSEEvent`
3. SSE broadcaster includes `rendered_html` in event payload
4. Canvas injects `rendered_html` directly into component card

### SSE Render Path (Fallback)
1. Hot-path renderer calls `render_fallback_card()` when no component match
2. Fallback HTML is generated server-side with proper escaping
3. Fallback HTML flows through SSE via `rendered_html` field
4. Canvas renders fallback card directly from injected HTML

### Files Modified (via adc-30pud, adc-6bsmx, adc-3lgj3)
- `src/canvas/canvas.js` - inject rendered_html into component cards
- `src/intent/router.py` - pass rendered_html through dispatch
- `src/render/hot_path.py` - generate component and fallback HTML
- `src/realtime/dispatch.py` - pass rendered_html to canvas via SSE
- `src/realtime/continuity.py` - accept rendered_html parameter
- `src/sse/broadcaster.py` - include rendered_html in SSEEvent
- `tests/test_canvas_component_fallback_sse.py` - comprehensive test suite

## Tests Passing
```
tests/test_canvas_component_fallback_sse.py::TestComponentCardViaSSE::test_component_match_includes_rendered_html_in_sse PASSED
tests/test_canvas_component_fallback_sse.py::TestComponentCardViaSSE::test_component_card_renders_from_sse_event PASSED
tests/test_canvas_component_fallback_sse.py::TestComponentCardViaSSE::test_component_path_never_blanks_canvas PASSED
tests/test_canvas_component_fallback_sse.py::TestFallbackCardViaSSE::test_no_component_match_includes_rendered_html_in_sse PASSED
tests/test_canvas_component_fallback_sse.py::TestFallbackCardViaSSE::test_fallback_card_renders_from_sse_event PASSED
tests/test_canvas_component_fallback_sse.py::TestFallbackCardViaSSE::test_fallback_path_never_blanks_canvas PASSED
tests/test_canvas_component_fallback_sse.py::TestBothPathsCoexist::test_component_and_fallback_cards_render_together PASSED
tests/test_canvas_component_fallback_sse.py::TestBothPathsCoexist::test_mixed_cards_never_blank_canvas PASSED
tests/test_canvas_component_fallback_sse.py::test_dom_runner_targets_real_canvas_module PASSED
======================== 9 passed, 4 warnings in 1.46s ========================
```

## Dependency Chain
- adc-35eq depends on adc-5nze (no-match result flag + generic fallback) - CLOSED
- adc-35eq depends on adc-30pud (extend headless canvas tests) - CLOSED
- adc-30pud depends on adc-6bsmx (wire fallback render HTML) - CLOSED
- adc-30pud depends on adc-3lgj3 (wire component render HTML) - CLOSED

All dependencies complete. Ready to close.
