# Verification: WARNING Logs Only on First Failure

**Task:** Verify WARNING logs appear only on the first Telegram send failure
**Date:** 2026-08-06
**Status:** ✅ Complete

## Implementation Verified

The `src/telegram/fallback.py` implementation correctly handles WARNING log deduplication:

### First Failure Behavior
- Logs exactly one WARNING with error context (type and message)
- Sets `_has_logged_first_failure = True`
- Seeds the rate-limit window (`_last_repeated_log_timestamp`)
- Tracks the failure type in `_seen_failure_types`

### Subsequent Same-Type Failures
- **No WARNING logged** - counted silently
- Increment `_failure_count` and `_last_failure_timestamp`
- Respect the cooldown window (default 300s, configurable)
- After cooldown, emit a DEBUG summary instead

### Different Failure Types
- Each new failure type gets its own independent WARNING
- Per-failure-type deduplication (adc-15u0)
- New types are never swallowed by the ongoing outage cooldown

## Test Results

All tests passed successfully:

- Test 1: First failure only produces WARNING - PASSED
- Test 2: Different failure types get independent WARNINGs - PASSED  
- Test 3: Repeated failures respect rate-limit cooldown - PASSED

## Evidence

**First failure (WARNING):**
```
WARNING telegram.fallback: First Telegram send failure detected. Error type: Exception. Error: Connection timeout. Subsequent failures of the same type are rate-limited (one DEBUG summary per 300s); a different failure type is logged independently.
```

**Second failure (silent):**
No WARNING log - failure counted only.

**Different failure type (independent WARNING):**
```
WARNING telegram.fallback: New Telegram send failure type during ongoing outage: HTTPError. Error: HTTP 500 Internal Server Error. Logged independently of the 300s same-type cooldown. (Total failures: 2; distinct failure types: 2.)
```

**After cooldown (DEBUG summary):**
```
DEBUG telegram.fallback: Repeated Telegram send failures: 2 failure(s) since last log (total 3). Latest error type: Exception. Error: Error 3.
```

## Test Script

`tests/verify_telegram_warning_once.py` - Comprehensive test suite covering:
1. First failure only produces WARNING
2. Different failure types get independent WARNINGs
3. Repeated failures respect rate-limit cooldown

Executed with: `.venv/bin/python tests/verify_telegram_warning_once.py`

## Conclusion

✅ All acceptance criteria met:
- First failure produces WARNING with error context
- Second failure does NOT produce another WARNING
- Logs readable in standard logging output
- Evidence added to bead body

The implementation correctly prevents log spam while ensuring each distinct failure type is properly surfaced with its own WARNING log.
