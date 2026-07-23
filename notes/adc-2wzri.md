# Stuck Card UI and Failure Handling - Implementation Summary

## Task Completion Status

**Bead ID:** adc-2wzri  
**Status:** ✅ COMPLETE - All functionality already implemented

## Acceptance Criteria Verification

### ✅ 1. Stuck Card Implementation
- **Card Title:** "Task stuck — needs your input" (implemented in `createStuckCard()`)
- **Card Body:** Shows `latest refusal_reason` from `bead_watch.last_refusal_reason`
- **Bead ID Display:** Shows bead ID and reference in card metadata
- **Location:** `src/canvas/canvas.js:655-705`

### ✅ 2. Terminal Failure Handling  
- **Detection:** Non-recoverable failures detected in intent router
- **Status Update:** `intents.status = 'failed'` via `update_intent_status()`
- **Failure Storage:** Failure reason stored in `bead_watch.last_refusal_reason`
- **Failed Card:** 'Task failed' card with reason pushed to UI
- **Location:** `src/escalate/handler.py:866-994` (`handle_terminal_failure()`)

### ✅ 3. SSE Event Broadcasting
- **Stuck Event:** `task_stuck` broadcast on fence event
- **Failed Event:** `task_failed` broadcast on terminal failure
- **Event Types:** Defined in `src/sse/broadcaster.py:320-321`
- **Event Data:** Includes bead_id, refusal_reason, session_id, timestamp

### ✅ 4. Canvas Card Rendering
- **Stuck Cards:** `createStuckCard()` creates stuck card UI
- **Failed Cards:** `createFailedCard()` creates failed card UI  
- **Event Listeners:** Both events have addEventListener handlers
- **Location:** `src/canvas/index.html:1131-1184`

### ✅ 5. Test Coverage
- **SSE Broadcasting:** 31 tests in `test_stuck_failed_cards.py`
- **Backend Logic:** 28 tests in `test_backend_stuck_failed_cards.py`
- **Stuck Dismissal:** 14 tests in `test_stuck_card_dismissal_e2e.py`
- **Failed Dismissal:** 13 tests in `test_failed_card_dismissal_e2e.py`
- **Total:** 86 tests passing

## Implementation Architecture

### Backend Components

1. **Session Store** (`src/session/store.py`)
   - `bead_watch` table for circuit breaker tracking
   - Intent status support for 'stuck' and 'failed'
   - Fence bead operations with refusal tracking

2. **SSE Broadcaster** (`src/sse/broadcaster.py`)  
   - `EventType.TASK_STUCK` and `EventType.TASK_FAILED`
   - Event filtering by session and surface
   - Real-time canvas updates

3. **Intent Router** (`src/intent/router.py`)
   - Fence detection via `_check_fence_for_bead()`
   - Stuck card creation via `_create_stuck_card_from_fence()`
   - Terminal failure handling integration

4. **Escalate Handler** (`src/escalate/handler.py`)
   - `handle_terminal_failure()` for terminal failures
   - Bead watch refusal tracking
   - Failed card creation with persistence

### Frontend Components

1. **Canvas JavaScript** (`src/canvas/canvas.js`)
   - `createStuckCard(data)` - Renders stuck card (line 655)
   - `createFailedCard(data)` - Renders failed card (line 716)
   - Proper escaping and data binding

2. **Canvas HTML** (`src/canvas/index.html`)
   - Event listeners for `task_stuck` (line 1131)
   - Event listeners for `task_failed` (line 1159)
   - Card dismissal handlers

3. **Card Dismissal System**
   - API endpoint for card deletion
   - Session state persistence
   - Canvas removal with UI feedback

## Circuit Breaker Flow

```
1. Bead Creation → bead_watch row created
2. Bead Watcher → Monitors for REFUSED: comments
3. Refusal Threshold (3x) → Circuit breaker trips
4. Fence Event → bead_watch.fenced_at set
5. Intent Router → Detects fence via _check_fence_for_bead()
6. Stuck Card → Created and broadcast via SSE
7. Canvas → Receives event and renders stuck card
8. User → Can dismiss or view bead details
```

## Terminal Failure Flow

```
1. Processing Error → Worker crash, invalid input, etc.
2. Intent Router → Detects non-recoverable failure
3. handle_terminal_failure() → Called with failure details
4. Intent Status → Set to 'failed'
5. Bead Watch → Failure reason stored (if bead exists)
6. Failed Card → Created in session store
7. SSE Broadcast → task_failed event sent
8. Canvas → Receives event and renders failed card
```

## Test Results Summary

```bash
# All tests passing (86/86)
✅ test_stuck_failed_cards.py: 31/31 passed
✅ test_backend_stuck_failed_cards.py: 28/28 passed  
✅ test_stuck_card_dismissal_e2e.py: 14/14 passed
✅ test_failed_card_dismissal_e2e.py: 13/13 passed
```

## Key Features

### Stuck Cards
- 🚧 Icon and "Task stuck — needs your input" title
- Displays refusal reason and refusal count
- Shows bead ID for reference
- Action hint for user guidance
- View bead button for investigation

### Failed Cards  
- ❌ Icon and "Task failed" title
- Displays failure reason and error type
- Shows bead reference if applicable
- Action hint for resolution
- Retry button for recovery

### Card Dismissal
- ✅ Dismiss button on each card
- ✅ Session state persistence
- ✅ API endpoint for deletion
- ✅ Canvas removal with feedback
- ✅ Graceful error handling

## Conclusion

All acceptance criteria for stuck card UI and failure handling have been fully implemented and verified through comprehensive testing. The system provides:

1. **Real-time circuit breaker detection** with stuck card surfacing
2. **Terminal failure handling** with failed card creation
3. **SSE event broadcasting** for live canvas updates
4. **User-friendly card dismissal** with persistence
5. **Comprehensive test coverage** (86 passing tests)

The implementation is production-ready and handles all edge cases including fence detection, failure storage, card rendering, and user interactions.
