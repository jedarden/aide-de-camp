# Thread-Safety Approach for Async FastAPI First-Failure State

## Overview

This document designs the thread-safety approach for safely reading/writing first-failure state across concurrent requests in the async FastAPI application. It identifies race conditions, evaluates locking mechanisms, and documents performance implications.

## Current Implementation Analysis

### Existing Code (NOT Thread-Safe)

```python
# src/telegram/fallback.py (current)
def __init__(self, bridge_url: str | None = None):
    self._has_logged_first_failure = False  # ❌ No lock protection
    self._failure_count = 0

def _handle_send_failure(self, error_context: str = ""):
    # ❌ Synchronous function - not async
    # ❌ No lock protection on check-and-set
    if not self._has_logged_first_failure:
        logger.warning("First failure...")
        self._has_logged_first_failure = True  # ❌ Race condition here
```

### Race Conditions Identified

#### Race Condition 1: Concurrent First Failures

**Scenario**: Multiple requests fail simultaneously at application startup

```
Time  T0: Request A fails → checks _has_logged_first_failure (False)
Time  T1: Request B fails → checks _has_logged_first_failure (False)
Time  T2: Request A sets flag to True, logs WARNING
Time  T3: Request B sets flag to True, logs WARNING  ❌ DUPLICATE WARNING
```

**Impact**: 
- Multiple WARNING logs for the same "first" failure
- Violates the requirement of exactly one WARNING per startup
- Log spam when bridge is down

#### Race Condition 2: Read-Write Race on failure_count

**Scenario**: Multiple concurrent failures increment the counter

```
Time  T0: failure_count = 0
Time  T1: Request A reads failure_count (0)
Time  T2: Request B reads failure_count (0)
Time  T3: Request A increments: failure_count = 1
Time  T4: Request B increments: failure_count = 1  ❌ Lost update (should be 2)
```

**Impact**:
- Inaccurate failure count
- Misleading diagnostics
- Wrong metrics for monitoring

#### Race Condition 3: Check-Then-Act on Timestamps

**Scenario**: Multiple failures update timestamps concurrently

```
Time  T0: Request A checks first_failure_timestamp (None)
Time  T1: Request B checks first_failure_timestamp (None)
Time  T2: Request A sets first_failure_timestamp = now
Time  T3: Request B sets first_failure_timestamp = now  ❌ Overwrite
```

**Impact**:
- Lost first-failure timestamp accuracy
- Difficult to correlate with logs
- Misleading diagnostics

## Locking Mechanisms Evaluation

### Option 1: asyncio.Lock (RECOMMENDED)

**Approach**:
```python
import asyncio

class TelegramFallback:
    def __init__(self):
        self._has_logged_first_failure = False
        self._failure_count = 0
        self._first_failure_lock = asyncio.Lock()  # ✅ Async-native lock

    async def _handle_send_failure(self, error_context: str = ""):
        async with self._first_failure_lock:  # ✅ Serialize critical section
            if not self._has_logged_first_failure:
                logger.warning("First failure...")
                self._has_logged_first_failure = True
                self._first_failure_timestamp = datetime.now()
                self._failure_count = 1
            else:
                logger.debug("Repeated failure...")
                self._failure_count += 1
            self._last_failure_timestamp = datetime.now()
```

**Pros**:
- ✅ Designed for async/await contexts
- ✅ Non-blocking when lock is free
- ✅ Minimal overhead (fast acquisition)
- ✅ Serializes the critical section (check + set)
- ✅ Native to FastAPI's async model
- ✅ Works with `async with` for clean syntax

**Cons**:
- Lock only works within the same event loop (not an issue for single-process FastAPI)
- Requires all call sites to `await` (good - enforces async discipline)

**Verdict**: ✅ **RECOMMENDED** - Perfect fit for async FastAPI

---

### Option 2: threading.Lock (NOT RECOMMENDED)

**Approach**:
```python
import threading

class TelegramFallback:
    def __init__(self):
        self._has_logged_first_failure = False
        self._lock = threading.Lock()  # ❌ Wrong for async

    def _handle_send_failure(self, error_context: str = ""):
        with self._lock:  # ❌ Blocking - defeats async benefits
            if not self._has_logged_first_failure:
                logger.warning("First failure...")
                self._has_logged_first_failure = True
```

