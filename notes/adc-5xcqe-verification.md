# Verification: Stuck and Failed Card Rendering

**Bead:** adc-5xcqe
**Date:** 2026-07-23
**Status:** ✅ COMPLETE

## Acceptance Criteria Verification

### ✅ 1. Canvas renders stuck cards with 'Task stuck — needs your input' title
- **Location:** `src/canvas/canvas.js:663`
- **Implementation:** `createStuckCard()` function creates card with title "Task stuck — needs your input"
- **Verification:** Test `test_family_5_stuck_card_basic_rendering` passes

### ✅ 2. Canvas renders failed cards with 'Task failed' title
- **Location:** `src/canvas/canvas.js:724`
- **Implementation:** `createFailedCard()` function creates card with title "Task failed"
- **Verification:** Test `test_family_5_failed_card_basic_rendering` passes

### ✅ 3. Cards show bead_id, refusal_reason/failure_reason
- **Stuck cards:** `src/canvas/canvas.js:670-674` - displays `stuck_reason` in styled wrapper
- **Failed cards:** `src/canvas/canvas.js:731-735` - displays `failure_reason` in styled wrapper
- **Bead IDs:** Both card types show bead_id in metadata section
- **Verification:** Tests `test_family_5_stuck_card_basic_rendering` and `test_family_5_failed_card_basic_rendering` pass

### ✅ 4. Visual distinction between stuck (warning) and failed (error) states
- **Stuck card styling:** `src/canvas/index.html:404-443`
  - Border-left: 4px solid #f59e0b (amber/orange)
  - Background: #1a1a0f (warm dark)
  - Icon: 🚧 (construction sign)
  - Theme: Warning/amber throughout

- **Failed card styling:** `src/canvas/index.html:415-424`
  - Border-left: 4px solid #ef4444 (red)
  - Background: #1a0f0f (cool dark)
  - Icon: ❌ (X mark)
  - Theme: Error/red throughout

- **Verification:** Test `test_family_5_stuck_vs_failed_visual_distinction` passes

### ✅ 5. Cards surface in the active session view
- **SSE integration:** `src/canvas/index.html:1131-1184`
  - `task_stuck` event listener (lines 1131-1156) creates and prepends stuck cards
  - `task_failed` event listener (lines 1159-1184) creates and prepends failed cards
  - Both remove pending cards before rendering
  - Both clear loading/empty states
  - Both prepend to container (newest first)

- **Verification:** Tests `test_family_5_stuck_card_replaces_pending` and `test_family_5_failed_card_replaces_pending` pass

## Test Results

All 7 tests in `tests/e2e/test_canvas_stuck_failed_cards.py` pass:
- ✅ `test_family_5_stuck_card_basic_rendering` - Full stuck card with all fields
- ✅ `test_family_5_stuck_card_minimal_data` - Minimal stuck card
- ✅ `test_family_5_failed_card_basic_rendering` - Full failed card with all fields
- ✅ `test_family_5_failed_card_minimal_data` - Minimal failed card
- ✅ `test_family_5_stuck_vs_failed_visual_distinction` - Visual differences confirmed
- ✅ `test_family_5_stuck_card_replaces_pending` - SSE event flow
- ✅ `test_family_5_failed_card_replaces_pending` - SSE event flow

## Implementation Details

### Stuck Card Features
- Construction icon (🚧) with amber glow
- Title: "Task stuck — needs your input"
- Reason display in amber-themed wrapper
- Refusal count metadata
- Bead ID in monospace font
- Optional action hint text
- "View bead" button with amber styling and hover effects

### Failed Card Features
- X icon (❌) with red glow
- Title: "Task failed"
- Reason display in red-themed wrapper
- Error type badge
- Bead ID in monospace font
- Optional message text
- "Retry" button with red styling and hover effects

## Escaping Contract
All dynamic values (bead_id, reasons, messages) are rendered as text nodes via the `el()` helper, ensuring proper HTML escaping and preventing XSS attacks.

## Server Status
- Server running: `uvicorn src.main:app` on port 8000
- Health check: ✅ OK
- Ready for manual browser verification

## Conclusion
The stuck and failed card rendering implementation is **complete and fully verified**. All acceptance criteria are met, all tests pass, and the server is running for manual browser verification if needed.
