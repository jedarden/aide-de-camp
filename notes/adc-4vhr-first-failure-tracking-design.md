# First-Failure Tracking Mechanism Design

## Overview
This document defines the design for tracking and detecting the **FIRST** Telegram send failure after application startup in the aide-de-camp (adc) FastAPI application.

## Current State

The existing implementation in `src/telegram/fallback.py` already includes a basic first-failure tracking mechanism:

```python
# Current implementation
self._has_logged_first_failure = False  # Track if we've logged the first failure after startup
self._failure_count = 0
self._last_failure_logged = None

def _handle_send_failure(self, error_context: str = ""):
    self._is_reachable = False
    self._failure_count += 1
    now = datetime.now()

    if not self._has_logged_first_failure:
        # First failure after startup - log at WARNING level
        logger.warning(...)
        self._has_logged_first_failure = True
        self._last_failure_logged = now
    else:
        # Subsequent failures - log at DEBUG level
        logger.debug(...)
```

## Design Requirements

### Functional Requirements
1. **First-failure detection**: Log a WARNING on the very first Telegram send failure after application startup
2. **Subsequent failure suppression**: All subsequent failures should be logged at DEBUG level only
3. **No false positives**: Only one WARNING should ever be logged per startup sequence
4. **State persistence**: State should persist across the application lifetime

### Non-Functional Requirements
1. **Thread-safety**: The application is async FastAPI; multiple concurrent requests could trigger Telegram sends simultaneously
2. **Race-condition prevention**: Multiple concurrent failures should not result in multiple WARNING logs
3. **Performance**: Minimal overhead on the hot path (Telegram send operations)
4. **Recovery awareness**: Option to reset first-failure state after successful sends (future enhancement)

## Proposed Design

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     TelegramFallback Instance                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  FirstFailureTracker (inner class or module)                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ State:                                               │    │
│  │   - _has_logged_first_failure: bool                 │    │
│  │   - _failure_count: int                             │    │
│  │   - _first_failure_lock: asyncio.Lock (thread-safe) │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### State Storage

**Location**: Per-instance state in `TelegramFallback.__init__()`

**Rationale**:
- `TelegramFallback` is a module-level singleton (`get_telegram_fallback()`)
- Only one instance exists per application lifetime
- State survives for the entire application runtime
- State resets naturally on application restart

**State Variables**:
```python
self._failure_tracker = FirstFailureTracker()  # Encapsulated tracker
```

### Thread-Safety Design

**Problem**: In async FastAPI, multiple `send_message()` calls can execute concurrently. Without synchronization:
- Two concurrent failures could both check `if not self._has_logged_first_failure` before either sets it
- This causes race conditions → multiple WARNING logs for the "first" failure

**Solution**: Use `asyncio.Lock` to serialize the first-failure check-and-set operation:

```python
class FirstFailureTracker:
    def __init__(self):
        self._has_logged_first_failure = False
        self._lock = asyncio.Lock()  # Async lock for concurrent access

    async def record_failure(self, error_context: str) -> str:
        """
        Record a failure and return the appropriate log level.
        
        Returns:
            'WARNING' if this is the first failure, 'DEBUG' otherwise
        """
        async with self._lock:
            if not self._has_logged_first_failure:
                self._has_logged_first_failure = True
                return 'WARNING'
            return 'DEBUG'
```

**Why asyncio.Lock?**
- Designed for async/await contexts
- Non-blocking when the lock is free
- Prevents race conditions on the first-failure flag
- Minimal overhead: lock acquisition is fast, only contends briefly at startup

### Initialization

The tracker initializes on first access via `get_telegram_fallback()`:

```python
# In TelegramFallback.__init__()
self._failure_tracker = FirstFailureTracker()
```

State is **NOT** persisted across restarts — this is intentional. Each application restart gets a fresh first-failure tracking window.

### Usage Pattern