**Pros**:
- Thread-safe across OS threads
- Familiar API

**Cons**:
- ❌ **Blocking**: Lock acquisition blocks the event loop
- ❌ **Wrong model**: FastAPI runs on one thread with cooperative multitasking
- ❌ **Performance risk**: Blocking call stalls all requests on that worker
- ❌ **Unnecessary**: asyncio.Lock is designed for this exact pattern

**Verdict**: ❌ **REJECTED** - Blocking in async context is anti-pattern

---

### Option 3: Module-Level Lock with Singleton (NOT RECOMMENDED)

**Approach**:
```python
# Module-level lock
_first_failure_lock = asyncio.Lock()

async def _handle_send_failure(fallback_instance, error_context: str = ""):
    async with _first_failure_lock:
        if not fallback_instance._has_logged_first_failure:
            # ...
```

**Pros**:
- Lock shared globally

**Cons**:
- ❌ **Unclear ownership**: Lock is separate from the state it protects
- ❌ **Harder to test**: Global state requires manual reset
- ❌ **Less encapsulated**: State and lock are in different places
- ❌ **No benefit**: Instance-level lock is sufficient (singleton pattern)

**Verdict**: ❌ **REJECTED** - Unnecessary complexity

---

### Option 4: Atomic Operations (NOT POSSIBLE)

**Approach**: Use atomic compare-and-swap (CAS) operations

**Problem**: 
- Python has no built-in atomic operations for objects
- `asyncio` doesn't provide atomic primitives for custom state
- Would require external libraries (e.g., `threading.atomic` - not async-aware)

**Verdict**: ❌ **NOT VIABLE** - No async-safe atomic operations in Python

---

### Option 5: Queue-Based Serialization (OVERKILL)

**Approach**: Push all failures to a queue, process sequentially

```python
class TelegramFallback:
    def __init__(self):
        self._failure_queue = asyncio.Queue()
        self._processor_task = None

    async def _process_failures(self):
        while True:
            failure = await self._failure_queue.get()
            # Process sequentially...
```

**Pros**:
- Guaranteed serialization
- Decouples failure handling from request path

**Cons**:
- ❌ **Overkill**: Full queue for a single boolean flag
- ❌ **Complex**: Requires background task lifecycle management
- ❌ **Latency**: Queue adds indirection overhead
- ❌ **Backpressure**: Could fill up if bridge is down for long time

**Verdict**: ❌ **REJECTED** - Wrong tool for the job

---

## Recommended Design: asyncio.Lock with Instance State

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│              TelegramFallback (Singleton)                │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  Instance Variables (protected by _first_failure_lock)  │
│  ┌───────────────────────────────────────────────────┐   │
│  │ _has_logged_first_failure: bool = False          │   │
│  │ _failure_count: int = 0                          │   │
│  │ _first_failure_timestamp: Optional[datetime]      │   │
│  │ _last_failure_timestamp: Optional[datetime]       │   │
│  │ _first_failure_lock: asyncio.Lock                │   │
│  └───────────────────────────────────────────────────┘   │
│                                                           │
│  Methods                                                  │
│  ├─► async _handle_send_failure()  [under lock]          │
│  └─► def get_bridge_status()        [no lock needed]     │
│                                                           │
└──────────────────────────────────────────────────────────┘

Singleton Access: get_telegram_fallback() returns the same instance
```

### Thread-Safe Implementation Pattern

#### Critical Section (Write Access)

```python
async def _handle_send_failure(self, error_context: str = ""):
    """
    Handle a send failure with thread-safe first-failure detection.
    
    All state mutations occur under lock protection to prevent
    race conditions from concurrent async requests.
    """
    async with self._first_failure_lock:  # 🔒 Serialize access
        if not self._has_logged_first_failure:
            # First failure - log at WARNING level
            logger.warning(
                f"First Telegram send failure detected at {self.bridge_url}. "
                f"Error: {error_context if error_context else 'unknown error'}. "
                f"Subsequent failures will be logged at DEBUG level only."
            )
            self._has_logged_first_failure = True  # ✅ Set under lock
            self._first_failure_timestamp = datetime.now()
            self._failure_count = 1
        else:
            # Subsequent failure - log at DEBUG level
            logger.debug(
                f"Repeated Telegram send failure #{self._failure_count + 1} "
                f"at {self.bridge_url}. "
                f"Error: {error_context if error_context else 'unknown error'}."
            )
            self._failure_count += 1  # ✅ Increment under lock
        self._last_failure_timestamp = datetime.now()  # ✅ Update under lock
