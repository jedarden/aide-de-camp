# adc-2yygc: First-Failure WARNING Logging with Deduplication

## Summary
Fixed duplicate WARNING logs in Telegram send failure handling by consolidating to a single source of truth: the state tracker.

## Problem
The code had two overlapping WARNING mechanisms that both fired on the first failure:
1. **State tracker WARNING** (`should_log_failure()`): Logs once per failure streak
2. **Per-startup WARNING** (`_has_logged_first_failure`): Logs once per process startup

This resulted in duplicate WARNING messages on the first send failure.

## Solution
Removed the duplicate WARNING from the per-startup logic (lines 439-456 in `fallback.py`). The state tracker now provides the single, canonical WARNING for first failures.

The per-startup logic still tracks failure types and rate-limiting, but no longer logs the duplicate WARNING.

## Implementation Details

### Files Modified
- `src/telegram/fallback.py`: Removed duplicate WARNING from `_record_failure_locked()`
- `tests/test_telegram_e2e_logging.py`: Updated test to match new WARNING message format

### Key Changes
1. **Removed** the WARNING log from the per-startup logic block (lines 439-456)
2. **Kept** all other per-startup tracking (failure types, rate-limiting, timestamps)
3. **Updated** test assertions to match the state tracker's WARNING format

### WARNING Message Format
The canonical WARNING now comes from the state tracker (lines 414-424):
```
Telegram bridge unreachable: send failed. Error type: {error_type}. Error: {message}. Bridge may be down or network issue.
```

## Acceptance Criteria Met
✅ First failed send after startup/reachability logs WARNING clearly
✅ WARNING includes helpful context (error type, error message, bridge status)
✅ Subsequent failures in the same streak do NOT log additional WARNINGs (no spam)
✅ State is correctly updated on each failure
✅ Successful sends reset the unreachable state (via `state_tracker.mark_as_reachable()`)

## Test Results
All tests pass:
- `tests/test_telegram_state_tracker.py`: 26 passed
- `tests/test_telegram_e2e_logging.py`: 11 passed
- `tests/verify_telegram_warning_once.py`: All scenarios passed

## Why This Approach
The state tracker provides a cleaner abstraction for reachability-based logging:
- Tracks failure streaks automatically
- Resets on successful sends
- Provides `should_log_failure()` method that encapsulates the deduplication logic

The per-failure-type dedup (adc-15u0) remains intact and logs its own WARNING when a different error type appears during an ongoing outage.
