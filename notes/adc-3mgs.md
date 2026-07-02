# Telegram Send Locations and Error Handling

## Summary

This document identifies all locations in the aide-de-camp codebase where Telegram send attempts occur and documents their current error handling patterns.

## Key Finding

**The primary Telegram send method (`send_message` in `src/telegram/fallback.py`) is never actually called with real messages.** All calls to Telegram send are currently stubs that log warnings and return `False` due to missing session→telegram_chat_id mapping.

## Location 1: `src/telegram/fallback.py` - Primary Send Implementation

### Method: `send_message()`

**File:** `src/telegram/fallback.py` (lines 44-93)

**Signature:**
```python
async def send_message(
    self,
    chat_id: int | str,
    message: str,
    parse_mode: str = "HTML",
) -> bool:
```

**Purpose:** Send a message to a Telegram chat via telegram-claude-bridge proxy.

**Error Handling:**
- Catches `httpx.RequestError` for network/connection issues
- Catches generic `Exception` for all other errors
- Calls `_handle_send_failure()` on failure (see below)
- Logs at `DEBUG` level for failures
- Returns `bool` success indicator

**Failure Information Available:**
- `httpx.RequestError` exception includes connection details
- HTTP response status code and text
- Raw exception message

**Current Behavior:**
- Success (200): Logs at INFO, updates `_is_reachable = True`, returns `True`
- Non-200 status: Logs at DEBUG with status code and response text
- Request error: Logs at DEBUG with exception message

**Rate-Limited Warning Logging:**
The `_handle_send_failure()` method (lines 197-212) implements intelligent warning logging:
- Only logs WARNING on first failure or if >60 seconds since last logged failure
- Subsequent failures logged at DEBUG only (prevents log spam)
- Tracks `_failure_count` and `_last_failure_logged` timestamp

### Method: `send_result()`

**File:** `src/telegram/fallback.py` (lines 95-106)

**Purpose:** Send structured result to Telegram.

**Current Behavior:**
- Formats result via `_format_result_message()`
- Delegates to `send_message()`
- Inherently has same error handling

### Method: `send_exception()`

**File:** `src/telegram/fallback.py` (lines 108-125)

**Purpose:** Send exception to Telegram for human attention.

**Current Behavior:**
- **NOT IMPLEMENTED** - Logs WARNING and returns `False`
- Warning: "session→telegram_chat mapping not implemented"

### Method: `send_workload_summary()`

**File:** `src/telegram/fallback.py` (lines 127-144)

**Purpose:** Send workload summary to Telegram.

**Current Behavior:**
- **NOT IMPLEMENTED** - Logs WARNING and returns `False`
- Warning: "session→telegram_chat mapping not implemented"

## Location 2: `src/watcher/daemon.py` - Bead Watcher Telegram Send

### Method: `_send_to_telegram()`

**File:** `src/watcher/daemon.py` (lines 215-241)

**Purpose:** Send result to Telegram when bead is closed and target surface is Telegram.

**Error Handling:**
- Catches generic `Exception` 
- Logs at ERROR level
- No return value (void)

**Failure Information Available:**
- Generic exception message

**Current Behavior:**
- **NOT IMPLEMENTED** - Logs WARNING and exits
- Warning explains: "session→telegram_chat mapping not implemented. telegram-claude-bridge uses pull-based architecture (per forum topic sessions)."
- Includes reference contract comment for future implementation

**Call Chain:**
1. `_process_bead_event()` → line 172 (when surface.type == "telegram")
2. `_process_bead_event()` → line 182 (when fallback_used is True)

### Helper Method: `_format_telegram_message()`

**File:** `src/watcher/daemon.py` (lines 242-266)

**Purpose:** Format result as Telegram message.

**Current Behavior:**
- Constructs message with urgency emoji
- Includes bead_id from result data
- Not currently called (send is stubbed)

## Location 3: `src/main.py` - Startup Bridge Check

### Method: `startup()` - Bridge Reachability Check

**File:** `src/main.py` (startup event handler)

**Purpose:** Check if telegram-claude-bridge is reachable at startup.

**Error Handling:**
- Catches generic `Exception`
- Logs at WARNING level

**Current Behavior:**
- Calls `telegram_fallback.check_bridge_available()`
- Logs INFO if reachable
- Logs WARNING if unreachable
- Logs WARNING if check fails

### API Endpoint: `api_v1_telegram_bridge_status()`

**File:** `src/main.py` (endpoint handler)

**Purpose:** Expose bridge status via REST API.

**Error Handling:**
- Catches generic `Exception`
- Returns 500 error with message
- Logs at ERROR level

## Error Handling Pattern Summary

### Logging Levels by Error Type

| Error Type | Level | Location |
|------------|-------|----------|
| First bridge failure in batch | WARNING | `fallback.py:207` |
| Subsequent failures (<60s) | DEBUG | `fallback.py:82,88,92` |
| Request error (network) | DEBUG | `fallback.py:88` |
| Generic send error | DEBUG | `fallback.py:92` |
| Daemon Telegram send error | ERROR | `daemon.py:240` |
| Startup check failure | WARNING | `main.py:startup` |
| Status API error | ERROR | `main.py:api_v1_telegram_bridge_status` |
| Unimplemented send methods | WARNING | `fallback.py:120,139` |

### State Tracking

**`TelegramFallback` instance maintains:**
- `_is_reachable`: bool or None (None=unknown, True=reachable, False=unreachable)
- `_failure_count`: int (total failures)
- `_last_failure_logged`: datetime or None (for rate limiting)

## Information Available at Failure Points

### In `send_message()` failures:

1. **HTTP Status Code**: Available via `response.status_code`
2. **HTTP Response Text**: Available via `response.text`
3. **RequestError Exception**: Includes connection/host details
4. **Generic Exception**: Exception type and message

### In `_send_to_telegram()` failures:

1. **Generic Exception**: Exception type and message only
2. **Context**: session_id (passed but not used in current stub)
3. **Result data**: result dict (passed but not used in current stub)

## Root Cause Limitation

All actual message sending is blocked by **missing session→telegram_chat_id mapping**:

```
session→telegram_chat mapping not implemented. 
telegram-claude-bridge uses pull-based architecture (per forum topic sessions).
```

This means:
- `chat_id` required by telegram-claude-bridge API is not available
- Current architecture assumes pull-based (bridge manages sessions)
- Need either:
  1. Session→chat_id mapping table/database
  2. Architecture change to push-based with registration
  3. Always send to a default monitoring channel

## Recommendations

1. **Define the target delivery model**: Are we sending to a fixed monitoring channel, or per-user chat sessions?
2. **If per-user**: Implement session→telegram_chat_id persistence
3. **If monitoring channel**: Use hardcoded chat_id for ops alerts
4. **Enhance error logging**: Include `chat_id`, `message_length`, `response_body` in failure logs
5. **Consider structured logging**: Use JSON logging for better parsing of failure context
