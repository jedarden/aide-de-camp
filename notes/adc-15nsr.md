# adc-15nsr: Wire per-source progress and elapsed time SSE updates

## Status: Already Completed

This bead's work was already completed in prior commits:
- `adc-2l8fe` (2026-07-22): Implemented `_setProgress()` targeting by `thread_id` in `thread_progress` event handler
- `adc-3wnm3` (2026-07-22): Verified elapsed time updates already implemented
- `adc-5zmyk` (2026-07-22): Applied `escapeHtml()` to all interpolated card values
- `adc-2l7pv` (2026-07-22): Added headless tests for thread_progress SSE events

## Implementation Verified

### SSE Event Handlers (src/canvas/index.html)
1. **thread_progress event** (lines 873-901)
   - Listens for `thread_progress` events from server
   - Extracts `thread_id`, `completed`, and `total` from event data
   - Finds the matching pending card via `querySelector('[data-pending-id="' + threadId + '"]')`
   - Calls `_setProgress(threadCard, { completed, total })` to update progress display

2. **progress_update event** (lines 904-927)
   - Alternative event name for progress updates
   - Uses `intent_id` to find the matching thread card
   - Calls `_setProgress()` to update progress

3. **Elapsed-time ticker** (lines 949-959)
   - Runs every second via `setInterval()`
   - Finds all pending cards with `document.querySelectorAll('.pending-card[data-pending-id]')`
   - Calls `tickPendingElapsed(card, now)` to update elapsed time counter
   - Calls `applyAgedTreatment(card, now)` to apply aged treatment if over 30s

### Canvas Functions (src/canvas/canvas.js)
1. **`_setProgress(card, progress)`** (lines 407-416)
   - Uses `node.textContent` to set progress text (e.g., "3/5 sources in")
   - Properly escapes all values via `textContent` (XSS protection)
   - Stores `completed` and `total` in `dataset` attributes
   - Hides progress element when `total` is 0

2. **`tickPendingElapsed(card, now)`** (lines 423-429)
   - Calculates elapsed time from `data-created-at` timestamp
   - Uses `node.textContent` to set elapsed time text (e.g., "12s elapsed")
   - Properly escapes all values via `textContent`

3. **`applyAgedTreatment(card, now)`** (lines 436-443)
   - Applies aged treatment when elapsed time exceeds 30s threshold
   - Toggles `.aged` class on the card
   - Shows/hides the aged note with retry button

## Acceptance Criteria Met

✅ Per-thread card updates with 'X/Y sources in' progress message
✅ Elapsed time counter updates per-thread card (e.g., 'elapsed: 12s')
✅ All text content is escaped via `escapeHtml()` (via `textContent`)
✅ Updates target correct card by `thread_id`
✅ Headless test verifies progress updates appear (all 11 tests pass)

## Test Results

```
tests/test_canvas_progress_updates.py::TestThreadProgressEvent::test_thread_progress_updates_card_by_thread_id PASSED
tests/test_canvas_progress_updates.py::TestThreadProgressEvent::test_thread_progress_targets_correct_thread_among_many PASSED
tests/test_canvas_progress_updates.py::TestElapsedTimeCounter::test_thread_progress_includes_elapsed_time_footer PASSED
tests/test_canvas_progress_updates.py::TestElapsedTimeCounter::test_elapsed_time_counter_on_initial_thread_card PASSED
tests/test_canvas_progress_updates.py::TestXSSProtection::test_progress_values_escaped_via_escapeHtml PASSED
tests/test_canvas_progress_updates.py::TestXSSProtection::test_all_interpolated_values_use_escapeHtml PASSED
tests/test_canvas_progress_updates.py::TestProgressAndTimeTogether::test_progress_and_elapsed_time_work_together PASSED
tests/test_canvas_progress_updates.py::TestProgressAndTimeTogether::test_multiple_progress_updates_keep_elapsed_time_visible PASSED
tests/test_canvas_progress_updates.py::TestProgressUpdateEdgeCases::test_multiple_thread_progress_events_increment_card PASSED
tests/test_canvas_progress_updates.py::TestProgressUpdateEdgeCases::test_progress_with_zero_total_hides_progress_element PASSED
tests/test_canvas_progress_updates.py::TestProgressUpdateEdgeCases::test_progress_updates_only_target_thread_not_others PASSED
```

All 11 tests pass in 0.30s.
