# Fence Detection in Intent Router

## Overview
Added fence detection logic to the intent router to detect when beads have been fenced (circuit breaker triggered) during intent processing.

## Implementation

### New Method: `_check_fence_for_bead()`
Located in: `src/intent/router.py`

Checks if a bead has been fenced by querying the `bead_watch` table for:
- `last_refusal_reason` (populated when a REFUSED: comment is detected)
- `fenced_at` (timestamp when circuit breaker tripped)

Returns fence context dict with:
- `bead_id`: The fenced bead reference
- `refusal_reason`: The most recent refusal reason
- `refusal_count`: Number of refusals recorded
- `fenced_at`: Timestamp when fence was applied

### New Method: `_create_stuck_card_from_fence()`
Located in: `src/intent/router.py`

Creates a stuck card when a fenced bead is detected, passing fence context:
- Links intent to topic
- Creates result with high urgency
- Broadcasts `TASK_STUCK` SSE event
- Includes fence metadata (bead_id, stuck_reason, refusal_count)

### Enhanced Method: `_escalate_to_bead()`
Located in: `src/intent/router.py`

Now checks for fenced beads at two points:

**Pre-Escalation Check:**
- Queries session for existing fenced beads via `get_fenced_beads_for_session()`
- If fenced beads found, creates stuck card instead of escalating
- Provides immediate feedback to user about blocked tasks

**Post-Escalation Check:**
- After bead creation, checks if newly created bead is immediately fenced
- Handles race condition where watcher daemon fences between escalate and check

### New Store Method: `get_fenced_beads_for_session()`
Located in: `src/session/store.py`

Returns all fenced beads for a session, joining `bead_watch` with `intents` to include context (intent_id, topic_id, project_slug).

## Acceptance Criteria Met

✅ **Detect fence event when last_refusal_reason is set**
- `_check_fence_for_bead()` checks for `last_refusal_reason` or `fenced_at`

✅ **Extract bead_id and reference from fenced bead**
- Returns fence_context with bead_id, refusal_reason, refusal_count, fenced_at

✅ **Pass fence context to stuck card creation**
- `_create_stuck_card_from_fence()` receives fence_context and creates stuck card

✅ **Detection integrated into intent router flow**
- `_escalate_to_bead()` checks for fenced beads before and after escalation

## Testing

Added comprehensive tests in `tests/test_fence_detection.py`:
- `test_check_fence_for_bead_with_refusal()` - Verifies fence detection when refusal reason set
- `test_check_fence_for_bead_not_fenced()` - Verifies returns None for non-fenced beads
- `test_check_fence_for_bead_not_found()` - Verifies handles missing beads
- `test_escalate_with_fenced_bead_in_session()` - Verifies pre-escalation fence check
- `test_create_stuck_card_from_fence()` - Verifies stuck card creation with fence context

All tests pass (5/5).

## Integration Flow

1. User sends utterance that classifies as task-profile
2. Intent router's `_escalate_to_bead()` is called
3. Router checks session for existing fenced beads
4. If fenced bead found:
   - Extract fence context (bead_id, refusal_reason, refusal_count)
   - Create stuck card with fence metadata
   - Broadcast TASK_STUCK SSE event
   - Return stuck status instead of escalating
5. If no fenced beads:
   - Proceed with normal escalation
   - Post-escalation fence check for race condition

## Related Files Modified

- `src/intent/router.py` - Added fence detection methods and enhanced escalation flow
- `src/session/store.py` - Added `get_fenced_beads_for_session()` method
- `tests/test_fence_detection.py` - New test file with 5 tests

## Notes

- Fence detection is non-blocking: errors in fence check log warnings but don't prevent escalation
- Post-escalation check handles race condition where watcher daemon fences bead between create and check
- Stuck cards are created with high urgency and include action hint for user
- SSE broadcast ensures all connected surfaces receive fence event
