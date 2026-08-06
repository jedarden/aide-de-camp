# Telegram Send Code and Error Handling Analysis

**Task ID:** adc-10abv  
**Date:** 2026-08-06  
**Purpose:** Locate all Telegram send code and document current error handling paths

---

## Executive Summary

All Telegram sends go through a single centralized `TelegramFallback` class in `src/telegram/fallback.py`. The error handling implements sophisticated rate-limited logging to prevent log spam during sustained outages, with per-failure-type deduplication.

---

## 1. Core Send Methods

### 1.1 Primary Send Method: `send_message()`

**Location:** `src/telegram/fallback.py:112-164`

This is the only method that actually makes HTTP requests to the Telegram Bot API. All other send methods route through this one.

```python
async def send_message(
    self,
    chat_id: int | str,
    message: str,
    parse_mode: str = "HTML",
) -> bool
```

**Key behavior:**
- Returns `True` on successful send
- Returns `False` on any failure
- Calls `_handle_send_failure()` for all error cases
- Updates reachability state (`_set_reachable(True/False)`)

**Error cases:**
1. **No bot_token configured** (line 129-134)
   - Logs: WARNING "send_message() called - no Telegram bot token configured"
   - Returns: `False`

2. **HTTP non-200 response** (line 154-157)
   - Logs: Via `_handle_send_failure()` with status code and response text
   - Returns: `False`

3. **httpx.RequestError** (line 159-161)
   - Logs: Via `_handle_send_failure()` with exception
   - Returns: `False`

4. **Any other exception** (line 162-164)
   - Logs: Via `_handle_send_failure()` with exception
   - Returns: `False`

---

## 2. Higher-Level Send Methods

### 2.1 `send_result()`

**Location:** `src/telegram/fallback.py:166-177`

Formats a structured result dict and delegates to `send_message()`.

**Not currently called anywhere in the codebase** (excluding tests).

### 2.2 `send_exception()`

**Location:** `src/telegram/fallback.py:179-202`

Intended for pushing exceptions to Telegram for human attention.

**Not currently called anywhere in the codebase** (excluding tests).

**Error handling if no chat_id configured:**
- Logs: WARNING with session_id
- Returns: `False`

### 2.3 `send_workload_summary()`

**Location:** `src/telegram/fallback.py:204-227`

Intended for sending workload summaries to Telegram.

**Not currently called anywhere in the codebase** (excluding tests).

**Error handling if no chat_id configured:**
- Logs: WARNING with session_id
- Returns: `False`

---

## 3. Error Handling Implementation

### 3.1 Failure Handler: `_handle_send_failure()`

**Location:** `src/telegram/fallback.py:310-330`

Entry point for reactive failure detection. Called ONLY from `send_message()`'s failure branches.

**Behavior:**
- Acquires lock to serialize first-failure claim
- Delegates to `_record_failure_locked()`
- No return value

### 3.2 Failure Recording: `_record_failure_locked()`

**Location:** `src/telegram/fallback.py:343-441`

Implements sophisticated rate-limited logging policy with per-failure-type deduplication (adc-15u0).

**State tracked:**
- `_has_logged_first_failure` (bool) - claim flag, one per startup
- `_failure_count` (int) - total failures
- `_first_failure_timestamp` (datetime) - set once
- `_last_failure_timestamp` (datetime) - updated every failure
- `_seen_failure_types` (set[str]) - distinct failure types this startup
- `_failures_since_last_log` (int) - dedup counter for current window
- `_last_repeated_log_timestamp` (datetime) - rate-limit window start

**Logging policy:**

1. **First failure after startup** (line 390-408)
   - Level: WARNING
   - Includes: Error type name + message
   - Sets: `_has_logged_first_failure = True`
   - Adds: Error type to `_seen_failure_types`
   - Seeds: Rate-limit window so WARNING isn't immediately followed by DEBUG storm
   - Emits: "First Telegram send failure detected. Error type: {error_type}. Error: {message}. Subsequent failures of the same type are rate-limited..."

2. **New failure type during ongoing outage** (line 410-426)
   - Level: WARNING
   - Condition: `error_type not in _seen_failure_types`
   - Logged immediately and independently - never swallowed by same-type cooldown
   - Adds: Error type to `_seen_failure_types`
   - Reseeds: Rate-limit window for this type
   - Emits: "New Telegram send failure type during ongoing outage: {error_type}. Error: {message}. Logged independently of the {interval}s same-type cooldown."

3. **Repeated failure of already-seen type** (line 428-440)
   - Level: DEBUG (not WARNING)
   - Condition: Rate-limit window elapsed (default: 300 seconds)
   - Otherwise: Counted silently to avoid log spam
   - Emits: "Repeated Telegram send failures: {batch} failure(s) since last log (total {failure_count}). Latest error type: {error_type}. Error: {message}."