```python
async def send_message(self, chat_id, message, parse_mode="HTML"):
    try:
        # ... send logic ...
        if response.status_code == 200:
            return True
        else:
            error_msg = f"status {response.status_code}"
            await self._handle_send_failure(error_msg)
            return False
    except Exception as e:
        await self._handle_send_failure(str(e))
        return False

async def _handle_send_failure(self, error_context: str):
    log_level = await self._failure_tracker.record_failure(error_context)
    
    if log_level == 'WARNING':
        logger.warning(
            f"First Telegram send failure detected at {self.bridge_url}. "
            f"Error: {error_context}. "
            f"Subsequent failures will be logged at DEBUG level only."
        )
    else:
        logger.debug(
            f"Repeated Telegram send failure at {self.bridge_url}. "
            f"Error: {error_context}"
        )
```

### Race Condition Scenarios

**Scenario 1: Two concurrent failures at startup**
```
Time  T1: Request A fails, acquires lock
Time  T2: Request B fails, waits for lock
Time  T3: Request A sets flag, releases lock, logs WARNING
Time  T4: Request B acquires lock, sees flag=True, logs DEBUG
```
✅ **Correct**: Only one WARNING logged

**Scenario 2: Failure followed by success, then failure again**
```
Time  T1: Request A fails, logs WARNING (flag=True)
Time  T2: Request B succeeds (flag remains True)
Time  T3: Request C fails, logs DEBUG (flag already True)
```
✅ **Correct**: Only first failure ever gets WARNING

**Scenario 3: Multiple concurrent failures after first failure**
```
Time  T1: First failure already happened (flag=True)
Time  T2: Requests A, B, C all fail concurrently
Time  T3: All acquire lock, see flag=True, all log DEBUG
```
✅ **Correct**: No WARNINGs, only DEBUG logs

## Implementation Guidance

### For the next bead (implementation):

1. **Create a new module** `src/telegram/first_failure_tracker.py` with the `FirstFailureTracker` class

2. **Refactor `TelegramFallback`**:
   - Replace `_has_logged_first_failure` with `_failure_tracker: FirstFailureTracker`
   - Make `_handle_send_failure()` async (currently synchronous)
   - Update all call sites to `await self._handle_send_failure(...)`

3. **Add tests** in `tests/test_first_failure_tracker.py`:
   - Test concurrent first failures (use `asyncio.gather()`)
   - Test subsequent failures are DEBUG
   - Test flag resets after restart (manual verification)

### Migration from current implementation

**Current code**:
```python
# Instance variables in TelegramFallback.__init__
self._has_logged_first_failure = False
self._last_failure_logged = None
self._failure_count = 0

# Synchronous handler
def _handle_send_failure(self, error_context: str = ""):
    if not self._has_logged_first_failure:
        logger.warning(...)
        self._has_logged_first_failure = True
    else:
        logger.debug(...)
```

**New code**:
```python
# Encapsulated tracker
self._failure_tracker = FirstFailureTracker()

# Async handler with lock protection
async def _handle_send_failure(self, error_context: str = ""):
    log_level = await self._failure_tracker.record_failure(error_context)
    if log_level == 'WARNING':
        logger.warning(...)
    else:
        logger.debug(...)
```

## Future Enhancements

### Recovery-based reset (optional future feature)
Track whether the Telegram bridge has recovered, and reset the first-failure flag after N successful sends:

```python
class FirstFailureTracker:
    def __init__(self, reset_after_success_count: int = 5):
        self._reset_threshold = reset_after_success_count
        self._success_count_since_failure = 0

    async def record_success(self):
        async with self._lock:
            self._success_count_since_failure += 1
            if self._success_count_since_failure >= self._reset_threshold:
                self._has_logged_first_failure = False
```

This would allow WARNING-level logging for "new" failure episodes after recovery, not just the very first failure at application startup.

## Summary

The proposed design:
1. ✅ Encapsulates first-failure tracking in a dedicated class
2. ✅ Uses `asyncio.Lock` for thread-safety in async FastAPI context
3. ✅ Stores state per-instance (singleton pattern ensures global visibility)
4. ✅ Initializes on first access, resets on application restart
5. ✅ Prevents race conditions on concurrent failures
6. ✅ Maintains minimal performance overhead
7. ✅ Provides clear migration path from existing implementation
