# adc-5nze: No-Match Result Flag and Built-in Generic Fallback Card

## Status: ✅ COMPLETE

All acceptance criteria met and verified through comprehensive tests.

## Implementation Summary

### 1. Server-Side Component Selector (`src/render/hot_path.py`)
- **Match threshold**: 70% (`DEFAULT_MATCH_THRESHOLD = 0.7`)
- **Selection logic**: Deterministic lookup in `component_usage_patterns` by `result_type`
- **Fallback flag**: Returns `RenderOutcome(card_fallback=True)` when no component matches
- **Write scope**: Fallback path writes nothing to component DB (only real matches write `card_cache`)

### 2. Database Schema (`src/session/store.py`)
```sql
card_fallback INTEGER NOT NULL DEFAULT 0 CHECK(card_fallback IN (0, 1))
```
- Persists the fallback decision to the database
- Observable via `get_latest_result_for_topic()` and API responses
- Updatable via `update_result_card_fallback(result_id, card_fallback)`

### 3. Built-in Generic Fallback Card (`src/canvas/canvas.js`)
**Function**: `createFallbackCard(result)` (lines 783-813)
- **Visual**: Key/value grid over `result.data` + summary line
- **Badge**: Urgency indicator (critical/high/normal/low)
- **Icon**: 🗒️ (clipboard/list icon)
- **Data attribute**: `data-builtin="fallback"` for CSS selectors

### 4. Escaping Contract (`src/canvas/canvas.js`)
**Function**: `escapeHtml(text)` (lines 150-154)
```javascript
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}
```
- **All values** are HTML-escaped at render time
- **Text nodes only**: `el()` helper inserts content as text nodes, never raw HTML
- **Security**: Markup-like log lines render as literal text

### 5. Client-Side Rendering Decision (`src/canvas/canvas.js`)
**Function**: `createTopicCard(cardData)` (lines 71-88)
```javascript
if (latestResult && latestResult.card_fallback) {
    const fallbackCard = createFallbackCard(latestResult);
    fallbackCard.dataset.topicId = topic.id;
    fallbackCard.dataset.topicType = topic.type || 'adhoc';
    fallbackCard.dataset.cardFallback = '1';
    return fallbackCard;
}
```

## Acceptance Criteria Verification

### ✅ AC1: First-ever result shape renders the generic fallback card
- **Test**: `test_first_ever_result_shape_renders_fallback_card` (TC-FB-011)
- **Implementation**: Novel `result_type` → no component match → `card_fallback=True` → fallback card
- **Result**: Canvas shows fallback card, never blank

### ✅ AC2: Escaping holds for markup values
- **Test**: `test_html_escaping_end_to_end` (TC-FB-012)
- **Implementation**: `escapeHtml()` + text-node insertion via `el()` helper
- **Result**: `<script>alert("xss")</script>` renders as escaped text: `&lt;script&gt;...`

### ✅ AC3: Result is flagged for observability
- **Test**: `test_get_latest_result_includes_card_fallback` (TC-FB-004)
- **Flag name**: `card_fallback` (database column and API field)
- **Observability**: 
  - Database: `results.card_fallback` (0/1)
  - API: `/api/v1/sessions/{id}/topics` includes `card_fallback`
  - Canvas: `data-card-fallback` attribute on fallback cards

## Test Coverage

**13 tests** in `test/test_fallback_card.py`:
- TC-FB-001 to TC-FB-004: Card fallback persistence
- TC-FB-005 to TC-FB-006: Hot-path no-match detection  
- TC-FB-007 to TC-FB-008: Canvas fallback rendering
- TC-FB-009 to TC-FB-010: HTML escaping
- TC-FB-011 to TC-FB-012: Integration tests
- TC-FB-013 to TC-FB-015: Edge cases

**All tests passing** (13/13 ✅)

## Component Library Integration

The fallback card is one of **four built-in card families** shipped in `canvas.js`:
1. **Generic fallback** - `createFallbackCard()` (this implementation)
2. **First-run welcome** - `createWelcomeCard()`
3. **Pending/ack cards** - `createPendingPlaceholderCard()`, `createPendingThreadCard()`
4. **Error/clarification** - `createErrorCard()`

All built-in cards are exempt from component library seeding requirements (plan § Phase 5: Cold start & demo seed).

## Related Work

This implementation completes the hot-path selector and fallback rendering system that was split from parent bead adc-bmaz. The selector depends on:
- `result_type` derivation (adc-35zq: result_type column)
- Component library write scope separation (adc-2jvu: hot-path selector)
- Match/miss decision logic (this implementation: 70% threshold)

## Files Modified

**Core Implementation**:
- `src/render/hot_path.py` - Hot-path selector with fallback outcome
- `src/session/store.py` - `card_fallback` column and update method
- `src/canvas/canvas.js` - Fallback card renderer and escaping contract

**Tests**:
- `test/test_fallback_card.py` - Comprehensive test coverage

**Documentation**:
- `docs/plan/plan.md` - Component Library built-in generic fallback card (line 592)
- `notes/adc-5nze.md` - This summary
