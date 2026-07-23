# Bead adc-1cqn1: Dispatch-ack SSE Event Splitting Verification

## Task
Wire dispatch-ack SSE event to split placeholder into per-thread cards

## Implementation Status
**COMPLETE** - The implementation was already present in the codebase from the parent bead (adc-351xo).

## Verification

### Acceptance Criteria Met
1. ✅ **dispatch-ack event triggers splitPlaceholderToThreads()** - Implemented in `src/canvas/index.html` line 852
2. ✅ **N per-thread cards appear on canvas (N from event payload)** - Verified by test
3. ✅ **Each per-thread card has thread_id and shows initial pending state** - Verified by test
4. ✅ **Original single placeholder is removed or replaced** - Implemented in `src/canvas/index.html` lines 860-865
5. ✅ **Headless test verifies split on ack event** - Test passes: `test_dispatch_ack_splits_placeholder_into_thread_cards`

### Code Review
The `dispatch_ack` event listener in `src/canvas/index.html` (lines 837-870):
- Parses event data for `utterance_id`, `intent_ids`, and `utterance`
- Finds the existing placeholder from `pendingPlaceholders` tracking
- Calls `splitPlaceholderToThreads(utterance, createdAt, intentIds)` to create N thread cards
- Replaces the placeholder with thread cards (or prepends if no placeholder exists)
- Removes placeholder from tracking

### Test Results
```bash
.venv/bin/python -m pytest tests/test_canvas_eventsource_reconnect.py::TestPendingAckCards::test_dispatch_ack_splits_placeholder_into_thread_cards -xvs
```
Result: **PASSED** - The test validates that when a dispatch_ack event arrives with intent_ids, the placeholder splits into per-thread pending cards (one per intent_id).

## Conclusion
The dispatch-ack SSE event splitting functionality is fully implemented and tested. This bead's acceptance criteria are met by the existing implementation from the parent bead (adc-351xo).

## Related Files
- `src/canvas/index.html` - Contains the dispatch_ack event listener
- `src/canvas/canvas.js` - Contains `splitPlaceholderToThreads()` function
- `tests/test_canvas_eventsource_reconnect.py` - Contains headless tests
- `tests/e2e/canvas_eventsource_runner.js` - Test harness for SSE events