**Rate-limit interval:**
- Default: 300 seconds (5 minutes)
- Configurable via: `ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS` env var
- Stored in: `_failure_log_interval_seconds`

### 3.3 Reset Method: `reset_first_failure_state()`

**Location:** `src/telegram/fallback.py:443-460`

Re-arms first-failure detection for testing and future recovery-based reset hooks.

**Resets:**
- `_has_logged_first_failure = False`
- `_first_failure_timestamp = None`
- `_last_repeated_log_timestamp = None`
- `_failures_since_last_log = 0`
- `_seen_failure_types.clear()`

**Retains:**
- `_failure_count` (diagnostic counter)
- `_last_failure_timestamp` (diagnostic)

---

## 4. Send Call Sites

### 4.1 Bead Watcher Daemon: `_send_to_telegram()`

**Location:** `src/watcher/daemon.py:1151-1174`

This is the ONLY active Telegram send call site (excluding tests).

**Called from:**
1. `_create_stuck_card()` (line 732) - Stuck task cards
2. `_broadcast_monitoring_result()` (line 1577) - Ambient monitoring results

**Behavior:**
- Uses shared `TelegramFallback` singleton (via `get_telegram_fallback()`)
- Checks for `chat_id` configuration
- Logs WARNING if no chat_id configured
- Returns `False` on configuration failure
- Formats result via `_format_telegram_message()`
- Delegates to `fallback.send_message()`

**Error path if no chat_id:**
```
WARNING: Cannot send result to Telegram for session {session_id}: 
no Telegram chat id configured (set ADC_TELEGRAM_CHAT_ID). 
Result push skipped.
```

### 4.2 Startup Health Check

**Location:** `src/main.py:158-169`

Checks Telegram Bot API reachability on startup.

**Behavior:**
- Calls `check_telegram_available()`
- Logs INFO if reachable
- Logs WARNING if unreachable
- Catches and logs any exception during check

**Uses:**
- Bot API `getMe` endpoint for verification
- Sets initial `_is_reachable` state

---

## 5. Current Log Emission Points

### 5.1 WARNING Logs

**Startup/First failure:**
```python
# Line 401-407 in fallback.py
logger.warning(
    f"First Telegram send failure detected. "
    f"Error type: {error_type}. Error: {message}. "
    f"Subsequent failures of the same type are rate-limited (one "
    f"DEBUG summary per {self._failure_log_interval_seconds:g}s); "
    f"a different failure type is logged independently."
)
```

**New failure type during outage:**
```python
# Line 418-425 in fallback.py
logger.warning(
    f"New Telegram send failure type during ongoing outage: "
    f"{error_type}. Error: {message}. "
    f"Logged independently of the "
    f"{self._failure_log_interval_seconds:g}s same-type cooldown. "
    f"(Total failures: {self._failure_count}; distinct failure "
    f"types: {len(self._seen_failure_types)}.)"
)
```

**No bot_token configured:**
```python
# Line 130-133 in fallback.py
logger.warning(
    f"send_message() called - no Telegram bot token configured "
    f"(set ADC_TELEGRAM_BOT_TOKEN). Message send skipped."
)
```

**No chat_id configured (send_exception):**
```python
# Line 194-198 in fallback.py
logger.warning(
    f"send_exception() called for session {session_id} - "
    f"no Telegram chat id configured (set ADC_TELEGRAM_CHAT_ID). "
    f"Exception push skipped."
)
```

**No chat_id configured (send_workload_summary):**
```python
# Line 219-223 in fallback.py
logger.warning(
    f"send_workload_summary() called for session {session_id} - "
    f"no Telegram chat id configured (set ADC_TELEGRAM_CHAT_ID). "
    f"Workload summary push skipped."
)
```

**No chat_id configured (watcher _send_to_telegram):**
```python
# Line 1166-1170 in daemon.py
logger.warning(
    f"Cannot send result to Telegram for session {session_id}: "
    f"no Telegram chat id configured (set ADC_TELEGRAM_CHAT_ID). "
    f"Result push skipped."
)
```

**Startup unreachable:**
```python
# Line 164-167 in main.py
logger.warning(
    "Telegram Bot API unreachable. "
    "Telegram fallback will not be available."
)
```

### 5.2 DEBUG Logs

**Repeated failures (rate-limited):**
```python
# Line 433-437 in fallback.py
logger.debug(
    f"Repeated Telegram send failures: {batch} failure(s) since last "
    f"log (total {self._failure_count}). "
    f"Latest error type: {error_type}. Error: {message}."
)
```

**Successful send:**
```python
# Line 151 in fallback.py
logger.info(f"Sent Telegram message to chat {chat_id}")
```

