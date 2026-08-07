# Telegram Send Function Analysis (Bead adc-vp6xj)

## Summary
Located and analyzed the telegram send function in the aide-de-camp codebase. Current failure detection is comprehensive and well-integrated with state tracking.

## Primary Send Function Location

**File:** `src/telegram/fallback.py`  
**Method:** `send_message()`  
**Lines:** 118-174

## Failure Detection Mechanisms

### 1. Configuration Failure (Lines 135-140)
```python
if self.bot_token is None:
    logger.warning("send_message() called - no Telegram bot token configured")
    return False
```
- **Detection:** No bot token configured
- **Return:** `False`
- **State impact:** Does NOT update state tracker
- **Error context:** Logged as WARNING

### 2. HTTP Failure (Lines 164-167)
```python
else:  # response.status_code != 200
    error_msg = f"status {response.status_code} - {response.text}"
    await self._handle_send_failure(error_context=error_msg, url=url)
    return False
```
- **Detection:** Non-200 HTTP response
- **Return:** `False`
- **State impact:** DOES update state tracker via `_handle_send_failure()`
- **Error context:** Status code + response body

### 3. Network Request Error (Lines 169-171)
```python
except httpx.RequestError as e:
    await self._handle_send_failure(error=e, url=...)
    return False
```
- **Detection:** HTTP client errors (network, DNS, timeout)
- **Return:** `False`
- **State impact:** DOES update state tracker via `_handle_send_failure()`
- **Error context:** Exception type + message

### 4. Generic Exception (Lines 172-174)
```python
except Exception as e:
    await self._handle_send_failure(error=e, url=...)
    return False
```
- **Detection:** Any unhandled exception
- **Return:** `False`
- **State impact:** DOES update state tracker via `_handle_send_failure()`
- **Error context:** Exception type + message

## Return Codes

- **`True`** — Successful send (HTTP 200 response)
- **`False`** — All failure paths

## Error Context Captured

The `_handle_send_failure()` method (lines 348-370) captures:
1. **Exception type** (`type(error).__name__`)
2. **Exception message** (`str(error)`)
3. **HTTP context** (status code + response text for non-200)
4. **Target URL** (attempted endpoint)
5. **Timestamp** (when failure occurred)

## State Tracker Integration

The `state_tracker.mark_as_unreachable()` is **ALREADY implemented** at line 427 in `_record_failure_locked()`:

```python
# STATE UPDATE FIRST - Update state tracker for reachability and deduplication
# This MUST be called before any logging to ensure state is updated first
self._state_tracker.mark_as_unreachable(now)
```

### Where mark_as_unreachable() is Called

1. **`send_message()` failure path** (indirectly via `_handle_send_failure()` → `_record_failure_locked()` at line 427)
   - Called for HTTP errors, network errors, and exceptions
   
2. **`check_telegram_available()` failure** (line 251, 274)
   - Called during health check failures

### Current State Tracker Behavior

The state tracker (`src/telegram/state_tracker.py`) provides:
- **Failure counting** — increments on each `mark_as_unreachable()` call
- **Timestamp tracking** — records last failure time
- **Failure streak detection** — resets to 1 when transitioning from reachable → unreachable
- **Logging control** — `should_log_failure()` returns True only once per failure streak

## Related Send Functions

### High-level wrappers that call `send_message()`:

1. **`send_result()`** (lines 176-187)
   - Formats result dict as message
   - Calls `send_message()`
   - Returns boolean success

2. **`send_exception()`** (lines 189-212)
   - Formats exception as message
   - Routes to configured `chat_id`
   - Returns boolean success

3. **`send_workload_summary()`** (lines 214-237)
   - Formats summary as message
   - Routes to configured `chat_id`
   - Returns boolean success

## Usage in Watcher Daemon

The watcher daemon (`src/watcher/daemon.py`) uses telegram send at:
- **Method:** `_send_to_telegram()` (line 1151)
- **Call pattern:** `await fallback.send_message(fallback.chat_id, message)` (line 1174)
- **Return handling:** Boolean result is returned but not currently used for state management

## Key Findings

✅ **Comprehensive failure detection** — All failure paths are caught and handled  
✅ **State tracking already integrated** — `mark_as_unreachable()` is called in all failure paths  
✅ **Detailed error context** — Exception type, message, and URL are captured  
✅ **Return code consistency** — All failures return `False`, success returns `True`  
✅ **Logging strategy** — First failure logs WARNING, subsequent failures rate-limited to DEBUG  

## What Constitutes a Send Failure

A send failure is when `send_message()` returns `False`, which occurs when:
1. Bot token is not configured
2. HTTP response status code is not 200
3. Network request fails (timeout, DNS error, connection refused)
4. Any unexpected exception is raised

## Modification Point for State Tracker

**No modification needed** — `state_tracker.mark_as_unreachable()` is already properly integrated in the failure handling path at line 427 of `src/telegram/fallback.py`.

The integration is correct because:
- It's called BEFORE any logging (STATE UPDATE FIRST pattern)
- It's in the locked section (`_record_failure_locked`) ensuring atomic updates
- It's called for ALL failure types (HTTP errors, network errors, exceptions)
- It includes proper timestamp tracking