```

#### Non-Critical Section (Read Access)

```python
def get_bridge_status(self) -> dict:
    """
    Get the current bridge status.
    
    Read operations do NOT require the lock as they:
    - Read immutable values (bool, int)
    - Don't require cross-field consistency
    - Are used for status/reporting, not decision-making
    """
    return {
        "reachable": self._is_reachable,
        "bridge_url": self.bridge_url,
        "failure_count": self._failure_count,  # ✅ Safe to read (no lock)
        "has_logged_first_failure": self._has_logged_first_failure,  # ✅ Safe
        "first_failure_timestamp": self._first_failure_timestamp.isoformat() 
            if self._first_failure_timestamp else None,
        "last_failure_timestamp": self._last_failure_timestamp.isoformat() 
            if self._last_failure_timestamp else None,
    }
```

### Lock Acquisition Flow (Concurrent Failures)

```
Request A fails          Request B fails          Request C fails
     │                        │                        │
     ▼                        ▼                        ▼
 Acquire lock? YES      Acquire lock? NO       Acquire lock? NO
 (wait for lock)        (queued)               (queued)
     │                        │                        │
     ▼                        │                        │
 Check flag=False          │                        │
 Log WARNING               │                        │
 Set flag=True             │                        │
 Update timestamps         │                        │
 Release lock              │                        │
     │                        ▼                        │
     │                   Acquire lock? YES            │
     │                   (wait for lock)              │
     │                        │                        │
     │                        ▼                        │
     │                   Check flag=True              │
     │                   Log DEBUG                   │
     │                   Increment count              │
     │                   Update timestamp             │
     │                   Release lock                 │
     │                        │                        ▼
     └────────────────────────┴─────────────────── Acquire lock? YES
                                                          (wait for lock)
                                                               │
                                                               ▼
                                                          Check flag=True
                                                          Log DEBUG
                                                          Increment count
                                                          Update timestamp
                                                          Release lock

Result: 1 WARNING, 2 DEBUG logs ✅ Correct
```

## Performance Implications

### Lock Contention Analysis

#### Scenario 1: Bridge Healthy (No Failures)
**Lock usage**: None (no failures, no lock acquisition)
**Performance impact**: Zero ✅

#### Scenario 2: First Failure at Startup
**Lock usage**: Single acquisition for ~1-2ms (logging + state updates)
**Performance impact**: Negligible ✅
- Only one WARNING log ever
- Lock is held for microseconds
- No contention (first failure is rare)

#### Scenario 3: Multiple Concurrent Failures (Bridge Down)
**Lock usage**: Each failing request acquires lock sequentially
**Performance impact**: Minimal ✅
- Lock acquisition is fast (~0.1ms when free)
- Contention only occurs when bridge is down (already degraded state)
- Each request waits 1-2ms max for lock
- Total latency increase: 2-5ms per request (acceptable)

#### Scenario 4: High Traffic with Bridge Down
**Lock usage**: Many requests queuing for lock
**Performance impact**: Bounded ✅
- Worst case: N requests queue, each takes 2ms under lock
- Total queue wait time: N × 2ms
- Example: 100 concurrent failures = 200ms total wait = 2ms average per request
- **Why this is acceptable**:
  - Bridge is already down (latency doesn't matter for failed sends)
  - Sends are already failing (no "happy path" to optimize)
  - Logging overhead dominates (2ms lock is <10% of total)

### Performance Measurements (Estimated)

| Operation | Time (without lock) | Time (with lock) | Overhead |
|-----------|-------------------|-----------------|----------|
| Successful send | ~50ms | ~50ms | 0% (no lock used) |
| First failure | ~10ms (logging) | ~12ms | +20% (2ms lock) |
| Subsequent failure | ~5ms (DEBUG log) | ~7ms | +40% (2ms lock) |
| Status check | <1ms | <1ms | 0% (no lock) |

**Conclusion**: Lock overhead is negligible (<5ms) and only affects the error path (already slow).

### Alternatives Considered for Performance

#### Option: Lock-Free with Compare-And-Swap
**Rejected**: No async-safe CAS operations in Python

#### Option: Per-Request State
**Rejected**: Would violate "one WARNING per startup" requirement

#### Option: Queue-Based Delegation
**Rejected**: Overkill for simple boolean flag

## Implementation Checklist

For the implementation bead (adc-44u or similar):

- [ ] Add `import asyncio` to `src/telegram/fallback.py`
- [ ] Add `self._first_failure_lock = asyncio.Lock()` to `__init__()`
- [ ] Make `_handle_send_failure()` async (add `async`)
- [ ] Wrap all state mutations in `async with self._first_failure_lock:`
- [ ] Update all call sites to `await self._handle_send_failure(...)`
- [ ] Add tests for concurrent failures using `asyncio.gather()`
- [ ] Add test for race condition prevention
- [ ] Verify only one WARNING is logged for N concurrent failures

## Testing Strategy

### Test 1: Concurrent First Failures
```python
async def test_concurrent_first_failures():
    """Verify only one WARNING is logged when multiple requests fail concurrently."""
    fallback = TelegramFallback()
    
    # Trigger 10 concurrent failures
    await asyncio.gather(*[
        fallback._handle_send_failure(f"error{i}")
        for i in range(10)
    ])
    
    # Verify state
    assert fallback._has_logged_first_failure == True
    assert fallback._failure_count == 10
    
    # Verify logs (count WARNING vs DEBUG)
    # Should see: 1 WARNING, 9 DEBUG
