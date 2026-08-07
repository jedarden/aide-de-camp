# Telegram Send Function Structure Analysis

## Overview
Analysis of the Telegram send function in `src/telegram/fallback.py` to understand current implementation and identify modification points for failure detection.

## Send Function Location

**File**: `src/telegram/fallback.py`  
**Function**: `send_message`  
**Lines**: 118-173  
**Signature**:
```python
async def send_message(
    self,
    chat_id: int | str,
    message: str,
    parse_mode: str = "HTML",
) -> bool:
```

## Current Error Handling

The function **already has comprehensive error handling** with three failure detection branches:

### 1. HTTP Non-200 Status Handling (Lines 156-166)
```python
if response.status_code == 200:
    logger.info(f"Sent Telegram message to chat {chat_id}")
    # Update reachability state
    if not self._state_tracker.is_reachable:
        self._state_tracker.mark_as_reachable()
    self._set_reachable(True)
    return True
else:
    error_msg = f"status {response.status_code} - {response.text}"
    await self._handle_send_failure(error_context=error_msg)
    return False
```

### 2. Network Request Error Handling (Lines 168-170)
```python
except httpx.RequestError as e:
    await self._handle_send_failure(error=e)
    return False
```

### 3. Generic Exception Handling (Lines 171-173)
```python
except Exception as e:
    await self._handle_send_failure(error=e)
    return False
```

## state_tracker Module Status

**Import Location**: Line 16
```python
from .state_tracker import BridgeState
```

**Initialization**: Line 116
```python
self._state_tracker = BridgeState()
```

**Module File**: `src/telegram/state_tracker.py`

**BridgeState Class Methods**:
- `mark_as_reachable()` - Reset failure state on success
- `mark_as_unreachable(timestamp)` - Record failure with timestamp
- `should_log_failure()` - Per-failure-streak dedup (returns True once per streak)
- `is_reachable` property - Current reachability status

## Failure Detection Points

There are **three existing failure detection points** that call `_handle_send_failure`:

| Line | Condition | Error Type | Handler Call |
|------|-----------|------------|--------------|
| 165 | HTTP status != 200 | HTTPError | `_handle_send_failure(error_context=error_msg)` |
| 169 | httpx.RequestError | RequestError | `_handle_send_failure(error=e)` |
| 172 | Generic Exception | Exception | `_handle_send_failure(error=e)` |

## Failure Handling Flow

### Call Chain
```
send_message (line 118)
  ├── On HTTP failure (line 165)
  ├── On RequestError (line 169)
  └── On Exception (line 172)
      ↓
_handle_send_failure (line 336)
  └── Acquires lock, calls _record_failure_locked
      ↓
_record_failure_locked (line 370)
  ├── Marks state_tracker as unreachable (line 406)
  ├── Checks if should log failure (line 410)
  ├── Logs WARNING on first failure (lines 414-424)
  ├── Updates failure counters (lines 426-428)
  └── Handles per-failure-type dedup (lines 437-503)
```

### Current Logging Order

1. **Success Path** (Line 157):
   ```python
   logger.info(f"Sent Telegram message to chat {chat_id}")
   # Then updates reachability state
   ```

2. **Failure Path** (Lines 165, 169, 172):
   ```python
   await self._handle_send_failure(...)  # Called before return False
   ```

3. **In _record_failure_locked** (Lines 410-424):
   ```python
   if self._state_tracker.should_log_failure():
       logger.warning("Telegram bridge unreachable: send failed. ...")
   ```

## State Tracker Integration Points

The `state_tracker` module is already integrated at key points:

| Line | Location | Integration |
|------|----------|-------------|
| 159 | Success path | Checks `is_reachable` property |
| 160 | Success path | Calls `mark_as_reachable()` |
| 406 | Failure path | Calls `mark_as_unreachable(now)` |
| 410 | Failure path | Calls `should_log_failure()` for dedup |

## Key Characteristics

1. **Comprehensive Coverage**: All three failure types (HTTP, network, generic) are already handled
2. **State Tracking**: BridgeState provides per-failure-streak dedup
3. **Rate Limiting**: Implements repeated-failure cooldown windows
4. **Per-Type Dedup**: Different failure types logged independently (adc-15u0)
5. **Thread Safety**: Uses `asyncio.Lock` for serializing failure updates

## Exact Line Numbers for Modification

If modifications are needed, the key insertion points are:

- **Before try block** (line 142): Add pre-send validation
- **Inside try block** (lines 143-166): Add response validation
- **Exception handlers** (lines 168-173): Already call `_handle_send_failure`
- **_handle_send_failure** (lines 336-356): Add additional failure processing
- **_record_failure_locked** (lines 370-504): Modify logging/rate-limiting behavior

## Related Functions

Other send functions that delegate to `send_message`:

- **send_result** (lines 175-186): Formats and sends result dicts
- **send_exception** (lines 188-211): Sends exceptions to configured chat_id
- **send_workload_summary** (lines 213-236): Sends workload summaries

## Conclusion

The telegram send function structure is **well-designed and complete** with:

✅ Comprehensive error handling for all failure types  
✅ State tracking for reachability and failure deduplication  
✅ Rate-limited logging to prevent log spam  
✅ Per-failure-type dedup for independent alerting  
✅ Thread-safe failure recording with locks  

**No additional failure detection is needed** - the existing implementation handles all three failure scenarios (HTTP errors, network errors, and generic exceptions) and integrates with the state_tracker for intelligent deduplication.
