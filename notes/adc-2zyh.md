# Telegram Send Locations in aide-de-camp

## Overview

This document identifies all locations in the aide-de-camp codebase where Telegram send operations occur, along with current error handling.

## Telegram Send Locations

### 1. Primary Telegram Integration (`src/telegram/fallback.py`)

#### `send_message()` - Line 47-94
**Purpose:** Send a message to a Telegram chat via telegram-claude-bridge

**Function signature:**
```python
async def send_message(
    self,
    chat_id: int | str,
    message: str,
    parse_mode: str = "HTML",
) -> bool
```

**Current error handling:**
- Catches `httpx.RequestError` for network/timeout errors
- Catches general `Exception` for unexpected errors
- Calls `_handle_send_failure()` on any error
- Returns `True` on success (status 200), `False` on failure
- First failure logs WARNING; subsequent failures log DEBUG only (rate-limited to avoid spam)

**Bridge endpoint:** `POST {bridge_url}/send`

---

#### `send_result()` - Line 96-107
**Purpose:** Send a structured result to Telegram

**Function signature:**
```python
async def send_result(self, chat_id: int | str, result: dict) -> bool
```

**Current error handling:**
- Delegates to `send_message()` - inherits its error handling
- Formats result using `_format_result_message()` before sending

---

#### `send_exception()` - Line 109-126
**Purpose:** Send an exception to Telegram for human attention

**Function signature:**
```python
async def send_exception(
    self,
    session_id: str,
    exception: dict,
) -> bool
```

**Current status:** **NOT IMPLEMENTED**
- Returns `False` immediately
- Logs warning about session→telegram_chat mapping not implemented
- telegram-claude-bridge uses pull-based architecture, not push-based

---

#### `send_workload_summary()` - Line 128-145
**Purpose:** Send a workload summary to Telegram

**Function signature:**
```python
async def send_workload_summary(
    self,
    session_id: str,
    summary: dict,
) -> bool
```

**Current status:** **NOT IMPLEMENTED**
- Returns `False` immediately
- Logs warning about session→telegram_chat mapping not implemented
- telegram-claude-bridge uses pull-based architecture, not push-based

---

### 2. Bead Watcher Daemon (`src/watcher/daemon.py`)

#### `_send_to_telegram()` - Line 215-240
**Purpose:** Send result to Telegram when a bead closes

**Function signature:**
```python
async def _send_to_telegram(self, result: dict, session_id: str) -> None
```

**Current status:** **NOT IMPLEMENTED**
- Logs warning that session→telegram_chat mapping is not implemented
- Contains commented documentation of the correct telegram-claude-bridge contract:
  ```
  POST http://telegram-claude-bridge:8000/send
  {
    "chat_id": 123456789,  # int64, REQUIRED
    "text": "message",     # string, REQUIRED
    "parse_mode": "HTML"   # string, OPTIONAL
  }
  ```

**Current error handling:**
- Logs warning on every call
- Catches general `Exception` and logs error

---

### 3. Surface Router (`src/surface/router.py`)

**No direct send operations.** This module determines routing decisions but does not perform sends itself.

---

### 4. Session Store (`src/session/store.py`)

**No direct send operations.** Contains `get_fallback_surface()` which returns the Telegram fallback surface configuration, but does not send messages.

---

### 5. Main App (`src/main.py`)

#### Startup health check - Line 149-161
**Purpose:** Check Telegram bridge reachability on startup

**Current error handling:**
- Catches general `Exception`
- Logs info/warning about bridge status
- Does not prevent app startup if bridge is unreachable

#### `/api/v1/status/telegram_bridge` endpoint - Line 1471-1479
**Purpose:** API endpoint to get Telegram bridge status

**Current error handling:**
- Catches general `Exception`
- Returns error response if status check fails

---

## Error Handling Pattern Summary

All Telegram send failures follow this pattern (implemented in `_handle_send_failure()`):

1. **First failure after startup:** Logs at WARNING level with details
2. **Subsequent failures:** Logs at DEBUG level only to avoid spam
3. **Failure tracking:** Maintains `_failure_count` and `_has_logged_first_failure` state
4. **Reachability state:** Sets `_is_reachable = False` on failure

---

## Key Findings

1. **Fully implemented:** `send_message()` and `send_result()` are the only fully functional send operations
2. **Not implemented:** `send_exception()` and `send_workload_summary()` are stubs that return `False`
3. **Bead watcher send:** `_send_to_telegram()` currently just logs a warning
4. **Architecture mismatch:** telegram-claude-bridge uses pull-based architecture (manages sessions internally per forum topic), while adc expects push-based delivery
5. **Rate limiting:** Failure logs are rate-limited to avoid spam (first failure: WARNING, subsequent: DEBUG)

---

## Contract Reference (telegram-claude-bridge)

**Send endpoint:** `POST http://telegram-claude-bridge:8000/send`

**Request body:**
```json
{
  "chat_id": 123456789,     // int64, REQUIRED - actual Telegram chat ID
  "text": "message",        // string, REQUIRED - message content
  "parse_mode": "HTML"      // string, OPTIONAL - formatting mode
}
```

**Health endpoint:** `GET http://telegram-claude-bridge:8000/health`

---

## Environment Configuration

- **Env var:** `ADC_TELEGRAM_BRIDGE_URL`
- **Default:** `http://telegram-claude-bridge:8000`
- **Override:** Constructor parameter takes precedence over env var

---

## Files Summary

| File | Lines | Send Operations | Status |
|------|-------|-----------------|--------|
| `src/telegram/fallback.py` | 47-94, 96-107, 109-126, 128-145 | `send_message()`, `send_result()`, `send_exception()`, `send_workload_summary()` | 2 implemented, 2 stubs |
| `src/watcher/daemon.py` | 215-240 | `_send_to_telegram()` | Stub (logs only) |
| `src/surface/router.py` | N/A | No direct sends | N/A |
| `src/session/store.py` | N/A | No direct sends | N/A |
| `src/main.py` | 149-161, 1471-1479 | Health check only | N/A |