```

### Test 2: Sequential Failures After First
```python
async def test_sequential_failures():
    """Verify subsequent failures log at DEBUG level."""
    fallback = TelegramFallback()
    
    # First failure
    await fallback._handle_send_failure("error1")
    assert fallback._has_logged_first_failure == True
    assert fallback._failure_count == 1
    
    # Subsequent failures
    await fallback._handle_send_failure("error2")
    await fallback._handle_send_failure("error3")
    
    assert fallback._failure_count == 3
    # Should see: 1 WARNING, 2 DEBUG
```

### Test 3: No Lock Contention on Success
```python
async def test_no_lock_on_success():
    """Verify successful sends don't acquire the lock."""
    fallback = TelegramFallback()
    
    # Mock successful send
    with patch.object(fallback, '_send_http_request', return_value=True):
        await fallback.send_message("chat_id", "message")
    
    # State unchanged, lock never acquired
    assert fallback._failure_count == 0
```

## Summary

### Race Conditions Prevented
1. ✅ **Duplicate WARNING logs**: Lock serializes check-and-set of `_has_logged_first_failure`
2. ✅ **Lost updates on counter**: Lock protects `failure_count` increment
3. ✅ **Timestamp overwrites**: Lock protects timestamp assignments

### Locking Strategy
- **Mechanism**: `asyncio.Lock` (async-native, non-blocking)
- **Scope**: Instance-level lock in `TelegramFallback` singleton
- **Critical section**: All state mutations in `_handle_send_failure()`
- **Non-critical**: Read-only access (`get_bridge_status()`) requires no lock

### Performance Impact
- **Happy path** (successful sends): Zero overhead (no lock acquisition)
- **Error path** (failures): +2-5ms per request (negligible, only affects degraded state)
- **Worst case** (100 concurrent failures): ~200ms total queue wait = 2ms per request average

### Why This Approach Works
1. ✅ **Matches FastAPI architecture**: Async-native, non-blocking
2. ✅ **Simple**: Single lock, clear critical section
3. ✅ **Performant**: Minimal overhead, only on error path
4. ✅ **Correct**: Prevents all identified race conditions
5. ✅ **Maintainable**: Clear pattern, easy to test

### Migration Path
From current (sync, no lock) → new (async, with lock):
1. Add lock to `__init__()`
2. Make `_handle_send_failure()` async
3. Wrap state mutations in `async with self._first_failure_lock:`
4. Update all call sites to `await self._handle_send_failure(...)`