### 5.3 ERROR Logs

**Bead watcher loop errors:**
```python
# Line 365 in daemon.py
logger.error(f"Error in bead watch loop: {e}", exc_info=True)
```

**Ambient monitoring loop errors:**
```python
# Line 395 in daemon.py
logger.error(f"Error in ambient monitoring loop: {e}", exc_info=True)
```

**Circuit breaker errors:**
```python
# Line 549 in daemon.py
logger.error(f"Error in circuit breaker check: {e}", exc_info=True)
```

**Monitoring result write errors:**
```python
# Line 1493 in daemon.py
logger.error(f"Error writing monitoring result for topic {topic_id}: {e}", exc_info=True)
```

**Broadcast errors:**
```python
# Line 1593 in daemon.py
logger.error(f"Error broadcasting monitoring result {result_id}: {e}", exc_info=True)
```

---

## 6. Error Handling Flow Diagram

```
send_message() called
    │
    ├─→ No bot_token configured?
    │   └─→ WARNING log → return False
    │
    ├─→ HTTP POST to Telegram Bot API
    │   │
    │   ├─→ Success (200)
    │   │   └─→ INFO log → _set_reachable(True) → return True
    │   │
    │   └─→ Failure
    │       │
    │       ├─→ httpx.RequestError?
    │       │   └─→ _handle_send_failure(exception)
    │       │
    │       ├─→ Non-200 status?
    │       │   └─→ _handle_send_failure(error_context)
    │       │
    │       └─→ Other exception?
    │           └─→ _handle_send_failure(exception)
    │
_handle_send_failure(error/error_context)
    │
    └─→ _record_failure_locked() [under lock]
        │
        ├─→ Update counters and timestamps
        │
        ├─→ First failure after startup?
        │   └─→ WARNING log (one per process startup)
        │
        ├─→ New failure type?
        │   └─→ WARNING log (immediate, per-type dedup)
        │
        └─→ Repeated failure of seen type?
            └─→ Rate-limit window elapsed?
                └─→ YES: DEBUG summary
                └─→ NO: Count silently
```

---

## 7. Configuration

### 7.1 Environment Variables

**Required for sends:**
- `ADC_TELEGRAM_BOT_TOKEN` - Bot API token
- `ADC_TELEGRAM_CHAT_ID` - Target chat ID for fallback surface

**Optional:**
- `ADC_TELEGRAM_FAILURE_LOG_INTERVAL_SECONDS` - Rate-limit window for repeated-failure DEBUG logs (default: 300)

### 7.2 Instance State

The global `TelegramFallback` singleton is accessed via `get_telegram_fallback()`.

**State includes:**
- Bot token and chat ID
- Reachability state (`_is_reachable`, `_last_check_time`)
- Failure tracking (count, timestamps, seen types)
- Rate-limit state

---

## 8. Unused Send Methods

The following higher-level send methods are **defined but never called** in the codebase (excluding tests):

1. `send_result()` - Format and send structured results
2. `send_exception()` - Send exceptions for human attention
3. `send_workload_summary()` - Send workload summaries

These methods exist as part of the public API but are not currently wired into any application flow. Only `send_message()` is actively used, via `_send_to_telegram()` in the bead watcher daemon.

---

## 9. Key Findings

1. **Single point of control:** All Telegram sends route through `send_message()` in one class
2. **Sophisticated error handling:** Rate-limited logging with per-failure-type dedup prevents log spam
3. **Graceful degradation:** Missing configuration is logged as WARNING, not a fatal error
4. **Reachability tracking:** Health state is tracked and exposed via `get_status()`
5. **Limited usage:** Only the bead watcher daemon actually sends to Telegram currently
6. **Unused API surface:** `send_exception()` and `send_workload_summary()` exist but aren't called

---

## 10. Acceptance Criteria Verification

✅ **Identified all Telegram send call sites**
   - `send_message()` in `fallback.py` (primary method)
   - `_send_to_telegram()` in `watcher/daemon.py` (only active caller)
   - `send_result()`, `send_exception()`, `send_workload_summary()` defined but unused

✅ **Documented current error handling approach**
   - Rate-limited logging: First failure = WARNING, subsequent = DEBUG (rate-limited)
   - Per-failure-type dedup: New failure types logged immediately
   - Graceful no-op on missing configuration: WARNING + return False
   - State tracking: failure_count, timestamps, seen types

✅ **Know where logs are emitted on send failure**
   - WARNING: First failure, new failure types, missing configuration
   - DEBUG: Repeated failures (rate-limited batches)
   - INFO: Successful sends
   - ERROR: Higher-level errors (watcher loop, monitoring, etc.)

---

**End of Analysis**
