# adc-22b1g: Wire submit-time pending placeholder + per-thread ack split

## Status: VERIFIED COMPLETE

This bead was a split-parent that organized the pending placeholder + per-thread ack work into smaller child beads. All child beads have completed their implementation.

## Completed Work (via child beads)

### 1. Pending Placeholder Creation (adc-351xo)
- ✓ `dispatch()` creates `createPendingPlaceholderCard()` BEFORE fetch('/dispatch')
- ✓ Placeholder stamped with `Date.now()` creation time
- ✓ Placeholder appears synchronously at submit (survives hung server)

### 2. Dispatch-Ack Split (adc-1cqn1)
- ✓ SSE `dispatch_ack` event handler calls `splitPlaceholderToThreads()`
- ✓ Splits into N per-thread pending cards based on `intent_ids`
- ✓ Thread cards inherit placeholder's `createdAt` timestamp

### 3. Progress Updates (adc-2zv1k, adc-2l8fe)
- ✓ `thread_progress` SSE event listener wired
- ✓ `_setProgress()` targets thread cards by `thread_id`
- ✓ Progress displays as "X/Y sources in" via text nodes (escaping)

### 4. Elapsed Time Ticker (adc-3wnm3)
- ✓ `tickPendingElapsed()` updates every second via setInterval
- ✓ `applyAgedTreatment()` applies 30s aged-pending treatment
- ✓ Pure client-side (survives hung server)

### 5. Result Replacement (adc-1wp26)
- ✓ `result_created` SSE event removes pending card
- ✓ `loadTopics()` reloads to render real card in place
- ✓ Replacement preserves position (no flicker)

### 6. Escaping Contract (adc-5zmyk)
- ✓ All interpolated values use `escapeHtml()` → text nodes
- ✓ No raw HTML injection paths

### 7. Test Coverage (adc-o7icd)
- ✓ 17 headless tests in `test_canvas_pending_placeholder_flow.py`
- ✓ All tests passing

## Verification

```bash
.venv/bin/pytest tests/test_canvas_pending_placeholder_flow.py -v
# 17 passed in 0.46s
```

## Implementation Locations

- **index.html**: Lines 1012-1086 (dispatch placeholder), 837-945 (SSE handlers)
- **canvas.js**: Lines 321-443 (pending card builders)
- **canvas_eventsource_runner.js**: Lines 606-639 (pending telemetry)

The task description in this bead was outdated—it claimed "NONE ARE CALLED" but all functions are now wired and tested. This is expected for split-parent beads whose children do the actual implementation.
