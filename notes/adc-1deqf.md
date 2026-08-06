# Task adc-1deqf: First-Failure Warning with State Tracking

**Status: ✅ ALREADY IMPLEMENTED**

## Summary

This task requested adding first-failure warning with state tracking for Telegram send failures. Upon investigation, the feature has already been fully implemented in the `TelegramFallback` class.

## Implementation Location

`src/telegram/fallback.py` - Lines 79-456

## State Tracking (lines 79-111)

The bridge state tracker includes:

- `_is_reachable: bool | None` - Current reachability state (None=unknown, True=reachable, False=unreachable)
- `_last_check_time: datetime | None` - When reachability was last determined
- `_has_logged_first_failure: bool` - Whether first-failure WARNING has been emitted (one per startup)
- `_has_failed_since_startup: bool` - Flag indicating if any failure occurred since service start
- `_failure_count: int` - Total number of failures
- `_first_failure_timestamp: datetime | None` - First failure time (set-once)
- `_last_failure_timestamp: datetime | None` - Most recent failure time
- `_seen_failure_types: set[str]` - Distinct failure types already logged this startup
- `_last_repeated_log_timestamp: datetime | None` - For rate-limiting repeated logs
- `_failures_since_last_log: int` - Count of failures since last repeated log

## First-Failure WARNING Logging (lines 403-421)

When a failure occurs and `_has_logged_first_failure` is False:

1. Sets `_has_logged_first_failure = True`
2. Sets `_has_failed_since_startup = True`
3. Records `_first_failure_timestamp`
4. Adds error type to `_seen_failure_types`
5. Seeds rate-limit window from now
6. Logs WARNING with error type and message

Example log:
```
WARNING telegram.fallback: First Telegram send failure detected. Error type: Exception. Error: Connection timeout. Subsequent failures of the same type are rate-limited (one DEBUG summary per 300s); a different failure type is logged independently.
```

## State Updates on Failures (lines 388-392)

Every failure updates:
- `_is_reachable` set to False
- `_last_check_time` updated to now
- `_failure_count` incremented
- `_last_failure_timestamp` updated
- `_failures_since_last_log` incremented

## Deduplication to Prevent Spam (lines 423-456)

Two mechanisms prevent log spam:

1. **Per-failure-type dedup**: Different failure types (HTTPError, RequestError, etc.) each get their own independent WARNING, so a new failure mode is never swallowed

2. **Rate-limited repeated failures**: Failures of an already-seen type are counted silently during a cooldown window (default 300s). When the window elapses, a single DEBUG summary reports the batch

## Integration Points

1. **Startup check** (`main.py` lines 157-169): Calls `check_telegram_available()` to establish initial reachability state

2. **Runtime failures** (`fallback.py` lines 157, 161-164, 231-258):
   - Non-2xx HTTP responses → `_handle_send_failure()`
   - `httpx.RequestError` exceptions → `_handle_send_failure()`
   - Other exceptions → `_handle_send_failure()`
   - Success → `_set_reachable(True)`

## Verification

All acceptance criteria met:

- ✅ First failed send after startup logs WARNING clearly
- ✅ Subsequent failures don't repeat the same WARNING (no spam)
- ✅ State tracks bridge reachability over time
- ✅ Works with both startup reachability and runtime failures

Test coverage: `tests/verify_telegram_warning_once.py` - All tests pass
