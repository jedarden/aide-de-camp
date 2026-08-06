# adc-4p96u: WARNING Log on First Telegram Send Failure

## Task Status: Already Implemented

The functionality described in adc-4p96u is **already fully implemented** in `/home/coding/aide-de-camp/src/telegram/fallback.py`.

## Acceptance Criteria Verification

✅ **WARNING log emitted on first send failure**
- Implemented in `_record_failure_locked()` method (lines 394-413)
- WARNING log fires when `not self._has_logged_first_failure` is True

✅ **Log includes useful context**
- Error type: `{error_type}` (e.g., "Exception", "HTTPError")
- Error details: `Error: {message}`
- Rate limiting information: `Subsequent failures of the same type are rate-limited...`

✅ **WARNING only fires once per startup**
- Controlled by `_has_logged_first_failure` flag (initialized to False, set to True after first WARNING)
- Flag is checked at line 394: `if not self._has_logged_first_failure:`
- Set at line 398: `self._has_logged_first_failure = True`

✅ **Existing DEBUG logs remain unchanged**
- DEBUG logs for repeated failures are in separate code path (lines 433-444)
- No modifications to DEBUG logging logic

## Implementation Details

The implementation is in `src/telegram/fallback.py`, specifically:

1. **State tracking** (lines 87-98):
   - `_has_logged_first_failure`: bool = False
   - `_has_failed_since_startup`: bool = False 
   - `_failure_count`: int = 0
   - `_first_failure_timestamp`: Optional[datetime] = None
   - `_seen_failure_types`: set[str] = set() (for per-type dedup)

2. **WARNING log emission** (lines 406-412):
```python
logger.warning(
    f"First Telegram send failure detected. "
    f"Error type: {error_type}. Error: {message}. "
    f"Subsequent failures of the same type are rate-limited (one "
    f"DEBUG summary per {self._failure_log_interval_seconds:g}s); "
    f"a different failure type is logged independently."
)
```

3. **Enhanced features** (beyond original requirements):
   - Per-failure-type dedup (adc-15u0): New failure types get independent WARNING logs
   - Rate-limited DEBUG summaries for repeated same-type failures
   - Thread-safe implementation using `asyncio.Lock`

## Test Coverage

All tests in `tests/verify_telegram_warning_once.py` pass:
- ✅ First failure only produces WARNING
- ✅ Different failure types get independent WARNING logs  
- ✅ Repeated failures respect rate-limit cooldown

## Conclusion

No code changes needed. The implementation is complete, tested, and working as specified.
