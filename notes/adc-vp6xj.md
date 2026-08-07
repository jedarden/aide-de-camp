# Telegram Send Function Analysis (adc-vp6xj)

## Task Summary
Locate telegram send function and identify failure modes to understand how send failures are currently detected and returned.

## Findings

### 1. Telegram Send Function Location

**Primary send function**: `src/telegram/fallback.py:send_message()` (lines 118-174)

This is the core method that sends messages via Telegram Bot API.

**Secondary send function**: `src/watcher/daemon.py:_send_to_telegram()` (lines 1151-1174)

This is a wrapper used by the bead watcher to send results to Telegram.

### 2. Current Error Handling Approach

The `send_message()` function already has comprehensive error handling:

```python
async def send_message(
    self,
    chat_id: int | str,
    message: str,
    parse_mode: str = "HTML",
) -> bool:
```

**Try/except structure**:
- ✅ Already has try/except blocks (lines 142-174)
- ✅ Catches `httpx.RequestError` for network failures (lines 169-171)
- ✅ Catches general `Exception` for any other errors (lines 172-174)
- ✅ Returns `False` on any failure (lines 167, 171, 174)
- ✅ Returns `True` on success (line 163)

**Return codes indicating failure**:
- `False` - Any failure (network error, HTTP non-200, exception, missing bot token)
- `True` - Success (HTTP 200 response)

### 3. What Constitutes a Send Failure

The code identifies **four distinct failure modes**:

1. **Missing bot token** (lines 135-140):
   - `bot_token` is `None`
   - Returns `False`, logs WARNING
   - Graceful no-op behavior

2. **HTTP non-200 response** (lines 164-167):
   - Telegram API returns status code != 200
   - Error context includes status code and response body
   - Calls `_handle_send_failure(error_context=...)`

3. **Network errors** (lines 169-171):
   - `httpx.RequestError` - connection failures, timeouts, DNS errors
   - Calls `_handle_send_failure(error=e)`

4. **General exceptions** (lines 172-174):
   - Any other unexpected exception
   - Calls `_handle_send_failure(error=e)`

### 4. Error Context Captured

The error handling captures excellent context:

- **Error type**: Exception class name (e.g., `ConnectError`, `Timeout`)
- **Error message**: Exception message or HTTP response body
- **URL**: The exact Telegram API endpoint attempted
- **Timestamp**: When the failure occurred

### 5. State Tracking Implementation

**KEY FINDING**: The `state_tracker.mark_as_unreachable()` call **is already present** in the code!

**Failure handling chain**:
```
send_message() (failure)
  → _handle_send_failure() (line 166, 170, or 173)
    → _record_failure_locked() (line 370)
      → self._state_tracker.mark_as_unreachable(now) (line 427)
```

**Success handling chain**:
```
send_message() (success, HTTP 200)
  → self._state_tracker.mark_as_reachable() (line 161)
```

### 6. State Tracker Location

**State tracker class**: `src/telegram/state_tracker.py:BridgeState`

Key methods:
- `mark_as_reachable()` - Resets failure state, marks bridge as reachable
- `mark_as_unreachable(timestamp)` - Records failure, increments failure count
- `should_log_failure()` - Prevents duplicate warning logs per failure streak
- `is_reachable` property - Current reachability state

### 7. Exact Modification Points

**NO MODIFICATION NEEDED** - The state tracker is already correctly integrated!

The existing implementation:
1. ✅ Marks as unreachable on failure (`fallback.py:427`)
2. ✅ Marks as reachable on success (`fallback.py:161`)
3. ✅ Provides failure deduplication to prevent log spam
4. ✅ Captures comprehensive error context
5. ✅ Exposes status via `/api/v1/status/telegram` endpoint

### 8. Watcher Integration

The bead watcher (`src/watcher/daemon.py`) uses Telegram via:
- `_send_to_telegram()` method (lines 1151-1174)
- Calls `fallback.send_message()` (line 1174)
- Inherits all state tracking behavior automatically

## Conclusion

The telegram send function already has **robust failure detection and state tracking**. The `state_tracker.mark_as_unreachable()` call is properly integrated into the failure handling chain at `src/telegram/fallback.py:427`.

**No additional modifications are needed** to implement state tracking on send failures - it's already there!

## Key Files

1. `src/telegram/fallback.py` - Main send function with error handling
2. `src/telegram/state_tracker.py` - Bridge state tracking
3. `src/watcher/daemon.py` - Bead watcher integration
4. `src/main.py` - Status endpoint wiring

## Failure Mode Reference

| Failure Mode | Detection Location | State Update |
|--------------|-------------------|--------------|
| Missing bot token | `fallback.py:135-140` | No state update (config issue) |
| HTTP non-200 | `fallback.py:164-167` | `mark_as_unreachable()` at line 427 |
| Network error | `fallback.py:169-171` | `mark_as_unreachable()` at line 427 |
| General exception | `fallback.py:172-174` | `mark_as_unreachable()` at line 427 |
| Success (HTTP 200) | `fallback.py:157-163` | `mark_as_reachable()` at line 161 |
