# Bead adc-c3heg: State Tracker mark_as_unreachable() Implementation

## Task
Implement `state_tracker.mark_as_unreachable()` call on failure in the exception handler.

## Finding
The `state_tracker.mark_as_unreachable()` call is **already fully implemented** in the current codebase. All acceptance criteria are met.

## Implementation Locations

### 1. Exception Handler in `check_telegram_available()` (line 272-284)
```python
except Exception as e:
    # STATE UPDATE FIRST - Mark as unreachable before logging
    self._state_tracker.mark_as_unreachable(datetime.now())
    self._set_reachable(False)

    # LOGGING AFTER STATE UPDATE - Capture error context
    error_type = type(e).__name__
    error_message = str(e) or "unknown error"
    logger.warning(...)
```
- **State update**: Line 274
- **Logging**: Lines 277-283 (after state update)
- **Timestamp**: `datetime.now()` passed directly

### 2. Failure Handler in `_record_failure_locked()` (line 384-520)
```python
def _record_failure_locked(self, error, error_context, url) -> bool:
    now = datetime.now()
    self._set_reachable(False, now=now)

    # STATE UPDATE FIRST - Update state tracker for reachability and deduplication
    # This MUST be called before any logging to ensure state is updated first
    self._state_tracker.mark_as_unreachable(now)

    # Capture exception context for logging
    if error is not None:
        error_type = type(error).__name__
        error_message = str(error) or error_context or "unknown error"
```
- **State update**: Line 427
- **Logging**: Line 441+ (after state update)
- **Timestamp**: `now = datetime.now()` at line 422, passed to `mark_as_unreachable(now)`

### 3. Other Call Sites
- Line 251: `check_telegram_available()` when bot_token is None
- Line 269: `check_telegram_available()` when HTTP response is not 200

## Acceptance Criteria Status

| Criterion | Status | Location |
|-----------|--------|----------|
| state_tracker.mark_as_unreachable() called on send failure | ✅ | Line 427 (`_record_failure_locked`) |
| Current timestamp (datetime.now()) passed as parameter | ✅ | Lines 251, 269, 274, 427 |
| State update occurs before logging statements | ✅ | All locations update before logging |
| State unreachable flag set on first failure in streak | ✅ | Handled by `BridgeState.mark_as_unreachable()` |
| Error context (exception) still available for logging | ✅ | Error captured before state update, used in logging |

## Related Code

- **Main implementation**: `src/telegram/fallback.py:427` (`_record_failure_locked`)
- **Exception handler**: `src/telegram/fallback.py:272-284` (`check_telegram_available`)
- **State tracker module**: `src/telegram/state_tracker.py`
- **Import statement**: `src/telegram/fallback.py:16` (`from .state_tracker import BridgeState`)

## Architecture

The implementation follows the correct order of operations:

1. **State update FIRST** (`mark_as_unreachable()`)
2. **Error context capture** (type, message)
3. **Logging AFTER state update** (with full error context)

This ensures that:
- State is always updated before any logging occurs
- Error information is preserved and available for logging
- The failure streak tracking works correctly via `BridgeState`

## Conclusion

All requirements for bead adc-c3heg are fully implemented. The code already:
1. Imports the state_tracker module (line 16)
2. Calls `mark_as_unreachable()` with `datetime.now()` on all failure paths
3. Performs state updates before logging
4. Preserves error context for logging after the state update

No changes were required - this bead validates existing implementation.

## Timestamp
2026-08-06
